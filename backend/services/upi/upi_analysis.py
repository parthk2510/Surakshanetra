import csv
import io
import logging
import math
import hashlib
import traceback
import time as _time
import json
import uuid
from datetime import datetime
from collections import defaultdict
from typing import Dict, Any, List, Optional, Tuple

# Use the centralized logger so UPI logs go to chainbreak.log
logger = logging.getLogger('upi_analysis')


DEFAULT_UPI_SETTINGS = {
    "rules": {
        "fanInThreshold": 5,
        "fanOutThreshold": 5,
        "rapidWindowMs": 300000,
        "rapidMinTx": 3,
        "circularMaxDepth": 3,
        "structuringThreshold": 10000,
        "structuringMarginPct": 10,
        "dormantDays": 30,
        "spikeMultiplier": 5,
        "passThroughRatioPct": 90
    },
    "weights": {
        "fanIn": 15,
        "fanOut": 15,
        "rapidBurst": 20,
        "circularFlow": 25,
        "structuring": 10,
        "dormantSpike": 10,
        "passThrough": 5
    },
    "limits": {
        "maxNodes": 5000,       # None = unlimited
        "maxEdges": 15000,       # None = unlimited
        "maxBatchSize": 100
    }
}

REQUIRED_CSV_HEADERS = [
    "tx_id", "timestamp", "sender_upi", "receiver_upi",
    "amount_inr", "status"
]


def is_valid_upi_id(upi_id):
    """
    Validate UPI ID format and prevent injection attacks.
    UPI format: username@bankcode (e.g., user@paytm)
    """
    if not upi_id or not isinstance(upi_id, str):
        return False
    
    upi_id = upi_id.strip()
    
    # Length validation
    if len(upi_id) < 5 or len(upi_id) > 100:
        return False
    
    # Must contain exactly one @
    if upi_id.count('@') != 1:
        return False
    
    # Split into parts
    parts = upi_id.split('@')
    if len(parts) != 2:
        return False
    
    username, bankcode = parts
    if not username or not bankcode:
        return False
    
    # Username validation: alphanumeric, dot, underscore, hyphen only
    import re
    if not re.match(r'^[a-zA-Z0-9._-]+$', username):
        return False
    
    # Bank code validation: alphanumeric, dot, hyphen only (typically 3-4 chars)
    if not re.match(r'^[a-zA-Z0-9.-]+$', bankcode):
        return False
    
    # Prevent common injection patterns
    dangerous_chars = [';', "'", '"', '\\', '\n', '\r', '\t']
    for char in dangerous_chars:
        if char in upi_id:
            return False
    
    return True


def normalize_upi_id(value):
    """
    Normalize and sanitize UPI ID.
    """
    if not value or not isinstance(value, str):
        return ""
    
    # Strip whitespace
    value = value.strip()
    
    # Convert to lowercase
    value = value.lower()
    
    # Remove any remaining dangerous characters (defense in depth)
    import re
    value = re.sub(r'[^\w@.-]', '', value)
    
    return value


def hash_id(input_str):
    return hashlib.md5(input_str.encode("utf-8")).hexdigest()[:12]


def risk_band_from_score(score):
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    if score >= 20:
        return "low"
    return "minimal"


def parse_csv_content(file_content):
    reader = csv.DictReader(io.StringIO(file_content))

    field_names = [f.strip().lower() for f in (reader.fieldnames or [])]
    logger.info(f"CSV headers found: {field_names}")
    
    # Check for essential headers with flexible matching
    essential_headers = {
        "sender_upi": ["sender_upi", "sender", "from_upi"],
        "receiver_upi": ["receiver_upi", "receiver", "to_upi"],
        "amount_inr": ["amount_inr", "amount", "value", "amount_inr"]
    }
    
    missing_headers = []
    for required, alternatives in essential_headers.items():
        if not any(alt in field_names for alt in alternatives):
            missing_headers.append(f"{required} (need one of: {alternatives})")
    
    if missing_headers:
        raise ValueError(f"Missing required CSV columns: {', '.join(missing_headers)}\nFound headers: {field_names}")

    transactions = []
    skipped = 0

    for row_num, row in enumerate(reader, start=2):
        row_lower = {k.strip().lower(): v.strip() for k, v in row.items() if k}

        # Flexible header matching
        sender = normalize_upi_id(
            row_lower.get("sender_upi") or 
            row_lower.get("sender") or 
            row_lower.get("from_upi") or ""
        )
        receiver = normalize_upi_id(
            row_lower.get("receiver_upi") or 
            row_lower.get("receiver") or 
            row_lower.get("to_upi") or ""
        )

        if not is_valid_upi_id(sender) or not is_valid_upi_id(receiver):
            skipped += 1
            continue

        try:
            amount = float(
                row_lower.get("amount_inr") or 
                row_lower.get("amount") or 
                row_lower.get("value") or "0"
            )
        except (ValueError, TypeError):
            skipped += 1
            continue

        # Handle timestamp - try multiple formats
        timestamp_str = row_lower.get("timestamp", "0")
        try:
            # Try Unix timestamp first
            timestamp = int(timestamp_str)
        except (ValueError, TypeError):
            try:
                # Try ISO format as fallback
                from datetime import datetime
                timestamp = int(datetime.fromisoformat(timestamp_str).timestamp() * 1000)
            except (ValueError, TypeError):
                # Default to current time
                timestamp = int(_time.time() * 1000)

        # Build transaction object
        transaction = {
            'id': row_lower.get('tx_id', f'tx_{row_num}'),
            'from': sender,
            'to': receiver,
            'amount': amount,
            'timestamp': timestamp,
            'status': row_lower.get('status', 'unknown'),
            'pattern': '',
            'label': '',
            'senderDevice': row_lower.get('sender_device_id', ''),
            'receiverDevice': row_lower.get('receiver_device_id', ''),
            'senderIpSubnet': row_lower.get('sender_ip_subnet', ''),
            'receiverIpSubnet': row_lower.get('receiver_ip_subnet', '')
        }
        transactions.append(transaction)
    
    return transactions


def analyze_upi_transactions(transactions, settings=None):
    _t0 = _time.time()

    if settings is None:
        settings = DEFAULT_UPI_SETTINGS

    rules = settings.get("rules", DEFAULT_UPI_SETTINGS["rules"])
    weights = settings.get("weights", DEFAULT_UPI_SETTINGS["weights"])
    limits = settings.get("limits", DEFAULT_UPI_SETTINGS["limits"])

    all_upi_ids = set()
    for tx in transactions:
        all_upi_ids.add(tx["from"])
        all_upi_ids.add(tx["to"])

    node_stats = {}
    for uid in all_upi_ids:
        node_stats[uid] = {
            "inTxCount": 0,
            "outTxCount": 0,
            "totalInAmount": 0.0,
            "totalOutAmount": 0.0,
            "inCounterparties": set(),
            "outCounterparties": set(),
            "inAmounts": [],
            "outAmounts": [],
            "events": [],
            "firstSeen": None,
            "lastActive": None,
            "devices": set(),
            "ips": set(),
            "reasonCodes": []
        }

    for tx in transactions:
        sender = tx["from"]
        receiver = tx["to"]
        amount = tx["amount"]
        ts = tx["timestamp"]

        s = node_stats[sender]
        s["outTxCount"] += 1
        s["totalOutAmount"] += amount
        s["outCounterparties"].add(receiver)
        s["outAmounts"].append(amount)
        s["events"].append({"ts": ts, "dir": "out", "amt": amount, "peer": receiver})
        if s["firstSeen"] is None or ts < s["firstSeen"]:
            s["firstSeen"] = ts
        if s["lastActive"] is None or ts > s["lastActive"]:
            s["lastActive"] = ts

        r = node_stats[receiver]
        r["inTxCount"] += 1
        r["totalInAmount"] += amount
        r["inCounterparties"].add(sender)
        r["inAmounts"].append(amount)
        r["events"].append({"ts": ts, "dir": "in", "amt": amount, "peer": sender})
        if r["firstSeen"] is None or ts < r["firstSeen"]:
            r["firstSeen"] = ts
        if r["lastActive"] is None or ts > r["lastActive"]:
            r["lastActive"] = ts

        # Track devices and IPs for fingerprinting (Sender Side)
        s_dev = tx.get("senderDevice", "").strip()
        if s_dev:
            s["devices"].add(s_dev)
        s_ip = tx.get("senderIpSubnet", "").strip()
        if s_ip:
             s["ips"].add(s_ip)
        
        # Track devices and IPs for fingerprinting (Receiver Side)
        r_dev = tx.get("receiverDevice", "").strip()
        if r_dev:
            r["devices"].add(r_dev)
        r_ip = tx.get("receiverIpSubnet", "").strip()
        if r_ip:
            r["ips"].add(r_ip)

    logger.info(f"UPI stats computed for {len(all_upi_ids)} accounts in {round((_time.time() - _t0) * 1000)}ms")

    fan_in_threshold = rules.get("fanInThreshold", 5)
    fan_out_threshold = rules.get("fanOutThreshold", 5)
    rapid_window = rules.get("rapidWindowMs", 300000)
    rapid_min_tx = rules.get("rapidMinTx", 3)
    structuring_threshold = rules.get("structuringThreshold", 10000)
    structuring_margin = rules.get("structuringMarginPct", 10) / 100.0
    pass_through_ratio = rules.get("passThroughRatioPct", 90) / 100.0

    w_fan_in = weights.get("fanIn", 15)
    w_fan_out = weights.get("fanOut", 15)
    w_rapid = weights.get("rapidBurst", 20)
    w_circular = weights.get("circularFlow", 25)
    w_structuring = weights.get("structuring", 10)
    w_pass_through = weights.get("passThrough", 5)
    w_dormant_spike = weights.get("dormantSpike", 10)
    w_multiple_devices = weights.get("multipleDevices", 30)
    w_multiple_ips = weights.get("multipleIps", 20)

    device_threshold = rules.get("deviceThreshold", 2)
    ip_threshold = rules.get("ipThreshold", 2)

    adjacency = defaultdict(set)
    for tx in transactions:
        adjacency[tx["from"]].add(tx["to"])

    def detect_circular(start, max_depth):
        if len(adjacency.get(start, set())) == 0:
            return False  # Fast exit for isolated nodes
            
        visited = set()
        stack = [(start, 0)]
        while stack:
            node, depth = stack.pop()
            if depth > max_depth:
                continue
            if node == start and depth > 0:
                return True
            if node in visited:
                continue
            visited.add(node)
            for neighbor in adjacency.get(node, set()):
                stack.append((neighbor, depth + 1))
        return False

    circular_max_depth = rules.get("circularMaxDepth", 3)

    for uid, stats in node_stats.items():
        score = 0
        reasons = []

        if len(stats["inCounterparties"]) >= fan_in_threshold:
            score += w_fan_in
            reasons.append("high_fan_in")

        if len(stats["outCounterparties"]) >= fan_out_threshold:
            score += w_fan_out
            reasons.append("high_fan_out")

        events_sorted = sorted(stats["events"], key=lambda e: e["ts"])
        
        # O(n log n) rapid burst sliding window
        left = 0
        for right in range(len(events_sorted)):
            while events_sorted[right]["ts"] - events_sorted[left]["ts"] > rapid_window:
                left += 1
            if (right - left + 1) >= rapid_min_tx:
                score += w_rapid
                reasons.append("rapid_burst")
                break

        if len(stats["outCounterparties"]) >= 2 and detect_circular(uid, circular_max_depth):
            score += w_circular
            reasons.append("circular_flow")

        lower_bound = structuring_threshold * (1 - structuring_margin)
        upper_bound = structuring_threshold
        structuring_count = sum(
            1 for amt in (stats["outAmounts"] + stats["inAmounts"])
            if lower_bound <= amt <= upper_bound
        )
        if structuring_count >= 2:
            score += w_structuring
            reasons.append("structuring")

        if stats["totalInAmount"] > 0 and stats["totalOutAmount"] > 0:
            ratio = stats["totalOutAmount"] / stats["totalInAmount"]
            if ratio >= pass_through_ratio:
                score += w_pass_through
                reasons.append("pass_through")

        # Dormant Spike Detection
        if len(events_sorted) >= 2:
            dormant_ms = rules.get("dormantDays", 30) * 86400000
            spike_mul = rules.get("spikeMultiplier", 5)
            for i in range(1, len(events_sorted)):
                curr = events_sorted[i]
                prev = events_sorted[i-1]
                if curr["ts"] - prev["ts"] >= dormant_ms:
                    # History up to this point
                    hist = events_sorted[:i]
                    avg_amt = sum(e["amt"] for e in hist) / len(hist)
                    if avg_amt > 0 and curr["amt"] >= (avg_amt * spike_mul):
                        score += w_dormant_spike
                        reasons.append("dormant_spike")
                        break

        # Fingerprinting Reasoning
        if len(stats["devices"]) >= device_threshold:
            score += w_multiple_devices
            reasons.append("multiple_devices")
        
        if len(stats["ips"]) >= ip_threshold:
            score += w_multiple_ips
            reasons.append("multiple_ips")

        risk_score = min(100, max(0, score))

        stats["riskScore"] = risk_score
        stats["riskBand"] = risk_band_from_score(risk_score)
        stats["reasonCodes"] = reasons

    _scored = sum(1 for uid in all_upi_ids if node_stats[uid]["riskScore"] > 0)
    logger.info(f"UPI risk scoring complete: {_scored}/{len(all_upi_ids)} accounts flagged")

    max_nodes = limits.get("maxNodes")   # None = unlimited
    max_edges = limits.get("maxEdges")   # None = unlimited

    scored_upi_ids = sorted(
        all_upi_ids,
        key=lambda uid: node_stats[uid]["riskScore"],
        reverse=True
    )
    if max_nodes is not None:
        scored_upi_ids = scored_upi_ids[:max_nodes]

    scored_set = set(scored_upi_ids)

    nodes = []
    for uid in scored_upi_ids:
        s = node_stats[uid]
        nodes.append({
            "id": uid,
            "upiId": uid,
            "riskScore": s["riskScore"],
            "riskBand": s["riskBand"],
            "inTxCount": s["inTxCount"],
            "outTxCount": s["outTxCount"],
            "totalInAmount": round(s["totalInAmount"], 2),
            "totalOutAmount": round(s["totalOutAmount"], 2),
            "inCounterparties": len(s["inCounterparties"]),
            "outCounterparties": len(s["outCounterparties"]),
            "firstSeen": s["firstSeen"],
            "lastActive": s["lastActive"],
            "reasonCodes": s["reasonCodes"]
        })

    edges = []
    seen_edges = set()
    devices_map = {} # Maps device_id -> set of UPI IDs using it
    
    for tx in transactions:
        if tx["from"] not in scored_set or tx["to"] not in scored_set:
            continue
            
        # Collect devices
        s_dev = tx.get("senderDevice", "").strip()
        if s_dev:
            if s_dev not in devices_map:
                devices_map[s_dev] = set()
            devices_map[s_dev].add(tx["from"])
            
        r_dev = tx.get("receiverDevice", "").strip()
        if r_dev:
            if r_dev not in devices_map:
                devices_map[r_dev] = set()
            devices_map[r_dev].add(tx["to"])
            
        # Collect transaction edges
        edge_key = f'{tx["from"]}->{tx["to"]}'
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        edges.append({
            "source": tx["from"],
            "target": tx["to"],
            "amount": tx["amount"],
            "txId": tx["id"],
            "timestamp": tx["timestamp"]
        })
        if max_edges is not None and len(edges) >= max_edges:
            break

    # Add Device nodes and USED_DEVICE edges
    for dev_id, users in devices_map.items():
        # Only include devices connected to scored users
        nodes.append({
            "id": dev_id,
            "label": dev_id[:12] + "...",
            "isDevice": True,
            "nodeType": "Device",
            "deviceUsers": len(users),
            "riskScore": 90.0 if len(users) > 1 else 10.0,
            "reasonCodes": ["shared_device"] if len(users) > 1 else []
        })
        for user in users:
            edges.append({
                "source": user,
                "target": dev_id,
                "edgeType": "USED_DEVICE"
            })

    risk_scores = [n["riskScore"] for n in nodes]
    avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0
    max_risk = max(risk_scores) if risk_scores else 0
    cluster_risk = min(100, int(avg_risk * 0.6 + max_risk * 0.4))

    critical = sum(1 for s in risk_scores if s >= 80)
    high = sum(1 for s in risk_scores if 60 <= s < 80)
    medium = sum(1 for s in risk_scores if 40 <= s < 60)
    low = sum(1 for s in risk_scores if 20 <= s < 40)
    minimal = sum(1 for s in risk_scores if s < 20)

    result = {
        "graph": {
            "nodes": nodes,
            "edges": edges
        },
        "risk": {
            "clusterRiskScore": cluster_risk,
            "averageRiskScore": round(avg_risk, 1),
            "maxRiskScore": max_risk,
            "distribution": {
                "critical": critical,
                "high": high,
                "medium": medium,
                "low": low,
                "minimal": minimal
            }
        },
        "metadata": {
            "totalNodes": len(nodes),
            "totalEdges": len(edges),
            "totalTransactions": len(transactions),
            "analysisTimestamp": datetime.utcnow().isoformat(),
            "settingsUsed": {
                "rules": rules,
                "weights": weights
            }
        }
    }

    logger.info(
        f"Analysis complete: {len(nodes)} nodes, {len(edges)} edges, "
        f"clusterRisk={cluster_risk}, critical={critical}, high={high}"
    )

    return result
