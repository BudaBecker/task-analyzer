"""Server time, product date, and deadline cutoffs.

Covers PCE-28, PCE-30 through PCE-33, PCE-49 and PCE-50 (REQ-011,
REQ-028).

Instants are aware UTC ``datetime`` values in memory and integer UTC
microseconds in storage. Conversion runs on integers and ``timedelta``,
never on floating-point epoch seconds, so an instant far from the epoch
keeps every microsecond it was given.

The product date is server time read in the retained product zone. A
naive value is refused instead of being read as host local time, so
neither the server's display zone nor the desktop's zone can change what
the product date is.

A deadline's cutoff is the local midnight that immediately follows its
calendar date, converted to UTC. It is never the deadline's start plus
24 hours: around an offset change a calendar day is not 24 elapsed
hours. A pending task is overdue from its cutoff onwards, with no grace
period of any kind.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

_ONE_MICROSECOND = timedelta(microseconds=1)
_EARLIEST_INSTANT = datetime.min.replace(tzinfo=UTC)


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


def deadline_cutoff(deadline: date, zone: ZoneInfo) -> datetime:
    """Resolve the UTC instant a deadline stops being met.

    The cutoff is the local midnight immediately after the deadline's
    calendar date, read in the product zone and converted to UTC. Both
    fold candidates for that midnight are round-tripped through UTC:

    * When candidates reproduce the nominal local time, the earliest is
      the cutoff, so a repeated midnight resolves to its first
      occurrence.
    * When none does, the midnight is absent and the candidates bracket
      the forward transition. Bisection on integer UTC microseconds then
      finds the first instant whose local time reaches the boundary.
      That instant may fall on a later calendar date, which is what
      happens when an entire date is skipped.

    Args:
        deadline: The task's deadline date.
        zone: The retained product time zone.

    Returns:
        The cutoff as an aware UTC instant.

    Raises:
        ValueError: If the deadline has no representable next calendar
            date, or if no candidate for that midnight is representable
            in UTC. Task validation rejects such deadlines beforehand,
            so an overflow never becomes a cutoff.
        RuntimeError: If the resolved instant fails the boundary check.
    """
    boundary = _next_calendar_boundary(deadline)
    candidates = _boundary_candidates(boundary, zone)
    exact = tuple(
        candidate
        for candidate in candidates
        if _local_wall_time(candidate, zone) == boundary
    )
    cutoff = (
        min(exact)
        if exact
        else _first_instant_reaching(boundary, zone, candidates)
    )
    _confirm_boundary(cutoff, boundary, zone)
    return cutoff


def _next_calendar_boundary(deadline: date) -> datetime:
    """Name the local wall time a deadline's cutoff falls on.

    Args:
        deadline: The task's deadline date.

    Returns:
        Midnight of the following calendar date, without a zone.

    Raises:
        ValueError: If the following calendar date is not representable.
    """
    if deadline >= date.max:
        raise ValueError(
            f"{deadline.isoformat()} has no representable next calendar"
            " date, so it has no cutoff; it is outside the supported"
            " deadline range."
        )
    return datetime.combine(deadline + timedelta(days=1), time.min)


def _boundary_candidates(
    boundary: datetime, zone: ZoneInfo
) -> tuple[datetime, ...]:
    """Convert both fold readings of a local boundary into UTC.

    Args:
        boundary: The nominal local wall time of the cutoff.
        zone: The retained product time zone.

    Returns:
        The representable candidates, one per fold reading.

    Raises:
        ValueError: If neither reading is representable in UTC.
    """
    candidates: list[datetime] = []
    for fold in (0, 1):
        local = boundary.replace(tzinfo=zone, fold=fold)
        try:
            candidates.append(local.astimezone(UTC))
        except OverflowError:
            continue
    if not candidates:
        raise ValueError(
            f"The cutoff of {boundary.date().isoformat()} in {zone.key}"
            " falls outside the representable range of UTC instants."
        )
    return tuple(candidates)


def _first_instant_reaching(
    boundary: datetime, zone: ZoneInfo, candidates: tuple[datetime, ...]
) -> datetime:
    """Find the first instant whose local time reaches the boundary.

    The candidates bracket a forward transition: the earlier one still
    reads before the boundary, the later one at or after it. Local time
    only moves forward, so bisecting the bracket by whole microseconds
    converges on the first instant at or after the boundary.

    Args:
        boundary: The nominal local wall time of the cutoff.
        zone: The retained product time zone.
        candidates: The representable fold candidates.

    Returns:
        The first instant whose local time is at or after the boundary.
    """
    earlier = min(candidates)
    later = max(candidates)
    while later - earlier > _ONE_MICROSECOND:
        middle = earlier + (later - earlier) // 2
        if _local_wall_time(middle, zone) < boundary:
            earlier = middle
        else:
            later = middle
    return later


def _confirm_boundary(
    cutoff: datetime, boundary: datetime, zone: ZoneInfo
) -> None:
    """Check a resolved cutoff against the boundary it stands for.

    The calendar date of the local reading is deliberately not required
    to match: a skipped date moves the cutoff onto a later one.

    Args:
        cutoff: The resolved instant.
        boundary: The nominal local wall time of the cutoff.
        zone: The retained product time zone.

    Raises:
        RuntimeError: If the instant reads before the boundary, or if
            the microsecond before it already reaches the boundary.
    """
    if _local_wall_time(cutoff, zone) < boundary:
        raise RuntimeError(
            f"The cutoff resolved for {boundary.isoformat()} in"
            f" {zone.key} reads before that boundary."
        )
    if cutoff <= _EARLIEST_INSTANT:
        return
    if _local_wall_time(cutoff - _ONE_MICROSECOND, zone) >= boundary:
        raise RuntimeError(
            f"The cutoff resolved for {boundary.isoformat()} in"
            f" {zone.key} is not the first instant reaching it."
        )


def _local_wall_time(instant: datetime, zone: ZoneInfo) -> datetime:
    """Read an instant as the wall time a product-zone clock shows.

    Args:
        instant: An aware instant.
        zone: The retained product time zone.

    Returns:
        The local wall time, without a zone so it compares by clock
        reading rather than by absolute instant.
    """
    return instant.astimezone(zone).replace(tzinfo=None)


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
