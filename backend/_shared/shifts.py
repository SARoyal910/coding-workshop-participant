"""
Engineer shift windows.

Shifts are defined in office time (ACME_TIMEZONE); results are returned in
UTC so they can be compared with database timestamps directly.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from _shared.constants import ACME_TIMEZONE, SHIFT_LENGTH_HOURS, SHIFT_START_HOURS

OFFICE_TZ = ZoneInfo(ACME_TIMEZONE)


def current_or_next_shift(shift: str, at: datetime) -> tuple[datetime, datetime]:
    """
    Return (start, end) in UTC of the shift that contains `at`, or the next one if `at` is between shifts.

    Example (night shift, 23:00-07:00 office time):
        at 02:00 -> yesterday 23:00 to today 07:00 (crosses midnight)
        at 08:00 -> today 23:00 to tomorrow 07:00 (next shift)
    """
    local = at.astimezone(OFFICE_TZ)
    start = local.replace(hour=SHIFT_START_HOURS[shift], minute=0, second=0, microsecond=0)
    if start > local:
        start -= timedelta(days=1)  # The most recent start is yesterday's.
    end = start + timedelta(hours=SHIFT_LENGTH_HOURS)
    if local >= end:
        start += timedelta(days=1)
        end += timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def is_on_shift(shift: str, at: datetime) -> bool:
    """Return True if `at` falls inside a `shift` window (start included, end excluded)."""
    start, end = current_or_next_shift(shift, at)
    return start <= at < end
