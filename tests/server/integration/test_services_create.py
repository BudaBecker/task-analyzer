"""Integration tests for the task creation command.

Covers PCE-01 through PCE-10, PCE-28, PCE-37, PCE-48, PCE-51, PCE-52;
REQ-007, REQ-008, REQ-010, REQ-028.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from helpers import FixedClock, configured_settings

from task_analyzer_server import schema, services, storage
from task_analyzer_server.contracts import (
    DEADLINE_FIELD,
    OBSERVATIONS_FIELD,
    TITLE_FIELD,
    ErrorCode,
    FieldErrorCode,
    OperationRequest,
    OperationResult,
    TaskSnapshot,
    ValidationIssue,
)
from task_analyzer_server.domain import title_key
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"
SERVER_NOW = datetime(2026, 9, 14, 2, 30, 0, 123456, tzinfo=UTC)

CREATE_TARGET = "/v1/tasks"
TITLE = "Read notes"

COMBINING_ACUTE = chr(0x0301)
ZERO_WIDTH_JOINER = chr(0x200D)

COMBINING_E = "e" + COMBINING_ACUTE

JOINED_FAMILY = ZERO_WIDTH_JOINER.join(
    ("\U0001f468", "\U0001f469", "\U0001f467", "\U0001f466")
)

TOO_LONG_TITLE = ValidationIssue(
    field=TITLE_FIELD, code=FieldErrorCode.TITLE_TOO_LONG
)
REQUIRED_TITLE = ValidationIssue(
    field=TITLE_FIELD, code=FieldErrorCode.TITLE_REQUIRED
)
TOO_LONG_OBSERVATIONS = ValidationIssue(
    field=OBSERVATIONS_FIELD, code=FieldErrorCode.OBSERVATIONS_TOO_LONG
)
INVALID_DEADLINE = ValidationIssue(
    field=DEADLINE_FIELD, code=FieldErrorCode.INVALID_DEADLINE
)


@pytest.fixture
def settings(tmp_path: Path) -> ServerSettings:
    return configured_settings(tmp_path, FixedClock(SERVER_NOW), PRODUCT_ZONE)


def creation_request(
    title: str = TITLE,
    observations: str | None = None,
    deadline: str | None = None,
    operation_id: UUID | None = None,
) -> OperationRequest:
    return OperationRequest(
        operation_id=uuid4() if operation_id is None else operation_id,
        method="POST",
        target=CREATE_TARGET,
        payload={
            "title": title,
            "observations": observations,
            "deadline": deadline,
        },
    )


def create(
    settings: ServerSettings,
    title: str = TITLE,
    observations: str | None = None,
    deadline: str | None = None,
) -> OperationResult:
    return services.create_task(
        settings,
        FixedClock(SERVER_NOW),
        creation_request(title, observations, deadline),
    )


def stored_tasks(settings: ServerSettings) -> tuple[TaskSnapshot, ...]:
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        return storage.read_tasks(connection)


def test_a_title_only_creation_produces_a_pending_task(
    settings: ServerSettings,
) -> None:
    result = create(settings)

    assert result.outcome == "succeeded"
    assert result.original_http_status == 201
    assert result.task is not None
    assert result.task.title == TITLE
    assert result.task.observations is None
    assert result.task.deadline is None
    assert result.task.status == "pending"
    assert result.task.completed_at is None


def test_optional_values_persist_exactly_as_supplied(
    settings: ServerSettings,
) -> None:
    create(settings, observations="Bring the folder", deadline="2026-09-14")

    stored = stored_tasks(settings)
    assert len(stored) == 1
    assert stored[0].observations == "Bring the folder"
    assert stored[0].deadline == date(2026, 9, 14)


def test_line_breaks_in_observations_are_retained(
    settings: ServerSettings,
) -> None:
    observations = "First line\nSecond line\n\nFourth line"

    create(settings, observations=observations)

    assert stored_tasks(settings)[0].observations == observations


def test_a_past_deadline_is_accepted(
    settings: ServerSettings,
) -> None:
    result = create(settings, deadline="2020-01-31")

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].deadline == date(2020, 1, 31)


def test_the_earliest_supported_deadline_is_accepted(
    settings: ServerSettings,
) -> None:
    result = create(settings, deadline="0001-01-01")

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].deadline == date(1, 1, 1)


def test_the_latest_supported_deadline_is_accepted(
    settings: ServerSettings,
) -> None:
    result = create(settings, deadline="9999-12-30")

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].deadline == date(9999, 12, 30)


def test_a_deadline_past_the_supported_range_is_rejected(
    settings: ServerSettings,
) -> None:
    result = create(settings, deadline="9999-12-31")

    assert result.outcome == "rejected"
    assert result.original_http_status == 422
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_VALIDATION_FAILED
    assert result.error.fields == (INVALID_DEADLINE,)
    assert stored_tasks(settings) == ()


def test_an_invalid_calendar_date_is_rejected(
    settings: ServerSettings,
) -> None:
    result = create(settings, deadline="2026-02-30")

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (INVALID_DEADLINE,)
    assert stored_tasks(settings) == ()


def test_an_empty_title_is_rejected(
    settings: ServerSettings,
) -> None:
    result = create(settings, title="")

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (REQUIRED_TITLE,)
    assert stored_tasks(settings) == ()


def test_a_whitespace_only_title_is_rejected(
    settings: ServerSettings,
) -> None:
    result = create(settings, title="   ")

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (REQUIRED_TITLE,)
    assert stored_tasks(settings) == ()


def test_a_title_of_two_hundred_characters_is_accepted(
    settings: ServerSettings,
) -> None:
    result = create(settings, title="a" * 200)

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].title == "a" * 200


def test_a_title_of_two_hundred_and_one_characters_is_rejected(
    settings: ServerSettings,
) -> None:
    result = create(settings, title="a" * 201)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_TITLE,)
    assert stored_tasks(settings) == ()


def test_a_title_is_measured_after_trimming_edge_spaces(
    settings: ServerSettings,
) -> None:
    result = create(settings, title="  " + "a" * 200 + "  ")

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].title == "  " + "a" * 200 + "  "


def test_two_hundred_combined_characters_are_accepted(
    settings: ServerSettings,
) -> None:
    result = create(settings, title=COMBINING_E * 200)

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].title == COMBINING_E * 200


def test_two_hundred_and_one_combined_characters_are_rejected(
    settings: ServerSettings,
) -> None:
    result = create(settings, title=COMBINING_E * 201)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_TITLE,)
    assert stored_tasks(settings) == ()


def test_two_hundred_joined_emoji_are_accepted(
    settings: ServerSettings,
) -> None:
    result = create(settings, title=JOINED_FAMILY * 200)

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].title == JOINED_FAMILY * 200


def test_two_hundred_and_one_joined_emoji_are_rejected(
    settings: ServerSettings,
) -> None:
    result = create(settings, title=JOINED_FAMILY * 201)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_TITLE,)
    assert stored_tasks(settings) == ()


def test_five_thousand_observation_characters_are_accepted(
    settings: ServerSettings,
) -> None:
    result = create(settings, observations="a" * 5000)

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].observations == "a" * 5000


def test_five_thousand_and_one_observation_characters_are_rejected(
    settings: ServerSettings,
) -> None:
    result = create(settings, observations="a" * 5001)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_OBSERVATIONS,)
    assert stored_tasks(settings) == ()


def test_five_thousand_combined_observation_characters_are_accepted(
    settings: ServerSettings,
) -> None:
    result = create(settings, observations=COMBINING_E * 5000)

    assert result.outcome == "succeeded"
    assert stored_tasks(settings)[0].observations == COMBINING_E * 5000


def test_five_thousand_and_one_combined_characters_are_rejected(
    settings: ServerSettings,
) -> None:
    result = create(settings, observations=COMBINING_E * 5001)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_OBSERVATIONS,)
    assert stored_tasks(settings) == ()


def test_an_unexpected_field_is_rejected(
    settings: ServerSettings,
) -> None:
    request = OperationRequest(
        operation_id=uuid4(),
        method="POST",
        target=CREATE_TARGET,
        payload={"title": TITLE, "status": "completed"},
    )

    result = services.create_task(settings, FixedClock(SERVER_NOW), request)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (
        ValidationIssue(field="status", code=FieldErrorCode.UNEXPECTED_FIELD),
    )
    assert stored_tasks(settings) == ()


def test_the_creation_instant_comes_from_the_server_clock(
    settings: ServerSettings,
) -> None:
    result = create(settings)

    assert result.task is not None
    assert result.task.created_at == SERVER_NOW
    assert stored_tasks(settings)[0].created_at == SERVER_NOW


def test_the_task_receives_a_server_generated_identity(
    settings: ServerSettings,
) -> None:
    first = create(settings, title="Read notes")
    second = create(settings, title="Read other notes")

    assert first.task is not None
    assert second.task is not None
    assert first.task.task_id != second.task.task_id
    assert {task.task_id for task in stored_tasks(settings)} == {
        first.task.task_id,
        second.task.task_id,
    }


def test_a_rejection_retains_its_result_without_a_task(
    settings: ServerSettings,
) -> None:
    request = creation_request(title="")

    result = services.create_task(settings, FixedClock(SERVER_NOW), request)

    assert services.lookup_operation(settings, request.operation_id) == (
        result
    )
    assert stored_tasks(settings) == ()


def test_success_is_reported_only_from_committed_state(
    settings: ServerSettings,
) -> None:
    result = create(settings, observations="Bring the folder")

    assert result.task is not None
    assert stored_tasks(settings) == (result.task,)
    assert services.lookup_operation(settings, result.operation_id) == (result)


def test_a_repeated_creation_creates_no_second_task(
    settings: ServerSettings,
) -> None:
    request = creation_request()
    original = services.create_task(settings, FixedClock(SERVER_NOW), request)

    repeated = services.create_task(settings, FixedClock(SERVER_NOW), request)

    assert repeated == original
    assert len(stored_tasks(settings)) == 1


def test_the_stored_comparison_key_is_the_central_derivation(
    settings: ServerSettings,
) -> None:
    submitted = " READ  NOTES "

    create(settings, title=submitted)

    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        row = connection.execute(
            "SELECT title, title_key FROM tasks"
        ).fetchone()

    assert row[0] == submitted
    assert row[1] == title_key(submitted)


def test_creation_is_refused_before_the_product_zone_is_fixed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unconfigured.sqlite3"
    schema.initialize_database(path)
    unconfigured = ServerSettings(
        database_path=path,
        log_level="INFO",
        db_busy_timeout_ms=BUSY_TIMEOUT_MS,
    )
    request = creation_request()

    with pytest.raises(services.ProtocolRefusalError) as refusal:
        services.create_task(unconfigured, FixedClock(SERVER_NOW), request)

    assert refusal.value.code == ErrorCode.PRODUCT_TIME_ZONE_REQUIRED
    assert services.lookup_operation(unconfigured, request.operation_id) is (
        None
    )
    assert stored_tasks(unconfigured) == ()
