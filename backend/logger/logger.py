# backend/logger/logger.py
# ============================================================================
# BLACK BOX LOGGER - Centralized Logging System with Execution Time Tracking
# (Framework-agnostic: no Flask imports)
# ============================================================================
import logging
import sys
import time
import traceback
import json
import functools
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional


# ============================================================================
# COLORIZED CONSOLE OUTPUT
# ============================================================================

class ColorCodes:
    """ANSI color codes for console output"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Text colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright text colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"

    # Background colors
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"


class ColorizedFormatter(logging.Formatter):
    """Custom formatter with colorized output for console"""

    LEVEL_COLORS = {
        logging.DEBUG: ColorCodes.DIM + ColorCodes.CYAN,
        logging.INFO: ColorCodes.GREEN,
        logging.WARNING: ColorCodes.YELLOW,
        logging.ERROR: ColorCodes.RED,
        logging.CRITICAL: ColorCodes.BOLD + ColorCodes.BG_RED + ColorCodes.WHITE,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, ColorCodes.WHITE)
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level_str = f"{color}[{record.levelname:8}]{ColorCodes.RESET}"
        time_str = f"{ColorCodes.DIM}{timestamp}{ColorCodes.RESET}"
        name_str = f"{ColorCodes.CYAN}{record.name}{ColorCodes.RESET}"

        extras = ""
        if hasattr(record, "endpoint") and record.endpoint:
            extras += f" {ColorCodes.MAGENTA}[{record.endpoint}]{ColorCodes.RESET}"
        if hasattr(record, "params") and record.params:
            extras += f" {ColorCodes.DIM}{record.params}{ColorCodes.RESET}"
        if hasattr(record, "duration") and record.duration:
            dur_color = (
                ColorCodes.GREEN if record.duration < 1000
                else ColorCodes.YELLOW if record.duration < 5000
                else ColorCodes.RED
            )
            extras += f" {dur_color}(Duration: {record.duration}ms){ColorCodes.RESET}"

        message = f"{time_str} {level_str} {name_str}{extras} - {record.getMessage()}"
        if record.exc_info:
            message += f"\n{ColorCodes.RED}{self.formatException(record.exc_info)}{ColorCodes.RESET}"
        return message


class FileFormatter(logging.Formatter):
    """Clean formatter for file output without colors"""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        parts = [f"[{timestamp}]", f"[{record.levelname:8}]"]
        if hasattr(record, "endpoint") and record.endpoint:
            parts.append(f"[{record.endpoint}]")
        if hasattr(record, "params") and record.params:
            parts.append(f"[{record.params}]")
        parts.append(f"- {record.getMessage()}")
        if hasattr(record, "duration") and record.duration:
            parts.append(f"(Duration: {record.duration}ms)")
        message = " ".join(parts)
        if record.exc_info:
            message += f"\n{'='*80}\nSTACK TRACE:\n{self.formatException(record.exc_info)}\n{'='*80}"
        return message


# ============================================================================
# LOGGER SETUP
# ============================================================================

def setup_logger(
    name: str = "chainbreak",
    log_level: int = logging.DEBUG,
    log_file: Optional[str] = None,
    enable_console: bool = True,
) -> logging.Logger:
    _logger = logging.getLogger(name)
    _logger.setLevel(log_level)
    if _logger.handlers:
        return _logger

    if log_file is None:
        project_root = Path(__file__).resolve().parents[2]
        log_dir = project_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "chainbreak.log"
    else:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(ColorizedFormatter())
        _logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(FileFormatter())
    _logger.addHandler(file_handler)

    return _logger


# Create default logger instance
logger = setup_logger()


# ============================================================================
# DECORATORS
# ============================================================================

def log_execution_time(
    endpoint_name: Optional[str] = None,
    log_params: bool = True,
    log_result: bool = False,
    log_level: int = logging.INFO,
) -> Callable:
    """Decorator to log execution time of API endpoints (framework-agnostic)."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            ep_name = endpoint_name or func.__name__
            params_str = ""
            if log_params:
                param_parts = []
                for arg in args:
                    if isinstance(arg, (str, int, float, bool)):
                        param_parts.append(str(arg)[:50])
                for key, value in kwargs.items():
                    if isinstance(value, (str, int, float, bool)):
                        param_parts.append(f"{key}={str(value)[:30]}")
                if param_parts:
                    params_str = ", ".join(param_parts)

            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                log_extra = {"endpoint": ep_name, "params": params_str, "duration": duration_ms}
                logger.log(log_level, "Completed successfully", extra=log_extra)
                if log_result and result is not None:
                    try:
                        result_str = json.dumps(result)[:200] if isinstance(result, dict) else str(result)[:200]
                        logger.debug(f"Result: {result_str}", extra=log_extra)
                    except Exception:
                        pass
                return result
            except Exception as e:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                log_extra = {"endpoint": ep_name, "params": params_str, "duration": duration_ms}
                logger.error(f"Failed: {type(e).__name__}: {str(e)}", exc_info=True, extra=log_extra)
                raise

        # Also support async functions
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            ep_name = endpoint_name or func.__name__
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.log(log_level, "Completed successfully", extra={"endpoint": ep_name, "params": "", "duration": duration_ms})
                return result
            except Exception as e:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.error(f"Failed: {type(e).__name__}: {str(e)}", exc_info=True, extra={"endpoint": ep_name, "params": "", "duration": duration_ms})
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    return decorator


def log_api_endpoint(func: Callable) -> Callable:
    """Convenience decorator for API endpoints."""
    return log_execution_time(
        endpoint_name=func.__name__,
        log_params=True,
        log_result=False,
        log_level=logging.INFO,
    )(func)


# ============================================================================
# ERROR HANDLING UTILITIES
# ============================================================================

class APIError(Exception):
    """Base class for API errors with clean JSON response"""

    def __init__(self, message: str, code: int = 500, details: Optional[dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        return {"error": self.message, "code": self.code, **self.details}


def format_error_response(error: Exception, code: int = 500, log_traceback: bool = True) -> tuple:
    error_mappings = {
        "TimeoutError": ("External API Timeout", 504),
        "ConnectionError": ("External Service Unavailable", 503),
        "RateLimitError": ("Rate Limit Exceeded", 429),
        "InvalidAddressError": ("Invalid Bitcoin Address", 400),
        "TransactionNotFoundError": ("Transaction Not Found", 404),
        "BlockNotFoundError": ("Block Not Found", 404),
        "BlockchainAPIError": ("Blockchain API Error", 502),
    }
    error_type = type(error).__name__
    if error_type in error_mappings:
        message, code = error_mappings[error_type]
    elif isinstance(error, APIError):
        message = error.message
        code = error.code
    else:
        message = "Internal Server Error"
        code = 500

    if log_traceback:
        logger.error(
            f"API Error: {error_type} - {str(error)}",
            exc_info=True,
            extra={"endpoint": "error_handler", "params": "", "duration": None},
        )
    return ({"error": message, "code": code}, code)


def safe_json_log(data: Any, max_length: int = 500) -> str:
    try:
        if isinstance(data, dict):
            safe_data = {}
            for key, value in data.items():
                if isinstance(value, str) and len(value) > max_length:
                    safe_data[key] = value[:max_length] + "..."
                elif isinstance(value, (list, dict)):
                    safe_data[key] = f"<{type(value).__name__}: {len(value)} items>"
                else:
                    safe_data[key] = value
            return json.dumps(safe_data)
        elif isinstance(data, list):
            return f"<list: {len(data)} items>"
        else:
            return str(data)[:max_length]
    except Exception:
        return f"<{type(data).__name__}>"


# ============================================================================
# PERFORMANCE METRICS
# ============================================================================

class PerformanceTracker:
    """Track and log performance metrics for analysis"""

    def __init__(self):
        self.metrics = {}

    def start(self, operation: str) -> float:
        start_time = time.perf_counter()
        self.metrics[operation] = {"start": start_time}
        return start_time

    def end(self, operation: str) -> float:
        end_time = time.perf_counter()
        if operation in self.metrics:
            start_time = self.metrics[operation]["start"]
            duration_ms = (end_time - start_time) * 1000
            self.metrics[operation]["duration"] = duration_ms
            return duration_ms
        return 0

    def log_summary(self, endpoint: str):
        if not self.metrics:
            return
        total_ms = sum(m.get("duration", 0) for m in self.metrics.values())
        summary_parts = []
        for op, d in self.metrics.items():
            duration = d.get("duration", 0)
            pct = (duration / total_ms * 100) if total_ms > 0 else 0
            summary_parts.append(f"{op}: {duration:.1f}ms ({pct:.1f}%)")
        logger.info(
            f"Performance breakdown: {' | '.join(summary_parts)} | Total: {total_ms:.1f}ms",
            extra={"endpoint": endpoint, "params": "", "duration": total_ms},
        )

    def reset(self):
        self.metrics = {}


# Create a global performance tracker instance
perf_tracker = PerformanceTracker()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "logger",
    "setup_logger",
    "log_execution_time",
    "log_api_endpoint",
    "APIError",
    "format_error_response",
    "safe_json_log",
    "PerformanceTracker",
    "perf_tracker",
    "ColorCodes",
]
