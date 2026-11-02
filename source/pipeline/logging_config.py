"""Run-scoped logging: every run gets an id and a log file under /logs."""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s - %(message)s"


def new_run_id() -> str:
    return uuid.uuid4().hex[:10]


def setup_logging(logs_dir: Path, run_id: str, level: str = "INFO") -> Path:
    """Configure console + file logging; returns the log file path."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"run_{stamp}_{run_id}.log"

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(console)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(file_handler)

    return log_path
