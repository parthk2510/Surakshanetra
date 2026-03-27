# -*- coding: utf-8 -*-
"""
STEP 2 – Isolation Forest (unsupervised anomaly detector)
"""

import pandas as pd
import numpy as np
import joblib
import sys
import time
from datetime import datetime

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    classification_report, roc_auc_score,
    average_precision_score, confusion_matrix,
)

from ..utils.config import DATA_DIR, MODEL_DIR, LOG_DIR, EPS
from ..utils.logger import get_logger

log = get_logger(__name__)

IF_FEATURES = [
    "avg_amount_sent", "max_amount_sent", "total_amount_sent",
    "max_send_velocity_1h", "max_session_count_day",
    "max_unique_counterparties_24h", "sender_degree",
    "avg_amount_received", "total_amount_received",
    "max_recv_velocity_1h", "receiver_degree",
    "total_txns_as_sender", "total_txns_as_receiver",
    "in_out_velocity_ratio", "burst_score",
    "fan_out_ratio", "recv_to_send_ratio",
]


def load_data():
    log.info("=" * 55)
    log.info("STEP 2: ISOLATION FOREST")
    log.info("=" * 55)

    features_path = DATA_DIR / "account_features.csv"
    labels_path = DATA_DIR / "account_labels.csv"

    log.info(f"Loading {features_path} …")
    feats = pd.read_csv(features_path)
    log.info(f"Shape: {feats.shape}")

    log.info(f"Loading {labels_path} …")
    labs = pd.read_csv(labels_path)
    log.info(f"Shape: {labs.shape}")

    df = feats.merge(labs, on="account_id", how="left")
    df["label"] = df["label"].fillna(0).astype(int)

    n_fraud = df["label"].sum()
    n_benign = (df["label"] == 0).sum()
    log.info(
        f"Merged {len(df):,} accounts | fraud={n_fraud:,} ({df['label'].mean():.2%}) | benign={n_benign:,}"
    )

    present = [c for c in IF_FEATURES if c in df.columns]
    missing = [c for c in IF_FEATURES if c not in df.columns]
    if missing:
        log.warning(f"Missing features (skipped): {missing}")
    log.info(f"Using {len(present)}/{len(IF_FEATURES)} features")
    return df, present


def train(df, features):
    log.info("-" * 55)
    log.info("TRAINING ISOLATION FOREST")
    log.info("-" * 55)

    X = df[features].fillna(0).values
    log.info(f"Feature matrix shape: {X.shape}")

    log.info("Fitting StandardScaler …")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # contamination = fraud rate (clamped to a sensible range)
    contamination = float(df["label"].mean())
    contamination = max(0.01, min(contamination, 0.5))
    log.info(f"Contamination parameter: {contamination:.4f}")

    log.info("Fitting IsolationForest (n_estimators=200) …")
    t0 = time.time()
    model = IsolationForest(
        n_estimators=200,
        max_samples="auto",
        contamination=contamination,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_scaled)
    log.info(f"  Training time: {time.time() - t0:.2f}s")
    return model, scaler, X_scaled


def score_and_evaluate(model, X_scaled, df, features):
    log.info("-" * 55)
    log.info("SCORING + EVALUATION")
    log.info("-" * 55)

    raw = model.decision_function(X_scaled)
    anomaly_score = 1 - (raw - raw.min()) / (raw.max() - raw.min() + 1e-9)
    preds = (model.predict(X_scaled) == -1).astype(int)

    log.info(
        f"Anomaly score range: [{anomaly_score.min():.4f}, {anomaly_score.max():.4f}]")
    log.info(f"Mean score: {anomaly_score.mean():.4f}")
    log.info(
        f"Flagged as anomaly: {preds.sum():,} / {len(preds):,} ({preds.mean():.2%})")

    y_true = df["label"].values
    log.info("\nClassification Report:")
    report = classification_report(
        y_true, preds, target_names=["Benign", "Fraud"])
    for line in report.strip().split("\n"):
        log.info(f"  {line}")

    if len(np.unique(y_true)) > 1:
        auroc = roc_auc_score(y_true, anomaly_score)
        auprc = average_precision_score(y_true, anomaly_score)
        log.info(f"AUROC : {auroc:.4f}")
        log.info(f"AUPRC : {auprc:.4f}")

    cm = confusion_matrix(y_true, preds, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    log.info(f"Confusion Matrix: TP={tp:,} FP={fp:,} FN={fn:,} TN={tn:,}")
    log.info(f"False Positive Rate: {fp/(fp+tn+1e-9):.4f}")

    result = pd.DataFrame({
        "account_id":    df["account_id"].values,
        "anomaly_score": anomaly_score,
        "anomaly_flag":  preds,
        "label":         y_true,
    })
    return result


def run():
    df, features = load_data()
    model, scaler, X_scaled = train(df, features)
    result = score_and_evaluate(model, X_scaled, df, features)

    # Persist artefacts ----------------------------------------------------
    out_path = DATA_DIR / "anomaly_scores.csv"
    result.to_csv(out_path, index=False)
    log.info(f"Saved: {out_path}")

    joblib.dump(model, MODEL_DIR / "isolation_forest.pkl")
    joblib.dump(scaler, MODEL_DIR / "if_scaler.pkl")
    joblib.dump(features, MODEL_DIR / "if_feature_columns.pkl")
    log.info(
        f"Saved: {MODEL_DIR / 'isolation_forest.pkl'} | "
        f"{MODEL_DIR / 'if_scaler.pkl'} | {MODEL_DIR / 'if_feature_columns.pkl'}"
    )
    log.info("STEP 2 COMPLETE")


if __name__ == "__main__":
    run()
