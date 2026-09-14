"""Unit tests for JSON-line structured logging.

Covers PCE-44; REQ-003.
"""

import json
import logging
import time
from collections.abc import Iterator
from typing import Any

import pytest

from task_analyzer_server.logging_config import (
    FORMAT_FAILURE_EVENT,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    DurationTimer,
    JsonLineFormatter,
    configure_logging,
)

FORBIDDEN_VALUES = {
    "title": "Renew the passport",
    "observations": "Line one\nLine two",
    "request_body": '{"title": "Renew the passport"}',
    "canonical_request": "POST /v1/tasks {}",
    "secret": "hunter2-token",
}


@pytest.fixture
def restored_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in original_handlers:
        root.addHandler(handler)
    root.setLevel(original_level)


def build_record(**extra: Any) -> logging.LogRecord:
    record = logging.LogRecord(
        name="task_analyzer_server",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="task_created",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_record_serializes_as_one_json_object_per_line() -> None:
    record = build_record(
        request_id="c0ffee",
        operation_id="op-1",
        task_id="task-1",
        outcome="succeeded",
        error_code=None,
        duration_ms=12,
    )

    line = JsonLineFormatter().format(record)

    assert "\n" not in line
    payload = json.loads(line)
    assert set(payload) == set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    assert payload["level"] == "INFO"
    assert payload["event"] == "task_created"
    assert payload["request_id"] == "c0ffee"
    assert payload["operation_id"] == "op-1"
    assert payload["task_id"] == "task-1"
    assert payload["outcome"] == "succeeded"
    assert payload["error_code"] is None
    assert payload["duration_ms"] == 12


def test_optional_identifiers_are_omitted_when_absent() -> None:
    record = build_record(request_id="c0ffee", outcome="rejected")

    payload = json.loads(JsonLineFormatter().format(record))

    assert set(payload) == set(REQUIRED_FIELDS)
    assert payload["outcome"] == "rejected"
    assert payload["error_code"] is None
    assert payload["duration_ms"] is None


def test_timestamp_is_a_utc_instant_with_six_fractional_digits() -> None:
    record = build_record()
    record.created = 1_757_721_600.123456

    payload = json.loads(JsonLineFormatter().format(record))

    assert payload["timestamp"] == "2025-09-13T00:00:00.123456Z"


def test_forbidden_content_is_never_emitted() -> None:
    record = build_record(request_id="c0ffee", **FORBIDDEN_VALUES)

    line = JsonLineFormatter().format(record)

    payload = json.loads(line)
    assert set(payload) == set(REQUIRED_FIELDS)
    for field, value in FORBIDDEN_VALUES.items():
        assert field not in payload
        assert value not in line
    assert "Renew the passport" not in line


def test_duration_comes_from_the_monotonic_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monotonic_now = {"seconds": 100.0}
    monkeypatch.setattr(time, "monotonic", lambda: monotonic_now["seconds"])

    timer = DurationTimer()
    monotonic_now["seconds"] = 100.25

    assert timer.elapsed_ms() == 250


def test_formatting_failure_does_not_raise() -> None:
    record = build_record(request_id="c0ffee", duration_ms=object())

    line = JsonLineFormatter().format(record)

    payload = json.loads(line)
    assert payload["event"] == FORMAT_FAILURE_EVENT
    assert payload["error_code"] == FORMAT_FAILURE_EVENT
    assert set(payload) == set(REQUIRED_FIELDS)


def test_logging_an_unserializable_record_does_not_raise_to_the_caller(
    restored_root_logger: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO")

    logging.getLogger("task_analyzer_server").info(
        "task_created", extra={"duration_ms": object()}
    )

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["event"] == FORMAT_FAILURE_EVENT


def test_configure_logging_writes_json_lines(
    restored_root_logger: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO")

    logging.getLogger("task_analyzer_server").info(
        "task_created", extra={"request_id": "c0ffee", "duration_ms": 7}
    )

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert set(payload) == set(REQUIRED_FIELDS)
    assert payload["event"] == "task_created"
    assert payload["request_id"] == "c0ffee"
    assert payload["duration_ms"] == 7


def test_configure_logging_applies_the_requested_level(
    restored_root_logger: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO")

    logging.getLogger("task_analyzer_server").debug("task_inspected")

    assert capsys.readouterr().out == ""
