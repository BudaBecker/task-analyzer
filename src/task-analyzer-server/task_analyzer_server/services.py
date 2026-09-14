"""Operation services for the Task Analyzer server.

Covers PCE-29 through PCE-31, PCE-35 and PCE-37 through PCE-43
(REQ-010, REQ-028, REQ-031).

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
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from task_analyzer_server import storage
from task_analyzer_server.clock import Clock, product_date
from task_analyzer_server.contracts import (
    ConfigurationView,
    ErrorCode,
    OperationRequest,
    OperationResult,
)
from task_analyzer_server.settings import ServerSettings

API_VERSION = "v1"
CANONICAL_SEPARATOR = "|"

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
        product_date=(
            None if zone_key is None else product_date(now, ZoneInfo(zone_key))
        ),
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
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
