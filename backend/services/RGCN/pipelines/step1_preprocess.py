# -*- coding: utf-8 -*-
"""
STEP 1 – Preprocess raw transaction data.
"""

import pandas as pd
import numpy as np
import sys
import time
from datetime import datetime

from ..utils.config import DATA_DIR, LOG_DIR, EPS
from ..utils.logger import get_logger

log = get_logger(__name__)

# ── Helper – timer context manager ──────────────────────────────────────


class _Timer:
    def __init__(self, fn_name: str):
        self.fn_name = fn_name

    def __enter__(self):
        self.start = time.time()
        log.info(f"  --> Starting: {self.fn_name}")
        return self

    def __exit__(self, *_):
        elapsed = time.time() - self.start
        log.info(f"  <-- Done: {self.fn_name} ({elapsed:.2f}s)")


def timer(fn_name: str):
    return _Timer(fn_name)

# ── Load dataset (parquet or csv) ───────────────────────────────────────


def load_dataset(path: str) -> pd.DataFrame:
    log.info(f"Loading dataset from: {path}")
    if not Path(path).exists():
        raise FileNotFoundError(path)

    with timer("read parquet/csv"):
        if path.endswith(".parquet"):
            try:
                import polars as pl
                df = pl.read_parquet(path).to_pandas()
                log.info("  Using polars for parquet read (fast)")
            except Exception as e:
                log.warning(f"  Polars failed ({e}); falling back to pandas")
                df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path)

    log.info(f"Shape: {len(df):,} rows × {df.shape[1]} cols")
    log.info(f"Columns: {list(df.columns)}")
    log.info(f"Memory: {df.memory_usage(deep=True).sum() / 1024**2:.1f} MiB")
    for col in df.columns:
        nulls = df[col].isna().sum()
        null_pct = nulls / len(df) * 100
        suffix = f"{null_pct:.1f}% null" if nulls else "no nulls"
        log.info(f"  {col:<45} dtype={str(df[col].dtype):<12} {suffix}")

    return df

# ── Detect label column (any of the common names) ─────────────────────


def detect_label_column(df: pd.DataFrame) -> str:
    for cand in ["label", "is_fraud", "fraud", "isFraud", "Label", "IS_FRAUD"]:
        if cand in df.columns:
            vc = df[cand].value_counts().to_dict()
            log.info(f"  Found label column '{cand}' – value counts: {vc}")
            return cand
    raise ValueError(
        f"Unable to locate a label column; columns: {list(df.columns)}")

# ── Account feature construction ────────────────────────────────────────


def build_account_features(df: pd.DataFrame) -> pd.DataFrame:
    log.info("=" * 55)
    log.info("BUILDING ACCOUNT FEATURE TABLE")
    log.info("=" * 55)

    # basic stats ---------------------------------------------------------
    uniq_senders = df["sender_id"].nunique()
    uniq_receivers = df["receiver_id"].nunique()
    total_unique = pd.concat([df["sender_id"], df["receiver_id"]]).nunique()
    log.info(f"Unique senders: {uniq_senders:,}")
    log.info(f"Unique receivers: {uniq_receivers:,}")
    log.info(f"Total unique accounts: {total_unique:,}")

    # timestamp handling ----------------------------------------------------
    if "timestamp" in df.columns:
        df["_ts_parsed"] = pd.to_datetime(df["timestamp"], errors="coerce")
        has_ts = True
    else:
        has_ts = False
        log.warning("  No 'timestamp' column – temporal split disabled")

    # --------------------------------------------------------------------
    # Sender‑side aggregation
    # --------------------------------------------------------------------
    with timer("sender-side aggregation"):
        agg_sender = {
            "avg_amount_sent": ("amount_inr", "mean"),
            "max_amount_sent": ("amount_inr", "max"),
            "total_amount_sent": ("amount_inr", "sum"),
            "max_send_velocity_1h": ("sender_amount_velocity_1h", "max"),
            "max_session_count_day": ("sender_session_count_day", "max"),
            "max_unique_counterparties_24h": ("sender_unique_counterparties_24h", "max"),
            "sender_degree": ("sender_degree", "max"),
            "total_txns_as_sender": ("tx_id", "count"),
        }
        if has_ts:
            agg_sender["first_txn_timestamp"] = ("_ts_parsed", "min")

        sender_agg = df.groupby("sender_id").agg(**agg_sender).reset_index()
        sender_agg = sender_agg.rename(columns={"sender_id": "account_id"})
        log.info(f"  Sender agg rows: {len(sender_agg):,}")

    # --------------------------------------------------------------------
    # Receiver‑side aggregation
    # --------------------------------------------------------------------
    with timer("receiver-side aggregation"):
        agg_receiver = {
            "avg_amount_received": ("amount_inr", "mean"),
            "total_amount_received": ("amount_inr", "sum"),
            "max_recv_velocity_1h": ("receiver_amount_velocity_1h", "max"),
            "receiver_degree": ("receiver_degree", "max"),
            "total_txns_as_receiver": ("tx_id", "count"),
        }
        receiver_agg = df.groupby("receiver_id").agg(
            **agg_receiver).reset_index()
        receiver_agg = receiver_agg.rename(
            columns={"receiver_id": "account_id"})
        log.info(f"  Receiver agg rows: {len(receiver_agg):,}")

    # --------------------------------------------------------------------
    # Merge sender + receiver
    # --------------------------------------------------------------------
    with timer("merge sender + receiver"):
        account_df = pd.merge(sender_agg, receiver_agg,
                              on="account_id", how="outer")
        account_df = account_df.fillna(0)
        log.info(f"  Merged account table rows: {len(account_df):,}")

    # --------------------------------------------------------------------
    # Encode sender_role as a numeric feature (role is a node attribute, not edge)
    # --------------------------------------------------------------------
    with timer("encode sender role"):
        role_series = df.groupby("sender_id")[
            "sender_role"].first().reset_index()
        role_series.columns = ["account_id", "sender_role_raw"]
        unique_roles = sorted(role_series["sender_role_raw"].unique())
        role_map = {r: i for i, r in enumerate(unique_roles)}
        log.info(f"  Role mapping: {role_map}")
        role_series["sender_role_encoded"] = role_series["sender_role_raw"].map(
            role_map)
        account_df = account_df.merge(
            role_series[["account_id", "sender_role_encoded"]], on="account_id", how="left"
        )
        account_df["sender_role_encoded"] = (
            account_df["sender_role_encoded"].fillna(-1).astype(int)
        )

    # --------------------------------------------------------------------
    # Derive extra ratios / scores, clip outliers at the 99‑th percentile
    # --------------------------------------------------------------------
    with timer("derived features"):
        account_df["in_out_velocity_ratio"] = (
            account_df["max_recv_velocity_1h"] /
            (account_df["max_send_velocity_1h"] + EPS)
        )
        account_df["burst_score"] = (
            account_df["max_amount_sent"] /
            (account_df["avg_amount_sent"] + EPS)
        )
        account_df["fan_out_ratio"] = (
            account_df["max_unique_counterparties_24h"] /
            (account_df["total_txns_as_sender"] + EPS)
        )
        account_df["recv_to_send_ratio"] = (
            account_df["total_txns_as_receiver"] /
            (account_df["total_txns_as_sender"] + EPS)
        )
        # Clip extreme outliers (p99)
        for col in [
            "in_out_velocity_ratio", "burst_score",
            "fan_out_ratio", "recv_to_send_ratio",
        ]:
            q99 = account_df[col].quantile(0.99)
            n_clipped = (account_df[col] > q99).sum()
            account_df[col] = account_df[col].clip(upper=q99)
            log.info(f"  {col}: clipped {n_clipped} rows at p99={q99:.4f}")

    # --------------------------------------------------------------------
    # Summary stats
    # --------------------------------------------------------------------
    log.info("Feature stats (mean | max):")
    for col in account_df.columns:
        if col == "account_id":
            continue
        log.info(
            f"  {col:<40} mean={account_df[col].mean():.3f} | max={account_df[col].max():.3f}"
        )

    log.info(
        f"Feature table ready: {len(account_df):,} accounts × {account_df.shape[1]} features"
    )
    return account_df

# ── Edge list builder (pairwise) ───────────────────────────────────────


def pairwise_edges(df, id_a, id_b, attr_a, attr_b,
                   edge_name="edge", max_group_size=20, max_total_edges=100_000):
    log.info(f"  Building '{edge_name}' edges (attr: {attr_a}/{attr_b})")
    log.info(
        f"    max_group_size={max_group_size} | max_total_edges={max_total_edges:,}")

    left = df[[id_a, attr_a]].rename(
        columns={id_a: "account_id", attr_a: "attribute"})
    right = df[[id_b, attr_b]].rename(
        columns={id_b: "account_id", attr_b: "attribute"})
    combined = pd.concat([left, right], ignore_index=True).drop_duplicates()
    log.info(f"    Unique (account, attribute) pairs: {len(combined):,}")

    # Count accounts per attribute
    attr_counts = combined.groupby(
        "attribute")["account_id"].count().reset_index()
    attr_counts.columns = ["attribute", "n_accounts"]
    too_small = (attr_counts["n_accounts"] < 2).sum()
    too_large = (attr_counts["n_accounts"] > max_group_size).sum()
    kept = ((attr_counts["n_accounts"] >= 2) & (
        attr_counts["n_accounts"] <= max_group_size)).sum()
    log.info(
        f"    Attr groups – too small (<2): {too_small} | too large (>{max_group_size}): {too_large} | kept: {kept}"
    )

    valid_attrs = attr_counts[
        (attr_counts["n_accounts"] >= 2) &
        (attr_counts["n_accounts"] <= max_group_size)
    ]["attribute"]
    combined = combined[combined["attribute"].isin(valid_attrs)]

    if combined.empty:
        log.warning(
            f"    No valid attribute groups for '{edge_name}' → empty edge list")
        return pd.DataFrame(columns=["src", "dst"])

    merged = combined.merge(combined, on="attribute", suffixes=("", "_b"))
    merged = merged[merged["account_id"] < merged["account_id_b"]]
    edges = merged[["account_id", "account_id_b"]].rename(
        columns={"account_id": "src", "account_id_b": "dst"})
    log.info(f"    Edges before cap: {len(edges):,}")

    if len(edges) > max_total_edges:
        log.warning(
            f"    Capping {len(edges)} → {max_total_edges} (random sample, seed=42)")
        edges = edges.sample(n=max_total_edges, random_state=42)

    log.info(f"    Final edge count: {len(edges):,}")
    return edges.reset_index(drop=True)

# ── Edge list orchestrator ───────────────────────────────────────────────


def build_edge_lists(df: pd.DataFrame):
    log.info("=" * 55)
    log.info("BUILDING EDGE LISTS")
    log.info("=" * 55)

    with timer("transacted_with edges"):
        edges_txn = df[["sender_id", "receiver_id", "amount_inr"]].rename(
            columns={"sender_id": "src",
                     "receiver_id": "dst", "amount_inr": "weight"}
        ).drop_duplicates(subset=["src", "dst"])
        log.info(f"  transacted_with: {len(edges_txn):,}")

    with timer("shares_device edges"):
        edges_device = pairwise_edges(
            df, "sender_id", "receiver_id",
            "sender_device_id", "receiver_device_id",
            edge_name="shares_device",
            max_group_size=20,
            max_total_edges=100_000,
        )

    with timer("shares_ip edges"):
        edges_ip = pairwise_edges(
            df, "sender_id", "receiver_id",
            "sender_ip_subnet", "receiver_ip_subnet",
            edge_name="shares_ip",
            max_group_size=150,
            max_total_edges=500_000,
        )

    log.info("-" * 55)
    log.info("Edge summary:")
    log.info(f"  transacted_with : {len(edges_txn):,}")
    log.info(f"  shares_device   : {len(edges_device):,}")
    log.info(f"  shares_ip       : {len(edges_ip):,}")
    log.info(
        f"  TOTAL           : {len(edges_txn)+len(edges_device)+len(edges_ip):,}")
    return edges_txn, edges_device, edges_ip

# ── Build account‑level labels (role → fraud/benign) ───────────────────────


def build_account_labels(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
    log.info("=" * 55)
    log.info("BUILDING ACCOUNT LABELS")
    log.info("=" * 55)

    MULE_ROLES = {
        "MULE_COLLECTOR", "MULE_LAYER", "MULE_SINK",
        "mule_collector", "mule_layer", "mule_sink",
        "mule", "MULE",
    }

    log.info(
        f"Unique sender_role values: {sorted(df['sender_role'].unique())}")

    # Sender side – each sender_id has one role (take first)
    sender_roles = df.groupby("sender_id")["sender_role"].first().reset_index()
    sender_roles.columns = ["account_id", "role"]
    sender_roles["label"] = sender_roles["role"].isin(MULE_ROLES).astype(int)

    # Receiver side – may never appear as sender
    if "receiver_role" in df.columns:
        receiver_roles = df.groupby("receiver_id")[
            "receiver_role"].first().reset_index()
        receiver_roles.columns = ["account_id", "role"]
        receiver_roles["label"] = receiver_roles["role"].isin(
            MULE_ROLES).astype(int)
        all_roles = pd.concat(
            [receiver_roles, sender_roles], ignore_index=True)
        account_labels = (
            all_roles
            .drop_duplicates(subset="account_id", keep="last")
            [["account_id", "label"]]
        )
    else:
        account_labels = sender_roles[["account_id", "label"]]

    n_fraud = (account_labels["label"] == 1).sum()
    n_benign = (account_labels["label"] == 0).sum()
    fraud_rate = account_labels["label"].mean()

    log.info("Account‑level labels (role based):")
    log.info(f"  Total accounts : {len(account_labels):,}")
    log.info(f"  Fraud accounts : {n_fraud:,} ({fraud_rate:.2%})")
    log.info(f"  Benign accounts: {n_benign:,} ({1 - fraud_rate:.2%})")
    log.info(
        f"  Class ratio    : 1 fraud per {n_benign/(n_fraud+EPS):.1f} benign accounts")

    # sanity check – show txn‑label distribution per role
    role_label_check = df.groupby("sender_role")[
        label_col].value_counts().to_string()
    log.info(f"Sanity check – txn labels per role:\n{role_label_check}")

    return account_labels

# ── Main entry point (called from run_pipeline) ───────────────────────────


def run(dataset_path: str):
    total_start = time.time()
    log.info("=" * 55)
    log.info("STEP 1: PREPROCESSING PIPELINE")
    log.info(f"Dataset: {dataset_path}")
    log.info("=" * 55)

    df = load_dataset(dataset_path)
    label_col = detect_label_column(df)

    # 1️⃣ Account features
    account_features = build_account_features(df)
    out_path = DATA_DIR / "account_features.csv"
    with timer("write account_features.csv"):
        account_features.to_csv(out_path, index=False)
        log.info(
            f"  Saved: {out_path} ({out_path.stat().st_size/1024:.1f} KB)")

    # 2️⃣ Edge lists
    edges_txn, edges_device, edges_ip = build_edge_lists(df)
    with timer("write edge CSVs"):
        (DATA_DIR / "edges_transacted.csv").write_text("")
        edges_txn.to_csv(DATA_DIR / "edges_transacted.csv", index=False)
        edges_device.to_csv(DATA_DIR / "edges_device.csv", index=False)
        edges_ip.to_csv(DATA_DIR / "edges_ip.csv", index=False)

    # 3️⃣ Account labels
    account_labels = build_account_labels(df, label_col)
    with timer("write account_labels.csv"):
        account_labels.to_csv(DATA_DIR / "account_labels.csv", index=False)

    log.info("=" * 55)
    elapsed = time.time() - total_start
    log.info(f"STEP 1 COMPLETE – elapsed {elapsed:.2f}s")
    log.info("Outputs:")
    for f in [
        "account_features.csv", "edges_transacted.csv", "edges_device.csv",
        "edges_ip.csv", "account_labels.csv"
    ]:
        p = DATA_DIR / f
        size = p.stat().st_size / 1024
        log.info(f"  {str(p):<45} {size:.1f} KB")
    log.info("=" * 55)


if __name__ == "__main__":
    # CLI convenience – just run the script directly
    dataset = sys.argv[1] if len(sys.argv) > 1 else "data/transactions.parquet"
    run(dataset)
