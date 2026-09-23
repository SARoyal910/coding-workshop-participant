"""
Engineers service data access. SQL only, always parameterized.

An engineer is a users row (role 'engineer') plus an engineer_profiles row.
The service wraps writes that touch both tables in one `transaction()`.
"""

from _shared import db
from _shared.db import transaction  # noqa: F401  (re-exported for service.py)
from _shared.engineer_stats import engineer_workload


def list_engineers(days: int, page: int, page_size: int) -> tuple[list[dict], int]:
    """Return one page of engineers with their workload stats, and the total number of engineers."""
    rows = engineer_workload(days, limit=page_size, offset=(page - 1) * page_size)
    total = rows[0]["total"] if rows else 0
    for row in rows:
        del row["total"]
    return rows, total


def get_engineer(days: int, user_id: int) -> dict | None:
    """Return one engineer with workload stats, or None if this user is not an engineer."""
    rows = engineer_workload(days, engineer_id=user_id)
    if not rows:
        return None
    del rows[0]["total"]
    return rows[0]


def create_user(name: str, email: str, password_hash: str) -> int | None:
    """
    Insert a user with role 'engineer'.

    Returns:
        The new id, or None if the email is already registered.
    """
    row = db.fetch_one(
        "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'engineer')"
        " ON CONFLICT (email) DO NOTHING RETURNING id",
        (name, email, password_hash),
    )
    return row["id"] if row else None


def create_profile(user_id: int, specialty: str, shift: str, phone: str | None) -> None:
    """Insert the engineer profile for a new engineer user (available by default)."""
    db.execute(
        "INSERT INTO engineer_profiles (user_id, specialty, shift, phone) VALUES (%s, %s, %s, %s)",
        (user_id, specialty, shift, phone),
    )


def update_name(user_id: int, name: str) -> None:
    """Change an engineer's display name."""
    db.execute("UPDATE users SET name = %s WHERE id = %s AND role = 'engineer'", (name, user_id))


def update_profile(user_id: int, specialty: str, shift: str, phone: str | None) -> None:
    """Change an engineer's specialty, shift and phone."""
    db.execute(
        "UPDATE engineer_profiles SET specialty = %s, shift = %s, phone = %s WHERE user_id = %s",
        (specialty, shift, phone, user_id),
    )


def set_availability(user_id: int, is_available: bool) -> None:
    """Mark an engineer available or unavailable."""
    db.execute("UPDATE engineer_profiles SET is_available = %s WHERE user_id = %s", (is_available, user_id))
