"""JSON-line structured logging for the Task Analyzer server.

Covers PCE-44 (REQ-003). Records are emitted through the standard
``logging`` module as one JSON object per line, carrying the approved
field list and nothing else.

The formatter works from an allow list. Any other attribute a caller
attaches to a record is dropped, so task titles, observations, request
bodies, canonical request text and secrets cannot reach the log even by
accident. The log message itself is the event name: keep it a stable
identifier, never user content.

Formatting never raises into the caller. A record that cannot be
serialized is replaced by a minimal failure record, because log
formatting must not decide whether a transaction commits.
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
    """Measure elapsed time with the monotonic clock.

    Wall-clock time can jump backwards when the host clock is corrected.
    Durations therefore come from ``time.monotonic`` only.
    """

    def __init__(self) -> None:
        """Start the measurement."""
        self._started_at = time.monotonic()

    def elapsed_ms(self) -> int:
        """Return the whole milliseconds elapsed since construction.

        Returns:
            The elapsed monotonic duration, rounded to milliseconds.
        """
        elapsed_seconds = time.monotonic() - self._started_at
        return round(elapsed_seconds * 1000)


class JsonLineFormatter(logging.Formatter):
    """Render a logging record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        """Render one record.

        Args:
            record: The record to render.

        Returns:
            One JSON object with the approved fields, without newlines.
        """
        try:
            payload = _build_payload(record)
            return json.dumps(payload)
        except Exception:
            # Deliberately broad: a logging failure must never surface
            # in the caller's control flow or abort a transaction.
            return json.dumps(_failure_payload(record))


def configure_logging(level: str) -> None:
    """Install JSON-line logging on the root logger.

    Replaces any previously installed root handlers so records are not
    emitted twice in a different format.

    Args:
        level: Standard logging level name, already validated by
            ``ServerSettings``.
    """
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
    """Collect the approved fields of one record.

    Args:
        record: The record to read.

    Returns:
        A mapping holding the required fields plus any supplied optional
        identifier.

    Raises:
        Exception: If a supplied value cannot be coerced to its field
            type. The caller turns that into a failure record.
    """
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
    """Build the minimal record used when formatting failed.

    Args:
        record: The record that could not be rendered.

    Returns:
        A mapping with the required fields only, naming the failure.
    """
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
    """Render a record's creation time as a UTC instant.

    Args:
        created: Seconds since the epoch, as recorded by ``logging``.

    Returns:
        An ISO-8601 UTC instant with six fractional digits and a ``Z``
        suffix.
    """
    moment = datetime.fromtimestamp(created, tz=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _optional_text(value: object) -> str | None:
    """Coerce an optional identifier or code to text.

    Args:
        value: The supplied value, or None when the field is unknown.

    Returns:
        The value as text, or None.
    """
    if value is None:
        return None
    return str(value)


def _optional_duration(value: object) -> int | None:
    """Coerce an optional duration to whole milliseconds.

    Args:
        value: The supplied duration, or None when not measured.

    Returns:
        The duration in whole milliseconds, or None.

    Raises:
        TypeError: If the value is not a number.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"duration_ms must be numeric; got {type(value)!r}")
    return round(value)
