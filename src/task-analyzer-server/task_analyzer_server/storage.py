"""SQLite access for the Task Analyzer server.

Covers PCE-11 through PCE-14, PCE-19 through PCE-25, PCE-29 and PCE-35
through PCE-43 (REQ-008, REQ-010, REQ-028, REQ-029, REQ-031).

This module owns every connection, statement, and transaction boundary.
Callers receive an open connection for the duration of one synchronous
call and nothing outlives it: there is no shared global connection, no
connection cached on a module attribute, and no transaction left open
across an HTTP response.

Durability is stated explicitly and then verified. SQLite ignores an
unknown pragma silently, so a misspelling would otherwise leave a
journal mode or a synchronization level weaker than the approved policy
with no visible sign. Every applied pragma is therefore read back, and a
mismatch fails loudly instead of being persisted against.

Transactions are explicit. The connection runs with
``isolation_level=None`` under legacy transaction control, so the driver
opens no transaction of its own and the version-specific default cannot
change what a statement does. Every write runs inside ``BEGIN
IMMEDIATE``, which takes the write lock up front, so a ledger check and
a uniqueness check made under it cannot be overtaken by a competing
writer. ``executescript()`` is never used here because it commits any
open transaction.

A failed commit is an error, never persistence: the failure propagates,
an active transaction is rolled back, and the connection is closed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from task_analyzer_server.clock import (
    from_utc_microseconds,
    to_utc_microseconds,
)
from task_analyzer_server.contracts import OperationResult, TaskSnapshot

BEGIN_IMMEDIATE = "BEGIN IMMEDIATE"
COMMIT = "COMMIT"

EXISTING_FILE_MODE = "mode=rw"

BUSY_TIMEOUT_PRAGMA = "busy_timeout"

DURABILITY_PRAGMAS: tuple[tuple[str, str, str | int], ...] = (
    ("journal_mode", "DELETE", "delete"),
    ("synchronous", "EXTRA", 3),
    ("foreign_keys", "ON", 1),
)
"""Pragma name, the setting applied, and the value expected back.

``synchronous`` reports the numeric level, where ``3`` is ``EXTRA``, and
``foreign_keys`` reports ``1`` when enforcement is on.
"""


READ_PRODUCT_TIME_ZONE = (
    "SELECT product_time_zone FROM product_configuration"
    " WHERE configuration_id = 1"
)
INSERT_PRODUCT_TIME_ZONE = (
    "INSERT INTO product_configuration"
    " (configuration_id, product_time_zone) VALUES (1, ?)"
)


INSERT_TASK = (
    "INSERT INTO tasks ("
    " task_id, title, title_key, observations, deadline_date,"
    " status, created_at_us, latest_completed_at_us, is_deleted"
    ") VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL, 0)"
)
UPDATE_TASK = (
    "UPDATE tasks SET title = ?, title_key = ?, observations = ?,"
    " deadline_date = ? WHERE task_id = ? AND is_deleted = 0"
)
READ_TASK = (
    "SELECT task_id, title, observations, deadline_date, status,"
    " created_at_us, latest_completed_at_us FROM tasks"
    " WHERE task_id = ? AND is_deleted = 0"
)
READ_TASKS = (
    "SELECT task_id, title, observations, deadline_date, status,"
    " created_at_us, latest_completed_at_us FROM tasks"
    " WHERE is_deleted = 0"
)
FIND_DATED_CONFLICT = (
    "SELECT task_id FROM tasks"
    " WHERE is_deleted = 0 AND deadline_date = ? AND title_key = ?"
    " AND task_id IS NOT ? LIMIT 1"
)
FIND_UNDATED_CONFLICT = (
    "SELECT task_id FROM tasks"
    " WHERE is_deleted = 0 AND deadline_date IS NULL"
    " AND status = 'pending' AND title_key = ?"
    " AND task_id IS NOT ? LIMIT 1"
)


READ_OPERATION = (
    "SELECT canonical_request, serialized_result FROM operation_results"
    " WHERE operation_id = ?"
)
INSERT_OPERATION = (
    "INSERT INTO operation_results ("
    " operation_id, canonical_request, outcome, http_status,"
    " serialized_result, resolved_at_us"
    ") VALUES (?, ?, ?, ?, ?, ?)"
)


@dataclass(frozen=True, slots=True)
class StoredOperation:
    """One retained terminal operation result and its request.

    Attributes:
        canonical_request: The canonical request text exactly as it was
            stored, so a repeated attempt is compared against the text
            itself rather than against a digest of it.
        result: The terminal result as it was serialized when the
            operation resolved. It is evidence of what happened then,
            never a reading of current task state.
    """

    canonical_request: str
    result: OperationResult


class TaskNotStoredError(LookupError):
    """Raised when a write reached no managed task row.

    The caller decides whether an absent target is a rejection, so this
    means the row disappeared from under a write that had already found
    it, which the held write transaction is meant to prevent.
    """


class ZoneOutcome(StrEnum):
    """What a compare-and-set attempt found on the singleton row.

    Attributes:
        STORED: The singleton was unset and now holds the requested key.
        ALREADY_SET: The singleton already held exactly that key.
        CONFLICTING: The singleton already held a different key, which
            was kept.
    """

    STORED = "stored"
    ALREADY_SET = "already_set"
    CONFLICTING = "conflicting"


@dataclass(frozen=True, slots=True)
class ConfiguredZone:
    """The product time zone after a compare-and-set attempt.

    Attributes:
        outcome: What the attempt found on the singleton row.
        product_time_zone: The retained IANA key once the attempt
            finished. It is the requested key except when the outcome
            is ``CONFLICTING``.
    """

    outcome: ZoneOutcome
    product_time_zone: str


class DurabilityPolicyError(RuntimeError):
    """Raised when a connection does not report the approved policy.

    The message names the pragma and both values, so an operator sees
    which setting was ignored rather than a generic storage failure.
    """


@contextmanager
def open_connection(
    path: Path, busy_timeout_ms: int
) -> Iterator[sqlite3.Connection]:
    """Open one connection to an existing database for one call.

    The database file must already exist: the connection opens in
    read/write mode without creation, so a running server can never
    bring a database into being by pointing at a missing path.

    On leaving the block an active transaction is rolled back and the
    connection is closed, including when the body raised. Nothing is
    reachable afterwards, which is what keeps connection ownership
    inside the synchronous call that opened it.

    Args:
        path: Absolute path of the database file.
        busy_timeout_ms: Bounded wait, in milliseconds, for a busy lock.

    Yields:
        The open connection, already verified against the policy.

    Raises:
        ValueError: If the path is not absolute.
        DurabilityPolicyError: If an applied pragma does not read back
            as the approved policy.
        sqlite3.Error: If the database cannot be opened.
    """
    connection = _open(path, busy_timeout_ms)
    try:
        yield connection
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


@contextmanager
def write_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """Run the body inside one immediate write transaction.

    The write lock is taken before the body runs, so every check the
    body makes and every row it writes belong to the same serialized
    write. The body's work becomes durable only when the commit itself
    succeeds; a failing commit rolls back and propagates, and is never
    translated into successful persistence.

    Args:
        connection: An open connection from :func:`open_connection`.

    Yields:
        ``None``, once the write lock is held.

    Raises:
        sqlite3.Error: If the transaction cannot be started, if the body
            fails, or if the commit fails.
    """
    connection.execute(BEGIN_IMMEDIATE)
    try:
        yield
        connection.execute(COMMIT)
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise


def read_product_time_zone(connection: sqlite3.Connection) -> str | None:
    """Read the retained product time zone.

    Args:
        connection: An open connection from :func:`open_connection`.

    Returns:
        The retained IANA key, or ``None`` when the singleton is unset.
        An unconfigured database reports its absence; no zone is ever
        invented for it.
    """
    row = connection.execute(READ_PRODUCT_TIME_ZONE).fetchone()
    return None if row is None else str(row[0])


def store_product_time_zone(
    connection: sqlite3.Connection, zone_key: str
) -> ConfiguredZone:
    """Set the product time zone only while the singleton is unset.

    This is a compare-and-set: the caller holds the write transaction
    from :func:`write_transaction`, so the read and the insert belong to
    one serialized write. There is no statement anywhere in this module
    that updates or deletes the singleton, so a retained zone cannot be
    replaced even by a defect elsewhere, and the primary key refuses a
    second row should a write ever reach storage without the lock.

    Args:
        connection: An open connection holding the write transaction.
        zone_key: The IANA key the caller wants retained. Validity is
            the caller's business rule, not storage's.

    Returns:
        What the attempt found and the zone retained afterwards.
    """
    retained = read_product_time_zone(connection)
    if retained is None:
        connection.execute(INSERT_PRODUCT_TIME_ZONE, (zone_key,))
        return ConfiguredZone(ZoneOutcome.STORED, zone_key)
    if retained == zone_key:
        return ConfiguredZone(ZoneOutcome.ALREADY_SET, retained)
    return ConfiguredZone(ZoneOutcome.CONFLICTING, retained)


def insert_task(
    connection: sqlite3.Connection,
    *,
    task_id: UUID,
    title: str,
    title_key: str,
    observations: str | None,
    deadline: date | None,
    created_at: datetime,
) -> TaskSnapshot:
    """Store one newly created task.

    Delivery 1A creates pending tasks only, so the row is written as
    pending, undeleted and without a completion timestamp; those three
    columns are part of the statement rather than of the caller's
    request. The comparison key is supplied because it comes from the
    single centralized derivation, which storage never duplicates.

    Args:
        connection: An open connection holding the write transaction.
        task_id: Server-generated identity of the new task.
        title: Submitted title, stored exactly as submitted.
        title_key: The centrally derived comparison key of that title.
        observations: Submitted observations, or ``None``.
        deadline: Submitted deadline date, or ``None``.
        created_at: Original creation instant sampled by the server.

    Returns:
        The task as it is now stored.

    Raises:
        TaskNotStoredError: If the stored row cannot be read back.
    """
    connection.execute(
        INSERT_TASK,
        (
            str(task_id),
            title,
            title_key,
            observations,
            _as_deadline_text(deadline),
            to_utc_microseconds(created_at),
        ),
    )
    return _require_task(connection, task_id)


def update_task(
    connection: sqlite3.Connection,
    *,
    task_id: UUID,
    title: str,
    title_key: str,
    observations: str | None,
    deadline: date | None,
) -> TaskSnapshot:
    """Replace the editable state of one managed task.

    A save replaces every editable field at once, so the statement sets
    all of them plus the derived key. Identity, original creation time,
    status, completion time and the deletion flag are absent from the
    statement, so no edit can move them.

    Args:
        connection: An open connection holding the write transaction.
        task_id: Identity of the task to edit.
        title: Submitted title, stored exactly as submitted.
        title_key: The centrally derived comparison key of that title.
        observations: Submitted observations, or ``None`` to clear.
        deadline: Submitted deadline date, or ``None`` to clear.

    Returns:
        The task as it is now stored.

    Raises:
        TaskNotStoredError: If no managed row carries that identity.
    """
    connection.execute(
        UPDATE_TASK,
        (
            title,
            title_key,
            observations,
            _as_deadline_text(deadline),
            str(task_id),
        ),
    )
    return _require_task(connection, task_id)


def read_task(
    connection: sqlite3.Connection, task_id: UUID
) -> TaskSnapshot | None:
    """Read one managed task.

    Args:
        connection: An open connection from :func:`open_connection`.
        task_id: Identity of the task to read.

    Returns:
        The committed task, or ``None`` when no managed row carries
        that identity. A row excluded from managed tasks reads as
        absent, exactly like one that never existed.
    """
    row = connection.execute(READ_TASK, (str(task_id),)).fetchone()
    return None if row is None else _as_snapshot(row)


def read_tasks(connection: sqlite3.Connection) -> tuple[TaskSnapshot, ...]:
    """Read every managed task.

    Args:
        connection: An open connection from :func:`open_connection`.

    Returns:
        The committed tasks, excluding rows marked deleted. Order is
        not a product guarantee.
    """
    rows = connection.execute(READ_TASKS).fetchall()
    return tuple(_as_snapshot(row) for row in rows)


def find_conflicting_task(
    connection: sqlite3.Connection,
    *,
    title_key: str,
    deadline: date | None,
    excluded_task_id: UUID | None = None,
) -> UUID | None:
    """Find the managed task a proposed state would collide with.

    The two populations are deliberately different. A dated state
    collides with any non-deleted task holding the same comparison key
    on the same deadline date, pending or completed alike. An undated
    state collides only with a non-deleted pending undated task, so
    completing an undated task frees its title. Deleted rows never
    take part, and an edit excludes its own target.

    Args:
        connection: An open connection holding the write transaction,
            so the answer cannot be overtaken by a competing writer.
        title_key: The centrally derived comparison key of the proposed
            title.
        deadline: The proposed deadline date, or ``None`` for an undated
            state.
        excluded_task_id: Identity to leave out of the comparison, which
            is the edited task itself. ``None`` compares against every
            eligible task.

    Returns:
        The identity of the conflicting task, or ``None`` when the
        proposed state is free.
    """
    excluded = None if excluded_task_id is None else str(excluded_task_id)
    if deadline is None:
        row = connection.execute(
            FIND_UNDATED_CONFLICT, (title_key, excluded)
        ).fetchone()
    else:
        row = connection.execute(
            FIND_DATED_CONFLICT,
            (_as_deadline_text(deadline), title_key, excluded),
        ).fetchone()
    return None if row is None else UUID(str(row[0]))


def read_operation(
    connection: sqlite3.Connection, operation_id: UUID
) -> StoredOperation | None:
    """Read the retained result of one operation.

    Args:
        connection: An open connection from :func:`open_connection`.
        operation_id: Identity of the operation to consult.

    Returns:
        The retained result and its canonical request, or ``None`` when
        no committed row carries that identity. ``None`` means the
        outcome is unknown: it is not a rejection, a cancellation, or a
        rollback, and callers must keep that difference.
    """
    row = connection.execute(READ_OPERATION, (str(operation_id),)).fetchone()
    if row is None:
        return None
    return StoredOperation(
        canonical_request=str(row[0]),
        result=OperationResult.model_validate_json(str(row[1])),
    )


def write_operation(
    connection: sqlite3.Connection,
    *,
    operation_id: UUID,
    canonical_request: str,
    result: OperationResult,
) -> None:
    """Retain the terminal result of one operation.

    The row is written inside the caller's transaction, so a result and
    the change it reports become durable together or not at all.

    Retention is permanent: this module carries no statement that
    updates or deletes a retained result, and no expiry sweeps one away.
    A repetition arriving long afterwards therefore still finds its
    original outcome instead of being treated as a new operation. The
    primary key refuses a second row for one identity rather than
    overwriting the first.

    Args:
        connection: An open connection holding the write transaction.
        operation_id: Identity of the resolved operation.
        canonical_request: The canonical request text to retain.
        result: The terminal result to retain.

    Raises:
        sqlite3.IntegrityError: If that identity already carries a
            retained result.
    """
    connection.execute(
        INSERT_OPERATION,
        (
            str(operation_id),
            canonical_request,
            result.outcome,
            result.original_http_status,
            result.model_dump_json(),
            to_utc_microseconds(result.resolved_at),
        ),
    )


def _require_task(
    connection: sqlite3.Connection, task_id: UUID
) -> TaskSnapshot:
    """Read back a task a write has just stored.

    Reading the row back makes the returned snapshot the persisted
    state rather than a restatement of the request.

    Args:
        connection: An open connection holding the write transaction.
        task_id: Identity of the task just written.

    Returns:
        The stored task.

    Raises:
        TaskNotStoredError: If no managed row carries that identity.
    """
    stored = read_task(connection, task_id)
    if stored is None:
        raise TaskNotStoredError(
            f"No managed task {task_id} was stored, so the write"
            " reached no row and its result cannot be reported."
        )
    return stored


def _as_snapshot(row: tuple[Any, ...]) -> TaskSnapshot:
    """Read one stored row as the task the desktop reads.

    Args:
        row: Columns in the order the read statements select them.

    Returns:
        The task that row holds.
    """
    deadline_text = row[3]
    completed_at_us = row[6]
    return TaskSnapshot(
        task_id=UUID(str(row[0])),
        title=str(row[1]),
        observations=None if row[2] is None else str(row[2]),
        deadline=(
            None
            if deadline_text is None
            else date.fromisoformat(str(deadline_text))
        ),
        status=_as_status(row[4]),
        created_at=from_utc_microseconds(int(row[5])),
        completed_at=(
            None
            if completed_at_us is None
            else from_utc_microseconds(int(completed_at_us))
        ),
    )


def _as_status(value: object) -> Literal["pending", "completed"]:
    """Read a stored status column as its contract value.

    Args:
        value: The stored status column.

    Returns:
        The status the task is in.

    Raises:
        ValueError: If the column holds anything else, which the
            table's check constraint is there to prevent.
    """
    if value == "pending":
        return "pending"
    if value == "completed":
        return "completed"
    raise ValueError(f"{value!r} is not a stored task status.")


def _as_deadline_text(deadline: date | None) -> str | None:
    """Write a deadline date in the stored calendar-date spelling.

    Args:
        deadline: The deadline date, or ``None``.

    Returns:
        The ``YYYY-MM-DD`` text, or ``None`` for an undated task.
    """
    return None if deadline is None else deadline.isoformat()


def _open(path: Path, busy_timeout_ms: int) -> sqlite3.Connection:
    """Open and verify one connection under the approved policy.

    Args:
        path: Absolute path of the database file.
        busy_timeout_ms: Bounded wait, in milliseconds, for a busy lock.

    Returns:
        The open connection.

    Raises:
        ValueError: If the path is not absolute.
        DurabilityPolicyError: If an applied pragma does not read back
            as the approved policy. The connection is closed first.
        sqlite3.Error: If the database cannot be opened.
    """
    if not path.is_absolute():
        raise ValueError(
            f"The database path must be absolute; got {str(path)!r}."
            " A relative path would depend on the working directory of"
            " the process."
        )
    # Legacy transaction control is pinned alongside the null isolation
    # level so this module's explicit BEGIN IMMEDIATE, COMMIT and
    # ROLLBACK stay authoritative whatever an interpreter defaults to.
    # The documented sentinel is an integer the stubs declare as a bool.
    connection: sqlite3.Connection
    connection = sqlite3.connect(  # type: ignore[call-overload]
        f"{path.as_uri()}?{EXISTING_FILE_MODE}",
        uri=True,
        isolation_level=None,
        autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,
        check_same_thread=True,
    )
    try:
        _apply_policy(connection, busy_timeout_ms)
    except BaseException:
        connection.close()
        raise
    return connection


def _apply_policy(
    connection: sqlite3.Connection, busy_timeout_ms: int
) -> None:
    """Apply the approved pragmas and confirm each took effect.

    Pragma statements accept no bound parameters, so the names and
    settings are interpolated. They come from this module's constants
    and from an already validated whole number of milliseconds; no
    submitted value reaches the statement text.

    Args:
        connection: The freshly opened connection.
        busy_timeout_ms: Bounded wait, in milliseconds, for a busy lock.

    Raises:
        DurabilityPolicyError: If any pragma does not read back as the
            approved policy.
    """
    for name, setting, effective in DURABILITY_PRAGMAS:
        connection.execute(f"PRAGMA {name} = {setting}")
        _confirm_pragma(connection, name, effective)
    connection.execute(
        f"PRAGMA {BUSY_TIMEOUT_PRAGMA} = {int(busy_timeout_ms):d}"
    )
    _confirm_pragma(connection, BUSY_TIMEOUT_PRAGMA, int(busy_timeout_ms))


def _confirm_pragma(
    connection: sqlite3.Connection, name: str, expected: str | int
) -> None:
    """Read one pragma back and compare it with the approved value.

    Args:
        connection: The connection the pragma was applied to.
        name: Pragma name.
        expected: The value the pragma must report.

    Raises:
        DurabilityPolicyError: If the pragma reports anything else,
            including nothing at all when the name is not recognized.
    """
    row = connection.execute(f"PRAGMA {name}").fetchone()
    actual = None if row is None else row[0]
    if not _reports(actual, expected):
        raise DurabilityPolicyError(
            f"PRAGMA {name} reports {actual!r} instead of the approved"
            f" {expected!r}. An ignored or misspelled pragma would"
            " silently weaken durability, so the connection is refused."
        )


def _reports(actual: object, expected: str | int) -> bool:
    """Report whether a pragma read-back matches the approved value.

    Args:
        actual: The value the pragma reported.
        expected: The value the policy requires.

    Returns:
        True when they match. Textual values compare without case,
        because SQLite reports a mode in its own spelling.
    """
    if isinstance(expected, str):
        return isinstance(actual, str) and actual.casefold() == (
            expected.casefold()
        )
    return actual == expected
