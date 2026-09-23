"""
Engineers service business logic: validation and permissions. No SQL, no HTTP.

Admins create engineer accounts and edit profiles. Engineers can see their
colleagues (who is available, who is overloaded) and set their own
availability. Engineers are never deleted, because tickets, work logs and the
audit log point at them; an admin marks them unavailable instead.
"""

import re
from datetime import datetime, timezone

import repository
from _shared.auth import hash_password
from _shared.constants import METRICS_WINDOW_DAYS, SHIFTS, SPECIALTIES
from _shared.errors import Conflict, Forbidden, NotFound
from _shared.shifts import is_on_shift
from _shared.validation import (
    NAME_MAX,
    get_acme_email,
    get_bool,
    get_choice,
    get_pagination,
    get_password,
    get_string,
    raise_if_errors,
    reject_unknown_fields,
)

CREATE_FIELDS = {"name", "email", "password", "specialty", "shift", "phone"}
UPDATE_FIELDS = {"name", "specialty", "shift", "phone"}
AVAILABILITY_FIELDS = {"is_available"}
LIST_PARAMS = {"page", "page_size"}

PHONE_MAX = 30
# Digits, spaces and + - ( ) . only, e.g. "+1 (555) 010-2233".
PHONE_PATTERN = re.compile(r"^[0-9+()\-. ]{7,30}$")


def _with_flags(engineer: dict) -> dict:
    """
    Add needs_reassignment (unavailable but still primary on active tickets,
    DESIGN.md 13.4) and on_shift_now (their shift is running right now).
    """
    engineer["needs_reassignment"] = not engineer["is_available"] and engineer["active_primary"] > 0
    engineer["on_shift_now"] = is_on_shift(engineer["shift"], datetime.now(timezone.utc))
    return engineer


def _load(user_id: int) -> dict:
    """Return one engineer with stats, or raise NotFound."""
    engineer = repository.get_engineer(METRICS_WINDOW_DAYS, user_id)
    if engineer is None:
        raise NotFound("Engineer not found")
    return _with_flags(engineer)


def _read_profile(data: dict, errors: dict) -> tuple[str, str, str | None]:
    """Validate the profile fields shared by create and update."""
    specialty = get_choice(data, "specialty", SPECIALTIES, errors)
    shift = get_choice(data, "shift", SHIFTS, errors)
    phone = get_string(data, "phone", errors, PHONE_MAX, required=False)
    if phone and not PHONE_PATTERN.match(phone):
        errors["phone"] = "Use digits, spaces and + - ( ) only, at least 7 characters"
    return specialty, shift, phone


def list_engineers(params: dict) -> dict:
    """Return one page of engineers with workload stats: {"items", "total", "page", "page_size"}."""
    errors: dict[str, str] = {}
    reject_unknown_fields(params, LIST_PARAMS, errors)
    raise_if_errors(errors)
    page, page_size = get_pagination(params)
    items, total = repository.list_engineers(METRICS_WINDOW_DAYS, page, page_size)
    return {"items": [_with_flags(item) for item in items], "total": total, "page": page, "page_size": page_size}


def create_engineer(data: dict) -> dict:
    """
    Create an engineer account with its profile. The admin sets the first password.

    Raises:
        ValidationError: missing or invalid fields.
        Conflict: the email is already registered (by anyone).
    """
    errors: dict[str, str] = {}
    reject_unknown_fields(data, CREATE_FIELDS, errors)
    name = get_string(data, "name", errors, NAME_MAX)
    email = get_acme_email(data, "email", errors)
    password = get_password(data, "password", errors, new=True)
    specialty, shift, phone = _read_profile(data, errors)
    raise_if_errors(errors)

    with repository.transaction():
        user_id = repository.create_user(name, email, hash_password(password))
        if user_id is None:
            raise Conflict("This email is already registered", {"email": "This email is already registered"})
        repository.create_profile(user_id, specialty, shift, phone)
    return _load(user_id)


def update_engineer(user_id: int, data: dict) -> dict:
    """
    Change an engineer's name, specialty, shift and phone (all sent together).

    Raises:
        NotFound: no engineer with this id.
        ValidationError: missing or invalid fields.
    """
    _load(user_id)
    errors: dict[str, str] = {}
    reject_unknown_fields(data, UPDATE_FIELDS, errors)
    name = get_string(data, "name", errors, NAME_MAX)
    specialty, shift, phone = _read_profile(data, errors)
    raise_if_errors(errors)

    with repository.transaction():
        repository.update_name(user_id, name)
        repository.update_profile(user_id, specialty, shift, phone)
    return _load(user_id)


def set_availability(user: dict, user_id: int, data: dict) -> dict:
    """
    Mark an engineer available or unavailable. Admins can do this for anyone,
    engineers only for themselves. Going unavailable while primary on active
    tickets is allowed; the response (and admin dashboard) flags needs_reassignment.

    Raises:
        Forbidden: an engineer changing someone else.
        NotFound: no engineer with this id.
        ValidationError: is_available is missing or not a boolean.
    """
    if user["role"] != "admin" and user["id"] != user_id:
        raise Forbidden("You can only change your own availability")
    _load(user_id)
    errors: dict[str, str] = {}
    reject_unknown_fields(data, AVAILABILITY_FIELDS, errors)
    is_available = get_bool(data, "is_available", errors)
    raise_if_errors(errors)

    repository.set_availability(user_id, is_available)
    return _load(user_id)
