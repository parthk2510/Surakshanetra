import os
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

try:
    from ..utils.logger import get_rgcn_logger
    from ..utils.config import PIPELINE_PATH, RGCN_ENV_VAR
    _log = get_rgcn_logger("chainbreak.rgcn.router")
except Exception:
    import logging
    _log = logging.getLogger("chainbreak.rgcn.router")
    PIPELINE_PATH = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "model", "fraud_pipeline.pkl")
    )
    RGCN_ENV_VAR = "RGCN_PIPELINE_PATH"

router = APIRouter(prefix="/rgcn", tags=["RGCN Fraud Detection"])

PIPELINE: Dict[str, Any] = {}
_pipeline_load_attempted = False


def _rebuild_pipeline_from_components(model_path: str) -> Dict[str, Any]:
    """
    Fallback: reconstruct the pipeline from individual model/data files when the
    main fraud_pipeline.pkl cannot be deserialized (e.g. Python/torch version mismatch).
    Re-saves a fresh fraud_pipeline.pkl so future restarts load instantly.
    """
    from pathlib import Path
    import sys

    model_dir = Path(model_path).parent          # …/RGCN/model/
    data_dir  = model_dir.parent / "data"        # …/RGCN/data/

    pipeline: Dict[str, Any] = {}

    # ── scores_lookup from CSV (plain data — zero serialisation risk) ────────
    scores_csv = data_dir / "final_scores.csv"
    if scores_csv.exists():
        try:
            import pandas as pd
            df = pd.read_csv(scores_csv)
            pipeline["scores_lookup"] = df.set_index("account_id").to_dict(orient="index")
            _log.info("Rebuilt scores_lookup from CSV: %d accounts", len(pipeline["scores_lookup"]))
        except Exception as e:
            _log.warning("Could not read final_scores.csv: %s", e)

    # ── scikit-learn isolation forest (stable across Python versions) ────────
    for fname, key in [
        ("isolation_forest.pkl", "isolation_forest"),
        ("if_scaler.pkl",        "if_scaler"),
        ("if_feature_columns.pkl", "if_feature_columns"),
        ("rgcn_config.pkl",      "rgcn_config"),
        ("rgcn_node_scaler.pkl", "rgcn_node_scaler"),
    ]:
        fpath = model_dir / fname
        if fpath.exists():
            try:
                pipeline[key] = joblib.load(fpath)
            except Exception as e:
                _log.warning("Could not load %s: %s", fname, e)

    # ── RGCN model weights (re-instantiate class + load state_dict) ─────────
    weights_path = model_dir / "rgcn_weights.pt"
    if weights_path.exists() and "rgcn_config" in pipeline:
        try:
            import torch
            import sys as _sys
            try:
                from backend.services.RGCN.pipelines.step4_rgcn_training import FraudRGCN
            except ImportError:
                from ..pipelines.step4_rgcn_training import FraudRGCN
            cfg = pipeline["rgcn_config"]
            model = FraudRGCN(**cfg)
            state = torch.load(weights_path, map_location="cpu", weights_only=True)
            model.load_state_dict(state)
            model.eval()
            pipeline["rgcn_model"] = model
            _log.info("RGCN model reconstructed from weights (%d params)",
                      sum(p.numel() for p in model.parameters()))
        except Exception as e:
            _log.warning("Could not reconstruct RGCN model from weights: %s", e)

    # ── node index maps ──────────────────────────────────────────────────────
    for fname, key in [
        ("node_index_map.pkl",       "node_index_map"),
        ("index_to_account_map.pkl", "index_to_account"),
    ]:
        fpath = data_dir / fname
        if fpath.exists():
            try:
                pipeline[key] = joblib.load(fpath)
            except Exception as e:
                _log.warning("Could not load %s: %s", fname, e)

    pipeline["version"] = "1.0.0-rebuilt"

    # Re-save so next startup loads the fresh pkl instantly
    if pipeline.get("scores_lookup"):
        try:
            joblib.dump(pipeline, model_path)
            _log.info("Re-saved rebuilt pipeline to %s", model_path)
        except Exception as e:
            _log.warning("Could not re-save rebuilt pipeline: %s", e)

    return pipeline


def _load_pipeline_from_disk() -> None:
    global PIPELINE, _pipeline_load_attempted
    _pipeline_load_attempted = True
    model_path = os.getenv(RGCN_ENV_VAR, PIPELINE_PATH)
    model_path = os.path.normpath(model_path)
    _log.info("Loading RGCN pipeline from: %s", model_path)
    if not os.path.exists(model_path):
        _log.warning("RGCN pipeline not found at %s — attempting component rebuild", model_path)
        rebuilt = _rebuild_pipeline_from_components(model_path)
        if rebuilt.get("scores_lookup"):
            PIPELINE = rebuilt
            _log.info("RGCN pipeline initialised from components (%d accounts)",
                      len(PIPELINE["scores_lookup"]))
        return
    import sys
    try:
        import backend.services.RGCN.pipelines.step4_rgcn_training as _s4
        sys.modules.setdefault("step4_rgcn_training", _s4)
        sys.modules.setdefault("backend.services.RGCN.pipelines.step4_rgcn_training", _s4)
    except Exception as _ie:
        _log.warning("Could not pre-register step4_rgcn_training module alias: %s", _ie)
    try:
        PIPELINE = joblib.load(model_path)
        count = len(PIPELINE.get("scores_lookup", {}))
        _log.info("RGCN pipeline loaded — %d accounts in lookup", count)
    except Exception as exc:
        _log.warning("fraud_pipeline.pkl failed to load (%s) — rebuilding from components", exc)
        rebuilt = _rebuild_pipeline_from_components(model_path)
        if rebuilt.get("scores_lookup"):
            PIPELINE = rebuilt
            _log.info("RGCN pipeline rebuilt from components (%d accounts)",
                      len(PIPELINE["scores_lookup"]))
        else:
            _log.error("RGCN pipeline unavailable — no scores_lookup could be built")


@router.on_event("startup")
def _load_pipeline() -> None:
    _load_pipeline_from_disk()


def _pipeline_loaded() -> bool:
    if not _pipeline_load_attempted:
        _load_pipeline_from_disk()
    return bool(PIPELINE.get("scores_lookup"))

# -----------------------------------------------------------------
# Helper functions (same logic as the original script)
# -----------------------------------------------------------------


def get_account_score(account_id: str) -> Dict:
    if not _pipeline_loaded():
        _log.warning("Pipeline not loaded when requesting account score for %s", account_id)
        raise HTTPException(
            status_code=503,
            detail="RGCN pipeline not loaded. Run `run_pipeline.py` first.",
        )
    lookup = PIPELINE.get("scores_lookup", {})
    if account_id not in lookup:
        _log.debug("Account not found in RGCN lookup: %s", account_id)
        raise HTTPException(
            status_code=404, detail=f"Account '{account_id}' not found")
    record = lookup[account_id].copy()
    record["account_id"] = account_id
    _log.debug(
        "RGCN score for %s: risk_tier=%s final_risk=%.4f",
        account_id, record.get("risk_tier"), record.get("final_risk_score", 0),
    )
    return record


def safe_float(val, default=0.0) -> float:
    try:
        return float(val) if val is not None and not (isinstance(val, float) and np.isnan(val)) else default
    except Exception:
        return default


def safe_int(val, default=0) -> int:
    try:
        return int(val) if val is not None else default
    except Exception:
        return default


def safe_str(val, default="unknown") -> str:
    return str(val) if val is not None else default

# -----------------------------------------------------------------
# Response models (mirrored from the original script)
# -----------------------------------------------------------------


class AccountRiskResponse(BaseModel):
    account_id:        str
    anomaly_score:     float
    fraud_probability: float
    final_risk_score: float
    risk_tier:        str
    predicted_fraud:  int
    flag_source:      str
    community_id:     int


class AccountListItem(BaseModel):
    account_id:       str
    final_risk_score: float
    risk_tier:        str
    flag_source:      str
    community_id:     int


class AccountListResponse(BaseModel):
    total:    int
    page:    int
    per_page: int
    accounts: List[AccountListItem]


class GraphNode(BaseModel):
    account_id:       str
    final_risk_score: float
    risk_tier:        str
    flag_source:      str
    community_id:     int
    anomaly_score:    float
    fraud_probability: float


class GraphEdge(BaseModel):
    source:        str
    target:        str
    relation_type: str


class CommunityGraphResponse(BaseModel):
    community_id: int
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class MetricsSummaryResponse(BaseModel):
    total_accounts:      int
    flagged_accounts:    int
    flag_rate:          float
    risk_tier_counts:   Dict[str, int]
    flag_source_counts: Dict[str, int]
    top_communities:    List[Dict]

# -----------------------------------------------------------------
# Endpoints – identical to the previous script but **mounted** under /rgcn
# -----------------------------------------------------------------


@router.get("/health")
def health():
    loaded = _pipeline_loaded()
    _log.info("Health check: pipeline_loaded=%s", loaded)
    if not loaded:
        return {
            "status": "pipeline_not_loaded",
            "accounts": 0,
            "version": "unknown",
            "message": "Run run_pipeline.py to train and serialize the RGCN model",
        }
    return {
        "status": "ok",
        "accounts": len(PIPELINE.get("scores_lookup", {})),
        "version": PIPELINE.get("version", "unknown"),
    }


@router.get("/account/{account_id}")
def get_account(account_id: str, traditional_risk_score: float = 0.0):
    _log.info("GET /rgcn/account/%s", account_id)
    from backend.services.decision_engine import _get_rgcn_score
    rec = _get_rgcn_score(account_id, traditional_risk_score=traditional_risk_score)
    
    if not rec:
        return {
            "available": False,
            "account_id": account_id,
            "message": "Account not found and inductive fallback failed.",
        }
    
    rec["available"] = True
    return AccountRiskResponse(
        account_id=account_id,
        anomaly_score=safe_float(rec.get("anomaly_score")),
        fraud_probability=safe_float(rec.get("fraud_probability")),
        final_risk_score=safe_float(rec.get("final_risk_score")),
        risk_tier=safe_str(rec.get("risk_tier", "Low")),
        predicted_fraud=safe_int(rec.get("predicted_fraud")),
        flag_source=safe_str(rec.get("flag_source", "none")),
        community_id=safe_int(rec.get("community_id", -1)),
    )


@router.get("/accounts", response_model=AccountListResponse)
def list_accounts(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    risk_tier: Optional[str] = Query(None),
    flag_source: Optional[str] = Query(None),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    flagged_only: bool = Query(False),
    community_id: Optional[int] = Query(None),
):
    lookup = PIPELINE.get("scores_lookup", {})
    records = [{"account_id": k, **v} for k, v in lookup.items()]

    # Apply filters -------------------------------------------------
    if flagged_only:
        records = [r for r in records if safe_int(
            r.get("predicted_fraud")) == 1]
    if risk_tier:
        records = [r for r in records if safe_str(
            r.get("risk_tier")).lower() == risk_tier.lower()]
    if flag_source:
        records = [r for r in records if safe_str(
            r.get("flag_source")).lower() == flag_source.lower()]
    if min_score > 0.0:
        records = [r for r in records if safe_float(
            r.get("final_risk_score")) >= min_score]
    if community_id is not None:
        records = [r for r in records if safe_int(
            r.get("community_id", -1)) == community_id]

    records.sort(key=lambda r: safe_float(r.get("final_risk_score")), reverse=True)

    total = len(records)
    _log.debug("list_accounts: returning %d/%d records page=%d", min(per_page, total), total, page)
    start = (page - 1) * per_page
    page_records = records[start:start + per_page]

    return AccountListResponse(
        total=total,
        page=page,
        per_page=per_page,
        accounts=[
            AccountListItem(
                account_id=rec["account_id"],
                final_risk_score=safe_float(rec.get("final_risk_score")),
                risk_tier=safe_str(rec.get("risk_tier", "Low")),
                flag_source=safe_str(rec.get("flag_source", "none")),
                community_id=safe_int(rec.get("community_id", -1)),
            )
            for rec in page_records
        ],
    )


@router.get("/graph/community/{community_id}", response_model=CommunityGraphResponse)
def community_graph(community_id: int):
    _log.info("GET /rgcn/graph/community/%d", community_id)
    lookup = PIPELINE.get("scores_lookup", {})

    community_accounts = {
        aid: rec for aid, rec in lookup.items()
        if safe_int(rec.get("community_id", -1)) == community_id
    }
    if not community_accounts:
        raise HTTPException(
            status_code=404,
            detail=f"Community {community_id} not found or empty"
        )

    nodes = [
        GraphNode(
            account_id=aid,
            final_risk_score=safe_float(rec.get("final_risk_score")),
            risk_tier=safe_str(rec.get("risk_tier", "Low")),
            flag_source=safe_str(rec.get("flag_source", "none")),
            community_id=safe_int(rec.get("community_id", -1)),
            anomaly_score=safe_float(rec.get("anomaly_score")),
            fraud_probability=safe_float(rec.get("fraud_probability")),
        )
        for aid, rec in community_accounts.items()
    ]

    # Build edges – we need the original heterogeneous graph
    graph_data = PIPELINE.get("graph_data")
    node_index_map = PIPELINE.get("node_index_map", {})
    index_to_account = PIPELINE.get("index_to_account", {})

    edges: List[GraphEdge] = []
    if graph_data is not None:
        # set of node IDs that belong to this community
        community_node_ids = {
            node_index_map[aid] for aid in community_accounts if aid in node_index_map
        }
        for rel_name in ["transacted_with", "shares_device", "shares_ip", "same_role"]:
            key = ("account", rel_name, "account")
            if key not in graph_data.edge_types:
                continue
            ei = graph_data[key].edge_index
            src, dst = ei[0].numpy(), ei[1].numpy()
            for s, d in zip(src, dst):
                if s in community_node_ids and d in community_node_ids:
                    src_aid = index_to_account.get(int(s))
                    dst_aid = index_to_account.get(int(d))
                    if src_aid and dst_aid:
                        edges.append(
                            GraphEdge(
                                source=src_aid,
                                target=dst_aid,
                                relation_type=rel_name,
                            )
                        )

    return CommunityGraphResponse(
        community_id=community_id,
        nodes=nodes,
        edges=edges,
    )


@router.get("/metrics/summary", response_model=MetricsSummaryResponse)
def metrics():
    _log.info("GET /rgcn/metrics/summary")
    lookup = PIPELINE.get("scores_lookup", {})
    records = list(lookup.values())

    total = len(records)
    flagged = sum(1 for r in records if safe_int(
        r.get("predicted_fraud")) == 1)

    # tier counts ----------------------------------------------------
    risk_tier_counts = {"Low": 0, "Medium": 0, "High": 0, "Critical": 0}
    for r in records:
        tier = safe_str(r.get("risk_tier", "Low"))
        if tier in risk_tier_counts:
            risk_tier_counts[tier] += 1

    # flag source counts ---------------------------------------------
    flag_source_counts: Dict[str, int] = {}
    for r in records:
        src = safe_str(r.get("flag_source", "none"))
        flag_source_counts[src] = flag_source_counts.get(src, 0) + 1

    # top communities -------------------------------------------------
    community_stats: Dict[int, Dict] = {}
    for r in records:
        cid = safe_int(r.get("community_id", -1))
        if cid == -1:
            continue
        if cid not in community_stats:
            community_stats[cid] = {"community_id": cid,
                                    "total": 0, "flagged": 0, "risk_vals": []}
        community_stats[cid]["total"] += 1
        if safe_int(r.get("predicted_fraud")) == 1:
            community_stats[cid]["flagged"] += 1
        community_stats[cid]["risk_vals"].append(
            safe_float(r.get("final_risk_score")))

    top_communities = []
    for cid, stats in community_stats.items():
        avg_risk = float(np.mean(stats["risk_vals"])
                         ) if stats["risk_vals"] else 0.0
        top_communities.append(
            {
                "community_id": cid,
                "total_accounts": stats["total"],
                "flagged_accounts": stats["flagged"],
                "avg_risk_score": round(avg_risk, 4),
            }
        )
    top_communities.sort(key=lambda x: x["avg_risk_score"], reverse=True)
    top_communities = top_communities[:10]

    return MetricsSummaryResponse(
        total_accounts=total,
        flagged_accounts=flagged,
        flag_rate=round(flagged / (total + 1e-9), 4),
        risk_tier_counts=risk_tier_counts,
        flag_source_counts=flag_source_counts,
        top_communities=top_communities,
    )
