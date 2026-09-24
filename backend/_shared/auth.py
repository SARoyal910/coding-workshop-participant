"""
Password hashing (bcrypt) and JSON Web Tokens (PyJWT).

A token proves who the caller is. Their role, name and email are read from
the database on every request, so a role change (for example an admin's
rights being revoked after a vacation) takes effect immediately rather than
when the 8-hour token expires.
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from _shared.errors import Forbidden, Unauthorized
from _shared.http import get_header

# Bandit B105 mistakes this algorithm name for a password.
TOKEN_ALGORITHM = "HS256"  # nosec B105
TOKEN_LIFETIME = timedelta(hours=8)  # One working shift.


def hash_password(password: str) -> str:
    """Hash a plain-text password with a random salt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if the plain-text password matches the stored hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _secret() -> str:
    """Read JWT_SECRET from the environment, failing loudly if it is missing."""
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise RuntimeError("JWT_SECRET is not set")
    return secret


def create_token(user: dict) -> str:
    """
    Create a signed token for a user row.

    Args:
        user: A dict with at least "id", "role", "name" and "email".
    """
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user["id"]),  # JWT requires "sub" to be a string.
        "role": user["role"],
        "name": user["name"],
        "email": user["email"],
        "iat": now,
        "exp": now + TOKEN_LIFETIME,
    }
    return jwt.encode(claims, _secret(), algorithm=TOKEN_ALGORITHM)


def lookup_account(user_id: int) -> dict | None:
    """Return the user's current role, name and email, or None if the account no longer exists."""
    from _shared import db  # imported here: db -> seed -> auth would otherwise be circular

    return db.fetch_one("SELECT role, name, email FROM users WHERE id = %s", (user_id,))


def require_user(event: dict, roles: tuple[str, ...] | None = None) -> dict:
    """
    Read and verify the Bearer token on a request.

    Args:
        event: The Lambda event. The caller's id is stored on it as "user_id"
            so the request log line can include it.
        roles: If given, the user's role must be one of these.

    Returns:
        A dict with the caller's "id" (int), "role", "name" and "email".

    Raises:
        Unauthorized: the token is missing, invalid or expired, or the account is gone.
        Forbidden: the user's role is not allowed.
    """
    scheme, _, token = get_header(event, "authorization").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized("Missing or malformed Authorization header")

    try:
        claims = jwt.decode(token, _secret(), algorithms=[TOKEN_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Your session expired, please log in again") from exc
    except jwt.InvalidTokenError as exc:
        raise Unauthorized("Invalid token") from exc

    user_id = int(claims["sub"])
    event["user_id"] = user_id
    # The token's role may be out of date; the database is the source of truth.
    account = lookup_account(user_id)
    if account is None:
        raise Unauthorized("Your account no longer exists")
    user = {"id": user_id, "role": account["role"], "name": account["name"], "email": account["email"]}
    if roles and user["role"] not in roles:
        raise Forbidden("You don't have permission to do this")
    return user
