"""Business rules for submitted task fields.

Covers PCE-01 through PCE-10, PCE-15 through PCE-18, PCE-23, PCE-48,
PCE-51 and PCE-52 (REQ-007, REQ-008, REQ-011, REQ-029).

Limits are expressed in user-perceived characters: default extended
grapheme clusters under Unicode UAX #29, segmented with the pinned
``regex`` package. Python's ``len``, UTF-8 byte length and framework
string limits count something else, so none of them implements this
rule.

Validation reads parsed input and reports issues. It never trims,
rewrites or truncates the text it accepts, and it never resolves a
deadline's cutoff: the supported calendar range is settled here, before
any time arithmetic runs.

Title uniqueness compares derived keys, never submitted text. This
module owns the single derivation, so a stored key and a conflict check
can never disagree. Submitted titles stay exactly as submitted.

The dependency runs one way only, from this module to ``contracts``.
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
    """Report every approved rule the submitted fields break.

    Args:
        data: Parsed task input, exactly as submitted.

    Returns:
        At most one issue per field, ordered title, observations, then
        deadline. An empty tuple means the input is acceptable.
    """
    candidates = (
        _title_issue(data.title),
        _observations_issue(data.observations),
        _deadline_issue(data.deadline),
    )
    return tuple(issue for issue in candidates if issue is not None)


def title_key(title: str) -> str:
    """Derive the uniqueness comparison key of a submitted title.

    The key trims edge spaces, reduces every run of comparison spaces to
    one, and applies Unicode case folding. Accents are retained, no
    compatibility normalization runs, and interior tabs or line breaks
    stay as they are rather than becoming spaces. Any further
    equivalence would need its own approval.

    This is the only derivation: stored keys and conflict checks both
    call it, so they cannot disagree. The submitted title is returned to
    the caller untouched, and is stored separately from its key.

    Args:
        title: Submitted title text.

    Returns:
        The comparison key for that title.
    """
    trimmed = title.strip(TITLE_EDGE_SPACE)
    collapsed: str = _COMPARISON_SPACE_RUN.sub(COMPARISON_SPACE, trimmed)
    return collapsed.casefold()


def _title_issue(title: str) -> ValidationIssue | None:
    """Apply the title rules to one submitted title.

    Emptiness is decided first and with Unicode whitespace recognition,
    so a blank title is reported as missing however long it is.

    Args:
        title: Submitted title text.

    Returns:
        The single issue the title raises, or ``None`` when it is
        acceptable.
    """
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
    """Apply the observation rules to one submitted value.

    Observations are counted exactly as supplied, so leading, trailing
    and embedded whitespace all count and line breaks are preserved.

    Args:
        observations: Submitted observations, or ``None`` when absent.

    Returns:
        The single issue the observations raise, or ``None`` when they
        are acceptable.
    """
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
    """Apply the deadline rules to one submitted value.

    Args:
        deadline: Submitted calendar-date text, or ``None`` when absent.

    Returns:
        The single issue the deadline raises, or ``None`` when it is
        acceptable.
    """
    if deadline is None:
        return None
    if _parse_deadline(deadline) is None:
        return ValidationIssue(
            field=DEADLINE_FIELD, code=FieldErrorCode.INVALID_DEADLINE
        )
    return None


def _parse_deadline(value: str) -> date | None:
    """Read an accepted deadline text as a calendar date.

    The accepted spelling is exactly ``YYYY-MM-DD`` in ASCII digits, so
    no alternative ISO 8601 form and no non-ASCII digit slips through.
    A past date is acceptable; only the calendar itself and the approved
    range decide.

    Args:
        value: Submitted deadline text.

    Returns:
        The calendar date, or ``None`` when the text is not a calendar
        date inside the approved range.
    """
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
    """Count user-perceived characters, stopping just past the limit.

    Args:
        text: Text to measure.
        limit: Highest acceptable number of clusters.

    Returns:
        The number of extended grapheme clusters, capped at one above
        the limit because exceeding it is all the caller needs to know.
    """
    count = 0
    for _ in _GRAPHEME_CLUSTER.finditer(text):
        count += 1
        if count > limit:
            break
    return count
