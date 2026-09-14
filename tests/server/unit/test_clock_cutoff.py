"""Unit tests for deadline cutoff resolution.

Covers PCE-32, PCE-33, PCE-49 and PCE-50; REQ-011.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from task_analyzer_server.clock import deadline_cutoff

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
NEW_YORK = ZoneInfo("America/New_York")
HAVANA = ZoneInfo("America/Havana")
APIA = ZoneInfo("Pacific/Apia")
UTC_ZONE = ZoneInfo("UTC")
PLUS_FOURTEEN = ZoneInfo("Etc/GMT-14")
MINUS_ELEVEN = ZoneInfo("Etc/GMT+11")

ONE_MICROSECOND = timedelta(microseconds=1)

SEPTEMBER_14 = date(2026, 9, 14)
SEPTEMBER_15_MIDNIGHT = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)

CUTOFF_FIXTURES = [
    (SEPTEMBER_14, SAO_PAULO, SEPTEMBER_15_MIDNIGHT),
    (date(2026, 3, 8), NEW_YORK, datetime(2026, 3, 9, 4, 0, tzinfo=UTC)),
    (date(2026, 11, 1), NEW_YORK, datetime(2026, 11, 2, 5, 0, tzinfo=UTC)),
    (date(2026, 10, 31), HAVANA, datetime(2026, 11, 1, 4, 0, tzinfo=UTC)),
    (date(2026, 3, 7), HAVANA, datetime(2026, 3, 8, 5, 0, tzinfo=UTC)),
    (date(2018, 11, 3), SAO_PAULO, datetime(2018, 11, 4, 3, 0, tzinfo=UTC)),
    (date(2011, 12, 29), APIA, datetime(2011, 12, 30, 10, 0, tzinfo=UTC)),
    (date(1, 1, 1), UTC_ZONE, datetime(1, 1, 2, 0, 0, tzinfo=UTC)),
    (date(1, 1, 1), PLUS_FOURTEEN, datetime(1, 1, 1, 10, 0, tzinfo=UTC)),
    (date(1, 1, 1), MINUS_ELEVEN, datetime(1, 1, 2, 11, 0, tzinfo=UTC)),
    (date(9999, 12, 30), UTC_ZONE, datetime(9999, 12, 31, 0, 0, tzinfo=UTC)),
    (
        date(9999, 12, 30),
        PLUS_FOURTEEN,
        datetime(9999, 12, 30, 10, 0, tzinfo=UTC),
    ),
    (
        date(9999, 12, 30),
        MINUS_ELEVEN,
        datetime(9999, 12, 31, 11, 0, tzinfo=UTC),
    ),
]


def test_ordinary_cutoff_is_the_next_local_midnight() -> None:
    cutoff = deadline_cutoff(SEPTEMBER_14, SAO_PAULO)

    assert cutoff == SEPTEMBER_15_MIDNIGHT
    assert cutoff.astimezone(SAO_PAULO) == datetime(
        2026, 9, 15, 0, 0, tzinfo=SAO_PAULO
    )


def test_deadline_is_met_throughout_its_own_calendar_date() -> None:
    last_moment = datetime(2026, 9, 14, 23, 59, 59, 999999, tzinfo=SAO_PAULO)

    assert last_moment < deadline_cutoff(SEPTEMBER_14, SAO_PAULO)


def test_deadline_is_overdue_from_the_next_midnight_onwards() -> None:
    midnight = datetime(2026, 9, 15, 0, 0, tzinfo=SAO_PAULO)
    cutoff = deadline_cutoff(SEPTEMBER_14, SAO_PAULO)

    assert midnight == cutoff
    assert midnight >= cutoff


def test_cutoff_is_not_the_deadline_start_plus_24_hours() -> None:
    deadline = date(2026, 3, 8)
    day_start = datetime(2026, 3, 8, 0, 0, tzinfo=NEW_YORK)

    cutoff = deadline_cutoff(deadline, NEW_YORK)

    assert cutoff == datetime(2026, 3, 9, 4, 0, tzinfo=UTC)
    assert cutoff - day_start == timedelta(hours=23)


def test_cutoff_follows_the_calendar_through_a_25_hour_day() -> None:
    day_start = datetime(2026, 11, 1, 0, 0, tzinfo=NEW_YORK)

    cutoff = deadline_cutoff(date(2026, 11, 1), NEW_YORK)

    assert cutoff == datetime(2026, 11, 2, 5, 0, tzinfo=UTC)
    assert cutoff - day_start == timedelta(hours=25)


def test_repeated_midnight_resolves_to_its_first_occurrence() -> None:
    cutoff = deadline_cutoff(date(2026, 10, 31), HAVANA)

    assert cutoff == datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
    assert cutoff < datetime(2026, 11, 1, 5, 0, tzinfo=UTC)


def test_both_occurrences_of_a_repeated_midnight_read_alike() -> None:
    first = datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
    second = datetime(2026, 11, 1, 5, 0, tzinfo=UTC)
    first_reading = first.astimezone(HAVANA).replace(tzinfo=None)
    second_reading = second.astimezone(HAVANA).replace(tzinfo=None)

    assert first_reading == second_reading == datetime(2026, 11, 1, 0, 0)
    assert deadline_cutoff(date(2026, 10, 31), HAVANA) == first


def test_absent_midnight_resolves_to_the_first_valid_instant() -> None:
    cutoff = deadline_cutoff(date(2026, 3, 7), HAVANA)

    assert cutoff == datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
    assert cutoff.astimezone(HAVANA) == datetime(
        2026, 3, 8, 1, 0, tzinfo=HAVANA
    )


def test_absent_midnight_in_a_second_zone() -> None:
    cutoff = deadline_cutoff(date(2018, 11, 3), SAO_PAULO)

    assert cutoff == datetime(2018, 11, 4, 3, 0, tzinfo=UTC)


def test_a_wholly_skipped_calendar_date_advances_the_cutoff() -> None:
    cutoff = deadline_cutoff(date(2011, 12, 29), APIA)

    assert cutoff == datetime(2011, 12, 30, 10, 0, tzinfo=UTC)
    assert cutoff.astimezone(APIA) == datetime(2011, 12, 31, 0, 0, tzinfo=APIA)


def test_the_skipped_date_cutoff_is_not_an_offset_addition() -> None:
    nominal_before_jump = datetime(2011, 12, 30, 10, 0, tzinfo=UTC)
    offset_difference = timedelta(hours=24)

    cutoff = deadline_cutoff(date(2011, 12, 29), APIA)

    assert cutoff == nominal_before_jump
    assert cutoff != nominal_before_jump - offset_difference


@pytest.mark.parametrize(
    ("deadline", "zone", "expected"),
    CUTOFF_FIXTURES,
    ids=lambda value: str(value),
)
def test_cutoff_matches_independently_checked_zone_data(
    deadline: date, zone: ZoneInfo, expected: datetime
) -> None:
    assert deadline_cutoff(deadline, zone) == expected


@pytest.mark.parametrize(
    ("deadline", "zone", "expected"),
    CUTOFF_FIXTURES,
    ids=lambda value: str(value),
)
def test_cutoff_is_the_first_instant_reaching_the_boundary(
    deadline: date, zone: ZoneInfo, expected: datetime
) -> None:
    boundary = datetime.combine(
        deadline + timedelta(days=1), datetime.min.time()
    )

    cutoff = deadline_cutoff(deadline, zone)

    assert cutoff.astimezone(zone).replace(tzinfo=None) >= boundary
    previous = (cutoff - ONE_MICROSECOND).astimezone(zone)
    assert previous.replace(tzinfo=None) < boundary
    assert cutoff == expected


def test_cutoff_is_an_aware_utc_instant() -> None:
    cutoff = deadline_cutoff(SEPTEMBER_14, SAO_PAULO)

    assert cutoff.utcoffset() == timedelta(0)


def test_a_deadline_with_no_next_calendar_date_is_refused() -> None:
    with pytest.raises(ValueError):
        deadline_cutoff(date.max, UTC_ZONE)
