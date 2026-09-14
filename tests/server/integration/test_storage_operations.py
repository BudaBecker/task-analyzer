"""Integration tests for the operation result ledger.

Covers PCE-37 through PCE-43; REQ-010, REQ-031.

Every test opens a newly allocated temporary database file created by
the explicit initializer. No test reads
``TASK_ANALYZER_DATABASE_PATH`` or touches any configured runtime
database.

Delivery 1A has no deletion command, so the test that proves a retained
result outlives its task removes the task row directly.
"""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime
from importlib import resources
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from task_analyzer_server import schema, storage
from task_analyzer_server.clock import to_utc_microseconds
from task_analyzer_server.contracts import (
    ErrorCode,
    FieldErrorCode,
    OperationError,
    OperationResult,
    TaskSnapshot,
    ValidationIssue,
)
from task_analyzer_server.domain import title_key

BUSY_TIMEOUT_MS = 5000

TITLE = "Read notes"
DEADLINE = date(2026, 9, 14)
CREATED_AT = datetime(2026, 9, 13, 12, 0, 0, 123456, tzinfo=UTC)
RESOLVED_AT = datetime(2026, 9, 13, 12, 0, 0, 654321, tzinfo=UTC)
LONG_PAST = datetime(1, 1, 1, 0, 0, 0, tzinfo=UTC)

CANONICAL_REQUEST = (
    'v1|POST|/v1/tasks|{"deadline":"2026-09-14",'
    '"observations":null,"title":"Read notes"}'
)
ANOTHER_CANONICAL_REQUEST = (
    'v1|POST|/v1/tasks|{"deadline":"2026-09-15",'
    '"observations":null,"title":"Read notes"}'
)

READ_LEDGER_COLUMNS = (
    "SELECT outcome, http_status, resolved_at_us, canonical_request"
    " FROM operation_results WHERE operation_id = ?"
)
DELETE_TASK_ROW = "DELETE FROM tasks WHERE task_id = ?"
COUNT_LEDGER_ROWS = "SELECT COUNT(*) FROM operation_results"


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


def success_result(
    operation_id: UUID,
    task_id: UUID,
    resolved_at: datetime = RESOLVED_AT,
) -> OperationResult:
    """Build the terminal result of an accepted creation.

    Args:
        operation_id: Identity of the resolved operation.
        task_id: Identity of the created task.
        resolved_at: When the server settled the outcome.

    Returns:
        The success result to retain.
    """
    return OperationResult(
        operation_id=operation_id,
        outcome="succeeded",
        original_http_status=201,
        task=TaskSnapshot(
            task_id=task_id,
            title=TITLE,
            observations=None,
            deadline=DEADLINE,
            status="pending",
            created_at=CREATED_AT,
            completed_at=None,
        ),
        error=None,
        resolved_at=resolved_at,
    )


def rejection_result(
    operation_id: UUID, conflicting_task_id: UUID
) -> OperationResult:
    """Build the terminal result of a uniqueness rejection.

    Args:
        operation_id: Identity of the resolved operation.
        conflicting_task_id: The task the attempt collided with.

    Returns:
        The rejection result to retain.
    """
    return OperationResult(
        operation_id=operation_id,
        outcome="rejected",
        original_http_status=409,
        task=None,
        error=OperationError(
            code=ErrorCode.TASK_UNIQUENESS_CONFLICT,
            fields=(
                ValidationIssue(
                    field="title", code=FieldErrorCode.TITLE_REQUIRED
                ),
            ),
            conflicting_task_id=conflicting_task_id,
        ),
        resolved_at=RESOLVED_AT,
    )


def retain(
    path: Path,
    operation_id: UUID,
    result: OperationResult,
    canonical_request: str = CANONICAL_REQUEST,
) -> None:
    """Retain one result through its own committed transaction.

    Args:
        path: Database file to write.
        operation_id: Identity of the resolved operation.
        result: The terminal result to retain.
        canonical_request: The canonical request text to retain.
    """
    with storage.open_connection(path, BUSY_TIMEOUT_MS) as connection:
        with storage.write_transaction(connection):
            storage.write_operation(
                connection,
                operation_id=operation_id,
                canonical_request=canonical_request,
                result=result,
            )


def consult(path: Path, operation_id: UUID) -> storage.StoredOperation | None:
    """Read one retained result through a separate new connection.

    Args:
        path: Database file to read.
        operation_id: Identity of the operation to consult.

    Returns:
        The retained result, or ``None`` when the outcome is unknown.
    """
    with storage.open_connection(path, BUSY_TIMEOUT_MS) as connection:
        return storage.read_operation(connection, operation_id)


def storage_source() -> str:
    """Read the source of the storage module.

    Returns:
        The text of ``storage.py`` as it is packaged.
    """
    package_files = resources.files(schema.PACKAGE_NAME)
    return package_files.joinpath("storage.py").read_text(encoding="utf-8")


def test_an_unknown_operation_reports_absence(
    database_path: Path,
) -> None:
    """No committed row means the outcome is not established."""
    assert consult(database_path, uuid4()) is None


def test_an_unknown_operation_is_not_a_rejection(
    database_path: Path,
) -> None:
    """Absence stays distinguishable from a retained rejection."""
    rejected = uuid4()
    retain(database_path, rejected, rejection_result(rejected, uuid4()))

    unknown = consult(database_path, uuid4())
    established = consult(database_path, rejected)

    assert unknown is None
    assert established is not None
    assert established.result.outcome == "rejected"


def test_a_retained_success_reads_back_field_for_field(
    database_path: Path,
) -> None:
    """A success is returned exactly as it was retained."""
    operation_id = uuid4()
    result = success_result(operation_id, uuid4())

    retain(database_path, operation_id, result)

    stored = consult(database_path, operation_id)
    assert stored is not None
    assert stored.result == result


def test_a_retained_rejection_reads_back_field_for_field(
    database_path: Path,
) -> None:
    """A rejection keeps its code, fields and conflicting identity."""
    operation_id = uuid4()
    conflicting = uuid4()
    result = rejection_result(operation_id, conflicting)

    retain(database_path, operation_id, result)

    stored = consult(database_path, operation_id)
    assert stored is not None
    assert stored.result == result
    assert stored.result.error is not None
    assert stored.result.error.conflicting_task_id == conflicting


def test_the_canonical_request_is_retained_as_its_own_text(
    database_path: Path,
) -> None:
    """Equality is decided against the retained text itself."""
    operation_id = uuid4()
    retain(database_path, operation_id, success_result(operation_id, uuid4()))

    stored = consult(database_path, operation_id)

    assert stored is not None
    assert stored.canonical_request == CANONICAL_REQUEST
    assert stored.canonical_request != ANOTHER_CANONICAL_REQUEST


def test_the_terminal_columns_carry_the_outcome_and_status(
    writing: sqlite3.Connection,
) -> None:
    """Outcome, original status and resolution time are stored."""
    operation_id = uuid4()
    storage.write_operation(
        writing,
        operation_id=operation_id,
        canonical_request=CANONICAL_REQUEST,
        result=success_result(operation_id, uuid4()),
    )

    row = writing.execute(READ_LEDGER_COLUMNS, (str(operation_id),)).fetchone()

    assert row[0] == "succeeded"
    assert row[1] == 201
    assert row[2] == to_utc_microseconds(RESOLVED_AT)
    assert row[3] == CANONICAL_REQUEST


def test_a_committed_result_is_readable_by_a_new_connection(
    database_path: Path,
) -> None:
    """A retained result outlives the connection that wrote it."""
    operation_id = uuid4()
    result = success_result(operation_id, uuid4())

    retain(database_path, operation_id, result)

    stored = consult(database_path, operation_id)
    assert stored is not None
    assert stored.result.task is not None
    assert stored.result.task.created_at == CREATED_AT


def test_a_result_is_written_inside_the_callers_transaction(
    database_path: Path,
) -> None:
    """A rolled-back operation establishes no outcome at all."""
    operation_id = uuid4()

    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        with pytest.raises(RuntimeError, match="injected"):
            with storage.write_transaction(connection):
                storage.write_operation(
                    connection,
                    operation_id=operation_id,
                    canonical_request=CANONICAL_REQUEST,
                    result=success_result(operation_id, uuid4()),
                )
                raise RuntimeError("injected storage failure")

    assert consult(database_path, operation_id) is None


def test_a_second_write_for_one_identity_is_refused(
    database_path: Path,
) -> None:
    """One operation identity can resolve only once."""
    operation_id = uuid4()
    retain(database_path, operation_id, success_result(operation_id, uuid4()))

    with pytest.raises(sqlite3.IntegrityError):
        retain(
            database_path,
            operation_id,
            rejection_result(operation_id, uuid4()),
            canonical_request=ANOTHER_CANONICAL_REQUEST,
        )


def test_a_refused_second_write_preserves_the_original_result(
    database_path: Path,
) -> None:
    """The first retained result survives a later write attempt."""
    operation_id = uuid4()
    original = success_result(operation_id, uuid4())
    retain(database_path, operation_id, original)

    with pytest.raises(sqlite3.IntegrityError):
        retain(
            database_path,
            operation_id,
            rejection_result(operation_id, uuid4()),
            canonical_request=ANOTHER_CANONICAL_REQUEST,
        )

    stored = consult(database_path, operation_id)
    assert stored is not None
    assert stored.result == original
    assert stored.canonical_request == CANONICAL_REQUEST


def test_a_retained_result_outlives_its_task(
    database_path: Path,
) -> None:
    """No cascade removes a result when its task row disappears."""
    operation_id = uuid4()
    task_id = uuid4()
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        with storage.write_transaction(connection):
            storage.insert_task(
                connection,
                task_id=task_id,
                title=TITLE,
                title_key=title_key(TITLE),
                observations=None,
                deadline=DEADLINE,
                created_at=CREATED_AT,
            )
            storage.write_operation(
                connection,
                operation_id=operation_id,
                canonical_request=CANONICAL_REQUEST,
                result=success_result(operation_id, task_id),
            )

    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        with storage.write_transaction(connection):
            connection.execute(DELETE_TASK_ROW, (str(task_id),))

    stored = consult(database_path, operation_id)
    assert stored is not None
    assert stored.result.task is not None
    assert stored.result.task.task_id == task_id


def test_the_ledger_carries_no_foreign_key_to_tasks(
    database_path: Path,
) -> None:
    """The ledger depends on no other table's rows."""
    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        references = connection.execute(
            "PRAGMA foreign_key_list('operation_results')"
        ).fetchall()

    assert references == []


def test_a_long_past_result_is_retained_without_expiry(
    database_path: Path,
) -> None:
    """Retention has no time limit, so no repetition becomes new."""
    operation_id = uuid4()
    result = success_result(operation_id, uuid4(), resolved_at=LONG_PAST)

    retain(database_path, operation_id, result)

    stored = consult(database_path, operation_id)
    assert stored is not None
    assert stored.result.resolved_at == LONG_PAST


def test_storage_never_updates_or_deletes_a_retained_result() -> None:
    """No statement in the module can rewrite or purge the ledger."""
    source = storage_source().lower()

    assert "update operation_results" not in source
    assert "delete from operation_results" not in source


def test_retaining_two_operations_keeps_both_rows(
    database_path: Path,
) -> None:
    """Distinct operations each keep their own retained result."""
    first = uuid4()
    second = uuid4()
    retain(database_path, first, success_result(first, uuid4()))
    retain(
        database_path,
        second,
        rejection_result(second, uuid4()),
        canonical_request=ANOTHER_CANONICAL_REQUEST,
    )

    with storage.open_connection(database_path, BUSY_TIMEOUT_MS) as connection:
        total = connection.execute(COUNT_LEDGER_ROWS).fetchone()[0]

    assert total == 2
    assert consult(database_path, first) is not None
    assert consult(database_path, second) is not None
