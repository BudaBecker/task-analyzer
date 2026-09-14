"""Integration tests for task storage access.

Covers PCE-11 through PCE-14, PCE-19 through PCE-25, PCE-36; REQ-008,
REQ-010, REQ-029.

Every test opens a newly allocated temporary database file created by
the explicit initializer. No test reads
``TASK_ANALYZER_DATABASE_PATH`` or touches any configured runtime
database.

Delivery 1A has no completion or deletion command, so completed and
deleted comparison candidates are inserted directly as fixtures.
"""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from task_analyzer_server import schema, storage
from task_analyzer_server.clock import to_utc_microseconds
from task_analyzer_server.domain import title_key

BUSY_TIMEOUT_MS = 5000

E_ACUTE = chr(0x00E9)

TITLE = "Read notes"
EQUIVALENT_TITLE = " READ  NOTES "
ACCENTED_TITLE = f"Review r{E_ACUTE}sum{E_ACUTE}"
PLAIN_TITLE = "Review resume"

DEADLINE = date(2026, 9, 14)
ANOTHER_DEADLINE = date(2026, 9, 15)
CREATED_AT = datetime(2026, 9, 13, 12, 0, 0, 123456, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 9, 13, 18, 0, 0, tzinfo=UTC)

INSERT_FIXTURE_TASK = (
    "INSERT INTO tasks ("
    " task_id, title, title_key, observations, deadline_date,"
    " status, created_at_us, latest_completed_at_us, is_deleted"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
READ_STORED_COLUMNS = (
    "SELECT title_key, status, latest_completed_at_us, is_deleted,"
    " created_at_us, deadline_date FROM tasks WHERE task_id = ?"
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """Create a disposable initialized database file.

    Args:
        tmp_path: pytest-allocated temporary directory.

    Returns:
        Absolute path of the newly created database file.
    """
    path = tmp_path / "disposable.sqlite3"
    schema.initialize_database(path)
    return path


@pytest.fixture
def writing(database_path: Path) -> Iterator[sqlite3.Connection]:
    """Open one connection holding a write transaction.

    Args:
        database_path: Disposable database created for this test.

    Yields:
        The open connection, with the write lock held and committed on
        a clean exit.
    """
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        with storage.write_transaction(connection):
            yield connection


def create_task(
    connection: sqlite3.Connection,
    *,
    title: str = TITLE,
    observations: str | None = None,
    deadline: date | None = None,
    created_at: datetime = CREATED_AT,
    task_id: UUID | None = None,
) -> UUID:
    """Store one pending task through the module under test.

    Args:
        connection: Open connection holding the write transaction.
        title: Submitted title.
        observations: Submitted observations, or ``None``.
        deadline: Submitted deadline date, or ``None``.
        created_at: Creation instant to store.
        task_id: Identity to use, or ``None`` to generate one.

    Returns:
        The identity of the stored task.
    """
    identity = uuid4() if task_id is None else task_id
    storage.insert_task(
        connection,
        task_id=identity,
        title=title,
        title_key=title_key(title),
        observations=observations,
        deadline=deadline,
        created_at=created_at,
    )
    return identity


def insert_fixture_task(
    connection: sqlite3.Connection,
    *,
    title: str,
    deadline: date | None,
    status: str = "pending",
    is_deleted: int = 0,
) -> UUID:
    """Insert a comparison candidate 1A has no command to produce.

    Args:
        connection: Open connection holding the write transaction.
        title: Submitted title of the candidate.
        deadline: Deadline date of the candidate, or ``None``.
        status: ``pending`` or ``completed``.
        is_deleted: ``0`` or ``1``.

    Returns:
        The identity of the inserted row.
    """
    identity = uuid4()
    connection.execute(
        INSERT_FIXTURE_TASK,
        (
            str(identity),
            title,
            title_key(title),
            None,
            None if deadline is None else deadline.isoformat(),
            status,
            to_utc_microseconds(CREATED_AT),
            (
                to_utc_microseconds(COMPLETED_AT)
                if status == "completed"
                else None
            ),
            is_deleted,
        ),
    )
    return identity


def read_stored_columns(
    connection: sqlite3.Connection, task_id: UUID
) -> tuple[object, ...]:
    """Read the internal columns a snapshot never publishes.

    Args:
        connection: Open connection to the disposable database.
        task_id: Identity of the row to read.

    Returns:
        Title key, status, completion microseconds, deletion flag,
        creation microseconds and deadline text.
    """
    row = connection.execute(READ_STORED_COLUMNS, (str(task_id),)).fetchone()
    return tuple(row)


def test_insert_stores_the_identity_and_submitted_text(
    writing: sqlite3.Connection,
) -> None:
    """The stored task carries the supplied identity and text."""
    identity = create_task(
        writing,
        title=TITLE,
        observations="Line one\nLine two",
        deadline=DEADLINE,
    )

    stored = storage.read_task(writing, identity)

    assert stored is not None
    assert stored.task_id == identity
    assert stored.title == TITLE
    assert stored.observations == "Line one\nLine two"
    assert stored.deadline == DEADLINE


def test_insert_stores_the_task_as_pending_without_completion(
    writing: sqlite3.Connection,
) -> None:
    """A created task is pending and carries no completion time."""
    identity = create_task(writing)

    stored = storage.read_task(writing, identity)

    assert stored is not None
    assert stored.status == "pending"
    assert stored.completed_at is None


def test_insert_stores_the_task_as_not_deleted(
    writing: sqlite3.Connection,
) -> None:
    """A created task is stored outside the deleted population."""
    identity = create_task(writing)

    assert read_stored_columns(writing, identity)[3] == 0


def test_insert_stores_the_centrally_derived_title_key(
    writing: sqlite3.Connection,
) -> None:
    """The stored key is the one central derivation produces."""
    identity = create_task(writing, title=EQUIVALENT_TITLE)

    assert read_stored_columns(writing, identity)[0] == title_key(
        EQUIVALENT_TITLE
    )


def test_insert_stores_the_supplied_creation_instant(
    writing: sqlite3.Connection,
) -> None:
    """The creation instant is stored and read back to the microsecond."""
    identity = create_task(writing)

    stored = storage.read_task(writing, identity)

    assert stored is not None
    assert stored.created_at == CREATED_AT
    assert read_stored_columns(writing, identity)[4] == to_utc_microseconds(
        CREATED_AT
    )


def test_insert_returns_the_task_as_it_was_stored(
    writing: sqlite3.Connection,
) -> None:
    """The returned snapshot is the persisted row, not the request."""
    identity = uuid4()

    returned = storage.insert_task(
        writing,
        task_id=identity,
        title=TITLE,
        title_key=title_key(TITLE),
        observations=None,
        deadline=DEADLINE,
        created_at=CREATED_AT,
    )

    assert returned == storage.read_task(writing, identity)


def test_a_committed_task_is_readable_by_a_new_connection(
    database_path: Path,
) -> None:
    """A committed task outlives the connection that wrote it."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        with storage.write_transaction(connection):
            identity = create_task(connection, deadline=DEADLINE)

    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        reopened = storage.read_task(connection, identity)

    assert reopened is not None
    assert reopened.title == TITLE
    assert reopened.deadline == DEADLINE
    assert reopened.created_at == CREATED_AT


def test_an_uncommitted_task_is_never_visible_elsewhere(
    database_path: Path,
) -> None:
    """A rolled-back creation leaves no task behind."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        with pytest.raises(RuntimeError, match="injected"):
            with storage.write_transaction(connection):
                create_task(connection)
                raise RuntimeError("injected storage failure")

    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        assert storage.read_tasks(connection) == ()


def test_update_replaces_every_editable_field(
    writing: sqlite3.Connection,
) -> None:
    """One save replaces title, observations and deadline together."""
    identity = create_task(writing, observations="Original", deadline=DEADLINE)

    storage.update_task(
        writing,
        task_id=identity,
        title=PLAIN_TITLE,
        title_key=title_key(PLAIN_TITLE),
        observations="Replaced",
        deadline=ANOTHER_DEADLINE,
    )

    stored = storage.read_task(writing, identity)
    assert stored is not None
    assert stored.title == PLAIN_TITLE
    assert stored.observations == "Replaced"
    assert stored.deadline == ANOTHER_DEADLINE


def test_update_persists_the_absence_of_cleared_values(
    writing: sqlite3.Connection,
) -> None:
    """Clearing an optional value stores its absence."""
    identity = create_task(writing, observations="Original", deadline=DEADLINE)

    storage.update_task(
        writing,
        task_id=identity,
        title=TITLE,
        title_key=title_key(TITLE),
        observations=None,
        deadline=None,
    )

    stored = storage.read_task(writing, identity)
    assert stored is not None
    assert stored.observations is None
    assert stored.deadline is None


def test_update_replaces_the_derived_title_key(
    writing: sqlite3.Connection,
) -> None:
    """A changed title changes the stored comparison key with it."""
    identity = create_task(writing, title=TITLE)

    storage.update_task(
        writing,
        task_id=identity,
        title=ACCENTED_TITLE,
        title_key=title_key(ACCENTED_TITLE),
        observations=None,
        deadline=None,
    )

    assert read_stored_columns(writing, identity)[0] == title_key(
        ACCENTED_TITLE
    )


def test_update_preserves_identity_creation_time_and_status(
    writing: sqlite3.Connection,
) -> None:
    """An edit moves no server-owned field of the task."""
    identity = create_task(writing, deadline=DEADLINE)
    before = storage.read_task(writing, identity)

    storage.update_task(
        writing,
        task_id=identity,
        title=PLAIN_TITLE,
        title_key=title_key(PLAIN_TITLE),
        observations=None,
        deadline=None,
    )

    after = storage.read_task(writing, identity)
    assert before is not None
    assert after is not None
    assert after.task_id == before.task_id
    assert after.created_at == before.created_at
    assert after.status == "pending"
    assert after.completed_at is None
    assert read_stored_columns(writing, identity)[3] == 0


def test_update_returns_the_task_as_it_was_stored(
    writing: sqlite3.Connection,
) -> None:
    """The returned snapshot is the persisted row after the edit."""
    identity = create_task(writing)

    returned = storage.update_task(
        writing,
        task_id=identity,
        title=PLAIN_TITLE,
        title_key=title_key(PLAIN_TITLE),
        observations="Replaced",
        deadline=ANOTHER_DEADLINE,
    )

    assert returned == storage.read_task(writing, identity)


def test_update_leaves_every_other_task_untouched(
    writing: sqlite3.Connection,
) -> None:
    """An edit reaches only the task it names."""
    edited = create_task(writing, title=TITLE, deadline=DEADLINE)
    other = create_task(writing, title=PLAIN_TITLE, deadline=DEADLINE)
    before = storage.read_task(writing, other)

    storage.update_task(
        writing,
        task_id=edited,
        title=ACCENTED_TITLE,
        title_key=title_key(ACCENTED_TITLE),
        observations="Replaced",
        deadline=ANOTHER_DEADLINE,
    )

    assert storage.read_task(writing, other) == before


def test_update_reaches_no_deleted_row(
    writing: sqlite3.Connection,
) -> None:
    """A row outside managed tasks cannot be edited."""
    deleted = insert_fixture_task(
        writing, title=TITLE, deadline=DEADLINE, is_deleted=1
    )

    with pytest.raises(storage.TaskNotStoredError):
        storage.update_task(
            writing,
            task_id=deleted,
            title=PLAIN_TITLE,
            title_key=title_key(PLAIN_TITLE),
            observations=None,
            deadline=None,
        )


def test_reading_an_absent_task_reports_absence(
    writing: sqlite3.Connection,
) -> None:
    """An identity nothing was stored under reads as absent."""
    assert storage.read_task(writing, uuid4()) is None


def test_reading_one_task_excludes_a_deleted_row(
    writing: sqlite3.Connection,
) -> None:
    """A deleted row reads as absent, like one that never existed."""
    deleted = insert_fixture_task(
        writing, title=TITLE, deadline=DEADLINE, is_deleted=1
    )

    assert storage.read_task(writing, deleted) is None


def test_managed_reads_return_every_committed_task(
    writing: sqlite3.Connection,
) -> None:
    """Reading managed tasks returns each stored task once."""
    first = create_task(writing, title=TITLE, deadline=DEADLINE)
    second = create_task(writing, title=PLAIN_TITLE, deadline=DEADLINE)

    stored = storage.read_tasks(writing)

    assert sorted(task.task_id for task in stored) == sorted([first, second])


def test_managed_reads_exclude_deleted_tasks(
    writing: sqlite3.Connection,
) -> None:
    """Deleted rows never appear among managed tasks."""
    kept = create_task(writing, title=TITLE, deadline=DEADLINE)
    insert_fixture_task(
        writing, title=PLAIN_TITLE, deadline=DEADLINE, is_deleted=1
    )

    stored = storage.read_tasks(writing)

    assert [task.task_id for task in stored] == [kept]


def test_a_dated_conflict_matches_an_equivalent_title(
    writing: sqlite3.Connection,
) -> None:
    """Equivalent titles on one deadline date collide."""
    existing = create_task(writing, title=TITLE, deadline=DEADLINE)

    conflict = storage.find_conflicting_task(
        writing, title_key=title_key(EQUIVALENT_TITLE), deadline=DEADLINE
    )

    assert conflict == existing


def test_a_dated_conflict_matches_a_completed_task(
    writing: sqlite3.Connection,
) -> None:
    """A dated comparison covers completed tasks as well."""
    completed = insert_fixture_task(
        writing, title=TITLE, deadline=DEADLINE, status="completed"
    )

    conflict = storage.find_conflicting_task(
        writing, title_key=title_key(EQUIVALENT_TITLE), deadline=DEADLINE
    )

    assert conflict == completed


def test_equivalent_titles_on_different_dates_do_not_conflict(
    writing: sqlite3.Connection,
) -> None:
    """A different deadline date lets equivalent titles coexist."""
    create_task(writing, title=TITLE, deadline=DEADLINE)

    conflict = storage.find_conflicting_task(
        writing,
        title_key=title_key(EQUIVALENT_TITLE),
        deadline=ANOTHER_DEADLINE,
    )

    assert conflict is None


def test_an_undated_state_does_not_conflict_with_a_dated_task(
    writing: sqlite3.Connection,
) -> None:
    """An undated task coexists with a dated equivalent title."""
    create_task(writing, title=TITLE, deadline=DEADLINE)

    conflict = storage.find_conflicting_task(
        writing, title_key=title_key(EQUIVALENT_TITLE), deadline=None
    )

    assert conflict is None


def test_a_dated_state_does_not_conflict_with_an_undated_task(
    writing: sqlite3.Connection,
) -> None:
    """A dated task coexists with an undated equivalent title."""
    create_task(writing, title=TITLE, deadline=None)

    conflict = storage.find_conflicting_task(
        writing, title_key=title_key(EQUIVALENT_TITLE), deadline=DEADLINE
    )

    assert conflict is None


def test_an_undated_conflict_matches_an_equivalent_pending_title(
    writing: sqlite3.Connection,
) -> None:
    """Undated pending tasks collide on an equivalent title."""
    existing = create_task(writing, title=TITLE, deadline=None)

    conflict = storage.find_conflicting_task(
        writing, title_key=title_key(EQUIVALENT_TITLE), deadline=None
    )

    assert conflict == existing


def test_an_undated_comparison_excludes_completed_tasks(
    writing: sqlite3.Connection,
) -> None:
    """Completing an undated task frees its title."""
    insert_fixture_task(
        writing, title=TITLE, deadline=None, status="completed"
    )

    conflict = storage.find_conflicting_task(
        writing, title_key=title_key(EQUIVALENT_TITLE), deadline=None
    )

    assert conflict is None


def test_accented_titles_are_not_equivalent(
    writing: sqlite3.Connection,
) -> None:
    """Accent differences keep two titles distinct."""
    create_task(writing, title=ACCENTED_TITLE, deadline=DEADLINE)

    conflict = storage.find_conflicting_task(
        writing, title_key=title_key(PLAIN_TITLE), deadline=DEADLINE
    )

    assert conflict is None


def test_a_dated_comparison_excludes_deleted_tasks(
    writing: sqlite3.Connection,
) -> None:
    """A deleted dated task takes no part in comparisons."""
    insert_fixture_task(writing, title=TITLE, deadline=DEADLINE, is_deleted=1)

    conflict = storage.find_conflicting_task(
        writing, title_key=title_key(EQUIVALENT_TITLE), deadline=DEADLINE
    )

    assert conflict is None


def test_an_undated_comparison_excludes_deleted_tasks(
    writing: sqlite3.Connection,
) -> None:
    """A deleted undated task takes no part in comparisons."""
    insert_fixture_task(writing, title=TITLE, deadline=None, is_deleted=1)

    conflict = storage.find_conflicting_task(
        writing, title_key=title_key(EQUIVALENT_TITLE), deadline=None
    )

    assert conflict is None


def test_a_dated_comparison_excludes_the_supplied_identity(
    writing: sqlite3.Connection,
) -> None:
    """An edit does not collide with the task it is editing."""
    identity = create_task(writing, title=TITLE, deadline=DEADLINE)

    conflict = storage.find_conflicting_task(
        writing,
        title_key=title_key(EQUIVALENT_TITLE),
        deadline=DEADLINE,
        excluded_task_id=identity,
    )

    assert conflict is None


def test_an_undated_comparison_excludes_the_supplied_identity(
    writing: sqlite3.Connection,
) -> None:
    """An undated edit does not collide with its own task."""
    identity = create_task(writing, title=TITLE, deadline=None)

    conflict = storage.find_conflicting_task(
        writing,
        title_key=title_key(EQUIVALENT_TITLE),
        deadline=None,
        excluded_task_id=identity,
    )

    assert conflict is None


def test_excluding_one_identity_still_finds_another_conflict(
    writing: sqlite3.Connection,
) -> None:
    """Self-exclusion removes one task, not the whole comparison."""
    edited = create_task(writing, title=PLAIN_TITLE, deadline=DEADLINE)
    other = insert_fixture_task(
        writing, title=EQUIVALENT_TITLE, deadline=DEADLINE
    )

    conflict = storage.find_conflicting_task(
        writing,
        title_key=title_key(TITLE),
        deadline=DEADLINE,
        excluded_task_id=edited,
    )

    assert conflict == other


def test_a_free_dated_state_reports_no_conflict(
    writing: sqlite3.Connection,
) -> None:
    """A title nothing else holds on that date is free."""
    create_task(writing, title=PLAIN_TITLE, deadline=DEADLINE)

    conflict = storage.find_conflicting_task(
        writing, title_key=title_key(TITLE), deadline=DEADLINE
    )

    assert conflict is None
