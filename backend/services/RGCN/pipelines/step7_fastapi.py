import os
import joblib
import torch
import torch.nn.functional as F
import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="UPI Fraud Detection API",
    description="Real-time risk scoring for mule accounts and collusive fraud rings",
    version="1.0.0",
)

# Allow React dev server (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global pipeline (loaded once on startup) ──────────────────────────────────
PIPELINE: Dict[str, Any] = {}

MODEL_DIR = "models"


@app.on_event("startup")
def load_pipeline():
    global PIPELINE
    pkl_path = f"{MODEL_DIR}/fraud_pipeline.pkl"
    if not os.path.exists(pkl_path):
        raise RuntimeError(f"Pipeline PKL not found at {pkl_path}. Run step6 first.")
    print(f"Loading pipeline from {pkl_path} ...")
    PIPELINE = joblib.load(pkl_path)
    print(f"✅ Pipeline loaded | {len(PIPELINE['scores_lookup']):,} accounts in lookup")


# ── Response models ────────────────────────────────────────────────────────────
class AccountRiskResponse(BaseModel):
    account_id:        str
    anomaly_score:     float
    fraud_probability: float
    final_risk_score:  float
    risk_tier:         str
    predicted_fraud:   int
    flag_source:       str
    community_id:      int


class AccountListItem(BaseModel):
    account_id:       str
    final_risk_score: float
    risk_tier:        str
    flag_source:      str
    community_id:     int


class AccountListResponse(BaseModel):
    total:    int
    page:     int
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
    nodes:        List[GraphNode]
    edges:        List[GraphEdge]


class MetricsSummaryResponse(BaseModel):
    total_accounts:     int
    flagged_accounts:   int
    flag_rate:          float
    risk_tier_counts:   Dict[str, int]
    flag_source_counts: Dict[str, int]
    top_communities:    List[Dict]


# ── Helpers ────────────────────────────────────────────────────────────────────
def get_account_score(account_id: str) -> Dict:
    """Fast O(1) lookup from precomputed scores."""
    lookup = PIPELINE.get("scores_lookup", {})
    if account_id not in lookup:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")
    record = lookup[account_id]
    record["account_id"] = account_id
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


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status":    "ok",
        "accounts":  len(PIPELINE.get("scores_lookup", {})),
        "version":   PIPELINE.get("version", "unknown"),
    }


@app.get("/api/account/{account_id}", response_model=AccountRiskResponse)
def get_account_risk(account_id: str):
    """
    Returns risk scores for a single account.
    Used by React dashboard when user clicks an account row.
    """
    record = get_account_score(account_id)
    return AccountRiskResponse(
        account_id        = account_id,
        anomaly_score     = safe_float(record.get("anomaly_score")),
        fraud_probability = safe_float(record.get("fraud_probability")),
        final_risk_score  = safe_float(record.get("final_risk_score")),
        risk_tier         = safe_str(record.get("risk_tier", "Low")),
        predicted_fraud   = safe_int(record.get("predicted_fraud")),
        flag_source       = safe_str(record.get("flag_source", "none")),
        community_id      = safe_int(record.get("community_id", -1)),
    )


@app.get("/api/accounts", response_model=AccountListResponse)
def list_accounts(
    page:         int   = Query(1,       ge=1),
    per_page:     int   = Query(50,      ge=1, le=500),
    risk_tier:    Optional[str]  = Query(None),
    flag_source:  Optional[str]  = Query(None),
    min_score:    float = Query(0.0,     ge=0.0, le=1.0),
    flagged_only: bool  = Query(False),
    community_id: Optional[int]  = Query(None),
):
    """
    Paginated list of accounts with filters.
    Feeds the main account risk table in the React dashboard.
    """
    lookup = PIPELINE.get("scores_lookup", {})
    records = [{"account_id": k, **v} for k, v in lookup.items()]

    # Apply filters
    if flagged_only:
        records = [r for r in records if safe_int(r.get("predicted_fraud")) == 1]
    if risk_tier:
        records = [r for r in records if safe_str(r.get("risk_tier")).lower() == risk_tier.lower()]
    if flag_source:
        records = [r for r in records if safe_str(r.get("flag_source")).lower() == flag_source.lower()]
    if min_score > 0.0:
        records = [r for r in records if safe_float(r.get("final_risk_score")) >= min_score]
    if community_id is not None:
        records = [r for r in records if safe_int(r.get("community_id", -1)) == community_id]

    # Sort by risk score descending
    records.sort(key=lambda r: safe_float(r.get("final_risk_score")), reverse=True)

    total  = len(records)
    start  = (page - 1) * per_page
    paged  = records[start: start + per_page]

    return AccountListResponse(
        total    = total,
        page     = page,
        per_page = per_page,
        accounts = [
            AccountListItem(
                account_id       = r["account_id"],
                final_risk_score = safe_float(r.get("final_risk_score")),
                risk_tier        = safe_str(r.get("risk_tier", "Low")),
                flag_source      = safe_str(r.get("flag_source", "none")),
                community_id     = safe_int(r.get("community_id", -1)),
            )
            for r in paged
        ],
    )


@app.get("/api/graph/community/{community_id}", response_model=CommunityGraphResponse)
def get_community_graph(community_id: int):
    """
    Returns all nodes and edges in a fraud community.
    Feeds the D3/Cytoscape network visualization in React.
    """
    lookup = PIPELINE.get("scores_lookup", {})

    # Get all accounts in this community
    community_accounts = {
        aid: rec for aid, rec in lookup.items()
        if safe_int(rec.get("community_id", -1)) == community_id
    }

    if not community_accounts:
        raise HTTPException(
            status_code=404,
            detail=f"Community {community_id} not found or has no accounts"
        )

    nodes = [
        GraphNode(
            account_id        = aid,
            final_risk_score  = safe_float(rec.get("final_risk_score")),
            risk_tier         = safe_str(rec.get("risk_tier", "Low")),
            flag_source       = safe_str(rec.get("flag_source", "none")),
            community_id      = safe_int(rec.get("community_id", -1)),
            anomaly_score     = safe_float(rec.get("anomaly_score")),
            fraud_probability = safe_float(rec.get("fraud_probability")),
        )
        for aid, rec in community_accounts.items()
    ]

    # Get edges between accounts in this community from graph data
    edges = []
    graph_data = PIPELINE.get("graph_data")
    node_index  = PIPELINE.get("node_index_map", {})
    index_to_acc = PIPELINE.get("index_to_account", {})

    if graph_data is not None:
        community_node_ids = set(
            node_index[aid] for aid in community_accounts if aid in node_index
        )

        relation_names = ["transacted_with", "shares_device", "shares_ip", "same_role"]
        for rel_name in relation_names:
            key = ("account", rel_name, "account")
            if key in graph_data.edge_types:
                ei = graph_data[key].edge_index
                src_arr = ei[0].numpy()
                dst_arr = ei[1].numpy()
                for s, d in zip(src_arr, dst_arr):
                    if s in community_node_ids and d in community_node_ids:
                        src_aid = index_to_acc.get(int(s))
                        dst_aid = index_to_acc.get(int(d))
                        if src_aid and dst_aid:
                            edges.append(GraphEdge(
                                source        = src_aid,
                                target        = dst_aid,
                                relation_type = rel_name,
                            ))

    return CommunityGraphResponse(
        community_id = community_id,
        nodes        = nodes,
        edges        = edges,
    )


@app.get("/api/metrics/summary", response_model=MetricsSummaryResponse)
def metrics_summary():
    """
    Aggregated KPIs for the dashboard summary cards.
    """
    lookup = PIPELINE.get("scores_lookup", {})
    records = list(lookup.values())

    total    = len(records)
    flagged  = sum(1 for r in records if safe_int(r.get("predicted_fraud")) == 1)

    tier_counts = {"Low": 0, "Medium": 0, "High": 0, "Critical": 0}
    source_counts: Dict[str, int] = {}

    community_stats: Dict[int, Dict] = {}

    for r in records:
        tier = safe_str(r.get("risk_tier", "Low"))
        if tier in tier_counts:
            tier_counts[tier] += 1

        src = safe_str(r.get("flag_source", "none"))
        source_counts[src] = source_counts.get(src, 0) + 1

        cid = safe_int(r.get("community_id", -1))
        if cid != -1:
            if cid not in community_stats:
                community_stats[cid] = {"community_id": cid, "total": 0, "flagged": 0, "avg_risk": []}
            community_stats[cid]["total"] += 1
            community_stats[cid]["avg_risk"].append(safe_float(r.get("final_risk_score")))
            if safe_int(r.get("predicted_fraud")) == 1:
                community_stats[cid]["flagged"] += 1

    # Top 10 highest-risk communities
    top_communities = []
    for cid, stats in community_stats.items():
        avg_risk = float(np.mean(stats["avg_risk"])) if stats["avg_risk"] else 0.0
        top_communities.append({
            "community_id": cid,
            "total_accounts": stats["total"],
            "flagged_accounts": stats["flagged"],
            "avg_risk_score": round(avg_risk, 4),
        })
    top_communities.sort(key=lambda x: x["avg_risk_score"], reverse=True)
    top_communities = top_communities[:10]

    return MetricsSummaryResponse(
        total_accounts     = total,
        flagged_accounts   = flagged,
        flag_rate          = round(flagged / (total + 1e-9), 4),
        risk_tier_counts   = tier_counts,
        flag_source_counts = source_counts,
        top_communities    = top_communities,
    )