"""Operation services for the Task Analyzer server.

Covers PCE-01 through PCE-16, PCE-27 through PCE-31, PCE-35, PCE-37 through
PCE-43, PCE-48, PCE-51 and PCE-52 (REQ-007, REQ-008, REQ-010, REQ-028,
REQ-029, REQ-031) and the lifecycle commands TLD-01 through TLD-34
(REQ-009, REQ-025, REQ-030).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from task_analyzer_server import storage
from task_analyzer_server.clock import Clock, product_date
from task_analyzer_server.contracts import (
    ConfigurationView,
    ErrorCode,
    OperationError,
    OperationRequest,
    OperationResult,
    TaskInput,
    TaskInputError,
    TaskListView,
    TaskSnapshot,
    ValidationIssue,
    parse_empty_command,
    parse_observations_input,
    parse_task_input,
)
from task_analyzer_server.domain import (
    title_key,
    validate_observations,
    validate_task,
)
from task_analyzer_server.settings import ServerSettings

API_VERSION = "v1"
CANONICAL_SEPARATOR = "|"

CREATED_STATUS = 201
ACCEPTED_STATUS = 200
NOT_FOUND_STATUS = 404
STATE_INCOMPATIBLE_STATUS = 409
UNIQUENESS_CONFLICT_STATUS = 409
VALIDATION_FAILED_STATUS = 422

PENDING_STATUS = "pending"
COMPLETED_STATUS = "completed"

OperationCommand = Callable[
    [sqlite3.Connection, OperationRequest], OperationResult
]


class ProtocolRefusalError(Exception):
    """Raised when a request is refused without a terminal outcome."""

    def __init__(self, code: ErrorCode) -> None:
        """Build the refusal from its stable code."""
        self.code = code
        super().__init__(code.value)


def canonical_request(request: OperationRequest) -> str:
    """Build the deterministic identity text of one request."""
    return CANONICAL_SEPARATOR.join(
        (
            API_VERSION,
            request.method.strip().upper(),
            _canonical_target(request.target),
            _canonical_payload(request.payload),
        )
    )


def apply_operation(
    settings: ServerSettings,
    request: OperationRequest,
    command: OperationCommand,
) -> OperationResult:
    """Resolve one submitted attempt exactly once."""
    canonical = canonical_request(request)
    with storage.open_connection(
        settings.database_path, settings.db_busy_timeout_ms
    ) as connection:
        with storage.write_transaction(connection):
            result = _resolve(connection, request, command, canonical)
    return result


def lookup_operation(
    settings: ServerSettings, operation_id: UUID
) -> OperationResult | None:
    """Consult the outcome an operation established."""
    with storage.open_connection(
        settings.database_path, settings.db_busy_timeout_ms
    ) as connection:
        retained = storage.read_operation(connection, operation_id)
    return None if retained is None else retained.result


def create_task(
    settings: ServerSettings, clock: Clock, request: OperationRequest
) -> OperationResult:
    """Create one pending task from a submitted operation."""

    def command(
        connection: sqlite3.Connection, submitted: OperationRequest
    ) -> OperationResult:
        """Apply the creation inside the open write transaction."""
        return _apply_creation(connection, submitted, clock)

    return apply_operation(settings, request, command)


def edit_task(
    settings: ServerSettings,
    clock: Clock,
    request: OperationRequest,
    task_id: UUID,
) -> OperationResult:
    """Replace the editable state of one pending task."""

    def command(
        connection: sqlite3.Connection, submitted: OperationRequest
    ) -> OperationResult:
        """Apply the edit inside the open write transaction."""
        return _apply_edit(connection, submitted, clock, task_id)

    return apply_operation(settings, request, command)


def complete_task(
    settings: ServerSettings,
    clock: Clock,
    request: OperationRequest,
    task_id: UUID,
) -> OperationResult:
    """Complete one pending task."""

    def command(
        connection: sqlite3.Connection, submitted: OperationRequest
    ) -> OperationResult:
        """Apply the completion inside the open write transaction."""
        return _apply_completion(connection, submitted, clock, task_id)

    return apply_operation(settings, request, command)


def edit_completed_observations(
    settings: ServerSettings,
    clock: Clock,
    request: OperationRequest,
    task_id: UUID,
) -> OperationResult:
    """Replace the observations of one completed task."""

    def command(
        connection: sqlite3.Connection, submitted: OperationRequest
    ) -> OperationResult:
        """Apply the observation edit inside the write transaction."""
        return _apply_completed_observations(
            connection, submitted, clock, task_id
        )

    return apply_operation(settings, request, command)


def reopen_task(
    settings: ServerSettings,
    clock: Clock,
    request: OperationRequest,
    task_id: UUID,
) -> OperationResult:
    """Return one completed task to the pending state."""

    def command(
        connection: sqlite3.Connection, submitted: OperationRequest
    ) -> OperationResult:
        """Apply the reopening inside the open write transaction."""
        return _apply_reopening(connection, submitted, clock, task_id)

    return apply_operation(settings, request, command)


def delete_task(
    settings: ServerSettings,
    clock: Clock,
    request: OperationRequest,
    task_id: UUID,
) -> OperationResult:
    """Remove one managed task from the collection."""

    def command(
        connection: sqlite3.Connection, submitted: OperationRequest
    ) -> OperationResult:
        """Apply the deletion inside the open write transaction."""
        return _apply_deletion(connection, submitted, clock, task_id)

    return apply_operation(settings, request, command)


def read_configuration(
    settings: ServerSettings, clock: Clock
) -> ConfigurationView:
    """Read the product configuration as it currently stands."""
    with storage.open_connection(
        settings.database_path, settings.db_busy_timeout_ms
    ) as connection:
        zone_key = storage.read_product_time_zone(connection)
    return configuration_view(clock, zone_key)


def configure_zone(
    settings: ServerSettings, clock: Clock, zone_key: str
) -> ConfigurationView:
    """Fix the product time zone, or confirm the one already fixed."""
    _confirm_known_zone(zone_key)
    with storage.open_connection(
        settings.database_path, settings.db_busy_timeout_ms
    ) as connection:
        with storage.write_transaction(connection):
            stored = storage.store_product_time_zone(connection, zone_key)
    if stored.outcome is storage.ZoneOutcome.CONFLICTING:
        raise ProtocolRefusalError(ErrorCode.PRODUCT_TIME_ZONE_FIXED)
    return configuration_view(clock, stored.product_time_zone)


def configuration_view(
    clock: Clock, zone_key: str | None
) -> ConfigurationView:
    """Describe the configuration at one sampled server instant."""
    now = clock.now()
    return ConfigurationView(
        configured=zone_key is not None,
        product_time_zone=zone_key,
        server_now=now,
        product_date=_product_date_in(now, zone_key),
    )


def read_task_list(settings: ServerSettings, clock: Clock) -> TaskListView:
    """Read every managed task with the time context of one reading."""
    with storage.open_connection(
        settings.database_path, settings.db_busy_timeout_ms
    ) as connection:
        connection.execute("BEGIN")
        zone_key = storage.read_product_time_zone(connection)
        tasks = storage.read_tasks(connection)
    now = clock.now()
    return TaskListView(
        items=tasks,
        product_time_zone=zone_key,
        server_now=now,
        product_date=_product_date_in(now, zone_key),
    )


def require_product_time_zone(connection: sqlite3.Connection) -> str:
    """Refuse a task command while the product zone is unset."""
    zone_key = storage.read_product_time_zone(connection)
    if zone_key is None:
        raise ProtocolRefusalError(ErrorCode.PRODUCT_TIME_ZONE_REQUIRED)
    return zone_key


def _product_date_in(now: datetime, zone_key: str | None) -> date | None:
    """Read one sampled instant as the product date."""
    return None if zone_key is None else product_date(now, ZoneInfo(zone_key))


def _apply_creation(
    connection: sqlite3.Connection,
    request: OperationRequest,
    clock: Clock,
) -> OperationResult:
    """Settle one creation attempt inside the write transaction."""
    require_product_time_zone(connection)
    accepted = _accepted_input(request.payload)
    if isinstance(accepted, tuple):
        return _validation_rejection(request, clock, accepted)
    key = title_key(accepted.title)
    deadline = _accepted_deadline(accepted.deadline)
    conflict = storage.find_conflicting_task(
        connection, title_key=key, deadline=deadline
    )
    if conflict is not None:
        return _conflict_rejection(request, clock, conflict)
    now = clock.now()
    try:
        stored = storage.insert_task(
            connection,
            task_id=uuid4(),
            title=accepted.title,
            title_key=key,
            observations=accepted.observations,
            deadline=deadline,
            created_at=now,
        )
    except sqlite3.IntegrityError:
        # The unique partial indexes back up the check above. A write
        # that still reaches them is the conflict they describe, not an
        # internal defect, and SQLite aborts only the offending
        # statement, so this rejection still commits with its
        # transaction. Any other broken constraint is re-raised.
        collided = storage.find_conflicting_task(
            connection, title_key=key, deadline=deadline
        )
        if collided is None:
            raise
        return _conflict_rejection(request, clock, collided)
    return _success(request, now, CREATED_STATUS, stored)


def _apply_edit(
    connection: sqlite3.Connection,
    request: OperationRequest,
    clock: Clock,
    task_id: UUID,
) -> OperationResult:
    """Settle one edit attempt inside the write transaction."""
    require_product_time_zone(connection)
    accepted = _accepted_input(request.payload)
    if isinstance(accepted, tuple):
        return _validation_rejection(request, clock, accepted)
    target = storage.read_task(connection, task_id)
    if target is None:
        return _rejection(
            request,
            clock.now(),
            NOT_FOUND_STATUS,
            OperationError(code=ErrorCode.TASK_NOT_FOUND),
        )
    if target.status != PENDING_STATUS:
        return _rejection(
            request,
            clock.now(),
            STATE_INCOMPATIBLE_STATUS,
            OperationError(code=ErrorCode.TASK_STATE_INCOMPATIBLE),
        )
    key = title_key(accepted.title)
    deadline = _accepted_deadline(accepted.deadline)
    conflict = storage.find_conflicting_task(
        connection,
        title_key=key,
        deadline=deadline,
        excluded_task_id=task_id,
    )
    if conflict is not None:
        return _conflict_rejection(request, clock, conflict)
    try:
        stored = storage.update_task(
            connection,
            task_id=task_id,
            title=accepted.title,
            title_key=key,
            observations=accepted.observations,
            deadline=deadline,
        )
    except sqlite3.IntegrityError:
        # The unique partial indexes back up the check above; see the
        # matching note in the creation command.
        collided = storage.find_conflicting_task(
            connection,
            title_key=key,
            deadline=deadline,
            excluded_task_id=task_id,
        )
        if collided is None:
            raise
        return _conflict_rejection(request, clock, collided)
    return _success(request, clock.now(), ACCEPTED_STATUS, stored)


def _apply_completion(
    connection: sqlite3.Connection,
    request: OperationRequest,
    clock: Clock,
    task_id: UUID,
) -> OperationResult:
    """Settle one completion attempt inside the write transaction."""
    require_product_time_zone(connection)
    issues = _accepted_empty_command(request.payload)
    if issues:
        return _validation_rejection(request, clock, issues)
    target = _eligible_target(connection, task_id, PENDING_STATUS)
    if isinstance(target, OperationError):
        return _state_rejection(request, clock, target)
    # Completing never widens a uniqueness population: the dated index
    # ignores status, and the undated index covers only pending rows.
    now = clock.now()
    stored = storage.complete_task(
        connection, task_id=task_id, completed_at=now
    )
    return _success(request, now, ACCEPTED_STATUS, stored)


def _apply_completed_observations(
    connection: sqlite3.Connection,
    request: OperationRequest,
    clock: Clock,
    task_id: UUID,
) -> OperationResult:
    """Settle one completed-observation edit inside the transaction."""
    require_product_time_zone(connection)
    try:
        accepted = parse_observations_input(request.payload)
    except TaskInputError as failure:
        return _validation_rejection(request, clock, failure.issues)
    issues = validate_observations(accepted.observations)
    if issues:
        return _validation_rejection(request, clock, issues)
    target = _eligible_target(connection, task_id, COMPLETED_STATUS)
    if isinstance(target, OperationError):
        return _state_rejection(request, clock, target)
    stored = storage.replace_observations(
        connection, task_id=task_id, observations=accepted.observations
    )
    return _success(request, clock.now(), ACCEPTED_STATUS, stored)


def _apply_reopening(
    connection: sqlite3.Connection,
    request: OperationRequest,
    clock: Clock,
    task_id: UUID,
) -> OperationResult:
    """Settle one reopening attempt inside the write transaction."""
    require_product_time_zone(connection)
    issues = _accepted_empty_command(request.payload)
    if issues:
        return _validation_rejection(request, clock, issues)
    target = _eligible_target(connection, task_id, COMPLETED_STATUS)
    if isinstance(target, OperationError):
        return _state_rejection(request, clock, target)
    key = title_key(target.title)
    conflict = storage.find_conflicting_task(
        connection,
        title_key=key,
        deadline=target.deadline,
        excluded_task_id=task_id,
    )
    if conflict is not None:
        return _conflict_rejection(request, clock, conflict)
    try:
        stored = storage.reopen_task(connection, task_id=task_id)
    except sqlite3.IntegrityError:
        # The undated pending index backs up the check above; see the
        # matching note in the creation command.
        collided = storage.find_conflicting_task(
            connection,
            title_key=key,
            deadline=target.deadline,
            excluded_task_id=task_id,
        )
        if collided is None:
            raise
        return _conflict_rejection(request, clock, collided)
    return _success(request, clock.now(), ACCEPTED_STATUS, stored)


def _apply_deletion(
    connection: sqlite3.Connection,
    request: OperationRequest,
    clock: Clock,
    task_id: UUID,
) -> OperationResult:
    """Settle one deletion attempt inside the write transaction."""
    require_product_time_zone(connection)
    issues = _accepted_empty_command(request.payload)
    if issues:
        return _validation_rejection(request, clock, issues)
    target = storage.read_task(connection, task_id)
    if target is None:
        return _rejection(
            request,
            clock.now(),
            NOT_FOUND_STATUS,
            OperationError(code=ErrorCode.TASK_NOT_FOUND),
        )
    storage.delete_task(connection, task_id=task_id)
    # The result carries the snapshot read before the flag made the task
    # unmanaged, so a lost response stays distinguishable from an
    # attempt against a task that was never there.
    return _success(request, clock.now(), ACCEPTED_STATUS, target)


def _eligible_target(
    connection: sqlite3.Connection,
    task_id: UUID,
    required_status: str,
) -> TaskSnapshot | OperationError:
    """Read the task a lifecycle command may act on, or say why not."""
    target = storage.read_task(connection, task_id)
    if target is None:
        return OperationError(code=ErrorCode.TASK_NOT_FOUND)
    if target.status != required_status:
        return OperationError(code=ErrorCode.TASK_STATE_INCOMPATIBLE)
    return target


def _state_rejection(
    request: OperationRequest, clock: Clock, error: OperationError
) -> OperationResult:
    """Build the durable rejection of an unavailable or wrong state."""
    status = (
        NOT_FOUND_STATUS
        if error.code is ErrorCode.TASK_NOT_FOUND
        else STATE_INCOMPATIBLE_STATUS
    )
    return _rejection(request, clock.now(), status, error)


def _accepted_empty_command(
    payload: object,
) -> tuple[ValidationIssue, ...]:
    """Apply the no-field payload contract of a lifecycle command."""
    try:
        parse_empty_command(payload)
    except TaskInputError as failure:
        return failure.issues
    return ()


def _accepted_input(
    payload: object,
) -> TaskInput | tuple[ValidationIssue, ...]:
    """Apply both parsing and the business rules to a payload."""
    try:
        data = parse_task_input(payload)
    except TaskInputError as failure:
        return failure.issues
    issues = validate_task(data)
    return issues if issues else data


def _accepted_deadline(deadline: str | None) -> date | None:
    """Read an already accepted deadline as a calendar date."""
    return None if deadline is None else date.fromisoformat(deadline)


def _conflict_rejection(
    request: OperationRequest, clock: Clock, conflicting_task_id: UUID
) -> OperationResult:
    """Build the durable rejection of a uniqueness conflict."""
    return _rejection(
        request,
        clock.now(),
        UNIQUENESS_CONFLICT_STATUS,
        OperationError(
            code=ErrorCode.TASK_UNIQUENESS_CONFLICT,
            conflicting_task_id=conflicting_task_id,
        ),
    )


def _validation_rejection(
    request: OperationRequest,
    clock: Clock,
    issues: tuple[ValidationIssue, ...],
) -> OperationResult:
    """Build the durable rejection of an invalid submission."""
    return _rejection(
        request,
        clock.now(),
        VALIDATION_FAILED_STATUS,
        OperationError(code=ErrorCode.TASK_VALIDATION_FAILED, fields=issues),
    )


def _success(
    request: OperationRequest,
    resolved_at: datetime,
    status: int,
    task: TaskSnapshot,
) -> OperationResult:
    """Build the terminal result of an accepted operation."""
    return OperationResult(
        operation_id=request.operation_id,
        outcome="succeeded",
        original_http_status=status,
        task=task,
        error=None,
        resolved_at=resolved_at,
    )


def _rejection(
    request: OperationRequest,
    resolved_at: datetime,
    status: int,
    error: OperationError,
) -> OperationResult:
    """Build the terminal result of a rejected operation."""
    return OperationResult(
        operation_id=request.operation_id,
        outcome="rejected",
        original_http_status=status,
        task=None,
        error=error,
        resolved_at=resolved_at,
    )


def _confirm_known_zone(zone_key: str) -> None:
    """Refuse a submitted key the server's zone data does not know."""
    try:
        ZoneInfo(zone_key)
    except (ZoneInfoNotFoundError, ValueError):
        raise ProtocolRefusalError(ErrorCode.INVALID_TIME_ZONE) from None


def _resolve(
    connection: sqlite3.Connection,
    request: OperationRequest,
    command: OperationCommand,
    canonical: str,
) -> OperationResult:
    """Settle one attempt while the write transaction is held."""
    retained = storage.read_operation(connection, request.operation_id)
    if retained is not None:
        if retained.canonical_request != canonical:
            raise ProtocolRefusalError(ErrorCode.OPERATION_ID_REUSED)
        return retained.result
    result = command(connection, request)
    storage.write_operation(
        connection,
        operation_id=request.operation_id,
        canonical_request=canonical,
        result=result,
    )
    return result


def _canonical_target(target: str) -> str:
    """Reduce a task target to the one spelling that identifies it."""
    trimmed = target.strip().rstrip("/")
    return trimmed.casefold()


def _canonical_payload(payload: object) -> str:
    """Write the submitted JSON values in one deterministic spelling."""
    if isinstance(payload, Decimal):
        if not payload.is_finite():
            raise ValueError("Not a finite JSON number")
        return str(payload)
    if isinstance(payload, dict):
        return (
            "{"
            + ",".join(
                json.dumps(key, ensure_ascii=False)
                + ":"
                + _canonical_payload(value)
                for key, value in sorted(payload.items())
            )
            + "}"
        )
    if isinstance(payload, list):
        return "[" + ",".join(map(_canonical_payload, payload)) + "]"
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
