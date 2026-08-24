"""Structured logging for IFS platform."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            payload.update(record.extra_data)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger("ifs")
    if root.handlers:
        return
    root.setLevel(level)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(JsonFormatter())
    root.addHandler(sh)
    fh = logging.FileHandler(LOG_DIR / "ifs_platform.log", encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"ifs.{name}")
