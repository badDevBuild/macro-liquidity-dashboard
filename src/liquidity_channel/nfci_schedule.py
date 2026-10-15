"""NFCI release-time freshness shared by collection and the read-only API.

Chicago Fed: Wednesday 08:30 ET, Thursday if a federal holiday falls on
Monday through Wednesday. Reference periods end on the preceding Friday.
https://www.chicagofed.org/research/data/nfci/current-data
https://www.chicagofed.org/research/data/data-release-calendar

The published 2026 calendar was checked on 2026-10-15 (see the test fixture).
Use the existing age limit outside the modern federal-holiday regime rather
than applying today's holiday rules to early historical observations.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
CALENDAR_URL = "https://www.chicagofed.org/research/data/data-release-calendar"


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (occurrence - 1))


def _observed(day: date) -> date:
    return day + timedelta(days=-1 if day.weekday() == 5 else 1 if day.weekday() == 6 else 0)


def _federal_holidays(year: int) -> set[date]:
    # Include adjacent New Year's Day observations crossing the year boundary.
    fixed = [(1, 1), (7, 4), (11, 11), (12, 25)]
    holidays = {
        _observed(date(y, month, day))
        for y in (year - 1, year, year + 1)
        for month, day in fixed
    }
    if year >= 2021:
        holidays.add(_observed(date(year, 6, 19)))
    holidays.update({
        _nth_weekday(year, 1, 0, 3),   # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),   # Washington's Birthday
        date(year, 5, 31) - timedelta(days=date(year, 5, 31).weekday()),
        _nth_weekday(year, 9, 0, 1),   # Labor Day
        _nth_weekday(year, 10, 0, 2),  # Columbus Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving (does not delay Wednesday)
    })
    return holidays


def release_at(reference_end: date) -> datetime | None:
    """Return the release of this reference week, never a release after 'now'."""
    if reference_end.weekday() != 4 or reference_end.year < 1986:
        return None
    monday = reference_end + timedelta(days=3)
    wednesday = monday + timedelta(days=2)
    holidays = _federal_holidays(wednesday.year)
    delayed = any(monday + timedelta(days=offset) in holidays for offset in range(3))
    release_day = wednesday + timedelta(days=int(delayed))
    return datetime.combine(release_day, time(8, 30), NEW_YORK).astimezone(UTC)


def nfci_freshness(
    source: dict[str, Any], observed_at: str, now: datetime
) -> dict[str, Any] | None:
    """Return a bounded window tied to the observation, or use the age fallback.

    No post-release grace: an unchanged upstream row expires at release time.
    The first missed release remains the deadline even weeks/months later.
    """
    if source.get("release_schedule") != "chicago_fed_nfci":
        return None
    current = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    observed = date.fromisoformat(observed_at[:10])
    own_release = release_at(observed)
    next_reference = observed + timedelta(days=7)
    deadline = release_at(next_reference)
    if own_release is None or deadline is None:
        return None
    status = (
        "stale" if current < own_release or current >= deadline
        else "waiting_release" if current.astimezone(NEW_YORK).date() >= next_reference
        else "current"
    )
    return {
        "status": status,
        "basis": "chicago_fed_nfci_release_calendar",
        "expires_at": deadline.isoformat().replace("+00:00", "Z"),
        "expected_observed_at": next_reference.isoformat(),
        "release_timezone": "America/New_York",
        "release_calendar_url": CALENDAR_URL,
    }
