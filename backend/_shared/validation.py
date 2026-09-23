"""
Input validation helpers.

Each helper checks one field and records a message in an `errors` dict
instead of raising right away, so the client gets every problem at once.
Call raise_if_errors(errors) when all fields have been checked.
"""

import math
import re
from datetime import date

from _shared.constants import EMAIL_DOMAIN
from _shared.errors import ValidationError

# Maximum lengths (characters) from DESIGN.md section 13.3.
NAME_MAX = 100
EMAIL_MAX = 254
TITLE_MAX = 200
DESCRIPTION_MAX = 5000
NOTE_MAX = 2000
REASON_MAX = 1000

PAGE_SIZE_DEFAULT = 25
PAGE_SIZE_MAX = 100

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72  # bcrypt only uses the first 72 bytes.

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_acme_email(email: str) -> bool:
    """Return True if the address is a well-formed @acme.inc email."""
    email = email.strip().lower()
    return bool(EMAIL_PATTERN.match(email)) and email.endswith("@" + EMAIL_DOMAIN)


def reject_unknown_fields(data: dict, allowed: set[str], errors: dict) -> None:
    """Record an error for every field in the body that the endpoint does not accept."""
    for field in sorted(set(data) - allowed):
        errors[field] = "Unknown field"


def get_string(data: dict, field: str, errors: dict, max_length: int, required: bool = True) -> str | None:
    """
    Read a string field. It is trimmed, and empty after trimming counts as missing.

    Returns:
        The trimmed value, or None if it is missing or invalid (an error is recorded).
    """
    value = data.get(field)
    if value is not None and not isinstance(value, str):
        errors[field] = "Must be a string"
        return None
    value = (value or "").strip()
    if not value:
        if required:
            errors[field] = "This field is required"
        return None
    if len(value) > max_length:
        errors[field] = f"Must be at most {max_length} characters"
        return None
    return value


def get_acme_email(data: dict, field: str, errors: dict) -> str | None:
    """Read an email field that must be an @acme.inc address. Returns it lowercased."""
    email = get_string(data, field, errors, EMAIL_MAX)
    if email is None:
        return None
    if not is_acme_email(email):
        errors[field] = f"Must be a valid @{EMAIL_DOMAIN} email address"
        return None
    return email.lower()


def get_password(data: dict, field: str, errors: dict, new: bool = False) -> str | None:
    """
    Read a password. Passwords are never trimmed.

    Args:
        new: True when the password is being set, which also checks its length.
    """
    password = data.get(field)
    if not isinstance(password, str) or not password:
        errors[field] = "This field is required"
        return None
    if new and len(password) < PASSWORD_MIN_LENGTH:
        errors[field] = f"Must be at least {PASSWORD_MIN_LENGTH} characters"
        return None
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        errors[field] = f"Must be at most {PASSWORD_MAX_BYTES} bytes"
        return None
    return password


def get_int(data: dict, field: str, errors: dict, required: bool = True, minimum: int = 1) -> int | None:
    """Read a whole-number field (e.g. an id or version). Strings of digits are accepted for query params."""
    value = data.get(field)
    if value is None or value == "":
        if required:
            errors[field] = "This field is required"
        return None
    # isascii + isdecimal: plain 0-9 only ("²" counts as a digit for isdigit() but int() rejects it).
    if isinstance(value, str) and value.strip().isascii() and value.strip().isdecimal():
        value = int(value)
    # bool is a subclass of int in Python, so reject it explicitly.
    if not isinstance(value, int) or isinstance(value, bool):
        errors[field] = "Must be a whole number"
        return None
    if value < minimum:
        errors[field] = f"Must be at least {minimum}"
        return None
    return value


def get_number(data: dict, field: str, errors: dict, required: bool = True) -> float | None:
    """Read a JSON number (int or float, not a boolean or string)."""
    value = data.get(field)
    if value is None:
        if required:
            errors[field] = "This field is required"
        return None
    # JSON parsing accepts NaN and Infinity, so reject anything that isn't a finite number.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        errors[field] = "Must be a number"
        return None
    return float(value)


def get_date(data: dict, field: str, errors: dict, required: bool = True) -> date | None:
    """Read a date sent as an ISO string, e.g. "2026-09-23"."""
    value = data.get(field)
    if value is None or value == "":
        if required:
            errors[field] = "This field is required"
        return None
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    errors[field] = "Must be a date like 2026-09-23"
    return None


def get_choice(data: dict, field: str, choices: tuple[str, ...], errors: dict,
               required: bool = True, default: str | None = None) -> str | None:
    """Read a field whose value must be one of `choices`."""
    value = data.get(field)
    if value is None or value == "":
        if required and default is None:
            errors[field] = "This field is required"
        return default
    if value not in choices:
        errors[field] = f"Must be one of: {', '.join(choices)}"
        return None
    return value


def get_pagination(params: dict) -> tuple[int, int]:
    """
    Read ?page= and ?page_size= (defaults 1 and 25, page_size at most 100).

    Raises:
        ValidationError: either value is not a positive whole number or is too large.
    """
    errors: dict[str, str] = {}
    page = get_int(params, "page", errors, required=False) or 1
    page_size = get_int(params, "page_size", errors, required=False) or PAGE_SIZE_DEFAULT
    if page_size > PAGE_SIZE_MAX:
        errors["page_size"] = f"Must be at most {PAGE_SIZE_MAX}"
    raise_if_errors(errors)
    return page, page_size


def raise_if_errors(errors: dict) -> None:
    """
    Raise a 400 listing every field error, if there are any.

    Raises:
        ValidationError: with details {field: message}.
    """
    if errors:
        raise ValidationError("Validation failed", errors)
