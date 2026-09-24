"""
Tests for the dashboard service through the real Lambda handler.

As in the other handler tests, only repository functions are replaced with
small fakes, so routing, token checks, the per-role choice and every
calculation in service.py run for real without a database.
"""

import pytest

from helpers import make_event, response_json, token_for

ADMIN = {"id": 1, "role": "admin", "name": "Alex Morgan", "email": "admin@acme.inc"}
EMPLOYEE = {"id": 10, "role": "employee", "name": "Dana Whitfield", "email": "dana.whitfield@acme.inc"}
ENGINEER = {"id": 20, "role": "engineer", "name": "Priya Nair", "email": "priya.nair@acme.inc"}


def engineer_row(engineer_id, shift, is_available=True, active_primary=0, missed_shifts=0):
    """One row as _shared.engineer_stats.engineer_workload returns it (only the fields the service reads)."""
    return {"id": engineer_id, "shift": shift, "is_available": is_available,
            "active_primary": active_primary, "missed_shifts": missed_shifts, "total": 3}


@pytest.fixture
def dashboard(load_service, monkeypatch):
    """
    The dashboard service with a fake repository.

    Three engineers: two on day shift (one unavailable but still primary on 2
    tickets) and one on night shift. The service's clock is fixed at 15:00 UTC
    (11:00 in New York), so the day shift is the one running.
    """
    svc = load_service("dashboard")
    repo = svc.repository
    calls = {}

    def status_counts(user_id=None, engineer_id=None):
        calls["status_counts"] = {"user_id": user_id, "engineer_id": engineer_id}
        return [{"status": "open", "count": 4}, {"status": "blocked", "count": 1}]

    def engineer_workload(days, engineer_id=None):
        rows = [
            engineer_row(20, "day", active_primary=1, missed_shifts=1),
            engineer_row(21, "day", is_available=False, active_primary=2),
            engineer_row(22, "night", missed_shifts=2),
        ]
        return [row for row in rows if engineer_id in (None, row["id"])]

    monkeypatch.setattr(repo, "status_counts", status_counts)

    def incident_totals(user_id=None, engineer_id=None):
        calls["incident_totals"] = {"user_id": user_id, "engineer_id": engineer_id}
        return {"total": 9, "active": 5, "archived": 4, "voided": 1}

    monkeypatch.setattr(repo, "incident_totals", incident_totals)
    monkeypatch.setattr(repo, "engineer_workload", engineer_workload)
    monkeypatch.setattr(repo, "issue_types", lambda days: [
        {"category": "IT", "issue_type": "Wi-Fi", "count": 5, "avg_hours": 1},
        {"category": "AV", "issue_type": "Projector", "count": 2, "avg_hours": 0},
        {"category": "IT", "issue_type": "Monitor", "count": 3, "avg_hours": 2},
    ])
    monkeypatch.setattr(repo, "communication", lambda days: {
        "first_update_hours": 2.5, "resolved": 6, "resolved_with_note": 5, "reopen_requested": 1})
    monkeypatch.setattr(repo, "pending_requests", lambda: [{"type": "reopen", "count": 2}])
    for name in ("recurring_seats", "recurring_floors", "building_hotspots"):
        monkeypatch.setattr(repo, name, lambda *args: [])
    monkeypatch.setattr(repo, "response_times", lambda days: {"acknowledge_hours": 1.0})
    monkeypatch.setattr(repo, "blocked_incidents", lambda: [])
    monkeypatch.setattr(repo, "escalated_by_reporters", lambda: [])
    monkeypatch.setattr(repo, "unassigned_pool_count", lambda: 7)

    import datetime as real_datetime

    class FixedClock(real_datetime.datetime):
        """datetime whose now() is always 2026-09-23 15:00 UTC."""

        @classmethod
        def now(cls, tz=None):
            return real_datetime.datetime(2026, 9, 23, 15, 0, tzinfo=real_datetime.timezone.utc)

    monkeypatch.setattr(svc.service, "datetime", FixedClock)
    svc.calls = calls
    return svc


def get_dashboard(svc, user=None):
    """GET /api/dashboard as the user; returns (status, body)."""
    token = token_for(user) if user else None
    response = svc.function.handler(make_event("GET", "/api/dashboard", token=token))
    return response["statusCode"], response_json(response)


def test_dashboard_needs_a_token(dashboard):
    """No token -> 401."""
    assert get_dashboard(dashboard)[0] == 401


def test_unknown_route_is_404(dashboard):
    """Only GET / exists."""
    response = dashboard.function.handler(make_event("GET", "/api/dashboard/other", token=token_for(ADMIN)))
    assert response["statusCode"] == 404


def test_admin_dashboard_answers_every_question(dashboard):
    """The admin view has one section per business question, plus pending requests."""
    status, body = get_dashboard(dashboard, ADMIN)
    assert status == 200
    assert body["role"] == "admin"
    for key in ("status_counts", "recurring", "response_times", "engineers", "shift_coverage",
                "categories", "issue_types", "needs_attention", "communication", "pending_requests"):
        assert key in body


def test_admin_status_counts_include_every_status(dashboard):
    """Statuses with no tickets are reported as 0, not left out."""
    _, body = get_dashboard(dashboard, ADMIN)
    assert body["status_counts"] == {"open": 4, "in_progress": 0, "blocked": 1, "resolved": 0, "closed": 0}
    assert dashboard.calls["status_counts"] == {"user_id": None, "engineer_id": None}


def test_admin_categories_add_up_issue_types(dashboard):
    """Category totals are the sum of their issue types."""
    _, body = get_dashboard(dashboard, ADMIN)
    assert body["categories"] == [{"category": "IT", "count": 8}, {"category": "AV", "count": 2}]


def test_admin_engineers_are_flagged_for_reassignment_and_shift(dashboard):
    """Unavailable but still primary -> needs reassignment; on_shift_now follows the fixed clock; paging total is dropped."""
    _, body = get_dashboard(dashboard, ADMIN)
    by_id = {row["id"]: row for row in body["engineers"]}
    assert by_id[21]["needs_reassignment"] is True
    assert by_id[20]["needs_reassignment"] is False
    assert (by_id[20]["on_shift_now"], by_id[22]["on_shift_now"]) == (True, False)
    assert all("total" not in row for row in body["engineers"])


def test_admin_shift_coverage_totals_each_shift(dashboard):
    """Every shift is listed, even one with no engineers, with totals and whether it is running now."""
    _, body = get_dashboard(dashboard, ADMIN)
    assert body["shift_coverage"] == [
        {"shift": "day", "engineers": 2, "available": 1, "active_primary": 3, "missed_shifts": 1, "is_current": True},
        {"shift": "swing", "engineers": 0, "available": 0, "active_primary": 0, "missed_shifts": 0, "is_current": False},
        {"shift": "night", "engineers": 1, "available": 1, "active_primary": 0, "missed_shifts": 2, "is_current": False},
    ]


def test_admin_communication_percentages(dashboard):
    """5 of 6 resolved had a note (83%); 1 of 6 was asked to be reopened (17%). Both rounded to whole numbers."""
    _, body = get_dashboard(dashboard, ADMIN)
    assert body["communication"] == {
        "first_update_hours": 2.5, "resolved": 6, "resolved_with_note_pct": 83, "reopen_rate_pct": 17}
    assert body["pending_requests"] == {"close_approval": 0, "reopen": 2}


def test_percentages_are_none_when_nothing_is_resolved(dashboard, monkeypatch):
    """No resolved tickets -> no percentage (not a division by zero, and not a misleading 0%)."""
    monkeypatch.setattr(dashboard.repository, "communication", lambda days: {
        "first_update_hours": None, "resolved": 0, "resolved_with_note": 0, "reopen_requested": 0})
    _, body = get_dashboard(dashboard, ADMIN)
    assert (body["communication"]["resolved_with_note_pct"], body["communication"]["reopen_rate_pct"]) == (None, None)


def test_engineer_sees_only_their_own_work(dashboard):
    """Status counts are filtered to the engineer's tickets; 'me' is their own row."""
    status, body = get_dashboard(dashboard, ENGINEER)
    assert status == 200
    assert dashboard.calls["status_counts"] == {"user_id": None, "engineer_id": 20}
    assert body["role"] == "engineer"
    assert body["unassigned_pool"] == 7
    assert (body["me"]["id"], body["me"]["on_shift_now"]) == (20, True)
    assert "total" not in body["me"]
    assert "engineers" not in body  # no team-wide data


def test_engineer_without_a_profile_gets_no_row(dashboard, monkeypatch):
    """An engineer with no workload row gets me = None instead of an error."""
    monkeypatch.setattr(dashboard.repository, "engineer_workload", lambda days, engineer_id=None: [])
    _, body = get_dashboard(dashboard, ENGINEER)
    assert body["me"] is None


def test_employee_sees_only_their_own_tickets(dashboard):
    """Status counts are filtered to the employee's reports."""
    status, body = get_dashboard(dashboard, EMPLOYEE)
    assert status == 200
    assert dashboard.calls["status_counts"] == {"user_id": 10, "engineer_id": None}
    assert body == {
        "role": "employee",
        "status_counts": {"open": 4, "in_progress": 0, "blocked": 1, "resolved": 0, "closed": 0},
        "totals": {"total": 9, "active": 5, "archived": 4, "voided": 1},
    }
    assert dashboard.calls["incident_totals"] == {"user_id": 10, "engineer_id": None}


@pytest.mark.parametrize(("user", "expected_filter"), [
    (ADMIN, {"user_id": None, "engineer_id": None}),        # every incident
    (ENGINEER, {"user_id": None, "engineer_id": 20}),       # tickets they worked on
])
def test_totals_are_scoped_to_the_role(dashboard, user, expected_filter):
    """The total counts what each role is responsible for, including archived tickets."""
    status, body = get_dashboard(dashboard, user)
    assert status == 200
    assert body["totals"] == {"total": 9, "active": 5, "archived": 4, "voided": 1}
    assert dashboard.calls["incident_totals"] == expected_filter
