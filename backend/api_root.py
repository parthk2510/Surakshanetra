import copy
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse as _JSONResponse
from fastapi.exceptions import RequestValidationError
from .api.v1.blockchain_routes import router as _blockchain_router, BackgroundJobStore
import time as _time_module
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid as _uuid
import threading
import re as _input_re
import os
from fastapi import FastAPI, Request, File, UploadFile, Query, Depends, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
import traceback
import json
from pathlib import Path
from datetime import datetime
from .chainbreak import ChainBreak
from .api_frontend import bp as frontend_bp
from .core.Community_Detection.louvain_simple_btc import run_louvain_algorithm
from .core.Community_Detection.leiden_algorithm_btc import run_leiden_algorithm
from .core.Community_Detection.label_propagation_btc import run_label_propagation
from .core.Community_Detection.infomap_algorithm_btc import run_infomap_algorithm
from .database.auth import _get_client_ip 

from .services.blockchain.blockchain_fetcher import (
    BlockchainComFetcher,
    BlockchainAPIError,
    InvalidAddressError,
    RateLimitError,
    TransactionNotFoundError,
    BlockNotFoundError,
)

try:
    from .logger.structured_logger import slog, log_endpoint, init_structured_logging
    HAS_STRUCTURED_LOGGING = True
except ImportError:
    HAS_STRUCTURED_LOGGING = False
    slog = None
    def log_endpoint(x=None): return lambda f: f

try:
    from backend.services.temporal.pipeline import TemporalAnalysisPipeline, create_mock_snapshots
    from backend.services.temporal.data_loader import TemporalDataLoader
    HAS_TEMPORAL_ANALYSIS = True
except ImportError as e:
    print(f"Warning: Temporal analysis not available: {e}")
    HAS_TEMPORAL_ANALYSIS = False

try:
    from .database.models import init_db, get_db
    from .database.auth import auth_bp, jwt_required, get_current_user, admin_required
    from .api_gateway import api_gateway, RecursiveFetcher
    from .logger.app_logger import setup_logging, get_recent_logs, RequestLogger
    setup_logging()
    HAS_AUTH = True
except ImportError as e:
    try:
        from .database.models import init_db, get_db
        from .database.auth import auth_bp, jwt_required, get_current_user, admin_required
        from .api_gateway import api_gateway, RecursiveFetcher
        from .logger.app_logger import setup_logging, get_recent_logs, RequestLogger
        setup_logging()
        HAS_AUTH = True
    except ImportError as e:
        print(f"Warning: Auth modules not loaded: {e}")
        HAS_AUTH = False
        def get_current_user(): return None
        def admin_required(): return None
        RequestLogger = None

try:
    from .logger.logger import (
        logger as custom_logger,
        log_execution_time,
        log_api_endpoint,
        format_error_response,
        perf_tracker
    )
except ImportError as e:
    print(f"Warning: Could not import logger: {e}")
    custom_logger = None
    log_execution_time = lambda *a, **kw: lambda f: f
    def log_api_endpoint(f): return f
    format_error_response = None
    perf_tracker = None

try:
    from .utils.json_encoder import safe_json_response, NumpyEncoder
except ImportError:
    def safe_json_response(x): return x
    NumpyEncoder = None

logger = logging.getLogger(__name__)


_CSV_MAX_BYTES = 50 * 1024 * 1024


def _sanitize_address(addr: str) -> str:
    """Strip whitespace and validate BTC/general address format."""
    addr = (addr or "").strip()[:100]
    return addr


def _is_valid_btc_address(addr: str) -> bool:
    return bool(_input_re.match(
        r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$|^bc1[a-z0-9]{39,59}$",
        addr
    ))


# ── Background job stores ─────────────────────────────────────────────────────


class UpiIngestionJobStore:
    _lock = threading.Lock()
    _jobs: dict = {}

    @classmethod
    def create_job(cls, csv_path: str) -> str:
        job_id = _uuid.uuid4().hex[:16]
        with cls._lock:
            cls._jobs[job_id] = {
                "job_id": job_id, "csv_path": csv_path, "status": "pending",
                "progress": 0, "message": "Queued", "result": None, "error": None,
                "created_at": datetime.utcnow().isoformat(), "completed_at": None,
            }
        return job_id

    @classmethod
    def get_job(cls, job_id: str):
        with cls._lock:
            job = cls._jobs.get(job_id)
            return dict(job) if job else None

    @classmethod
    def update_job(cls, job_id: str, **kwargs):
        with cls._lock:
            if job_id in cls._jobs:
                cls._jobs[job_id].update(kwargs)

    @classmethod
    def get_active_job(cls):
        with cls._lock:
            for job in cls._jobs.values():
                if job["status"] in ("pending", "running"):
                    return dict(job)
        return None


def _run_upi_ingestion(job_id: str, csv_path: str, driver, batch_size: int = 500):
    logger.info("[Ingestion %s] Starting: %s", job_id, csv_path)
    try:
        UpiIngestionJobStore.update_job(
            job_id, status="running", progress=5, message="Reading CSV and preparing batches…")
        result = load_upi_csv_to_neo4j(csv_path, driver, batch_size=batch_size)
        loaded = result.get("transactionsLoaded", 0)
        errors = result.get("rowErrors", 0)
        UpiIngestionJobStore.update_job(
            job_id, status="complete", progress=100,
            message=f"Loaded {loaded} transactions ({errors} row errors)",
            result=result, completed_at=datetime.utcnow().isoformat()
        )
    except FileNotFoundError as exc:
        UpiIngestionJobStore.update_job(job_id, status="error", error=str(
            exc), message=f"File not found: {exc}", completed_at=datetime.utcnow().isoformat())
    except Exception as exc:
        logger.error("[Ingestion %s] Failed: %s", job_id, exc, exc_info=True)
        UpiIngestionJobStore.update_job(job_id, status="error", error=str(
            exc), message=f"Ingestion failed: {str(exc)[:300]}", completed_at=datetime.utcnow().isoformat())
    finally:
        try:
            import tempfile
            import os as _os
            tmp_dir = tempfile.gettempdir()
            if csv_path.startswith(tmp_dir) and _os.path.exists(csv_path):
                _os.unlink(csv_path)
        except Exception:
            pass


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="ChainBreak API", version="2.0.0")

_ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5000,http://127.0.0.1:3000,http://127.0.0.1:5000"
    ).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization",
                   "X-CSRF-TOKEN", "X-Request-ID"],
)

if RequestLogger is not None:
    app.add_middleware(RequestLogger)

BASE_DIR = Path(__file__).resolve().parent.parent
GRAPH_DIR = BASE_DIR / "data" / "graph"
CASES_DIR = BASE_DIR / "data" / "cases"
UPI_CASES_DIR = BASE_DIR / "data" / "upi-cases"
TEMPORAL_REPORTS_DIR = BASE_DIR / "data" / "temporal_reports"

for _d in (GRAPH_DIR, CASES_DIR, UPI_CASES_DIR, TEMPORAL_REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

logger.info(
    f"Data dirs: graph={GRAPH_DIR}, cases={CASES_DIR}, upi_cases={UPI_CASES_DIR}")


@app.on_event("startup")
async def startup_event():
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"DB init error: {e}")
    if HAS_STRUCTURED_LOGGING:
        logger.info("Structured logging ready")


# Register routers
if HAS_AUTH:
    app.include_router(auth_bp)

try:
    from .api.v1.user_management_routes import user_mgmt_bp
    app.include_router(user_mgmt_bp)
except ImportError as e:
    logger.warning(f"User management routes not loaded: {e}")

# ── RGCN Fraud Detection router ───────────────────────────────────────────────
try:
    from .services.RGCN.api.router import router as _rgcn_router
    app.include_router(_rgcn_router, prefix="/api")
    logger.info("RGCN router registered at /api/rgcn/*")
except ImportError as e:
    logger.warning(f"RGCN router not loaded: {e}")

app.include_router(_blockchain_router)
app.include_router(frontend_bp)


# ── ChainBreak singleton ──────────────────────────────────────────────────────

_chainbreak_instance = None
_chainbreak_initialized = False


def get_chainbreak():
    global _chainbreak_instance, _chainbreak_initialized
    if _chainbreak_instance is not None and _chainbreak_initialized:
        return _chainbreak_instance
    try:
        from .chainbreak import ChainBreak
        _chainbreak_instance = ChainBreak()
        _chainbreak_initialized = True
        logger.info("ChainBreak instance created successfully")
        return _chainbreak_instance
    except Exception as e:
        logger.error(f"Failed to initialize ChainBreak: {e}")
        _chainbreak_initialized = False
        return None


def reset_chainbreak():
    global _chainbreak_instance, _chainbreak_initialized
    if _chainbreak_instance is not None:
        try:
            _chainbreak_instance.close()
        except Exception as e:
            logger.warning(f"Error closing ChainBreak: {e}")
    _chainbreak_instance = None
    _chainbreak_initialized = False


def _get_neo4j_driver():
    """
    Get the active Neo4j driver.
    Primary: extract from ChainBreak singleton's data_ingestor.
    Fallback: try neo4j_config module (optional).
    """
    # --- Primary: get driver from ChainBreak singleton ---
    cb = _chainbreak_instance
    if cb is not None:
        try:
            driver = getattr(cb, "data_ingestor", None)
            if driver is not None:
                driver = getattr(driver, "driver", None)
            if driver is not None:
                return driver
        except Exception:
            pass

    # --- Fallback: neo4j_config module (may not exist) ---
    try:
        from .neo4j_config import get_neo4j_manager
        manager = get_neo4j_manager()
        if manager.is_available():
            return manager.driver
    except (ImportError, Exception):
        pass

    # --- Fallback: build driver from env vars then config.yaml ---
    try:
        from neo4j import GraphDatabase
        uri = os.environ.get("NEO4J_URI")
        user = os.environ.get("NEO4J_USERNAME")
        password = os.environ.get("NEO4J_PASSWORD")
        if not uri:
            try:
                import yaml
                _config_path = Path(__file__).resolve().parent.parent / "config.yaml"
                with open(_config_path, "r") as f:
                    cfg = yaml.safe_load(f)
                neo4j_cfg = cfg.get("neo4j", {})
                uri = neo4j_cfg.get("uri", "bolt://localhost:7687")
                user = user or neo4j_cfg.get("username", "neo4j")
                password = password or neo4j_cfg.get("password")
            except Exception:
                uri = "bolt://localhost:7687"
                user = user or "neo4j"
        if not password:
            logger.warning("NEO4J_PASSWORD not configured — Neo4j connection will likely fail")
            password = ""
        driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            max_connection_pool_size=100,
            connection_timeout=30,
            max_transaction_retry_time=30,
        )
        driver.verify_connectivity()
        logger.info(
            "_get_neo4j_driver: connected via env/config fallback to %s", uri)
        return driver
    except Exception as e:
        logger.warning(f"_get_neo4j_driver: all strategies failed — {e}")
        return None


_FRONTEND_BUILD = Path("frontend/build").resolve()


def _serve_index():
    index = _FRONTEND_BUILD / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"error": "Frontend not built. Run: cd frontend && npm run build"}, status_code=503)


# ── Static / frontend routes ──────────────────────────────────────────────────

@app.get("/")
def index_new():
    return _serve_index()


@app.get("/manifest.json")
def serve_manifest():
    f = _FRONTEND_BUILD / "manifest.json"
    return FileResponse(str(f)) if f.exists() else JSONResponse({"error": "Not found"}, status_code=404)


@app.get("/favicon.ico")
def serve_favicon():
    f = _FRONTEND_BUILD / "favicon.ico"
    return FileResponse(str(f)) if f.exists() else JSONResponse({"error": "Not found"}, status_code=404)


@app.get("/static/{path:path}")
def serve_static(path: str):
    static_root = (_FRONTEND_BUILD / "static").resolve()
    f = static_root / path
    try:
        f = f.resolve()
    except Exception:
        return JSONResponse({"error": "Static file not found"}, status_code=404)
    # Prevent path traversal outside the static directory
    if not str(f).startswith(str(static_root)):
        return JSONResponse({"error": "Static file not found"}, status_code=404)
    return FileResponse(str(f)) if f.exists() else JSONResponse({"error": "Static file not found"}, status_code=404)


# ── Core API routes ───────────────────────────────────────────────────────────


@app.get("/api/mode")
def get_backend_mode():
    try:
        cb = get_chainbreak()
        if cb:
            return JSONResponse({"success": True, "data": {"backend_mode": cb.get_backend_mode(), "neo4j_available": cb.is_neo4j_available()}})
        return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/status")
def get_system_status():
    try:
        cb = get_chainbreak()
        if cb:
            return JSONResponse({"success": True, "data": cb.get_system_status()})
        return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/health")
def health_check():
    return JSONResponse({"status": "healthy", "auth_enabled": HAS_AUTH, "version": "2.0.0"})


# ── Decision Engine ───────────────────────────────────────────────────────────

@app.get("/api/decision/{identifier}")
def decision_engine(
    identifier: str,
    traditional_risk_score: float = Query(0.0, ge=0.0, le=1.0),
    rgcn_weight: float = Query(0.55, ge=0.0, le=1.0),
    community_weight: float = Query(0.20, ge=0.0, le=1.0),
    traditional_weight: float = Query(0.25, ge=0.0, le=1.0),
):
    """
    Comprehensive decision endpoint combining RGCN, community detection and
    traditional heuristics into a single confidence-scored verdict.

    ``identifier`` is a UPI account ID or Bitcoin address.
    """
    try:
        from .services.decision_engine import DecisionEngine
        result = DecisionEngine.analyze(
            account_id=identifier,
            traditional_risk_score=traditional_risk_score,
            rgcn_weight=rgcn_weight,
            community_weight=community_weight,
            traditional_weight=traditional_weight,
        )
        return JSONResponse({"success": True, "data": result})
    except Exception as exc:
        logger.error("Decision engine error for %s: %s", identifier, exc)
        return JSONResponse(
            {"success": False, "error": str(exc)}, status_code=500
        )


@app.post("/api/decision/batch")
async def decision_engine_batch(request: Request):
    """
    Batch decision endpoint – accepts a list of identifiers and returns
    a decision for each.  Body: {"identifiers": [...], "options": {...}}
    """
    try:
        body = await request.json()
        identifiers = body.get("identifiers", [])
        options = body.get("options", {})
        if not identifiers or not isinstance(identifiers, list):
            return JSONResponse(
                {"success": False, "error": "identifiers must be a non-empty list"},
                status_code=400,
            )
        if len(identifiers) > 200:
            return JSONResponse(
                {"success": False, "error": "Maximum 200 identifiers per batch"},
                status_code=400,
            )
        from .services.decision_engine import DecisionEngine
        results = {}
        for iid in identifiers:
            if not isinstance(iid, str):
                continue
            results[iid] = DecisionEngine.analyze(
                account_id=iid,
                traditional_risk_score=float(
                    options.get("traditional_risk_score", 0.0)),
                rgcn_weight=float(options.get("rgcn_weight", 0.55)),
                community_weight=float(options.get("community_weight", 0.20)),
                traditional_weight=float(
                    options.get("traditional_weight", 0.25)),
            )
        return JSONResponse({"success": True, "data": results, "count": len(results)})
    except Exception as exc:
        logger.error("Batch decision engine error: %s", exc)
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


# ── Graph routes ──────────────────────────────────────────────────────────────

@app.get("/api/graph/list")
def list_graphs():
    try:
        files = [f.name for f in GRAPH_DIR.glob("*.json")]
        return JSONResponse({"success": True, "files": files})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.delete("/api/graph/delete")
async def delete_graph(request: Request):
    try:
        data = await request.json()
        filename = data.get("filename")
        if not filename:
            return JSONResponse({"success": False, "error": "Filename is required"}, status_code=400)
        if ".." in filename or "/" in filename or "\\" in filename:
            return JSONResponse({"success": False, "error": "Invalid filename"}, status_code=400)
        file_path = GRAPH_DIR / filename
        if not file_path.exists():
            return JSONResponse({"success": False, "error": "File not found"}, status_code=404)
        file_path.unlink()
        return JSONResponse({"success": True, "message": f"Graph {filename} deleted successfully"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/graph/download")
def download_graph(filename: str = Query(default="")):
    try:
        if not filename:
            return JSONResponse({"success": False, "error": "Filename is required"}, status_code=400)
        if ".." in filename or "/" in filename or "\\" in filename:
            return JSONResponse({"success": False, "error": "Invalid filename"}, status_code=400)
        file_path = GRAPH_DIR / filename
        if not file_path.exists():
            return JSONResponse({"success": False, "error": "File not found"}, status_code=404)
        return FileResponse(str(file_path), filename=filename)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/graph/address")
async def fetch_graph_address(request: Request):
    try:
        data = await request.json()
        address = data.get("address", "").strip()
        tx_limit = data.get("tx_limit", 50)
        if not address:
            return JSONResponse({"success": False, "error": "Address is required"}, status_code=400)
        if not isinstance(tx_limit, int) or tx_limit < 1 or tx_limit > 200:
            return JSONResponse({"success": False, "error": "Transaction limit must be between 1 and 200"}, status_code=400)
        cb = get_chainbreak()
        if not cb:
            return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
        try:
            fetcher = BlockchainComFetcher()
            graph = fetcher.build_graph_for_address(address, tx_limit=tx_limit)
        except RateLimitError:
            return JSONResponse({"success": False, "error": "API rate limit exceeded. Please try again later."}, status_code=429)
        except BlockchainAPIError as e:
            return JSONResponse({"success": False, "error": f"Blockchain API error: {str(e)}"}, status_code=502)
        if not graph or not isinstance(graph, dict):
            return JSONResponse({"success": False, "error": "Invalid graph data received"}, status_code=500)
        nodes = graph.get("nodes", [])
        if len(nodes) == 0:
            return JSONResponse({"success": False, "error": "No transaction data found for this address"}, status_code=404)
        safe_address = _input_re.sub(r'[^A-Za-z0-9_\-]', '_', address)
        filename = f"graph_{safe_address[:12]}_{tx_limit}.json"
        file_path = GRAPH_DIR / filename
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(graph, f, indent=2, ensure_ascii=False)
        return JSONResponse({"success": True, "file": filename, "graph": graph, "meta": graph.get("meta", {}), "stats": {"nodes": len(nodes), "edges": len(graph.get("edges", [])), "tx_limit": tx_limit}})
    except Exception as e:
        logger.error(
            f"Unexpected error in fetch_graph_address: {traceback.format_exc()}")
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@app.get("/api/graph/get")
def get_graph(name: str = Query(default="")):
    try:
        if not name:
            return JSONResponse({"success": False, "error": "Name parameter required"}, status_code=400)
        file_path = GRAPH_DIR / name
        if not file_path.exists():
            return JSONResponse({"success": False, "error": "Graph not found"}, status_code=404)
        with open(file_path, "r") as f:
            graph_json = json.load(f)
        return JSONResponse(graph_json)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Analyze address (main forensic endpoint) ──────────────────────────────────

@app.post("/api/analyze")
@app.post("/api/analyze/address")
async def analyze_address(request: Request):
    import re
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    address = data.get("address", "").strip()
    tx_limit = min(int(data.get("tx_limit", 50) or 50), 200)
    include_community = data.get("include_community", True)
    if not address:
        return JSONResponse({"success": False, "error": "Address is required"}, status_code=400)
    if not _input_re.match(r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$|^bc1[a-z0-9]{39,59}$", address):
        return JSONResponse({"success": False, "error": "Invalid Bitcoin address format"}, status_code=400)
    cb = get_chainbreak()
    if not cb:
        return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
    try:
        result = cb.analyze_address(
            address, tx_limit=tx_limit, include_community=include_community)
        if not result:
            return JSONResponse({"success": False, "error": "No data found"}, status_code=404)
        return JSONResponse({"success": True, "data": result})
    except InvalidAddressError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except BlockchainAPIError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=502)
    except Exception as e:
        logger.error("analyze_address error: %s\n%s", e, traceback.format_exc())
        return JSONResponse({"success": False, "error": "Internal server error"}, status_code=500)


@app.get("/api/analyze/{address}")
async def analyze_address_get(address: str, tx_limit: int = Query(default=50), include_community: bool = Query(default=True)):
    import re
    if not _input_re.match(r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$|^bc1[a-z0-9]{39,59}$", address):
        return JSONResponse({"success": False, "error": "Invalid Bitcoin address format"}, status_code=400)
    cb = get_chainbreak()
    if not cb:
        return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
    try:
        result = cb.analyze_address(address, tx_limit=min(
            tx_limit, 200), include_community=include_community)
        if not result:
            return JSONResponse({"success": False, "error": "No data found"}, status_code=404)
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Export / Report ────────────────────────────────────────────────────────────

@app.post("/api/export")
async def export_graph(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    graph_data = data.get("graph_data")
    export_format = data.get("format", "json").lower()
    if not graph_data:
        return JSONResponse({"success": False, "error": "graph_data is required"}, status_code=400)
    if export_format not in ["json", "csv", "gexf"]:
        return JSONResponse({"success": False, "error": "Format must be json, csv, or gexf"}, status_code=400)
    cb = get_chainbreak()
    if not cb:
        return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
    try:
        result = cb.export_data(graph_data, format=export_format)
        return JSONResponse({"success": True, "data": result, "format": export_format})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/report")
async def generate_report(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    graph_data = data.get("graph_data")
    report_format = data.get("format", "json").lower()
    include_sections = data.get("include_sections", [])
    if not graph_data:
        return JSONResponse({"success": False, "error": "graph_data is required"}, status_code=400)
    cb = get_chainbreak()
    if not cb:
        return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
    try:
        result = cb.generate_report(
            graph_data, format=report_format, include_sections=include_sections)
        return JSONResponse({"success": True, "data": result, "format": report_format})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Address utilities ──────────────────────────────────────────────────────────

@app.get("/api/addresses")
def get_addresses(q: str = Query(default=""), limit: int = Query(default=10)):
    try:
        cb = get_chainbreak()
        if not cb:
            return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
        results = cb.search_addresses(q, limit=min(limit, 100))
        return JSONResponse({"success": True, "data": results})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/statistics")
def get_statistics():
    try:
        cb = get_chainbreak()
        if not cb:
            return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
        stats = cb.get_statistics()
        return JSONResponse({"success": True, "data": stats})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Community detection ───────────────────────────────────────────────────────

@app.post("/api/louvain")
async def run_louvain(request: Request):
    try:
        data = await request.json()
        graph_data = data.get("graph_data") or data.get("graphData") or data
        result = run_louvain_algorithm(graph_data)
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        logger.error(f"Louvain failed: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/leiden")
async def run_leiden(request: Request):
    try:
        data = await request.json()
        graph_data = data.get("graph_data") or data.get("graphData") or data
        result = run_leiden_algorithm(graph_data)
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        logger.error(f"Leiden failed: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/label-propagation")
async def run_lp(request: Request):
    try:
        data = await request.json()
        graph_data = data.get("graph_data") or data.get("graphData") or data
        result = run_label_propagation(graph_data)
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/infomap")
async def run_info(request: Request):
    try:
        data = await request.json()
        graph_data = data.get("graph_data") or data.get("graphData") or data
        result = run_infomap_algorithm(graph_data)
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Case management (RBAC-aware, absolute paths) ─────────────────────────────

def _clean_case_id(raw: str) -> str:
    """Return a sanitized CASE-<id> string from any raw input."""
    s = raw.replace(".json", "").strip()
    return s if s.startswith("CASE-") else f"CASE-{s}"


@app.get("/api/cases")
def list_cases(current_user=Depends(get_current_user)):
    """List all saved blockchain case files. Requires authentication."""
    try:
        if not CASES_DIR.exists():
            return JSONResponse({"success": True, "cases": []})
        is_admin = current_user is not None and getattr(
            current_user, "role", "") == "admin"
        current_uid = getattr(current_user, "id",
                              None) if current_user else None
        cases = []
        for cf in CASES_DIR.glob("CASE-*.json"):
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                meta = data.get("metadata", {})
                if not meta.get("caseId"):
                    meta["caseId"] = cf.stem
                # RBAC: non-admins only see their own cases (matched by saved userId)
                if not is_admin and current_uid is not None:
                    owner = meta.get("userId") or meta.get("createdBy")
                    if owner and str(owner) != str(current_uid):
                        continue
                cases.append({
                    "filename": cf.name,
                    "caseId": meta.get("caseId", cf.stem),
                    "lastUpdated": meta.get("lastUpdated", meta.get("timestamp", "")),
                    "createdAt": meta.get("createdAt", meta.get("created_at", "")),
                    "nodeCount": meta.get("nodeCount", 0),
                    "edgeCount": meta.get("edgeCount", 0),
                    "userId": meta.get("userId", ""),
                    "createdBy": meta.get("createdBy", meta.get("created_by", "")),
                    "primaryAddress": meta.get("primaryAddress", ""),
                    "metadata": meta,
                })
            except Exception as e:
                logger.warning(f"Failed to read case file {cf}: {e}")
        cases.sort(key=lambda x: x["metadata"].get(
            "lastUpdated", ""), reverse=True)
        return JSONResponse({"success": True, "cases": cases[:100]})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, current_user=Depends(get_current_user)):
    """Fetch a single case file by ID. Requires authentication."""
    try:
        clean_id = _clean_case_id(case_id)
        case_file = CASES_DIR / f"{clean_id}.json"
        if not case_file.exists():
            return JSONResponse({"success": False, "error": f"Case {clean_id} not found"}, status_code=404)
        with open(case_file, "r", encoding="utf-8") as f:
            case_data = json.load(f)
        if not case_data.get("metadata", {}).get("caseId"):
            case_data.setdefault("metadata", {})["caseId"] = clean_id
        return JSONResponse(case_data)
    except json.JSONDecodeError:
        return JSONResponse({"success": False, "error": "Case file is corrupted"}, status_code=500)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/cases")
async def save_case(request: Request, current_user=Depends(get_current_user)):
    """Save a blockchain investigation case. Requires authentication."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    try:
        case_data = data.get("case_data") or data
        metadata = case_data.setdefault("metadata", {})
        # Stamp the saving user so RBAC filtering works on list
        if current_user:
            metadata.setdefault("userId", str(getattr(current_user, "id", "")))
            metadata.setdefault("createdBy", getattr(
                current_user, "username", ""))
        case_id = metadata.get("caseId")
        if not case_id:
            ts = datetime.utcnow().strftime("%b-%d-%Y-%H%M")
            addr = metadata.get("primaryAddress", "Unknown")[:10]
            case_id = f"CASE-{addr}-{ts}"
            metadata["caseId"] = case_id
        metadata["lastUpdated"] = datetime.utcnow().isoformat() + "Z"
        clean_id = _clean_case_id(case_id)
        file_path = CASES_DIR / f"{clean_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(case_data, f, indent=2, ensure_ascii=False, default=str)
        return JSONResponse({"success": True, "caseId": clean_id, "filename": f"{clean_id}.json",
                             "message": f"Case {clean_id} saved"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/cases/save")
async def save_case_alt(request: Request, current_user=Depends(get_current_user)):
    return await save_case(request, current_user)


@app.delete("/api/cases/{case_id}")
def delete_case(case_id: str, current_user=Depends(get_current_user)):
    """Delete a case file. Admins can delete any case; users can delete their own."""
    try:
        clean_id = _clean_case_id(case_id)
        case_file = CASES_DIR / f"{clean_id}.json"
        if not case_file.exists():
            return JSONResponse({"success": False, "error": "Case not found"}, status_code=404)
        # RBAC ownership check
        is_admin = current_user is not None and getattr(
            current_user, "role", "") == "admin"
        if not is_admin:
            try:
                with open(case_file, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                owner = stored.get("metadata", {}).get("userId")
                current_uid = str(getattr(current_user, "id",
                                  "")) if current_user else ""
                if owner and owner != current_uid:
                    return JSONResponse({"success": False, "error": "Forbidden: not your case"}, status_code=403)
            except Exception:
                pass  # If we can't read, allow deletion to proceed
        case_file.unlink()
        return JSONResponse({"success": True, "message": f"Case {clean_id} deleted"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── UPI Case Management ───────────────────────────────────────────────────────

@app.get("/api/upi-cases")
def list_upi_cases(current_user=Depends(get_current_user)):
    try:
        cases_dir = UPI_CASES_DIR
        if not cases_dir.exists():
            return JSONResponse({"success": True, "cases": []})
        is_admin = current_user is not None and getattr(
            current_user, 'role', '') == 'admin'
        current_user_id = getattr(
            current_user, 'id', None) if current_user is not None else None
        cases = []
        for case_file in cases_dir.glob("*.json"):
            try:
                with open(case_file, "r", encoding="utf-8") as f:
                    case_data = json.load(f)
                metadata = case_data.get("metadata", {})
                if not is_admin and current_user_id is not None:
                    case_owner = metadata.get("user_id")
                    if case_owner is not None and case_owner != current_user_id:
                        continue
                upi_analysis = case_data.get("upiAnalysis", {})
                graph_data = case_data.get("graphData", case_data.get("graph", {}))
                total_accounts = (
                    upi_analysis.get("totalAccounts")
                    or upi_analysis.get("accounts")
                    or len(graph_data.get("nodes", []))
                    or metadata.get("totalAccounts", 0)
                )
                total_transactions = (
                    upi_analysis.get("totalTransactions")
                    or upi_analysis.get("transactions")
                    or len(graph_data.get("edges", []))
                    or metadata.get("totalTransactions", 0)
                )
                cases.append({
                    "fileName": case_file.name,
                    "caseId": case_data.get("caseId", case_file.stem),
                    "timestamp": case_data.get("timestamp", 0),
                    "riskScore": metadata.get("riskScore", 0),
                    "riskBand": metadata.get("riskBand", "unknown"),
                    "fileSize": case_file.stat().st_size,
                    "totalAccounts": total_accounts,
                    "totalTransactions": total_transactions,
                    "highRiskCount": metadata.get("highRiskCount", upi_analysis.get("highRiskAccounts", 0)),
                    "createdBy": metadata.get("created_by", metadata.get("createdBy", "unknown")),
                    "createdAt": metadata.get("created_at", case_data.get("timestamp", 0)),
                    "metadata": metadata,
                })
            except Exception as e:
                logger.warning(
                    f"Failed to read UPI case file {case_file}: {e}")
        cases.sort(key=lambda x: x["timestamp"], reverse=True)
        return JSONResponse({"success": True, "cases": cases[:50]})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/upi-cases/{case_id}")
def get_upi_case(case_id: str, current_user=Depends(get_current_user)):
    try:
        # Strict ID validation — prevent path traversal
        if not _input_re.match(r'^[A-Za-z0-9_\-]+$', case_id.replace(".json", "")):
            return JSONResponse({"success": False, "error": "Invalid case ID"}, status_code=400)
        clean_id = case_id.replace(".json", "")
        cases_root = UPI_CASES_DIR.resolve()
        case_file = (cases_root / f"{clean_id}.json").resolve()
        if not str(case_file).startswith(str(cases_root)):
            return JSONResponse({"success": False, "error": "Invalid path"}, status_code=400)
        if not case_file.exists():
            return JSONResponse({"success": False, "error": f"Case {clean_id} not found"}, status_code=404)
        with open(case_file, "r", encoding="utf-8") as f:
            case_data = json.load(f)
        return JSONResponse(case_data)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/upi-cases")
async def save_upi_case(request: Request, current_user=Depends(get_current_user)):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    try:
        user_role = getattr(current_user, 'role',
                            '') if current_user is not None else ''
        if user_role == 'viewer':
            return JSONResponse({"success": False, "error": "Viewers cannot save analyses"}, status_code=403)

        if "case_data" in data:
            case_data = data["case_data"]
        elif "data" in data:
            case_data = data["data"]
        else:
            case_data = data

        metadata = case_data.get("metadata", {})
        case_id = case_data.get("caseId") or metadata.get("caseId")
        if not case_id:
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            case_id = f"UPI-CASE-{timestamp}"
            case_data["caseId"] = case_id
            metadata["caseId"] = case_id

        if current_user is not None:
            metadata["user_id"] = current_user.id
            metadata["created_by"] = current_user.username

        cases_dir = UPI_CASES_DIR
        cases_dir.mkdir(parents=True, exist_ok=True)
        clean_id = case_id.replace(".json", "")
        file_path = cases_dir / f"{clean_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(case_data, f, indent=2, ensure_ascii=False, default=str)
        logger.info(
            f"UPI case saved: {clean_id} by user={getattr(current_user, 'username', 'unknown')}")
        return JSONResponse({"success": True, "caseId": clean_id, "filename": f"{clean_id}.json"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/upi-cases/save")
async def save_upi_case_alt(request: Request, current_user=Depends(get_current_user)):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    try:
        user_role = getattr(current_user, 'role',
                            '') if current_user is not None else ''
        if user_role == 'viewer':
            return JSONResponse({"success": False, "error": "Viewers cannot save analyses"}, status_code=403)
        if "case_data" in data:
            case_data = data["case_data"]
        elif "data" in data:
            case_data = data["data"]
        else:
            case_data = data
        metadata = case_data.get("metadata", {})
        case_id = case_data.get("caseId") or metadata.get("caseId")
        if not case_id:
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            case_id = f"UPI-CASE-{timestamp}"
            case_data["caseId"] = case_id
            metadata["caseId"] = case_id
        if current_user is not None:
            metadata["user_id"] = current_user.id
            metadata["created_by"] = current_user.username
        cases_dir = UPI_CASES_DIR
        cases_dir.mkdir(parents=True, exist_ok=True)
        clean_id = case_id.replace(".json", "")
        file_path = cases_dir / f"{clean_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(case_data, f, indent=2, ensure_ascii=False, default=str)
        logger.info(
            f"UPI case saved: {clean_id} by user={getattr(current_user, 'username', 'unknown')}")
        return JSONResponse({"success": True, "caseId": clean_id, "filename": f"{clean_id}.json"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.delete("/api/upi-cases/{case_id}")
def delete_upi_case(case_id: str, current_user=Depends(get_current_user)):
    try:
        clean_id = case_id.replace(".json", "")
        case_file = UPI_CASES_DIR / f"{clean_id}.json"
        if not case_file.exists():
            return JSONResponse({"success": False, "error": "Case not found"}, status_code=404)
        is_admin = current_user is not None and getattr(
            current_user, 'role', '') == 'admin'
        if not is_admin and current_user is not None:
            with open(case_file, "r", encoding="utf-8") as f:
                import json as _json
                case_data = _json.load(f)
            owner_id = case_data.get("metadata", {}).get("user_id")
            if owner_id is not None and owner_id != current_user.id:
                return JSONResponse({"success": False, "error": "Forbidden"}, status_code=403)
        case_file.unlink()
        return JSONResponse({"success": True, "message": f"Case {clean_id} deleted"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Threat intelligence ───────────────────────────────────────────────────────

@app.post("/api/threat-intelligence/analyze")
@app.post("/api/threat-intel/analyze")
async def threat_intel_analyze(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    address = data.get("address", "").strip()
    if not address:
        return JSONResponse({"success": False, "error": "Address is required"}, status_code=400)
    cb = get_chainbreak()
    if not cb:
        return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
    try:
        result = cb.get_threat_intelligence(address)
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        logger.error(f"Threat intel error: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/threat-intelligence/address/{address}")
@app.get("/api/threat-intel/address/{address}")
def threat_intel_get(address: str):
    cb = get_chainbreak()
    if not cb:
        return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
    try:
        result = cb.get_threat_intelligence(address)
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/threat-intelligence/status")
@app.get("/api/threat-intel/status")
def threat_intel_status():
    try:
        cb = get_chainbreak()
        if cb:
            status = cb.get_threat_intel_status()
            return JSONResponse({"success": True, "data": status})
        return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/threat-intelligence/batch")
@app.post("/api/threat-intel/batch")
async def threat_intel_batch(request: Request):
    try:
        data = await request.json()
        addresses = data.get("addresses", [])
        if not addresses or not isinstance(addresses, list):
            return JSONResponse({"success": False, "error": "addresses list required"}, status_code=400)
        if len(addresses) > 50:
            return JSONResponse({"success": False, "error": "Max 50 addresses per batch"}, status_code=400)
        cb = get_chainbreak()
        if not cb:
            return JSONResponse({"success": False, "error": "ChainBreak not initialized"}, status_code=500)
        results = {}
        for addr in addresses:
            try:
                results[addr] = cb.get_threat_intelligence(addr)
            except Exception as e:
                results[addr] = {"error": str(e)}
        return JSONResponse({"success": True, "data": results})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Gateway stats ─────────────────────────────────────────────────────────────

@app.get("/api/gateway/stats")
def gateway_stats():
    try:
        if HAS_AUTH:
            stats = api_gateway.get_stats()
        else:
            stats = {"message": "Gateway not initialized"}
        return JSONResponse({"success": True, "stats": stats})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Logs ──────────────────────────────────────────────────────────────────────

@app.get("/api/logs")
def get_logs(lines: int = Query(default=100), level: str = Query(default=None), current_user=Depends(get_current_user)):
    try:
        if HAS_AUTH:
            logs = get_recent_logs(lines=min(lines, 500), level=level)
        else:
            log_file = Path("logs/chainbreak.log")
            if log_file.exists():
                with open(log_file, "r") as f:
                    logs = f.readlines()[-lines:]
            else:
                logs = ["No logs available"]
        return JSONResponse({"success": True, "logs": logs, "count": len(logs)})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/logs/sync")
async def sync_frontend_logs(request: Request, current_user=Depends(get_current_user)):
    try:
        data = await request.json()
        if not data or "logs" not in data:
            return JSONResponse({"success": False, "error": "No logs provided"}, status_code=400)
        logs = data.get("logs", [])
        if len(logs) > 100:
            return JSONResponse({"success": False, "error": "Too many log entries in batch (max 100)"}, status_code=400)
        _fe_logger = logging.getLogger("frontend")
        for log_entry in logs:
            action = log_entry.get("action", "frontend.unknown")
            message = log_entry.get("message", "")
            level = log_entry.get("level", "INFO").upper()
            log_line = f"[FE] [{action}] {message}"
            log_level = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARN": logging.WARNING,
                         "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL}.get(level, logging.INFO)
            _fe_logger.log(log_level, log_line)
        logger.info(f"Synced {len(logs)} frontend logs to backend")
        return JSONResponse({"success": True, "synced": len(logs), "message": f"Successfully synced {len(logs)} log entries"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Audit / Frontend Event Logging ────────────────────────────────────────────

@app.post("/api/audit/event")
async def log_audit_event(request: Request, current_user=Depends(get_current_user)):
    """Receive frontend UI interaction events and write them to the audit log."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)

    # Basic sanitization
    action = str(data.get("action", "unknown"))[:100]
    component = str(data.get("component", "frontend"))[:60]
    message = str(data.get("message", ""))[:500]
    level = str(data.get("level", "INFO")).upper()
    if level not in ("DEBUG", "INFO", "WARN", "WARNING", "ERROR"):
        level = "INFO"
    extra = data.get("extra", {})
    if not isinstance(extra, dict):
        extra = {}

    # Use authenticated user identity rather than trusting the request body
    username = getattr(current_user, "username", "authenticated") if current_user else "anonymous"
    ip = _get_client_ip(request)
    ua = request.headers.get("User-Agent", "")[:200]

    audit_logger = logging.getLogger("audit.frontend")
    log_fn = getattr(audit_logger, level.lower()
                     if level != "WARN" else "warning")
    log_fn(
        "FRONTEND user=%s ip=%s component=%s action=%s message=%s ua=%s extra=%s",
        username, ip, component, action, message, ua[:80], str(extra)[:200]
    )
    return JSONResponse({"success": True})


# ── Temporal analysis ─────────────────────────────────────────────────────────

@app.post("/api/temporal/analyze")
async def analyze_temporal(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "No data provided"}, status_code=400)
    if not data:
        return JSONResponse({"success": False, "error": "No data provided"}, status_code=400)
    snapshot_t1 = data.get("snapshot_t1")
    snapshot_t2 = data.get("snapshot_t2")
    algorithm = data.get("algorithm", "louvain")
    resolution = float(data.get("resolution", 1.0))
    save_report = data.get("save_report", True)
    if not snapshot_t1 or not snapshot_t2:
        return JSONResponse({"success": False, "error": "Both snapshots are required"}, status_code=400)
    try:
        from .temporal_analysis.pipeline import TemporalAnalysisPipeline
        from datetime import datetime as dt
        pipeline = TemporalAnalysisPipeline(
            algorithm=algorithm, resolution=resolution, seed=42)
        ts1 = dt.fromisoformat(snapshot_t1.get(
            "timestamp", dt.now().isoformat()).replace("Z", "+00:00"))
        ts2 = dt.fromisoformat(snapshot_t2.get(
            "timestamp", dt.now().isoformat()).replace("Z", "+00:00"))
        logger.info(
            f"Running temporal analysis: {algorithm}, T1={len(snapshot_t1.get('nodes', []))} nodes")
        result = pipeline.run_from_data(
            data_t1={"nodes": snapshot_t1.get(
                "nodes", []), "edges": snapshot_t1.get("edges", [])},
            data_t2={"nodes": snapshot_t2.get(
                "nodes", []), "edges": snapshot_t2.get("edges", [])},
            timestamp_t1=ts1, timestamp_t2=ts2, metadata={
                "algorithm": algorithm, "resolution": resolution}
        )
        response_data = {
            "algorithm": algorithm, "resolution": resolution, "timestamp": datetime.now().isoformat(),
            "summary": {"nmi_score": result.nmi_score, "communities_t1": result.community_t1.num_communities, "communities_t2": result.community_t2.num_communities, "delta_communities": result.community_t2.num_communities - result.community_t1.num_communities, "modularity_t1": result.community_t1.modularity, "modularity_t2": result.community_t2.modularity, "is_stable": result.is_stable, "nodes_unchanged_pct": result.comparison.percentage_unchanged},
            "community_t1": {"partition": result.community_t1.partition, "num_communities": result.community_t1.num_communities, "modularity": result.community_t1.modularity},
            "community_t2": {"partition": result.community_t2.partition, "num_communities": result.community_t2.num_communities, "modularity": result.community_t2.modularity},
            "transitions": {"splits": [{"source": s.source_community, "targets": list(s.target_communities), "ratio": s.split_ratio} for s in result.transitions.splits], "merges": [{"sources": list(m.source_communities), "target": m.target_community, "ratio": m.merge_ratio} for m in result.transitions.merges], "emergences": [{"community_id": e.community_id, "size": e.size} for e in result.transitions.emergences], "dissolutions": [{"community_id": d.community_id, "size": d.original_size} for d in result.transitions.dissolutions], "stable": list(result.transitions.stable_communities)}
        }
        if save_report:
            report_filename = f"temporal_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{algorithm}.json"
            report_path = TEMPORAL_REPORTS_DIR / report_filename
            with open(report_path, "w") as f:
                json.dump(response_data, f, indent=2, default=str)
            response_data["report_saved"] = str(report_path)
        return JSONResponse({"success": True, "data": response_data})
    except Exception as e:
        logger.error(
            f"Temporal analysis failed: {e}\n{traceback.format_exc()}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/temporal/demo")
def temporal_demo():
    try:
        from .temporal_analysis.pipeline import TemporalAnalysisPipeline, create_mock_snapshots
        from datetime import datetime as dt, timedelta
        data_t1, data_t2 = create_mock_snapshots()
        pipeline = TemporalAnalysisPipeline(
            algorithm="louvain", resolution=1.0, seed=42)
        result = pipeline.run_from_data(data_t1=data_t1, data_t2=data_t2, timestamp_t1=dt.now(
        ) - timedelta(days=7), timestamp_t2=dt.now(), metadata={"demo": True})
        return JSONResponse({"success": True, "demo": True, "data": {"summary": {"nmi_score": result.nmi_score, "communities_t1": result.community_t1.num_communities, "communities_t2": result.community_t2.num_communities, "is_stable": result.is_stable}, "num_transitions": result.num_transitions}})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/temporal/status")
def temporal_status():
    try:
        from .temporal_analysis.pipeline import TemporalAnalysisPipeline
        available = True
        features = ["louvain", "leiden", "label_propagation",
                    "nmi_comparison", "transition_detection"]
    except ImportError:
        available = False
        features = []
    return JSONResponse({"success": True, "data": {"available": available, "features": features, "reports_directory": str(TEMPORAL_REPORTS_DIR)}})


@app.get("/api/temporal/reports")
def list_temporal_reports():
    try:
        reports = []
        for report_file in TEMPORAL_REPORTS_DIR.glob("*.json"):
            reports.append({"filename": report_file.name, "path": str(report_file), "size": report_file.stat(
            ).st_size, "created": datetime.fromtimestamp(report_file.stat().st_ctime).isoformat()})
        reports.sort(key=lambda x: x["created"], reverse=True)
        return JSONResponse({"success": True, "reports": reports})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/temporal/reports/{filename}")
def get_temporal_report(filename: str, current_user=Depends(get_current_user)):
    try:
        reports_root = TEMPORAL_REPORTS_DIR.resolve()
        report_path = (reports_root / filename).resolve()
        # Prevent path traversal outside the reports directory
        if not str(report_path).startswith(str(reports_root)):
            return JSONResponse({"success": False, "error": "Report not found"}, status_code=404)
        if not report_path.exists():
            return JSONResponse({"success": False, "error": "Report not found"}, status_code=404)
        with open(report_path, "r") as f:
            report_data = json.load(f)
        return JSONResponse({"success": True, "data": report_data})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── UPI Analysis helpers ──────────────────────────────────────────────────────

try:
    from .services.upi.upi_analysis import parse_csv_content, analyze_upi_transactions, DEFAULT_UPI_SETTINGS
    from .services.upi.upi_community_detection import detect_upi_communities, get_suspicious_communities
    from .services.upi.upi_community_comparison import run_comprehensive_comparison, generate_validation_batch
    from .services.upi.upi_community_cache import community_cache
    from .services.upi.upi_neo4j_community import get_neo4j_graph
    HAS_UPI_ANALYSIS = True
except ImportError as e:
    logger.warning(f"UPI analysis module not loaded: {e}")
    HAS_UPI_ANALYSIS = False
    community_cache = None

try:
    from .services.upi.upi_neo4j_community import (
        load_upi_csv_to_neo4j,
        run_community_detection_neo4j,
        run_fingerprinting_neo4j,
        get_mule_detection_results,
        get_neo4j_graph,
        get_neo4j_graph_stats,
    )
    HAS_NEO4J_COMMUNITY = True
except ImportError as e:
    logger.warning(f"upi_neo4j_community not available: {e}")
    HAS_NEO4J_COMMUNITY = False


def _translate_upi_settings(frontend_settings):
    if not frontend_settings or not isinstance(frontend_settings, dict):
        return None
    rules = frontend_settings.get("rules", {})
    if "fanInThreshold" in rules:
        return frontend_settings
    try:
        backend_rules = {
            "fanInThreshold": rules.get("fanIn", {}).get("unique", 5) if isinstance(rules.get("fanIn"), dict) else rules.get("fanInThreshold", 5),
            "fanOutThreshold": rules.get("fanOut", {}).get("unique", 5) if isinstance(rules.get("fanOut"), dict) else rules.get("fanOutThreshold", 5),
            "rapidWindowMs": rules.get("rapid", {}).get("windowMs", 300000) if isinstance(rules.get("rapid"), dict) else rules.get("rapidWindowMs", 300000),
            "rapidMinTx": rules.get("rapid", {}).get("minTx", 3) if isinstance(rules.get("rapid"), dict) else rules.get("rapidMinTx", 3),
            "circularMaxDepth": rules.get("circular", {}).get("maxDepth", 3) if isinstance(rules.get("circular"), dict) else rules.get("circularMaxDepth", 3),
            "structuringThreshold": rules.get("structuring", {}).get("threshold", 10000) if isinstance(rules.get("structuring"), dict) else rules.get("structuringThreshold", 10000),
            "structuringMarginPct": rules.get("structuring", {}).get("marginPct", 10) if isinstance(rules.get("structuring"), dict) else rules.get("structuringMarginPct", 10),
            "dormantDays": rules.get("dormant", {}).get("days", 30) if isinstance(rules.get("dormant"), dict) else rules.get("dormantDays", 30),
            "spikeMultiplier": rules.get("dormant", {}).get("spikeMultiplier", 5) if isinstance(rules.get("dormant"), dict) else rules.get("spikeMultiplier", 5),
            "passThroughRatioPct": rules.get("passthrough", {}).get("ratioPct", 90) if isinstance(rules.get("passthrough"), dict) else rules.get("passThroughRatioPct", 90),
        }
        translated = {
            "rules": backend_rules,
            "weights": frontend_settings.get("weights", DEFAULT_UPI_SETTINGS["weights"] if HAS_UPI_ANALYSIS else {}),
            "limits": frontend_settings.get("limits", DEFAULT_UPI_SETTINGS["limits"] if HAS_UPI_ANALYSIS else {}),
        }
        return translated
    except Exception as e:
        logger.warning(f"UPI settings translation failed: {e}")
        return None


# ── UPI endpoints ─────────────────────────────────────────────────────────────

@app.post("/api/upi/analyze")
async def analyze_upi_transactions_endpoint(request: Request, current_user=Depends(get_current_user)):
    if not HAS_UPI_ANALYSIS:
        return JSONResponse({"success": False, "error": "UPI analysis module not available"}, status_code=500)

    import time as _time
    _start = _time.time()
    try:
        content_type = request.headers.get("content-type", "")
        csv_content = None
        settings = None

        if "multipart/form-data" in content_type:
            form = await request.form()
            csv_file = form.get("file") or form.get("csv_file")
            if not csv_file:
                return JSONResponse({"success": False, "error": "No CSV file provided. Upload a .csv file."}, status_code=400)
            _raw = await csv_file.read(_CSV_MAX_BYTES + 1)
            if len(_raw) > _CSV_MAX_BYTES:
                return JSONResponse({"success": False, "error": "CSV file too large (max 50 MB)"}, status_code=413)
            try:
                csv_content = _raw.decode("utf-8")
            except UnicodeDecodeError:
                return JSONResponse({"success": False, "error": "CSV file must be UTF-8 encoded"}, status_code=400)
            logger.info(
                f"UPI analyze: Received file '{csv_file.filename}' ({len(csv_content)} bytes)")
            settings_json = form.get("settings")
            if settings_json:
                try:
                    settings = json.loads(settings_json)
                except json.JSONDecodeError:
                    settings = None
        else:
            data = await request.json()
            if not data:
                return JSONResponse({"success": False, "error": "Invalid request body"}, status_code=400)
            csv_content = data.get("csv_content")
            settings = data.get("settings")

        if not csv_content or not csv_content.strip():
            return JSONResponse({"success": False, "error": "Empty CSV content"}, status_code=400)

        backend_settings = _translate_upi_settings(
            settings) if settings else None
        logger.info("UPI: Starting transaction analysis...")
        transactions = parse_csv_content(csv_content)
        if len(transactions) == 0:
            return JSONResponse({"success": False, "error": "No valid transactions found in CSV"}, status_code=400)

        logger.info(
            f"UPI: Parsed {len(transactions)} valid transactions, running analysis for user={getattr(current_user, 'username', 'unknown')}...")
        result = analyze_upi_transactions(transactions, backend_settings)
        _elapsed = round((_time.time() - _start) * 1000, 2)
        logger.info(
            f"UPI analysis complete in {_elapsed}ms: {result['metadata']['totalNodes']} nodes, {result['metadata']['totalEdges']} edges user={getattr(current_user, 'username', 'unknown')}")

        persistence_status = {"neo4j_available": False,
                              "data_persisted": False, "error": None}
        chainbreak = get_chainbreak()
        if chainbreak and chainbreak.is_neo4j_available():
            try:
                db_mode = getattr(chainbreak, "backend_mode", "unknown")
                logger.info(
                    f"UPI: Neo4j backend available (mode: {db_mode}), attempting data persistence...")
                persistence_status["neo4j_available"] = True
                ingestion_result = chainbreak.data_ingestor.ingest_upi_transactions(
                    transactions, db_mode=db_mode)
                persistence_status["data_persisted"] = ingestion_result.get(
                    "success", False)
                persistence_status["ingestion_id"] = ingestion_result.get(
                    "ingestion_id")
                persistence_status["ingestion_summary"] = {
                    "total_rows_read": ingestion_result.get("total_rows_read", 0), "valid_rows_processed": ingestion_result.get("valid_rows_processed", 0),
                    "rows_skipped": ingestion_result.get("rows_skipped", 0), "nodes_created": ingestion_result.get("nodes_created", 0),
                    "nodes_matched": ingestion_result.get("nodes_matched", 0), "relationships_created": ingestion_result.get("relationships_created", 0),
                    "batches_processed": ingestion_result.get("batches_processed", 0), "batches_failed": ingestion_result.get("batches_failed", 0),
                    "execution_time_ms": ingestion_result.get("execution_time_ms", 0),
                }
                if ingestion_result.get("error"):
                    persistence_status["error"] = ingestion_result["error"]
                else:
                    account_risks = {}
                    for node in result.get("graph", {}).get("nodes", []):
                        upi_id = node.get("upiId") or node.get("id")
                        if upi_id:
                            account_risks[upi_id] = {"riskScore": node.get("riskScore", 0), "riskBand": node.get("riskBand", "minimal"), "reasonCodes": node.get("reasonCodes", []), "totalInAmount": node.get("totalInAmount", 0), "totalOutAmount": node.get(
                                "totalOutAmount", 0), "inTxCount": node.get("inTxCount", 0), "outTxCount": node.get("outTxCount", 0), "inCounterparties": node.get("inCounterparties", 0), "outCounterparties": node.get("outCounterparties", 0)}
                    if account_risks:
                        chainbreak.data_ingestor.update_upi_account_risk_scores(
                            account_risks)
                    logger.info("UPI: Neo4j persistence complete")
            except Exception as persist_error:
                logger.error(
                    f"UPI: Error during Neo4j persistence: {persist_error}")
                persistence_status["error"] = str(persist_error)
                persistence_status["data_persisted"] = False
        else:
            logger.info(
                "UPI: Neo4j backend not available, skipping data persistence")

        result["persistence"] = persistence_status

        if community_cache is not None and result.get("graph"):
            def _precompute(graph_data):
                for alg in ["louvain", "leiden", "label_propagation"]:
                    try:
                        if community_cache.get(graph_data, alg, 1.0) is None:
                            res = detect_upi_communities(
                                upi_analysis_result={"graph": graph_data}, algorithm=alg, resolution=1.0)
                            community_cache.put(graph_data, alg, 1.0, res)
                    except Exception:
                        pass
            threading.Thread(target=_precompute, args=(
                result["graph"],), daemon=True).start()

        return JSONResponse({"success": True, "data": result})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        logger.error(f"UPI analysis failed: {e}\n{traceback.format_exc()}")
        return JSONResponse({"success": False, "error": f"Internal analysis error: {str(e)}"}, status_code=500)


@app.get("/api/upi/settings")
def get_upi_default_settings():
    if not HAS_UPI_ANALYSIS:
        return JSONResponse({"success": False, "error": "UPI analysis module not available"}, status_code=500)
    return JSONResponse({"success": True, "data": DEFAULT_UPI_SETTINGS})


@app.get("/api/upi/health")
def upi_health_check():
    neo4j_connected = False
    try:
        cb = get_chainbreak()
        if cb and cb.is_neo4j_available():
            neo4j_connected = True
    except Exception:
        pass
    return JSONResponse({"success": True, "data": {"available": HAS_UPI_ANALYSIS, "module": "upi_analysis", "neo4j_connected": neo4j_connected, "neo4j_community_available": HAS_NEO4J_COMMUNITY, "endpoints": ["/api/upi/analyze", "/api/upi/settings", "/api/upi/health", "/api/upi/communities/detect", "/api/upi/communities/suspicious", "/api/upi/communities/compare", "/api/upi/communities/validation", "/api/upi/neo4j/graph", "/api/upi/neo4j/community-detect"], "default_settings": DEFAULT_UPI_SETTINGS if HAS_UPI_ANALYSIS else None}})


@app.post("/api/upi/communities/detect")
async def detect_upi_communities_endpoint(request: Request, current_user=Depends(get_current_user)):
    if not HAS_UPI_ANALYSIS:
        return JSONResponse({"success": False, "error": "UPI analysis module not available"}, status_code=503)
    try:
        data = await request.json()
        if not data:
            return JSONResponse({"success": False, "error": "Invalid JSON data"}, status_code=400)
        graph_data = data.get("graph_data")
        if not graph_data:
            return JSONResponse({"success": False, "error": "Graph data is required"}, status_code=400)
        if "nodes" not in graph_data or "edges" not in graph_data:
            return JSONResponse({"success": False, "error": "Graph data must contain 'nodes' and 'edges'"}, status_code=400)
        if len(graph_data["nodes"]) == 0:
            return JSONResponse({"success": False, "error": "Graph must have at least one node"}, status_code=400)
        if len(graph_data["edges"]) == 0:
            return JSONResponse({"success": False, "error": "Graph must have at least one edge"}, status_code=400)

        algorithm = data.get("algorithm", "louvain")
        resolution = data.get("resolution", 1.0)
        min_risk_score = data.get("min_risk_score", 60.0)
        export_results = data.get("export_results", False)
        valid_algorithms = ["louvain", "leiden",
                            "label_propagation", "infomap"]
        if algorithm not in valid_algorithms:
            return JSONResponse({"success": False, "error": f"Invalid algorithm. Choose from: {', '.join(valid_algorithms)}"}, status_code=400)
        if not isinstance(resolution, (int, float)) or resolution <= 0:
            return JSONResponse({"success": False, "error": "Resolution must be a positive number"}, status_code=400)

        cached = community_cache.get(
            graph_data, algorithm, resolution) if community_cache else None
        if cached is not None:
            community_results = cached
        else:
            community_results = detect_upi_communities(upi_analysis_result={
                                                       "graph": graph_data}, algorithm=algorithm, resolution=resolution)
            if community_cache:
                community_cache.put(graph_data, algorithm,
                                    resolution, community_results)

        suspicious_communities = get_suspicious_communities(
            community_results, min_risk_score=min_risk_score, min_members=3)
        community_results["suspicious_communities"] = suspicious_communities

        if export_results:
            try:
                export_dir = BASE_DIR / "data" / "upi_communities"
                export_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = export_dir / \
                    f"upi_communities_{algorithm}_{timestamp}.json"
                from .services.upi.upi_community_detection import export_community_analysis_to_json
                export_community_analysis_to_json(
                    community_results, str(output_path))
                community_results["export_file"] = output_path.name
            except Exception as e:
                logger.warning(f"Failed to export community results: {e}")

        return JSONResponse({"success": True, "data": community_results})
    except Exception as e:
        logger.error(
            f"UPI community detection error: {e}\n{traceback.format_exc()}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/upi/communities/suspicious")
async def get_suspicious_upi_communities_endpoint(request: Request, current_user=Depends(get_current_user)):
    if not HAS_UPI_ANALYSIS:
        return JSONResponse({"success": False, "error": "UPI analysis module not available"}, status_code=503)
    try:
        data = await request.json()
        if not data:
            return JSONResponse({"success": False, "error": "Invalid JSON data"}, status_code=400)
        community_results = data.get("community_results")
        if not community_results:
            return JSONResponse({"success": False, "error": "Community results are required"}, status_code=400)
        min_risk_score = data.get("min_risk_score", 60.0)
        min_members = data.get("min_members", 3)
        suspicious_communities = get_suspicious_communities(
            community_results, min_risk_score=min_risk_score, min_members=min_members)
        high_risk_count = len(
            [c for c in suspicious_communities if c.get("riskLevel") == "high"])
        critical_risk_count = len(
            [c for c in suspicious_communities if c.get("riskLevel") == "critical"])
        result = {"suspicious_communities": suspicious_communities, "total_suspicious": len(
            suspicious_communities), "high_risk_communities": high_risk_count, "critical_risk_communities": critical_risk_count, "criteria": {"min_risk_score": min_risk_score, "min_members": min_members}}
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/upi/communities/compare")
async def compare_upi_communities_endpoint(request: Request, current_user=Depends(get_current_user)):
    if not HAS_UPI_ANALYSIS:
        return JSONResponse({"success": False, "error": "UPI analysis module not available"}, status_code=503)
    try:
        data = await request.json()
        if not data:
            return JSONResponse({"success": False, "error": "Invalid JSON data"}, status_code=400)
        graph_data = data.get("graph_data")
        if not graph_data:
            return JSONResponse({"success": False, "error": "Graph data is required"}, status_code=400)
        if "nodes" not in graph_data or "edges" not in graph_data:
            return JSONResponse({"success": False, "error": "Graph data must contain 'nodes' and 'edges'"}, status_code=400)
        if not graph_data["nodes"] or not graph_data["edges"]:
            return JSONResponse({"success": False, "error": "Graph must have nodes and edges"}, status_code=400)

        algorithms = data.get(
            "algorithms", ["louvain", "leiden", "label_propagation", "infomap"])
        if data.get("run_all_algorithms", True):
            algorithms = ["louvain", "leiden", "label_propagation", "infomap"]
        valid_algorithms = ["louvain", "leiden",
                            "label_propagation", "infomap"]
        algorithms = [a for a in algorithms if a in valid_algorithms]
        if not algorithms:
            return JSONResponse({"success": False, "error": f"No valid algorithms. Choose from: {', '.join(valid_algorithms)}"}, status_code=400)

        community_results = {}

        def _run_algorithm(alg):
            cached = community_cache.get(
                graph_data, alg, 1.0) if community_cache else None
            if cached is not None:
                return alg, cached
            result = detect_upi_communities(
                upi_analysis_result={"graph": graph_data}, algorithm=alg, resolution=1.0)
            if community_cache:
                community_cache.put(graph_data, alg, 1.0, result)
            return alg, result

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(
                _run_algorithm, alg): alg for alg in algorithms}
            for future in as_completed(futures):
                try:
                    alg_name, result = future.result()
                    community_results[alg_name] = result
                except Exception as e:
                    logger.warning(f"Failed to run {futures[future]}: {e}")

        if not community_results:
            return JSONResponse({"success": False, "error": "All algorithms failed"}, status_code=500)

        comparison_results = run_comprehensive_comparison(
            graph_data, community_results)

        if data.get("generate_validation_batch", False):
            top_n = data.get("top_n_validation", 50)
            validation_data = generate_validation_batch(
                comparison_results, top_n)
            comparison_results["validation_batch"] = validation_data

        if data.get("export_results", False):
            try:
                export_dir = BASE_DIR / "data" / "upi_comparisons"
                export_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = export_dir / \
                    f"upi_community_comparison_{timestamp}.json"
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(comparison_results, f, indent=2,
                              ensure_ascii=False, default=str)
                comparison_results["export_file"] = output_path.name
            except Exception as e:
                logger.warning(f"Failed to export comparison results: {e}")

        safe_results = safe_json_response(comparison_results)
        return JSONResponse({"success": True, "data": safe_results})
    except Exception as e:
        logger.error(
            f"Community comparison error: {e}\n{traceback.format_exc()}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/upi/communities/validation")
async def get_validation_batch_endpoint(request: Request, current_user=Depends(get_current_user)):
    if not HAS_UPI_ANALYSIS:
        return JSONResponse({"success": False, "error": "UPI analysis module not available"}, status_code=503)
    try:
        data = await request.json()
        if not data:
            return JSONResponse({"success": False, "error": "Invalid JSON data"}, status_code=400)
        comparison_results = data.get("comparison_results")
        if not comparison_results:
            return JSONResponse({"success": False, "error": "Comparison results are required"}, status_code=400)
        top_n = data.get("top_n", 50)
        risk_threshold = data.get("risk_threshold", 70.0)
        validation_data = generate_validation_batch(comparison_results, top_n)
        if risk_threshold > 0:
            validation_data["validation_batch"]["accounts"] = [
                a for a in validation_data["validation_batch"]["accounts"] if a.get("weighted_score", 0) >= risk_threshold]
            validation_data["validation_batch"]["total_accounts"] = len(
                validation_data["validation_batch"]["accounts"])
        return JSONResponse({"success": True, "data": validation_data})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── UPI Neo4j endpoints ───────────────────────────────────────────────────────

@app.post("/api/upi/neo4j/load")
async def upi_neo4j_load(request: Request, current_user=Depends(get_current_user)):
    if not HAS_NEO4J_COMMUNITY:
        return JSONResponse({"success": False, "error": "Neo4j community module not available"}, status_code=500)
    driver = _get_neo4j_driver()
    if not driver:
        return JSONResponse({"success": False, "error": "Neo4j not connected. Check credentials/connection."}, status_code=503)
    try:
        import tempfile as _tempfile
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            form = await request.form()
            csv_file = form.get("file") or form.get("csv_file")
            if not csv_file:
                return JSONResponse({"success": False, "error": "No file field in multipart upload"}, status_code=400)
            tmp = _tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
            contents = await csv_file.read(_CSV_MAX_BYTES + 1)
            if len(contents) > _CSV_MAX_BYTES:
                tmp.close()
                return JSONResponse({"success": False, "error": "CSV file too large (max 50 MB)"}, status_code=413)
            try:
                contents.decode("utf-8")
            except UnicodeDecodeError:
                tmp.close()
                return JSONResponse({"success": False, "error": "CSV file must be UTF-8 encoded"}, status_code=400)
            tmp.write(contents)
            tmp.close()
            csv_path = tmp.name
            batch_size = int(form.get("batch_size", 500))
        else:
            data = await request.json()
            default_csv = str(Path(__file__).resolve(
            ).parent.parent / "upi_mule_dataset.csv")
            csv_path = data.get("csv_path", default_csv)
            batch_size = int(data.get("batch_size", 500))

        job_id = UpiIngestionJobStore.create_job(csv_path)
        t = threading.Thread(target=_run_upi_ingestion, args=(
            job_id, csv_path, driver, batch_size), daemon=True)
        t.start()

        resp = JSONResponse({"success": True, "job_id": job_id, "message": "Ingestion started in background. Poll status endpoint for progress.",
                            "status_url": f"/api/upi/neo4j/load/status/{job_id}"}, status_code=202)
        resp.headers["Retry-After"] = "5"
        return resp
    except Exception as e:
        logger.error("UPI Neo4j load error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/upi/neo4j/load/status/{job_id}")
def upi_neo4j_load_status(job_id: str):
    job = UpiIngestionJobStore.get_job(job_id)
    if not job:
        return JSONResponse({"success": False, "error": "Job not found"}, status_code=404)
    return JSONResponse({"success": True, "data": job})


@app.post("/api/upi/neo4j/community-detect")
async def upi_neo4j_community_detect(request: Request, current_user=Depends(get_current_user)):
    if not HAS_NEO4J_COMMUNITY:
        return JSONResponse({"success": False, "error": "Neo4j community module not available"}, status_code=500)
    driver = _get_neo4j_driver()
    if not driver:
        return JSONResponse({"success": False, "error": "Neo4j not connected. Check credentials/connection."}, status_code=503)
    try:
        data = (await request.json()) or {}
        resolution = float(data.get("resolution", 1.0))
        run_fp = data.get("run_fingerprinting", True)
        _ALGO_MAP = {"louvain": "greedy_modularity", "leiden": "greedy_modularity", "label_propagation": "label_prop",
                     "label_prop": "label_prop", "infomap": "greedy_modularity", "wcc": "wcc", "greedy_modularity": "greedy_modularity"}
        raw_algo = data.get("algorithm", "greedy_modularity")
        algorithm = _ALGO_MAP.get(raw_algo, "greedy_modularity")
        community_result = run_community_detection_neo4j(
            driver, algorithm=algorithm, resolution=resolution)
        fp_result = run_fingerprinting_neo4j(driver) if run_fp else None
        return JSONResponse({"success": True, "data": {"communityDetection": community_result, "fingerprinting": fp_result}})
    except Exception as e:
        logger.error(
            f"Community detection error: {e}\n{traceback.format_exc()}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/upi/neo4j/graph")
def upi_neo4j_graph(limit: int = Query(default=2000), current_user=Depends(get_current_user)):
    if not HAS_NEO4J_COMMUNITY:
        return JSONResponse({"success": False, "error": "Neo4j community module not available"}, status_code=500)
    driver = _get_neo4j_driver()
    if not driver:
        return JSONResponse({"success": False, "error": "Neo4j not connected."}, status_code=503)
    active_job = UpiIngestionJobStore.get_active_job()
    if active_job:
        resp = JSONResponse({"success": False, "ingesting": True, "job_id": active_job["job_id"], "message": active_job.get(
            "message", "Ingestion in progress — please retry shortly")}, status_code=202)
        resp.headers["Retry-After"] = "5"
        return resp
    try:
        limit = min(limit, 10000)
        graph = get_neo4j_graph(driver, limit=limit)
        stats = get_neo4j_graph_stats(driver)
        return JSONResponse({"success": True, "data": {"nodes": graph["nodes"], "edges": graph["edges"], "stats": stats}})
    except Exception as e:
        logger.error("Neo4j graph fetch error: %s", e, exc_info=True)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/upi/neo4j/mule-detection")
def upi_neo4j_mule_detection(min_risk: float = Query(default=50.0), limit: int = Query(default=200), current_user=Depends(get_current_user)):
    if not HAS_NEO4J_COMMUNITY:
        return JSONResponse({"success": False, "error": "Neo4j community module not available"}, status_code=500)
    driver = _get_neo4j_driver()
    if not driver:
        return JSONResponse({"success": False, "error": "Neo4j not connected."}, status_code=503)
    try:
        result = get_mule_detection_results(
            driver, min_risk=min_risk, limit=limit)
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── Exception handlers ────────────────────────────────────────────────────────


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        logger.warning(f"404 error: {request.url}")
        return _JSONResponse({"error": "Not found", "path": request.url.path}, status_code=404)
    return _JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc!r}")
    return _JSONResponse({"error": "Internal server error", "detail": str(exc)}, status_code=500)


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    logger.error(f"500 error: {exc}")
    return _JSONResponse({"error": "Internal server error"}, status_code=500)


# ── create_app for v2 API registration ────────────────────────────────────────

def create_app(config=None):
    try:
        from backend.api.v2.endpoints import api_bp as api_v2_bp, init_services
        app.include_router(api_v2_bp)
        init_services(data_dir=str(BASE_DIR / "data"))
        logger.info("API v2 registered - endpoints at /api/v2/*")
    except ImportError as e:
        logger.warning(f"API v2 not loaded: {e}")
    return app


@app.post("/api/case/save")
async def save_case_singular(request: Request, current_user=Depends(get_current_user)):
    """Save an investigation case file to disk. Body: {caseFile: {...}}"""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    try:
        case_data = data.get("caseFile") or data.get("case_data") or data
        fetcher = BlockchainComFetcher()
        metadata = case_data.setdefault("metadata", {})
        # Stamp the saving user
        if current_user:
            metadata.setdefault("userId", str(getattr(current_user, "id", "")))
            metadata.setdefault("createdBy", getattr(
                current_user, "username", ""))
        case_id = metadata.get("caseId")
        out_path = fetcher.save_case_file(
            case_data, case_id=case_id, cases_dir=CASES_DIR)
        return JSONResponse({
            "success": True,
            "caseId": metadata.get("caseId", out_path.stem),
            "filename": out_path.name,
            "path": str(out_path),
            "message": f"Case saved to {out_path.name}"
        })
    except Exception as e:
        logger.error(f"case/save error: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ── SPA catch-all — MUST BE REGISTERED LAST ──────────────────────────────────

@app.get("/{catch_all:path}")
def serve_spa_fallback(catch_all: str):
    """React SPA fallback: serve index.html for all non-API browser navigation."""
    if catch_all.startswith("api/"):
        return JSONResponse({"error": "API endpoint not found", "path": f"/{catch_all}"}, status_code=404)
    try:
        build = Path("frontend/build").resolve()
        if build.exists():
            fp = build / catch_all
            if fp.exists() and fp.is_file():
                return FileResponse(str(fp))
            return FileResponse(str(build / "index.html"))
        alt = Path("frontend").resolve() / catch_all
        if alt.exists():
            return FileResponse(str(alt))
        return JSONResponse({"error": "Frontend not found"}, status_code=404)
    except Exception:
        return JSONResponse({"error": "File not found"}, status_code=404)
