"""Time, timezone and business-date helpers (docs/01_ARCHITECTURE.md section 17).

Pure helpers only: the business timezone is passed in by the caller (the settings
module owns the `org.timezone` value), so the kernel stays free of business policy.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("naive datetimes are not allowed for instants")
    return value.astimezone(UTC)


def business_date_of(instant: datetime, tz: ZoneInfo) -> date:
    return as_utc(instant).astimezone(tz).date()


def business_day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Half-open [start, end) instants for a business date."""
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def at_business_time(day: date, value: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, value, tzinfo=tz).astimezone(UTC)


def shift_bounds(day: date, start: time, end: time, tz: ZoneInfo, crosses_midnight: bool) -> tuple[datetime, datetime]:
    start_at = at_business_time(day, start, tz)
    end_at = at_business_time(day, end, tz)
    if crosses_midnight and end_at <= start_at:
        end_at += timedelta(days=1)
    return start_at, end_at


def floor_minutes(delta: timedelta) -> int:
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        return 0
    return seconds // 60


def seconds_between(start: datetime, end: datetime) -> int:
    return max(0, int((as_utc(end) - as_utc(start)).total_seconds()))


def merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Merge overlapping/adjacent intervals so double punches cannot inflate time."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged: list[tuple[datetime, datetime]] = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def interval_seconds(intervals: list[tuple[datetime, datetime]]) -> int:
    return sum(seconds_between(start, end) for start, end in merge_intervals(intervals))


def intersect_seconds(
    intervals: list[tuple[datetime, datetime]], containers: list[tuple[datetime, datetime]]
) -> int:
    """Total overlap of `intervals` with any interval in `containers`."""
    total = 0
    merged_containers = merge_intervals(containers)
    for start, end in merge_intervals(intervals):
        for c_start, c_end in merged_containers:
            overlap_start = max(start, c_start)
            overlap_end = min(end, c_end)
            if overlap_end > overlap_start:
                total += seconds_between(overlap_start, overlap_end)
    return total


def parse_time_value(raw: str) -> time:
    hour, _, minute = raw.partition(":")
    return time(int(hour), int(minute or 0))


def business_month_bounds(year: int, month: int, tz: ZoneInfo) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end - timedelta(days=1)