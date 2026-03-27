"""
Centralized Structured Logger for ChainBreak

Provides structured logging with the format:
{timestamp, request_id, user_id, route, action, status, latency_ms, payload_hash}

All logs are emitted to ChainBreak/logs/chainbreak.log
"""

import logging
import hashlib
import json
import time
import uuid
import functools
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Dict
from contextvars import ContextVar

# Framework-agnostic request context (replaces Flask's g/request)
_request_id_var: ContextVar[str] = ContextVar('request_id', default='no-ctx')
_user_id_var: ContextVar[str] = ContextVar('user_id', default='anonymous')
_route_var: ContextVar[str] = ContextVar('route', default='no-route')

def has_request_context() -> bool:
    return _request_id_var.get('no-ctx') != 'no-ctx'

# ============================================================================
# STRUCTURED LOG RECORD
# ============================================================================

class StructuredLogRecord:
    """Represents a single structured log entry."""
    
    __slots__ = ['timestamp', 'request_id', 'user_id', 'route', 'action', 
                 'status', 'latency_ms', 'payload_hash', 'level', 'message', 'extra']
    
    def __init__(
        self,
        action: str,
        status: str = "info",
        latency_ms: Optional[float] = None,
        payload: Optional[Any] = None,
        message: str = "",
        level: str = "INFO",
        extra: Optional[Dict] = None
    ):
        self.timestamp = datetime.utcnow().isoformat() + "Z"
        self.request_id = self._get_request_id()
        self.user_id = self._get_user_id()
        self.route = self._get_route()
        self.action = action
        self.status = status
        self.latency_ms = round(latency_ms, 2) if latency_ms else None
        self.payload_hash = self._hash_payload(payload)
        self.level = level
        self.message = message
        self.extra = extra or {}
    
    @staticmethod
    def _get_request_id() -> str:
        """Get or generate request ID from context var."""
        rid = _request_id_var.get("no-ctx")
        if rid == "no-ctx":
            rid = str(uuid.uuid4())[:8]
            _request_id_var.set(rid)
        return rid
    
    @staticmethod
    def _get_user_id() -> str:
        """Get user ID from context var."""
        return _user_id_var.get("anonymous")

    @staticmethod
    def _get_route() -> str:
        """Get current route from context var."""
        return _route_var.get("no-route")
    
    @staticmethod
    def _hash_payload(payload: Any) -> Optional[str]:
        """Create a short hash of the payload for traceability."""
        if payload is None:
            return None
        try:
            if isinstance(payload, dict):
                content = json.dumps(payload, sort_keys=True, default=str)
            else:
                content = str(payload)
            return hashlib.sha256(content.encode()).hexdigest()[:12]
        except:
            return None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON logging."""
        return {
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "route": self.route,
            "action": self.action,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "payload_hash": self.payload_hash,
            "level": self.level,
            "message": self.message,
            **self.extra
        }
    
    def to_log_line(self) -> str:
        """Convert to compact log line format."""
        parts = [
            f"[{self.timestamp}]",
            f"[{self.level:8}]",
            f"[req:{self.request_id}]",
            f"[user:{self.user_id}]",
            f"[{self.route}]",
            f"action={self.action}",
            f"status={self.status}",
        ]
        if self.latency_ms is not None:
            parts.append(f"latency={self.latency_ms}ms")
        if self.payload_hash:
            parts.append(f"payload={self.payload_hash}")
        if self.message:
            parts.append(f"msg=\"{self.message}\"")
        return " ".join(parts)


# ============================================================================
# STRUCTURED LOGGER
# ============================================================================

class StructuredLogger:
    """
    Centralized structured logger for ChainBreak.
    
    Emits logs in the format:
    {timestamp, request_id, user_id, route, action, status, latency_ms, payload_hash}
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Setup log file path - Project root / logs (parents[2] goes up: logger/ -> backend/ -> project/)
        project_root = Path(__file__).resolve().parents[2]
        self.log_dir = project_root / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "chainbreak.log"
        
        # Setup Python logger
        self.logger = logging.getLogger("chainbreak.structured")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        
        # Prevent duplicate handlers
        if not self.logger.handlers:
            # File handler
            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(file_handler)
            
            # Console handler for errors
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.WARNING)
            console_handler.setFormatter(logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s'
            ))
            self.logger.addHandler(console_handler)
        
        self._initialized = True
    
    def _log(self, record: StructuredLogRecord):
        """Write a structured log record."""
        log_line = record.to_log_line()
        level = getattr(logging, record.level.upper(), logging.INFO)
        self.logger.log(level, log_line)
    
    # ========================================================================
    # Core Logging Methods
    # ========================================================================
    
    def info(self, action: str, message: str = "", payload: Any = None, 
             latency_ms: float = None, **extra):
        """Log an info-level event."""
        record = StructuredLogRecord(
            action=action,
            status="success",
            latency_ms=latency_ms,
            payload=payload,
            message=message,
            level="INFO",
            extra=extra
        )
        self._log(record)
    
    def warn(self, action: str, message: str = "", payload: Any = None,
             latency_ms: float = None, **extra):
        """Log a warning-level event."""
        record = StructuredLogRecord(
            action=action,
            status="warning",
            latency_ms=latency_ms,
            payload=payload,
            message=message,
            level="WARNING",
            extra=extra
        )
        self._log(record)
    
    def error(self, action: str, message: str = "", payload: Any = None,
              latency_ms: float = None, error: Exception = None, **extra):
        """Log an error-level event."""
        if error:
            extra['error_type'] = type(error).__name__
            extra['error_msg'] = str(error)
        record = StructuredLogRecord(
            action=action,
            status="error",
            latency_ms=latency_ms,
            payload=payload,
            message=message,
            level="ERROR",
            extra=extra
        )
        self._log(record)
    
    def debug(self, action: str, message: str = "", payload: Any = None, **extra):
        """Log a debug-level event."""
        record = StructuredLogRecord(
            action=action,
            status="debug",
            payload=payload,
            message=message,
            level="DEBUG",
            extra=extra
        )
        self._log(record)
    
    # ========================================================================
    # Specialized Logging Methods
    # ========================================================================
    
    def api_request(self, action: str, status: str = "started", 
                    payload: Any = None, latency_ms: float = None):
        """Log an API request start/end."""
        self.info(
            action=f"api.{action}",
            message=f"API {status}",
            payload=payload,
            latency_ms=latency_ms
        )
    
    def user_action(self, action: str, details: str = "", payload: Any = None):
        """Log a user-initiated action."""
        self.info(
            action=f"user.{action}",
            message=details,
            payload=payload
        )
    
    def state_transition(self, from_state: str, to_state: str, entity: str = ""):
        """Log a state transition."""
        self.info(
            action="state.transition",
            message=f"{entity}: {from_state} -> {to_state}",
            from_state=from_state,
            to_state=to_state,
            entity=entity
        )
    
    def temporal_analysis(self, action: str, details: Dict = None, 
                         latency_ms: float = None):
        """Log temporal analysis events."""
        self.info(
            action=f"temporal.{action}",
            message=str(details) if details else "",
            payload=details,
            latency_ms=latency_ms
        )


# ============================================================================
# DECORATOR FOR API ENDPOINTS
# ============================================================================

def log_endpoint(action_name: str = None):
    """
    Decorator to automatically log API endpoint calls.

    Usage:
        @router.get("/api/temporal/analyze")
        @log_endpoint("temporal.analyze")
        async def analyze_temporal():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            _slog = StructuredLogger()
            start_time = time.perf_counter()
            action = action_name or func.__name__

            _slog.api_request(action, "started")

            try:
                result = await func(*args, **kwargs)
                latency = (time.perf_counter() - start_time) * 1000
                _slog.api_request(action, "completed", latency_ms=latency)
                return result
            except Exception as e:
                latency = (time.perf_counter() - start_time) * 1000
                _slog.error(
                    action=f"api.{action}",
                    message="Request failed",
                    latency_ms=latency,
                    error=e
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            _slog = StructuredLogger()
            start_time = time.perf_counter()
            action = action_name or func.__name__

            _slog.api_request(action, "started")

            try:
                result = func(*args, **kwargs)
                latency = (time.perf_counter() - start_time) * 1000
                _slog.api_request(action, "completed", latency_ms=latency)
                return result
            except Exception as e:
                latency = (time.perf_counter() - start_time) * 1000
                _slog.error(
                    action=f"api.{action}",
                    message="Request failed",
                    latency_ms=latency,
                    error=e
                )
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def init_structured_logging(app):
    """No-op stub kept for import compatibility. Use RequestLogger middleware instead."""
    pass


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

slog = StructuredLogger()

__all__ = ['StructuredLogger', 'slog', 'log_endpoint', 'init_structured_logging']
