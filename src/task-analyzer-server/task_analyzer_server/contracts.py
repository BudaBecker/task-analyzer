"""Wire contracts for the Task Analyzer server.

Covers PCE-01, PCE-10, PCE-11, PCE-16 and PCE-48 (REQ-007, REQ-008).

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
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

TITLE_FIELD = "title"
OBSERVATIONS_FIELD = "observations"
DEADLINE_FIELD = "deadline"
PAYLOAD_FIELD = "payload"

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
