import logging
import re as _re
import threading
import time as _time_module
import uuid as _uuid
from datetime import datetime

from fastapi import APIRouter, Query, Request, Depends
from fastapi.responses import JSONResponse

from backend.services.blockchain.blockchain_fetcher import (
    BlockchainComFetcher,
    BlockchainAPIError,
    InvalidAddressError,
    RateLimitError,
    TransactionNotFoundError,
    BlockNotFoundError,
)

logger = logging.getLogger(__name__)

_BTC_RE = _re.compile(r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$|^bc1[a-z0-9]{39,59}$")

router = APIRouter(prefix="/api/blockchain", tags=["blockchain"])
blockchain_bp = router


class BackgroundJobStore:
    _lock = threading.Lock()
    _jobs: dict = {}

    @classmethod
    def create_job(cls, address: str, max_limit: int) -> str:
        job_id = _uuid.uuid4().hex[:16]
        with cls._lock:
            cls._jobs[job_id] = {
                "job_id": job_id, "address": address, "status": "pending",
                "max_limit": max_limit, "fetched_count": 0, "total_on_chain": 0,
                "error": None, "result": None,
                "created_at": datetime.utcnow().isoformat(), "completed_at": None,
            }
        return job_id

    @classmethod
    def get_job(cls, job_id: str):
        with cls._lock:
            job = cls._jobs.get(job_id)
            if job is None:
                return None
            out = dict(job)
            if out.get("result") is not None:
                out["result_preview"] = {
                    "fetched_count": out["fetched_count"],
                    "total_on_chain": out["total_on_chain"],
                }
                out.pop("result", None)
            return out

    @classmethod
    def get_job_result(cls, job_id: str):
        with cls._lock:
            job = cls._jobs.get(job_id)
            return dict(job) if job else None

    @classmethod
    def update_job(cls, job_id: str, **kwargs):
        with cls._lock:
            if job_id in cls._jobs:
                cls._jobs[job_id].update(kwargs)

    @classmethod
    def cancel_job(cls, job_id: str) -> bool:
        with cls._lock:
            if job_id in cls._jobs:
                cls._jobs[job_id]["status"] = "cancelled"
                return True
            return False

    @classmethod
    def is_cancelled(cls, job_id: str) -> bool:
        with cls._lock:
            job = cls._jobs.get(job_id)
            return True if job is None else job["status"] == "cancelled"

    @classmethod
    def cleanup_old_jobs(cls, max_age_seconds: int = 3600) -> int:
        import time as _t
        now = _t.time()
        with cls._lock:
            to_delete = []
            for jid, job in cls._jobs.items():
                try:
                    created_dt = datetime.fromisoformat(job.get("created_at", ""))
                    if (now - created_dt.timestamp()) > max_age_seconds and job["status"] in ("complete", "error", "cancelled"):
                        to_delete.append(jid)
                except (ValueError, TypeError):
                    pass
            for jid in to_delete:
                del cls._jobs[jid]
        return len(to_delete)


def _run_background_deep_fetch(job_id: str, address: str, max_limit: int):
    try:
        BackgroundJobStore.update_job(job_id, status="running")
        fetcher = BlockchainComFetcher()
        initial_data = fetcher.fetch_address(address, limit=50, offset=0)
        total_on_chain = initial_data.get("n_tx", 0)
        all_txs = list(initial_data.get("txs", []))
        safe_max = min(max_limit, 2000)
        target_count = min(safe_max, total_on_chain)
        BackgroundJobStore.update_job(job_id, total_on_chain=total_on_chain, fetched_count=len(all_txs))
        offset = len(all_txs)
        errors = 0
        while len(all_txs) < target_count and offset < total_on_chain:
            if BackgroundJobStore.is_cancelled(job_id):
                BackgroundJobStore.update_job(job_id, status="cancelled", completed_at=datetime.utcnow().isoformat())
                return
            _time_module.sleep(0.3)
            try:
                batch = fetcher.fetch_address(address, limit=50, offset=offset)
                new_txs = batch.get("txs", [])
                if not new_txs:
                    break
                all_txs.extend(new_txs)
                offset += len(new_txs)
                BackgroundJobStore.update_job(job_id, fetched_count=len(all_txs))
                if len(new_txs) < 50:
                    break
            except Exception as e:
                logger.warning("Deep-fetch batch error (job=%s): %s", job_id, e)
                errors += 1
                if errors >= 5:
                    break
                _time_module.sleep(2.0)
        BackgroundJobStore.update_job(
            job_id, status="complete", fetched_count=len(all_txs),
            result={"txs": all_txs[:safe_max]}, completed_at=datetime.utcnow().isoformat()
        )
    except Exception as e:
        logger.error("Deep-fetch failed (job=%s): %s", job_id, e, exc_info=True)
        BackgroundJobStore.update_job(job_id, status="error", error=str(e), completed_at=datetime.utcnow().isoformat())


@router.get("/address/{address}")
def get_blockchain_address(address: str, limit: int = Query(default=50), offset: int = Query(default=0)):
    if not _BTC_RE.match(address):
        return JSONResponse({"success": False, "error": "Invalid Bitcoin address format"}, status_code=400)
    try:
        fetcher = BlockchainComFetcher()
        data = fetcher.fetch_address(address, limit=min(limit, 200), offset=offset)
        return JSONResponse({"success": True, "data": data})
    except RateLimitError:
        return JSONResponse({"success": False, "error": "Rate limit exceeded"}, status_code=429)
    except BlockchainAPIError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=502)
    except Exception as e:
        logger.error("blockchain/address error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@router.get("/transaction/{tx_hash}")
def get_blockchain_transaction(tx_hash: str):
    try:
        fetcher = BlockchainComFetcher()
        data = fetcher.get_transaction(tx_hash)
        return JSONResponse({"success": True, "data": data})
    except TransactionNotFoundError:
        return JSONResponse({"success": False, "error": "Transaction not found"}, status_code=404)
    except Exception as e:
        logger.error("blockchain/transaction error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@router.get("/block/{block_hash_or_height}")
def get_blockchain_block(block_hash_or_height: str):
    try:
        fetcher = BlockchainComFetcher()
        data = fetcher.get_block(block_hash_or_height)
        return JSONResponse({"success": True, "data": data})
    except BlockNotFoundError:
        return JSONResponse({"success": False, "error": "Block not found"}, status_code=404)
    except Exception as e:
        logger.error("blockchain/block error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@router.get("/stats")
def get_blockchain_stats():
    try:
        fetcher = BlockchainComFetcher()
        data = fetcher.get_blockchain_stats()
        return JSONResponse({"success": True, "data": data})
    except Exception as e:
        logger.error("blockchain/stats error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@router.post("/analyze")
async def analyze_blockchain_address(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    address = data.get("address", "").strip()
    max_transactions = min(int(data.get("max_transactions", 50) or 50), 500)
    include_community_detection = data.get("include_community_detection", True)
    if not address:
        return JSONResponse({"success": False, "error": "Address is required"}, status_code=400)
    if not _BTC_RE.match(address):
        return JSONResponse({"success": False, "error": "Invalid Bitcoin address format"}, status_code=400)
    from backend.api_root import get_chainbreak
    cb = get_chainbreak()
    if not cb:
        return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
    try:
        result = cb.analyze_bitcoin_address(
            address,
            max_transactions=max_transactions,
            include_community_detection=include_community_detection,
        )
        return JSONResponse({"success": True, "data": result})
    except InvalidAddressError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except BlockchainAPIError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=502)
    except Exception as e:
        logger.error("blockchain/analyze error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@router.post("/deep-fetch/start")
async def start_deep_fetch(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON data"}, status_code=400)
    address = data.get("address", "").strip()
    max_limit = min(int(data.get("max_limit", 500)), 2000)
    if not address:
        return JSONResponse({"success": False, "error": "Address is required"}, status_code=400)
    if not _BTC_RE.match(address):
        return JSONResponse({"success": False, "error": "Invalid Bitcoin address format"}, status_code=400)
    job_id = BackgroundJobStore.create_job(address, max_limit)
    thread = threading.Thread(target=_run_background_deep_fetch, args=(job_id, address, max_limit), daemon=True)
    thread.start()
    return JSONResponse({"success": True, "data": {
        "job_id": job_id, "address": address, "max_limit": max_limit, "status": "pending",
        "poll_url": f"/api/blockchain/deep-fetch/status/{job_id}",
        "result_url": f"/api/blockchain/deep-fetch/result/{job_id}",
    }})


@router.get("/deep-fetch/status/{job_id}")
def get_deep_fetch_status(job_id: str):
    job = BackgroundJobStore.get_job(job_id)
    if job is None:
        return JSONResponse({"success": False, "error": "Job not found"}, status_code=404)
    return JSONResponse({"success": True, "data": job})


@router.get("/deep-fetch/result/{job_id}")
def get_deep_fetch_result(job_id: str):
    job = BackgroundJobStore.get_job_result(job_id)
    if job is None:
        return JSONResponse({"success": False, "error": "Job not found"}, status_code=404)
    if job["status"] != "complete":
        return JSONResponse({
            "success": False,
            "error": f"Job not complete, current status: {job['status']}",
            "data": {"status": job["status"], "fetched_count": job["fetched_count"]},
        }, status_code=202)
    return JSONResponse({"success": True, "data": {
        "job_id": job_id, "address": job["address"],
        "total_on_chain": job["total_on_chain"], "fetched_count": job["fetched_count"],
        "transactions": job.get("result", {}).get("txs", []),
    }})


@router.post("/deep-fetch/cancel/{job_id}")
def cancel_deep_fetch(job_id: str):
    if BackgroundJobStore.cancel_job(job_id):
        return JSONResponse({"success": True, "message": "Job cancelled"})
    return JSONResponse({"success": False, "error": "Job not found"}, status_code=404)


@router.get("/recursive-fetch/{address}")
def recursive_fetch(
    address: str,
    depth: int = Query(default=1),
    max_addresses: int = Query(default=50),
    graph: str = Query(default="true"),
):
    if not _BTC_RE.match(address):
        return JSONResponse({"success": False, "error": "Invalid Bitcoin address format"}, status_code=400)
    try:
        from backend.api_gateway import RecursiveFetcher
        depth = min(depth, 3)
        max_addresses = min(max_addresses, 500)
        return_graph = graph.lower() == "true"
        fetcher = BlockchainComFetcher()
        recursive = RecursiveFetcher(fetcher)
        recursive.max_depth = depth
        recursive.max_addresses = max_addresses
        logger.info("Starting recursive fetch for %s... (depth=%d, max_addresses=%d)", address[:12], depth, max_addresses)
        recursive.fetch_address_recursive(address, depth=1)
        if return_graph:
            graph_results = recursive.get_graph_results()
            return JSONResponse({
                "success": True, "data": graph_results,
                "graph": graph_results.get("graph", {}),
                "settings": {"depth": depth, "max_addresses": max_addresses},
            })
        results = recursive.get_results()
        return JSONResponse({"success": True, "data": results, "settings": {"depth": depth, "max_addresses": max_addresses}})
    except Exception as e:
        logger.error("Recursive fetch failed: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@router.get("/address-comprehensive/{address}")
def get_address_comprehensive(address: str, limit: int = Query(default=100)):
    try:
        fetcher = BlockchainComFetcher()
        data = fetcher.fetch_address_comprehensive(address, max_limit=min(limit, 2000))
        return JSONResponse({"success": True, "data": data})
    except RateLimitError:
        return JSONResponse({"success": False, "error": "Rate limit exceeded. Please wait."}, status_code=429)
    except (InvalidAddressError, BlockchainAPIError) as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=404)
    except Exception as e:
        logger.error("address-comprehensive error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@router.post("/unspent")
async def fetch_unspent_endpoint(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    addresses = data.get("addresses", [])
    limit = min(int(data.get("limit", 250)), 1000)
    confirmations = int(data.get("confirmations", 0))
    if not addresses:
        return JSONResponse({"success": False, "error": "addresses list required"}, status_code=400)
    try:
        fetcher = BlockchainComFetcher()
        result = fetcher.fetch_unspent(addresses, limit=limit, confirmations=confirmations)
        utxos = result.get("unspent_outputs", [])
        return JSONResponse({"success": True, "data": {
            "unspent_outputs": utxos, "count": len(utxos), "addresses_queried": len(addresses),
        }})
    except RateLimitError:
        return JSONResponse({"success": False, "error": "Rate limit exceeded"}, status_code=429)
    except BlockchainAPIError as e:
        if "No free" in str(e):
            return JSONResponse({"success": True, "data": {"unspent_outputs": [], "count": 0}})
        return JSONResponse({"success": False, "error": str(e)}, status_code=502)
    except Exception as e:
        logger.error("fetchUnspent error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@router.post("/balance")
async def fetch_balance_endpoint(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    addresses = data.get("addresses", [])
    if not addresses:
        return JSONResponse({"success": False, "error": "addresses required"}, status_code=400)
    try:
        fetcher = BlockchainComFetcher()
        balances = fetcher.fetch_balance(addresses)
        return JSONResponse({"success": True, "data": {"balances": balances}})
    except RateLimitError:
        return JSONResponse({"success": False, "error": "Rate limit exceeded"}, status_code=429)
    except Exception as e:
        logger.error("fetchBalance error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@router.post("/multi-address")
async def fetch_multi_address_endpoint(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    addresses = data.get("addresses", [])
    limit = min(int(data.get("limit", 50)), 200)
    if not addresses:
        return JSONResponse({"success": False, "error": "addresses required"}, status_code=400)
    try:
        fetcher = BlockchainComFetcher()
        graph_data = fetcher.build_multi_address_graph(addresses, tx_limit=limit)
        all_txs: list = []
        seen: set = set()
        for node in graph_data.get("nodes", []):
            if node.get("type") == "transaction":
                rd = node.get("rawData") or {}
                txid = rd.get("hash")
                if txid and txid not in seen:
                    seen.add(txid)
                    all_txs.append(rd)
        return JSONResponse({"success": True, "data": {
            "txs": all_txs, "addresses": addresses, "graph": graph_data,
            "aggregation_info": {
                "total_addresses": len(addresses), "total_transactions": len(all_txs),
                "node_count": graph_data.get("meta", {}).get("node_count", 0),
                "edge_count": graph_data.get("meta", {}).get("edge_count", 0),
                "parallel_mode": False,
            },
        }})
    except RateLimitError:
        return JSONResponse({"success": False, "error": "Rate limit exceeded"}, status_code=429)
    except Exception as e:
        logger.error("multi-address error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@router.get("/network-stats")
def get_network_stats():
    try:
        import requests as _req
        resp = _req.get("https://api.blockchain.info/stats", timeout=8)
        resp.raise_for_status()
        return JSONResponse({"success": True, "data": resp.json()})
    except Exception as e:
        logger.warning("network-stats error: %s", e)
        return JSONResponse({"success": True, "data": {
            "total_fees_btc": 0, "n_btc_mined": 0, "n_tx": 0,
            "note": "network stats temporarily unavailable",
        }})


_VALID_CHART_TYPES = frozenset({
    "transactions-per-second", "market-price", "total-bitcoins", "hash-rate",
    "difficulty", "n-transactions", "mempool-size", "n-transactions-per-block",
    "blocks-size", "avg-block-size", "miners-revenue", "transaction-fees",
    "cost-per-transaction", "n-unique-addresses", "my-wallet-n-users",
})
_VALID_TIMESPANS = frozenset({"1days", "7days", "30days", "60days", "180days", "1year", "all"})


@router.get("/chart/{chart_type}")
def get_chart_data(chart_type: str, timespan: str = Query(default="30days")):
    if chart_type not in _VALID_CHART_TYPES:
        return JSONResponse({"success": False, "error": f"Unknown chart type '{chart_type}'"}, status_code=400)
    if timespan not in _VALID_TIMESPANS:
        timespan = "30days"
    try:
        import requests as _req
        url = f"https://api.blockchain.info/charts/{chart_type}"
        resp = _req.get(url, params={"timespan": timespan, "format": "json", "cors": "true"}, timeout=10)
        resp.raise_for_status()
        return JSONResponse({"success": True, "data": resp.json()})
    except Exception as e:
        logger.warning("chart/%s error: %s", chart_type, e)
        return JSONResponse({"success": True, "data": {
            "status": "unavailable", "name": chart_type, "period": timespan, "values": [],
        }})


@router.get("/latest-block")
def get_latest_block():
    try:
        import requests as _req
        resp = _req.get("https://blockchain.info/latestblock", timeout=8)
        resp.raise_for_status()
        return JSONResponse({"success": True, "data": resp.json()})
    except Exception as e:
        logger.error("latest-block error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": "Unable to fetch latest block"}, status_code=502)


@router.get("/unconfirmed-transactions")
def get_unconfirmed_transactions(limit: int = Query(default=100)):
    try:
        import requests as _req
        resp = _req.get(
            "https://blockchain.info/unconfirmed-transactions",
            params={"format": "json"}, timeout=10,
        )
        resp.raise_for_status()
        txs = resp.json().get("txs", [])[:min(limit, 500)]
        return JSONResponse({"success": True, "data": {"transactions": txs, "count": len(txs)}})
    except Exception as e:
        logger.warning("mempool error: %s", e)
        return JSONResponse({"success": True, "data": {"transactions": [], "note": "mempool unavailable"}})


@router.get("/blocks-today")
def get_blocks_today():
    try:
        import requests as _req, time as _t
        resp = _req.get(
            f"https://blockchain.info/blocks/{int(_t.time() * 1000)}",
            params={"format": "json"}, timeout=10,
        )
        resp.raise_for_status()
        return JSONResponse({"success": True, "data": resp.json()})
    except Exception as e:
        logger.warning("blocks-today error: %s", e)
        return JSONResponse({"success": True, "data": {"blocks": []}})


@router.get("/blocks-by-pool/{pool_name}")
def get_blocks_by_pool(pool_name: str):
    import re as _re
    if not _re.match(r'^[A-Za-z0-9._\- ]{1,80}$', pool_name):
        return JSONResponse({"success": False, "error": "Invalid pool name"}, status_code=400)
    try:
        import requests as _req
        import urllib.parse as _up
        resp = _req.get(
            f"https://blockchain.info/blocks/{_up.quote(pool_name, safe='')}",
            params={"format": "json"}, timeout=10,
        )
        resp.raise_for_status()
        return JSONResponse({"success": True, "data": resp.json()})
    except Exception as e:
        logger.warning("blocks-by-pool/%s error: %s", pool_name, e)
        return JSONResponse({"success": True, "data": {"blocks": []}})
