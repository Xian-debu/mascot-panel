"""结构化日志：一条一行 JSON，带 reason_code；同时写 stderr 与滚动文件。

旧实现把 print 散在各处，崩溃后什么也留不下（docs/05 P-11）。
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path

MAX_BYTES = 1_000_000
BACKUPS = 3


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("reason_code", "event", "state", "detail"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def default_log_dir() -> Path:
    import os

    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "mascot" / "logs"
    return Path.home() / ".mascot" / "logs"


def setup_logging(log_dir: Path | None = None, level: str = "INFO") -> Path:
    directory = log_dir or default_log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_file = directory / "mascot.log"

    handlers: list[logging.Handler] = []
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())
    handlers.append(file_handler)

    if sys.stderr is not None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(JsonFormatter())
        handlers.append(stream)

    root = logging.getLogger()
    root.handlers[:] = handlers
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    return log_file
