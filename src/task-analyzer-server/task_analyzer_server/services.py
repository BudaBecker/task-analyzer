"""Operation services for the Task Analyzer server.

Covers PCE-01 through PCE-16, PCE-27 through PCE-31, PCE-35, PCE-37
through PCE-43, PCE-48, PCE-51 and PCE-52 (REQ-007, REQ-008, REQ-010,
REQ-028, REQ-029, REQ-031).

One submitted attempt resolves once. The runner here turns a request
plus a command into exactly one terminal result, and it does so in the
order the approved recovery sequence requires:

1. Build a deterministic canonical representation of the request.
2. Take the write lock with ``BEGIN IMMEDIATE``, before reading the
   ledger and before any command inspects task state.
3. A repeated identity carrying the same canonical request returns the
   retained result. The command never runs again, so nothing is
   validated or applied a second time.
4. A repeated identity carrying a different canonical request is a
   protocol conflict. The retained entry and every task stay as they
   were.
5. Otherwise the command runs and produces its terminal result, whether
   that result accepts or rejects the request.
6. The result is retained in the same transaction as any change it
   reports.
7. The transaction commits before the result is returned.

Nothing terminal is returned when a step fails: the transaction ends
without a result and the caller consults the original identity instead.

The runner knows nothing about what a command does, so the commands of
delivery 1B use it unchanged.

Fixing the product time zone is deliberately outside that flow. It is a
compare-and-set on a singleton, so the same key is safe to repeat
without an operation identity and no retained zone is ever replaced.
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
    parse_task_input,
)
from task_analyzer_server.domain import title_key, validate_task
from task_analyzer_server.settings import ServerSettings

API_VERSION = "v1"
CANONICAL_SEPARATOR = "|"

CREATED_STATUS = 201
EDITED_STATUS = 200
NOT_FOUND_STATUS = 404
STATE_INCOMPATIBLE_STATUS = 409
UNIQUENESS_CONFLICT_STATUS = 409
VALIDATION_FAILED_STATUS = 422

PENDING_STATUS = "pending"

OperationCommand = Callable[
    [sqlite3.Connection, OperationRequest], OperationResult
]
"""A command the runner applies inside the open write transaction.

It returns the terminal result of the attempt, accepting or rejecting
it. Raising instead means no outcome was established.
"""


class ProtocolRefusalError(Exception):
    """Raised when a request is refused without a terminal outcome.

    A refusal is not an operation result: it records nothing, changes
    nothing, and must never be read as evidence that an attempt was
    applied, rejected, cancelled or rolled back.

    Attributes:
        code: The stable code naming the refusal.
    """

    def __init__(self, code: ErrorCode) -> None:
        """Build the refusal from its stable code.

        Args:
            code: The stable code naming the refusal.
        """
        self.code = code
        super().__init__(code.value)


def canonical_request(request: OperationRequest) -> str:
    """Build the deterministic identity text of one request.

    The text covers the API version, the method, the canonical task
    target and the submitted JSON values as parsed, before any business
    normalization. Object-key order and JSON whitespace are removed, so
    they cannot change what counts as the same attempt, while a changed
    field value, target or method produces different text.

    The text itself is retained with the result, so a later comparison
    reads the request that was actually resolved rather than a digest of
    it.

    Args:
        request: The submitted operation and its envelope values.

    Returns:
        The canonical representation of that request.

    Raises:
        ValueError: If the payload holds a number JSON cannot carry.
        TypeError: If the payload holds a value that is not parsed JSON.
    """
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
    """Resolve one submitted attempt exactly once.

    Args:
        settings: Runtime configuration naming the database.
        request: The submitted operation and its envelope values.
        command: The command to apply for a new attempt.

    Returns:
        The terminal result of the attempt, retained and committed.

    Raises:
        ProtocolRefusalError: If the identity was already resolved for a
            different request, or if the command refuses the request
            before any outcome exists.
        sqlite3.Error: If the database cannot serve or commit the
            attempt. No terminal outcome is produced, and the original
            identity remains the way to establish one.
    """
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
    """Consult the outcome an operation established.

    The read takes no write transaction, so consulting an outcome never
    competes with the work that establishes one.

    Args:
        settings: Runtime configuration naming the database.
        operation_id: Identity of the operation to consult.

    Returns:
        The retained terminal result, or ``None`` when no committed
        outcome exists. ``None`` means unknown: work may never have
        arrived, may still be in flight, or may have rolled back. It is
        never a rejection.
    """
    with storage.open_connection(
        settings.database_path, settings.db_busy_timeout_ms
    ) as connection:
        retained = storage.read_operation(connection, operation_id)
    return None if retained is None else retained.result


def create_task(
    settings: ServerSettings, clock: Clock, request: OperationRequest
) -> OperationResult:
    """Create one pending task from a submitted operation.

    The attempt runs through the shared runner, so a repetition returns
    the original outcome instead of creating a second task.

    Args:
        settings: Runtime configuration naming the database.
        clock: The server's source of the current instant.
        request: The submitted creation operation.

    Returns:
        The terminal result: the created task, or the rejection that
        left every task untouched.

    Raises:
        ProtocolRefusalError: If the attempt is refused before any
            outcome exists.
        sqlite3.Error: If the database cannot serve or commit the
            attempt.
    """

    def command(
        connection: sqlite3.Connection, submitted: OperationRequest
    ) -> OperationResult:
        """Apply the creation inside the open write transaction.

        Args:
            connection: Connection holding the write transaction.
            submitted: The submitted creation operation.

        Returns:
            The terminal result of the attempt.
        """
        return _apply_creation(connection, submitted, clock)

    return apply_operation(settings, request, command)


def edit_task(
    settings: ServerSettings,
    clock: Clock,
    request: OperationRequest,
    task_id: UUID,
) -> OperationResult:
    """Replace the editable state of one pending task.

    A save carries the whole form, so the edit replaces every editable
    field at once: an omitted or cleared optional value persists as
    absent. Identity, original creation time and pending status belong
    to the server and no edit moves them.

    Args:
        settings: Runtime configuration naming the database.
        clock: The server's source of the current instant.
        request: The submitted edit operation.
        task_id: Identity of the task the request targets.

    Returns:
        The terminal result: the edited task, or the rejection that
        left it exactly as it was.

    Raises:
        ProtocolRefusalError: If the attempt is refused before any
            outcome exists.
        sqlite3.Error: If the database cannot serve or commit the
            attempt.
    """

    def command(
        connection: sqlite3.Connection, submitted: OperationRequest
    ) -> OperationResult:
        """Apply the edit inside the open write transaction.

        Args:
            connection: Connection holding the write transaction.
            submitted: The submitted edit operation.

        Returns:
            The terminal result of the attempt.
        """
        return _apply_edit(connection, submitted, clock, task_id)

    return apply_operation(settings, request, command)


def read_configuration(
    settings: ServerSettings, clock: Clock
) -> ConfigurationView:
    """Read the product configuration as it currently stands.

    The connection is opened for this reading alone and takes no write
    transaction, so the answer is a fresh committed snapshot and never
    competes with work in flight.

    Args:
        settings: Runtime configuration naming the database.
        clock: The server's source of the current instant.

    Returns:
        The configuration at one sampled server instant. An
        unconfigured server reports the absence of a zone rather than
        inventing one.
    """
    with storage.open_connection(
        settings.database_path, settings.db_busy_timeout_ms
    ) as connection:
        zone_key = storage.read_product_time_zone(connection)
    return configuration_view(clock, zone_key)


def configure_zone(
    settings: ServerSettings, clock: Clock, zone_key: str
) -> ConfigurationView:
    """Fix the product time zone, or confirm the one already fixed.

    Setup is a compare-and-set on a singleton, not a task operation, so
    it records no operation result and needs no operation identity. The
    same key is therefore safe to send again: it returns the retained
    configuration instead of a second outcome.

    Validity is decided before any connection is opened, so a key the
    zone database does not know stores nothing at all.

    Args:
        settings: Runtime configuration naming the database.
        clock: The server's source of the current instant.
        zone_key: The IANA key the desktop supplies during setup.

    Returns:
        The configuration as it stands once the attempt finished.

    Raises:
        ProtocolRefusalError: ``INVALID_TIME_ZONE`` if the key is not a
            known IANA zone, or ``PRODUCT_TIME_ZONE_FIXED`` if another
            key is already retained. The retained zone is never
            replaced.
    """
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
    """Describe the configuration at one sampled server instant.

    The product date comes from server time read in the retained zone.
    Neither the desktop's zone nor the server host's display zone takes
    part, so a client that moves or changes its clock cannot change what
    the product date is.

    Args:
        clock: The server's source of the current instant.
        zone_key: The retained IANA key, or ``None`` while unset.

    Returns:
        The configuration view for that instant.
    """
    now = clock.now()
    return ConfigurationView(
        configured=zone_key is not None,
        product_time_zone=zone_key,
        server_now=now,
        product_date=_product_date_in(now, zone_key),
    )


def read_task_list(settings: ServerSettings, clock: Clock) -> TaskListView:
    """Read every managed task with the time context of one reading.

    Tasks and the retained zone come from the same committed snapshot,
    and the server instant is sampled once, so a reading is internally
    consistent: its product date always belongs to the instant it
    publishes. The order the tasks arrive in is not a product guarantee.

    Args:
        settings: Runtime configuration naming the database.
        clock: The server's source of the current instant.

    Returns:
        The managed tasks, empty when nothing is managed, together with
        the zone and time context of this reading.
    """
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
    """Refuse a task command while the product zone is unset.

    The refusal happens before any task work, so an unconfigured server
    records no terminal task result for the attempt: the desktop
    completes setup and submits the action again.

    Args:
        connection: An open connection from the operation flow.

    Returns:
        The retained IANA key.

    Raises:
        ProtocolRefusalError: ``PRODUCT_TIME_ZONE_REQUIRED`` if no zone
            has been fixed yet.
    """
    zone_key = storage.read_product_time_zone(connection)
    if zone_key is None:
        raise ProtocolRefusalError(ErrorCode.PRODUCT_TIME_ZONE_REQUIRED)
    return zone_key


def _product_date_in(now: datetime, zone_key: str | None) -> date | None:
    """Read one sampled instant as the product date.

    Args:
        now: The sampled server instant.
        zone_key: The retained IANA key, or ``None`` while unset.

    Returns:
        The product date at that instant, or ``None`` while no zone is
        configured. No zone is ever invented to produce a date.
    """
    return None if zone_key is None else product_date(now, ZoneInfo(zone_key))


def _apply_creation(
    connection: sqlite3.Connection,
    request: OperationRequest,
    clock: Clock,
) -> OperationResult:
    """Settle one creation attempt inside the write transaction.

    The instant is sampled here, with write access already held, so the
    recorded original creation time is the moment the task actually
    became part of the collection.

    Args:
        connection: Connection holding the write transaction.
        request: The submitted creation operation.
        clock: The server's source of the current instant.

    Returns:
        The created task's success result, or a durable rejection that
        creates nothing.

    Raises:
        ProtocolRefusalError: If no product time zone has been fixed.
    """
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
    """Settle one edit attempt inside the write transaction.

    A target outside managed tasks reads as absent, so an edit can never
    create a task. A managed target that is not pending is outside the
    1A edit command: it is rejected with no change to its state or its
    times, and delivery 1B adds the approved completed-task editing.

    Args:
        connection: Connection holding the write transaction.
        request: The submitted edit operation.
        clock: The server's source of the current instant.
        task_id: Identity of the task the request targets.

    Returns:
        The edited task's success result, or a durable rejection that
        leaves the task exactly as it was.

    Raises:
        ProtocolRefusalError: If no product time zone has been fixed.
    """
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
    return _success(request, clock.now(), EDITED_STATUS, stored)


def _accepted_input(
    payload: object,
) -> TaskInput | tuple[ValidationIssue, ...]:
    """Apply both parsing and the business rules to a payload.

    Args:
        payload: Parsed JSON payload of the submitted operation.

    Returns:
        The accepted input, or the issues that rejected it. The issues
        are never empty, so the two are told apart by type alone.
    """
    try:
        data = parse_task_input(payload)
    except TaskInputError as failure:
        return failure.issues
    issues = validate_task(data)
    return issues if issues else data


def _accepted_deadline(deadline: str | None) -> date | None:
    """Read an already accepted deadline as a calendar date.

    Validation has settled the spelling and the supported range before
    this runs, so this is only the conversion of accepted text, never a
    second calendar rule.

    Args:
        deadline: Accepted deadline text, or ``None`` when absent.

    Returns:
        The calendar date, or ``None`` for an undated task.
    """
    return None if deadline is None else date.fromisoformat(deadline)


def _conflict_rejection(
    request: OperationRequest, clock: Clock, conflicting_task_id: UUID
) -> OperationResult:
    """Build the durable rejection of a uniqueness conflict.

    Args:
        request: The submitted operation.
        clock: The server's source of the current instant.
        conflicting_task_id: The task the attempt collided with.

    Returns:
        The rejection result, which leaves both the target task and the
        conflicting task exactly as they were.
    """
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
    """Build the durable rejection of an invalid submission.

    Args:
        request: The submitted operation.
        clock: The server's source of the current instant.
        issues: The rejected fields and their stable codes.

    Returns:
        The rejection result, which changes no task.
    """
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
    """Build the terminal result of an accepted operation.

    Args:
        request: The submitted operation.
        resolved_at: When the server settled the outcome.
        status: The status the original request answered with.
        task: The task as it is now stored.

    Returns:
        The success result.
    """
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
    """Build the terminal result of a rejected operation.

    Args:
        request: The submitted operation.
        resolved_at: When the server settled the outcome.
        status: The status the original request answered with.
        error: Why the operation was rejected.

    Returns:
        The rejection result.
    """
    return OperationResult(
        operation_id=request.operation_id,
        outcome="rejected",
        original_http_status=status,
        task=None,
        error=error,
        resolved_at=resolved_at,
    )


def _confirm_known_zone(zone_key: str) -> None:
    """Refuse a submitted key the server's zone data does not know.

    Args:
        zone_key: The submitted IANA key.

    Raises:
        ProtocolRefusalError: ``INVALID_TIME_ZONE`` if the key is
            unknown or not a usable zone name.
    """
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
    """Settle one attempt while the write transaction is held.

    Args:
        connection: An open connection holding the write transaction.
        request: The submitted operation and its envelope values.
        command: The command to apply for a new attempt.
        canonical: The canonical representation of the request.

    Returns:
        The terminal result of the attempt, not yet committed.

    Raises:
        ProtocolRefusalError: If the identity was already resolved for a
            different request.
    """
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
    """Reduce a task target to the one spelling that identifies it.

    A trailing separator and letter case do not change which task a
    target names, so neither changes the attempt's identity. Every
    other difference does.

    Args:
        target: The submitted task target path.

    Returns:
        The canonical spelling of that target.
    """
    trimmed = target.strip().rstrip("/")
    return trimmed.casefold()


def _canonical_payload(payload: object) -> str:
    """Write the submitted JSON values in one deterministic spelling.

    Args:
        payload: Parsed JSON payload, before business normalization.

    Returns:
        The payload with sorted object keys and no optional whitespace.

    Raises:
        ValueError: If the payload holds a number JSON cannot carry.
        TypeError: If the payload holds a value that is not parsed JSON.
    """
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
