"""
Auth service data access. SQL only, always parameterized.
"""

from _shared import db


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


def ping() -> None:
    """Run a trivial query; raises if the database is unreachable."""
    db.fetch_one("SELECT 1 AS ok")
