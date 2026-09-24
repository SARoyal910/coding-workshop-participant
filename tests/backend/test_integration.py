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
    """The real service handlers (each loaded cleanly)."""
    return {name: load_service(name).function.handler
            for name in ("auth", "incidents", "dashboard", "facilities", "engineers")}


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

    # One pending reopen request at a time. The reporter is stopped by the
    # pending check; an admin gets past it and is stopped by the unique index.
    status, _ = call(incidents, "POST", f"{base}/requests", {"reason": "Still dropping"}, reporter_token)
    assert status == 200
    status, body = call(incidents, "POST", f"{base}/requests", {"reason": "Really still dropping"}, reporter_token)
    assert (status, body["error"]) == (409, "This ticket is waiting for an admin's approval")
    status, body = call(incidents, "POST", f"{base}/requests", {"reason": "Seen it too"}, admin_token)
    assert (status, body["error"]) == (409, "A reopen request is already pending for this ticket")

    # Only an admin may void; the ticket then moves to the archive, marked voided with the reason.
    void_body = {"version": ticket["version"], "reason": "Duplicate report"}
    assert call(incidents, "DELETE", base, void_body, reporter_token)[0] == 403
    response = incidents(make_event("DELETE", base, void_body, admin_token))
    assert response["statusCode"] == 204
    status, voided = call(incidents, "GET", base, token=reporter_token)
    assert (status, voided["is_voided"], voided["is_archived"], voided["void_reason"]) == (200, True, True, "Duplicate report")

    def listed(token: str, archived: bool) -> list[int]:
        query = {"archived": "true", "page_size": "100"} if archived else {"page_size": "100"}
        response = incidents(make_event("GET", "/api/incidents", token=token, query=query))
        return [item["id"] for item in response_json(response)["items"]]

    for token in (reporter_token, admin_token):  # the reporter and the admin both find it in the archive
        assert ticket["id"] in listed(token, archived=True)
        assert ticket["id"] not in listed(token, archived=False)


def test_facilities_constraints_and_delete_guard(handlers, load_service):
    """
    The real SQL: unique names become 409s, a place with an incident can't be
    deleted, and an empty building is deleted with its floors and seats.
    """
    facilities, incidents = handlers["facilities"], handlers["incidents"]
    admin_token = login(handlers, "admin@acme.inc", TEST_SEED_PASSWORD)
    reporter_token = login(handlers, "dana.whitfield@acme.inc", TEST_SEED_PASSWORD)

    status, building = call(facilities, "POST", "/api/facilities/buildings",
                            {"name": "Integration Annex", "address": "1 Test Way"}, admin_token)
    assert status == 201, building
    bid = building["id"]
    assert call(facilities, "POST", "/api/facilities/buildings",
                {"name": "Integration Annex", "address": "Again"}, admin_token)[0] == 409
    status, floor = call(facilities, "POST", f"/api/facilities/buildings/{bid}/floors", {"number": 1}, admin_token)
    assert status == 201, floor
    status, other_floor = call(facilities, "POST", f"/api/facilities/buildings/{bid}/floors", {"number": 2}, admin_token)
    assert status == 201, other_floor
    # Renumbering onto an existing floor hits the UNIQUE constraint -> 409, not 500.
    assert call(facilities, "PUT", f"/api/facilities/floors/{other_floor['id']}", {"number": 1}, admin_token)[0] == 409
    status, seat = call(facilities, "POST", f"/api/facilities/floors/{floor['id']}/seats", {"code": "IA-1-001"}, admin_token)
    assert status == 201, seat

    status, ticket = call(incidents, "POST", "/api/incidents", {
        "title": "Integration test annex light", "description": "Flickering.", "category": "facilities",
        "issue_type": "Lighting", "building_id": bid, "floor_id": floor["id"], "seat_id": seat["id"],
    }, reporter_token)
    assert status == 201, ticket

    for path in (f"/api/facilities/seats/{seat['id']}", f"/api/facilities/floors/{floor['id']}",
                 f"/api/facilities/buildings/{bid}"):
        status, body = call(facilities, "DELETE", path, token=admin_token)
        assert status == 409, (path, body)
        assert "1 incident" in body["error"]

    # The repository's foreign-key guard: even without the service's pre-check, the delete is refused and rolled back.
    assert load_service("facilities").repository.delete_building(bid) is False
    status, listing = call(facilities, "GET", "/api/facilities/buildings", token=admin_token)
    annex = next(item for item in listing["items"] if item["id"] == bid)
    assert [f["number"] for f in annex["floors"]] == [1, 2]

    # An empty building goes with its floors and seats.
    _, empty = call(facilities, "POST", "/api/facilities/buildings", {"name": "Integration Temp", "address": "x"}, admin_token)
    _, empty_floor = call(facilities, "POST", f"/api/facilities/buildings/{empty['id']}/floors", {"number": 5}, admin_token)
    call(facilities, "POST", f"/api/facilities/floors/{empty_floor['id']}/seats", {"code": "T-1"}, admin_token)
    assert call(facilities, "DELETE", f"/api/facilities/buildings/{empty['id']}", token=admin_token)[0] == 204
    assert call(facilities, "PUT", f"/api/facilities/floors/{empty_floor['id']}", {"number": 6}, admin_token)[0] == 404


def test_engineer_accounts_and_availability(handlers):
    """An admin creates an engineer who can log in; availability flags reassignment."""
    engineers = handlers["engineers"]
    admin_token = login(handlers, "admin@acme.inc", TEST_SEED_PASSWORD)
    new = {"name": "Integration Engineer", "email": "integration.engineer@acme.inc", "password": "a-long-password",
           "specialty": "AV", "shift": "night", "phone": "+1 555 010 9999"}

    status, engineer = call(engineers, "POST", "/api/engineers", new, admin_token)
    assert status == 201, engineer
    assert (engineer["shift"], engineer["active_primary"], engineer["is_available"]) == ("night", 0, True)
    assert call(engineers, "POST", "/api/engineers", new, admin_token)[0] == 409
    engineer_token = login(handlers, new["email"], new["password"])

    status, listing = call(engineers, "GET", "/api/engineers", token=engineer_token)
    assert status == 200
    assert listing["total"] == len(listing["items"]) == 6  # 5 seeded + this one
    busiest = listing["items"][0]  # sorted by active primary tickets

    # An engineer can only change their own availability; an admin can change anyone's.
    path = f"/api/engineers/{busiest['id']}/availability"
    assert call(engineers, "PUT", path, {"is_available": False}, engineer_token)[0] == 403
    status, updated = call(engineers, "PUT", path, {"is_available": False}, admin_token)
    assert status == 200, updated
    assert updated["needs_reassignment"] is (busiest["active_primary"] > 0)
    call(engineers, "PUT", path, {"is_available": True}, admin_token)

    status, edited = call(engineers, "PUT", f"/api/engineers/{engineer['id']}",
                          {"name": "Integration Engineer", "specialty": "IT", "shift": "day", "phone": None}, admin_token)
    assert (status, edited["specialty"], edited["phone"]) == (200, "IT", None)


def test_recurring_detection_and_missed_shifts(handlers):
    """
    DESIGN.md section 10 against real rows, on a fresh building so seeded data can't interfere:
    - recurring: 2 reports at a seat is not a pattern, the 3rd is (and badges all three); voided ones don't count
    - the report form's similar check sees the open duplicates
    - missed shift commitment: the acked shift ended and the ticket was neither resolved nor blocked in time
    """
    from _shared import db

    facilities, incidents, engineers = handlers["facilities"], handlers["incidents"], handlers["engineers"]
    admin_token = login(handlers, "admin@acme.inc", TEST_SEED_PASSWORD)
    reporter_token = login(handlers, "dana.whitfield@acme.inc", TEST_SEED_PASSWORD)

    _, building = call(facilities, "POST", "/api/facilities/buildings", {"name": "Integration Recurring", "address": "x"}, admin_token)
    _, floor = call(facilities, "POST", f"/api/facilities/buildings/{building['id']}/floors", {"number": 1}, admin_token)
    _, seat = call(facilities, "POST", f"/api/facilities/floors/{floor['id']}/seats", {"code": "IR-1-001"}, admin_token)

    def report(title):
        status, ticket = call(incidents, "POST", "/api/incidents", {
            "title": f"Integration test {title}", "description": "Flickers.", "category": "IT", "issue_type": "Monitor",
            "building_id": building["id"], "floor_id": floor["id"], "seat_id": seat["id"],
        }, reporter_token)
        assert status == 201, ticket
        return ticket["id"]

    def level(incident_id):
        return (call(incidents, "GET", f"/api/incidents/{incident_id}", token=admin_token)[1]["recurring"] or {}).get("level")

    first, second = report("monitor 1"), report("monitor 2")
    assert level(first) is None and level(second) is None  # 2 is below the threshold
    third = report("monitor 3")
    assert [level(i) for i in (first, second, third)] == ["seat", "seat", "seat"]
    detail = call(incidents, "GET", f"/api/incidents/{first}", token=admin_token)[1]["recurring"]
    assert (detail["count"], sorted(r["id"] for r in detail["related"])) == (3, sorted([second, third]))

    query = {"issue_type": "Monitor", "floor_id": str(floor["id"]), "seat_id": str(seat["id"])}
    response = incidents(make_event("GET", "/api/incidents/similar", token=reporter_token, query=query))
    similar = response_json(response)
    assert (similar["open_count"], similar["recurring"]["level"]) == (3, "seat")

    # Voiding one drops the pattern below the threshold again.
    version = call(incidents, "GET", f"/api/incidents/{third}", token=admin_token)[1]["version"]
    assert incidents(make_event("DELETE", f"/api/incidents/{third}", {"version": version, "reason": "Duplicate"},
                                admin_token))["statusCode"] == 204
    assert level(first) is None

    # Missed shift commitments, for a brand-new engineer (so seeded acks can't interfere).
    _, engineer = call(engineers, "POST", "/api/engineers", {
        "name": "Integration Shift", "email": "integration.shift@acme.inc", "password": "a-long-password",
        "specialty": "IT", "shift": "day"}, admin_token)
    four = report("monitor 4")

    def ack(incident_id, hours_ago_start, hours_ago_end):
        db.execute(
            "INSERT INTO incident_acks (incident_id, engineer_id, acknowledged_at, shift_ends_at)"
            " VALUES (%s, %s, now() - make_interval(hours => %s), now() - make_interval(hours => %s))",
            (incident_id, engineer["id"], hours_ago_start, hours_ago_end),
        )

    ack(first, 10, 2)    # shift over, still open -> missed
    ack(second, 10, 2)   # shift over, but blocked during the shift -> not missed
    db.execute("INSERT INTO incident_events (incident_id, actor_id, type, from_value, to_value, created_at)"
               " VALUES (%s, %s, 'status_changed', 'open', 'blocked', now() - interval '5 hours')",
               (second, engineer["id"]))
    ack(four, 10, 2)     # resolved before the shift ended -> not missed
    db.execute("UPDATE incidents SET resolved_at = now() - interval '3 hours' WHERE id = %s", (four,))
    ack(four, 1, -5)     # shift still running -> not missed (yet)

    listing = call(engineers, "GET", "/api/engineers", token=admin_token)[1]
    row = next(item for item in listing["items"] if item["id"] == engineer["id"])
    assert row["missed_shifts"] == 1


def test_two_engineers_taking_a_ticket_at_once_get_one_primary(handlers, load_service):
    """
    The join race: engineer A's "take" is still uncommitted when engineer B takes
    the same ticket. B's insert waits on the one-primary-per-ticket index, finds A
    won, and B is added as a helper instead. There is never a second primary.
    """
    import threading
    import time

    from _shared import db

    incidents = handlers["incidents"]
    reporter_token = login(handlers, "dana.whitfield@acme.inc", TEST_SEED_PASSWORD)
    _, options = call(incidents, "GET", "/api/incidents/options", token=reporter_token)
    building = options["buildings"][0]
    status, ticket = call(incidents, "POST", "/api/incidents", {
        "title": "Integration test join race", "description": "Two engineers at once.", "category": "IT",
        "issue_type": "Printer", "building_id": building["id"], "floor_id": building["floors"][0]["id"],
    }, reporter_token)
    assert status == 201, ticket
    ids = {row["email"]: row["id"] for row in db.fetch_all(
        "SELECT id, email FROM users WHERE email IN ('priya.nair@acme.inc', 'tom.becker@acme.inc')")}
    engineer_a, engineer_b = ids["priya.nair@acme.inc"], ids["tom.becker@acme.inc"]
    repository = load_service("incidents").repository

    other = _admin_connection()  # a second, independent connection plays engineer A
    other.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(TEST_SCHEMA)))
    result = {}
    try:
        with other.transaction():
            other.execute("INSERT INTO incident_engineers (incident_id, engineer_id, role, added_by)"
                          " VALUES (%s, %s, 'primary', %s)", (ticket["id"], engineer_a, engineer_a))
            # B joins now, through the app's own connection; it blocks until A commits.
            worker = threading.Thread(target=lambda: result.update(role=repository.add_engineer(ticket["id"], engineer_b)))
            worker.start()
            time.sleep(1.5)
            assert worker.is_alive(), "B should be waiting on A's uncommitted primary row"
        worker.join(timeout=15)
    finally:
        other.close()

    assert result["role"] == "helper"
    roles = db.fetch_all("SELECT engineer_id, role FROM incident_engineers WHERE incident_id = %s ORDER BY role DESC",
                         (ticket["id"],))
    assert roles == [{"engineer_id": engineer_a, "role": "primary"}, {"engineer_id": engineer_b, "role": "helper"}]

    # Joining again is still a no-op, and the database itself refuses a second primary.
    assert repository.add_engineer(ticket["id"], engineer_b) is None
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute("INSERT INTO incident_engineers (incident_id, engineer_id, role, added_by)"
                   " VALUES (%s, 1, 'primary', 1)", (ticket["id"],))


def test_dashboards_match_the_rows_they_summarize(handlers):
    """
    Every dashboard query runs against the seeded rows, and the headline
    numbers agree with direct counts of the same tables.
    """
    from _shared import db

    dashboard = handlers["dashboard"]
    active = "FROM incidents WHERE NOT is_voided AND NOT is_archived"

    status, admin = call(dashboard, "GET", "/api/dashboard", token=login(handlers, "admin@acme.inc", TEST_SEED_PASSWORD))
    assert status == 200, admin
    assert sum(admin["status_counts"].values()) == db.fetch_one(f"SELECT count(*) AS n {active}")["n"]  # nosec B608
    assert sum(row["engineers"] for row in admin["shift_coverage"]) == len(admin["engineers"])
    assert sum(row["count"] for row in admin["categories"]) == sum(row["count"] for row in admin["issue_types"])
    for pct in (admin["communication"]["resolved_with_note_pct"], admin["communication"]["reopen_rate_pct"]):
        assert pct is None or 0 <= pct <= 100

    employee = db.fetch_one("SELECT id FROM users WHERE email = 'dana.whitfield@acme.inc'")["id"]
    status, mine = call(dashboard, "GET", "/api/dashboard", token=login(handlers, "dana.whitfield@acme.inc", TEST_SEED_PASSWORD))
    assert status == 200, mine
    assert sum(mine["status_counts"].values()) == db.fetch_one(
        f"SELECT count(*) AS n {active} AND reporter_id = %s", (employee,))["n"]  # nosec B608

    engineer = db.fetch_one("SELECT u.id, u.email FROM users u JOIN engineer_profiles p ON p.user_id = u.id"
                            " ORDER BY u.id LIMIT 1")
    status, own = call(dashboard, "GET", "/api/dashboard", token=login(handlers, engineer["email"], TEST_SEED_PASSWORD))
    assert status == 200, own
    assert own["me"]["id"] == engineer["id"]
    assert own["unassigned_pool"] == db.fetch_one(
        f"SELECT count(*) AS n {active} AND id NOT IN (SELECT incident_id FROM incident_engineers)")["n"]  # nosec B608


def test_report_covering_several_seats(handlers):
    """One report for a row of desks: all seats are returned on the ticket and counted in the list."""
    incidents = handlers["incidents"]
    token = login(handlers, "dana.whitfield@acme.inc", TEST_SEED_PASSWORD)
    _, options = call(incidents, "GET", "/api/incidents/options", token=token)
    floor = next(f for b in options["buildings"] for f in b["floors"] if len(f["seats"]) >= 3)
    building = next(b for b in options["buildings"] if floor in b["floors"])
    seat_ids = [seat["id"] for seat in floor["seats"][:3]]
    status, ticket = call(incidents, "POST", "/api/incidents", {
        "title": "Integration test monitors", "description": "Whole row flickers.", "category": "IT",
        "issue_type": "Monitor", "building_id": building["id"], "floor_id": floor["id"], "seat_ids": seat_ids,
    }, token)
    assert status == 201, ticket
    assert ticket["seat_id"] == seat_ids[0]
    assert sorted(seat["id"] for seat in ticket["seats"]) == sorted(seat_ids)
    response = incidents(make_event("GET", "/api/incidents", token=token, query={"q": "Integration test monitors"}))
    assert response["statusCode"] == 200
    page = response_json(response)
    assert [item["seat_count"] for item in page["items"]] == [3]


def test_admin_reassigns_the_primary_engineer(handlers):
    """The old primary comes off the ticket, a helper can be promoted, and the change is logged."""
    incidents = handlers["incidents"]
    reporter_token = login(handlers, "dana.whitfield@acme.inc", TEST_SEED_PASSWORD)
    priya_token = login(handlers, "priya.nair@acme.inc", TEST_SEED_PASSWORD)
    jordan_token = login(handlers, "jordan.lee@acme.inc", TEST_SEED_PASSWORD)
    admin_token = login(handlers, "admin@acme.inc", TEST_SEED_PASSWORD)
    _, options = call(incidents, "GET", "/api/incidents/options", token=reporter_token)
    building = options["buildings"][0]
    status, ticket = call(incidents, "POST", "/api/incidents", {
        "title": "Integration test reassign", "description": "Dock is dead.", "category": "IT",
        "issue_type": "Docking station", "building_id": building["id"], "floor_id": building["floors"][0]["id"],
    }, reporter_token)
    assert status == 201, ticket
    base = f"/api/incidents/{ticket['id']}"
    call(incidents, "POST", f"{base}/join", token=priya_token)   # primary
    _, ticket = call(incidents, "POST", f"{base}/join", token=jordan_token)  # helper
    jordan_id = next(e["id"] for e in ticket["engineers"] if e["name"] == "Jordan Lee")

    status, ticket = call(incidents, "POST", f"{base}/assign", {"engineer_id": jordan_id}, admin_token)
    assert status == 200, ticket
    assert [(e["name"], e["role"]) for e in ticket["engineers"]] == [("Jordan Lee", "primary")]
    event = next(e for e in ticket["events"] if e["type"] == "engineer_reassigned")
    assert (event["from_value"], event["to_value"]) == ("Priya Nair", "Jordan Lee")


def test_critical_incident_is_a_site_alert(handlers):
    """
    Only an admin may report critical; while it is active every role sees it
    in GET /alerts and can open it read-only; once resolved it is private again.
    """
    incidents = handlers["incidents"]
    admin_token = login(handlers, "admin@acme.inc", TEST_SEED_PASSWORD)
    employee_token = login(handlers, "luis.romero@acme.inc", TEST_SEED_PASSWORD)
    engineer_token = login(handlers, "tom.becker@acme.inc", TEST_SEED_PASSWORD)
    _, options = call(incidents, "GET", "/api/incidents/options", token=employee_token)
    assert "critical" not in options["priorities"]
    building = options["buildings"][0]
    report = {
        "title": "Integration test door access", "description": "Badge readers are down.", "category": "security",
        "issue_type": "Door access", "priority": "critical",
        "building_id": building["id"], "floor_id": building["floors"][0]["id"],
    }
    assert call(incidents, "POST", "/api/incidents", report, employee_token)[0] == 400
    status, ticket = call(incidents, "POST", "/api/incidents", report, admin_token)
    assert status == 201, ticket
    base = f"/api/incidents/{ticket['id']}"

    for token in (employee_token, engineer_token):
        status, alerts = call(incidents, "GET", "/api/incidents/alerts", token=token)
        assert status == 200
        assert ticket["id"] in [alert["id"] for alert in alerts["items"]]
    status, seen = call(incidents, "GET", base, token=employee_token)
    assert status == 200
    assert seen["status_since"] and seen["allowed_actions"]["can_add_note"] is False

    call(incidents, "POST", f"{base}/join", token=engineer_token)
    status, ticket = call(incidents, "POST", f"{base}/status",
                          {"version": seen["version"], "status": "in_progress"}, engineer_token)
    assert status == 200, ticket
    status, ticket = call(incidents, "POST", f"{base}/status", {
        "version": ticket["version"], "status": "resolved", "resolution_note": "Restarted the badge controller",
    }, engineer_token)
    assert status == 200, ticket
    _, alerts = call(incidents, "GET", "/api/incidents/alerts", token=employee_token)
    assert ticket["id"] not in [alert["id"] for alert in alerts["items"]]
    assert call(incidents, "GET", base, token=employee_token)[0] == 404


def test_public_schema_untouched(test_schema):
    """Nothing written by these tests reached the demo data."""
    admin = _admin_connection()
    try:
        assert _public_counts(admin) == test_schema
        assert admin.execute(
            "SELECT count(*) FROM public.incidents WHERE title LIKE 'Integration test %'"
        ).fetchone()[0] == 0
        assert admin.execute(
            "SELECT count(*) FROM public.buildings WHERE name LIKE 'Integration %'"
        ).fetchone()[0] == 0
        assert admin.execute(
            "SELECT count(*) FROM public.users WHERE email IN (%s, %s, %s, %s, %s)",
            ("integration.tester@acme.inc", "reporter.int@acme.inc", "reporter2.int@acme.inc",
             "integration.engineer@acme.inc", "integration.shift@acme.inc"),
        ).fetchone()[0] == 0
    finally:
        admin.close()
