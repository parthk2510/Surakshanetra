# -*- coding: utf-8 -*-
"""
STEP 6 – Serialize *everything* into a single pickle for fast API start‑up.
"""

import joblib
import torch
import pandas as pd
import time
from datetime import datetime

from ..utils.config import DATA_DIR, MODEL_DIR, LOG_DIR, EPS
from ..utils.logger import get_logger
from ..pipelines.step4_rgcn_training import FraudRGCN   # re‑use model class

log = get_logger(__name__)


def load_component(name: str, loader):
    log.info(f"Loading {name} …")
    t0 = time.time()
    obj = loader()
    log.info(f"  OK ({time.time() - t0:.2f}s)")
    return obj


def run():
    log.info("=" * 55)
    log.info("STEP 6 – PKL SERIALIZATION")
    log.info("=" * 55)

    # ── Isolation‑Forest artefacts ───────────────────────────────────────
    if_model = load_component("isolation_forest.pkl", lambda: joblib.load(
        MODEL_DIR / "isolation_forest.pkl"))
    if_scaler = load_component(
        "if_scaler.pkl", lambda: joblib.load(MODEL_DIR / "if_scaler.pkl"))
    if_cols = load_component("if_feature_columns.pkl", lambda: joblib.load(
        MODEL_DIR / "if_feature_columns.pkl"))

    # ── RGCN artefacts ───────────────────────────────────────────────────
    rgcn_cfg = load_component(
        "rgcn_config.pkl", lambda: joblib.load(MODEL_DIR / "rgcn_config.pkl"))
    rgcn_scaler = load_component("rgcn_node_scaler.pkl", lambda: joblib.load(
        MODEL_DIR / "rgcn_node_scaler.pkl"))

    log.info("Re‑constructing the RGCN architecture & loading weights …")
    rgcn_model = FraudRGCN(**rgcn_cfg)
    state = torch.load(MODEL_DIR / "rgcn_weights.pt",
                       map_location="cpu", weights_only=True)
    rgcn_model.load_state_dict(state)
    rgcn_model.eval()
    log.info(
        f"  RGCN model loaded – {sum(p.numel() for p in rgcn_model.parameters()):,} parameters")

    # ── Node index maps ───────────────────────────────────────────────────
    node_index_map = load_component(
        "node_index_map.pkl", lambda: joblib.load(DATA_DIR / "node_index_map.pkl"))
    index_to_account = load_component("index_to_account_map.pkl", lambda: joblib.load(
        DATA_DIR / "index_to_account_map.pkl"))

    # ── Final scores lookup (fast O(1) per‑account) ───────────────────────
    final_scores = pd.read_csv(DATA_DIR / "final_scores.csv")
    scores_lookup = final_scores.set_index(
        "account_id").to_dict(orient="index")
    log.info(f"Scores lookup built – {len(scores_lookup):,} entries")

    # ── Graph data (the full PyG HeteroData object) ───────────────────────
    graph_data = torch.load(DATA_DIR / "graph_data.pt", weights_only=False)
    log.info(f"Graph data loaded – {graph_data}")

    pipeline = {
        "isolation_forest":   if_model,
        "if_scaler":          if_scaler,
        "if_feature_columns": if_cols,
        "rgcn_model":         rgcn_model,
        "rgcn_config":        rgcn_cfg,
        "rgcn_node_scaler":   rgcn_scaler,
        "node_index_map":     node_index_map,
        "index_to_account":   index_to_account,
        "scores_lookup":      scores_lookup,
        "graph_data":        graph_data,
        # business hyper‑parameters (mirrored from step5)
        "if_weight":          0.40,
        "rgcn_weight":        0.60,
        "risk_threshold":    0.50,
        "version":            "1.0.0",
    }

    out_path = MODEL_DIR / "fraud_pipeline.pkl"
    log.info("Serializing pipeline …")
    t0 = time.time()
    joblib.dump(pipeline, out_path)
    log.info(
        f"Saved {out_path} ({out_path.stat().st_size / 1024**2:.1f} MiB) in {time.time() - t0:.2f}s")
    log.info("Pipeline contents:")
    for k, v in pipeline.items():
        log.info(f"  {k:<25} {type(v).__name__}")

    log.info("STEP 6 COMPLETE")


if __name__ == "__main__":
    run()
