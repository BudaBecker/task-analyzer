"""JSON-line structured logging for the Task Analyzer server.

Covers PCE-44 (REQ-003).
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any

REQUIRED_FIELDS = (
    "timestamp",
    "level",
    "event",
    "request_id",
    "outcome",
    "error_code",
    "duration_ms",
)
OPTIONAL_FIELDS = ("operation_id", "task_id")

FORMAT_FAILURE_EVENT = "log_record_not_serializable"


class DurationTimer:
    """Measure elapsed time with the monotonic clock."""

    def __init__(self) -> None:
        """Start the measurement."""
        self._started_at = time.monotonic()

    def elapsed_ms(self) -> int:
        """Return the whole milliseconds elapsed since construction."""
        elapsed_seconds = time.monotonic() - self._started_at
        return round(elapsed_seconds * 1000)


class JsonLineFormatter(logging.Formatter):
    """Render a logging record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        """Render one record."""
        try:
            payload = _build_payload(record)
            return json.dumps(payload)
        except Exception:
            # Deliberately broad: a logging failure must never surface
            # in the caller's control flow or abort a transaction.
            return json.dumps(_failure_payload(record))


def configure_logging(level: str) -> None:
    """Install JSON-line logging on the root logger."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonLineFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn installs non-propagating handlers before calling the factory.
    runtime_handler = logging.StreamHandler(stream=sys.stderr)
    runtime_handler.setFormatter(JsonLineFormatter())
    runtime = logging.getLogger("uvicorn")
    runtime.handlers = [runtime_handler]
    runtime.setLevel(level)
    runtime.propagate = False
    for name in ("uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(level)
        logger.propagate = True


def _build_payload(record: logging.LogRecord) -> dict[str, Any]:
    """Collect the approved fields of one record."""
    payload: dict[str, Any] = {
        "timestamp": _format_timestamp(record.created),
        "level": record.levelname,
        "event": record.getMessage(),
        "request_id": _optional_text(getattr(record, "request_id", None)),
        "outcome": _optional_text(getattr(record, "outcome", None)),
        "error_code": _optional_text(getattr(record, "error_code", None)),
        "duration_ms": _optional_duration(
            getattr(record, "duration_ms", None)
        ),
    }
    for field in OPTIONAL_FIELDS:
        value = getattr(record, field, None)
        if value is not None:
            payload[field] = _optional_text(value)
    return payload


def _failure_payload(record: logging.LogRecord) -> dict[str, Any]:
    """Build the minimal record used when formatting failed."""
    return {
        "timestamp": _format_timestamp(getattr(record, "created", 0.0)),
        "level": str(getattr(record, "levelname", "ERROR")),
        "event": FORMAT_FAILURE_EVENT,
        "request_id": None,
        "outcome": None,
        "error_code": FORMAT_FAILURE_EVENT,
        "duration_ms": None,
    }


def _format_timestamp(created: float) -> str:
    """Render a record's creation time as a UTC instant."""
    moment = datetime.fromtimestamp(created, tz=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _optional_text(value: object) -> str | None:
    """Coerce an optional identifier or code to text."""
    if value is None:
        return None
    return str(value)


def _optional_duration(value: object) -> int | None:
    """Coerce an optional duration to whole milliseconds."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"duration_ms must be numeric; got {type(value)!r}")
    return round(value)
