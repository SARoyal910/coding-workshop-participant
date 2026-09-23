"""
Unit tests for backend/_shared/shifts.py current_or_next_shift.

Shifts are defined in office time (America/New_York): day 07-15, swing 15-23,
night 23-07. Inputs and outputs are UTC, so each test writes the office time
it means and converts it.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from _shared.shifts import current_or_next_shift

OFFICE = ZoneInfo("America/New_York")


def office(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """An office-time moment, returned in UTC (the form the function receives and returns)."""
    return datetime(year, month, day, hour, minute, tzinfo=OFFICE).astimezone(timezone.utc)


@pytest.mark.parametrize(("shift", "at", "start", "end"), [
    # Inside each shift -> that shift (winter, UTC-5).
    ("day", office(2026, 1, 15, 10), office(2026, 1, 15, 7), office(2026, 1, 15, 15)),
    ("swing", office(2026, 1, 15, 18), office(2026, 1, 15, 15), office(2026, 1, 15, 23)),
    ("night", office(2026, 1, 15, 23, 30), office(2026, 1, 15, 23), office(2026, 1, 16, 7)),
    # Night shift crosses midnight: 02:00 belongs to the shift that began yesterday at 23:00.
    ("night", office(2026, 1, 16, 2), office(2026, 1, 15, 23), office(2026, 1, 16, 7)),
    # Boundaries: the start instant is inside, the end instant is not.
    ("day", office(2026, 1, 15, 7), office(2026, 1, 15, 7), office(2026, 1, 15, 15)),
    ("day", office(2026, 1, 15, 15), office(2026, 1, 16, 7), office(2026, 1, 16, 15)),
    # Summer time (UTC-4) works the same way.
    ("day", office(2026, 7, 15, 9), office(2026, 7, 15, 7), office(2026, 7, 15, 15)),
])
def test_current_shift(shift, at, start, end):
    """A moment inside a shift returns that shift's start and end."""
    assert current_or_next_shift(shift, at) == (start, end)


@pytest.mark.parametrize(("shift", "at", "start", "end"), [
    # Between shifts -> the next one.
    ("day", office(2026, 1, 15, 20), office(2026, 1, 16, 7), office(2026, 1, 16, 15)),   # evening
    ("day", office(2026, 1, 15, 5), office(2026, 1, 15, 7), office(2026, 1, 15, 15)),    # early morning
    ("swing", office(2026, 1, 15, 10), office(2026, 1, 15, 15), office(2026, 1, 15, 23)),
    ("night", office(2026, 1, 15, 8), office(2026, 1, 15, 23), office(2026, 1, 16, 7)),  # docstring example
])
def test_between_shifts_returns_next_shift(shift, at, start, end):
    """A moment outside the shift returns the next occurrence."""
    assert current_or_next_shift(shift, at) == (start, end)


def test_results_are_utc():
    """Results are timezone-aware UTC, ready to compare with database timestamps."""
    start, end = current_or_next_shift("day", office(2026, 1, 15, 10))
    assert start.tzinfo == timezone.utc and end.tzinfo == timezone.utc
    assert start == datetime(2026, 1, 15, 12, tzinfo=timezone.utc)  # 07:00 EST = 12:00 UTC


def test_unknown_shift_raises():
    """Only day, swing and night exist."""
    with pytest.raises(KeyError):
        current_or_next_shift("graveyard", office(2026, 1, 15, 10))
