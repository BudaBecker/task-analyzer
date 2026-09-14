"""Integration tests for uniqueness in creation and editing.

Covers PCE-17 through PCE-27, PCE-41, PCE-42; REQ-008, REQ-029,
REQ-031.

Every test opens a newly allocated temporary database file created by
the explicit initializer. Settings are built for that file directly, so
no test reads ``TASK_ANALYZER_DATABASE_PATH`` or touches any configured
runtime database.

The protected comparison examples are used throughout: ``Read notes``
and `` READ  NOTES `` are equivalent titles, while ``Review resume``
with and without accents are different ones. Delivery 1A has no
completion or deletion command, so completed and deleted comparison
candidates are inserted directly as fixtures.
"""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from task_analyzer_server import schema, services, storage
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


class FixedClock:
    """A clock reporting one instant."""

    def now(self) -> datetime:
        """Read the fixed instant.

        Returns:
            The instant every test shares.
        """
        return SERVER_NOW


@pytest.fixture
def settings(tmp_path: Path) -> ServerSettings:
    """Build settings for a configured disposable database.

    Args:
        tmp_path: pytest-allocated temporary directory.

    Returns:
        Settings naming the newly created database file, with the
        product time zone already fixed.
    """
    path = tmp_path / "disposable.sqlite3"
    schema.initialize_database(path)
    configured = ServerSettings(
        database_path=path,
        log_level="INFO",
        db_busy_timeout_ms=BUSY_TIMEOUT_MS,
    )
    services.configure_zone(configured, FixedClock(), PRODUCT_ZONE)
    return configured


def create_request(
    title: str, deadline: str | None, observations: str | None = None
) -> OperationRequest:
    """Build one submitted creation operation.

    Args:
        title: Submitted title text.
        deadline: Submitted calendar-date text, or ``None``.
        observations: Submitted observations, or ``None``.

    Returns:
        The submitted operation.
    """
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
    """Build one submitted edit operation.

    Args:
        task_id: Identity of the task the request targets.
        title: Submitted title text.
        deadline: Submitted calendar-date text, or ``None``.
        observations: Submitted observations, or ``None``.

    Returns:
        The submitted operation.
    """
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
    """Run one creation through the command under test.

    Args:
        settings: Settings naming the configured disposable database.
        title: Submitted title text.
        deadline: Submitted calendar-date text, or ``None``.
        observations: Submitted observations, or ``None``.

    Returns:
        The terminal result of the attempt.
    """
    return services.create_task(
        settings, FixedClock(), create_request(title, deadline, observations)
    )


def created_id(
    settings: ServerSettings, title: str, deadline: str | None
) -> UUID:
    """Create one task and return its identity.

    Args:
        settings: Settings naming the configured disposable database.
        title: Submitted title text.
        deadline: Submitted calendar-date text, or ``None``.

    Returns:
        The identity of the created task.
    """
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
    """Run one edit through the command under test.

    Args:
        settings: Settings naming the configured disposable database.
        task_id: Identity of the task to edit.
        title: Submitted title text.
        deadline: Submitted calendar-date text, or ``None``.
        observations: Submitted observations, or ``None``.

    Returns:
        The terminal result of the attempt.
    """
    return services.edit_task(
        settings,
        FixedClock(),
        edit_request(task_id, title, deadline, observations),
        task_id,
    )


def stored_columns(
    settings: ServerSettings, task_id: UUID
) -> tuple[object, ...]:
    """Read every stored column of one row, managed or not.

    Args:
        settings: Settings naming the disposable database.
        task_id: Identity of the row to read.

    Returns:
        Every column the tasks table holds for that row.
    """
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        row = connection.execute(
            READ_STORED_COLUMNS, (str(task_id),)
        ).fetchone()
    return tuple(row)


def stored_tasks(settings: ServerSettings) -> tuple[TaskSnapshot, ...]:
    """Read every managed task through a separate connection.

    Args:
        settings: Settings naming the disposable database.

    Returns:
        The committed managed tasks.
    """
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
    """Insert a comparison candidate 1A has no command to produce.

    Args:
        settings: Settings naming the disposable database.
        title: Submitted title of the candidate.
        deadline: Deadline text of the candidate, or ``None``.
        status: ``pending`` or ``completed``.
        is_deleted: ``0`` or ``1``.

    Returns:
        The identity of the inserted row.
    """
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
    """Make the first conflict check miss a row the index will catch.

    This stands in for a competing write landing between the check and
    the write itself, which the held write lock otherwise prevents.

    Args:
        monkeypatch: pytest monkeypatching fixture.
    """
    real: Callable[..., UUID | None] = storage.find_conflicting_task
    checks = {"count": 0}

    def missing_first(
        connection: sqlite3.Connection, **arguments: Any
    ) -> UUID | None:
        """Report no conflict the first time, then answer normally.

        Args:
            connection: Connection holding the write transaction.
            **arguments: The lookup's keyword arguments.

        Returns:
            The conflicting identity, or ``None``.
        """
        checks["count"] += 1
        if checks["count"] == 1:
            return None
        return real(connection, **arguments)

    monkeypatch.setattr(storage, "find_conflicting_task", missing_first)


def test_equivalent_titles_on_one_date_conflict_on_creation(
    settings: ServerSettings,
) -> None:
    """Case and spacing differences do not make a different title."""
    create(settings, TITLE, DEADLINE)

    result = create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "rejected"
    assert result.original_http_status == 409
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT


def test_an_uppercase_title_conflicts_on_creation(
    settings: ServerSettings,
) -> None:
    """Comparison ignores case alone as well."""
    create(settings, TITLE, DEADLINE)

    result = create(settings, UPPERCASE_TITLE, DEADLINE)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT


def test_a_creation_conflict_identifies_the_conflicting_task(
    settings: ServerSettings,
) -> None:
    """The rejection names the task the attempt collided with."""
    existing = created_id(settings, TITLE, DEADLINE)

    result = create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert result.error is not None
    assert result.error.conflicting_task_id == existing


def test_a_creation_conflict_leaves_the_conflicting_task_unchanged(
    settings: ServerSettings,
) -> None:
    """A refused creation changes nothing about the existing task."""
    existing = created_id(settings, TITLE, DEADLINE)
    before = stored_columns(settings, existing)

    create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert stored_columns(settings, existing) == before


def test_a_creation_conflict_creates_no_task(
    settings: ServerSettings,
) -> None:
    """A refused creation leaves exactly the tasks that existed."""
    create(settings, TITLE, DEADLINE)

    create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert len(stored_tasks(settings)) == 1


def test_a_dated_creation_conflicts_with_a_completed_task(
    settings: ServerSettings,
) -> None:
    """A dated comparison covers completed tasks on that date."""
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
    """A different deadline date is a different uniqueness slot."""
    create(settings, TITLE, DEADLINE)

    result = create(settings, EQUIVALENT_TITLE, ANOTHER_DEADLINE)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_an_undated_creation_coexists_with_a_dated_task(
    settings: ServerSettings,
) -> None:
    """An undated task never collides with a dated one."""
    create(settings, TITLE, DEADLINE)

    result = create(settings, EQUIVALENT_TITLE, None)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_a_dated_creation_coexists_with_an_undated_task(
    settings: ServerSettings,
) -> None:
    """A dated task never collides with an undated one."""
    create(settings, TITLE, None)

    result = create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_accented_titles_are_different_titles(
    settings: ServerSettings,
) -> None:
    """Accents are preserved when titles are compared."""
    create(settings, ACCENTED_TITLE, DEADLINE)

    result = create(settings, PLAIN_TITLE, DEADLINE)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_undated_pending_tasks_conflict_on_creation(
    settings: ServerSettings,
) -> None:
    """Two undated pending tasks cannot share a title."""
    existing = created_id(settings, TITLE, None)

    result = create(settings, EQUIVALENT_TITLE, None)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert result.error.conflicting_task_id == existing


def test_a_completed_undated_task_frees_its_title(
    settings: ServerSettings,
) -> None:
    """Undated comparison covers pending tasks only."""
    insert_fixture_task(
        settings, title=TITLE, deadline=None, status="completed"
    )

    result = create(settings, EQUIVALENT_TITLE, None)

    assert result.outcome == "succeeded"


def test_a_deleted_dated_task_does_not_block_creation(
    settings: ServerSettings,
) -> None:
    """Deleted rows take no part in dated comparisons."""
    insert_fixture_task(settings, title=TITLE, deadline=DEADLINE, is_deleted=1)

    result = create(settings, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "succeeded"


def test_a_deleted_undated_task_does_not_block_creation(
    settings: ServerSettings,
) -> None:
    """Deleted rows take no part in undated comparisons either."""
    insert_fixture_task(settings, title=TITLE, deadline=None, is_deleted=1)

    result = create(settings, EQUIVALENT_TITLE, None)

    assert result.outcome == "succeeded"


def test_a_uniqueness_rejection_is_retained_for_consultation(
    settings: ServerSettings,
) -> None:
    """Consulting the original attempt returns that same rejection."""
    create(settings, TITLE, DEADLINE)
    request = create_request(EQUIVALENT_TITLE, DEADLINE)

    result = services.create_task(settings, FixedClock(), request)

    assert services.lookup_operation(settings, request.operation_id) == (
        result
    )
    assert result.outcome == "rejected"


def test_a_different_conflicting_operation_is_rejected_not_replayed(
    settings: ServerSettings,
) -> None:
    """A second operation with a matching title is not a repetition."""
    first = create_request(TITLE, DEADLINE)
    second = create_request(EQUIVALENT_TITLE, DEADLINE)

    accepted = services.create_task(settings, FixedClock(), first)
    refused = services.create_task(settings, FixedClock(), second)

    assert accepted.outcome == "succeeded"
    assert refused.outcome == "rejected"
    assert refused.operation_id == second.operation_id
    assert refused.error is not None
    assert refused.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert len(stored_tasks(settings)) == 1


def test_an_edit_into_a_dated_conflict_is_rejected(
    settings: ServerSettings,
) -> None:
    """An edit cannot move a task onto another task's slot."""
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
    """A refused edit changes neither the target nor the other task."""
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
    """Saving a task over itself is not a conflict with itself."""
    task_id = created_id(settings, TITLE, DEADLINE)

    result = edit(settings, task_id, TITLE, DEADLINE, "Added observations")

    assert result.outcome == "succeeded"
    assert result.task is not None
    assert result.task.observations == "Added observations"


def test_an_edit_excludes_itself_under_an_equivalent_title(
    settings: ServerSettings,
) -> None:
    """Respelling a title equivalently still excludes the task itself."""
    task_id = created_id(settings, TITLE, DEADLINE)

    result = edit(settings, task_id, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "succeeded"
    assert result.task is not None
    assert result.task.title == EQUIVALENT_TITLE


def test_an_edit_into_an_undated_conflict_is_rejected(
    settings: ServerSettings,
) -> None:
    """Clearing a deadline can collide with an undated pending task."""
    existing = created_id(settings, TITLE, None)
    edited = created_id(settings, OTHER_TITLE, None)

    result = edit(settings, edited, EQUIVALENT_TITLE, None)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.conflicting_task_id == existing


def test_an_edit_onto_a_different_date_coexists(
    settings: ServerSettings,
) -> None:
    """Moving to another deadline date leaves both tasks valid."""
    create(settings, TITLE, DEADLINE)
    edited = created_id(settings, OTHER_TITLE, ANOTHER_DEADLINE)

    result = edit(settings, edited, EQUIVALENT_TITLE, ANOTHER_DEADLINE)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_an_edit_conflicts_with_a_completed_dated_task(
    settings: ServerSettings,
) -> None:
    """Dated comparison on editing covers completed tasks too."""
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
    """An undated edit compares against pending tasks only."""
    insert_fixture_task(
        settings, title=TITLE, deadline=None, status="completed"
    )
    edited = created_id(settings, OTHER_TITLE, None)

    result = edit(settings, edited, EQUIVALENT_TITLE, None)

    assert result.outcome == "succeeded"


def test_an_edit_ignores_deleted_tasks(
    settings: ServerSettings,
) -> None:
    """Deleted rows take no part in comparisons on editing."""
    insert_fixture_task(settings, title=TITLE, deadline=DEADLINE, is_deleted=1)
    edited = created_id(settings, OTHER_TITLE, DEADLINE)

    result = edit(settings, edited, EQUIVALENT_TITLE, DEADLINE)

    assert result.outcome == "succeeded"


def test_an_undated_edit_coexists_with_a_dated_equivalent_title(
    settings: ServerSettings,
) -> None:
    """An undated edit never collides with a dated task."""
    create(settings, TITLE, DEADLINE)
    edited = created_id(settings, OTHER_TITLE, None)

    result = edit(settings, edited, EQUIVALENT_TITLE, None)

    assert result.outcome == "succeeded"
    assert len(stored_tasks(settings)) == 2


def test_an_edit_conflict_is_retained_for_consultation(
    settings: ServerSettings,
) -> None:
    """A refused edit is durable evidence of that refusal."""
    create(settings, TITLE, DEADLINE)
    edited = created_id(settings, OTHER_TITLE, DEADLINE)
    request = edit_request(edited, EQUIVALENT_TITLE, DEADLINE)

    result = services.edit_task(settings, FixedClock(), request, edited)

    assert result.outcome == "rejected"
    assert services.lookup_operation(settings, request.operation_id) == (
        result
    )


def test_an_index_violation_on_creation_becomes_a_uniqueness_rejection(
    settings: ServerSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write reaching the index is the conflict, not a defect."""
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
    """The same translation protects the edit command."""
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
    """Another broken constraint is never reported as a conflict."""
    reused = uuid4()
    monkeypatch.setattr(services, "uuid4", lambda: reused)
    create(settings, TITLE, DEADLINE)

    with pytest.raises(sqlite3.IntegrityError):
        create(settings, OTHER_TITLE, ANOTHER_DEADLINE)

    assert len(stored_tasks(settings)) == 1


def test_a_retained_uniqueness_rejection_survives_a_freed_conflict(
    settings: ServerSettings,
) -> None:
    """A repeated attempt returns its rejection, not a fresh decision."""
    existing = created_id(settings, TITLE, DEADLINE)
    request = create_request(EQUIVALENT_TITLE, DEADLINE)
    refused = services.create_task(settings, FixedClock(), request)
    edit(settings, existing, TITLE, ANOTHER_DEADLINE)

    repeated = services.create_task(settings, FixedClock(), request)

    assert repeated == refused
    assert repeated.outcome == "rejected"
    assert len(stored_tasks(settings)) == 1
