"""
Unit tests for backend/_shared/auth.py: password hashing and JWT checks.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from _shared import auth
from _shared.errors import Forbidden, Unauthorized

from helpers import ACCOUNTS

USER = {"id": 7, "role": "engineer", "name": "Priya Nair", "email": "priya.nair@acme.inc"}


@pytest.fixture(autouse=True)
def user_account():
    """USER exists in the (faked) users table with the same details as the token."""
    ACCOUNTS[USER["id"]] = {"role": USER["role"], "name": USER["name"], "email": USER["email"]}
    yield
    ACCOUNTS.pop(USER["id"], None)


def bearer(token: str) -> dict:
    """An event carrying this token."""
    return {"headers": {"Authorization": f"Bearer {token}"}}


def test_hash_and_verify_password():
    """A hash verifies its own password only, and never contains the plain text."""
    hashed = auth.hash_password("correct horse")
    assert "correct horse" not in hashed
    assert auth.verify_password("correct horse", hashed) is True
    assert auth.verify_password("wrong horse", hashed) is False


def test_token_round_trip_sets_user_id_on_event():
    """require_user returns the claims and stores the id on the event for logging."""
    event = bearer(auth.create_token(USER))
    assert auth.require_user(event) == USER
    assert event["user_id"] == 7


def test_role_restriction():
    """A role outside the allowed list is 403, not 401 (the token itself is fine)."""
    event = bearer(auth.create_token(USER))
    assert auth.require_user(event, roles=("engineer", "admin"))["id"] == 7
    with pytest.raises(Forbidden):
        auth.require_user(bearer(auth.create_token(USER)), roles=("admin",))


@pytest.mark.parametrize("header", ["", "Bearer", "Bearer ", "Token abc", "abc"])
def test_missing_or_malformed_header(header):
    """No token, or a scheme other than Bearer, is 401."""
    with pytest.raises(Unauthorized, match="Missing or malformed"):
        auth.require_user({"headers": {"authorization": header}})


def test_bearer_scheme_is_case_insensitive():
    """"bearer" works like "Bearer"."""
    event = {"headers": {"authorization": f"bearer {auth.create_token(USER)}"}}
    assert auth.require_user(event)["id"] == 7


def test_token_signed_with_another_secret_is_rejected():
    """A forged token (different key) is 401 "Invalid token"."""
    forged = jwt.encode({"sub": "1", "role": "admin", "name": "x", "email": "x@acme.inc"},
                        "not-the-secret-at-all-but-long-enough", algorithm="HS256")
    with pytest.raises(Unauthorized, match="Invalid token"):
        auth.require_user(bearer(forged))


def test_alg_none_token_is_rejected():
    """An unsigned token ("alg": "none") is not accepted."""
    unsigned = jwt.encode({"sub": "1", "role": "admin", "name": "x", "email": "x@acme.inc"}, None, algorithm="none")
    with pytest.raises(Unauthorized):
        auth.require_user(bearer(unsigned))


def test_expired_token_has_a_clear_message(jwt_secret):
    """Expired tokens get the "session expired" message the frontend shows."""
    past = datetime.now(timezone.utc) - timedelta(hours=9)
    expired = jwt.encode({"sub": "7", "role": "engineer", "name": "x", "email": "x@acme.inc",
                          "iat": past, "exp": past + timedelta(hours=8)}, jwt_secret, algorithm="HS256")
    with pytest.raises(Unauthorized, match="expired"):
        auth.require_user(bearer(expired))


def test_token_lifetime_is_eight_hours(jwt_secret):
    """Tokens last one working shift."""
    claims = jwt.decode(auth.create_token(USER), jwt_secret, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 8 * 3600
    assert claims["sub"] == "7"


def test_missing_secret_fails_loudly(monkeypatch):
    """Without JWT_SECRET the service refuses to sign rather than using an empty key."""
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        auth.create_token(USER)


def test_role_comes_from_the_database_not_the_token():
    """A promotion or demotion applies at once, even to a token issued before it."""
    token = auth.create_token(USER)  # issued while an engineer
    ACCOUNTS[USER["id"]] = {"role": "admin", "name": USER["name"], "email": USER["email"]}
    assert auth.require_user(bearer(token), roles=("admin",))["role"] == "admin"
    ACCOUNTS[USER["id"]] = {"role": "employee", "name": USER["name"], "email": USER["email"]}
    with pytest.raises(Forbidden):
        auth.require_user(bearer(token), roles=("engineer", "admin"))


def test_token_for_a_missing_account_is_401():
    """A valid token for an account that no longer exists is rejected."""
    token = auth.create_token(USER)
    ACCOUNTS.pop(USER["id"])
    with pytest.raises(Unauthorized):
        auth.require_user(bearer(token))
