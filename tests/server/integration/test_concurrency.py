"""Integration tests for concurrency and injected failures.

Covers PCE-19, PCE-20, PCE-27, PCE-37, PCE-39, PCE-42, PCE-43;
REQ-010, REQ-029, REQ-031.

Overlapping work runs on independent connections: each service call
opens its own, so two threads competing here compete the way two
requests do. Nothing is synchronized by waiting a while. Threads meet on
a barrier, and a helper process announces on its own pipe that it holds
the write transaction, so every ordering this suite depends on is one
the test established rather than one it hoped for.

Stopping a process is a real stop. The helper is killed while its
transaction is open, which leaves the database to recover exactly as it
would after the server died mid-write.

Disposable-database machinery is shared with the durability suite.
"""

import sqlite3
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_durability import initialized_database

from task_analyzer_server import services, storage
from task_analyzer_server.contracts import (
    ErrorCode,
    OperationRequest,
    OperationResult,
)
from task_analyzer_server.settings import ServerSettings

BUSY_TIMEOUT_MS = 5000
IMPATIENT_TIMEOUT_MS = 50

READY_TIMEOUT_SECONDS = 60.0

PRODUCT_ZONE = "America/Sao_Paulo"
SERVER_NOW = datetime(2026, 9, 14, 12, 0, 0, 123456, tzinfo=UTC)

TASKS_TARGET = "/v1/tasks"
TASK_TITLE = "Read notes"
OTHER_TITLE = "Review the draft"
HELD_TITLE = "Held by the stopped process"
DEADLINE = "2026-09-14"

COMMITTED_EXIT_CODE = 9

COUNT_TASKS = "SELECT COUNT(*) FROM tasks WHERE is_deleted = 0"
COUNT_RESULTS = "SELECT COUNT(*) FROM operation_results"

HOLDER_PROGRAM = '''"""Hold one uncommitted write transaction open.

The rows below are written inside the transaction and never committed.
The process announces that it holds the write lock and then blocks, so
the test decides when it stops.
"""

import sys
from pathlib import Path

from task_analyzer_server import storage

INSERT_TASK = (
    "INSERT INTO tasks (task_id, title, title_key, observations,"
    " deadline_date, status, created_at_us, latest_completed_at_us,"
    " is_deleted) VALUES (?, ?, ?, NULL, NULL, 'pending', 0, NULL, 0)"
)
INSERT_RESULT = (
    "INSERT INTO operation_results (operation_id, canonical_request,"
    " outcome, http_status, serialized_result, resolved_at_us)"
    " VALUES (?, 'held', 'succeeded', 201, '{}', 0)"
)

database, operation_id, task_id, title = sys.argv[1:5]
with storage.open_connection(Path(database), 5000) as connection:
    connection.execute("BEGIN IMMEDIATE")
    connection.execute(INSERT_TASK, (task_id, title, title))
    connection.execute(INSERT_RESULT, (operation_id,))
    print("ready", flush=True)
    sys.stdin.readline()
'''

COMMITTER_PROGRAM = '''"""Commit one creation, then stop before answering.

The process ends the moment the operation is committed, so no response
can reach anyone. The outcome must still be discoverable afterwards.
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from task_analyzer_server import services
from task_analyzer_server.contracts import OperationRequest
from task_analyzer_server.settings import ServerSettings


class FrozenClock:
    """A clock reporting one instant."""

    def now(self) -> datetime:
        """Read that instant.

        Returns:
            The instant this clock always reports.
        """
        return datetime(2026, 9, 14, 12, 0, 0, 123456, tzinfo=UTC)


database, operation_id, title = sys.argv[1:4]
services.create_task(
    ServerSettings(
        database_path=Path(database),
        log_level="INFO",
        db_busy_timeout_ms=5000,
    ),
    FrozenClock(),
    OperationRequest(
        operation_id=UUID(operation_id),
        method="POST",
        target="/v1/tasks",
        payload={"title": title},
    ),
)
os._exit(9)
'''


class FixedClock:
    """A clock reporting one instant, in one representation."""

    def now(self) -> datetime:
        """Read the fixed instant.

        Returns:
            The instant this clock always reports.
        """
        return SERVER_NOW


def settings_for(
    database: Path, busy_timeout_ms: int = BUSY_TIMEOUT_MS
) -> ServerSettings:
    """Build settings naming one disposable database.

    Args:
        database: Path of the disposable database.
        busy_timeout_ms: Bounded wait for a busy lock.

    Returns:
        Settings for that file.
    """
    return ServerSettings(
        database_path=database,
        log_level="INFO",
        db_busy_timeout_ms=busy_timeout_ms,
    )


@pytest.fixture
def database(tmp_path: Path) -> Path:
    """Allocate a disposable database with the product zone fixed.

    Args:
        tmp_path: pytest-allocated temporary directory.

    Returns:
        Path of the newly created database file.
    """
    target = initialized_database(tmp_path)
    services.configure_zone(settings_for(target), FixedClock(), PRODUCT_ZONE)
    return target


@pytest.fixture
def settings(database: Path) -> ServerSettings:
    """Build settings naming the disposable database.

    Args:
        database: Path of the disposable database.

    Returns:
        Settings for that file.
    """
    return settings_for(database)


def creation(operation_id: UUID, payload: object) -> OperationRequest:
    """Build one submitted creation operation.

    Args:
        operation_id: Identity of the attempt.
        payload: The submitted task payload.

    Returns:
        The submitted operation and its envelope values.
    """
    return OperationRequest(
        operation_id=operation_id,
        method="POST",
        target=TASKS_TARGET,
        payload=payload,
    )


def run_together(
    first: Callable[[], OperationResult],
    second: Callable[[], OperationResult],
) -> tuple[object, object]:
    """Run two attempts that enter the server at the same moment.

    Both threads wait on one barrier and are released together, so the
    overlap is established by the test rather than by timing.

    Args:
        first: The first attempt.
        second: The second attempt.

    Returns:
        What each attempt produced, which is its result or the exception
        it raised.
    """
    barrier = threading.Barrier(2)
    outcomes: dict[int, object] = {}

    def run(index: int, attempt: Callable[[], OperationResult]) -> None:
        """Run one attempt once both threads are ready.

        Args:
            index: Which attempt this is.
            attempt: The attempt to run.
        """
        barrier.wait()
        try:
            outcomes[index] = attempt()
        except BaseException as failure:
            outcomes[index] = failure

    threads = [
        threading.Thread(target=run, args=(index, attempt))
        for index, attempt in enumerate((first, second))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return outcomes[0], outcomes[1]


@contextmanager
def holding_write_lock(
    database: Path, workspace: Path, operation_id: UUID, task_id: UUID
) -> Iterator["subprocess.Popen[str]"]:
    """Run a helper that holds an uncommitted write transaction.

    The helper announces readiness on its own pipe, so the block runs
    only once the write lock is genuinely held.

    Args:
        database: The disposable database to lock.
        workspace: Directory to write the helper program in.
        operation_id: Identity the helper writes a result for.
        task_id: Identity the helper writes a task for.

    Yields:
        The running helper process.

    Raises:
        AssertionError: If the helper never reports that it is ready.
    """
    program = workspace / "hold_transaction.py"
    program.write_text(HOLDER_PROGRAM, encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            str(program),
            str(database),
            str(operation_id),
            str(task_id),
            HELD_TITLE,
        ],
        cwd=str(workspace),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        announcement = process.stdout.readline()
        assert announcement.strip() == "ready", (
            "The helper never took the write lock:"
            f" {'' if process.stderr is None else process.stderr.read()}"
        )
        yield process
    finally:
        process.kill()
        process.wait(timeout=READY_TIMEOUT_SECONDS)


def commit_then_stop(
    database: Path, workspace: Path, operation_id: UUID, title: str
) -> int:
    """Run a helper that commits one creation and then stops.

    Args:
        database: The disposable database to write to.
        workspace: Directory to write the helper program in.
        operation_id: Identity of the attempt.
        title: Title of the task to create.

    Returns:
        The exit code the helper stopped with.
    """
    program = workspace / "commit_then_stop.py"
    program.write_text(COMMITTER_PROGRAM, encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(program),
            str(database),
            str(operation_id),
            title,
        ],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=READY_TIMEOUT_SECONDS,
        check=False,
    )
    assert completed.returncode == COMMITTED_EXIT_CODE, (
        f"The helper stopped with {completed.returncode}:"
        f" {completed.stdout}{completed.stderr}"
    )
    return completed.returncode


def counted(database: Path, statement: str) -> int:
    """Count rows through a separate new connection.

    Args:
        database: Path of the disposable database.
        statement: The counting statement to run.

    Returns:
        The counted rows.
    """
    with storage.open_connection(database, BUSY_TIMEOUT_MS) as connection:
        return int(connection.execute(statement).fetchone()[0])


def accepted_and_rejected(
    outcomes: tuple[object, object],
) -> tuple[OperationResult, OperationResult]:
    """Split two results into the accepted and the rejected one.

    Args:
        outcomes: What the two attempts produced.

    Returns:
        The accepted result and the rejected one.

    Raises:
        AssertionError: If the pair is not exactly one of each.
    """
    results = [item for item in outcomes if isinstance(item, OperationResult)]
    assert len(results) == 2, f"Both attempts must settle: {outcomes}"
    succeeded = [item for item in results if item.outcome == "succeeded"]
    rejected = [item for item in results if item.outcome == "rejected"]
    assert len(succeeded) == 1
    assert len(rejected) == 1
    return succeeded[0], rejected[0]


def test_two_copies_of_one_attempt_create_one_task(
    settings: ServerSettings, database: Path
) -> None:
    """One attempt sent twice at once is applied once."""
    identity = uuid4()
    payload = {"title": TASK_TITLE, "deadline": DEADLINE}

    run_together(
        lambda: services.create_task(
            settings, FixedClock(), creation(identity, payload)
        ),
        lambda: services.create_task(
            settings, FixedClock(), creation(identity, payload)
        ),
    )

    assert counted(database, COUNT_TASKS) == 1


def test_two_copies_of_one_attempt_report_the_same_result(
    settings: ServerSettings,
) -> None:
    """The second copy observes the first copy's terminal result."""
    identity = uuid4()
    payload = {"title": TASK_TITLE, "deadline": DEADLINE}

    first, second = run_together(
        lambda: services.create_task(
            settings, FixedClock(), creation(identity, payload)
        ),
        lambda: services.create_task(
            settings, FixedClock(), creation(identity, payload)
        ),
    )

    assert isinstance(first, OperationResult)
    assert isinstance(second, OperationResult)
    assert first == second
    assert first.outcome == "succeeded"


def test_two_copies_of_one_attempt_retain_one_result(
    settings: ServerSettings, database: Path
) -> None:
    """One attempt leaves one retained outcome, not two."""
    identity = uuid4()
    payload = {"title": TASK_TITLE}

    run_together(
        lambda: services.create_task(
            settings, FixedClock(), creation(identity, payload)
        ),
        lambda: services.create_task(
            settings, FixedClock(), creation(identity, payload)
        ),
    )

    assert counted(database, COUNT_RESULTS) == 1


def test_two_conflicting_operations_accept_one_task_at_most(
    settings: ServerSettings, database: Path
) -> None:
    """Two different operations cannot both take one title and date."""
    payload = {"title": TASK_TITLE, "deadline": DEADLINE}

    outcomes = run_together(
        lambda: services.create_task(
            settings, FixedClock(), creation(uuid4(), payload)
        ),
        lambda: services.create_task(
            settings, FixedClock(), creation(uuid4(), payload)
        ),
    )
    accepted, _ = accepted_and_rejected(outcomes)

    assert counted(database, COUNT_TASKS) == 1
    assert accepted.task is not None


def test_the_refused_conflicting_operation_names_the_conflict(
    settings: ServerSettings,
) -> None:
    """The refused operation is a uniqueness rejection, not a success."""
    payload = {"title": TASK_TITLE, "deadline": DEADLINE}

    outcomes = run_together(
        lambda: services.create_task(
            settings, FixedClock(), creation(uuid4(), payload)
        ),
        lambda: services.create_task(
            settings, FixedClock(), creation(uuid4(), payload)
        ),
    )
    accepted, rejected = accepted_and_rejected(outcomes)

    assert rejected.error is not None
    assert rejected.error.code == ErrorCode.TASK_UNIQUENESS_CONFLICT
    assert accepted.task is not None
    assert rejected.error.conflicting_task_id == accepted.task.task_id


def test_a_conflicting_operation_is_not_treated_as_a_replay(
    settings: ServerSettings, database: Path
) -> None:
    """A matching title never makes one operation another's repetition."""
    first_id = uuid4()
    second_id = uuid4()
    payload = {"title": TASK_TITLE, "deadline": DEADLINE}

    outcomes = run_together(
        lambda: services.create_task(
            settings, FixedClock(), creation(first_id, payload)
        ),
        lambda: services.create_task(
            settings, FixedClock(), creation(second_id, payload)
        ),
    )
    accepted, rejected = accepted_and_rejected(outcomes)

    assert {accepted.operation_id, rejected.operation_id} == {
        first_id,
        second_id,
    }
    assert counted(database, COUNT_RESULTS) == 2


def test_a_stop_before_commit_leaves_no_committed_task(
    database: Path, tmp_path: Path
) -> None:
    """Work that never committed leaves no task behind."""
    with holding_write_lock(database, tmp_path, uuid4(), uuid4()):
        pass

    assert counted(database, COUNT_TASKS) == 0


def test_a_stop_before_commit_leaves_no_committed_result(
    database: Path, tmp_path: Path
) -> None:
    """Work that never committed leaves no outcome behind either."""
    with holding_write_lock(database, tmp_path, uuid4(), uuid4()):
        pass

    assert counted(database, COUNT_RESULTS) == 0


def test_the_same_attempt_still_settles_after_a_stop(
    settings: ServerSettings, database: Path, tmp_path: Path
) -> None:
    """Repeating the stopped attempt can still establish its result."""
    identity = uuid4()
    with holding_write_lock(database, tmp_path, identity, uuid4()):
        pass

    result = services.create_task(
        settings, FixedClock(), creation(identity, {"title": TASK_TITLE})
    )

    assert result.outcome == "succeeded"
    assert services.lookup_operation(settings, identity) == result
    assert counted(database, COUNT_TASKS) == 1


def test_an_outcome_committed_before_a_stop_is_discoverable(
    settings: ServerSettings, database: Path, tmp_path: Path
) -> None:
    """A response nobody received does not undo what was committed."""
    identity = uuid4()

    commit_then_stop(database, tmp_path, identity, TASK_TITLE)
    retained = services.lookup_operation(settings, identity)

    assert retained is not None
    assert retained.outcome == "succeeded"
    assert counted(database, COUNT_TASKS) == 1


def test_a_committed_outcome_is_not_applied_twice(
    settings: ServerSettings, database: Path, tmp_path: Path
) -> None:
    """Repeating an attempt that already committed changes nothing."""
    identity = uuid4()
    commit_then_stop(database, tmp_path, identity, TASK_TITLE)
    retained = services.lookup_operation(settings, identity)

    repeated = services.create_task(
        settings, FixedClock(), creation(identity, {"title": TASK_TITLE})
    )

    assert repeated == retained
    assert counted(database, COUNT_TASKS) == 1
    assert counted(database, COUNT_RESULTS) == 1


def test_a_lock_timeout_is_an_infrastructure_failure(
    database: Path, tmp_path: Path
) -> None:
    """A writer that cannot take the lock reports that, not an outcome."""
    impatient = settings_for(database, IMPATIENT_TIMEOUT_MS)

    with holding_write_lock(database, tmp_path, uuid4(), uuid4()):
        with pytest.raises(sqlite3.OperationalError) as failure:
            services.create_task(
                impatient,
                FixedClock(),
                creation(uuid4(), {"title": OTHER_TITLE}),
            )

    assert not isinstance(failure.value, services.ProtocolRefusalError)


def test_a_lock_timeout_establishes_no_terminal_result(
    database: Path, tmp_path: Path
) -> None:
    """The blocked attempt leaves nothing retained under its identity."""
    impatient = settings_for(database, IMPATIENT_TIMEOUT_MS)
    identity = uuid4()

    with holding_write_lock(database, tmp_path, uuid4(), uuid4()):
        with pytest.raises(sqlite3.OperationalError):
            services.create_task(
                impatient,
                FixedClock(),
                creation(identity, {"title": OTHER_TITLE}),
            )

    assert services.lookup_operation(impatient, identity) is None
    assert counted(database, COUNT_TASKS) == 0


def test_lookup_during_in_flight_work_is_unknown_not_rejected(
    settings: ServerSettings, database: Path, tmp_path: Path
) -> None:
    """While work is in flight its outcome is unknown, never refused."""
    identity = uuid4()

    with holding_write_lock(database, tmp_path, identity, uuid4()):
        in_flight = services.lookup_operation(settings, identity)

    assert in_flight is None
