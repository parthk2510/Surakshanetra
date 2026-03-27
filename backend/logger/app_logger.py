import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "chainbreak.log"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

os.makedirs(LOG_DIR, exist_ok=True)


def setup_logging() -> logging.Logger:
    if getattr(setup_logging, "_initialized", False):
        return logging.getLogger()

    log_format = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(log_format, datefmt=date_format)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    logging.getLogger("uvicorn.access").propagate = False
    logging.getLogger("uvicorn.error").propagate = True

    setup_logging._initialized = True
    return root


def get_recent_logs(lines: int = 100, level: str = None):
    if not LOG_FILE.exists():
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        recent = [ln.strip() for ln in all_lines[-lines:] if ln.strip()]
        if level:
            recent = [ln for ln in recent if f"[{level.upper()}]" in ln]
        return recent
    except Exception as exc:
        return [f"Error reading logs: {exc}"]


def log_api_request(endpoint, method, status_code, duration_ms, user_id=None):
    logging.getLogger("api").info(
        "API %s %s -> %d (%.1fms) user=%s",
        method,
        endpoint,
        status_code,
        duration_ms,
        user_id or "ANON",
    )


def log_blockchain_request(address, request_type, success, duration_ms):
    status = "SUCCESS" if success else "FAILED"
    logging.getLogger("blockchain").info(
        "BLOCKCHAIN %s %s... -> %s (%.1fms)", request_type, address[:16], status, duration_ms
    )


def log_security_event(event_type, details, user_id=None, ip_address=None):
    logging.getLogger("security").warning(
        "SECURITY %s: %s [user=%s, ip=%s]", event_type, details, user_id, ip_address
    )


import uuid as _uuid_module

class RequestLogger(BaseHTTPMiddleware):
    # Paths to skip verbose logging (static assets, health checks)
    _SKIP_PATHS = {"/api/health", "/favicon.ico", "/_next/", "/static/"}

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP", "")
        if real_ip:
            return real_ip.strip()
        if request.client:
            return request.client.host
        return "unknown"

    @staticmethod
    def _parse_user_agent(ua: str) -> str:
        """Return a short readable summary of the User-Agent string."""
        if not ua:
            return "unknown"
        if "Mobile" in ua or "Android" in ua or "iPhone" in ua:
            device = "mobile"
        else:
            device = "desktop"
        for browser in ("Chrome", "Firefox", "Safari", "Edge", "Opera"):
            if browser in ua:
                return f"{browser}/{device}"
        return f"other/{device}"

    @staticmethod
    def _extract_user_from_token(request: Request) -> str:
        """Extract username from Bearer JWT without full verification (for logging only)."""
        try:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
                # Decode payload without verification just for logging
                import base64, json as _json
                parts = token.split(".")
                if len(parts) == 3:
                    padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    payload = _json.loads(base64.urlsafe_b64decode(padded))
                    return payload.get("sub", "unknown")
        except Exception:
            pass
        return "anonymous"

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip noisy paths
        path = request.url.path
        if any(path.startswith(s) for s in self._SKIP_PATHS):
            return await call_next(request)

        request_id = str(_uuid_module.uuid4())[:12]
        start = time.monotonic()

        ip = self._get_client_ip(request)
        ua_raw = request.headers.get("User-Agent", "")
        browser = self._parse_user_agent(ua_raw)
        username = self._extract_user_from_token(request)

        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        audit_logger = logging.getLogger("audit")
        audit_logger.info(
            "REQUEST req_id=%s user=%s ip=%s browser=%s method=%s path=%s status=%d duration=%.1fms ua=%s",
            request_id,
            username,
            ip,
            browser,
            request.method,
            path,
            response.status_code,
            duration_ms,
            ua_raw[:120] if ua_raw else "none",
        )
        return response

    def init_app(self, app):
        app.add_middleware(RequestLogger)


logger = setup_logging()
