"""
Auth service data access. SQL only, always parameterized.
"""

from _shared import db
from _shared.db import transaction  # noqa: F401  (re-exported for service.py)


def find_user_by_email(email: str) -> dict | None:
    """Return the user with this email, including password_hash, or None."""
    return db.fetch_one(
        "SELECT id, name, email, role, created_at, password_hash FROM users WHERE email = %s",
        (email,),
    )


def find_user_by_id(user_id: int) -> dict | None:
    """Return the user with this id (without password_hash), or None."""
    return db.fetch_one(
        "SELECT id, name, email, role, created_at FROM users WHERE id = %s",
        (user_id,),
    )


def create_employee(name: str, email: str, password_hash: str) -> dict | None:
    """
    Insert a user with role 'employee'.

    Returns:
        The new user, or None if the email is already taken. ON CONFLICT also
        covers two sign-ups with the same email arriving at the same moment.
    """
    return db.fetch_one(
        "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'employee')"
        " ON CONFLICT (email) DO NOTHING"
        " RETURNING id, name, email, role, created_at",
        (name, email, password_hash),
    )


# ---------- people: the admin's list of users and role changes ----------

def list_users(role: str | None, search: str | None, page: int, page_size: int) -> tuple[list[dict], int]:
    """
    Return one page of users (admins, then engineers, then employees, by name) with
    any engineer profile, and the total count.
    """
    rows = db.fetch_all(
        "SELECT u.id, u.name, u.email, u.role, u.created_at, p.specialty, p.shift, p.is_available,"
        "       count(*) OVER () AS total"
        "  FROM users u LEFT JOIN engineer_profiles p ON p.user_id = u.id"
        " WHERE (%(role)s::text IS NULL OR u.role = %(role)s)"
        "   AND (%(search)s::text IS NULL OR u.name ILIKE %(search)s OR u.email ILIKE %(search)s)"
        " ORDER BY array_position(ARRAY['admin', 'engineer', 'employee'], u.role), u.name"
        " LIMIT %(limit)s OFFSET %(offset)s",
        {
            "role": role, "search": f"%{search}%" if search else None,
            "limit": page_size, "offset": (page - 1) * page_size,
        },
    )
    total = rows[0]["total"] if rows else 0
    for row in rows:
        del row["total"]
    return rows, total


def get_person(user_id: int) -> dict | None:
    """Return one user with any engineer profile, or None."""
    return db.fetch_one(
        "SELECT u.id, u.name, u.email, u.role, u.created_at, p.specialty, p.shift, p.is_available"
        "  FROM users u LEFT JOIN engineer_profiles p ON p.user_id = u.id WHERE u.id = %s",
        (user_id,),
    )


def set_role(user_id: int, role: str) -> None:
    """Change a user's role."""
    db.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))


def save_engineer_profile(user_id: int, specialty: str, shift: str) -> None:
    """Create the user's engineer profile, or update its specialty and shift if they had one before."""
    db.execute(
        "INSERT INTO engineer_profiles (user_id, specialty, shift) VALUES (%s, %s, %s)"
        " ON CONFLICT (user_id) DO UPDATE SET specialty = EXCLUDED.specialty, shift = EXCLUDED.shift",
        (user_id, specialty, shift),
    )


def active_primary_count(user_id: int) -> int:
    """How many active tickets this user is the primary engineer on."""
    row = db.fetch_one(
        "SELECT count(*) AS n FROM incident_engineers ie JOIN incidents i ON i.id = ie.incident_id"
        " WHERE ie.engineer_id = %s AND ie.role = 'primary'"
        "   AND i.status IN ('open', 'in_progress', 'blocked') AND NOT i.is_archived AND NOT i.is_voided",
        (user_id,),
    )
    return row["n"]


def ping() -> None:
    """Run a trivial query; raises if the database is unreachable."""
    db.fetch_one("SELECT 1 AS ok")
