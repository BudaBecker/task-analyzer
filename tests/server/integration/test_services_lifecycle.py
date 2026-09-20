"""Integration tests for the task lifecycle and deletion commands.

Covers TLD-01 through TLD-27, TLD-30 and TLD-32; REQ-008, REQ-009,
REQ-025, REQ-028, REQ-029, REQ-030, REQ-031.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from helpers import FixedClock, configured_settings

from task_analyzer_server import services, storage
from task_analyzer_server.clock import Clock
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
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"
CREATED_AT = datetime(2026, 9, 14, 2, 30, 0, 123456, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 9, 18, 11, 45, 0, 500000, tzinfo=UTC)
LATER_AT = datetime(2026, 9, 20, 9, 15, 0, 987654, tzinfo=UTC)

TITLE = "Read notes"
EQUIVALENT_TITLE = " READ  NOTES "
OTHER_TITLE = "Review the draft"
DEADLINE = "2026-09-14"
OTHER_DEADLINE = "2026-09-20"

OBSERVATIONS = "first note\nsecond note"
COMBINING_ACUTE = chr(0x0301)
COMBINING_E = "e" + COMBINING_ACUTE

TOO_LONG_OBSERVATIONS = ValidationIssue(
    field=OBSERVATIONS_FIELD, code=FieldErrorCode.OBSERVATIONS_TOO_LONG
)
INVALID_OBSERVATIONS = ValidationIssue(
    field=OBSERVATIONS_FIELD, code=FieldErrorCode.INVALID_FIELD_TYPE
)
UNEXPECTED_TITLE = ValidationIssue(
    field=TITLE_FIELD, code=FieldErrorCode.UNEXPECTED_FIELD
)
UNEXPECTED_DEADLINE = ValidationIssue(
    field=DEADLINE_FIELD, code=FieldErrorCode.UNEXPECTED_FIELD
)

READ_STORED_COLUMNS = (
    "SELECT title, observations, deadline_date, status, created_at_us,"
    " latest_completed_at_us, is_deleted FROM tasks WHERE task_id = ?"
)
IS_DELETED_COLUMN = 6

# One lifecycle attempt as these tests drive it, and the same command as
# the service publishes it.
Attempt = Callable[[ServerSettings, UUID, datetime, UUID], OperationResult]
Command = Callable[
    [ServerSettings, Clock, OperationRequest, UUID], OperationResult
]
RequestBuilder = Callable[[UUID], OperationRequest]


@pytest.fixture
def settings(tmp_path: Path) -> ServerSettings:
    return configured_settings(tmp_path, FixedClock(CREATED_AT), PRODUCT_ZONE)


def create(
    settings: ServerSettings,
    title: str = TITLE,
    observations: str | None = None,
    deadline: str | None = None,
) -> UUID:
    result = services.create_task(
        settings,
        FixedClock(CREATED_AT),
        OperationRequest(
            operation_id=uuid4(),
            method="POST",
            target="/v1/tasks",
            payload={
                "title": title,
                "observations": observations,
                "deadline": deadline,
            },
        ),
    )
    assert result.task is not None
    return result.task.task_id


def creation_outcome(
    settings: ServerSettings,
    title: str = TITLE,
    deadline: str | None = None,
) -> OperationResult:
    return services.create_task(
        settings,
        FixedClock(LATER_AT),
        OperationRequest(
            operation_id=uuid4(),
            method="POST",
            target="/v1/tasks",
            payload={"title": title, "deadline": deadline},
        ),
    )


def completion_request(
    task_id: UUID, operation_id: UUID | None = None
) -> OperationRequest:
    return OperationRequest(
        operation_id=uuid4() if operation_id is None else operation_id,
        method="POST",
        target=f"/v1/tasks/{task_id}/completion",
        payload={},
    )


def reopening_request(
    task_id: UUID, operation_id: UUID | None = None
) -> OperationRequest:
    return OperationRequest(
        operation_id=uuid4() if operation_id is None else operation_id,
        method="POST",
        target=f"/v1/tasks/{task_id}/reopening",
        payload={},
    )


def deletion_request(
    task_id: UUID, operation_id: UUID | None = None
) -> OperationRequest:
    return OperationRequest(
        operation_id=uuid4() if operation_id is None else operation_id,
        method="DELETE",
        target=f"/v1/tasks/{task_id}",
        payload={},
    )


def observations_request(
    task_id: UUID,
    payload: object,
    operation_id: UUID | None = None,
) -> OperationRequest:
    return OperationRequest(
        operation_id=uuid4() if operation_id is None else operation_id,
        method="PUT",
        target=f"/v1/tasks/{task_id}/observations",
        payload=payload,
    )


def complete(
    settings: ServerSettings,
    task_id: UUID,
    instant: datetime = COMPLETED_AT,
    operation_id: UUID | None = None,
) -> OperationResult:
    return services.complete_task(
        settings,
        FixedClock(instant),
        completion_request(task_id, operation_id),
        task_id,
    )


def edit_observations(
    settings: ServerSettings,
    task_id: UUID,
    payload: object,
    instant: datetime = LATER_AT,
    operation_id: UUID | None = None,
) -> OperationResult:
    return services.edit_completed_observations(
        settings,
        FixedClock(instant),
        observations_request(task_id, payload, operation_id),
        task_id,
    )


def reopen(
    settings: ServerSettings,
    task_id: UUID,
    instant: datetime = LATER_AT,
    operation_id: UUID | None = None,
) -> OperationResult:
    return services.reopen_task(
        settings,
        FixedClock(instant),
        reopening_request(task_id, operation_id),
        task_id,
    )


def delete(
    settings: ServerSettings,
    task_id: UUID,
    instant: datetime = LATER_AT,
    operation_id: UUID | None = None,
) -> OperationResult:
    return services.delete_task(
        settings,
        FixedClock(instant),
        deletion_request(task_id, operation_id),
        task_id,
    )


def completed(
    settings: ServerSettings,
    title: str = TITLE,
    observations: str | None = None,
    deadline: str | None = None,
) -> UUID:
    task_id = create(settings, title, observations, deadline)
    assert complete(settings, task_id).outcome == "succeeded"
    return task_id


def stored_task(
    settings: ServerSettings, task_id: UUID
) -> TaskSnapshot | None:
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        return storage.read_task(connection, task_id)


def managed_task(settings: ServerSettings, task_id: UUID) -> TaskSnapshot:
    stored = stored_task(settings, task_id)
    assert stored is not None
    return stored


def stored_columns(
    settings: ServerSettings, task_id: UUID
) -> tuple[object, ...]:
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        row = connection.execute(
            READ_STORED_COLUMNS, (str(task_id),)
        ).fetchone()
    assert row is not None
    return tuple(row)


def managed_tasks(settings: ServerSettings) -> tuple[TaskSnapshot, ...]:
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        return storage.read_tasks(connection)


def rejection_code(result: OperationResult) -> ErrorCode:
    assert result.outcome == "rejected"
    assert result.error is not None
    return result.error.code


def test_completing_a_pending_task_stores_the_completed_status(
    settings: ServerSettings,
) -> None:
    task_id = create(settings)

    result = complete(settings, task_id)

    assert result.outcome == "succeeded"
    assert result.original_http_status == 200
    assert managed_task(settings, task_id).status == "completed"


def test_completion_records_the_server_instant_it_was_applied(
    settings: ServerSettings,
) -> None:
    task_id = create(settings)

    result = complete(settings, task_id)

    assert result.task is not None
    assert result.task.completed_at == COMPLETED_AT
    assert managed_task(settings, task_id).completed_at == COMPLETED_AT


def test_completion_preserves_the_whole_identity_and_content(
    settings: ServerSettings,
) -> None:
    task_id = create(settings, observations=OBSERVATIONS, deadline=DEADLINE)
    before = managed_task(settings, task_id)

    result = complete(settings, task_id)

    assert result.task is not None
    assert result.task.task_id == task_id
    assert result.task.title == before.title
    assert result.task.observations == OBSERVATIONS
    assert result.task.deadline == date.fromisoformat(DEADLINE)
    assert result.task.created_at == CREATED_AT


def test_completing_an_undated_task_frees_its_title(
    settings: ServerSettings,
) -> None:
    completed(settings)

    reused = creation_outcome(settings, title=EQUIVALENT_TITLE)

    assert reused.outcome == "succeeded"


def test_a_completed_dated_task_still_blocks_its_deadline_date(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings, deadline=DEADLINE)

    reused = creation_outcome(
        settings, title=EQUIVALENT_TITLE, deadline=DEADLINE
    )

    assert rejection_code(reused) == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert reused.error is not None
    assert reused.error.conflicting_task_id == task_id


def test_a_new_completion_of_a_completed_task_is_incompatible(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings)
    before = stored_columns(settings, task_id)

    repeated = complete(settings, task_id, instant=LATER_AT)

    assert rejection_code(repeated) == ErrorCode.TASK_STATE_INCOMPATIBLE
    assert repeated.original_http_status == 409
    assert stored_columns(settings, task_id) == before


def test_completing_an_absent_task_creates_nothing(
    settings: ServerSettings,
) -> None:
    absent = uuid4()

    result = complete(settings, absent)

    assert rejection_code(result) == ErrorCode.TASK_NOT_FOUND
    assert result.original_http_status == 404
    assert managed_tasks(settings) == ()


def test_valid_observations_reach_a_completed_task(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings)

    result = edit_observations(
        settings, task_id, {"observations": OBSERVATIONS}
    )

    assert result.outcome == "succeeded"
    stored = managed_task(settings, task_id)
    assert stored.observations == OBSERVATIONS
    assert stored.status == "completed"


def test_clearing_completed_observations_persists_their_absence(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings, observations=OBSERVATIONS)

    edit_observations(settings, task_id, {"observations": None})

    assert managed_task(settings, task_id).observations is None


@pytest.mark.parametrize(
    "submitted",
    [OBSERVATIONS, "a" * 5000, COMBINING_E * 5000],
    ids=["multiline", "boundary", "clusters"],
)
def test_accepted_completed_observations_are_retained_exactly(
    settings: ServerSettings, submitted: str
) -> None:
    task_id = completed(settings)

    result = edit_observations(settings, task_id, {"observations": submitted})

    assert result.outcome == "succeeded"
    assert managed_task(settings, task_id).observations == submitted


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"observations": "a" * 5001}, (TOO_LONG_OBSERVATIONS,)),
        ({"observations": COMBINING_E * 5001}, (TOO_LONG_OBSERVATIONS,)),
        ({"observations": 5}, (INVALID_OBSERVATIONS,)),
        ({}, (INVALID_OBSERVATIONS,)),
    ],
    ids=["too_long", "too_many_clusters", "wrong_type", "missing"],
)
def test_a_refused_observation_payload_leaves_the_task_alone(
    settings: ServerSettings,
    payload: object,
    expected: tuple[ValidationIssue, ...],
) -> None:
    task_id = completed(settings, observations=OBSERVATIONS)
    before = stored_columns(settings, task_id)

    result = edit_observations(settings, task_id, payload)

    assert rejection_code(result) == ErrorCode.TASK_VALIDATION_FAILED
    assert result.original_http_status == 422
    assert result.error is not None
    assert result.error.fields == expected
    assert stored_columns(settings, task_id) == before


def test_editing_completed_observations_preserves_everything_else(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings, deadline=DEADLINE)
    before = managed_task(settings, task_id)

    result = edit_observations(
        settings, task_id, {"observations": OBSERVATIONS}
    )

    assert result.task is not None
    assert result.task.task_id == task_id
    assert result.task.title == before.title
    assert result.task.deadline == before.deadline
    assert result.task.status == "completed"
    assert result.task.created_at == CREATED_AT
    assert result.task.completed_at == COMPLETED_AT


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"observations": OBSERVATIONS, "title": OTHER_TITLE},
            (UNEXPECTED_TITLE,),
        ),
        (
            {"observations": OBSERVATIONS, "deadline": OTHER_DEADLINE},
            (UNEXPECTED_DEADLINE,),
        ),
    ],
    ids=["title", "deadline"],
)
def test_the_observation_command_changes_no_other_field(
    settings: ServerSettings,
    payload: object,
    expected: tuple[ValidationIssue, ...],
) -> None:
    task_id = completed(settings)
    before = stored_columns(settings, task_id)

    result = edit_observations(settings, task_id, payload)

    assert rejection_code(result) == ErrorCode.TASK_VALIDATION_FAILED
    assert result.error is not None
    assert result.error.fields == expected
    assert stored_columns(settings, task_id) == before


def test_a_completed_task_is_not_retitled_without_reopening(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings)
    before = stored_columns(settings, task_id)

    result = services.edit_task(
        settings,
        FixedClock(LATER_AT),
        OperationRequest(
            operation_id=uuid4(),
            method="PUT",
            target=f"/v1/tasks/{task_id}",
            payload={"title": OTHER_TITLE, "deadline": OTHER_DEADLINE},
        ),
        task_id,
    )

    assert rejection_code(result) == ErrorCode.TASK_STATE_INCOMPATIBLE
    assert stored_columns(settings, task_id) == before


def test_editing_the_observations_of_a_pending_task_is_incompatible(
    settings: ServerSettings,
) -> None:
    task_id = create(settings, observations=OBSERVATIONS)
    before = stored_columns(settings, task_id)

    result = edit_observations(settings, task_id, {"observations": "new"})

    assert rejection_code(result) == ErrorCode.TASK_STATE_INCOMPATIBLE
    assert stored_columns(settings, task_id) == before


def test_editing_the_observations_of_an_absent_task_creates_nothing(
    settings: ServerSettings,
) -> None:
    result = edit_observations(
        settings, uuid4(), {"observations": OBSERVATIONS}
    )

    assert rejection_code(result) == ErrorCode.TASK_NOT_FOUND
    assert managed_tasks(settings) == ()


def test_reopening_a_completed_task_restores_the_pending_status(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings)

    result = reopen(settings, task_id)

    assert result.outcome == "succeeded"
    assert result.original_http_status == 200
    assert managed_task(settings, task_id).status == "pending"


def test_reopening_clears_the_completion_time_and_keeps_the_rest(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings, observations=OBSERVATIONS, deadline=DEADLINE)

    result = reopen(settings, task_id)

    assert result.task is not None
    assert result.task.completed_at is None
    assert result.task.task_id == task_id
    assert result.task.title == TITLE
    assert result.task.observations == OBSERVATIONS
    assert result.task.deadline == date.fromisoformat(DEADLINE)
    assert result.task.created_at == CREATED_AT
    assert managed_task(settings, task_id).completed_at is None


def test_reopening_does_not_compare_a_task_against_itself(
    settings: ServerSettings,
) -> None:
    # A dated task belongs to its own uniqueness population whatever its
    # status, so the check would find the target itself unless the
    # reopening excluded it.
    task_id = completed(settings, deadline=DEADLINE)

    result = reopen(settings, task_id)

    assert result.outcome == "succeeded"
    assert managed_task(settings, task_id).status == "pending"


def test_reopening_an_undated_task_is_refused_by_an_equivalent_pending(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings)
    conflicting = create(settings, title=EQUIVALENT_TITLE)

    result = reopen(settings, task_id)

    assert rejection_code(result) == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert result.original_http_status == 409
    assert result.error is not None
    assert result.error.conflicting_task_id == conflicting


def test_a_refused_reopening_leaves_both_tasks_untouched(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings)
    conflicting = create(settings, title=EQUIVALENT_TITLE)
    before = stored_columns(settings, task_id)
    conflicting_before = stored_columns(settings, conflicting)

    reopen(settings, task_id)

    assert stored_columns(settings, task_id) == before
    assert stored_columns(settings, conflicting) == conflicting_before


def test_reopening_a_dated_task_keeps_its_deadline_date_reserved(
    settings: ServerSettings,
) -> None:
    # A dated title key is unique across both statuses, so no dated
    # collision can survive to be found when the task reopens. The rule
    # it would report still holds after the transition.
    task_id = completed(settings, deadline=DEADLINE)

    result = reopen(settings, task_id)

    assert result.outcome == "succeeded"
    blocked = creation_outcome(
        settings, title=EQUIVALENT_TITLE, deadline=DEADLINE
    )
    assert rejection_code(blocked) == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert blocked.error is not None
    assert blocked.error.conflicting_task_id == task_id


def test_reopening_succeeds_once_the_conflicting_task_is_deleted(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings)
    conflicting = create(settings, title=EQUIVALENT_TITLE)
    refused = reopen(settings, task_id)

    delete(settings, conflicting)
    retried = reopen(settings, task_id)

    assert refused.outcome == "rejected"
    assert retried.outcome == "succeeded"
    assert services.lookup_operation(settings, refused.operation_id) == refused


def test_reopening_a_pending_task_is_incompatible(
    settings: ServerSettings,
) -> None:
    task_id = create(settings)
    before = stored_columns(settings, task_id)

    result = reopen(settings, task_id)

    assert rejection_code(result) == ErrorCode.TASK_STATE_INCOMPATIBLE
    assert result.original_http_status == 409
    assert stored_columns(settings, task_id) == before


def test_reopening_an_absent_task_creates_nothing(
    settings: ServerSettings,
) -> None:
    result = reopen(settings, uuid4())

    assert rejection_code(result) == ErrorCode.TASK_NOT_FOUND
    assert managed_tasks(settings) == ()


def test_completing_a_reopened_task_replaces_the_cleared_instant(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings)
    reopen(settings, task_id)

    result = complete(settings, task_id, instant=LATER_AT)

    assert result.task is not None
    assert result.task.created_at == CREATED_AT
    assert result.task.completed_at == LATER_AT


def test_deleting_a_task_removes_it_from_the_managed_collection(
    settings: ServerSettings,
) -> None:
    task_id = create(settings)

    result = delete(settings, task_id)

    assert result.outcome == "succeeded"
    assert result.original_http_status == 200
    assert managed_tasks(settings) == ()
    assert stored_task(settings, task_id) is None


def test_a_successful_deletion_reports_the_final_snapshot(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings, observations=OBSERVATIONS, deadline=DEADLINE)

    result = delete(settings, task_id)

    assert result.task is not None
    assert result.task.task_id == task_id
    assert result.task.title == TITLE
    assert result.task.observations == OBSERVATIONS
    assert result.task.status == "completed"
    assert result.task.completed_at == COMPLETED_AT


@pytest.mark.parametrize(
    "deadline", [None, DEADLINE], ids=["undated", "dated"]
)
def test_a_deleted_task_no_longer_blocks_an_equivalent_task(
    settings: ServerSettings, deadline: str | None
) -> None:
    task_id = create(settings, deadline=deadline)
    delete(settings, task_id)

    reused = creation_outcome(
        settings, title=EQUIVALENT_TITLE, deadline=deadline
    )

    assert reused.outcome == "succeeded"


@pytest.mark.parametrize(
    "attempt",
    [complete, reopen, delete],
    ids=["complete", "reopen", "delete"],
)
def test_a_deleted_task_is_never_restored_by_a_later_command(
    settings: ServerSettings, attempt: Attempt
) -> None:
    task_id = completed(settings)
    delete(settings, task_id)

    result = attempt(settings, task_id, LATER_AT, uuid4())

    assert rejection_code(result) == ErrorCode.TASK_NOT_FOUND
    assert result.original_http_status == 404
    assert managed_tasks(settings) == ()
    assert stored_columns(settings, task_id)[IS_DELETED_COLUMN] == 1


def test_editing_the_observations_of_a_deleted_task_is_refused(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings)
    delete(settings, task_id)

    result = edit_observations(
        settings, task_id, {"observations": OBSERVATIONS}
    )

    assert rejection_code(result) == ErrorCode.TASK_NOT_FOUND
    assert managed_tasks(settings) == ()


def test_deleting_an_absent_task_changes_no_persisted_state(
    settings: ServerSettings,
) -> None:
    survivor = create(settings)
    before = stored_columns(settings, survivor)

    result = delete(settings, uuid4())

    assert rejection_code(result) == ErrorCode.TASK_NOT_FOUND
    assert stored_columns(settings, survivor) == before


@pytest.mark.parametrize(
    ("command", "build"),
    [
        (services.complete_task, completion_request),
        (services.reopen_task, reopening_request),
        (services.delete_task, deletion_request),
    ],
    ids=["complete", "reopen", "delete"],
)
def test_a_lifecycle_command_carries_no_fields(
    settings: ServerSettings, command: Command, build: RequestBuilder
) -> None:
    task_id = create(settings)
    before = stored_columns(settings, task_id)
    submitted = replace(build(task_id), payload={"title": OTHER_TITLE})

    result = command(settings, FixedClock(LATER_AT), submitted, task_id)

    assert rejection_code(result) == ErrorCode.TASK_VALIDATION_FAILED
    assert result.error is not None
    assert result.error.fields == (UNEXPECTED_TITLE,)
    assert stored_columns(settings, task_id) == before


def test_a_repeated_completion_attempt_returns_its_original_result(
    settings: ServerSettings,
) -> None:
    task_id = create(settings)
    identity = uuid4()
    original = complete(settings, task_id, operation_id=identity)

    repeated = complete(
        settings, task_id, instant=LATER_AT, operation_id=identity
    )

    assert repeated == original
    assert managed_task(settings, task_id).completed_at == COMPLETED_AT


@pytest.mark.parametrize("attempt", [reopen, delete], ids=["reopen", "delete"])
def test_a_repeated_lifecycle_attempt_applies_its_change_once(
    settings: ServerSettings, attempt: Attempt
) -> None:
    task_id = completed(settings)
    identity = uuid4()
    original = attempt(settings, task_id, LATER_AT, identity)
    before = stored_columns(settings, task_id)

    repeated = attempt(settings, task_id, LATER_AT, identity)

    assert repeated == original
    assert stored_columns(settings, task_id) == before


def test_a_repeated_observation_edit_returns_its_original_result(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings)
    identity = uuid4()
    original = edit_observations(
        settings, task_id, {"observations": OBSERVATIONS}, LATER_AT, identity
    )

    repeated = edit_observations(
        settings, task_id, {"observations": OBSERVATIONS}, LATER_AT, identity
    )

    assert repeated == original
    assert managed_task(settings, task_id).observations == OBSERVATIONS


def test_a_reused_identity_against_another_command_is_refused(
    settings: ServerSettings,
) -> None:
    task_id = create(settings)
    identity = uuid4()
    original = complete(settings, task_id, operation_id=identity)

    with pytest.raises(services.ProtocolRefusalError) as refusal:
        reopen(settings, task_id, operation_id=identity)

    assert refusal.value.code == ErrorCode.OPERATION_ID_REUSED
    assert services.lookup_operation(settings, identity) == original
    assert managed_task(settings, task_id).status == "completed"


def test_a_reused_identity_against_another_task_is_refused(
    settings: ServerSettings,
) -> None:
    first = create(settings)
    second = create(settings, title=OTHER_TITLE)
    identity = uuid4()
    original = complete(settings, first, operation_id=identity)

    with pytest.raises(services.ProtocolRefusalError) as refusal:
        complete(settings, second, operation_id=identity)

    assert refusal.value.code == ErrorCode.OPERATION_ID_REUSED
    assert services.lookup_operation(settings, identity) == original
    assert managed_task(settings, second).status == "pending"


def test_a_reused_identity_against_another_body_is_refused(
    settings: ServerSettings,
) -> None:
    task_id = completed(settings)
    identity = uuid4()
    original = edit_observations(
        settings, task_id, {"observations": OBSERVATIONS}, LATER_AT, identity
    )

    with pytest.raises(services.ProtocolRefusalError) as refusal:
        edit_observations(
            settings, task_id, {"observations": None}, LATER_AT, identity
        )

    assert refusal.value.code == ErrorCode.OPERATION_ID_REUSED
    assert services.lookup_operation(settings, identity) == original
    assert managed_task(settings, task_id).observations == OBSERVATIONS


def test_the_original_result_survives_the_whole_lifecycle_of_its_task(
    settings: ServerSettings,
) -> None:
    task_id = create(settings)
    identity = uuid4()
    original = complete(settings, task_id, operation_id=identity)
    reopen(settings, task_id)
    delete(settings, task_id)

    repeated = complete(
        settings, task_id, instant=LATER_AT, operation_id=identity
    )

    assert repeated == original
    assert services.lookup_operation(settings, identity) == original
    assert managed_tasks(settings) == ()
