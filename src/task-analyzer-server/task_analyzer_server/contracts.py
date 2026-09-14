"""Wire contracts for the Task Analyzer server.

Covers PCE-01, PCE-10, PCE-11, PCE-16, PCE-26, PCE-38, PCE-40, PCE-41,
PCE-43 and PCE-48 (REQ-007, REQ-008, REQ-010, REQ-029, REQ-031).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    PlainSerializer,
    SerializerFunctionWrapHandler,
    ValidationError,
    model_serializer,
    model_validator,
)

TITLE_FIELD = "title"
OBSERVATIONS_FIELD = "observations"
DEADLINE_FIELD = "deadline"
PAYLOAD_FIELD = "payload"

OPERATION_ID_FIELD = "operation_id"

_EXTRA_FORBIDDEN_ERROR = "extra_forbidden"
_MISSING_ERROR = "missing"


class FieldErrorCode(StrEnum):
    """Stable field-error codes shared by every rejection result."""

    TITLE_REQUIRED = "TITLE_REQUIRED"
    TITLE_TOO_LONG = "TITLE_TOO_LONG"
    OBSERVATIONS_TOO_LONG = "OBSERVATIONS_TOO_LONG"
    INVALID_DEADLINE = "INVALID_DEADLINE"
    INVALID_FIELD_TYPE = "INVALID_FIELD_TYPE"
    UNEXPECTED_FIELD = "UNEXPECTED_FIELD"


class ErrorCode(StrEnum):
    """Stable codes carried by operation and protocol errors."""

    TASK_VALIDATION_FAILED = "TASK_VALIDATION_FAILED"
    TASK_UNIQUENESS_CONFLICT = "TASK_UNIQUENESS_CONFLICT"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_STATE_INCOMPATIBLE = "TASK_STATE_INCOMPATIBLE"
    OPERATION_ID_REUSED = "OPERATION_ID_REUSED"
    INVALID_OPERATION_ENVELOPE = "INVALID_OPERATION_ENVELOPE"
    OPERATION_RESULT_UNKNOWN = "OPERATION_RESULT_UNKNOWN"
    PRODUCT_TIME_ZONE_REQUIRED = "PRODUCT_TIME_ZONE_REQUIRED"
    PRODUCT_TIME_ZONE_FIXED = "PRODUCT_TIME_ZONE_FIXED"
    INVALID_TIME_ZONE = "INVALID_TIME_ZONE"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def _as_utc_instant(value: datetime) -> datetime:
    """Read a value as an instant on the UTC timeline."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            "A published instant must be time-zone aware so it cannot"
            " be labelled UTC while meaning host local time."
        )
    return value.astimezone(UTC)


def _serialize_utc_instant(value: datetime) -> str:
    """Write an instant in the approved UTC wire format."""
    return (
        f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
        f"T{value.hour:02d}:{value.minute:02d}:{value.second:02d}"
        f".{value.microsecond:06d}Z"
    )


UtcInstant = Annotated[
    datetime,
    AfterValidator(_as_utc_instant),
    PlainSerializer(_serialize_utc_instant, return_type=str, when_used="json"),
]


class ValidationIssue(BaseModel):
    """One rejected field paired with the code explaining it."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    field: str
    code: FieldErrorCode


class TaskInput(BaseModel):
    """The editable task fields exactly as submitted."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    title: str
    observations: str | None = None
    deadline: str | None = None


class TaskInputError(ValueError):
    """Raised when a payload is not the approved task-input shape."""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        """Build the error from the translated issues."""
        self.issues = issues
        super().__init__("The submitted task payload was not accepted.")


@dataclass(frozen=True, slots=True)
class OperationRequest:
    """One submitted operation bound to its envelope values."""

    operation_id: UUID
    method: str
    target: str
    payload: object


class TaskSnapshot(BaseModel):
    """A managed task as the desktop reads it."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    task_id: UUID
    title: str
    observations: str | None
    deadline: date | None
    status: Literal["pending", "completed"]
    created_at: UtcInstant
    completed_at: UtcInstant | None


class ConfigurationView(BaseModel):
    """The product configuration as the desktop reads it."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    configured: bool
    product_time_zone: str | None
    server_now: UtcInstant
    product_date: date | None


class TaskListView(BaseModel):
    """Every managed task, with the time context of one reading."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    items: tuple[TaskSnapshot, ...]
    product_time_zone: str | None
    server_now: UtcInstant
    product_date: date | None


class OperationError(BaseModel):
    """Why a durable operation was rejected."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    code: ErrorCode
    fields: tuple[ValidationIssue, ...] = ()
    conflicting_task_id: UUID | None = None


class OperationResult(BaseModel):
    """The terminal outcome of one submitted operation."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operation_id: UUID
    outcome: Literal["succeeded", "rejected"]
    original_http_status: int
    task: TaskSnapshot | None
    error: OperationError | None
    resolved_at: UtcInstant

    @model_validator(mode="after")
    def _carry_exactly_one_body(self) -> OperationResult:
        """Require exactly one of the task snapshot and the error."""
        if (self.task is None) == (self.error is None):
            raise ValueError(
                "An operation result carries exactly one of its task"
                " snapshot and its error."
            )
        return self


class ProtocolErrorDetail(BaseModel):
    """Why a request failed before any operation was registered."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    code: ErrorCode
    fields: tuple[ValidationIssue, ...] = ()


class ProtocolError(BaseModel):
    """A transport or envelope failure, never a terminal outcome."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    request_id: UUID
    error: ProtocolErrorDetail
    operation_id: UUID | None = None

    @model_serializer(mode="wrap")
    def _publish(self, handler: SerializerFunctionWrapHandler) -> Any:
        """Publish the operation identity only when one was usable."""
        published: Any = handler(self)
        if self.operation_id is None:
            del published[OPERATION_ID_FIELD]
        return published


def parse_task_input(payload: object) -> TaskInput:
    """Parse a submitted payload into the approved task input."""
    try:
        return TaskInput.model_validate(payload)
    except ValidationError as failure:
        raise TaskInputError(_translate(failure)) from None


def _translate(failure: ValidationError) -> tuple[ValidationIssue, ...]:
    """Translate framework errors into stable issues."""
    issues: list[ValidationIssue] = []
    details = failure.errors(
        include_url=False, include_context=False, include_input=False
    )
    for error in details:
        issue = _issue_for(error["type"], error["loc"])
        if issue not in issues:
            issues.append(issue)
    return tuple(issues)


def _issue_for(
    error_type: str, location: tuple[int | str, ...]
) -> ValidationIssue:
    """Build the stable issue for one framework error."""
    field = _field_name(location)
    if error_type == _EXTRA_FORBIDDEN_ERROR:
        return ValidationIssue(
            field=field, code=FieldErrorCode.UNEXPECTED_FIELD
        )
    if error_type == _MISSING_ERROR and field == TITLE_FIELD:
        return ValidationIssue(field=field, code=FieldErrorCode.TITLE_REQUIRED)
    return ValidationIssue(field=field, code=FieldErrorCode.INVALID_FIELD_TYPE)


def _field_name(location: tuple[int | str, ...]) -> str:
    """Name the field a framework error points at."""
    if not location:
        return PAYLOAD_FIELD
    return ".".join(str(part) for part in location)
