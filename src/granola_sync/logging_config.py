"""Structured logging setup with Rich terminal output and file logging."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from rich.logging import RichHandler

_LOG_RETENTION_DAYS = 30


def _cleanup_old_logs(log_path: Path, retention_days: int) -> None:
    """Delete sync_*.log files older than retention_days (best-effort)."""
    cutoff = time.time() - retention_days * 86400
    for old in log_path.glob("sync_*.log"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def setup_logging(log_dir: str = "logs", verbose: bool = False) -> Path:
    """Configure logging with Rich terminal handler and file handler.

    Args:
        log_dir: Directory for log files.
        verbose: Enable DEBUG level logging.

    Returns:
        Path to the log file.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    _cleanup_old_logs(log_path, _LOG_RETENTION_DAYS)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"sync_{timestamp}.log"

    level = logging.DEBUG if verbose else logging.INFO

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Clear existing handlers
    root.handlers.clear()

    # Rich terminal handler (clean output)
    rich_handler = RichHandler(
        level=logging.INFO,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
    )
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(rich_handler)

    # File handler (detailed)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)

    return log_file
