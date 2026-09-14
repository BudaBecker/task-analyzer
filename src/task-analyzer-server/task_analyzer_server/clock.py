"""Server time, product date, and microsecond conversions.

Covers PCE-28, PCE-30 and PCE-31 (REQ-028).

Instants are aware UTC ``datetime`` values in memory and integer UTC
microseconds in storage. Conversion runs on integers and ``timedelta``,
never on floating-point epoch seconds, so an instant far from the epoch
keeps every microsecond it was given.

The product date is server time read in the retained product zone. A
naive value is refused instead of being read as host local time, so
neither the server's display zone nor the desktop's zone can change what
the product date is.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

_ONE_MICROSECOND = timedelta(microseconds=1)


@runtime_checkable
class Clock(Protocol):
    """The server's source of the current instant.

    Time is the only service dependency a test needs to control, so this
    is the single substitution point: a test supplies its own clock and
    every derived value follows from the instant it returns.
    """

    def now(self) -> datetime:
        """Return the current instant.

        Returns:
            The current instant as an aware UTC value.
        """


class SystemClock:
    """The host clock, always read in UTC."""

    def now(self) -> datetime:
        """Read the current instant from the host clock.

        Returns:
            The current instant as an aware UTC value.
        """
        return datetime.now(UTC)


def to_utc_microseconds(instant: datetime) -> int:
    """Convert an instant into its integer UTC microseconds.

    Args:
        instant: An aware instant, in any zone.

    Returns:
        Whole microseconds since the UTC epoch, negative before it.

    Raises:
        ValueError: If the instant is naive. A naive value would be read
            as host local time, which would make storage depend on the
            server's display zone.
    """
    elapsed = _require_aware(instant).astimezone(UTC) - EPOCH
    return elapsed // _ONE_MICROSECOND


def from_utc_microseconds(microseconds: int) -> datetime:
    """Convert integer UTC microseconds back into an instant.

    Args:
        microseconds: Whole microseconds since the UTC epoch.

    Returns:
        The instant as an aware UTC value.
    """
    return EPOCH + timedelta(microseconds=microseconds)


def product_date(instant: datetime, zone: ZoneInfo) -> date:
    """Read an instant as a calendar date in the product zone.

    Args:
        instant: An aware instant, in any zone.
        zone: The retained product time zone.

    Returns:
        The calendar date that instant falls on in that zone.

    Raises:
        ValueError: If the instant is naive.
    """
    return _require_aware(instant).astimezone(zone).date()


def _require_aware(instant: datetime) -> datetime:
    """Refuse an instant that carries no offset.

    Args:
        instant: The instant to check.

    Returns:
        The same instant, once it is known to be aware.

    Raises:
        ValueError: If the instant has no usable UTC offset.
    """
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError(
            "A server instant must be time-zone aware; a naive value"
            " would be read as the host's local time."
        )
    return instant
