"""
Auth service business logic: validation and rules. No SQL, no HTTP.
"""

import logging

import repository
from _shared.auth import create_token, hash_password, verify_password
from _shared.constants import ROLES, SHIFTS, SPECIALTIES
from _shared.errors import Conflict, Forbidden, NotFound, Unauthorized, ValidationError
from _shared.validation import (
    EMAIL_MAX,
    NAME_MAX,
    get_acme_email,
    get_choice,
    get_pagination,
    get_password,
    get_string,
    raise_if_errors,
    reject_unknown_fields,
)

logger = logging.getLogger(__name__)

REGISTER_FIELDS = {"name", "email", "password"}
LOGIN_FIELDS = {"email", "password"}
PEOPLE_PARAMS = {"page", "page_size", "role", "q"}
ROLE_FIELDS = {"role", "specialty", "shift"}
SEARCH_MAX = 100


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


# ---------- people: admins see every user and change roles ----------

def _require_admin(caller: dict) -> None:
    if caller["role"] != "admin":
        raise Forbidden("Only an admin can manage people")


def list_people(caller: dict, params: dict) -> dict:
    """Every employee, engineer and admin, optionally filtered by role or a name/email search."""
    _require_admin(caller)
    errors: dict[str, str] = {}
    reject_unknown_fields(params, PEOPLE_PARAMS, errors)
    role = get_choice(params, "role", ROLES, errors, required=False)
    search = get_string(params, "q", errors, SEARCH_MAX, required=False)
    raise_if_errors(errors)
    page, page_size = get_pagination(params)
    items, total = repository.list_users(role, search, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def change_role(caller: dict, user_id: int, data: dict) -> dict:
    """
    An admin changes someone's role: promote an employee to engineer, make an
    engineer an admin (for example while the admin is on vacation), or take it
    back. The change applies to their very next request (require_user reads
    the role from the database).

    Becoming an engineer needs a specialty and shift unless they had an
    engineer profile before; any previous profile is kept, so an engineer who
    was made admin goes back to their old specialty and shift.

    Raises:
        Forbidden: the caller is not an admin.
        NotFound: no such user.
        ValidationError: bad role, or specialty/shift missing for a new engineer.
        Conflict: changing your own role, or making someone an employee while
            they are still primary on active tickets.
    """
    _require_admin(caller)
    errors: dict[str, str] = {}
    reject_unknown_fields(data, ROLE_FIELDS, errors)
    role = get_choice(data, "role", ROLES, errors)
    specialty = get_choice(data, "specialty", SPECIALTIES, errors, required=False)
    shift = get_choice(data, "shift", SHIFTS, errors, required=False)
    if (specialty is None) != (shift is None):
        errors["specialty" if specialty is None else "shift"] = "Send specialty and shift together"
    raise_if_errors(errors)

    person = repository.get_person(user_id)
    if person is None:
        raise NotFound("User not found")
    if user_id == caller["id"]:
        # Also guarantees there is always at least one admin left.
        raise Conflict("You can't change your own role. Ask another admin.")

    if role == "engineer" and not (specialty and shift) and not person["specialty"]:
        raise ValidationError("Validation failed", {
            field: "Required to make someone an engineer"
            for field, value in (("specialty", specialty), ("shift", shift)) if not value
        })
    if role == "employee" and person["role"] != "employee":
        active = repository.active_primary_count(user_id)
        if active:
            raise Conflict(f"{person['name']} is primary on {active} active ticket(s). Reassign them first.")

    with repository.transaction():
        if role == "engineer" and specialty and shift:
            repository.save_engineer_profile(user_id, specialty, shift)
        if role != person["role"]:
            repository.set_role(user_id, role)
    return repository.get_person(user_id)


def is_healthy() -> bool:
    """Return True if the database answers a trivial query."""
    try:
        repository.ping()
        return True
    except Exception:  # pylint: disable=broad-except
        logger.exception("Health check failed")
        return False
