# -*- coding: utf-8 -*-
"""
STEP 5 – Combine Isolation‑Forest anomaly scores with RGCN fraud probabilities.
"""

import pandas as pd
import numpy as np
import time
from datetime import datetime

from ..utils.config import DATA_DIR, OUTPUT_DIR, LOG_DIR, EPS
from ..utils.logger import get_logger

log = get_logger(__name__)

# These are the *business* weights you can tune in a config file later.
IF_WEIGHT = 0.40
RGCN_WEIGHT = 0.60
RISK_THRESHOLD = 0.50


def load_all():
    log.info("=" * 55)
    log.info("STEP 5: SCORE MERGING")
    log.info("=" * 55)

    # ----------------------------------------------------------------
    # 1️⃣ Load anomaly (`step2`) and RGCN (`step4`) scores
    # ----------------------------------------------------------------
    anomaly = pd.read_csv(
        DATA_DIR / "anomaly_scores.csv")[["account_id", "anomaly_score", "anomaly_flag"]]
    log.info(f"Anomaly rows: {len(anomaly):,}")

    rgcn = pd.read_csv(
        DATA_DIR / "rgcn_probabilities.csv")[["account_id", "fraud_probability"]]
    log.info(f"RGCN rows: {len(rgcn):,}")

    # ----------------------------------------------------------------
    # 2️⃣ Load ground‑truth labels (optional, for evaluation)
    # ----------------------------------------------------------------
    labels = pd.read_csv(
        DATA_DIR / "account_labels.csv")[["account_id", "label"]]
    log.info(f"Label rows: {len(labels):,}")

    # ----------------------------------------------------------------
    # 3️⃣ Merge everything (outer → keep accounts that may appear only in one source)
    # ----------------------------------------------------------------
    df = anomaly.merge(rgcn, on="account_id", how="outer")
    df = df.merge(labels, on="account_id", how="left")
    # Fill missing values with zeros (the model never saw them)
    df["anomaly_score"] = df["anomaly_score"].fillna(0.0)
    df["fraud_probability"] = df["fraud_probability"].fillna(0.0)
    df["anomaly_flag"] = df["anomaly_flag"].fillna(0).astype(int)
    df["label"] = df["label"].fillna(0).astype(int)

    # ----------------------------------------------------------------
    # 4️⃣ Optional community info (used later by the UI)
    # ----------------------------------------------------------------
    community_path = DATA_DIR / "community_assignments.csv"
    if community_path.exists():
        log.info("Loading community_assignments.csv …")
        community = pd.read_csv(community_path)
        df = df.merge(community, on="account_id", how="left")
        df["community_id"] = df["community_id"].fillna(-1).astype(int)
        log.info(
            f"   {community['community_id'].nunique()} communities merged")
    else:
        log.warning("Community file missing – setting to -1")
        df["community_id"] = -1

    log.info(f"Merged dataframe rows: {len(df):,}")
    return df


def compute_scores(df):
    log.info("-" * 55)
    log.info(
        f"COMPUTING FINAL RISK SCORE (IF={IF_WEIGHT}, RGCN={RGCN_WEIGHT})")

    df["final_risk_score"] = IF_WEIGHT * df["anomaly_score"] + \
        RGCN_WEIGHT * df["fraud_probability"]
    log.info(
        f"Risk range: [{df['final_risk_score'].min():.4f}, {df['final_risk_score'].max():.4f}], mean={df['final_risk_score'].mean():.4f}")

    # Risk‑tier buckets – adjust the cuts to match your product needs
    bins = [0.0, 0.35, 0.60, 0.80, 1.01]
    labels = ["Low", "Medium", "High", "Critical"]
    df["risk_tier"] = pd.cut(df["final_risk_score"],
                             bins=bins, labels=labels, right=False).astype(str)

    # Binary flag for “should we block / investigate?”
    df["predicted_fraud"] = (df["final_risk_score"] >=
                             RISK_THRESHOLD).astype(int)

    # Human‑readable source of the flag
    df["flag_source"] = "none"
    df.loc[df["anomaly_flag"] == 1, "flag_source"] = "isolation_forest"
    df.loc[df["fraud_probability"] >= 0.5, "flag_source"] = "rgcn"
    both = (df["anomaly_flag"] == 1) & (df["fraud_probability"] >= 0.5)
    df.loc[both, "flag_source"] = "both"

    # Quick distribution logging
    log.info("Risk tier distribution:")
    for tier in ["Critical", "High", "Medium", "Low"]:
        n = (df["risk_tier"] == tier).sum()
        log.info(f"  {tier:<9}: {n:,} ({n/len(df):.1%})")

    log.info("Flag source breakdown:")
    for src, n in df["flag_source"].value_counts().items():
        log.info(f"  {src:<20}: {n:,}")

    return df


def evaluate(df):
    log.info("-" * 55)
    log.info("EVALUATION REPORT")
    y_true = df["label"].values
    y_pred = df["predicted_fraud"].values
    y_score = df["final_risk_score"].values

    from sklearn.metrics import (
        classification_report, roc_auc_score,
        average_precision_score, confusion_matrix, f1_score,
    )

    report = classification_report(y_true, y_pred, labels=[0, 1],
                                   target_names=["Benign", "Fraud"], zero_division=0)
    log.info("\nCombined system (IF + RGCN) classification report:\n" + report)

    if len(np.unique(y_true)) > 1:
        auroc = roc_auc_score(y_true, y_score)
        auprc = average_precision_score(y_true, y_score)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        log.info(f"AUROC={auroc:.4f} | AUPRC={auprc:.4f} | F1={f1:.4f}")

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    fpr = fp / (fp + tn + 1e-9)
    log.info(
        f"Confusion matrix: TP={tp:,} FP={fp:,} FN={fn:,} TN={tn:,} (FPR={fpr:.4f})")

    # Community‑ring detection (if you have communities)
    if "community_id" in df.columns and df["community_id"].nunique() > 1:
        rings = (
            df[df["community_id"] != -1]
            .groupby("community_id")
            .agg(total=("account_id", "count"),
                 fraud=("label", "sum"),
                 avg_risk=("final_risk_score", "mean"))
            .reset_index()
        )
        rings["is_fraud_ring"] = (
            rings["fraud"] / rings["total"] >= 0.5).astype(int)
        total_rings = len(rings)
        detected = rings["is_fraud_ring"].sum()
        log.info(
            f"Ring detection: {detected}/{total_rings} ({detected/total_rings:.2%})")

    # Write a pretty‑printed text file for auditors
    lines = ["="*65, " FRAUD DETECTION – EVALUATION REPORT ", "="*65,
             "\n-- Classification report --\n", report,
             f"\nAUROC = {auroc:.4f}" if len(np.unique(y_true)) > 1 else "",
             f"AUPRC = {auprc:.4f}" if len(np.unique(y_true)) > 1 else "",
             f"F1    = {f1:.4f}" if len(np.unique(y_true)) > 1 else "",
             f"\nConfusion matrix: TP={tp:,} FP={fp:,} FN={fn:,} TN={tn:,}",
             f"FPR={fpr:.4f}",
             ]
    if "community_id" in df.columns:
        lines.append(
            f"\nRing detection: {detected}/{total_rings} ({detected/total_rings:.2%})")
    full_report = "\n".join(str(l) for l in lines if l != "")
    out_path = OUTPUT_DIR / "evaluation_report.txt"
    out_path.write_text(full_report)
    log.info(f"Saved evaluation report to {out_path}")


def run():
    start = time.time()
    df = load_all()
    df = compute_scores(df)
    evaluate(df)

    # Write the final CSV that the API will serve
    out_cols = [
        "account_id", "anomaly_score", "anomaly_flag", "fraud_probability",
        "final_risk_score", "risk_tier", "predicted_fraud", "flag_source",
        "community_id", "label",
    ]
    out_path = DATA_DIR / "final_scores.csv"
    df[out_cols].to_csv(out_path, index=False)
    log.info(f"Saved final scores to {out_path} ({len(df):,} rows)")
    log.info(f"STEP 5 COMPLETE in {time.time() - start:.2f}s")


if __name__ == "__main__":
    run()
