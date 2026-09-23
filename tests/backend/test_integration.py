"""
Integration tests: the real handlers against a real PostgreSQL database.

Safety rules (the demo data must never be touched):
- Opt-in only: skipped unless RUN_INTEGRATION=1.
- Everything runs in a separate schema named "test", dropped and re-created
  at the start of the run and dropped again at the end. POSTGRES_SCHEMA=test
  makes backend/_shared/db.py run "SET search_path TO test" on connect, so the
  app's unqualified CREATE TABLE / INSERT / SELECT statements all land there.
- The seed password and JWT secret are test values set here; the real ones in
  backend/.env are never used (load_env_file never overrides a set variable).
- The public schema's row counts are recorded before and checked after.

Connection settings (POSTGRES_*) come from backend/.env, read the same way as
backend/dev_server.py does. No value from it is ever printed.
"""

import os
from typing import Iterator

import psycopg
import pytest
from psycopg import sql

from helpers import BACKEND_DIR, TEST_JWT_SECRET, make_event, response_json, token_for

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1 to run (needs PostgreSQL)"),
]

TEST_SCHEMA = "test"
TEST_SEED_PASSWORD = "integration-test-seed-pw"  # nosec B105 - only used for the throwaway test schema


def _admin_connection() -> psycopg.Connection:
    """A plain connection (default search_path) used only to manage the test schema and count public rows."""
    is_local = os.getenv("IS_LOCAL", "false") == "true"
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_NAME", "postgres"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASS", ""),
        sslmode=os.getenv("POSTGRES_SSLMODE", "disable" if is_local else "require"),
        connect_timeout=10,
        autocommit=True,
    )


def _public_counts(conn: psycopg.Connection) -> dict[str, int]:
    """Row counts of the demo tables in the public schema."""
    return {
        table: conn.execute(sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))).fetchone()[0]
        for table in ("users", "incidents")
    }


def _forget_app_connection() -> None:
    """Close and drop _shared.db's cached connection so the next call reconnects with the current env."""
    from _shared import db

    if db._connection is not None:  # pylint: disable=protected-access
        db._connection.close()  # pylint: disable=protected-access
    db._connection = None  # pylint: disable=protected-access


@pytest.fixture(scope="module")
def test_schema() -> Iterator[dict[str, int]]:
    """
    Point the app at a fresh "test" schema for this module, then clean up.

    Yields the public schema's row counts from before the run.
    """
    import dev_server  # backend/ is on sys.path (see conftest); importing it starts nothing.

    saved_env = dict(os.environ)
    # Set before loading .env: load_env_file uses setdefault, so these win over the real values.
    os.environ["POSTGRES_SCHEMA"] = TEST_SCHEMA
    os.environ["SEED_PASSWORD"] = TEST_SEED_PASSWORD
    os.environ["JWT_SECRET"] = TEST_JWT_SECRET
    dev_server.load_env_file(BACKEND_DIR / ".env")

    admin = _admin_connection()
    before = _public_counts(admin)
    admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(TEST_SCHEMA)))
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(TEST_SCHEMA)))
    _forget_app_connection()
    try:
        yield before
    finally:
        _forget_app_connection()
        admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(TEST_SCHEMA)))
        after = _public_counts(admin)
        admin.close()
        os.environ.clear()
        os.environ.update(saved_env)
        assert after == before, "public schema changed during the integration run"


@pytest.fixture
def handlers(test_schema, load_service) -> dict:
    """The real auth and incidents handlers (each loaded cleanly)."""
    auth = load_service("auth").function.handler
    incidents = load_service("incidents").function.handler
    return {"auth": auth, "incidents": incidents}


def call(handler, method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    """Call a handler and return (status, decoded body)."""
    response = handler(make_event(method, path, body, token))
    return response["statusCode"], response_json(response)


def login(handlers: dict, email: str, password: str) -> str:
    """Log in and return the token (fails the test if login fails)."""
    status, body = call(handlers["auth"], "POST", "/api/auth/login", {"email": email, "password": password})
    assert status == 200, body
    return body["token"]


def test_app_uses_test_schema_and_seeds_it(handlers):
    """The app's connection is on the test schema, which was seeded with the test password."""
    from _shared import db

    assert db.fetch_one("SELECT current_schema() AS schema")["schema"] == TEST_SCHEMA
    assert db.fetch_one("SELECT count(*) AS n FROM users")["n"] > 0
    assert login(handlers, "admin@acme.inc", TEST_SEED_PASSWORD)


def test_register_then_login(handlers):
    """Register -> login works; duplicate register -> 409; wrong password -> 401."""
    auth = handlers["auth"]
    new_user = {"name": "Integration Tester", "email": "integration.tester@acme.inc", "password": "a-long-password"}
    status, body = call(auth, "POST", "/api/auth/register", new_user)
    assert status == 201, body
    assert body["user"]["role"] == "employee"

    assert login(handlers, "INTEGRATION.TESTER@acme.inc", "a-long-password")
    assert call(auth, "POST", "/api/auth/register", new_user)[0] == 409
    status, body = call(auth, "POST", "/api/auth/login",
                        {"email": new_user["email"], "password": "not-the-password"})
    assert (status, body["error"]) == (401, "Invalid email or password")

    ghost = token_for({"id": 999999, "role": "employee", "name": "Ghost", "email": "ghost@acme.inc"})
    assert call(auth, "GET", "/api/auth/me", token=ghost)[0] == 401  # valid token, but no such user


def test_create_incident_then_change_status(handlers):
    """An employee reports an incident; an admin starts work; a stale version is rejected."""
    incidents = handlers["incidents"]
    status, body = call(handlers["auth"], "POST", "/api/auth/register",
                        {"name": "Reporter", "email": "reporter.int@acme.inc", "password": "a-long-password"})
    assert status == 201, body
    reporter_token, reporter_id = body["token"], body["user"]["id"]
    admin_token = login(handlers, "admin@acme.inc", TEST_SEED_PASSWORD)

    status, options = call(incidents, "GET", "/api/incidents/options", token=reporter_token)
    assert status == 200
    building = options["buildings"][0]
    floor = building["floors"][0]

    status, created = call(incidents, "POST", "/api/incidents", {
        "title": "Integration test printer", "description": "Paper jam on every job.",
        "category": "IT", "issue_type": "Printer", "building_id": building["id"], "floor_id": floor["id"],
    }, reporter_token)
    assert status == 201, created
    assert (created["status"], created["version"], created["reporter_id"]) == ("open", 1, reporter_id)
    path = f"/api/incidents/{created['id']}/status"

    # The reporter may not start work on it.
    assert call(incidents, "POST", path, {"version": 1, "status": "in_progress"}, reporter_token)[0] == 403

    status, updated = call(incidents, "POST", path, {"version": 1, "status": "in_progress"}, admin_token)
    assert status == 200, updated
    assert (updated["status"], updated["version"]) == ("in_progress", 2)
    assert [event["type"] for event in updated["events"]][:2] == ["created", "status_changed"]

    # Re-sending the old version is an optimistic-lock conflict.
    status, body = call(incidents, "POST", path, {"version": 1, "status": "blocked", "reason": "Waiting"}, admin_token)
    assert status == 409, body

    # The reporter sees the new status.
    status, seen = call(incidents, "GET", f"/api/incidents/{created['id']}", token=reporter_token)
    assert (status, seen["status"]) == (200, "in_progress")



def test_join_reopen_and_void_edge_cases(handlers):
    """
    DESIGN.md 13.4 against real rows: joining twice adds one engineer; a second
    reopen request while one is pending is 409; voiding hides the ticket.
    """
    incidents = handlers["incidents"]
    status, body = call(handlers["auth"], "POST", "/api/auth/register",
                        {"name": "Reporter Two", "email": "reporter2.int@acme.inc", "password": "a-long-password"})
    assert status == 201, body
    reporter_token = body["token"]
    engineer_token = login(handlers, "priya.nair@acme.inc", TEST_SEED_PASSWORD)
    admin_token = login(handlers, "admin@acme.inc", TEST_SEED_PASSWORD)

    _, options = call(incidents, "GET", "/api/incidents/options", token=reporter_token)
    building = options["buildings"][0]
    status, ticket = call(incidents, "POST", "/api/incidents", {
        "title": "Integration test Wi-Fi", "description": "Drops every minute.", "category": "IT",
        "issue_type": "Wi-Fi", "building_id": building["id"], "floor_id": building["floors"][0]["id"],
    }, reporter_token)
    assert status == 201, ticket
    base = f"/api/incidents/{ticket['id']}"

    # Join twice: both 200, one engineer row, as primary.
    for _ in range(2):
        status, ticket = call(incidents, "POST", f"{base}/join", token=engineer_token)
        assert status == 200, ticket
    assert [(e["name"], e["role"]) for e in ticket["engineers"]] == [("Priya Nair", "primary")]

    # Work the ticket to resolved (each step sends the version it just received).
    status, ticket = call(incidents, "POST", f"{base}/status",
                          {"version": ticket["version"], "status": "in_progress"}, engineer_token)
    assert status == 200, ticket
    status, ticket = call(incidents, "POST", f"{base}/status", {
        "version": ticket["version"], "status": "resolved", "resolution_note": "Replaced the access point",
    }, engineer_token)
    assert (status, ticket["status"]) == (200, "resolved"), ticket

    # One pending reopen request at a time (enforced by a unique index).
    status, _ = call(incidents, "POST", f"{base}/requests", {"reason": "Still dropping"}, reporter_token)
    assert status == 200
    status, body = call(incidents, "POST", f"{base}/requests", {"reason": "Really still dropping"}, reporter_token)
    assert (status, body["error"]) == (409, "A reopen request is already pending for this ticket")

    # Only an admin may void; afterwards the reporter can no longer see it.
    void_body = {"version": ticket["version"], "reason": "Duplicate report"}
    assert call(incidents, "DELETE", base, void_body, reporter_token)[0] == 403
    response = incidents(make_event("DELETE", base, void_body, admin_token))
    assert response["statusCode"] == 204
    assert call(incidents, "GET", base, token=reporter_token)[0] == 404


def test_public_schema_untouched(test_schema):
    """Nothing written by these tests reached the demo data."""
    admin = _admin_connection()
    try:
        assert _public_counts(admin) == test_schema
        assert admin.execute(
            "SELECT count(*) FROM public.incidents WHERE title LIKE 'Integration test %'"
        ).fetchone()[0] == 0
        assert admin.execute(
            "SELECT count(*) FROM public.users WHERE email IN (%s, %s, %s)",
            ("integration.tester@acme.inc", "reporter.int@acme.inc", "reporter2.int@acme.inc"),
        ).fetchone()[0] == 0
    finally:
        admin.close()
