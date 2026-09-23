"""
Error-path tests for the facilities and engineers services and the approvals
queue, through the real Lambda handlers.

As in test_incidents_handler.py, only repository functions are replaced with
small fakes, so routing, token and role checks, validation and error mapping
all run for real without a database.
"""

import contextlib

import pytest

from helpers import make_event, response_json, token_for

ADMIN = {"id": 1, "role": "admin", "name": "Alex Morgan", "email": "admin@acme.inc"}
EMPLOYEE = {"id": 10, "role": "employee", "name": "Dana Whitfield", "email": "dana.whitfield@acme.inc"}
ENGINEER = {"id": 20, "role": "engineer", "name": "Priya Nair", "email": "priya.nair@acme.inc"}
OTHER_ENGINEER = {"id": 21, "role": "engineer", "name": "Tom Becker", "email": "tom.becker@acme.inc"}


def call(handler, method, path, user=None, body=None, query=None):
    """Run the handler and return (status, decoded body)."""
    token = token_for(user) if user else None
    response = handler(make_event(method, path, body=body, token=token, query=query))
    return response["statusCode"], response_json(response)


# ---------- facilities ----------

@pytest.fixture
def facilities(load_service, monkeypatch):
    """The facilities service with a fake repository: building 5 has 2 incidents, floor 7 has none."""
    svc = load_service("facilities")
    repo = svc.repository
    writes = []
    monkeypatch.setattr(repo, "get_building", lambda building_id: (
        {"id": 5, "name": "HQ Tower", "address": "1 Main St", "incident_count": 2} if building_id == 5 else None
    ))
    monkeypatch.setattr(repo, "get_floor", lambda floor_id: (
        {"id": 7, "building_id": 5, "number": 3, "incident_count": 0} if floor_id == 7 else None
    ))
    monkeypatch.setattr(repo, "create_building", lambda name, address: writes.append("create_building"))  # None = name taken
    monkeypatch.setattr(repo, "create_floor", lambda building_id, number: writes.append("create_floor"))
    monkeypatch.setattr(repo, "delete_building", lambda building_id: writes.append("delete_building") or True)
    monkeypatch.setattr(repo, "delete_floor", lambda floor_id: writes.append("delete_floor") or False)  # race: FK says no
    svc.writes = writes
    return svc


@pytest.mark.parametrize("user", [EMPLOYEE, ENGINEER])
def test_facilities_are_admin_only(facilities, user):
    """Only admins manage locations; everyone else gets 403 before anything is read."""
    status, body = call(facilities.function.handler, "GET", "/api/facilities/buildings", user)
    assert status == 403
    assert facilities.writes == []


def test_facilities_need_a_token(facilities):
    """No token -> 401."""
    status, _ = call(facilities.function.handler, "POST", "/api/facilities/buildings", body={"name": "X", "address": "Y"})
    assert status == 401


def test_create_building_validates_every_field(facilities):
    """Blank name, missing address and unknown fields are all reported at once."""
    status, body = call(facilities.function.handler, "POST", "/api/facilities/buildings", ADMIN,
                        {"name": "   ", "floors": 3})
    assert status == 400
    assert body["details"] == {"name": "This field is required", "address": "This field is required", "floors": "Unknown field"}
    assert facilities.writes == []


def test_duplicate_building_name_is_409(facilities):
    """The repository returns None when the unique name is taken."""
    status, body = call(facilities.function.handler, "POST", "/api/facilities/buildings", ADMIN,
                        {"name": "HQ Tower", "address": "Elsewhere"})
    assert status == 409
    assert body["details"] == {"name": "This name is already used"}


def test_building_with_incidents_cannot_be_deleted(facilities):
    """409 with the reason, and the delete is never attempted."""
    status, body = call(facilities.function.handler, "DELETE", "/api/facilities/buildings/5", ADMIN)
    assert status == 409
    assert "2 incidents" in body["error"]
    assert "delete_building" not in facilities.writes


def test_delete_missing_building_is_404(facilities):
    """Unknown ids are 404."""
    status, _ = call(facilities.function.handler, "DELETE", "/api/facilities/buildings/99", ADMIN)
    assert status == 404


def test_delete_floor_race_with_new_incident_is_409(facilities):
    """If an incident arrives between the check and the delete, the foreign key wins and we answer 409, not 500."""
    status, body = call(facilities.function.handler, "DELETE", "/api/facilities/floors/7", ADMIN)
    assert status == 409
    assert "now has incidents" in body["error"]


@pytest.mark.parametrize("number, message", [
    ("three", "Must be a whole number"),
    (True, "Must be a whole number"),
    (201, "Must be at most 200"),
    (-11, "Must be at least -10"),
])
def test_floor_number_limits(facilities, number, message):
    """Floor numbers are whole numbers from -10 (basements) to 200."""
    status, body = call(facilities.function.handler, "POST", "/api/facilities/buildings/5/floors", ADMIN, {"number": number})
    assert status == 400
    assert body["details"] == {"number": message}


def test_floor_on_missing_building_is_404(facilities):
    """A floor can only be added to an existing building."""
    status, _ = call(facilities.function.handler, "POST", "/api/facilities/buildings/99/floors", ADMIN, {"number": 1})
    assert status == 404


# ---------- engineers ----------

def engineer_row(user, **overrides):
    """An engineer as the shared workload query returns it."""
    row = {
        "id": user["id"], "name": user["name"], "email": user["email"], "phone": None,
        "specialty": "IT", "shift": "day", "is_available": True,
        "active_primary": 4, "active_helper": 0, "helped_others": 1, "hours_logged": 6.5, "missed_shifts": 0,
    }
    row.update(overrides)
    return row


@pytest.fixture
def engineers(load_service, monkeypatch):
    """The engineers service with a fake repository holding ENGINEER and OTHER_ENGINEER."""
    svc = load_service("engineers")
    repo = svc.repository
    rows = {ENGINEER["id"]: engineer_row(ENGINEER), OTHER_ENGINEER["id"]: engineer_row(OTHER_ENGINEER)}
    writes = []

    def set_availability(user_id, is_available):
        writes.append(("set_availability", user_id, is_available))
        rows[user_id]["is_available"] = is_available

    monkeypatch.setattr(repo, "get_engineer", lambda days, user_id: dict(rows[user_id]) if user_id in rows else None)
    monkeypatch.setattr(repo, "set_availability", set_availability)
    monkeypatch.setattr(repo, "transaction", contextlib.nullcontext)
    monkeypatch.setattr(repo, "create_user", lambda name, email, password_hash: None)  # None = email taken
    monkeypatch.setattr(repo, "create_profile", lambda *args: writes.append("create_profile"))
    svc.writes = writes
    return svc


VALID_ENGINEER = {"name": "Rhea Kapoor", "email": "rhea.kapoor@acme.inc", "password": "welcome-2026",
                  "specialty": "AV", "shift": "night"}


def test_employees_cannot_see_engineers(engineers):
    """The engineer list is for staff only."""
    status, _ = call(engineers.function.handler, "GET", "/api/engineers", EMPLOYEE)
    assert status == 403


def test_only_admins_create_engineers(engineers):
    """An engineer can't create accounts."""
    status, _ = call(engineers.function.handler, "POST", "/api/engineers", ENGINEER, VALID_ENGINEER)
    assert status == 403


def test_create_engineer_cannot_set_role(engineers):
    """'role' is not an accepted field, so nobody can create an admin this way."""
    status, body = call(engineers.function.handler, "POST", "/api/engineers", ADMIN, {**VALID_ENGINEER, "role": "admin"})
    assert status == 400
    assert body["details"] == {"role": "Unknown field"}


def test_create_engineer_validates_fields(engineers):
    """Company email, a known shift and a phone-like phone number."""
    status, body = call(engineers.function.handler, "POST", "/api/engineers", ADMIN,
                        {**VALID_ENGINEER, "email": "rhea@gmail.com", "shift": "evening", "phone": "call me"})
    assert status == 400
    assert set(body["details"]) == {"email", "shift", "phone"}


def test_create_engineer_with_taken_email_is_409(engineers):
    """No profile is written when the user insert hits the unique email."""
    status, body = call(engineers.function.handler, "POST", "/api/engineers", ADMIN, VALID_ENGINEER)
    assert status == 409
    assert body["details"] == {"email": "This email is already registered"}
    assert "create_profile" not in engineers.writes


def test_engineer_cannot_change_someone_elses_availability(engineers):
    """Engineers may only toggle themselves."""
    status, _ = call(engineers.function.handler, "PUT", f"/api/engineers/{OTHER_ENGINEER['id']}/availability", ENGINEER,
                     {"is_available": False})
    assert status == 403
    assert engineers.writes == []


def test_availability_must_be_a_boolean(engineers):
    """'false' as a string is rejected rather than read as true."""
    status, body = call(engineers.function.handler, "PUT", f"/api/engineers/{ENGINEER['id']}/availability", ENGINEER,
                        {"is_available": "false"})
    assert status == 400
    assert body["details"] == {"is_available": "Must be true or false"}


def test_going_unavailable_with_active_tickets_flags_reassignment(engineers):
    """Allowed (DESIGN.md 13.4), but the response says the tickets need a new owner."""
    status, body = call(engineers.function.handler, "PUT", f"/api/engineers/{ENGINEER['id']}/availability", ENGINEER,
                        {"is_available": False})
    assert status == 200
    assert body["is_available"] is False
    assert body["needs_reassignment"] is True


def test_availability_for_non_engineer_is_404(engineers):
    """Admins can toggle anyone, but only engineers have availability."""
    status, _ = call(engineers.function.handler, "PUT", f"/api/engineers/{EMPLOYEE['id']}/availability", ADMIN,
                     {"is_available": False})
    assert status == 404


# ---------- approvals queue (incidents service) ----------

@pytest.fixture
def approvals(load_service, monkeypatch):
    """The incidents service with list_pending_requests faked."""
    svc = load_service("incidents")
    calls = []
    monkeypatch.setattr(svc.repository, "list_pending_requests",
                        lambda request_type, page, page_size: calls.append((request_type, page, page_size)) or ([], 0))
    svc.calls = calls
    return svc


@pytest.mark.parametrize("user", [EMPLOYEE, ENGINEER])
def test_approvals_queue_is_admin_only(approvals, user):
    """Only admins decide requests, so only they see the queue."""
    status, _ = call(approvals.function.handler, "GET", "/api/incidents/requests", user)
    assert status == 403
    assert approvals.calls == []


def test_approvals_queue_filters_by_type(approvals):
    """?type= narrows the queue; the default page is 1 with 25 rows."""
    status, body = call(approvals.function.handler, "GET", "/api/incidents/requests", ADMIN, query={"type": "reopen"})
    assert status == 200
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 25}
    assert approvals.calls == [("reopen", 1, 25)]


def test_approvals_queue_rejects_unknown_type(approvals):
    """Only the two request types exist."""
    status, body = call(approvals.function.handler, "GET", "/api/incidents/requests", ADMIN, query={"type": "refund"})
    assert status == 400
    assert "type" in body["details"]
