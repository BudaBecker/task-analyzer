"""Wire contracts for the Task Analyzer server.

Covers PCE-01, PCE-10, PCE-11, PCE-16, PCE-26, PCE-38, PCE-40, PCE-41,
PCE-43 and PCE-48 (REQ-007, REQ-008, REQ-010, REQ-029, REQ-031).

Structural parsing of a submitted payload lives here and stays separate
from the business rules in ``domain``. The dependency runs one way only:
this module never imports ``domain`` or ``services``.

Parsing is strict. A payload is either exactly the approved shape or it
is rejected with the stable field codes below, so no value is coerced
and no server-owned field is silently applied. A structurally valid
payload still faces business validation, which keeps a rejected task
operation inside the durable operation flow instead of turning it into a
protocol error.

Framework validation objects and echoed input never cross this boundary:
callers receive only ``ValidationIssue`` pairs of field name and code.

Responses publish exactly the approved fields and nothing else. UTC
instants carry an explicit ``Z`` and six fractional digits, deadlines are
``YYYY-MM-DD``, and identities are canonical lowercase hyphenated UUID
text. A durable operation result always carries a terminal outcome and
exactly one of its task snapshot and its error; a protocol error carries
neither an outcome nor a task, so it can never be mistaken for one.
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
    """Stable field-error codes shared by every rejection result.

    The desktop owns user-facing wording; these codes are the contract.
    ``TITLE_REQUIRED`` also covers an omitted title, because a title is
    the one editable field a save must always supply.
    """

    TITLE_REQUIRED = "TITLE_REQUIRED"
    TITLE_TOO_LONG = "TITLE_TOO_LONG"
    OBSERVATIONS_TOO_LONG = "OBSERVATIONS_TOO_LONG"
    INVALID_DEADLINE = "INVALID_DEADLINE"
    INVALID_FIELD_TYPE = "INVALID_FIELD_TYPE"
    UNEXPECTED_FIELD = "UNEXPECTED_FIELD"


class ErrorCode(StrEnum):
    """Stable codes carried by operation and protocol errors.

    A durable rejection and a protocol error draw from the same
    catalogue, so one code always means one thing to the desktop.
    """

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
    """Read a value as an instant on the UTC timeline.

    Args:
        value: The submitted instant.

    Returns:
        The same instant expressed in UTC.

    Raises:
        ValueError: If the value carries no offset. A naive value would
            be published as UTC while meaning host local time.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            "A published instant must be time-zone aware so it cannot"
            " be labelled UTC while meaning host local time."
        )
    return value.astimezone(UTC)


def _serialize_utc_instant(value: datetime) -> str:
    """Write an instant in the approved UTC wire format.

    Args:
        value: An instant already on the UTC timeline.

    Returns:
        The instant with an explicit ``Z`` and six fractional digits,
        padded without relying on platform date formatting.
    """
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
"""A UTC instant, published with an explicit ``Z`` and six digits."""


class ValidationIssue(BaseModel):
    """One rejected field paired with the code explaining it.

    Attributes:
        field: Name of the rejected input field.
        code: Stable code describing why the field was rejected.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    field: str
    code: FieldErrorCode


class TaskInput(BaseModel):
    """The editable task fields exactly as submitted.

    A save replaces every editable field at once. An omitted optional
    value means absent and an explicit ``null`` clears it, so both reach
    the rest of the server as ``None``. The deadline stays textual here;
    calendar and range rules belong to business validation.

    Attributes:
        title: Submitted title text, untrimmed and untruncated.
        observations: Submitted observations, line breaks preserved, or
            ``None`` when absent or cleared.
        deadline: Submitted calendar-date text, or ``None`` when absent
            or cleared.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    title: str
    observations: str | None = None
    deadline: str | None = None


class TaskInputError(ValueError):
    """Raised when a payload is not the approved task-input shape.

    Attributes:
        issues: The rejected fields and their stable codes, in the order
            they were found and without repetition.
    """

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        """Build the error from the translated issues.

        Args:
            issues: The rejected fields and their stable codes.
        """
        self.issues = issues
        super().__init__("The submitted task payload was not accepted.")


@dataclass(frozen=True, slots=True)
class OperationRequest:
    """One submitted operation bound to its envelope values.

    Attributes:
        operation_id: Client-generated UUID identifying the attempt.
        method: HTTP method of the submitted operation.
        target: Canonical task target path of the operation.
        payload: Parsed JSON payload, before business normalization.
    """

    operation_id: UUID
    method: str
    target: str
    payload: object


class TaskSnapshot(BaseModel):
    """A managed task as the desktop reads it.

    Internal comparison and deletion fields stay out of the contract:
    the title key and the deletion flag are storage concerns. The
    snapshot also omits any dynamic emphasis or metric.

    Attributes:
        task_id: Server-generated task identity.
        title: Title exactly as submitted.
        observations: Observations as submitted, or ``None``.
        deadline: Deadline calendar date, or ``None``.
        status: Whether the task is pending or completed.
        created_at: Original creation instant, sampled by the server.
        completed_at: Latest completion instant, or ``None``.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    task_id: UUID
    title: str
    observations: str | None
    deadline: date | None
    status: Literal["pending", "completed"]
    created_at: UtcInstant
    completed_at: UtcInstant | None


class ConfigurationView(BaseModel):
    """The product configuration as the desktop reads it.

    Attributes:
        configured: Whether a product time zone has been fixed.
        product_time_zone: The retained IANA key, or ``None``.
        server_now: The server instant this view was sampled at.
        product_date: The current product date, or ``None`` while no
            zone is configured.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    configured: bool
    product_time_zone: str | None
    server_now: UtcInstant
    product_date: date | None


class TaskListView(BaseModel):
    """Every managed task, with the time context of one reading.

    Attributes:
        items: The task snapshots, empty when no task is managed. Order
            is not a product guarantee.
        product_time_zone: The retained IANA key, or ``None``.
        server_now: The single server instant sampled for this reading.
        product_date: The current product date, or ``None`` while no
            zone is configured.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    items: tuple[TaskSnapshot, ...]
    product_time_zone: str | None
    server_now: UtcInstant
    product_date: date | None


class OperationError(BaseModel):
    """Why a durable operation was rejected.

    Attributes:
        code: The stable code for this rejection.
        fields: The rejected fields and their codes, empty when the
            rejection is not about a field.
        conflicting_task_id: The task a uniqueness rejection collided
            with, or ``None`` for any other rejection.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    code: ErrorCode
    fields: tuple[ValidationIssue, ...] = ()
    conflicting_task_id: UUID | None = None


class OperationResult(BaseModel):
    """The terminal outcome of one submitted operation.

    The same value answers the original request and every later
    consultation of that operation, so a lost response never changes
    what the operation did. The transport status of a consultation does
    not override ``outcome`` or ``original_http_status``.

    Attributes:
        operation_id: The client-generated identity of the attempt.
        outcome: Whether the operation succeeded or was rejected.
        original_http_status: The status the original request answered
            with.
        task: The resulting task snapshot, or ``None`` for a rejection.
        error: The rejection detail, or ``None`` for a success.
        resolved_at: When the server settled the outcome.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operation_id: UUID
    outcome: Literal["succeeded", "rejected"]
    original_http_status: int
    task: TaskSnapshot | None
    error: OperationError | None
    resolved_at: UtcInstant

    @model_validator(mode="after")
    def _carry_exactly_one_body(self) -> OperationResult:
        """Require exactly one of the task snapshot and the error.

        Returns:
            The validated result.

        Raises:
            ValueError: If both are present or both are absent.
        """
        if (self.task is None) == (self.error is None):
            raise ValueError(
                "An operation result carries exactly one of its task"
                " snapshot and its error."
            )
        return self


class ProtocolErrorDetail(BaseModel):
    """Why a request failed before any operation was registered.

    Attributes:
        code: The stable code for this failure.
        fields: The rejected fields and their codes, empty when the
            failure is not about a field.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    code: ErrorCode
    fields: tuple[ValidationIssue, ...] = ()


class ProtocolError(BaseModel):
    """A transport or envelope failure, never a terminal outcome.

    It carries no outcome and no task, so it cannot be read as evidence
    that an operation was applied, rejected, cancelled or rolled back.
    The request identity correlates the response with the server log
    record; it is neither the operation identity nor part of a stored
    result.

    Attributes:
        request_id: Server-generated identity of this HTTP request.
        error: The failure code and any field detail.
        operation_id: The submitted operation identity, present only
            when a usable one was supplied.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    request_id: UUID
    error: ProtocolErrorDetail
    operation_id: UUID | None = None

    @model_serializer(mode="wrap")
    def _publish(self, handler: SerializerFunctionWrapHandler) -> Any:
        """Publish the operation identity only when one was usable.

        Args:
            handler: The framework's serializer for this model.

        Returns:
            The serialized model, without ``operation_id`` when no
            usable identity was supplied.
        """
        published: Any = handler(self)
        if self.operation_id is None:
            del published[OPERATION_ID_FIELD]
        return published


def parse_task_input(payload: object) -> TaskInput:
    """Parse a submitted payload into the approved task input.

    Args:
        payload: Parsed JSON value taken from the request body.

    Returns:
        The submitted fields, unchanged and untruncated.

    Raises:
        TaskInputError: If the payload is not an object of exactly the
            approved fields and types. The framework error is not
            chained, so neither its objects nor the submitted values can
            leak through a traceback.
    """
    try:
        return TaskInput.model_validate(payload)
    except ValidationError as failure:
        raise TaskInputError(_translate(failure)) from None


def _translate(failure: ValidationError) -> tuple[ValidationIssue, ...]:
    """Translate framework errors into stable issues.

    Args:
        failure: The framework validation error.

    Returns:
        One issue per distinct field and code, in the order reported.
    """
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
    """Build the stable issue for one framework error.

    Args:
        error_type: The framework's error type name.
        location: The framework's field location.

    Returns:
        The field name and stable code for that error.
    """
    field = _field_name(location)
    if error_type == _EXTRA_FORBIDDEN_ERROR:
        return ValidationIssue(
            field=field, code=FieldErrorCode.UNEXPECTED_FIELD
        )
    if error_type == _MISSING_ERROR and field == TITLE_FIELD:
        return ValidationIssue(field=field, code=FieldErrorCode.TITLE_REQUIRED)
    return ValidationIssue(field=field, code=FieldErrorCode.INVALID_FIELD_TYPE)


def _field_name(location: tuple[int | str, ...]) -> str:
    """Name the field a framework error points at.

    Args:
        location: The framework's field location.

    Returns:
        The dotted field name, or the whole-payload name when the error
        is about the payload itself rather than one of its fields.
    """
    if not location:
        return PAYLOAD_FIELD
    return ".".join(str(part) for part in location)
