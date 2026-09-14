"""Unit tests for strict task-input parsing.

Covers PCE-01, PCE-10, PCE-11, PCE-16 and PCE-48; REQ-007, REQ-008.
"""

import ast
import inspect
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from task_analyzer_server import contracts
from task_analyzer_server.contracts import (
    DEADLINE_FIELD,
    OBSERVATIONS_FIELD,
    PAYLOAD_FIELD,
    TITLE_FIELD,
    FieldErrorCode,
    OperationRequest,
    TaskInput,
    TaskInputError,
    ValidationIssue,
    parse_task_input,
)


def issues_of(payload: object) -> tuple[ValidationIssue, ...]:
    with pytest.raises(TaskInputError) as failure:
        parse_task_input(payload)
    return failure.value.issues


def test_title_only_payload_is_accepted() -> None:
    parsed = parse_task_input({"title": "Read notes"})

    assert parsed.title == "Read notes"
    assert parsed.observations is None
    assert parsed.deadline is None


def test_optional_values_are_kept_exactly_as_supplied() -> None:
    parsed = parse_task_input(
        {
            "title": "Read notes",
            "observations": "Chapter 3",
            "deadline": "2026-09-14",
        }
    )

    assert parsed.observations == "Chapter 3"
    assert parsed.deadline == "2026-09-14"


def test_observation_line_breaks_are_preserved() -> None:
    supplied = "first line\nsecond line\r\nthird line"

    parsed = parse_task_input(
        {"title": "Read notes", "observations": supplied}
    )

    assert parsed.observations == supplied


def test_null_observations_clear_the_value() -> None:
    parsed = parse_task_input({"title": "Read notes", "observations": None})

    assert parsed.observations is None


def test_null_deadline_clears_the_value() -> None:
    parsed = parse_task_input({"title": "Read notes", "deadline": None})

    assert parsed.deadline is None


def test_omitted_optionals_match_explicit_nulls() -> None:
    omitted = parse_task_input({"title": "Read notes"})

    cleared = parse_task_input(
        {"title": "Read notes", "observations": None, "deadline": None}
    )

    assert omitted == cleared


def test_missing_title_is_reported_as_required() -> None:
    assert issues_of({}) == (
        ValidationIssue(field=TITLE_FIELD, code=FieldErrorCode.TITLE_REQUIRED),
    )


def test_null_title_is_rejected_as_invalid_type() -> None:
    assert issues_of({"title": None}) == (
        ValidationIssue(
            field=TITLE_FIELD, code=FieldErrorCode.INVALID_FIELD_TYPE
        ),
    )


def test_numeric_title_is_not_coerced() -> None:
    assert issues_of({"title": 42}) == (
        ValidationIssue(
            field=TITLE_FIELD, code=FieldErrorCode.INVALID_FIELD_TYPE
        ),
    )


def test_boolean_title_is_not_coerced() -> None:
    assert issues_of({"title": True}) == (
        ValidationIssue(
            field=TITLE_FIELD, code=FieldErrorCode.INVALID_FIELD_TYPE
        ),
    )


def test_numeric_observations_are_not_coerced() -> None:
    payload = {"title": "Read notes", "observations": 5}

    assert issues_of(payload) == (
        ValidationIssue(
            field=OBSERVATIONS_FIELD, code=FieldErrorCode.INVALID_FIELD_TYPE
        ),
    )


def test_numeric_deadline_is_not_coerced() -> None:
    payload = {"title": "Read notes", "deadline": 20260914}

    assert issues_of(payload) == (
        ValidationIssue(
            field=DEADLINE_FIELD, code=FieldErrorCode.INVALID_FIELD_TYPE
        ),
    )


def test_unknown_field_is_rejected() -> None:
    payload = {"title": "Read notes", "priority": "high"}

    assert issues_of(payload) == (
        ValidationIssue(
            field="priority", code=FieldErrorCode.UNEXPECTED_FIELD
        ),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "completed"),
        ("created_at", "2026-09-13T12:00:00.000000Z"),
        ("completed_at", "2026-09-13T12:00:00.000000Z"),
        ("task_id", "20000000-0000-4000-8000-000000000001"),
        ("title_key", "read notes"),
        ("is_deleted", 0),
    ],
)
def test_server_owned_field_is_rejected(field: str, value: object) -> None:
    payload = {"title": "Read notes", field: value}

    assert issues_of(payload) == (
        ValidationIssue(field=field, code=FieldErrorCode.UNEXPECTED_FIELD),
    )


def test_non_object_payload_is_rejected() -> None:
    assert issues_of(["Read notes"]) == (
        ValidationIssue(
            field=PAYLOAD_FIELD, code=FieldErrorCode.INVALID_FIELD_TYPE
        ),
    )


def test_every_rejected_field_is_reported() -> None:
    payload = {"title": 42, "observations": 5, "priority": "high"}

    assert issues_of(payload) == (
        ValidationIssue(
            field=TITLE_FIELD, code=FieldErrorCode.INVALID_FIELD_TYPE
        ),
        ValidationIssue(
            field=OBSERVATIONS_FIELD, code=FieldErrorCode.INVALID_FIELD_TYPE
        ),
        ValidationIssue(
            field="priority", code=FieldErrorCode.UNEXPECTED_FIELD
        ),
    )


def test_rejection_never_echoes_submitted_values() -> None:
    secret = "Read the confidential notes"

    with pytest.raises(TaskInputError) as failure:
        parse_task_input({"title": secret, "observations": 5})

    assert secret not in str(failure.value)
    assert failure.value.__cause__ is None
    assert failure.value.__suppress_context__ is True
    for issue in failure.value.issues:
        assert set(issue.model_dump()) == {"field", "code"}


def test_structurally_valid_payload_reaches_business_validation() -> None:
    parsed = parse_task_input({"title": "   "})

    assert parsed.title == "   "


def test_stable_field_error_codes() -> None:
    assert {code.value for code in FieldErrorCode} == {
        "TITLE_REQUIRED",
        "TITLE_TOO_LONG",
        "OBSERVATIONS_TOO_LONG",
        "INVALID_DEADLINE",
        "INVALID_FIELD_TYPE",
        "UNEXPECTED_FIELD",
    }


def test_validation_issue_is_an_immutable_value() -> None:
    issue = ValidationIssue(
        field=TITLE_FIELD, code=FieldErrorCode.TITLE_REQUIRED
    )

    assert issue == ValidationIssue(
        field=TITLE_FIELD, code=FieldErrorCode.TITLE_REQUIRED
    )
    assert len({issue, issue}) == 1
    with pytest.raises(ValidationError):
        issue.field = OBSERVATIONS_FIELD  # type: ignore[misc]


def test_task_input_is_immutable() -> None:
    parsed = parse_task_input({"title": "Read notes"})

    with pytest.raises(ValidationError):
        parsed.title = "Other"  # type: ignore[misc]


def test_operation_request_binds_its_envelope() -> None:
    operation_id = UUID("10000000-0000-4000-8000-000000000001")
    payload = {"title": "Read notes"}

    request = OperationRequest(
        operation_id=operation_id,
        method="POST",
        target="/v1/tasks",
        payload=payload,
    )

    assert request.operation_id == operation_id
    assert request.method == "POST"
    assert request.target == "/v1/tasks"
    assert request.payload == payload


def test_operation_request_is_immutable() -> None:
    request = OperationRequest(
        operation_id=UUID("10000000-0000-4000-8000-000000000001"),
        method="POST",
        target="/v1/tasks",
        payload={"title": "Read notes"},
    )

    with pytest.raises(AttributeError):
        request.method = "PUT"  # type: ignore[misc]


def test_contracts_never_import_domain_or_services() -> None:
    source = Path(str(inspect.getsourcefile(contracts))).read_text(
        encoding="utf-8"
    )
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)

    tails = {name.rsplit(".", 1)[-1] for name in imported}
    assert tails.isdisjoint({"domain", "services"})


def test_parsed_input_exposes_only_the_contract_fields() -> None:
    parsed = parse_task_input({"title": "Read notes"})

    assert set(TaskInput.model_fields) == {
        TITLE_FIELD,
        OBSERVATIONS_FIELD,
        DEADLINE_FIELD,
    }
    assert set(parsed.model_dump()) == {
        TITLE_FIELD,
        OBSERVATIONS_FIELD,
        DEADLINE_FIELD,
    }
