"""Business rules for submitted task fields.

Covers PCE-01 through PCE-10, PCE-15 through PCE-18, PCE-23, PCE-48, PCE-51
and PCE-52 (REQ-007, REQ-008, REQ-011, REQ-029) and the completed-task
observation rules TLD-10 and TLD-11 (REQ-009).
"""

from __future__ import annotations

from datetime import date

import regex  # type: ignore[import-untyped]

from task_analyzer_server.contracts import (
    DEADLINE_FIELD,
    OBSERVATIONS_FIELD,
    TITLE_FIELD,
    FieldErrorCode,
    TaskInput,
    ValidationIssue,
)

TITLE_MAX_CLUSTERS = 200
OBSERVATIONS_MAX_CLUSTERS = 5000

MINIMUM_DEADLINE = date(1, 1, 1)
MAXIMUM_DEADLINE = date(9999, 12, 30)

TITLE_EDGE_SPACE = " "
COMPARISON_SPACE = " "

_GRAPHEME_CLUSTER = regex.compile(r"\X")
_DEADLINE_TEXT = regex.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_COMPARISON_SPACE_RUN = regex.compile(f"{COMPARISON_SPACE}{{2,}}")


def validate_task(data: TaskInput) -> tuple[ValidationIssue, ...]:
    """Report every approved rule the submitted fields break."""
    candidates = (
        _title_issue(data.title),
        _observations_issue(data.observations),
        _deadline_issue(data.deadline),
    )
    return tuple(issue for issue in candidates if issue is not None)


def validate_observations(
    observations: str | None,
) -> tuple[ValidationIssue, ...]:
    """Apply the observation rules alone, without title or deadline."""
    issue = _observations_issue(observations)
    return () if issue is None else (issue,)


def title_key(title: str) -> str:
    """Derive the uniqueness comparison key of a submitted title."""
    trimmed = title.strip(TITLE_EDGE_SPACE)
    collapsed: str = _COMPARISON_SPACE_RUN.sub(COMPARISON_SPACE, trimmed)
    return collapsed.casefold()


def _title_issue(title: str) -> ValidationIssue | None:
    """Apply the title rules to one submitted title."""
    trimmed = title.strip(TITLE_EDGE_SPACE)
    if not trimmed or trimmed.isspace():
        return ValidationIssue(
            field=TITLE_FIELD, code=FieldErrorCode.TITLE_REQUIRED
        )
    if _cluster_count(trimmed, TITLE_MAX_CLUSTERS) > TITLE_MAX_CLUSTERS:
        return ValidationIssue(
            field=TITLE_FIELD, code=FieldErrorCode.TITLE_TOO_LONG
        )
    return None


def _observations_issue(observations: str | None) -> ValidationIssue | None:
    """Apply the observation rules to one submitted value."""
    if observations is None:
        return None
    limit = OBSERVATIONS_MAX_CLUSTERS
    if _cluster_count(observations, limit) > limit:
        return ValidationIssue(
            field=OBSERVATIONS_FIELD,
            code=FieldErrorCode.OBSERVATIONS_TOO_LONG,
        )
    return None


def _deadline_issue(deadline: str | None) -> ValidationIssue | None:
    """Apply the deadline rules to one submitted value."""
    if deadline is None:
        return None
    if _parse_deadline(deadline) is None:
        return ValidationIssue(
            field=DEADLINE_FIELD, code=FieldErrorCode.INVALID_DEADLINE
        )
    return None


def _parse_deadline(value: str) -> date | None:
    """Read an accepted deadline text as a calendar date."""
    if _DEADLINE_TEXT.match(value) is None:
        return None
    try:
        parsed = date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return None
    if not MINIMUM_DEADLINE <= parsed <= MAXIMUM_DEADLINE:
        return None
    return parsed


def _cluster_count(text: str, limit: int) -> int:
    """Count user-perceived characters, stopping just past the limit."""
    count = 0
    for _ in _GRAPHEME_CLUSTER.finditer(text):
        count += 1
        if count > limit:
            break
    return count
