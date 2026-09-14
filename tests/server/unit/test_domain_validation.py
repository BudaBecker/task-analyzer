"""Unit tests for task field validation.

Covers PCE-01 through PCE-10, PCE-15, PCE-16, PCE-48, PCE-51 and PCE-52;
REQ-007, REQ-008, REQ-011.
"""

import pytest

from task_analyzer_server.contracts import (
    DEADLINE_FIELD,
    OBSERVATIONS_FIELD,
    TITLE_FIELD,
    FieldErrorCode,
    TaskInput,
    ValidationIssue,
)
from task_analyzer_server.domain import validate_task

COMBINING_ACUTE = chr(0x0301)
ZERO_WIDTH_JOINER = chr(0x200D)
NO_BREAK_SPACE = chr(0x00A0)
EM_SPACE = chr(0x2003)
ARABIC_INDIC_ZERO = 0x0660

COMBINING_E = "e" + COMBINING_ACUTE

JOINED_FAMILY = ZERO_WIDTH_JOINER.join(
    ("\U0001f468", "\U0001f469", "\U0001f467", "\U0001f466")
)

TOO_LONG_TITLE = ValidationIssue(
    field=TITLE_FIELD, code=FieldErrorCode.TITLE_TOO_LONG
)
REQUIRED_TITLE = ValidationIssue(
    field=TITLE_FIELD, code=FieldErrorCode.TITLE_REQUIRED
)
TOO_LONG_OBSERVATIONS = ValidationIssue(
    field=OBSERVATIONS_FIELD, code=FieldErrorCode.OBSERVATIONS_TOO_LONG
)
INVALID_DEADLINE = ValidationIssue(
    field=DEADLINE_FIELD, code=FieldErrorCode.INVALID_DEADLINE
)


def issues_for(
    title: str = "Read notes",
    observations: str | None = None,
    deadline: str | None = None,
) -> tuple[ValidationIssue, ...]:
    return validate_task(
        TaskInput(title=title, observations=observations, deadline=deadline)
    )


def test_title_only_task_is_accepted() -> None:
    assert issues_for(title="Read notes") == ()


def test_absent_optional_values_are_accepted() -> None:
    assert issues_for(observations=None, deadline=None) == ()


def test_empty_title_is_required() -> None:
    assert issues_for(title="") == (REQUIRED_TITLE,)


def test_space_only_title_is_required() -> None:
    assert issues_for(title="     ") == (REQUIRED_TITLE,)


@pytest.mark.parametrize(
    "title",
    [
        "\t",
        "\n",
        "\r\n",
        NO_BREAK_SPACE,
        EM_SPACE,
        " \t \n ",
    ],
)
def test_unicode_whitespace_title_is_required(title: str) -> None:
    assert issues_for(title=title) == (REQUIRED_TITLE,)


def test_blank_title_is_required_regardless_of_length() -> None:
    assert issues_for(title=" " * 300) == (REQUIRED_TITLE,)


def test_title_of_200_plain_characters_is_accepted() -> None:
    assert issues_for(title="a" * 200) == ()


def test_title_of_201_plain_characters_is_too_long() -> None:
    assert issues_for(title="a" * 201) == (TOO_LONG_TITLE,)


def test_title_of_200_combined_characters_is_accepted() -> None:
    title = COMBINING_E * 200

    assert len(title) == 400
    assert issues_for(title=title) == ()


def test_title_of_201_combined_characters_is_too_long() -> None:
    assert issues_for(title=COMBINING_E * 201) == (TOO_LONG_TITLE,)


def test_title_of_200_joined_emoji_is_accepted() -> None:
    title = JOINED_FAMILY * 200

    assert len(title) == 1400
    assert issues_for(title=title) == ()


def test_title_of_201_joined_emoji_is_too_long() -> None:
    assert issues_for(title=JOINED_FAMILY * 201) == (TOO_LONG_TITLE,)


def test_title_is_counted_after_trimming_edge_spaces() -> None:
    assert issues_for(title=f"   {'a' * 200}   ") == ()


def test_edge_spaces_do_not_rescue_an_overlong_title() -> None:
    assert issues_for(title=f"   {'a' * 201}   ") == (TOO_LONG_TITLE,)


def test_overlong_title_is_rejected_rather_than_shortened() -> None:
    data = TaskInput(title="a" * 201)

    assert validate_task(data) == (TOO_LONG_TITLE,)
    assert data.title == "a" * 201


def test_far_oversized_title_is_still_too_long() -> None:
    assert issues_for(title="a" * 200_000) == (TOO_LONG_TITLE,)


def test_observations_of_5000_plain_characters_are_accepted() -> None:
    assert issues_for(observations="a" * 5000) == ()


def test_observations_of_5001_plain_characters_are_too_long() -> None:
    assert issues_for(observations="a" * 5001) == (TOO_LONG_OBSERVATIONS,)


def test_observations_of_5000_combined_characters_are_accepted() -> None:
    observations = COMBINING_E * 5000

    assert len(observations) == 10000
    assert issues_for(observations=observations) == ()


def test_observations_of_5001_combined_characters_are_too_long() -> None:
    assert issues_for(observations=COMBINING_E * 5001) == (
        TOO_LONG_OBSERVATIONS,
    )


def test_observations_of_5000_joined_emoji_are_accepted() -> None:
    assert issues_for(observations=JOINED_FAMILY * 5000) == ()


def test_observations_of_5001_joined_emoji_are_too_long() -> None:
    assert issues_for(observations=JOINED_FAMILY * 5001) == (
        TOO_LONG_OBSERVATIONS,
    )


def test_observations_with_line_breaks_are_accepted_at_the_limit() -> None:
    observations = ("a" * 9 + "\n") * 500

    assert issues_for(observations=observations) == ()


def test_observations_are_counted_as_supplied() -> None:
    observations = f" {'a' * 4999} "

    assert issues_for(observations=observations) == (TOO_LONG_OBSERVATIONS,)


def test_overlong_observations_are_rejected_rather_than_shortened() -> None:
    supplied = "line one\n" + "a" * 5000
    data = TaskInput(title="Read notes", observations=supplied)

    assert validate_task(data) == (TOO_LONG_OBSERVATIONS,)
    assert data.observations == supplied


def test_valid_deadline_is_accepted() -> None:
    assert issues_for(deadline="2026-09-14") == ()


def test_past_deadline_is_accepted() -> None:
    assert issues_for(deadline="1900-01-01") == ()


def test_minimum_supported_deadline_is_accepted() -> None:
    assert issues_for(deadline="0001-01-01") == ()


def test_maximum_supported_deadline_is_accepted() -> None:
    assert issues_for(deadline="9999-12-30") == ()


def test_last_representable_date_is_rejected() -> None:
    assert issues_for(deadline="9999-12-31") == (INVALID_DEADLINE,)


@pytest.mark.parametrize("deadline", ["0000-12-31", "0000-01-01"])
def test_deadline_below_the_supported_range_is_rejected(
    deadline: str,
) -> None:
    assert issues_for(deadline=deadline) == (INVALID_DEADLINE,)


@pytest.mark.parametrize(
    "deadline",
    ["2026-02-30", "2025-02-29", "2026-13-01", "2026-00-10", "2026-04-31"],
)
def test_non_calendar_deadline_is_rejected(deadline: str) -> None:
    assert issues_for(deadline=deadline) == (INVALID_DEADLINE,)


@pytest.mark.parametrize(
    "deadline",
    [
        "",
        "20260914",
        "2026-9-14",
        "14/09/2026",
        "2026-W38-1",
        "2026-09-14T00:00:00Z",
        "2026-09-14 ",
    ],
)
def test_deadline_outside_the_accepted_spelling_is_rejected(
    deadline: str,
) -> None:
    assert issues_for(deadline=deadline) == (INVALID_DEADLINE,)


def test_non_ascii_digit_deadline_is_rejected() -> None:
    deadline = "".join(
        chr(ARABIC_INDIC_ZERO + int(character))
        if character.isdigit()
        else character
        for character in "2026-09-14"
    )

    assert issues_for(deadline=deadline) == (INVALID_DEADLINE,)


def test_every_broken_rule_is_reported() -> None:
    issues = issues_for(
        title="", observations="a" * 5001, deadline="2026-02-30"
    )

    assert issues == (
        REQUIRED_TITLE,
        TOO_LONG_OBSERVATIONS,
        INVALID_DEADLINE,
    )


def test_rejected_edit_input_is_left_untouched() -> None:
    data = TaskInput(
        title="  ", observations="Chapter 3", deadline="2026-02-30"
    )

    assert validate_task(data) == (REQUIRED_TITLE, INVALID_DEADLINE)
    assert data.title == "  "
    assert data.observations == "Chapter 3"
    assert data.deadline == "2026-02-30"
