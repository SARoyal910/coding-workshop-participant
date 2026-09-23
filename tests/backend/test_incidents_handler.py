"""
Error-path tests for the incidents service, through the real Lambda handler.

Each test calls function.handler(event) exactly like Lambda would, so routing,
token checks, validation, permissions and error mapping are all exercised.
Only the repository (SQL) functions are replaced with small fakes, so no
database is needed. monkeypatch.setattr fails if a patched function no longer
exists, which catches drift between these tests and repository.py.
"""

import contextlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from helpers import make_event, response_json, token_for

ADMIN = {"id": 1, "role": "admin", "name": "Alex Morgan", "email": "admin@acme.inc"}
REPORTER = {"id": 10, "role": "employee", "name": "Dana Whitfield", "email": "dana.whitfield@acme.inc"}
OTHER_EMPLOYEE = {"id": 11, "role": "employee", "name": "Luis Romero", "email": "luis.romero@acme.inc"}
ASSIGNED_ENGINEER = {"id": 20, "role": "engineer", "name": "Priya Nair", "email": "priya.nair@acme.inc"}
UNASSIGNED_ENGINEER = {"id": 21, "role": "engineer", "name": "Tom Becker", "email": "tom.becker@acme.inc"}

INCIDENT_ID = 42
STATUS_PATH = f"/api/incidents/{INCIDENT_ID}/status"


def incident_row(**overrides) -> dict:
    """An incident as repository.get_incident returns it (only the columns the service reads)."""
    row = {
        "id": INCIDENT_ID, "title": "Wi-Fi keeps dropping", "description": "Every few minutes.",
        "status": "open", "priority": "medium", "reporter_id": REPORTER["id"],
        "is_archived": False, "is_voided": False, "version": 3,
        "created_at": datetime(2025, 12, 1, 9, 0, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


@pytest.fixture
def incidents(load_service, monkeypatch):
    """
    The incidents service with a fake repository.

    Returns a namespace where tests set `.incident` (the row, or None for "not
    found") and `.engineers` (ids on the ticket), and read `.writes` to check
    that nothing was saved.
    """
    svc = load_service("incidents")
    state = SimpleNamespace(
        handler=svc.function.handler, incident=incident_row(), engineers=[ASSIGNED_ENGINEER["id"]],
        update_succeeds=True, request_is_new=True, writes=[], repository=svc.repository,
    )

    def update_status(incident_id, version, status, blocked_reason):
        """Pretend the UPDATE ... WHERE version = %s matched (or not, for a stale version)."""
        state.writes.append(("update_status", status))
        return state.update_succeeds

    repo = svc.repository
    monkeypatch.setattr(repo, "get_incident", lambda incident_id: state.incident)
    monkeypatch.setattr(repo, "get_engineers", lambda incident_id: [{"id": i} for i in state.engineers])
    monkeypatch.setattr(repo, "transaction", contextlib.nullcontext)
    monkeypatch.setattr(repo, "update_status", update_status)
    monkeypatch.setattr(repo, "update_details", lambda *args: state.writes.append("update_details") or False)
    monkeypatch.setattr(repo, "add_event", lambda *args, **kwargs: state.writes.append("add_event"))
    monkeypatch.setattr(repo, "floor_in_building", lambda floor_id, building_id: False)
    monkeypatch.setattr(repo, "recurring_counts", lambda ids, days: {})  # no recurring pattern

    def add_engineer(incident_id, engineer_id):
        """Like the real INSERT: primary if nobody is on it yet, else helper; None if already on it."""
        if engineer_id in state.engineers:
            return None
        role = "helper" if state.engineers else "primary"
        state.writes.append(("add_engineer", engineer_id, role))
        state.engineers.append(engineer_id)
        return role

    def create_request(incident_id, request_type, reason, requested_by):
        """The unique index allows one pending request per type; request_is_new=False simulates a duplicate."""
        state.writes.append(("create_request", request_type))
        return state.request_is_new

    monkeypatch.setattr(repo, "add_engineer", add_engineer)
    monkeypatch.setattr(repo, "mark_assigned", lambda incident_id: state.writes.append("mark_assigned"))
    monkeypatch.setattr(repo, "create_request", create_request)
    monkeypatch.setattr(repo, "void", lambda *args: state.writes.append("void") or state.update_succeeds)
    monkeypatch.setattr(repo, "add_work_log", lambda *args: state.writes.append("add_work_log"))
    # Read-only lookups used when a successful response renders the full ticket.
    for name in ("get_notes", "get_events", "get_requests", "get_work_logs", "get_acks"):
        monkeypatch.setattr(repo, name, lambda incident_id: [])
    return state


def call(state, method: str, path: str, user: dict | None, body: dict | str | None = None,
         query: dict | None = None) -> tuple[int, dict]:
    """Call the handler as `user` (None = no token) and return (status, decoded body)."""
    token = token_for(user) if user else None
    response = state.handler(make_event(method, path, body, token, query))
    return response["statusCode"], response_json(response)


# ---------- 401: authentication ----------

def test_no_token_is_401(incidents):
    """Every incidents route needs a token."""
    status, body = call(incidents, "GET", f"/api/incidents/{INCIDENT_ID}", None)
    assert status == 401
    assert body == {"error": "Missing or malformed Authorization header", "details": {}}


def test_garbage_token_is_401(incidents):
    """A token that is not a valid JWT is rejected."""
    event = make_event("GET", "/api/incidents", token="not-a-jwt")
    response = incidents.handler(event)
    assert response["statusCode"] == 401
    assert response_json(response)["error"] == "Invalid token"


# ---------- 404: not found / not visible ----------

def test_unknown_route_is_404(incidents):
    """Paths that match no route are 404."""
    status, _ = call(incidents, "GET", "/api/incidents/42/nonsense", REPORTER)
    assert status == 404


def test_missing_incident_is_404(incidents):
    """An id that does not exist is 404."""
    incidents.incident = None
    status, body = call(incidents, "POST", STATUS_PATH, ADMIN, {"version": 3, "status": "in_progress"})
    assert (status, body["error"]) == (404, "Incident not found")


def test_other_employees_ticket_is_404_not_403(incidents):
    """Employees get 404 for tickets they did not report, so ids of other people's tickets are not revealed."""
    status, body = call(incidents, "POST", STATUS_PATH, OTHER_EMPLOYEE, {"version": 3, "status": "in_progress"})
    assert (status, body["error"]) == (404, "Incident not found")
    assert incidents.writes == []


def test_engineer_sees_other_engineers_ticket_but_cannot_change_it(incidents):
    """Engineers see every active ticket read-only; changing one they are not on is 403."""
    status, body = call(incidents, "POST", STATUS_PATH, UNASSIGNED_ENGINEER, {"version": 3, "status": "in_progress"})
    assert (status, body["error"]) == (403, "You don't have permission to make this change")
    assert incidents.writes == []


def test_engineer_cannot_see_archived_ticket_they_were_not_on(incidents):
    """Archived tickets are visible to engineers only if they worked on them."""
    incidents.incident = incident_row(is_archived=True, status="closed")
    status, _ = call(incidents, "POST", STATUS_PATH, UNASSIGNED_ENGINEER, {"version": 3, "status": "in_progress"})
    assert status == 404


def test_engineer_not_on_ticket_must_join_before_adding_notes(incidents):
    """Seeing a ticket is not enough to add notes to it."""
    status, body = call(incidents, "POST", f"/api/incidents/{INCIDENT_ID}/notes", UNASSIGNED_ENGINEER,
                        {"body": "Have you tried turning it off and on?"})
    assert (status, body["error"]) == (403, "Join this ticket before adding notes")


def test_engineer_not_on_ticket_cannot_acknowledge(incidents):
    """Acknowledging is a shift commitment, so only engineers on the ticket may do it."""
    status, body = call(incidents, "POST", f"/api/incidents/{INCIDENT_ID}/acknowledge", UNASSIGNED_ENGINEER)
    assert (status, body["error"]) == (403, "Join the ticket before acknowledging it")


def test_scope_all_is_accepted_for_engineers(incidents, monkeypatch):
    """?scope=all is a valid engineer filter (the repository call is faked)."""
    monkeypatch.setattr(incidents.repository, "list_incidents", lambda user, filters, page, size: ([], 0))
    status, body = call(incidents, "GET", "/api/incidents", UNASSIGNED_ENGINEER, query={"scope": "all"})
    assert (status, body["total"]) == (200, 0)


def test_voided_ticket_is_hidden_from_non_admins(incidents):
    """Even the reporter gets 404 for a voided ticket."""
    incidents.incident = incident_row(is_voided=True)
    status, _ = call(incidents, "POST", STATUS_PATH, REPORTER, {"version": 3, "status": "closed"})
    assert status == 404


def test_voided_ticket_is_visible_but_read_only_for_admins(incidents):
    """Admins can still find a voided ticket, but it cannot be changed (409)."""
    incidents.incident = incident_row(is_voided=True)
    status, body = call(incidents, "POST", STATUS_PATH, ADMIN, {"version": 3, "status": "in_progress"})
    assert (status, body["error"]) == (409, "This ticket was voided and can no longer be changed")


# ---------- 403: permissions ----------

def test_reporter_cannot_change_status(incidents):
    """An employee (even the reporter) cannot start work on a ticket."""
    status, body = call(incidents, "POST", STATUS_PATH, REPORTER, {"version": 3, "status": "in_progress"})
    assert (status, body["error"]) == (403, "You don't have permission to make this change")
    assert incidents.writes == []


def test_pool_engineer_must_join_before_changing_status(incidents):
    """An engineer can see an unassigned ticket, but must join it before working it."""
    incidents.engineers = []
    status, _ = call(incidents, "POST", STATUS_PATH, UNASSIGNED_ENGINEER, {"version": 3, "status": "in_progress"})
    assert status == 403


def test_engineer_cannot_edit_title(incidents):
    """Only the reporter or an admin may edit the title and description."""
    status, body = call(incidents, "PUT", f"/api/incidents/{INCIDENT_ID}", ASSIGNED_ENGINEER,
                        {"version": 3, "title": "New title"})
    assert (status, body["error"]) == (403, "Only the reporter or an admin can edit this ticket")


def test_scope_filter_is_for_engineers_only(incidents):
    """?scope=mine|pool only makes sense for engineers."""
    status, body = call(incidents, "GET", "/api/incidents", REPORTER, query={"scope": "pool"})
    assert status == 400
    assert body["details"] == {"scope": "Only engineers can filter by scope"}


# ---------- 400: validation ----------

def test_block_without_reason_is_400(incidents):
    """Blocking requires a reason."""
    status, body = call(incidents, "POST", STATUS_PATH, ASSIGNED_ENGINEER, {"version": 3, "status": "blocked"})
    assert status == 400
    assert body["details"] == {"reason": "A reason is required to block a ticket"}
    assert incidents.writes == []


def test_block_with_blank_reason_is_400(incidents):
    """A reason of only spaces counts as no reason."""
    status, body = call(incidents, "POST", STATUS_PATH, ASSIGNED_ENGINEER,
                        {"version": 3, "status": "blocked", "reason": "   "})
    assert status == 400
    assert "reason" in body["details"]


def test_resolve_without_note_is_400(incidents):
    """Resolving requires a resolution note."""
    incidents.incident = incident_row(status="in_progress")
    status, body = call(incidents, "POST", STATUS_PATH, ASSIGNED_ENGINEER, {"version": 3, "status": "resolved"})
    assert status == 400
    assert body["details"] == {"resolution_note": "Describe how the issue was resolved"}


def test_unknown_field_is_400(incidents):
    """Fields the endpoint does not accept are rejected, e.g. trying to set reporter_id."""
    status, body = call(incidents, "POST", STATUS_PATH, ASSIGNED_ENGINEER,
                        {"version": 3, "status": "in_progress", "reporter_id": 1})
    assert status == 400
    assert body["details"] == {"reporter_id": "Unknown field"}


def test_missing_version_and_bad_status_are_reported_together(incidents):
    """All field errors come back at once."""
    status, body = call(incidents, "POST", STATUS_PATH, ASSIGNED_ENGINEER, {"status": "done"})
    assert status == 400
    assert set(body["details"]) == {"version", "status"}


def test_invalid_json_is_400(incidents):
    """A body that is not JSON is 400, not 500."""
    status, body = call(incidents, "POST", STATUS_PATH, ASSIGNED_ENGINEER, "{oops")
    assert (status, body["error"]) == (400, "Request body must be valid JSON")


def test_create_incident_missing_fields_is_400(incidents):
    """Every required field is listed in details."""
    status, body = call(incidents, "POST", "/api/incidents", REPORTER, {})
    assert status == 400
    assert {"title", "description", "category", "issue_type", "building_id", "floor_id"} <= set(body["details"])


def test_create_incident_issue_type_must_match_category(incidents):
    """An IT issue type cannot be filed under facilities."""
    status, body = call(incidents, "POST", "/api/incidents", REPORTER, {
        "title": "t", "description": "d", "category": "facilities", "issue_type": "Wi-Fi",
        "building_id": 1, "floor_id": 1,
    })
    assert status == 400
    assert "issue_type" in body["details"]


def test_create_incident_floor_must_be_in_building(incidents):
    """Referenced ids must fit together (the fake repository says the floor is elsewhere)."""
    status, body = call(incidents, "POST", "/api/incidents", REPORTER, {
        "title": "t", "description": "d", "category": "IT", "issue_type": "Wi-Fi",
        "building_id": 1, "floor_id": 99,
    })
    assert status == 400
    assert body["details"] == {"floor_id": "Floor not found in this building"}


def test_page_size_over_limit_is_400(incidents):
    """Lists are capped at 100 per page."""
    status, body = call(incidents, "GET", "/api/incidents", REPORTER, query={"page_size": "500"})
    assert status == 400
    assert "page_size" in body["details"]


# ---------- 409: conflicts ----------

def test_invalid_transition_is_409(incidents):
    """open -> resolved skips the workflow."""
    status, body = call(incidents, "POST", STATUS_PATH, ASSIGNED_ENGINEER,
                        {"version": 3, "status": "resolved", "resolution_note": "fixed"})
    assert (status, body["error"]) == (409, "A ticket can't move from open to resolved")
    assert incidents.writes == []


def test_stale_version_is_409(incidents):
    """Optimistic locking: if the UPDATE matched no row (version changed), the client is told to refresh."""
    incidents.update_succeeds = False
    status, body = call(incidents, "POST", STATUS_PATH, ASSIGNED_ENGINEER, {"version": 2, "status": "in_progress"})
    assert status == 409
    assert body["error"] == "This ticket was updated by someone else. Refresh to see the latest."
    # The UPDATE was attempted, but no audit event was written after it failed.
    assert incidents.writes == [("update_status", "in_progress")]


def test_stale_version_on_edit_is_409(incidents):
    """Editing the title with an old version is also a 409."""
    status, body = call(incidents, "PUT", f"/api/incidents/{INCIDENT_ID}", REPORTER,
                        {"version": 1, "title": "A different title"})
    assert status == 409
    assert body["error"].startswith("This ticket was updated by someone else")


def test_archived_ticket_is_read_only(incidents):
    """Archived tickets cannot be changed, even by an admin."""
    incidents.incident = incident_row(is_archived=True, status="closed")
    status, body = call(incidents, "POST", STATUS_PATH, ADMIN, {"version": 3, "status": "in_progress"})
    assert (status, body["error"]) == (409, "This ticket is archived and can no longer be changed")


# ---------- join, reopen requests, void, work logs (DESIGN.md 13.4) ----------

JOIN_PATH = f"/api/incidents/{INCIDENT_ID}/join"


def test_join_twice_is_200_without_a_duplicate(incidents):
    """The first join adds a primary engineer; joining again changes nothing."""
    incidents.engineers = []
    first_status, first = call(incidents, "POST", JOIN_PATH, UNASSIGNED_ENGINEER)
    second_status, second = call(incidents, "POST", JOIN_PATH, UNASSIGNED_ENGINEER)

    assert (first_status, second_status) == (200, 200)
    assert incidents.engineers == [UNASSIGNED_ENGINEER["id"]]  # one row, not two
    assert incidents.writes.count(("add_engineer", UNASSIGNED_ENGINEER["id"], "primary")) == 1
    assert first["allowed_actions"]["can_join"] is False
    assert second["allowed_actions"]["can_join"] is False


def test_second_engineer_joins_as_helper(incidents):
    """Later engineers are helpers, and the ticket is not re-assigned."""
    status, _ = call(incidents, "POST", JOIN_PATH, UNASSIGNED_ENGINEER)
    assert status == 200
    assert ("add_engineer", UNASSIGNED_ENGINEER["id"], "helper") in incidents.writes
    assert "mark_assigned" not in incidents.writes


def test_employee_cannot_join(incidents):
    """Only engineers join tickets."""
    status, body = call(incidents, "POST", JOIN_PATH, REPORTER)
    assert (status, body["error"]) == (403, "Only engineers can join tickets")


@pytest.mark.parametrize("engineers", [[], [ASSIGNED_ENGINEER["id"]]])
def test_work_log_by_engineer_not_on_ticket_is_403(incidents, engineers):
    """An engineer who can see the ticket (pool or someone else's) must join before logging work."""
    incidents.engineers = engineers
    status, body = call(incidents, "POST", f"/api/incidents/{INCIDENT_ID}/work-logs", UNASSIGNED_ENGINEER,
                        {"work_date": "2026-01-01", "hours": 1, "description": "Checked the router"})
    assert (status, body["error"]) == (403, "Only engineers on this ticket can log work")
    assert "add_work_log" not in incidents.writes


def test_work_log_with_nan_hours_is_400(incidents):
    """Python's json.loads accepts the non-standard NaN literal, so a client can send it."""
    status, _ = call(incidents, "POST", f"/api/incidents/{INCIDENT_ID}/work-logs", ASSIGNED_ENGINEER,
                     '{"work_date": "2026-01-01", "hours": NaN, "description": "x"}')
    assert status == 400


def test_second_reopen_request_is_409(incidents):
    """Only one reopen request may be pending at a time."""
    incidents.incident = incident_row(status="resolved")
    path = f"/api/incidents/{INCIDENT_ID}/requests"
    first_status, _ = call(incidents, "POST", path, REPORTER, {"reason": "Still broken"})
    incidents.request_is_new = False  # the pending request now exists
    second_status, body = call(incidents, "POST", path, REPORTER, {"reason": "Still broken!"})

    assert first_status == 200
    assert (second_status, body["error"]) == (409, "A reopen request is already pending for this ticket")


def test_reopen_request_on_open_ticket_is_409(incidents):
    """Only resolved or closed tickets can be reopened."""
    status, body = call(incidents, "POST", f"/api/incidents/{INCIDENT_ID}/requests", REPORTER, {"reason": "x"})
    assert (status, body["error"]) == (409, "Only resolved or closed tickets can be reopened")


def test_void_by_admin_is_204(incidents):
    """Voiding is a soft delete that returns no content."""
    response = incidents.handler(make_event("DELETE", f"/api/incidents/{INCIDENT_ID}",
                                            {"version": 3, "reason": "Duplicate of #41"}, token_for(ADMIN)))
    assert (response["statusCode"], response["body"]) == (204, "")
    assert "void" in incidents.writes


@pytest.mark.parametrize("user", [REPORTER, ASSIGNED_ENGINEER])
def test_void_by_non_admin_is_403(incidents, user):
    """Even users who can see the ticket cannot void it."""
    status, body = call(incidents, "DELETE", f"/api/incidents/{INCIDENT_ID}", user,
                        {"version": 3, "reason": "Duplicate"})
    assert (status, body["error"]) == (403, "Only an admin can void a ticket")
    assert "void" not in incidents.writes


def test_void_without_reason_is_400(incidents):
    """A reason is required so the audit trail explains the void."""
    status, body = call(incidents, "DELETE", f"/api/incidents/{INCIDENT_ID}", ADMIN, {"version": 3})
    assert status == 400
    assert body["details"] == {"reason": "This field is required"}
