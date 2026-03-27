from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from typing import Dict, List, Any
import logging
from pathlib import Path

from backend.services.blockchain.blockchain_fetcher import BlockchainComFetcher, FetcherConfig
from backend.core.data_ingestion_json import JSONDataIngestor, CaseFileManager

logger = logging.getLogger(__name__)

api_bp = APIRouter(prefix="/api/v2", tags=["api_v2"])

blockchain_fetcher = None
data_ingestor = None
case_manager = None


def init_services(data_dir: str = "data"):
    global blockchain_fetcher, data_ingestor, case_manager
    config = FetcherConfig(rate_limit_s=0.2, timeout=30, max_retries=5, cache_enabled=True, concurrent_requests=5)
    blockchain_fetcher = BlockchainComFetcher(config=config)
    case_manager = CaseFileManager(data_dir=f"{data_dir}/cases")
    data_ingestor = JSONDataIngestor(data_dir=data_dir, case_manager=case_manager)
    logger.info("API v2 services initialized")


@api_bp.post("/address/single")
async def fetch_single_address(request: Request):
    data = await request.json()
    address = data.get("address")
    tx_limit = data.get("tx_limit", 50)
    case_id = data.get("case_id")
    if not address:
        return JSONResponse({"success": False, "error": "Address required"}, status_code=400)
    try:
        addr_data = blockchain_fetcher.fetch_address(address, limit=tx_limit)
        if case_id:
            data_ingestor.ingest_address_batch([address], case_id=case_id, fetch_callback=lambda a: blockchain_fetcher.fetch_address(a, limit=tx_limit))
        return JSONResponse({"success": True, "address": address, "data": addr_data, "case_id": case_id})
    except Exception as e:
        logger.error(f"Error fetching address {address}: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.post("/address/batch")
async def fetch_address_batch(request: Request):
    data = await request.json()
    addresses = data.get("addresses", [])
    tx_limit = data.get("tx_limit", 50)
    case_id = data.get("case_id")
    if not addresses:
        return JSONResponse({"success": False, "error": "Addresses required"}, status_code=400)
    try:
        result = data_ingestor.ingest_address_batch(addresses, case_id=case_id, fetch_callback=lambda addr: blockchain_fetcher.fetch_address(addr, limit=tx_limit), max_workers=3)
        return JSONResponse({"success": True, "result": result, "case_id": case_id})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.post("/address/cluster")
async def fetch_address_cluster(request: Request):
    data = await request.json()
    address = data.get("address")
    max_depth = data.get("max_depth", 2)
    if not address:
        return JSONResponse({"success": False, "error": "Address required"}, status_code=400)
    try:
        cluster = blockchain_fetcher.fetch_address_cluster(address, max_depth=max_depth)
        return JSONResponse({"success": True, "cluster": cluster})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.post("/graph/multi-address")
async def build_multi_address_graph(request: Request):
    data = await request.json()
    addresses = data.get("addresses", [])
    tx_limit = data.get("tx_limit", 50)
    case_id = data.get("case_id")
    if not addresses:
        return JSONResponse({"success": False, "error": "Addresses required"}, status_code=400)
    try:
        graph_data = blockchain_fetcher.build_multi_address_graph(addresses, tx_limit=tx_limit)
        if case_id:
            data_ingestor.ingest_address_batch(addresses, case_id=case_id, fetch_callback=lambda addr: blockchain_fetcher.fetch_address(addr, limit=tx_limit))
        return JSONResponse({"success": True, "graph": graph_data})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.post("/case/create")
async def create_case(request: Request):
    data = await request.json()
    case_id = data.get("case_id")
    metadata = data.get("metadata", {})
    if not case_id:
        return JSONResponse({"success": False, "error": "case_id required"}, status_code=400)
    try:
        case_manager.create_case(case_id, metadata=metadata)
        return JSONResponse({"success": True, "case_id": case_id})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.get("/case/{case_id}")
def get_case(case_id: str):
    try:
        case_data = case_manager.load_case(case_id)
        if not case_data:
            return JSONResponse({"success": False, "error": "Case not found"}, status_code=404)
        return JSONResponse({"success": True, "case": case_data})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.post("/case/{case_id}/add-address")
async def add_address_to_case(case_id: str, request: Request):
    data = await request.json()
    address = data.get("address")
    tx_limit = data.get("tx_limit", 50)
    if not address:
        return JSONResponse({"success": False, "error": "Address required"}, status_code=400)
    try:
        result = data_ingestor.ingest_address_batch([address], case_id=case_id, fetch_callback=lambda addr: blockchain_fetcher.fetch_address(addr, limit=tx_limit))
        return JSONResponse({"success": True, "result": result})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.get("/case/{case_id}/graph")
def get_case_graph(case_id: str):
    try:
        graph_data = data_ingestor.get_graph_for_case(case_id)
        return JSONResponse({"success": True, "graph": graph_data})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.post("/case/{case_id}/export")
async def export_case(case_id: str, request: Request):
    data = await request.json()
    fmt = data.get("format", "json")
    try:
        export_path = data_ingestor.export_case_graph(case_id, format=fmt)
        return JSONResponse({"success": True, "export_path": export_path, "format": fmt})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.get("/case/list")
def list_cases():
    try:
        cases = case_manager.list_cases()
        return JSONResponse({"success": True, "cases": cases})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.get("/case/{case_id}/pending-addresses")
def get_pending_addresses(case_id: str):
    try:
        pending = data_ingestor.get_pending_addresses()
        return JSONResponse({"success": True, "pending_addresses": pending})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.get("/transaction/{tx_hash}")
def get_transaction(tx_hash: str):
    try:
        tx_data = blockchain_fetcher.fetch_tx(tx_hash)
        return JSONResponse({"success": True, "transaction": tx_data})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@api_bp.get("/address/{address}/statistics")
def get_address_statistics(address: str):
    try:
        stats = data_ingestor.get_address_statistics(address)
        return JSONResponse({"success": True, "statistics": stats})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
