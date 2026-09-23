"""
Input validation helpers.

Each helper checks one field and records a message in an `errors` dict
instead of raising right away, so the client gets every problem at once.
Call raise_if_errors(errors) when all fields have been checked.
"""

import re

from _shared.constants import EMAIL_DOMAIN
from _shared.errors import ValidationError

# Maximum lengths (characters) from DESIGN.md section 13.3.
NAME_MAX = 100
EMAIL_MAX = 254
TITLE_MAX = 200
DESCRIPTION_MAX = 5000
NOTE_MAX = 2000
REASON_MAX = 1000

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


def raise_if_errors(errors: dict) -> None:
    """
    Raise a 400 listing every field error, if there are any.

    Raises:
        ValidationError: with details {field: message}.
    """
    if errors:
        raise ValidationError("Validation failed", errors)
