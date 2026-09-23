"""
Auth service business logic: validation and rules. No SQL, no HTTP.
"""

import logging

import repository
from _shared.auth import create_token, hash_password, verify_password
from _shared.errors import Conflict, Unauthorized
from _shared.validation import (
    EMAIL_MAX,
    NAME_MAX,
    get_acme_email,
    get_password,
    get_string,
    raise_if_errors,
    reject_unknown_fields,
)

logger = logging.getLogger(__name__)

REGISTER_FIELDS = {"name", "email", "password"}
LOGIN_FIELDS = {"email", "password"}


def _session(user: dict) -> dict:
    """The response for a successful register/login/refresh: a token plus the user."""
    return {"token": create_token(user), "user": user}


def register(data: dict) -> dict:
    """
    Create an employee account and log the user in.

    Only @acme.inc emails are accepted. The role is always 'employee': sending
    "role" is rejected as an unknown field, so nobody can register as admin.

    Raises:
        ValidationError: a field is missing, invalid or unknown.
        Conflict: the email is already registered.
    """
    errors: dict[str, str] = {}
    reject_unknown_fields(data, REGISTER_FIELDS, errors)
    name = get_string(data, "name", errors, NAME_MAX)
    email = get_acme_email(data, "email", errors)
    password = get_password(data, "password", errors, new=True)
    raise_if_errors(errors)

    user = repository.create_employee(name, email, hash_password(password))
    if user is None:
        raise Conflict("This email is already registered", {"email": "This email is already registered"})
    logger.info("Registered user %s", user["id"])
    return _session(user)


def login(data: dict) -> dict:
    """
    Check an email and password and return a new session.

    Raises:
        ValidationError: a field is missing or unknown.
        Unauthorized: the email/password pair is wrong. The message is the same
            whether or not the account exists, so emails can't be probed.
    """
    errors: dict[str, str] = {}
    reject_unknown_fields(data, LOGIN_FIELDS, errors)
    email = get_string(data, "email", errors, EMAIL_MAX)
    password = get_password(data, "password", errors)
    raise_if_errors(errors)

    user = repository.find_user_by_email(email.lower())
    if user is None or not verify_password(password, user.pop("password_hash")):
        raise Unauthorized("Invalid email or password")
    return _session(user)


def current_user(user_id: int) -> dict:
    """
    Return the user behind a valid token, read fresh from the database.

    Raises:
        Unauthorized: the account no longer exists.
    """
    user = repository.find_user_by_id(user_id)
    if user is None:
        raise Unauthorized("User no longer exists")
    return user


def refresh(user_id: int) -> dict:
    """Issue a new token for a still-valid session, using the user's current role."""
    return _session(current_user(user_id))


def is_healthy() -> bool:
    """Return True if the database answers a trivial query."""
    try:
        repository.ping()
        return True
    except Exception:  # pylint: disable=broad-except
        logger.exception("Health check failed")
        return False
