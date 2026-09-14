"""HTTP boundary of the Task Analyzer server.

Covers PCE-26, PCE-38, PCE-40 through PCE-43, PCE-46 and PCE-47
(REQ-010, REQ-027, REQ-029, REQ-031).

A route reads the operation envelope, calls a service and publishes the
result. No business rule lives here, and no route mutates a task.

Two failure kinds are deliberately kept apart. A request whose envelope
cannot be read at all, such as an operation identity that is not a
usable UUID, never reaches the operation flow: nothing about it is
retained and the answer is a protocol error. A request carrying a usable
envelope enters the flow even when its task fields are wrong, so that
rejection is retained and stays consultable afterwards.

A protocol error carries a server-generated request identity and no
terminal outcome, so it can never be read as evidence that an operation
was applied, rejected, cancelled or rolled back. The same identity is
written to the log record describing the failure, which is what
correlates a reported error with the server's own account of it. The
error never carries submitted input.

Every response is served with ``Cache-Control: no-store``: the desktop
reads current server state, never a cached copy of it.

There is no product sign-in anywhere in this module. No route reads a
credential and no forwarded identity header is treated as a product
account, so nothing here turns the personal collection into an account.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from task_analyzer_server import services
from task_analyzer_server.clock import Clock
from task_analyzer_server.contracts import (
    ErrorCode,
    OperationRequest,
    OperationResult,
    ProtocolError,
    ProtocolErrorDetail,
)
from task_analyzer_server.logging_config import DurationTimer
from task_analyzer_server.settings import ServerSettings

API_PREFIX = "/v1"

OPERATION_ID_HEADER = "Operation-Id"
PRODUCT_TIME_ZONE_FIELD = "product_time_zone"

CACHE_CONTROL_HEADER = "Cache-Control"
NO_STORE = "no-store"
JSON_MEDIA_TYPE = "application/json"

REQUEST_ID_KEY = "task_analyzer_request_id"
OPERATION_ID_KEY = "task_analyzer_operation_id"

PROTOCOL_ERROR_EVENT = "protocol_error"
OPERATION_RESOLVED_EVENT = "operation_resolved"

OK_STATUS = 200
BAD_REQUEST_STATUS = 400
NOT_FOUND_STATUS = 404
CONFLICT_STATUS = 409
UNPROCESSABLE_STATUS = 422
INTERNAL_ERROR_STATUS = 500
STORAGE_UNAVAILABLE_STATUS = 503

SERVER_ERROR_FLOOR = 500

REFUSAL_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_OPERATION_ENVELOPE: BAD_REQUEST_STATUS,
    ErrorCode.OPERATION_RESULT_UNKNOWN: NOT_FOUND_STATUS,
    ErrorCode.OPERATION_ID_REUSED: CONFLICT_STATUS,
    ErrorCode.PRODUCT_TIME_ZONE_REQUIRED: CONFLICT_STATUS,
    ErrorCode.PRODUCT_TIME_ZONE_FIXED: CONFLICT_STATUS,
    ErrorCode.INVALID_TIME_ZONE: UNPROCESSABLE_STATUS,
}
"""The status each refusal answers with, decided in one place.

Every route raises the refusal and none of them chooses a status, so one
code always reaches the desktop as the same status.
"""

router = APIRouter(prefix=API_PREFIX)
"""Every route of the server.

Routes added by later deliveries register here, so composition never has
to be revisited to publish them.
"""

_logger = logging.getLogger(__name__)


def install_error_handlers(app: FastAPI) -> None:
    """Install the shared failure handlers on a composed application.

    Args:
        app: The application the handlers answer for.
    """
    app.add_exception_handler(services.ProtocolRefusalError, _handle_refusal)
    app.add_exception_handler(sqlite3.Error, _handle_storage_failure)
    app.add_exception_handler(Exception, _handle_unexpected)


@router.get("/configuration")
def read_configuration(request: Request) -> Response:
    """Publish the product configuration as it currently stands.

    Args:
        request: The submitted HTTP request.

    Returns:
        The configuration at one sampled server instant.
    """
    return published(
        services.read_configuration(_settings_of(request), _clock_of(request)),
        OK_STATUS,
    )


@router.put("/configuration")
async def configure_product_time_zone(request: Request) -> Response:
    """Fix the product time zone, or confirm the one already fixed.

    Setup is a compare-and-set on a singleton rather than a task
    operation, so it carries no operation identity and the same key is
    safe to send again. A different key never replaces a retained zone.

    Args:
        request: The submitted HTTP request.

    Returns:
        The configuration as it stands once the attempt finished.

    Raises:
        ProtocolRefusalError: ``INVALID_TIME_ZONE`` if no usable zone
            key was submitted, or ``PRODUCT_TIME_ZONE_FIXED`` if
            another key is already retained.
    """
    zone_key = _submitted_zone_key(await request.body())
    return published(
        await run_in_threadpool(
            services.configure_zone,
            _settings_of(request),
            _clock_of(request),
            zone_key,
        ),
        OK_STATUS,
    )


@router.post("/tasks")
async def create_task(request: Request) -> Response:
    """Create one pending task from a submitted operation.

    The envelope is read first, so a request the server cannot identify
    never reaches the operation flow. Once the envelope is usable, the
    task fields are validated inside that flow, which is what keeps a
    rejected submission consultable afterwards.

    Args:
        request: The submitted HTTP request.

    Returns:
        The terminal result of the attempt, answered with the status
        that attempt was originally settled with.

    Raises:
        ProtocolRefusalError: If the envelope is unusable, the identity
            was already resolved for different content, or no product
            time zone has been fixed.
    """
    timer = DurationTimer()
    submitted = await _submitted_operation(request)
    return _resolved(
        request,
        await run_in_threadpool(
            services.create_task,
            _settings_of(request),
            _clock_of(request),
            submitted,
        ),
        timer,
    )


@router.put("/tasks/{task_id}")
async def edit_task(request: Request, task_id: str) -> Response:
    """Replace the editable state of one pending task.

    The whole editable form arrives at once, so an omitted optional
    value and an explicit ``null`` both mean the value is absent
    afterwards. Identity, original creation time and status belong to
    the server and no edit moves them.

    Args:
        request: The submitted HTTP request.
        task_id: Identity of the task the request targets.

    Returns:
        The terminal result of the attempt, answered with the status
        that attempt was originally settled with.

    Raises:
        ProtocolRefusalError: If the envelope is unusable, the identity
            was already resolved for different content, or no product
            time zone has been fixed.
    """
    timer = DurationTimer()
    submitted = await _submitted_operation(request)
    target = _usable_identity(task_id)
    return _resolved(
        request,
        await run_in_threadpool(
            services.edit_task,
            _settings_of(request),
            _clock_of(request),
            submitted,
            target,
        ),
        timer,
    )


@router.get("/tasks")
def read_tasks(request: Request) -> Response:
    """Publish every managed task with the context of one reading.

    The reading carries no sorting, filtering, pagination, emphasis or
    metric: those are presentation and analysis concerns, not this
    route's.

    Args:
        request: The submitted HTTP request.

    Returns:
        The managed tasks and the time context of this reading.
    """
    return published(
        services.read_task_list(_settings_of(request), _clock_of(request)),
        OK_STATUS,
    )


@router.get("/operations/{operation_id}")
def read_operation_result(request: Request, operation_id: str) -> Response:
    """Consult the outcome one operation established.

    The transport status of a consultation is not the operation's
    outcome. Either terminal outcome is published with ``200``, because
    the question asked here is answered: the server knows what that
    operation did. Consumers read ``outcome`` and must never read this
    ``200`` as evidence that a task was persisted.

    Args:
        request: The submitted HTTP request.
        operation_id: The original operation identity, as submitted.

    Returns:
        The retained terminal result.

    Raises:
        ProtocolRefusalError: ``INVALID_OPERATION_ENVELOPE`` if the
            identity is not usable, or ``OPERATION_RESULT_UNKNOWN`` if
            no committed result carries it. Unknown is not a rejection,
            a cancellation or a rollback.
    """
    identity = usable_operation_id(request, operation_id)
    retained = services.lookup_operation(_settings_of(request), identity)
    if retained is None:
        raise services.ProtocolRefusalError(ErrorCode.OPERATION_RESULT_UNKNOWN)
    return published(retained, OK_STATUS)


def published(model: BaseModel, status: int) -> Response:
    """Publish one contract model as this server's JSON response.

    The model serializes itself, so the approved wire spelling of
    instants, dates and identities is the one that reaches the desktop
    rather than a framework's rendering of the same values.

    Args:
        model: The contract model to publish.
        status: The HTTP status to answer with.

    Returns:
        The response, marked uncacheable.
    """
    return Response(
        content=model.model_dump_json(),
        status_code=status,
        media_type=JSON_MEDIA_TYPE,
        headers={CACHE_CONTROL_HEADER: NO_STORE},
    )


def usable_operation_id(request: Request, submitted: str) -> UUID:
    """Read a submitted operation identity, or refuse the envelope.

    A usable identity is remembered for this request, so a later failure
    can name the operation the desktop should consult. An unusable one
    is remembered nowhere, so the answer cannot suggest that an
    operation exists.

    Args:
        request: The submitted HTTP request.
        submitted: The identity text as submitted.

    Returns:
        The submitted identity.

    Raises:
        ProtocolRefusalError: ``INVALID_OPERATION_ENVELOPE`` if the text
            is not a usable UUID.
    """
    identity = _usable_identity(submitted)
    _request_state(request)[OPERATION_ID_KEY] = identity
    return identity


def _usable_identity(submitted: str) -> UUID:
    """Read one submitted envelope identity.

    Both the operation and the task target are named by identities the
    server must be able to read before any work starts. Text that is not
    one names nothing, so the request never reaches the operation flow
    and nothing about it is retained.

    Args:
        submitted: The identity text as submitted.

    Returns:
        The submitted identity.

    Raises:
        ProtocolRefusalError: ``INVALID_OPERATION_ENVELOPE`` if the text
            is not a usable UUID.
    """
    try:
        return UUID(submitted.strip())
    except ValueError:
        raise services.ProtocolRefusalError(
            ErrorCode.INVALID_OPERATION_ENVELOPE
        ) from None


async def _submitted_operation(request: Request) -> OperationRequest:
    """Read the operation envelope one task command submitted.

    The identity, the method and the target come from the request
    itself, and the payload is the JSON it carried, parsed but not yet
    judged. Whether those task fields are acceptable is the operation
    flow's decision, not this one's, so an invalid submission still
    reaches the flow and still gets a retained answer.

    Args:
        request: The submitted HTTP request.

    Returns:
        The submitted operation and its envelope values.

    Raises:
        ProtocolRefusalError: ``INVALID_OPERATION_ENVELOPE`` if no
            usable operation identity was supplied or the body is not
            JSON at all.
    """
    identity = usable_operation_id(
        request, request.headers.get(OPERATION_ID_HEADER, "")
    )
    body = await request.body()
    try:
        payload = json.loads(
            body, parse_float=_json_number, parse_constant=_invalid_constant
        )
    except ValueError:
        raise services.ProtocolRefusalError(
            ErrorCode.INVALID_OPERATION_ENVELOPE
        ) from None
    return OperationRequest(
        operation_id=identity,
        method=request.method,
        target=request.url.path,
        payload=payload,
    )


def _invalid_constant(value: str) -> None:
    raise ValueError(f"Not a JSON number: {value}")


def _json_number(value: str) -> float | Decimal:
    # Preserve large valid numbers until strict field validation rejects them.
    number = float(value)
    return number if math.isfinite(number) else Decimal(value)


def _resolved(
    request: Request, result: OperationResult, timer: DurationTimer
) -> Response:
    """Publish and record the terminal result of one attempt.

    The result is already committed when this runs, so the recorded
    success event never describes work that was not persisted. The
    status is the one the attempt was originally settled with, which is
    what makes a repetition answer exactly like the original request.

    Args:
        request: The submitted HTTP request.
        result: The terminal result of the attempt.
        timer: The monotonic measurement started when the request
            arrived.

    Returns:
        The published result.
    """
    _logger.info(
        OPERATION_RESOLVED_EVENT,
        extra={
            "request_id": str(_request_id(request)),
            "operation_id": str(result.operation_id),
            "task_id": None
            if result.task is None
            else str(result.task.task_id),
            "outcome": result.outcome,
            "error_code": (
                None if result.error is None else result.error.code.value
            ),
            "duration_ms": timer.elapsed_ms(),
        },
    )
    return published(result, result.original_http_status)


def _submitted_zone_key(body: bytes) -> str:
    """Read the zone key a setup request submitted.

    Setup takes exactly one field, so a body that cannot be read, is not
    an object, carries another field, or holds anything but text leaves
    the server with no usable zone key. That is the same answer an
    unknown key gets: the submitted zone is not one the server can fix.

    Args:
        body: The submitted request body.

    Returns:
        The submitted zone key, unvalidated.

    Raises:
        ProtocolRefusalError: ``INVALID_TIME_ZONE`` if no usable zone
            key was submitted.
    """
    try:
        payload = json.loads(body)
    except ValueError:
        raise services.ProtocolRefusalError(
            ErrorCode.INVALID_TIME_ZONE
        ) from None
    if not isinstance(payload, dict) or set(payload) != {
        PRODUCT_TIME_ZONE_FIELD
    }:
        raise services.ProtocolRefusalError(ErrorCode.INVALID_TIME_ZONE)
    submitted = payload[PRODUCT_TIME_ZONE_FIELD]
    if not isinstance(submitted, str):
        raise services.ProtocolRefusalError(ErrorCode.INVALID_TIME_ZONE)
    return submitted


def _handle_refusal(request: Request, exception: Exception) -> Response:
    """Answer a refusal that established no terminal outcome.

    Args:
        request: The refused HTTP request.
        exception: The refusal raised by a route or a service.

    Returns:
        The protocol error for that refusal.
    """
    refusal = cast(services.ProtocolRefusalError, exception)
    return _protocol_error(request, refusal.code, REFUSAL_STATUS[refusal.code])


def _handle_storage_failure(
    request: Request, exception: Exception
) -> Response:
    """Answer a storage failure without inventing an outcome.

    A lock wait, an I/O failure or a failed commit leaves the server
    unable to say what happened, so it says exactly that. The desktop
    consults the original operation identity instead.

    Args:
        request: The failed HTTP request.
        exception: The storage failure.

    Returns:
        The protocol error for that failure.
    """
    return _protocol_error(
        request,
        ErrorCode.STORAGE_UNAVAILABLE,
        STORAGE_UNAVAILABLE_STATUS,
    )


def _handle_unexpected(request: Request, exception: Exception) -> Response:
    """Answer an unexpected defect without inventing an outcome.

    The connection helper has already rolled back and closed any
    transaction still open, so no partial work survives this answer.

    Args:
        request: The failed HTTP request.
        exception: The unexpected failure.

    Returns:
        The protocol error for that failure.
    """
    return _protocol_error(
        request, ErrorCode.INTERNAL_ERROR, INTERNAL_ERROR_STATUS
    )


def _protocol_error(
    request: Request, code: ErrorCode, status: int
) -> Response:
    """Build and record one protocol error.

    The response and the log record carry the same request identity, so
    a reported failure can be found in the server's own account of it.
    Neither carries submitted input.

    Args:
        request: The failed HTTP request.
        code: The stable code naming the failure.
        status: The HTTP status to answer with.

    Returns:
        The protocol error response.
    """
    state = _request_state(request)
    operation_id = state.get(OPERATION_ID_KEY)
    error = ProtocolError(
        request_id=_request_id(request),
        error=ProtocolErrorDetail(code=code),
        operation_id=operation_id if isinstance(operation_id, UUID) else None,
    )
    _logger.log(
        (logging.ERROR if status >= SERVER_ERROR_FLOOR else logging.WARNING),
        PROTOCOL_ERROR_EVENT,
        extra={
            "request_id": str(error.request_id),
            "operation_id": (
                None if error.operation_id is None else str(error.operation_id)
            ),
            "error_code": code.value,
        },
    )
    return published(error, status)


def _request_id(request: Request) -> UUID:
    """Name this HTTP request, once.

    Args:
        request: The HTTP request to name.

    Returns:
        The identity of this request, generated on first use and stable
        for the rest of it.
    """
    state = _request_state(request)
    existing = state.get(REQUEST_ID_KEY)
    if isinstance(existing, UUID):
        return existing
    generated = uuid4()
    state[REQUEST_ID_KEY] = generated
    return generated


def _request_state(request: Request) -> dict[str, Any]:
    """Reach the values remembered for one HTTP request.

    Args:
        request: The HTTP request.

    Returns:
        The mutable mapping shared by every layer of that request.
    """
    return cast(dict[str, Any], request.scope.setdefault("state", {}))


def _settings_of(request: Request) -> ServerSettings:
    """Reach the runtime settings the application was composed with.

    Args:
        request: The HTTP request being served.

    Returns:
        The settings of this application.
    """
    return cast(ServerSettings, request.app.state.settings)


def _clock_of(request: Request) -> Clock:
    """Reach the clock the application was composed with.

    Args:
        request: The HTTP request being served.

    Returns:
        The server's source of the current instant.
    """
    return cast(Clock, request.app.state.clock)
