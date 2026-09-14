"""Integration tests for uniqueness in creation and editing.

Covers PCE-17 through PCE-27, PCE-41, PCE-42; REQ-008, REQ-029, REQ-031.
"""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from helpers import FixedClock, configured_settings

from task_analyzer_server import services, storage
from task_analyzer_server.clock import to_utc_microseconds
from task_analyzer_server.contracts import (
    ErrorCode,
    OperationRequest,
    OperationResult,
    TaskSnapshot,
)
from task_analyzer_server.domain import title_key
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000

PRODUCT_ZONE = "America/Sao_Paulo"
SERVER_NOW = datetime(2026, 9, 14, 2, 30, 0, 123456, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 9, 13, 18, 0, 0, tzinfo=UTC)

E_ACUTE = chr(0x00E9)

TITLE = "Read notes"
EQUIVALENT_TITLE = " READ  NOTES "
UPPERCASE_TITLE = "READ NOTES"
ACCENTED_TITLE = f"Review r{E_ACUTE}sum{E_ACUTE}"
PLAIN_TITLE = "Review resume"
OTHER_TITLE = "Write the report"

DEADLINE = "2026-09-14"
ANOTHER_DEADLINE = "2026-09-15"

INSERT_FIXTURE_TASK = (
    "INSERT INTO tasks ("
    " task_id, title, title_key, observations, deadline_date,"
    " status, created_at_us, latest_completed_at_us, is_deleted"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
READ_STORED_COLUMNS = (
    "SELECT title, title_key, observations, deadline_date, status,"
    " created_at_us, latest_completed_at_us, is_deleted FROM tasks"
    " WHERE task_id = ?"
)


@pytest.fixture
def settings(tmp_path: Path) -> ServerSettings:
    return configured_settings(tmp_path, FixedClock(SERVER_NOW), PRODUCT_ZONE)


def create_request(
    title: str, deadline: str | None, observations: str | None = None
) -> OperationRequest:
    return OperationRequest(
        operation_id=uuid4(),
        method="POST",
        target="/v1/tasks",
        payload={
            "title": title,
            "observations": observations,
            "deadline": deadline,
        },
    )


def edit_request(
    task_id: UUID,
    title: str,
    deadline: str | None,
    observations: str | None = None,
) -> OperationRequest:
    return OperationRequest(
        operation_id=uuid4(),
        method="PUT",
        target=f"/v1/tasks/{task_id}",
        payload={
            "title": title,
            "observations": observations,
            "deadline": deadline,
        },
    )


def create(
    settings: ServerSettings,
    title: str,
    deadline: str | None,
    observations: str | None = None,
) -> OperationResult:
    return services.create_task(
        settings,
        FixedClock(SERVER_NOW),
        create_request(title, deadline, observations),
    )


def created_id(
    settings: ServerSettings, title: str, deadline: str | None
) -> UUID:
    result = create(settings, title, deadline)
    assert result.task is not None
    return result.task.task_id


def edit(
    settings: ServerSettings,
    task_id: UUID,
    title: str,
    deadline: str | None,
    observations: str | None = None,
) -> OperationResult:
    return services.edit_task(
        settings,
        FixedClock(SERVER_NOW),
        edit_request(task_id, title, deadline, observations),
        task_id,
    )


def stored_columns(
    settings: ServerSettings, task_id: UUID
) -> tuple[object, ...]:
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        row = connection.execute(
            READ_STORED_COLUMNS, (str(task_id),)
        ).fetchone()
    return tuple(row)


def stored_tasks(settings: ServerSettings) -> tuple[TaskSnapshot, ...]:
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        return storage.read_tasks(connection)


def insert_fixture_task(
    settings: ServerSettings,
    *,
    title: str,
    deadline: str | None,
    status: str = "pending",
    is_deleted: int = 0,
) -> UUID:
    identity = uuid4()
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        with storage.write_transaction(connection):
            connection.execute(
                INSERT_FIXTURE_TASK,
                (
                    str(identity),
                    title,
                    title_key(title),
                    None,
                    deadline,
                    status,
                    to_utc_microseconds(SERVER_NOW),
                    (
                        to_utc_microseconds(COMPLETED_AT)
                        if status == "completed"
                        else None
                    ),
                    is_deleted,
                ),
            )
    return identity


def blind_first_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real: Callable[..., UUID | None] = storage.find_conflicting_task
    checks = {"count": 0}

    def missing_first(
        connection: sqlite3.Connection, **arguments: Any
    ) -> UUID | None:
        checks["count"] += 1
        if checks["count"] == 1:
            return None
        return real(connection, **arguments)

    monkeypatch.setattr(storage, "find_conflicting_task", missing_first)


def test_equivalent_titles_on_one_date_conflict_on_creation(
    settings: ServerSettings,
) -> None:
    create(settings, TITLE, DEADLINE)

    result = create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "rejected"
    assert result.original_http_status == 409
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT


def test_an_uppercase_title_conflicts_on_creation(
    settings: ServerSettings,
) -> None:
    create(settings, TITLE, DEADLINE)

    result = create(settings, UPPERCASE_TITLE, DEADLINE)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT


def test_a_creation_conflict_identifies_the_conflicting_task(
    settings: ServerSettings,
) -> None:
    existing = created_id(settings, TITLE, DEADLINE)

    result = create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert result.error is not None
    assert result.error.conflicting_task_id == existing


def test_a_creation_conflict_leaves_the_conflicting_task_unchanged(
    settings: ServerSettings,
) -> None:
    existing = created_id(settings, TITLE, DEADLINE)
    before = stored_columns(settings, existing)

    create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert stored_columns(settings, existing) == before


def test_a_creation_conflict_creates_no_task(
    settings: ServerSettings,
) -> None:
    create(settings, TITLE, DEADLINE)

    create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert len(stored_tasks(settings)) == 1


def test_a_dated_creation_conflicts_with_a_completed_task(
    settings: ServerSettings,
) -> None:
    completed = insert_fixture_task(
        settings, title=TITLE, deadline=DEADLINE, status="completed"
    )

    result = create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.conflicting_task_id == completed


def test_equivalent_titles_on_different_dates_coexist(
    settings: ServerSettings,
) -> None:
    create(settings, TITLE, DEADLINE)

    result = create(settings, EQUIVALENT_TITLE, ANOTHER_DEADLINE)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_an_undated_creation_coexists_with_a_dated_task(
    settings: ServerSettings,
) -> None:
    create(settings, TITLE, DEADLINE)

    result = create(settings, EQUIVALENT_TITLE, None)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_a_dated_creation_coexists_with_an_undated_task(
    settings: ServerSettings,
) -> None:
    create(settings, TITLE, None)

    result = create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_accented_titles_are_different_titles(
    settings: ServerSettings,
) -> None:
    create(settings, ACCENTED_TITLE, DEADLINE)

    result = create(settings, PLAIN_TITLE, DEADLINE)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_undated_pending_tasks_conflict_on_creation(
    settings: ServerSettings,
) -> None:
    existing = created_id(settings, TITLE, None)

    result = create(settings, EQUIVALENT_TITLE, None)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert result.error.conflicting_task_id == existing


def test_a_completed_undated_task_frees_its_title(
    settings: ServerSettings,
) -> None:
    insert_fixture_task(
        settings, title=TITLE, deadline=None, status="completed"
    )

    result = create(settings, EQUIVALENT_TITLE, None)

    assert result.outcome == "succeeded"


def test_a_deleted_dated_task_does_not_block_creation(
    settings: ServerSettings,
) -> None:
    insert_fixture_task(settings, title=TITLE, deadline=DEADLINE, is_deleted=1)

    result = create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "succeeded"


def test_a_deleted_undated_task_does_not_block_creation(
    settings: ServerSettings,
) -> None:
    insert_fixture_task(settings, title=TITLE, deadline=None, is_deleted=1)

    result = create(settings, EQUIVALENT_TITLE, None)

    assert result.outcome == "succeeded"


def test_a_uniqueness_rejection_is_retained_for_consultation(
    settings: ServerSettings,
) -> None:
    create(settings, TITLE, DEADLINE)
    request = create_request(EQUIVALENT_TITLE, DEADLINE)

    result = services.create_task(settings, FixedClock(SERVER_NOW), request)

    assert services.lookup_operation(settings, request.operation_id) == (
        result
    )
    assert result.outcome == "rejected"


def test_a_different_conflicting_operation_is_rejected_not_replayed(
    settings: ServerSettings,
) -> None:
    first = create_request(TITLE, DEADLINE)
    second = create_request(EQUIVALENT_TITLE, DEADLINE)

    accepted = services.create_task(settings, FixedClock(SERVER_NOW), first)
    refused = services.create_task(settings, FixedClock(SERVER_NOW), second)

    assert accepted.outcome == "succeeded"
    assert refused.outcome == "rejected"
    assert refused.operation_id == second.operation_id
    assert refused.error is not None
    assert refused.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert len(stored_tasks(settings)) == 1


def test_an_edit_into_a_dated_conflict_is_rejected(
    settings: ServerSettings,
) -> None:
    existing = created_id(settings, TITLE, DEADLINE)
    edited = created_id(settings, OTHER_TITLE, DEADLINE)

    result = edit(settings, edited, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "rejected"
    assert result.original_http_status == 409
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert result.error.conflicting_task_id == existing


def test_an_edit_conflict_leaves_both_tasks_unchanged(
    settings: ServerSettings,
) -> None:
    existing = created_id(settings, TITLE, DEADLINE)
    edited = created_id(settings, OTHER_TITLE, DEADLINE)
    existing_before = stored_columns(settings, existing)
    edited_before = stored_columns(settings, edited)

    edit(settings, edited, EQUIVALENT_TITLE, DEADLINE)

    assert stored_columns(settings, existing) == existing_before
    assert stored_columns(settings, edited) == edited_before


def test_an_edit_excludes_the_task_itself(
    settings: ServerSettings,
) -> None:
    task_id = created_id(settings, TITLE, DEADLINE)

    result = edit(settings, task_id, TITLE, DEADLINE, "Added observations")

    assert result.outcome == "succeeded"
    assert result.task is not None
    assert result.task.observations == "Added observations"


def test_an_edit_excludes_itself_under_an_equivalent_title(
    settings: ServerSettings,
) -> None:
    task_id = created_id(settings, TITLE, DEADLINE)

    result = edit(settings, task_id, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "succeeded"
    assert result.task is not None
    assert result.task.title == EQUIVALENT_TITLE


def test_an_edit_into_an_undated_conflict_is_rejected(
    settings: ServerSettings,
) -> None:
    existing = created_id(settings, TITLE, None)
    edited = created_id(settings, OTHER_TITLE, None)

    result = edit(settings, edited, EQUIVALENT_TITLE, None)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.conflicting_task_id == existing


def test_an_edit_onto_a_different_date_coexists(
    settings: ServerSettings,
) -> None:
    create(settings, TITLE, DEADLINE)
    edited = created_id(settings, OTHER_TITLE, ANOTHER_DEADLINE)

    result = edit(settings, edited, EQUIVALENT_TITLE, ANOTHER_DEADLINE)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_an_edit_conflicts_with_a_completed_dated_task(
    settings: ServerSettings,
) -> None:
    completed = insert_fixture_task(
        settings, title=TITLE, deadline=DEADLINE, status="completed"
    )
    edited = created_id(settings, OTHER_TITLE, DEADLINE)

    result = edit(settings, edited, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.conflicting_task_id == completed


def test_an_undated_edit_ignores_completed_undated_tasks(
    settings: ServerSettings,
) -> None:
    insert_fixture_task(
        settings, title=TITLE, deadline=None, status="completed"
    )
    edited = created_id(settings, OTHER_TITLE, None)

    result = edit(settings, edited, EQUIVALENT_TITLE, None)

    assert result.outcome == "succeeded"


def test_an_edit_ignores_deleted_tasks(
    settings: ServerSettings,
) -> None:
    insert_fixture_task(settings, title=TITLE, deadline=DEADLINE, is_deleted=1)
    edited = created_id(settings, OTHER_TITLE, DEADLINE)

    result = edit(settings, edited, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "succeeded"


def test_an_undated_edit_coexists_with_a_dated_equivalent_title(
    settings: ServerSettings,
) -> None:
    create(settings, TITLE, DEADLINE)
    edited = created_id(settings, OTHER_TITLE, None)

    result = edit(settings, edited, EQUIVALENT_TITLE, None)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_an_edit_conflict_is_retained_for_consultation(
    settings: ServerSettings,
) -> None:
    create(settings, TITLE, DEADLINE)
    edited = created_id(settings, OTHER_TITLE, DEADLINE)
    request = edit_request(edited, EQUIVALENT_TITLE, DEADLINE)

    result = services.edit_task(
        settings, FixedClock(SERVER_NOW), request, edited
    )

    assert result.outcome == "rejected"
    assert services.lookup_operation(settings, request.operation_id) == (
        result
    )


def test_an_index_violation_on_creation_becomes_a_uniqueness_rejection(
    settings: ServerSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = created_id(settings, TITLE, DEADLINE)
    blind_first_check(monkeypatch)

    result = create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "rejected"
    assert result.original_http_status == 409
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert result.error.conflicting_task_id == existing
    assert len(stored_tasks(settings)) == 1


def test_an_index_violation_on_editing_becomes_a_uniqueness_rejection(
    settings: ServerSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = created_id(settings, TITLE, DEADLINE)
    edited = created_id(settings, OTHER_TITLE, DEADLINE)
    edited_before = stored_columns(settings, edited)
    blind_first_check(monkeypatch)

    result = edit(settings, edited, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert result.error.conflicting_task_id == existing
    assert stored_columns(settings, edited) == edited_before


def test_a_violation_that_is_no_conflict_is_not_disguised(
    settings: ServerSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    reused = uuid4()
    monkeypatch.setattr(services, "uuid4", lambda: reused)
    create(settings, TITLE, DEADLINE)

    with pytest.raises(sqlite3.IntegrityError):
        create(settings, OTHER_TITLE, ANOTHER_DEADLINE)

    assert len(stored_tasks(settings)) == 1


def test_a_retained_uniqueness_rejection_survives_a_freed_conflict(
    settings: ServerSettings,
) -> None:
    existing = created_id(settings, TITLE, DEADLINE)
    request = create_request(EQUIVALENT_TITLE, DEADLINE)
    refused = services.create_task(settings, FixedClock(SERVER_NOW), request)
    edit(settings, existing, TITLE, ANOTHER_DEADLINE)

    repeated = services.create_task(settings, FixedClock(SERVER_NOW), request)

    assert repeated == refused
    assert repeated.outcome == "rejected"
    assert len(stored_tasks(settings)) == 1
