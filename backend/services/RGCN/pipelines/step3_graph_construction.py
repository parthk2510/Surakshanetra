# -*- coding: utf-8 -*-
"""
STEP 3 – Build a PyTorch‑Geometric heterogeneous graph.
"""

import pandas as pd
import numpy as np
import torch
import joblib
import time
from datetime import datetime

from torch_geometric.data import HeteroData
from sklearn.preprocessing import StandardScaler

from ..utils.config import DATA_DIR, MODEL_DIR, LOG_DIR, EPS
from ..utils.logger import get_logger

log = get_logger(__name__)

NODE_FEATURES = [
    "avg_amount_sent", "max_amount_sent", "max_send_velocity_1h",
    "max_session_count_day", "max_unique_counterparties_24h", "sender_degree",
    "avg_amount_received", "max_recv_velocity_1h", "receiver_degree",
    "in_out_velocity_ratio", "burst_score", "fan_out_ratio",
    "recv_to_send_ratio", "anomaly_score", "sender_role_encoded",
    "community_id", "community_confidence",
]


def load_all_data():
    log.info("=" * 55)
    log.info("STEP 3: GRAPH CONSTRUCTION")
    log.info("=" * 55)

    # ----------------------------------------------------------------
    # 1️⃣ Load all CSV artefacts
    # ----------------------------------------------------------------
    feats = pd.read_csv(DATA_DIR / "account_features.csv")
    log.info(f"Features: {len(feats):,} rows, {feats.shape[1]} cols")

    anom = pd.read_csv(
        DATA_DIR / "anomaly_scores.csv")[["account_id", "anomaly_score"]]
    log.info(
        f"Anomaly scores: {len(anom):,} rows (mean={anom['anomaly_score'].mean():.4f})")

    labs = pd.read_csv(DATA_DIR / "account_labels.csv")
    log.info(
        f"Labels: {len(labs):,} rows (fraud rate={labs['label'].mean():.2%})")

    df = feats.merge(anom, on="account_id", how="left")
    df = df.merge(labs, on="account_id", how="left")
    df["label"] = df["label"].fillna(0).astype(int)
    df["anomaly_score"] = df["anomaly_score"].fillna(0.0)

    # ----------------------------------------------------------------
    # 2️⃣ Optional community file (you may not have it)
    # ----------------------------------------------------------------
    community_path = DATA_DIR / "community_assignments.csv"
    if community_path.exists():
        log.info("Loading community_assignments.csv …")
        comm = pd.read_csv(community_path)
        df = df.merge(comm, on="account_id", how="left")
        df["community_id"] = df.get("community_id", 0).fillna(-1).astype(int)
        df["community_confidence"] = df.get(
            "community_confidence", 0.0).fillna(0.0)
        log.info(f"Found {comm['community_id'].nunique()} communities")
    else:
        log.warning("community_assignments.csv not found – using zeros")
        df["community_id"] = 0
        df["community_confidence"] = 0.0

    log.info(f"Final node table: {len(df):,} accounts × {df.shape[1]} cols")
    return df


def build_node_features(df):
    log.info("-" * 55)
    log.info("BUILDING NODE FEATURE MATRIX")

    available = [c for c in NODE_FEATURES if c in df.columns]
    missing = [c for c in NODE_FEATURES if c not in df.columns]
    if missing:
        log.warning(f"Missing node features (filled with 0): {missing}")
        for c in missing:
            df[c] = 0.0

    X = df[NODE_FEATURES].fillna(0).values.astype(np.float32)
    log.info(f"Raw matrix: {X.shape}")

    scaler = StandardScaler()
    X[:, :-2] = scaler.fit_transform(X[:, :-2])   # keep community columns raw
    joblib.dump(scaler, MODEL_DIR / "rgcn_node_scaler.pkl")
    log.info(f"Scaled behaviour features (kept last 2 raw) – saved scaler")

    return torch.tensor(X, dtype=torch.float)


def load_edges(node_index, edge_file, rel_name):
    p = DATA_DIR / edge_file
    if not p.exists():
        log.warning(f"Edge file missing: {p} – skipping '{rel_name}'")
        return None

    df = pd.read_csv(p)
    before = len(df)
    df = df[df["src"].isin(node_index) & df["dst"].isin(node_index)]
    removed = before - len(df)
    if removed:
        log.warning(f"{rel_name}: filtered {removed:,} rows (unknown IDs)")

    if df.empty:
        log.warning(f"{rel_name}: 0 edges after filter – skipping")
        return None

    src = df["src"].map(node_index).values
    dst = df["dst"].map(node_index).values
    ei = torch.tensor(np.stack([src, dst], axis=0), dtype=torch.long)
    log.info(f"{rel_name}: {ei.shape[1]:,} edges")
    return ei


def build_graph(df, node_index):
    log.info("-" * 55)
    log.info("ASSEMBLING HETEROGENEOUS GRAPH")

    data = HeteroData()
    data["account"].x = build_node_features(df)
    data["account"].y = torch.tensor(df["label"].values, dtype=torch.long)

    # ── Train / val / test split – temporal if we have a timestamp ────────
    N = len(df)
    if "first_txn_timestamp" in df.columns:
        log.info("Temporal split (sorted by first_txn_timestamp)")
        sorted_idx = df["first_txn_timestamp"].argsort().values
        n_train = int(0.70 * N)
        n_val = int(0.15 * N)
        train_idx = sorted_idx[:n_train]
        val_idx = sorted_idx[n_train:n_train + n_val]
        test_idx = sorted_idx[n_train + n_val:]
    else:
        log.warning("No timestamp – using stratified random split")
        np.random.seed(42)
        idx = np.arange(N)
        fraud = idx[df["label"].values == 1]
        benign = idx[df["label"].values == 0]

        def split(arr):
            n1 = int(0.70 * len(arr))
            n2 = int(0.15 * len(arr))
            return arr[:n1], arr[n1:n1 + n2], arr[n1 + n2:]

        f_tr, f_va, f_te = split(fraud)
        b_tr, b_va, b_te = split(benign)
        train_idx = np.concatenate([f_tr, b_tr])
        val_idx = np.concatenate([f_va, b_va])
        test_idx = np.concatenate([f_te, b_te])

    # masks -------------------------------------------------------------
    train_mask = torch.zeros(N, dtype=torch.bool)
    val_mask = torch.zeros(N, dtype=torch.bool)
    test_mask = torch.zeros(N, dtype=torch.bool)

    train_mask[train_idx] = True
    val_mask[val_idx] = True
    test_mask[test_idx] = True

    data["account"].train_mask = train_mask
    data["account"].val_mask = val_mask
    data["account"].test_mask = test_mask

    log.info(
        f"Split – train:{train_mask.sum():,} val:{val_mask.sum():,} test:{test_mask.sum():,}")
    log.info(
        f"Fraud counts – train:{data['account'].y[train_mask].sum():,} val:{data['account'].y[val_mask].sum():,} test:{data['account'].y[test_mask].sum():,}")

    # ── Edge loading (three relation types) ───────────────────────────────
    edge_map = {
        ("account", "transacted_with", "account"): "edges_transacted.csv",
        ("account", "shares_device",   "account"): "edges_device.csv",
        ("account", "shares_ip",       "account"): "edges_ip.csv",
    }
    total_edges = 0
    for rel, fname in edge_map.items():
        ei = load_edges(node_index, fname, rel[1])
        if ei is not None:
            data[rel].edge_index = ei
            total_edges += ei.shape[1]

    log.info(f"Total edges across all relations: {total_edges:,}")
    log.info(f"Loaded edge types: {[k[1] for k in data.edge_types]}")
    return data


def run():
    t0 = time.time()
    df = load_all_data()

    node_index = {aid: i for i, aid in enumerate(df["account_id"])}
    # for reverse lookup (used later by the API)
    index_to_account = {i: aid for aid, i in node_index.items()}

    # Save the mappings for later **fast lookup**
    joblib.dump(node_index, DATA_DIR / "node_index_map.pkl")
    joblib.dump(index_to_account, DATA_DIR / "index_to_account_map.pkl")
    log.info(f"Node index built: {len(node_index):,} accounts")

    graph = build_graph(df, node_index)

    torch.save(graph, DATA_DIR / "graph_data.pt")
    log.info(f"Saved graph to {DATA_DIR / 'graph_data.pt'}")
    log.info(f"STEP 3 COMPLETE (took {time.time() - t0:.2f}s)")


if __name__ == "__main__":
    run()
