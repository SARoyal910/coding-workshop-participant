"""
Handler tests for recurring-issue badges and the report form's similar-incident
check (GET /api/incidents/similar), with the repository faked.

The key rule: employees get counts, but never other people's tickets.
"""

import pytest

from helpers import make_event, response_json, token_for

ADMIN = {"id": 1, "role": "admin", "name": "Alex Morgan", "email": "admin@acme.inc"}
REPORTER = {"id": 10, "role": "employee", "name": "Dana Whitfield", "email": "dana.whitfield@acme.inc"}
ENGINEER = {"id": 20, "role": "engineer", "name": "Priya Nair", "email": "priya.nair@acme.inc"}

# Two open Wi-Fi tickets at the seat: one Dana's, one someone else's.
OPEN_AT_SEAT = [
    {"id": 5, "title": "Wi-Fi keeps dropping", "status": "open", "reporter_id": REPORTER["id"], "seat_code": "12-A-034"},
    {"id": 4, "title": "No Wi-Fi", "status": "in_progress", "reporter_id": 99, "seat_code": "12-A-034"},
]
RELATED = [{"id": 4, "title": "No Wi-Fi", "status": "in_progress", "is_archived": False, "seat_code": "12-A-034"}]


def call(handler, path, user, query=None):
    """GET through the real handler and return (status, body)."""
    response = handler(make_event("GET", path, token=token_for(user), query=query))
    return response["statusCode"], response_json(response)


@pytest.fixture
def incidents(load_service, monkeypatch):
    """The incidents service with the recurring queries faked (5 at the seat, 6 on the floor)."""
    svc = load_service("incidents")
    repo = svc.repository
    counts = {"seat_count": 5, "floor_count": 6, "floor_seats": 2}
    monkeypatch.setattr(repo, "open_at_location", lambda issue_type, floor_id, seat_id, limit: list(OPEN_AT_SEAT))
    monkeypatch.setattr(repo, "recent_counts_at_location", lambda issue_type, floor_id, seat_id, days: dict(counts))
    monkeypatch.setattr(repo, "recurring_counts", lambda ids, days: {i: dict(counts) for i in ids})
    monkeypatch.setattr(repo, "related_incidents", lambda *args, **kwargs: list(RELATED))
    monkeypatch.setattr(repo, "get_incident", lambda incident_id: {
        "id": incident_id, "reporter_id": REPORTER["id"], "status": "open",
        "is_archived": False, "is_voided": False, "floor_number": 12, "seat_code": "12-A-034",
    })
    for name in ("get_engineers", "get_notes", "get_work_logs", "get_requests", "get_acks", "get_events"):
        monkeypatch.setattr(repo, name, lambda incident_id: [])
    return svc.function.handler


SIMILAR = {"issue_type": "Wi-Fi", "floor_id": "7", "seat_id": "40"}


def test_similar_for_staff_lists_every_open_match(incidents):
    """Staff see all open duplicates and the recurring pattern."""
    status, body = call(incidents, "/api/incidents/similar", ENGINEER, SIMILAR)
    assert status == 200
    assert body["open_count"] == 2
    assert [item["id"] for item in body["items"]] == [5, 4]
    assert body["recurring"] == {"level": "seat", "count": 5, "window_days": 30}


def test_similar_for_employee_hides_other_peoples_tickets(incidents):
    """Dana learns there are 2 open reports but only gets a link to her own."""
    status, body = call(incidents, "/api/incidents/similar", REPORTER, SIMILAR)
    assert status == 200
    assert body["open_count"] == 2
    assert [item["id"] for item in body["items"]] == [5]


@pytest.mark.parametrize(("query", "field"), [
    ({"floor_id": "7"}, "issue_type"),
    ({"issue_type": "Teleporter", "floor_id": "7"}, "issue_type"),
    ({"issue_type": "Wi-Fi"}, "floor_id"),
    ({"issue_type": "Wi-Fi", "floor_id": "seven"}, "floor_id"),
    ({"issue_type": "Wi-Fi", "floor_id": "7", "building_id": "1"}, "building_id"),
])
def test_similar_validates_query(incidents, query, field):
    """Missing or bad parameters are a 400 naming the field."""
    status, body = call(incidents, "/api/incidents/similar", REPORTER, query)
    assert status == 400
    assert field in body["details"]


def test_detail_recurring_for_staff_includes_related(incidents):
    """An admin sees the pattern and the related tickets."""
    status, body = call(incidents, "/api/incidents/5", ADMIN)
    assert status == 200
    assert body["recurring"]["level"] == "seat"
    assert body["recurring"]["count"] == 5
    assert body["recurring"]["related"] == RELATED


def test_detail_recurring_for_employee_is_count_only(incidents):
    """The reporter sees the badge and count, never other people's tickets."""
    status, body = call(incidents, "/api/incidents/5", REPORTER)
    assert status == 200
    assert body["recurring"]["count"] == 5
    assert body["recurring"]["related"] == []
