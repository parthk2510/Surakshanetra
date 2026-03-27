import logging
import os
from logging.handlers import RotatingFileHandler

_LOG_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "logs")
)
LOG_FILE = os.path.join(_LOG_DIR, "chainbreak.log")

_FMT = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_rgcn_logger(name: str = "chainbreak.rgcn") -> logging.Logger:
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
    except OSError:
        pass

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    try:
        fh = RotatingFileHandler(
            LOG_FILE,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_FMT)
        logger.addHandler(fh)
    except (OSError, IOError) as exc:
        logging.getLogger(__name__).warning("Cannot open log file %s: %s", LOG_FILE, exc)

    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(_FMT)
    logger.addHandler(sh)

    return logger


rgcn_logger = get_rgcn_logger("chainbreak.rgcn.service")

# Alias used by pipeline training scripts
get_logger = get_rgcn_logger
