"""
Unit tests for backend/_shared/validation.py.

Each helper records a message in an `errors` dict instead of raising, so most
tests check both the returned value and what ended up in `errors`.
"""

from datetime import date

import pytest

from _shared import validation
from _shared.errors import ValidationError


# ---------- is_acme_email ----------

@pytest.mark.parametrize("email", [
    "dana@acme.inc",
    "Dana.Whitfield@ACME.INC",   # case does not matter
    "  dana@acme.inc  ",         # surrounding spaces are trimmed
    "first.last+tag@acme.inc",
])
def test_is_acme_email_accepts_company_addresses(email):
    """Well-formed @acme.inc addresses are accepted."""
    assert validation.is_acme_email(email) is True


@pytest.mark.parametrize("email", [
    "a@acme.inc.evil.com",   # acme.inc is only a subdomain of another domain
    "a@notacme.inc",         # ends with "acme.inc" but is a different domain
    "a@sub.acme.inc",        # subdomains of acme.inc are not company mailboxes
    "a@gmail.com",
    "acme.inc",
    "@acme.inc",             # no local part
    "a b@acme.inc",          # whitespace inside
    "a@b@acme.inc",          # two @
    "",
])
def test_is_acme_email_rejects_everything_else(email):
    """Anything that is not exactly <local>@acme.inc is rejected."""
    assert validation.is_acme_email(email) is False


def test_get_acme_email_lowercases():
    """The stored email is lowercased so login is case-insensitive."""
    errors: dict = {}
    assert validation.get_acme_email({"email": " Dana@ACME.inc "}, "email", errors) == "dana@acme.inc"
    assert errors == {}


def test_get_acme_email_records_error():
    """A non-company email records a clear message."""
    errors: dict = {}
    assert validation.get_acme_email({"email": "dana@gmail.com"}, "email", errors) is None
    assert errors == {"email": "Must be a valid @acme.inc email address"}


# ---------- get_string ----------

def test_get_string_trims():
    """Values are trimmed."""
    errors: dict = {}
    assert validation.get_string({"title": "  Printer jammed \n"}, "title", errors, 50) == "Printer jammed"
    assert errors == {}


@pytest.mark.parametrize("data", [{}, {"title": None}, {"title": ""}, {"title": "   "}])
def test_get_string_missing_or_blank_is_required(data):
    """Missing, null, empty and whitespace-only all count as missing."""
    errors: dict = {}
    assert validation.get_string(data, "title", errors, 50) is None
    assert errors == {"title": "This field is required"}


def test_get_string_optional_missing_is_not_an_error():
    """required=False: missing is fine and returns None."""
    errors: dict = {}
    assert validation.get_string({"q": "  "}, "q", errors, 50, required=False) is None
    assert errors == {}


def test_get_string_too_long():
    """Length is checked after trimming; exactly max_length is allowed."""
    errors: dict = {}
    assert validation.get_string({"t": " " + "x" * 5 + " "}, "t", errors, 5) == "xxxxx"
    assert validation.get_string({"t": "x" * 6}, "t", errors, 5) is None
    assert errors == {"t": "Must be at most 5 characters"}


@pytest.mark.parametrize("value", [123, ["a"], {"a": 1}, True])
def test_get_string_rejects_non_strings(value):
    """Numbers, lists, objects and booleans are not strings."""
    errors: dict = {}
    assert validation.get_string({"title": value}, "title", errors, 50) is None
    assert errors == {"title": "Must be a string"}


# ---------- reject_unknown_fields ----------

def test_reject_unknown_fields_lists_every_extra_field():
    """Each unexpected field gets its own error (e.g. someone sending "role" to register)."""
    errors: dict = {}
    validation.reject_unknown_fields({"name": "x", "role": "admin", "id": 1}, {"name"}, errors)
    assert errors == {"id": "Unknown field", "role": "Unknown field"}


def test_reject_unknown_fields_accepts_known_fields():
    """A body with only allowed fields records nothing."""
    errors: dict = {}
    validation.reject_unknown_fields({"name": "x"}, {"name", "email"}, errors)
    assert errors == {}


# ---------- get_int ----------

@pytest.mark.parametrize(("value", "expected"), [(5, 5), ("5", 5), (" 7 ", 7), (1, 1)])
def test_get_int_accepts_ints_and_digit_strings(value, expected):
    """Ints and digit strings (query parameters are always strings) are accepted."""
    errors: dict = {}
    assert validation.get_int({"n": value}, "n", errors) == expected
    assert errors == {}


@pytest.mark.parametrize("value", [True, False, 1.5, 2.0, "abc", "-3", "1e3", [1]])
def test_get_int_rejects_non_whole_numbers(value):
    """Booleans (a subclass of int in Python), floats and other strings are rejected."""
    errors: dict = {}
    assert validation.get_int({"n": value}, "n", errors) is None
    assert errors == {"n": "Must be a whole number"}


def test_get_int_minimum():
    """Values below the minimum (default 1) are rejected; a custom minimum is honored."""
    errors: dict = {}
    assert validation.get_int({"n": 0}, "n", errors) is None
    assert errors == {"n": "Must be at least 1"}
    errors = {}
    assert validation.get_int({"n": 0}, "n", errors, minimum=0) == 0
    assert errors == {}


@pytest.mark.parametrize("data", [{}, {"n": None}, {"n": ""}])
def test_get_int_required_and_optional(data):
    """Missing values are an error only when required."""
    errors: dict = {}
    assert validation.get_int(data, "n", errors) is None
    assert errors == {"n": "This field is required"}
    errors = {}
    assert validation.get_int(data, "n", errors, required=False) is None
    assert errors == {}


def test_get_int_superscript_digit_is_a_validation_error_not_a_crash():
    """'²'.isdigit() is True, so get_int calls int('²'), which raises instead of recording an error."""
    errors: dict = {}
    assert validation.get_int({"n": "²"}, "n", errors) is None
    assert errors == {"n": "Must be a whole number"}


# ---------- get_number ----------

@pytest.mark.parametrize(("value", "expected"), [(2, 2.0), (1.25, 1.25), (0, 0.0)])
def test_get_number_accepts_json_numbers(value, expected):
    """Ints and floats are returned as float."""
    errors: dict = {}
    assert validation.get_number({"h": value}, "h", errors) == expected
    assert errors == {}


@pytest.mark.parametrize("value", [True, False, "1.5", "", [1], {"h": 1}])
def test_get_number_rejects_bools_and_strings(value):
    """Booleans and strings (even numeric ones) are not numbers."""
    errors: dict = {}
    assert validation.get_number({"h": value}, "h", errors) is None
    assert errors == {"h": "Must be a number"}


def test_get_number_required_and_optional():
    """Missing is an error only when required."""
    errors: dict = {}
    assert validation.get_number({}, "h", errors) is None
    assert errors == {"h": "This field is required"}
    errors = {}
    assert validation.get_number({}, "h", errors, required=False) is None
    assert errors == {}


# ---------- get_date ----------

def test_get_date_parses_iso_string():
    """An ISO date string becomes a date."""
    errors: dict = {}
    assert validation.get_date({"d": "2026-09-23"}, "d", errors) == date(2026, 9, 23)
    assert errors == {}


@pytest.mark.parametrize("value", ["23/09/2026", "2026-02-30", "yesterday", 20260923, ["2026-09-23"]])
def test_get_date_rejects_other_formats(value):
    """Other formats, impossible dates and non-strings are rejected."""
    errors: dict = {}
    assert validation.get_date({"d": value}, "d", errors) is None
    assert errors == {"d": "Must be a date like 2026-09-23"}


@pytest.mark.parametrize("data", [{}, {"d": None}, {"d": ""}])
def test_get_date_required_and_optional(data):
    """Missing is an error only when required."""
    errors: dict = {}
    assert validation.get_date(data, "d", errors) is None
    assert errors == {"d": "This field is required"}
    errors = {}
    assert validation.get_date(data, "d", errors, required=False) is None
    assert errors == {}


# ---------- get_choice ----------

def test_get_choice_valid_value():
    """A listed value is returned."""
    errors: dict = {}
    assert validation.get_choice({"p": "high"}, "p", ("low", "high"), errors) == "high"
    assert errors == {}


def test_get_choice_default_when_missing():
    """With a default, a missing value is not an error and the default is returned."""
    errors: dict = {}
    assert validation.get_choice({}, "p", ("low", "medium"), errors, default="medium") == "medium"
    assert errors == {}


def test_get_choice_required_when_missing():
    """Without a default, a missing required value is an error."""
    errors: dict = {}
    assert validation.get_choice({"p": ""}, "p", ("low",), errors) is None
    assert errors == {"p": "This field is required"}


@pytest.mark.parametrize("value", ["urgent", "HIGH", 1, ["high"]])
def test_get_choice_invalid_value(value):
    """Values outside the list (case-sensitive) are rejected and the options are listed."""
    errors: dict = {}
    assert validation.get_choice({"p": value}, "p", ("low", "high"), errors, default="low") is None
    assert errors == {"p": "Must be one of: low, high"}


# ---------- get_pagination ----------

def test_get_pagination_defaults():
    """No parameters -> page 1 with 25 items."""
    assert validation.get_pagination({}) == (1, 25)


def test_get_pagination_reads_strings():
    """Query parameters arrive as strings."""
    assert validation.get_pagination({"page": "3", "page_size": "100"}) == (3, 100)


@pytest.mark.parametrize(("params", "field"), [
    ({"page_size": "101"}, "page_size"),   # above the maximum of 100
    ({"page_size": "0"}, "page_size"),
    ({"page": "0"}, "page"),
    ({"page": "abc"}, "page"),
    ({"page": "-1"}, "page"),
])
def test_get_pagination_bad_values(params, field):
    """Bad values raise a 400 naming the field."""
    with pytest.raises(ValidationError) as caught:
        validation.get_pagination(params)
    assert field in caught.value.details
    assert caught.value.status == 400


# ---------- get_password ----------

def test_get_password_is_not_trimmed():
    """Spaces are part of the password."""
    errors: dict = {}
    assert validation.get_password({"pw": " secret "}, "pw", errors) == " secret "
    assert errors == {}


def test_get_password_new_needs_eight_characters():
    """New passwords need at least 8 characters; existing (login) passwords do not."""
    errors: dict = {}
    assert validation.get_password({"pw": "short"}, "pw", errors, new=True) is None
    assert errors == {"pw": "Must be at least 8 characters"}
    errors = {}
    assert validation.get_password({"pw": "short"}, "pw", errors) == "short"
    assert errors == {}


def test_get_password_72_byte_limit():
    """bcrypt only uses 72 bytes, so longer passwords are rejected. The limit is bytes, not characters."""
    errors: dict = {}
    assert validation.get_password({"pw": "a" * 72}, "pw", errors, new=True) == "a" * 72
    assert validation.get_password({"pw": "a" * 73}, "pw", errors, new=True) is None
    assert errors == {"pw": "Must be at most 72 bytes"}
    errors = {}
    # 25 "é" characters are 50 bytes (fine); 37 are 74 bytes (too long) though only 37 characters.
    assert validation.get_password({"pw": "é" * 25}, "pw", errors, new=True) == "é" * 25
    assert validation.get_password({"pw": "é" * 37}, "pw", errors, new=True) is None
    assert errors == {"pw": "Must be at most 72 bytes"}


@pytest.mark.parametrize("data", [{}, {"pw": ""}, {"pw": 12345678}, {"pw": None}])
def test_get_password_missing_or_not_a_string(data):
    """Missing, empty and non-string passwords are all "required"."""
    errors: dict = {}
    assert validation.get_password(data, "pw", errors) is None
    assert errors == {"pw": "This field is required"}


# ---------- raise_if_errors ----------

def test_raise_if_errors_does_nothing_without_errors():
    """No errors -> no exception."""
    validation.raise_if_errors({})


def test_raise_if_errors_raises_with_all_details():
    """All collected errors are returned together in `details`."""
    with pytest.raises(ValidationError) as caught:
        validation.raise_if_errors({"a": "bad", "b": "worse"})
    assert caught.value.message == "Validation failed"
    assert caught.value.details == {"a": "bad", "b": "worse"}
