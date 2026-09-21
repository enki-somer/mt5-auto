from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import Queue
from typing import Any

from app.config import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "logs"
MAX_BYTES = 2_000_000
BACKUP_COUNT = 5

_LOGGER_FILES = {
    "application": "application.log",
    "telegram": "telegram.log",
    "parser": "parser.log",
    "mt5": "mt5.log",
    "trades": "trades.log",
    "errors": "errors.log",
}

_SECRET_ASSIGN = re.compile(
    r"(password|api_hash|bot_token|telegram_bot_token|mt5_password|token)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if _SECRET_ASSIGN.search(message):
            record.msg = "[redacted log line containing a secret assignment]"
            record.args = ()
        return True


def _build_handler(path: Path, level: int) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler.addFilter(RedactingFilter())
    return handler


class GuiLogHandler(logging.Handler):
    def __init__(self, log_queue: Queue[dict[str, Any]]) -> None:
        super().__init__()
        self._queue = log_queue
        self.addFilter(RedactingFilter())
        self.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)s  %(name)s  %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put_nowait(
                {
                    "level": record.levelname,
                    "name": record.name,
                    "message": self.format(record),
                }
            )
        except Exception:
            self.handleError(record)


def attach_queue_handler(log_queue: Queue[dict[str, Any]]) -> GuiLogHandler:
    handler = GuiLogHandler(log_queue)
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
    return handler


def setup_logging(log_queue: Queue[dict[str, Any]] | None = None) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if getattr(root, "_trade_aut_configured", False):
        if log_queue is not None:
            attach_queue_handler(log_queue)
        return
    root.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(console)
    root.addHandler(_build_handler(LOG_DIR / "application.log", logging.INFO))
    errors = logging.getLogger("errors")
    errors.addHandler(_build_handler(LOG_DIR / "errors.log", logging.ERROR))
    errors.propagate = True
    for name, filename in _LOGGER_FILES.items():
        if name == "errors":
            continue
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.addHandler(_build_handler(LOG_DIR / filename, logging.INFO))
        logger.propagate = True
    if log_queue is not None:
        attach_queue_handler(log_queue)
    root._trade_aut_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
