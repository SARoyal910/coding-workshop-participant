"""
Tests for the auth service through the real Lambda handler, with the
repository (SQL) replaced by an in-memory fake. No database is needed.
"""

from types import SimpleNamespace

import pytest

from helpers import make_event, response_json, token_for

PASSWORD = "correct-horse-battery"  # nosec B105 - test data only


@pytest.fixture(scope="module")
def password_hash() -> str:
    """bcrypt is slow on purpose, so hash the test password once per module."""
    from _shared.auth import hash_password

    return hash_password(PASSWORD)


@pytest.fixture
def auth(load_service, monkeypatch, password_hash):
    """
    The auth service with a fake repository holding one existing user.

    `state.users` maps email -> row; `state.db_up` controls /health.
    """
    svc = load_service("auth")
    existing = {"id": 5, "name": "Dana Whitfield", "email": "dana@acme.inc", "role": "employee",
                "created_at": "2026-01-01T00:00:00+00:00", "password_hash": password_hash}
    state = SimpleNamespace(handler=svc.function.handler, users={existing["email"]: existing}, db_up=True)

    def find_user_by_email(email):
        """Return a copy, like a fresh database row (the service pops password_hash from it)."""
        row = state.users.get(email)
        return dict(row) if row else None

    def find_user_by_id(user_id):
        for row in state.users.values():
            if row["id"] == user_id:
                return {key: value for key, value in row.items() if key != "password_hash"}
        return None

    def create_employee(name, email, hashed):
        """Mimic INSERT ... ON CONFLICT (email) DO NOTHING RETURNING ..."""
        if email in state.users:
            return None
        row = {"id": 100 + len(state.users), "name": name, "email": email, "role": "employee",
               "created_at": "2026-01-02T00:00:00+00:00", "password_hash": hashed}
        state.users[email] = row
        return {key: value for key, value in row.items() if key != "password_hash"}

    def ping():
        if not state.db_up:
            raise ConnectionError("database unreachable")

    repo = svc.repository
    monkeypatch.setattr(repo, "find_user_by_email", find_user_by_email)
    monkeypatch.setattr(repo, "find_user_by_id", find_user_by_id)
    monkeypatch.setattr(repo, "create_employee", create_employee)
    monkeypatch.setattr(repo, "ping", ping)
    return state


def post(state, path: str, body: dict | str) -> tuple[int, dict]:
    """POST to the auth handler without a token."""
    response = state.handler(make_event("POST", path, body))
    return response["statusCode"], response_json(response)


# ---------- register ----------

def test_register_creates_employee_and_returns_token(auth):
    """A valid @acme.inc sign-up returns 201 with a token; the role is always employee."""
    status, body = post(auth, "/api/auth/register",
                        {"name": " Mei Chen ", "email": "Mei.Chen@ACME.inc", "password": "long-enough-pw"})
    assert status == 201
    assert body["user"]["email"] == "mei.chen@acme.inc"
    assert body["user"]["name"] == "Mei Chen"
    assert body["user"]["role"] == "employee"
    assert "password_hash" not in body["user"]
    assert body["token"]


@pytest.mark.parametrize("email", ["mei@gmail.com", "mei@acme.inc.evil.com", "mei@notacme.inc"])
def test_register_non_acme_email_is_400(auth, email):
    """Only company addresses can self-register."""
    status, body = post(auth, "/api/auth/register", {"name": "Mei", "email": email, "password": "long-enough-pw"})
    assert status == 400
    assert body["details"] == {"email": "Must be a valid @acme.inc email address"}


def test_register_cannot_choose_role(auth):
    """Sending "role": "admin" is rejected as an unknown field, not silently ignored."""
    status, body = post(auth, "/api/auth/register",
                        {"name": "Mei", "email": "mei@acme.inc", "password": "long-enough-pw", "role": "admin"})
    assert status == 400
    assert body["details"] == {"role": "Unknown field"}


def test_register_short_password_is_400(auth):
    """New passwords need 8+ characters."""
    status, body = post(auth, "/api/auth/register", {"name": "Mei", "email": "mei@acme.inc", "password": "short"})
    assert status == 400
    assert body["details"] == {"password": "Must be at least 8 characters"}


def test_register_duplicate_email_is_409(auth):
    """An email that is already registered (in any case) is a 409."""
    status, body = post(auth, "/api/auth/register",
                        {"name": "Dana", "email": "DANA@acme.inc", "password": "long-enough-pw"})
    assert status == 409
    assert body == {"error": "This email is already registered",
                    "details": {"email": "This email is already registered"}}


# ---------- login ----------

def test_login_success(auth):
    """Correct credentials return a token and the user without the password hash."""
    status, body = post(auth, "/api/auth/login", {"email": "Dana@Acme.Inc", "password": PASSWORD})
    assert status == 200
    assert body["user"]["id"] == 5
    assert "password_hash" not in body["user"]


def test_wrong_password_and_unknown_user_look_the_same(auth):
    """Both failures are 401 with the same message, so nobody can probe which emails exist."""
    wrong_password = post(auth, "/api/auth/login", {"email": "dana@acme.inc", "password": "wrong-password"})
    unknown_user = post(auth, "/api/auth/login", {"email": "nobody@acme.inc", "password": PASSWORD})
    assert wrong_password == unknown_user == (401, {"error": "Invalid email or password", "details": {}})


def test_login_missing_fields_is_400(auth):
    """Empty body lists both fields."""
    status, body = post(auth, "/api/auth/login", {})
    assert status == 400
    assert set(body["details"]) == {"email", "password"}


def test_login_wrong_method_is_404(auth):
    """GET /login is not a route."""
    response = auth.handler(make_event("GET", "/api/auth/login"))
    assert response["statusCode"] == 404


# ---------- me / refresh ----------

def test_me_without_token_is_401(auth):
    """/me needs a Bearer token."""
    response = auth.handler(make_event("GET", "/api/auth/me"))
    assert response["statusCode"] == 401


def test_me_with_token_returns_fresh_user(auth):
    """/me reads the user from the database, not only from the token."""
    token = token_for({"id": 5, "role": "employee", "name": "Old Name", "email": "dana@acme.inc"})
    response = auth.handler(make_event("GET", "/api/auth/me", token=token))
    assert response["statusCode"] == 200
    assert response_json(response)["user"]["name"] == "Dana Whitfield"


def test_me_for_deleted_user_is_401(auth):
    """A valid token for an account that no longer exists is 401."""
    token = token_for({"id": 999, "role": "employee", "name": "Gone", "email": "gone@acme.inc"})
    response = auth.handler(make_event("GET", "/api/auth/me", token=token))
    assert response["statusCode"] == 401
    assert response_json(response)["error"] == "User no longer exists"


def test_refresh_returns_new_token(auth):
    """A still-valid token can be exchanged for a new one."""
    token = token_for({"id": 5, "role": "employee", "name": "Dana", "email": "dana@acme.inc"})
    response = auth.handler(make_event("POST", "/api/auth/refresh", token=token))
    assert response["statusCode"] == 200
    assert response_json(response)["token"]


# ---------- health ----------

def test_health_ok_and_unavailable(auth):
    """/health is 200 when the database answers and 503 when it does not."""
    assert auth.handler(make_event("GET", "/api/auth/health"))["statusCode"] == 200
    auth.db_up = False
    response = auth.handler(make_event("GET", "/api/auth/health"))
    assert response["statusCode"] == 503
    assert response_json(response) == {"status": "unavailable"}
