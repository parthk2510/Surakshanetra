from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import logging

from .services.blockchain.blockchain_fetcher import BlockchainComFetcher, FetcherConfig

logger = logging.getLogger(__name__)

bp = APIRouter(tags=["frontend"])

DATA_DIR = Path("data/graph")
DATA_DIR.mkdir(parents=True, exist_ok=True)

logger.info("Frontend API serving graph files from %s", DATA_DIR.resolve())


@bp.get("/api/graph/list")
def list_graphs():
    try:
        files = sorted([p.name for p in DATA_DIR.glob("*.json")])
        return JSONResponse({"success": True, "files": files})
    except Exception as e:
        logger.error("list_graphs error: %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@bp.get("/api/graph/get")
async def get_graph(name: str = ""):
    try:
        name = name.strip()
        if not name:
            return JSONResponse({"success": False, "error": "name required"}, status_code=400)
        graph_root = DATA_DIR.resolve()
        file_path = (graph_root / name).resolve()
        # Prevent path traversal outside the graph data directory
        if not str(file_path).startswith(str(graph_root)):
            return JSONResponse({"success": False, "error": "Graph not found"}, status_code=404)
        if not file_path.exists():
            return JSONResponse({"success": False, "error": "Graph not found"}, status_code=404)
        return FileResponse(str(file_path), media_type="application/json")
    except Exception as e:
        logger.error("get_graph error: %s", e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@bp.get("/frontend/{filename:path}")
def serve_frontend(filename: str):
    root = Path("frontend").resolve()
    file_path = (root / filename).resolve()
    # Prevent path traversal outside the frontend directory
    if not str(file_path).startswith(str(root)):
        return JSONResponse({"error": "File not found"}, status_code=404)
    if not file_path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(str(file_path))
