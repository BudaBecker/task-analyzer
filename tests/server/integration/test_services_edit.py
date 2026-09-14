"""Integration tests for the pending-task edit command.

Covers PCE-11 through PCE-16, PCE-27, PCE-51, PCE-52; REQ-007, REQ-008,
REQ-010, REQ-028, REQ-029.

Every test opens a newly allocated temporary database file created by
the explicit initializer. Settings are built for that file directly, so
no test reads ``TASK_ANALYZER_DATABASE_PATH`` or touches any configured
runtime database.

Delivery 1A has no completion or deletion command, so completed and
deleted edit targets are inserted directly as fixtures.
"""

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from task_analyzer_server import schema, services, storage
from task_analyzer_server.clock import to_utc_microseconds
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
LATER_NOW = datetime(2026, 9, 20, 9, 15, 0, 987654, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 9, 13, 18, 0, 0, tzinfo=UTC)

TITLE = "Read notes"
NEW_TITLE = "Read the revised notes"

COMBINING_ACUTE = chr(0x0301)
COMBINING_E = "e" + COMBINING_ACUTE
"""One user-perceived character: base letter plus a combining acute."""

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

    def __init__(self, instant: datetime = SERVER_NOW) -> None:
        """Build the clock.

        Args:
            instant: The instant every reading returns.
        """
        self.instant = instant

    def now(self) -> datetime:
        """Read the fixed instant.

        Returns:
            The instant this clock was built with.
        """
        return self.instant


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


def create(
    settings: ServerSettings,
    title: str = TITLE,
    observations: str | None = None,
    deadline: str | None = None,
) -> UUID:
    """Create one pending task to edit.

    Args:
        settings: Settings naming the configured disposable database.
        title: Submitted title text.
        observations: Submitted observations, or ``None``.
        deadline: Submitted calendar-date text, or ``None``.

    Returns:
        The identity of the created task.
    """
    result = services.create_task(
        settings,
        FixedClock(),
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


def edit_request(
    task_id: UUID,
    title: str = NEW_TITLE,
    observations: str | None = None,
    deadline: str | None = None,
    operation_id: UUID | None = None,
) -> OperationRequest:
    """Build one submitted edit operation.

    Args:
        task_id: Identity of the task the request targets.
        title: Submitted title text.
        observations: Submitted observations, or ``None``.
        deadline: Submitted calendar-date text, or ``None``.
        operation_id: Identity of the attempt, or ``None`` for a new one.

    Returns:
        The submitted operation.
    """
    return OperationRequest(
        operation_id=uuid4() if operation_id is None else operation_id,
        method="PUT",
        target=f"/v1/tasks/{task_id}",
        payload={
            "title": title,
            "observations": observations,
            "deadline": deadline,
        },
    )


def edit(
    settings: ServerSettings,
    task_id: UUID,
    title: str = NEW_TITLE,
    observations: str | None = None,
    deadline: str | None = None,
    clock: FixedClock | None = None,
) -> OperationResult:
    """Run one edit through the command under test.

    Args:
        settings: Settings naming the configured disposable database.
        task_id: Identity of the task to edit.
        title: Submitted title text.
        observations: Submitted observations, or ``None``.
        deadline: Submitted calendar-date text, or ``None``.
        clock: Clock to sample, or ``None`` for the default instant.

    Returns:
        The terminal result of the attempt.
    """
    return services.edit_task(
        settings,
        FixedClock() if clock is None else clock,
        edit_request(task_id, title, observations, deadline),
        task_id,
    )


def stored_task(
    settings: ServerSettings, task_id: UUID
) -> TaskSnapshot | None:
    """Read one managed task through a separate connection.

    Args:
        settings: Settings naming the disposable database.
        task_id: Identity of the task to read.

    Returns:
        The committed task, or ``None`` when it is not managed.
    """
    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as connection:
        return storage.read_task(connection, task_id)


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


def insert_fixture_task(
    settings: ServerSettings,
    *,
    status: str = "pending",
    is_deleted: int = 0,
) -> UUID:
    """Insert an edit target 1A has no command to produce.

    Args:
        settings: Settings naming the disposable database.
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
                    TITLE,
                    title_key(TITLE),
                    "Original observations",
                    "2026-09-14",
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


def test_a_valid_edit_persists_every_editable_field(
    settings: ServerSettings,
) -> None:
    """One save replaces title, observations and deadline together."""
    task_id = create(settings, observations="Original", deadline="2026-09-14")

    result = edit(
        settings,
        task_id,
        title=NEW_TITLE,
        observations="Replaced",
        deadline="2026-09-20",
    )

    assert result.outcome == "succeeded"
    assert result.original_http_status == 200
    stored = stored_task(settings, task_id)
    assert stored is not None
    assert stored.title == NEW_TITLE
    assert stored.observations == "Replaced"
    assert stored.deadline == date(2026, 9, 20)


def test_an_edit_replaces_the_whole_editable_state(
    settings: ServerSettings,
) -> None:
    """Values the save omits are replaced, not merged."""
    task_id = create(settings, observations="Original", deadline="2026-09-14")

    edit(settings, task_id, title=NEW_TITLE)

    stored = stored_task(settings, task_id)
    assert stored is not None
    assert stored.observations is None
    assert stored.deadline is None


def test_clearing_observations_persists_their_absence(
    settings: ServerSettings,
) -> None:
    """An explicitly cleared optional value is stored as absent."""
    task_id = create(settings, observations="Original", deadline="2026-09-14")

    edit(settings, task_id, observations=None, deadline="2026-09-14")

    stored = stored_task(settings, task_id)
    assert stored is not None
    assert stored.observations is None
    assert stored.deadline == date(2026, 9, 14)


def test_clearing_the_deadline_persists_its_absence(
    settings: ServerSettings,
) -> None:
    """Removing a deadline leaves the task undated."""
    task_id = create(settings, observations="Original", deadline="2026-09-14")

    edit(settings, task_id, observations="Original", deadline=None)

    stored = stored_task(settings, task_id)
    assert stored is not None
    assert stored.deadline is None
    assert stored.observations == "Original"


def test_an_edit_preserves_identity_creation_time_and_status(
    settings: ServerSettings,
) -> None:
    """A changed title moves no server-owned field of the task."""
    task_id = create(settings, observations="Original", deadline="2026-09-14")
    before = stored_task(settings, task_id)

    result = edit(
        settings, task_id, title=NEW_TITLE, clock=FixedClock(LATER_NOW)
    )

    assert before is not None
    assert result.task is not None
    assert result.task.task_id == task_id
    assert result.task.created_at == before.created_at
    assert result.task.status == "pending"
    assert result.task.completed_at is None


def test_the_stored_creation_time_is_untouched_by_a_later_edit(
    settings: ServerSettings,
) -> None:
    """The original creation instant survives an edit at another time."""
    task_id = create(settings)

    edit(settings, task_id, clock=FixedClock(LATER_NOW))

    stored = stored_task(settings, task_id)
    assert stored is not None
    assert stored.created_at == SERVER_NOW


def test_an_edit_updates_the_stored_comparison_key(
    settings: ServerSettings,
) -> None:
    """A changed title changes the stored comparison key with it."""
    task_id = create(settings)

    edit(settings, task_id, title=" READ  NOTES ")

    columns = stored_columns(settings, task_id)
    assert columns[0] == " READ  NOTES "
    assert columns[1] == title_key(" READ  NOTES ")


def test_an_edit_of_an_absent_task_is_a_stored_rejection(
    settings: ServerSettings,
) -> None:
    """An identity nothing was stored under cannot be edited."""
    absent = uuid4()
    request = edit_request(absent)

    result = services.edit_task(settings, FixedClock(), request, absent)

    assert result.outcome == "rejected"
    assert result.original_http_status == 404
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_NOT_FOUND
    assert services.lookup_operation(settings, request.operation_id) == (
        result
    )


def test_an_edit_never_creates_a_task(
    settings: ServerSettings,
) -> None:
    """A rejected edit of an absent task creates nothing."""
    absent = uuid4()

    services.edit_task(settings, FixedClock(), edit_request(absent), absent)

    assert stored_task(settings, absent) is None


def test_an_edit_of_a_deleted_task_is_not_found(
    settings: ServerSettings,
) -> None:
    """A row excluded from managed tasks reads as absent."""
    deleted = insert_fixture_task(settings, is_deleted=1)
    before = stored_columns(settings, deleted)

    result = services.edit_task(
        settings, FixedClock(), edit_request(deleted), deleted
    )

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_NOT_FOUND
    assert stored_columns(settings, deleted) == before


def test_an_edit_of_a_completed_task_is_a_state_rejection(
    settings: ServerSettings,
) -> None:
    """A completed task is outside the 1A pending-edit command."""
    completed = insert_fixture_task(settings, status="completed")

    result = services.edit_task(
        settings, FixedClock(), edit_request(completed), completed
    )

    assert result.outcome == "rejected"
    assert result.original_http_status == 409
    assert result.error is not None
    assert result.error.code == ErrorCode.TASK_STATE_INCOMPATIBLE


def test_a_state_rejection_changes_no_state_or_time(
    settings: ServerSettings,
) -> None:
    """The refused target keeps every stored column it had."""
    completed = insert_fixture_task(settings, status="completed")
    before = stored_columns(settings, completed)

    services.edit_task(
        settings,
        FixedClock(LATER_NOW),
        edit_request(completed),
        completed,
    )

    assert stored_columns(settings, completed) == before


def test_an_invalid_title_rejection_leaves_the_task_unchanged(
    settings: ServerSettings,
) -> None:
    """A rejected edit leaves the whole persisted task as it was."""
    task_id = create(settings, observations="Original", deadline="2026-09-14")
    before = stored_columns(settings, task_id)

    result = edit(settings, task_id, title="   ")

    assert result.outcome == "rejected"
    assert result.original_http_status == 422
    assert result.error is not None
    assert result.error.fields == (REQUIRED_TITLE,)
    assert stored_columns(settings, task_id) == before


def test_an_invalid_deadline_rejection_leaves_the_task_unchanged(
    settings: ServerSettings,
) -> None:
    """An invalid calendar date changes nothing about the task."""
    task_id = create(settings, observations="Original", deadline="2026-09-14")
    before = stored_columns(settings, task_id)

    result = edit(settings, task_id, deadline="2026-02-30")

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (INVALID_DEADLINE,)
    assert stored_columns(settings, task_id) == before


def test_a_rejected_edit_retains_its_result(
    settings: ServerSettings,
) -> None:
    """A rejected edit is durable evidence of that rejection."""
    task_id = create(settings)
    request = edit_request(task_id, title="")

    result = services.edit_task(settings, FixedClock(), request, task_id)

    assert services.lookup_operation(settings, request.operation_id) == (
        result
    )


def test_a_title_of_two_hundred_characters_is_accepted_as_an_edit(
    settings: ServerSettings,
) -> None:
    """The title limit holds on editing exactly as on creation."""
    task_id = create(settings)

    result = edit(settings, task_id, title="a" * 200)

    assert result.outcome == "succeeded"
    stored = stored_task(settings, task_id)
    assert stored is not None
    assert stored.title == "a" * 200


def test_a_title_of_two_hundred_and_one_characters_is_rejected_as_an_edit(
    settings: ServerSettings,
) -> None:
    """One character past the title limit is rejected on editing."""
    task_id = create(settings)
    before = stored_columns(settings, task_id)

    result = edit(settings, task_id, title="a" * 201)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_TITLE,)
    assert stored_columns(settings, task_id) == before


def test_two_hundred_combined_characters_are_accepted_as_an_edit(
    settings: ServerSettings,
) -> None:
    """Editing counts user-perceived characters, not code points."""
    task_id = create(settings)

    result = edit(settings, task_id, title=COMBINING_E * 200)

    assert result.outcome == "succeeded"
    stored = stored_task(settings, task_id)
    assert stored is not None
    assert stored.title == COMBINING_E * 200


def test_two_hundred_and_one_combined_characters_are_rejected_as_an_edit(
    settings: ServerSettings,
) -> None:
    """The combined-character boundary holds on editing too."""
    task_id = create(settings)
    before = stored_columns(settings, task_id)

    result = edit(settings, task_id, title=COMBINING_E * 201)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_TITLE,)
    assert stored_columns(settings, task_id) == before


def test_five_thousand_observation_characters_are_accepted_as_an_edit(
    settings: ServerSettings,
) -> None:
    """The observation limit holds on editing exactly as on creation."""
    task_id = create(settings)

    result = edit(settings, task_id, observations="a" * 5000)

    assert result.outcome == "succeeded"
    stored = stored_task(settings, task_id)
    assert stored is not None
    assert stored.observations == "a" * 5000


def test_five_thousand_and_one_observation_characters_are_rejected_as_an_edit(
    settings: ServerSettings,
) -> None:
    """One character past the observation limit is rejected on editing."""
    task_id = create(settings)
    before = stored_columns(settings, task_id)

    result = edit(settings, task_id, observations="a" * 5001)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (TOO_LONG_OBSERVATIONS,)
    assert stored_columns(settings, task_id) == before


def test_the_supported_deadline_endpoints_are_accepted_as_edits(
    settings: ServerSettings,
) -> None:
    """Both ends of the approved range are editable deadlines."""
    earliest = create(settings, title="Earliest")
    latest = create(settings, title="Latest")

    edit(settings, earliest, title="Earliest", deadline="0001-01-01")
    edit(settings, latest, title="Latest", deadline="9999-12-30")

    first = stored_task(settings, earliest)
    second = stored_task(settings, latest)
    assert first is not None
    assert second is not None
    assert first.deadline == date(1, 1, 1)
    assert second.deadline == date(9999, 12, 30)


def test_a_deadline_past_the_supported_range_is_rejected_as_an_edit(
    settings: ServerSettings,
) -> None:
    """9999-12-31 is outside the approved range on editing too."""
    task_id = create(settings, deadline="2026-09-14")
    before = stored_columns(settings, task_id)

    result = edit(settings, task_id, deadline="9999-12-31")

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (INVALID_DEADLINE,)
    assert stored_columns(settings, task_id) == before


def test_line_breaks_in_edited_observations_are_retained(
    settings: ServerSettings,
) -> None:
    """Multiline observations keep every line break on editing."""
    task_id = create(settings)
    observations = "First line\nSecond line\n\nFourth line"

    edit(settings, task_id, observations=observations)

    stored = stored_task(settings, task_id)
    assert stored is not None
    assert stored.observations == observations


def test_a_repeated_edit_is_not_applied_twice(
    settings: ServerSettings,
) -> None:
    """Repeating one edit returns its original outcome unchanged."""
    task_id = create(settings, observations="Original")
    request = edit_request(task_id, title=NEW_TITLE)
    original = services.edit_task(settings, FixedClock(), request, task_id)
    after_first = stored_columns(settings, task_id)

    repeated = services.edit_task(
        settings, FixedClock(LATER_NOW), request, task_id
    )

    assert repeated == original
    assert stored_columns(settings, task_id) == after_first


def test_an_old_edit_replayed_after_a_later_edit_changes_nothing(
    settings: ServerSettings,
) -> None:
    """A stale repetition returns its snapshot without rewriting state."""
    task_id = create(settings)
    old = edit_request(task_id, title="First replacement")
    original = services.edit_task(settings, FixedClock(), old, task_id)
    edit(settings, task_id, title="Second replacement")

    replayed = services.edit_task(
        settings, FixedClock(LATER_NOW), old, task_id
    )

    assert replayed == original
    stored = stored_task(settings, task_id)
    assert stored is not None
    assert stored.title == "Second replacement"


def test_an_edit_is_refused_before_the_product_zone_is_fixed(
    tmp_path: Path,
) -> None:
    """An unconfigured server records no terminal task result."""
    path = tmp_path / "unconfigured.sqlite3"
    schema.initialize_database(path)
    unconfigured = ServerSettings(
        database_path=path,
        log_level="INFO",
        db_busy_timeout_ms=BUSY_TIMEOUT_MS,
    )
    absent = uuid4()
    request = edit_request(absent)

    with pytest.raises(services.ProtocolRefusalError) as refusal:
        services.edit_task(unconfigured, FixedClock(), request, absent)

    assert refusal.value.code == ErrorCode.PRODUCT_TIME_ZONE_REQUIRED
    assert services.lookup_operation(unconfigured, request.operation_id) is (
        None
    )


def test_an_edit_reaches_only_the_task_it_names(
    settings: ServerSettings,
) -> None:
    """Editing one task leaves every other task untouched."""
    edited = create(settings, title="Read notes", deadline="2026-09-14")
    other = create(settings, title="Review resume", deadline="2026-09-14")
    before = stored_columns(settings, other)

    edit(settings, edited, title=NEW_TITLE, observations="Replaced")

    assert stored_columns(settings, other) == before


def test_an_unexpected_field_is_rejected_on_editing(
    settings: ServerSettings,
) -> None:
    """A server-owned field is refused rather than silently applied."""
    task_id = create(settings)
    before = stored_columns(settings, task_id)
    request = OperationRequest(
        operation_id=uuid4(),
        method="PUT",
        target=f"/v1/tasks/{task_id}",
        payload={"title": NEW_TITLE, "created_at": "2020-01-01T00:00:00Z"},
    )

    result = services.edit_task(settings, FixedClock(), request, task_id)

    assert result.outcome == "rejected"
    assert result.error is not None
    assert result.error.fields == (
        ValidationIssue(
            field="created_at", code=FieldErrorCode.UNEXPECTED_FIELD
        ),
    )
    assert stored_columns(settings, task_id) == before


def test_the_edited_task_is_the_one_a_later_reader_finds(
    settings: ServerSettings,
) -> None:
    """Success reports committed state, not the request."""
    task_id = create(settings, observations="Original")

    result = edit(settings, task_id, observations="Replaced")

    assert result.task == stored_task(settings, task_id)


def test_a_deleted_target_is_never_revived_by_an_edit(
    settings: ServerSettings,
) -> None:
    """A rejected edit does not bring an excluded row back."""
    deleted = insert_fixture_task(settings, is_deleted=1)

    services.edit_task(settings, FixedClock(), edit_request(deleted), deleted)

    assert stored_task(settings, deleted) is None
    assert stored_columns(settings, deleted)[7] == 1


def test_the_edit_target_is_read_inside_the_write_transaction(
    settings: ServerSettings,
) -> None:
    """A blocked writer cannot read or edit the target at all."""
    task_id = create(settings)
    blocked = ServerSettings(
        database_path=settings.database_path,
        log_level=settings.log_level,
        db_busy_timeout_ms=250,
    )

    with storage.open_connection(
        settings.database_path, BUSY_TIMEOUT_MS
    ) as holder:
        with storage.write_transaction(holder):
            with pytest.raises(sqlite3.OperationalError):
                services.edit_task(
                    blocked,
                    FixedClock(),
                    edit_request(task_id),
                    task_id,
                )
