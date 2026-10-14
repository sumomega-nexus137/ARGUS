"""Operational clock.

* LIVE mode       → wall clock (UTC).
* SIMULATION mode → per-area simulation clock (``sim_now``), advanced explicitly by users.
* HISTORICAL mode → replay clock (``sim_now``) inside a historical event.

Freshness / data age is always computed against the operational clock so SIMULATION data is
never presented as live.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.models import OperationalArea


def area_now(area: OperationalArea) -> datetime:
    if area.clock_mode == "LIVE" or area.sim_now is None:
        return datetime.now(UTC)
    return area.sim_now


def area_tz(area: OperationalArea) -> timezone:
    return timezone(timedelta(minutes=area.utc_offset_min or 0))


def minutes_between(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 60.0


def to_minutes(ref: datetime, t: datetime) -> float:
    return minutes_between(ref, t)


def from_minutes(ref: datetime, m: float | None) -> datetime | None:
    if m is None or m != m or m in (float("inf"), float("-inf")):
        return None
    return ref + timedelta(minutes=float(m))
