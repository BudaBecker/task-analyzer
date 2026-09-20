"""SQLite access for the Task Analyzer server.

Covers PCE-11 through PCE-14, PCE-19 through PCE-25, PCE-29 and PCE-35
through PCE-43 (REQ-008, REQ-010, REQ-028, REQ-029, REQ-031) and the
lifecycle mutations TLD-01 through TLD-27 (REQ-009, REQ-025, REQ-030).
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
COMPLETE_TASK = (
    "UPDATE tasks SET status = 'completed', latest_completed_at_us = ?"
    " WHERE task_id = ? AND is_deleted = 0"
)
REPLACE_OBSERVATIONS = (
    "UPDATE tasks SET observations = ? WHERE task_id = ? AND is_deleted = 0"
)
REOPEN_TASK = (
    "UPDATE tasks SET status = 'pending', latest_completed_at_us = NULL"
    " WHERE task_id = ? AND is_deleted = 0"
)
DELETE_TASK = (
    "UPDATE tasks SET is_deleted = 1 WHERE task_id = ? AND is_deleted = 0"
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
    """One retained terminal operation result and its request."""

    canonical_request: str
    result: OperationResult


class TaskNotStoredError(LookupError):
    """Raised when a write reached no managed task row."""


class ZoneOutcome(StrEnum):
    """What a compare-and-set attempt found on the singleton row."""

    STORED = "stored"
    ALREADY_SET = "already_set"
    CONFLICTING = "conflicting"


@dataclass(frozen=True, slots=True)
class ConfiguredZone:
    """The product time zone after a compare-and-set attempt."""

    outcome: ZoneOutcome
    product_time_zone: str


class DurabilityPolicyError(RuntimeError):
    """Raised when a connection does not report the approved policy."""


@contextmanager
def open_connection(
    path: Path, busy_timeout_ms: int
) -> Iterator[sqlite3.Connection]:
    """Open one connection to an existing database for one call."""
    connection = _open(path, busy_timeout_ms)
    try:
        yield connection
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


@contextmanager
def write_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """Run the body inside one immediate write transaction."""
    connection.execute(BEGIN_IMMEDIATE)
    try:
        yield
        connection.execute(COMMIT)
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise


def read_product_time_zone(connection: sqlite3.Connection) -> str | None:
    """Read the retained product time zone."""
    row = connection.execute(READ_PRODUCT_TIME_ZONE).fetchone()
    return None if row is None else str(row[0])


def store_product_time_zone(
    connection: sqlite3.Connection, zone_key: str
) -> ConfiguredZone:
    """Set the product time zone only while the singleton is unset."""
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
    """Store one newly created task."""
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
    """Replace the editable state of one managed task."""
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


def complete_task(
    connection: sqlite3.Connection,
    *,
    task_id: UUID,
    completed_at: datetime,
) -> TaskSnapshot:
    """Mark one managed task completed at the sampled instant."""
    connection.execute(
        COMPLETE_TASK, (to_utc_microseconds(completed_at), str(task_id))
    )
    return _require_task(connection, task_id)


def replace_observations(
    connection: sqlite3.Connection,
    *,
    task_id: UUID,
    observations: str | None,
) -> TaskSnapshot:
    """Replace only the observations of one managed task."""
    connection.execute(REPLACE_OBSERVATIONS, (observations, str(task_id)))
    return _require_task(connection, task_id)


def reopen_task(
    connection: sqlite3.Connection, *, task_id: UUID
) -> TaskSnapshot:
    """Return one managed task to pending and clear its completion."""
    connection.execute(REOPEN_TASK, (str(task_id),))
    return _require_task(connection, task_id)


def delete_task(connection: sqlite3.Connection, *, task_id: UUID) -> None:
    """Remove one task from the managed collection.

    The row stays so its history survives; the flag is what excludes it
    from managed reads and from the unique partial indexes.
    """
    deleted = connection.execute(DELETE_TASK, (str(task_id),)).rowcount
    if deleted != 1:
        raise TaskNotStoredError(
            f"Deleting managed task {task_id} reached {deleted} rows"
            " instead of one, so its removal cannot be reported."
        )


def read_task(
    connection: sqlite3.Connection, task_id: UUID
) -> TaskSnapshot | None:
    """Read one managed task."""
    row = connection.execute(READ_TASK, (str(task_id),)).fetchone()
    return None if row is None else _as_snapshot(row)


def read_tasks(connection: sqlite3.Connection) -> tuple[TaskSnapshot, ...]:
    """Read every managed task."""
    rows = connection.execute(READ_TASKS).fetchall()
    return tuple(_as_snapshot(row) for row in rows)


def find_conflicting_task(
    connection: sqlite3.Connection,
    *,
    title_key: str,
    deadline: date | None,
    excluded_task_id: UUID | None = None,
) -> UUID | None:
    """Find the managed task a proposed state would collide with."""
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
    """Read the retained result of one operation."""
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
    """Retain the terminal result of one operation."""
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
    """Read back a task a write has just stored."""
    stored = read_task(connection, task_id)
    if stored is None:
        raise TaskNotStoredError(
            f"No managed task {task_id} was stored, so the write"
            " reached no row and its result cannot be reported."
        )
    return stored


def _as_snapshot(row: tuple[Any, ...]) -> TaskSnapshot:
    """Read one stored row as the task the desktop reads."""
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
    """Read a stored status column as its contract value."""
    if value == "pending":
        return "pending"
    if value == "completed":
        return "completed"
    raise ValueError(f"{value!r} is not a stored task status.")


def _as_deadline_text(deadline: date | None) -> str | None:
    """Write a deadline date in the stored calendar-date spelling."""
    return None if deadline is None else deadline.isoformat()


def _open(path: Path, busy_timeout_ms: int) -> sqlite3.Connection:
    """Open and verify one connection under the approved policy."""
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
    """Apply the approved pragmas and confirm each took effect."""
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
    """Read one pragma back and compare it with the approved value."""
    row = connection.execute(f"PRAGMA {name}").fetchone()
    actual = None if row is None else row[0]
    if not _reports(actual, expected):
        raise DurabilityPolicyError(
            f"PRAGMA {name} reports {actual!r} instead of the approved"
            f" {expected!r}. An ignored or misspelled pragma would"
            " silently weaken durability, so the connection is refused."
        )


def _reports(actual: object, expected: str | int) -> bool:
    """Report whether a pragma read-back matches the approved value."""
    if isinstance(expected, str):
        return isinstance(actual, str) and actual.casefold() == (
            expected.casefold()
        )
    return actual == expected
