"""HTTP boundary of the Task Analyzer server.

Covers PCE-26, PCE-38, PCE-40 through PCE-43, PCE-46 and PCE-47 (REQ-010,
REQ-027, REQ-029, REQ-031) and the lifecycle routes TLD-01 through TLD-34
(REQ-008, REQ-009, REQ-025, REQ-030).
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from collections.abc import Callable
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

TaskCommand = Callable[
    [ServerSettings, Clock, OperationRequest, UUID], OperationResult
]

router = APIRouter(prefix=API_PREFIX)

_logger = logging.getLogger(__name__)


def install_error_handlers(app: FastAPI) -> None:
    """Install the shared failure handlers on a composed application."""
    app.add_exception_handler(services.ProtocolRefusalError, _handle_refusal)
    app.add_exception_handler(sqlite3.Error, _handle_storage_failure)
    app.add_exception_handler(Exception, _handle_unexpected)


@router.get("/configuration")
def read_configuration(request: Request) -> Response:
    """Publish the product configuration as it currently stands."""
    return published(
        services.read_configuration(_settings_of(request), _clock_of(request)),
        OK_STATUS,
    )


@router.put("/configuration")
async def configure_product_time_zone(request: Request) -> Response:
    """Fix the product time zone, or confirm the one already fixed."""
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
    """Create one pending task from a submitted operation."""
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
    """Replace the editable state of one pending task."""
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


@router.post("/tasks/{task_id}/completion")
async def complete_task(request: Request, task_id: str) -> Response:
    """Complete one pending task."""
    return await _resolved_command(request, task_id, services.complete_task)


@router.put("/tasks/{task_id}/observations")
async def edit_completed_observations(
    request: Request, task_id: str
) -> Response:
    """Replace the observations of one completed task."""
    return await _resolved_command(
        request, task_id, services.edit_completed_observations
    )


@router.post("/tasks/{task_id}/reopening")
async def reopen_task(request: Request, task_id: str) -> Response:
    """Return one completed task to the pending state."""
    return await _resolved_command(request, task_id, services.reopen_task)


@router.delete("/tasks/{task_id}")
async def delete_task(request: Request, task_id: str) -> Response:
    """Remove one managed task from the collection."""
    return await _resolved_command(request, task_id, services.delete_task)


@router.get("/tasks")
def read_tasks(request: Request) -> Response:
    """Publish every managed task with the context of one reading."""
    return published(
        services.read_task_list(_settings_of(request), _clock_of(request)),
        OK_STATUS,
    )


@router.get("/operations/{operation_id}")
def read_operation_result(request: Request, operation_id: str) -> Response:
    """Consult the outcome one operation established."""
    identity = usable_operation_id(request, operation_id)
    retained = services.lookup_operation(_settings_of(request), identity)
    if retained is None:
        raise services.ProtocolRefusalError(ErrorCode.OPERATION_RESULT_UNKNOWN)
    return published(retained, OK_STATUS)


def published(model: BaseModel, status: int) -> Response:
    """Publish one contract model as this server's JSON response."""
    return Response(
        content=model.model_dump_json(),
        status_code=status,
        media_type=JSON_MEDIA_TYPE,
        headers={CACHE_CONTROL_HEADER: NO_STORE},
    )


def usable_operation_id(request: Request, submitted: str) -> UUID:
    """Read a submitted operation identity, or refuse the envelope."""
    identity = _usable_identity(submitted)
    _request_state(request)[OPERATION_ID_KEY] = identity
    return identity


def _usable_identity(submitted: str) -> UUID:
    """Read one submitted envelope identity."""
    try:
        return UUID(submitted.strip())
    except ValueError:
        raise services.ProtocolRefusalError(
            ErrorCode.INVALID_OPERATION_ENVELOPE
        ) from None


async def _submitted_operation(request: Request) -> OperationRequest:
    """Read the operation envelope one task command submitted."""
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


async def _resolved_command(
    request: Request, task_id: str, command: TaskCommand
) -> Response:
    """Resolve one lifecycle command against one identified task."""
    timer = DurationTimer()
    submitted = await _submitted_operation(request)
    target = _usable_identity(task_id)
    return _resolved(
        request,
        await run_in_threadpool(
            command,
            _settings_of(request),
            _clock_of(request),
            submitted,
            target,
        ),
        timer,
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
    """Publish and record the terminal result of one attempt."""
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
    """Read the zone key a setup request submitted."""
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
    """Answer a refusal that established no terminal outcome."""
    refusal = cast(services.ProtocolRefusalError, exception)
    return _protocol_error(request, refusal.code, REFUSAL_STATUS[refusal.code])


def _handle_storage_failure(
    request: Request, exception: Exception
) -> Response:
    """Answer a storage failure without inventing an outcome."""
    return _protocol_error(
        request,
        ErrorCode.STORAGE_UNAVAILABLE,
        STORAGE_UNAVAILABLE_STATUS,
    )


def _handle_unexpected(request: Request, exception: Exception) -> Response:
    """Answer an unexpected defect without inventing an outcome."""
    return _protocol_error(
        request, ErrorCode.INTERNAL_ERROR, INTERNAL_ERROR_STATUS
    )


def _protocol_error(
    request: Request, code: ErrorCode, status: int
) -> Response:
    """Build and record one protocol error."""
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
    """Name this HTTP request, once."""
    state = _request_state(request)
    existing = state.get(REQUEST_ID_KEY)
    if isinstance(existing, UUID):
        return existing
    generated = uuid4()
    state[REQUEST_ID_KEY] = generated
    return generated


def _request_state(request: Request) -> dict[str, Any]:
    """Reach the values remembered for one HTTP request."""
    return cast(dict[str, Any], request.scope.setdefault("state", {}))


def _settings_of(request: Request) -> ServerSettings:
    """Reach the runtime settings the application was composed with."""
    return cast(ServerSettings, request.app.state.settings)


def _clock_of(request: Request) -> Clock:
    """Reach the clock the application was composed with."""
    return cast(Clock, request.app.state.clock)
