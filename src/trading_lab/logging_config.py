"""Centralised logging configuration for trading-lab.

Call setup_logging() once at the start of any script or application entry point.
All subsequent getLogger() calls will inherit the configured handlers and format.
"""
import logging
import logging.handlers
from pathlib import Path

from trading_lab.paths import LOGS_DIR

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a rotating file handler and stdout handler.

    Safe to call multiple times — additional handlers are not added if the
    root logger already has handlers attached.

    Args:
        level: Logging level for both handlers (default INFO).
    """
    root = logging.getLogger()
    if root.handlers:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        LOGS_DIR / "trading_lab.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
