"""Server time, product date, and deadline cutoffs.

Covers PCE-28, PCE-30 through PCE-33, PCE-49 and PCE-50 (REQ-011, REQ-028).
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
    """The server's source of the current instant."""

    def now(self) -> datetime:
        """Return the current instant."""


class SystemClock:
    """The host clock, always read in UTC."""

    def now(self) -> datetime:
        """Read the current instant from the host clock."""
        return datetime.now(UTC)


def to_utc_microseconds(instant: datetime) -> int:
    """Convert an instant into its integer UTC microseconds."""
    elapsed = _require_aware(instant).astimezone(UTC) - EPOCH
    return elapsed // _ONE_MICROSECOND


def from_utc_microseconds(microseconds: int) -> datetime:
    """Convert integer UTC microseconds back into an instant."""
    return EPOCH + timedelta(microseconds=microseconds)


def product_date(instant: datetime, zone: ZoneInfo) -> date:
    """Read an instant as a calendar date in the product zone."""
    return _require_aware(instant).astimezone(zone).date()


def deadline_cutoff(deadline: date, zone: ZoneInfo) -> datetime:
    """Resolve the UTC instant a deadline stops being met."""
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
    """Name the local wall time a deadline's cutoff falls on."""
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
    """Convert both fold readings of a local boundary into UTC."""
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
    """Find the first instant whose local time reaches the boundary."""
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
    """Check a resolved cutoff against the boundary it stands for."""
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
    """Read an instant as the wall time a product-zone clock shows."""
    return instant.astimezone(zone).replace(tzinfo=None)


def _require_aware(instant: datetime) -> datetime:
    """Refuse an instant that carries no offset."""
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError(
            "A server instant must be time-zone aware; a naive value"
            " would be read as the host's local time."
        )
    return instant
