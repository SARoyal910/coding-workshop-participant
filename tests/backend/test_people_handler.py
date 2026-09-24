"""
Tests for people management in the auth service (GET /users, PUT /users/{id}/role),
through the real Lambda handler with a fake repository.
"""

import contextlib

import pytest

from helpers import make_event, response_json, token_for

ADMIN = {"id": 1, "role": "admin", "name": "Alex Morgan", "email": "admin@acme.inc"}
EMPLOYEE = {"id": 10, "role": "employee", "name": "Dana Whitfield", "email": "dana.whitfield@acme.inc"}
ENGINEER = {"id": 20, "role": "engineer", "name": "Priya Nair", "email": "priya.nair@acme.inc"}


@pytest.fixture
def people(load_service, monkeypatch):
    """The auth service with a fake people table; .writes records role and profile changes."""
    svc = load_service("auth")
    repo = svc.repository
    rows = {
        1: {**ADMIN, "specialty": None, "shift": None, "is_available": None},
        10: {**EMPLOYEE, "specialty": None, "shift": None, "is_available": None},
        20: {**ENGINEER, "specialty": "IT", "shift": "day", "is_available": True},
    }
    state = type("State", (), {})()
    state.handler, state.rows, state.writes, state.active = svc.function.handler, rows, [], 0

    def set_role(user_id, role):
        state.writes.append(("set_role", user_id, role))
        rows[user_id]["role"] = role

    def save_profile(user_id, specialty, shift):
        state.writes.append(("profile", user_id, specialty, shift))
        rows[user_id].update(specialty=specialty, shift=shift)

    monkeypatch.setattr(repo, "get_person", lambda user_id: dict(rows[user_id]) if user_id in rows else None)
    monkeypatch.setattr(repo, "set_role", set_role)
    monkeypatch.setattr(repo, "save_engineer_profile", save_profile)
    monkeypatch.setattr(repo, "active_primary_count", lambda user_id: state.active)
    monkeypatch.setattr(repo, "transaction", contextlib.nullcontext)
    monkeypatch.setattr(repo, "list_users", lambda role, search, page, size: (
        [r for r in rows.values() if role in (None, r["role"])], len(rows)))
    return state


def call(state, method, path, user, body=None, query=None):
    response = state.handler(make_event(method, path, body, token_for(user), query))
    return response["statusCode"], response_json(response)


ROLE = "/api/auth/users/{}/role"


@pytest.mark.parametrize("user", [EMPLOYEE, ENGINEER])
def test_only_admins_see_people(people, user):
    status, body = call(people, "GET", "/api/auth/users", user)
    assert (status, body["error"]) == (403, "Only an admin can manage people")


def test_admin_lists_everyone_and_filters_by_role(people):
    status, body = call(people, "GET", "/api/auth/users", ADMIN)
    assert status == 200 and body["total"] == 3
    _, engineers = call(people, "GET", "/api/auth/users", ADMIN, query={"role": "engineer"})
    assert [p["id"] for p in engineers["items"]] == [20]


def test_promoting_an_employee_to_engineer_needs_specialty_and_shift(people):
    status, body = call(people, "PUT", ROLE.format(10), ADMIN, {"role": "engineer"})
    assert status == 400
    assert set(body["details"]) == {"specialty", "shift"}
    assert not people.writes


def test_promote_employee_to_engineer(people):
    status, body = call(people, "PUT", ROLE.format(10), ADMIN, {"role": "engineer", "specialty": "AV", "shift": "swing"})
    assert (status, body["role"], body["specialty"], body["shift"]) == (200, "engineer", "AV", "swing")
    assert people.writes == [("profile", 10, "AV", "swing"), ("set_role", 10, "engineer")]


def test_engineer_made_admin_and_back_keeps_their_profile(people):
    """Covering for an admin on vacation, then returning to engineering work."""
    assert call(people, "PUT", ROLE.format(20), ADMIN, {"role": "admin"})[0] == 200
    status, body = call(people, "PUT", ROLE.format(20), ADMIN, {"role": "engineer"})
    assert (status, body["role"], body["specialty"], body["shift"]) == (200, "engineer", "IT", "day")


def test_admin_cannot_change_their_own_role(people):
    """This also guarantees at least one admin always remains."""
    status, body = call(people, "PUT", ROLE.format(1), ADMIN, {"role": "engineer", "specialty": "IT", "shift": "day"})
    assert (status, body["error"]) == (409, "You can't change your own role. Ask another admin.")


def test_cannot_make_an_engineer_an_employee_while_primary_on_tickets(people):
    people.active = 2
    status, body = call(people, "PUT", ROLE.format(20), ADMIN, {"role": "employee"})
    assert (status, body["error"]) == (409, "Priya Nair is primary on 2 active ticket(s). Reassign them first.")
    assert not people.writes


def test_specialty_without_shift_is_400(people):
    status, body = call(people, "PUT", ROLE.format(10), ADMIN, {"role": "engineer", "specialty": "AV"})
    assert (status, body["details"]) == (400, {"shift": "Send specialty and shift together"})


def test_unknown_user_is_404(people):
    assert call(people, "PUT", ROLE.format(999), ADMIN, {"role": "admin"})[0] == 404
