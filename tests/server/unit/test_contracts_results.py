"""Unit tests for response and result contracts.

Covers PCE-26, PCE-38, PCE-40, PCE-41 and PCE-43; REQ-010, REQ-029,
REQ-031.
"""

import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from task_analyzer_server.contracts import (
    DEADLINE_FIELD,
    OBSERVATIONS_FIELD,
    OPERATION_ID_FIELD,
    TITLE_FIELD,
    ConfigurationView,
    ErrorCode,
    FieldErrorCode,
    OperationError,
    OperationResult,
    ProtocolError,
    ProtocolErrorDetail,
    TaskListView,
    TaskSnapshot,
    ValidationIssue,
)

OPERATION_ID = UUID("10000000-0000-4000-8000-000000000001")
TASK_ID = UUID("20000000-0000-4000-8000-000000000001")
CONFLICTING_TASK_ID = UUID("20000000-0000-4000-8000-000000000002")
REQUEST_ID = UUID("30000000-0000-4000-8000-000000000001")

RESOLVED_AT = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
SAO_PAULO = ZoneInfo("America/Sao_Paulo")

DESIGN_EXAMPLE_RESULT: dict[str, Any] = {
    "operation_id": "10000000-0000-4000-8000-000000000001",
    "outcome": "succeeded",
    "original_http_status": 201,
    "task": {
        "task_id": "20000000-0000-4000-8000-000000000001",
        "title": "Read notes",
        "observations": None,
        "deadline": "2026-09-14",
        "status": "pending",
        "created_at": "2026-09-13T12:00:00.000000Z",
        "completed_at": None,
    },
    "error": None,
    "resolved_at": "2026-09-13T12:00:00.000000Z",
}


def created_snapshot(**overrides: Any) -> TaskSnapshot:
    fields: dict[str, Any] = {
        "task_id": TASK_ID,
        "title": "Read notes",
        "observations": None,
        "deadline": date(2026, 9, 14),
        "status": "pending",
        "created_at": RESOLVED_AT,
        "completed_at": None,
    }
    fields.update(overrides)
    return TaskSnapshot(**fields)


def created_result() -> OperationResult:
    return OperationResult(
        operation_id=OPERATION_ID,
        outcome="succeeded",
        original_http_status=201,
        task=created_snapshot(),
        error=None,
        resolved_at=RESOLVED_AT,
    )


def test_task_snapshot_exposes_exactly_the_contract_fields() -> None:
    expected = {
        "task_id",
        TITLE_FIELD,
        OBSERVATIONS_FIELD,
        DEADLINE_FIELD,
        "status",
        "created_at",
        "completed_at",
    }

    assert set(TaskSnapshot.model_fields) == expected
    assert set(created_snapshot().model_dump(mode="json")) == expected


@pytest.mark.parametrize(
    "internal_field",
    ["title_key", "is_deleted", "created_at_us", "latest_completed_at_us"],
)
def test_task_snapshot_refuses_internal_fields(internal_field: str) -> None:
    with pytest.raises(ValidationError):
        created_snapshot(**{internal_field: "x"})


def test_created_task_is_pending_with_no_completion_time() -> None:
    published = created_snapshot().model_dump(mode="json")

    assert published["status"] == "pending"
    assert published["completed_at"] is None


def test_task_identity_publishes_as_canonical_lowercase_text() -> None:
    snapshot = created_snapshot(
        task_id=UUID("20000000-0000-4000-8000-00000000000A")
    )

    published = snapshot.model_dump(mode="json")["task_id"]

    assert published == "20000000-0000-4000-8000-00000000000a"


def test_deadline_publishes_as_a_calendar_date() -> None:
    snapshot = created_snapshot(deadline=date(1, 1, 1))

    assert snapshot.model_dump(mode="json")[DEADLINE_FIELD] == "0001-01-01"


def test_observations_keep_their_line_breaks() -> None:
    supplied = "first line\nsecond line"

    snapshot = created_snapshot(observations=supplied)

    assert snapshot.model_dump(mode="json")[OBSERVATIONS_FIELD] == supplied


def test_instants_publish_with_z_and_six_fractional_digits() -> None:
    published = created_snapshot().model_dump(mode="json")

    assert published["created_at"] == "2026-09-13T12:00:00.000000Z"


def test_instants_keep_every_microsecond() -> None:
    snapshot = created_snapshot(
        created_at=datetime(2026, 9, 13, 12, 0, 0, 123456, tzinfo=UTC)
    )

    assert (
        snapshot.model_dump(mode="json")["created_at"]
        == "2026-09-13T12:00:00.123456Z"
    )


def test_an_instant_in_another_zone_publishes_in_utc() -> None:
    snapshot = created_snapshot(
        created_at=datetime(2026, 9, 13, 9, 0, tzinfo=SAO_PAULO)
    )

    assert (
        snapshot.model_dump(mode="json")["created_at"]
        == "2026-09-13T12:00:00.000000Z"
    )


def test_a_naive_instant_is_refused() -> None:
    with pytest.raises(ValidationError):
        created_snapshot(created_at=datetime(2026, 9, 13, 12, 0))


def test_unconfigured_view_reports_no_zone_and_no_product_date() -> None:
    view = ConfigurationView(
        configured=False,
        product_time_zone=None,
        server_now=RESOLVED_AT,
        product_date=None,
    )

    assert view.model_dump(mode="json") == {
        "configured": False,
        "product_time_zone": None,
        "server_now": "2026-09-13T12:00:00.000000Z",
        "product_date": None,
    }


def test_configured_view_reports_the_retained_zone_and_date() -> None:
    view = ConfigurationView(
        configured=True,
        product_time_zone="America/Sao_Paulo",
        server_now=RESOLVED_AT,
        product_date=date(2026, 9, 13),
    )

    assert view.model_dump(mode="json") == {
        "configured": True,
        "product_time_zone": "America/Sao_Paulo",
        "server_now": "2026-09-13T12:00:00.000000Z",
        "product_date": "2026-09-13",
    }


def test_an_empty_collection_publishes_an_empty_items_array() -> None:
    view = TaskListView(
        items=(),
        product_time_zone="America/Sao_Paulo",
        server_now=RESOLVED_AT,
        product_date=date(2026, 9, 13),
    )

    assert view.model_dump(mode="json")["items"] == []


def test_a_task_list_carries_its_items_and_time_context() -> None:
    view = TaskListView(
        items=(created_snapshot(),),
        product_time_zone="America/Sao_Paulo",
        server_now=RESOLVED_AT,
        product_date=date(2026, 9, 13),
    )

    published = view.model_dump(mode="json")

    assert published["items"] == [DESIGN_EXAMPLE_RESULT["task"]]
    assert published["product_time_zone"] == "America/Sao_Paulo"
    assert published["server_now"] == "2026-09-13T12:00:00.000000Z"
    assert published["product_date"] == "2026-09-13"


def test_a_successful_result_carries_its_task_and_no_error() -> None:
    result = created_result()

    assert result.task is not None
    assert result.error is None
    assert result.outcome == "succeeded"


def test_a_rejected_result_carries_its_error_and_no_task() -> None:
    result = OperationResult(
        operation_id=OPERATION_ID,
        outcome="rejected",
        original_http_status=422,
        task=None,
        error=OperationError(code=ErrorCode.TASK_VALIDATION_FAILED),
        resolved_at=RESOLVED_AT,
    )

    assert result.task is None
    assert result.error is not None
    assert result.outcome == "rejected"


def test_a_result_carrying_both_a_task_and_an_error_is_refused() -> None:
    with pytest.raises(ValidationError):
        OperationResult(
            operation_id=OPERATION_ID,
            outcome="succeeded",
            original_http_status=201,
            task=created_snapshot(),
            error=OperationError(code=ErrorCode.TASK_VALIDATION_FAILED),
            resolved_at=RESOLVED_AT,
        )


def test_a_result_carrying_neither_a_task_nor_an_error_is_refused() -> None:
    with pytest.raises(ValidationError):
        OperationResult(
            operation_id=OPERATION_ID,
            outcome="rejected",
            original_http_status=409,
            task=None,
            error=None,
            resolved_at=RESOLVED_AT,
        )


def test_a_non_field_error_publishes_an_empty_fields_array() -> None:
    error = OperationError(code=ErrorCode.TASK_NOT_FOUND)

    assert error.model_dump(mode="json") == {
        "code": "TASK_NOT_FOUND",
        "fields": [],
        "conflicting_task_id": None,
    }


def test_a_field_error_publishes_field_and_code_pairs() -> None:
    error = OperationError(
        code=ErrorCode.TASK_VALIDATION_FAILED,
        fields=(
            ValidationIssue(
                field=TITLE_FIELD, code=FieldErrorCode.TITLE_REQUIRED
            ),
            ValidationIssue(
                field=DEADLINE_FIELD, code=FieldErrorCode.INVALID_DEADLINE
            ),
        ),
    )

    assert error.model_dump(mode="json")["fields"] == [
        {"field": "title", "code": "TITLE_REQUIRED"},
        {"field": "deadline", "code": "INVALID_DEADLINE"},
    ]


def test_a_uniqueness_rejection_identifies_the_conflicting_task() -> None:
    error = OperationError(
        code=ErrorCode.TASK_UNIQUENESS_CONFLICT,
        conflicting_task_id=CONFLICTING_TASK_ID,
    )

    assert error.model_dump(mode="json") == {
        "code": "TASK_UNIQUENESS_CONFLICT",
        "fields": [],
        "conflicting_task_id": "20000000-0000-4000-8000-000000000002",
    }


def test_a_stored_uniqueness_rejection_reads_back_unchanged() -> None:
    stored = OperationResult(
        operation_id=OPERATION_ID,
        outcome="rejected",
        original_http_status=409,
        task=None,
        error=OperationError(
            code=ErrorCode.TASK_UNIQUENESS_CONFLICT,
            conflicting_task_id=CONFLICTING_TASK_ID,
        ),
        resolved_at=RESOLVED_AT,
    )

    read_back = OperationResult.model_validate_json(stored.model_dump_json())

    assert read_back == stored
    assert read_back.original_http_status == 409
    assert read_back.outcome == "rejected"


def test_a_stored_creation_result_reads_back_unchanged() -> None:
    stored = created_result()

    read_back = OperationResult.model_validate_json(stored.model_dump_json())

    assert read_back == stored
    assert read_back.original_http_status == 201


def test_a_protocol_error_publishes_exactly_its_contract_fields() -> None:
    error = ProtocolError(
        request_id=REQUEST_ID,
        error=ProtocolErrorDetail(code=ErrorCode.INVALID_OPERATION_ENVELOPE),
    )

    assert error.model_dump(mode="json") == {
        "request_id": "30000000-0000-4000-8000-000000000001",
        "error": {"code": "INVALID_OPERATION_ENVELOPE", "fields": []},
    }


def test_a_protocol_error_omits_an_unsupplied_operation_identity() -> None:
    error = ProtocolError(
        request_id=REQUEST_ID,
        error=ProtocolErrorDetail(code=ErrorCode.INVALID_OPERATION_ENVELOPE),
    )

    assert OPERATION_ID_FIELD not in json.loads(error.model_dump_json())


def test_a_protocol_error_carries_a_usable_operation_identity() -> None:
    error = ProtocolError(
        request_id=REQUEST_ID,
        error=ProtocolErrorDetail(code=ErrorCode.OPERATION_ID_REUSED),
        operation_id=OPERATION_ID,
    )

    published = json.loads(error.model_dump_json())

    assert published[OPERATION_ID_FIELD] == str(OPERATION_ID)


def test_a_protocol_error_never_carries_a_terminal_outcome() -> None:
    error = ProtocolError(
        request_id=REQUEST_ID,
        error=ProtocolErrorDetail(code=ErrorCode.STORAGE_UNAVAILABLE),
    )

    published = error.model_dump(mode="json")

    assert "outcome" not in published
    assert "task" not in published
    assert "outcome" not in ProtocolError.model_fields


def test_a_protocol_error_request_id_is_nonempty_canonical_text() -> None:
    error = ProtocolError(
        request_id=REQUEST_ID,
        error=ProtocolErrorDetail(code=ErrorCode.INTERNAL_ERROR),
    )

    published = error.model_dump(mode="json")["request_id"]

    assert published == "30000000-0000-4000-8000-000000000001"
    assert published != ""


def test_the_design_example_creation_result_serializes_field_for_field() -> (
    None
):
    assert created_result().model_dump(mode="json") == DESIGN_EXAMPLE_RESULT
    assert json.loads(created_result().model_dump_json()) == (
        DESIGN_EXAMPLE_RESULT
    )


def test_stable_operation_and_protocol_error_codes() -> None:
    assert {code.value for code in ErrorCode} == {
        "TASK_VALIDATION_FAILED",
        "TASK_UNIQUENESS_CONFLICT",
        "TASK_NOT_FOUND",
        "TASK_STATE_INCOMPATIBLE",
        "OPERATION_ID_REUSED",
        "INVALID_OPERATION_ENVELOPE",
        "OPERATION_RESULT_UNKNOWN",
        "PRODUCT_TIME_ZONE_REQUIRED",
        "PRODUCT_TIME_ZONE_FIXED",
        "INVALID_TIME_ZONE",
        "STORAGE_UNAVAILABLE",
        "INTERNAL_ERROR",
    }
