"""Unit tests for deadline cutoff resolution.

Covers PCE-32, PCE-33, PCE-49 and PCE-50; REQ-011.

Every expected instant is a literal read from IANA zone-transition
data, never a value produced by the helper under test:

* ``America/Sao_Paulo`` holds -03:00 all year since 2019, so the
  approved September 14 example cuts off at 2026-09-15T03:00:00Z.
* ``America/New_York`` starts DST on 2026-03-08 and ends it on
  2026-11-01, which makes those two calendar days 23 and 25 hours long.
* ``America/Havana`` ends DST on 2026-11-01 at 01:00 local, so midnight
  that day happens twice, at -04:00 then at -05:00. It starts DST on
  2026-03-08 at 00:00 local, so that midnight never happens.
* ``America/Sao_Paulo`` started DST on 2018-11-04 at 00:00 local.
* ``Pacific/Apia`` jumped from 2011-12-29T23:59:59-10:00 straight to
  2011-12-31T00:00:00+14:00, skipping the whole of 2011-12-30.
* ``Etc/GMT-14`` is +14:00 and ``Etc/GMT+11`` is -11:00 at every
  instant, which makes them safe at the supported date endpoints.
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
    """A September 14 deadline cuts off at September 15, 00:00."""
    cutoff = deadline_cutoff(SEPTEMBER_14, SAO_PAULO)

    assert cutoff == SEPTEMBER_15_MIDNIGHT
    assert cutoff.astimezone(SAO_PAULO) == datetime(
        2026, 9, 15, 0, 0, tzinfo=SAO_PAULO
    )


def test_deadline_is_met_throughout_its_own_calendar_date() -> None:
    """The last microsecond of September 14 has not reached the cutoff."""
    last_moment = datetime(2026, 9, 14, 23, 59, 59, 999999, tzinfo=SAO_PAULO)

    assert last_moment < deadline_cutoff(SEPTEMBER_14, SAO_PAULO)


def test_deadline_is_overdue_from_the_next_midnight_onwards() -> None:
    """September 15, 00:00 reaches the cutoff, with no grace period."""
    midnight = datetime(2026, 9, 15, 0, 0, tzinfo=SAO_PAULO)
    cutoff = deadline_cutoff(SEPTEMBER_14, SAO_PAULO)

    assert midnight == cutoff
    assert midnight >= cutoff


def test_cutoff_is_not_the_deadline_start_plus_24_hours() -> None:
    """A 23-hour calendar day cuts off an hour before elapsed 24."""
    deadline = date(2026, 3, 8)
    day_start = datetime(2026, 3, 8, 0, 0, tzinfo=NEW_YORK)

    cutoff = deadline_cutoff(deadline, NEW_YORK)

    assert cutoff == datetime(2026, 3, 9, 4, 0, tzinfo=UTC)
    assert cutoff - day_start == timedelta(hours=23)


def test_cutoff_follows_the_calendar_through_a_25_hour_day() -> None:
    """A 25-hour calendar day cuts off an hour after elapsed 24."""
    day_start = datetime(2026, 11, 1, 0, 0, tzinfo=NEW_YORK)

    cutoff = deadline_cutoff(date(2026, 11, 1), NEW_YORK)

    assert cutoff == datetime(2026, 11, 2, 5, 0, tzinfo=UTC)
    assert cutoff - day_start == timedelta(hours=25)


def test_repeated_midnight_resolves_to_its_first_occurrence() -> None:
    """When midnight happens twice, the earlier instant is the cutoff."""
    cutoff = deadline_cutoff(date(2026, 10, 31), HAVANA)

    assert cutoff == datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
    assert cutoff < datetime(2026, 11, 1, 5, 0, tzinfo=UTC)


def test_both_occurrences_of_a_repeated_midnight_read_alike() -> None:
    """The chosen instant is the first of two identical readings."""
    first = datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
    second = datetime(2026, 11, 1, 5, 0, tzinfo=UTC)
    first_reading = first.astimezone(HAVANA).replace(tzinfo=None)
    second_reading = second.astimezone(HAVANA).replace(tzinfo=None)

    assert first_reading == second_reading == datetime(2026, 11, 1, 0, 0)
    assert deadline_cutoff(date(2026, 10, 31), HAVANA) == first


def test_absent_midnight_resolves_to_the_first_valid_instant() -> None:
    """A midnight skipped by a forward jump moves to the jump itself."""
    cutoff = deadline_cutoff(date(2026, 3, 7), HAVANA)

    assert cutoff == datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
    assert cutoff.astimezone(HAVANA) == datetime(
        2026, 3, 8, 1, 0, tzinfo=HAVANA
    )


def test_absent_midnight_in_a_second_zone() -> None:
    """The rule holds for another zone that starts DST at midnight."""
    cutoff = deadline_cutoff(date(2018, 11, 3), SAO_PAULO)

    assert cutoff == datetime(2018, 11, 4, 3, 0, tzinfo=UTC)


def test_a_wholly_skipped_calendar_date_advances_the_cutoff() -> None:
    """Apia skipped 2011-12-30 entirely, so the cutoff lands after it."""
    cutoff = deadline_cutoff(date(2011, 12, 29), APIA)

    assert cutoff == datetime(2011, 12, 30, 10, 0, tzinfo=UTC)
    assert cutoff.astimezone(APIA) == datetime(2011, 12, 31, 0, 0, tzinfo=APIA)


def test_the_skipped_date_cutoff_is_not_an_offset_addition() -> None:
    """Adding the offset difference to midnight would overshoot."""
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
    """Each fixture resolves to its recorded transition instant.

    Args:
        deadline: The task's deadline date.
        zone: The retained product time zone.
        expected: The instant read from IANA zone-transition data.
    """
    assert deadline_cutoff(deadline, zone) == expected


@pytest.mark.parametrize(
    ("deadline", "zone", "expected"),
    CUTOFF_FIXTURES,
    ids=lambda value: str(value),
)
def test_cutoff_is_the_first_instant_reaching_the_boundary(
    deadline: date, zone: ZoneInfo, expected: datetime
) -> None:
    """The cutoff reaches the boundary and the microsecond before does not.

    Args:
        deadline: The task's deadline date.
        zone: The retained product time zone.
        expected: The instant read from IANA zone-transition data.
    """
    boundary = datetime.combine(
        deadline + timedelta(days=1), datetime.min.time()
    )

    cutoff = deadline_cutoff(deadline, zone)

    assert cutoff.astimezone(zone).replace(tzinfo=None) >= boundary
    previous = (cutoff - ONE_MICROSECOND).astimezone(zone)
    assert previous.replace(tzinfo=None) < boundary
    assert cutoff == expected


def test_cutoff_is_an_aware_utc_instant() -> None:
    """The resolved cutoff carries an explicit zero UTC offset."""
    cutoff = deadline_cutoff(SEPTEMBER_14, SAO_PAULO)

    assert cutoff.utcoffset() == timedelta(0)


def test_a_deadline_with_no_next_calendar_date_is_refused() -> None:
    """The last representable date never yields an invented cutoff."""
    with pytest.raises(ValueError):
        deadline_cutoff(date.max, UTC_ZONE)
