"""
API Test Script
Run while uvicorn is running:
  python test_api.py
"""

import requests
import json
import sys

BASE = "http://127.0.0.1:8000"
PASS = []
FAIL = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ✅ PASS | {name}")
        PASS.append(name)
    else:
        print(f"  ❌ FAIL | {name} | {detail}")
        FAIL.append(name)


def test(endpoint, params=None):
    try:
        r = requests.get(f"{BASE}{endpoint}", params=params, timeout=10)
        return r.status_code, r.json()
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Cannot connect to {BASE}")
        print("   Make sure uvicorn is running:")
        print("   uvicorn step7_fastapi:app --reload --port 8000\n")
        sys.exit(1)
    except Exception as e:
        return None, str(e)


# ── 1. Health ─────────────────────────────────────────────────────────────────
print("\n── 1. Health Check ──────────────────────────────────")
code, data = test("/health")
check("Status 200",          code == 200)
check("status=ok",           data.get("status") == "ok", data)
check("version present",     "version" in data)
# Dynamically read actual account count — no hardcoding
TOTAL_ACCOUNTS = data.get("accounts", 0)
check("accounts > 0",        TOTAL_ACCOUNTS > 0, data)
print(f"  ℹ️  API serving {TOTAL_ACCOUNTS:,} accounts")

# ── 2. Metrics Summary ────────────────────────────────────────────────────────
print("\n── 2. Metrics Summary ───────────────────────────────")
code, data = test("/api/metrics/summary")
check("Status 200",                    code == 200)
check("total_accounts matches health", data.get("total_accounts") == TOTAL_ACCOUNTS, data)
check("flagged_accounts > 0",    data.get("flagged_accounts", 0) > 0, data)
check("flag_rate > 0",           data.get("flag_rate", 0) > 0, data)
check("risk_tier_counts present",    "risk_tier_counts" in data)
check("top_communities present",     "top_communities" in data)
tiers = data.get("risk_tier_counts", {})
check("All 4 tiers present",     all(t in tiers for t in ["Low","Medium","High","Critical"]), tiers)
print(f"  ℹ️  Flagged: {data.get('flagged_accounts')} / {data.get('total_accounts')} ({data.get('flag_rate'):.1%})")
print(f"  ℹ️  Tiers: {tiers}")

# ── 3. Account List ───────────────────────────────────────────────────────────
print("\n── 3. Account List ──────────────────────────────────")
code, data = test("/api/accounts", {"page": 1, "per_page": 10})
check("Status 200",          code == 200)
check("total > 0",           data.get("total", 0) > 0, data)
check("accounts is list",    isinstance(data.get("accounts"), list))
check("10 accounts returned",len(data.get("accounts", [])) == 10)
if data.get("accounts"):
    first = data["accounts"][0]
    check("account_id present",      "account_id" in first)
    check("final_risk_score present","final_risk_score" in first)
    check("risk_tier present",       "risk_tier" in first)
    check("risk score in [0,1]",     0 <= first.get("final_risk_score", -1) <= 1, first)
    sample_account_id = first["account_id"]
    print(f"  ℹ️  Top account: {sample_account_id} | score={first['final_risk_score']:.4f} | tier={first['risk_tier']}")

# ── 4. Single Account ─────────────────────────────────────────────────────────
print("\n── 4. Single Account ────────────────────────────────")
code, data = test(f"/api/account/{sample_account_id}")
check("Status 200",               code == 200)
check("account_id matches",       data.get("account_id") == sample_account_id)
check("anomaly_score present",    "anomaly_score" in data)
check("fraud_probability present","fraud_probability" in data)
check("final_risk_score present", "final_risk_score" in data)
check("risk_tier present",        "risk_tier" in data)
check("predicted_fraud present",  "predicted_fraud" in data)
check("community_id present",     "community_id" in data)
check("anomaly_score in [0,1]",   0 <= data.get("anomaly_score", -1) <= 1)
check("fraud_prob in [0,1]",      0 <= data.get("fraud_probability", -1) <= 1)
print(f"  ℹ️  anomaly={data.get('anomaly_score'):.4f} | fraud_prob={data.get('fraud_probability'):.4f} | tier={data.get('risk_tier')}")

# ── 5. 404 for unknown account ────────────────────────────────────────────────
print("\n── 5. Unknown Account (should 404) ──────────────────")
code, data = test("/api/account/NONEXISTENT_ACCOUNT_XYZ")
check("Status 404", code == 404)

# ── 6. Account List — Filters ─────────────────────────────────────────────────
print("\n── 6. Account List Filters ──────────────────────────")
code, data = test("/api/accounts", {"flagged_only": "true", "per_page": 50})
check("Status 200",               code == 200)
check("flagged_only works",       all(a["final_risk_score"] >= 0.5 for a in data.get("accounts", [])))
print(f"  ℹ️  Flagged accounts returned: {data.get('total')}")

code, data = test("/api/accounts", {"risk_tier": "Critical", "per_page": 50})
check("Status 200 for tier filter", code == 200)
check("All returned are Critical",  all(a["risk_tier"] == "Critical" for a in data.get("accounts", [])))
print(f"  ℹ️  Critical tier accounts: {data.get('total')}")

code, data = test("/api/accounts", {"min_score": "0.8", "per_page": 50})
check("Status 200 for min_score",   code == 200)
check("All scores >= 0.8",          all(a["final_risk_score"] >= 0.8 for a in data.get("accounts", [])))

# ── 7. Community Graph ────────────────────────────────────────────────────────
print("\n── 7. Community Graph ───────────────────────────────")
# Get a community_id from the metrics summary
code, summary = test("/api/metrics/summary")
top_communities = summary.get("top_communities", [])
if top_communities:
    cid = top_communities[0]["community_id"]
    code, data = test(f"/api/graph/community/{cid}")
    check("Status 200",           code == 200)
    check("community_id matches", data.get("community_id") == cid)
    check("nodes is list",        isinstance(data.get("nodes"), list))
    check("edges is list",        isinstance(data.get("edges"), list))
    check("nodes not empty",      len(data.get("nodes", [])) > 0)
    if data.get("nodes"):
        n = data["nodes"][0]
        check("node has account_id",        "account_id" in n)
        check("node has final_risk_score",  "final_risk_score" in n)
        check("node has risk_tier",         "risk_tier" in n)
    print(f"  ℹ️  Community {cid}: {len(data.get('nodes',[]))} nodes | {len(data.get('edges',[]))} edges")
else:
    print("  ⚠️  No communities found — community_assignments.csv may be missing")

# ── 8. Pagination ─────────────────────────────────────────────────────────────
print("\n── 8. Pagination ────────────────────────────────────")
code, p1 = test("/api/accounts", {"page": 1, "per_page": 5})
code, p2 = test("/api/accounts", {"page": 2, "per_page": 5})
ids_p1 = [a["account_id"] for a in p1.get("accounts", [])]
ids_p2 = [a["account_id"] for a in p2.get("accounts", [])]
check("Page 1 has 5 accounts",  len(ids_p1) == 5)
check("Page 2 has 5 accounts",  len(ids_p2) == 5)
check("Pages don't overlap",    len(set(ids_p1) & set(ids_p2)) == 0, f"overlap: {set(ids_p1)&set(ids_p2)}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print(f"  RESULTS: {len(PASS)} passed | {len(FAIL)} failed")
if FAIL:
    print(f"  Failed tests:")
    for f in FAIL:
        print(f"    ✗ {f}")
else:
    print("  All tests passed — API is healthy ✅")
print("=" * 55)