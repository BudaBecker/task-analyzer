"""Unit tests for server time and the product date.

Covers PCE-28, PCE-30 and PCE-31; REQ-028.

Expected microsecond values are derived from calendar day counts, not
from the conversion helpers under test.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from task_analyzer_server.clock import (
    EPOCH,
    Clock,
    SystemClock,
    from_utc_microseconds,
    product_date,
    to_utc_microseconds,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
TOKYO = ZoneInfo("Asia/Tokyo")
UTC_ZONE = ZoneInfo("UTC")

MICROSECONDS_PER_DAY = 86_400_000_000

LAST_SUPPORTED_INSTANT = datetime(9999, 12, 30, 23, 59, 59, 999999, tzinfo=UTC)
LAST_SUPPORTED_MICROSECONDS = 253_402_214_399_999_999
"""2,932,895 days after the epoch, plus 86,399.999999 seconds."""

FIRST_SUPPORTED_INSTANT = datetime(1, 1, 1, tzinfo=UTC)
FIRST_SUPPORTED_MICROSECONDS = -62_135_596_800_000_000
"""719,162 days before the epoch."""


class FixedClock:
    """A clock pinned to one controlled instant.

    Attributes:
        instant: The instant every reading returns.
    """

    def __init__(self, instant: datetime) -> None:
        """Pin the clock.

        Args:
            instant: The instant every reading returns.
        """
        self.instant = instant

    def now(self) -> datetime:
        """Return the pinned instant.

        Returns:
            The instant this clock was built with.
        """
        return self.instant


def test_system_clock_returns_an_aware_utc_instant() -> None:
    """Server time carries an explicit zero UTC offset."""
    instant = SystemClock().now()

    assert instant.tzinfo is not None
    assert instant.utcoffset() == timedelta(0)


def test_system_clock_reads_the_current_utc_moment() -> None:
    """Server time is the UTC wall clock, not a host-local reading."""
    instant = SystemClock().now()

    assert abs(instant - datetime.now(UTC)) < timedelta(seconds=5)


def test_a_substituted_clock_supplies_the_controlled_instant() -> None:
    """A test clock is accepted wherever the server reads time."""
    controlled = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    clock: Clock = FixedClock(controlled)

    assert isinstance(clock, Clock)
    assert clock.now() == controlled


def test_the_epoch_is_zero_microseconds() -> None:
    """The epoch instant is the conversion origin."""
    assert to_utc_microseconds(EPOCH) == 0
    assert from_utc_microseconds(0) == EPOCH


def test_a_whole_day_is_its_exact_microsecond_count() -> None:
    """One day after the epoch is 86,400,000,000 microseconds."""
    instant = datetime(1970, 1, 2, tzinfo=UTC)

    assert to_utc_microseconds(instant) == MICROSECONDS_PER_DAY


def test_instants_before_the_epoch_are_negative() -> None:
    """The first supported instant converts to its negative count."""
    assert (
        to_utc_microseconds(FIRST_SUPPORTED_INSTANT)
        == FIRST_SUPPORTED_MICROSECONDS
    )


def test_the_last_supported_instant_keeps_every_microsecond() -> None:
    """A distant instant is exact, which float seconds cannot be."""
    assert (
        to_utc_microseconds(LAST_SUPPORTED_INSTANT)
        == LAST_SUPPORTED_MICROSECONDS
    )


@pytest.mark.parametrize(
    "instant",
    [
        FIRST_SUPPORTED_INSTANT,
        EPOCH,
        datetime(2026, 9, 13, 12, 0, 0, 123456, tzinfo=UTC),
        LAST_SUPPORTED_INSTANT,
    ],
)
def test_microsecond_conversion_round_trips(instant: datetime) -> None:
    """Storing and reading back an instant changes nothing.

    Args:
        instant: The aware UTC instant to round-trip.
    """
    assert from_utc_microseconds(to_utc_microseconds(instant)) == instant


def test_microseconds_convert_back_to_an_aware_utc_instant() -> None:
    """A stored value reads back with an explicit zero UTC offset."""
    instant = from_utc_microseconds(LAST_SUPPORTED_MICROSECONDS)

    assert instant.utcoffset() == timedelta(0)


def test_conversion_uses_the_absolute_instant_not_its_offset() -> None:
    """The same moment converts alike however it is written."""
    in_utc = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    in_tokyo = datetime(2026, 9, 13, 21, 0, tzinfo=TOKYO)

    assert to_utc_microseconds(in_tokyo) == to_utc_microseconds(in_utc)


def test_a_naive_instant_is_refused_by_conversion() -> None:
    """A value without an offset is never stored as UTC."""
    with pytest.raises(ValueError):
        to_utc_microseconds(datetime(2026, 9, 13, 12, 0))


def test_product_date_reads_the_instant_west_of_utc() -> None:
    """Late UTC evening is still the previous date in Sao Paulo."""
    instant = datetime(2026, 9, 14, 2, 30, tzinfo=UTC)

    assert product_date(instant, SAO_PAULO) == date(2026, 9, 13)


def test_product_date_reads_the_instant_east_of_utc() -> None:
    """Late UTC evening is already the next date in Tokyo."""
    instant = datetime(2026, 9, 13, 22, 0, tzinfo=UTC)

    assert product_date(instant, TOKYO) == date(2026, 9, 14)


def test_product_date_follows_the_configured_zone_only() -> None:
    """One moment gives one product date, however it is written."""
    moment = datetime(2026, 9, 14, 2, 30, tzinfo=UTC)
    same_moment_in_tokyo = moment.astimezone(TOKYO)
    same_moment_in_sao_paulo = moment.astimezone(SAO_PAULO)

    assert product_date(same_moment_in_tokyo, SAO_PAULO) == date(2026, 9, 13)
    assert product_date(same_moment_in_sao_paulo, SAO_PAULO) == date(
        2026, 9, 13
    )
    assert product_date(moment, UTC_ZONE) == date(2026, 9, 14)


def test_product_date_refuses_a_naive_instant() -> None:
    """The host's local zone can never decide the product date."""
    with pytest.raises(ValueError):
        product_date(datetime(2026, 9, 14, 2, 30), SAO_PAULO)


def test_product_date_derives_from_the_substituted_clock() -> None:
    """A controlled instant decides the product date it falls on."""
    clock: Clock = FixedClock(datetime(2026, 9, 14, 2, 30, tzinfo=UTC))

    assert product_date(clock.now(), SAO_PAULO) == date(2026, 9, 13)
