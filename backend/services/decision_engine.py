"""
Decision Engine – combines RGCN, community detection, and traditional
risk heuristics into a single, confidence-scored verdict.

Usage (from api_root.py):
    from .services.decision_engine import DecisionEngine
    result = DecisionEngine.analyze(account_id)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from .RGCN.utils.logger import get_rgcn_logger
    logger = get_rgcn_logger("chainbreak.decision_engine")
except Exception:
    logger = logging.getLogger(__name__)

# ── Risk tier boundaries ───────────────────────────────────────────────────────
_TIER_THRESHOLDS = [
    (0.80, "Critical"),
    (0.60, "High"),
    (0.35, "Medium"),
    (0.00, "Low"),
]


def _classify_tier(score: float) -> str:
    for threshold, label in _TIER_THRESHOLDS:
        if score >= threshold:
            return label
    return "Low"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        import math
        f = float(val)
        return default if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return default


def _get_rgcn_score(account_id: str, traditional_risk_score: float = 0.0) -> Optional[Dict]:
    """Pull RGCN fraud scores from the in-process pipeline (lazy import) or fallback iteratively."""
    try:
        from backend.services.RGCN.api.router import PIPELINE, _pipeline_loaded
        if not _pipeline_loaded():
            return None
        lookup = PIPELINE.get("scores_lookup", {})
        if account_id in lookup:
            record = lookup[account_id].copy()
            record["account_id"] = account_id
            return record

        # --- INDUCTIVE FALLBACK ---
        # If unseen (OOD node), synthesize a score based on traditional heuristics 
        # using the trained pipeline's weights as priors.
        rgcn_weight = PIPELINE.get("rgcn_weight", 0.60)
        if_weight = PIPELINE.get("if_weight", 0.40)
        risk_threshold = PIPELINE.get("risk_threshold", 0.50)

        anomaly_score = traditional_risk_score * if_weight
        fraud_probability = traditional_risk_score * rgcn_weight
        final_risk = (traditional_risk_score * 0.5) + (fraud_probability * 0.5)

        predicted_fraud = 1 if final_risk > risk_threshold else 0

        # Re-use classification helper
        def classify(score):
            THRESHOLDS = [(0.80, "Critical"), (0.60, "High"), (0.35, "Medium"), (0.0, "Low")]
            for thresh, lbl in THRESHOLDS:
                if score >= thresh: return lbl
            return "Low"

        return {
            "account_id": account_id,
            "fraud_probability": round(fraud_probability, 4),
            "anomaly_score": round(anomaly_score, 4),
            "final_risk_score": round(final_risk, 4),
            "predicted_fraud": predicted_fraud,
            "flag_source": "Inductive Fallback",
            "risk_tier": classify(final_risk)
        }

    except Exception as exc:
        logger.debug("RGCN score unavailable: %s", exc)
        return None


def _get_community_insights(account_id: str) -> Optional[Dict]:
    """
    Extract community-level risk from the RGCN pipeline graph data.
    Returns None when the pipeline is not loaded or the account has no community.
    """
    try:
        from backend.services.RGCN.api.router import PIPELINE, _pipeline_loaded
        if not _pipeline_loaded():
            return None
        lookup = PIPELINE.get("scores_lookup", {})
        record = lookup.get(account_id)
        if record is None:
            return None
        community_id = record.get("community_id", -1)
        if community_id == -1:
            return None

        # Aggregate community statistics from all members
        members = [
            v for v in lookup.values()
            if v.get("community_id") == community_id
        ]
        if not members:
            return None

        flagged = sum(1 for m in members if m.get("predicted_fraud") == 1)
        avg_risk = sum(_safe_float(m.get("final_risk_score")) for m in members) / len(members)

        return {
            "community_id": community_id,
            "community_size": len(members),
            "flagged_members": flagged,
            "flag_rate": round(flagged / len(members), 4),
            "avg_community_risk": round(avg_risk, 4),
            "community_risk_tier": _classify_tier(avg_risk),
        }
    except Exception as exc:
        logger.debug("Community insights unavailable: %s", exc)
        return None


# ── Main engine ────────────────────────────────────────────────────────────────

class DecisionEngine:
    """
    Combines multiple risk signals into a single comprehensive decision.

    Weights (configurable via kwargs in .analyze()):
        rgcn_weight          – weight of RGCN fraud probability   (default 0.55)
        community_weight     – weight of community risk score      (default 0.20)
        traditional_weight   – weight of heuristic / trad score    (default 0.25)
    """

    @staticmethod
    def analyze(
        account_id: str,
        traditional_risk_score: float = 0.0,
        traditional_signals: Optional[List[str]] = None,
        rgcn_weight: float = 0.55,
        community_weight: float = 0.20,
        traditional_weight: float = 0.25,
    ) -> Dict:
        """
        Run all available risk engines and merge into one verdict.

        Parameters
        ----------
        account_id            : UPI account ID or Bitcoin address
        traditional_risk_score: Pre-computed heuristic risk score [0, 1]
        traditional_signals   : Human-readable risk signals from heuristics
        rgcn_weight           : Fraction of final score from RGCN
        community_weight      : Fraction of final score from community analysis
        traditional_weight    : Fraction of final score from heuristics

        Returns
        -------
        Comprehensive decision dict with ``final_score``, ``risk_tier``,
        ``confidence``, and per-engine breakdowns.
        """
        logger.info("DecisionEngine.analyze: account_id=%s", account_id)
        signals_used: List[str] = []
        engines: Dict[str, Any] = {}

        # ── 1. RGCN ───────────────────────────────────────────────────────────
        rgcn = _get_rgcn_score(account_id, traditional_risk_score=traditional_risk_score)
        if rgcn:
            signals_used.append("rgcn")
            engines["rgcn"] = {
                "fraud_probability":  _safe_float(rgcn.get("fraud_probability")),
                "anomaly_score":      _safe_float(rgcn.get("anomaly_score")),
                "final_risk_score":   _safe_float(rgcn.get("final_risk_score")),
                "predicted_fraud":    int(rgcn.get("predicted_fraud", 0)),
                "flag_source":        str(rgcn.get("flag_source", "none")),
                "model_risk_tier":    str(rgcn.get("risk_tier", "Low")),
            }

        # ── 2. Community detection ────────────────────────────────────────────
        community = _get_community_insights(account_id)
        if community:
            signals_used.append("community")
            engines["community"] = community

        # ── 3. Traditional heuristics ─────────────────────────────────────────
        if traditional_risk_score > 0 or traditional_signals:
            signals_used.append("traditional")
            engines["traditional"] = {
                "risk_score": _safe_float(traditional_risk_score),
                "signals":    traditional_signals or [],
            }

        # ── 4. Weighted combination ───────────────────────────────────────────
        # Normalise weights to the engines that are actually available
        available_weight = 0.0
        score_sum = 0.0

        if "rgcn" in engines:
            score_sum += rgcn_weight * _safe_float(
                engines["rgcn"]["final_risk_score"]
            )
            available_weight += rgcn_weight

        if "community" in engines:
            score_sum += community_weight * _safe_float(
                engines["community"]["avg_community_risk"]
            )
            available_weight += community_weight

        if "traditional" in engines:
            score_sum += traditional_weight * _safe_float(
                engines["traditional"]["risk_score"]
            )
            available_weight += traditional_weight

        # If nothing is available, default to the traditional score
        if available_weight == 0:
            final_score = _safe_float(traditional_risk_score)
        else:
            final_score = score_sum / available_weight  # re-normalise to [0,1]

        final_score = max(0.0, min(1.0, final_score))

        # ── 5. Confidence score ───────────────────────────────────────────────
        # Base confidence grows with each additional corroborating signal
        confidence = 0.35  # floor: at least some data
        if "rgcn" in engines:
            confidence += 0.30
        if "community" in engines:
            confidence += 0.20
        if "traditional" in engines:
            confidence += 0.15
        confidence = round(min(1.0, confidence), 4)

        # Boost/penalise confidence when engines agree/disagree strongly
        if len(engines) >= 2:
            all_scores = []
            if "rgcn" in engines:
                all_scores.append(engines["rgcn"]["final_risk_score"])
            if "community" in engines:
                all_scores.append(engines["community"]["avg_community_risk"])
            if "traditional" in engines:
                all_scores.append(engines["traditional"]["risk_score"])

            if len(all_scores) >= 2:
                score_range = max(all_scores) - min(all_scores)
                # Engines agree well → boost confidence
                if score_range < 0.15:
                    confidence = min(1.0, confidence + 0.05)
                # Engines diverge heavily → reduce confidence
                elif score_range > 0.40:
                    confidence = max(0.20, confidence - 0.10)

        # ── 6. Verdict ────────────────────────────────────────────────────────
        risk_tier = _classify_tier(final_score)

        action_map = {
            "Critical": "BLOCK – Immediate review required",
            "High":     "FLAG – Manual investigation recommended",
            "Medium":   "MONITOR – Enhanced due diligence",
            "Low":      "ALLOW – Standard monitoring",
        }
        recommended_action = action_map.get(risk_tier, "ALLOW")

        logger.info(
            "DecisionEngine result: account=%s tier=%s score=%.4f confidence=%.4f engines=%s",
            account_id, risk_tier, final_score, confidence, ",".join(signals_used) or "none",
        )
        return {
            "account_id":         account_id,
            "final_score":        round(final_score, 4),
            "risk_tier":          risk_tier,
            "confidence":         confidence,
            "recommended_action": recommended_action,
            "signals_used":       signals_used,
            "engine_count":       len(engines),
            "engines":            engines,
        }
