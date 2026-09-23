"""
Unit tests for backend/incidents/rules.py (DESIGN.md sections 5 and 6).

rules.py is pure, so these tests need no database and no mocks: they call the
functions with plain dicts and ids.
"""

from types import ModuleType

import pytest

# People used throughout. Ids are arbitrary but distinct.
ADMIN = {"id": 1, "role": "admin"}
REPORTER = {"id": 10, "role": "employee"}
OTHER_EMPLOYEE = {"id": 11, "role": "employee"}
ASSIGNED_ENGINEER = {"id": 20, "role": "engineer"}
UNASSIGNED_ENGINEER = {"id": 21, "role": "engineer"}

REPORTER_ID = REPORTER["id"]
ON_TICKET = {ASSIGNED_ENGINEER["id"]}  # engineer ids on the ticket
POOL: set[int] = set()  # nobody on the ticket yet

# The workflow from DESIGN.md section 5: (from, to) -> (who, requires).
EXPECTED_TRANSITIONS = {
    ("open", "in_progress"): ("assigned", None),
    ("open", "blocked"): ("assigned", "reason"),
    ("in_progress", "blocked"): ("assigned", "reason"),
    ("in_progress", "resolved"): ("assigned", "resolution_note"),
    ("blocked", "in_progress"): ("assigned", None),
    ("resolved", "closed"): ("reporter", None),
}

# Moves that must never be allowed through POST /{id}/status.
FORBIDDEN_TRANSITIONS = [
    ("open", "resolved"),         # must be worked on first
    ("open", "closed"),
    ("in_progress", "open"),      # no going back to open
    ("in_progress", "closed"),    # must be resolved first
    ("blocked", "resolved"),      # unblock first
    ("blocked", "closed"),
    ("resolved", "in_progress"),  # reopening goes through a reopen request instead
    ("resolved", "open"),
    ("closed", "open"),
    ("closed", "in_progress"),
    ("open", "open"),             # "moving" to the same status
    ("open", "archived"),         # not a status at all
]


@pytest.fixture
def rules(load_service) -> ModuleType:
    """The incidents service's rules module."""
    return load_service("incidents").modules["rules"]


# ---------- get_rule: which moves exist ----------

@pytest.mark.parametrize(("current", "target"), list(EXPECTED_TRANSITIONS))
def test_every_designed_transition_is_allowed(rules, current, target):
    """Each move from DESIGN.md exists, with the right actor and required field."""
    rule = rules.get_rule(current, target)
    assert rule is not None
    assert (rule["who"], rule["requires"]) == EXPECTED_TRANSITIONS[(current, target)]


def test_workflow_contains_every_designed_transition(rules):
    """Nothing from the design is missing from the WORKFLOW dict."""
    assert set(EXPECTED_TRANSITIONS) <= set(rules.WORKFLOW)


@pytest.mark.parametrize(("current", "target"), FORBIDDEN_TRANSITIONS)
def test_forbidden_transitions_have_no_rule(rules, current, target):
    """Moves outside the workflow return None, which the service turns into a 409."""
    assert rules.get_rule(current, target) is None


# ---------- is_permitted: who may make a move ----------

@pytest.mark.parametrize(("user", "expected"), [
    (ADMIN, True),
    (ASSIGNED_ENGINEER, True),
    (UNASSIGNED_ENGINEER, False),
    (REPORTER, False),
    (OTHER_EMPLOYEE, False),
])
def test_is_permitted_for_assigned_engineer_moves(rules, user, expected):
    """open -> in_progress: only an engineer on the ticket, or an admin."""
    rule = rules.get_rule("open", "in_progress")
    assert rules.is_permitted(rule, user, REPORTER_ID, ON_TICKET) is expected


@pytest.mark.parametrize(("user", "expected"), [
    (ADMIN, True),
    (REPORTER, True),
    (ASSIGNED_ENGINEER, False),
    (UNASSIGNED_ENGINEER, False),
    (OTHER_EMPLOYEE, False),
])
def test_is_permitted_for_reporter_moves(rules, user, expected):
    """resolved -> closed: only the reporter, or an admin."""
    rule = rules.get_rule("resolved", "closed")
    assert rules.is_permitted(rule, user, REPORTER_ID, ON_TICKET) is expected


def test_employee_id_in_engineer_ids_is_still_not_permitted(rules):
    """The role is checked too: an employee id listed as an engineer id gets no engineer rights."""
    rule = rules.get_rule("open", "in_progress")
    assert rules.is_permitted(rule, REPORTER, REPORTER_ID, {REPORTER["id"]}) is False


def test_engineer_who_reported_the_ticket_can_close_it(rules):
    """An engineer can also be a reporter; closing is decided by being the reporter."""
    rule = rules.get_rule("resolved", "closed")
    assert rules.is_permitted(rule, UNASSIGNED_ENGINEER, UNASSIGNED_ENGINEER["id"], ON_TICKET) is True


def test_unknown_who_is_denied_for_non_admins(rules):
    """A rule with an unexpected "who" fails closed for everybody except admins."""
    rule = {"who": "someone_new", "requires": None}
    assert rules.is_permitted(rule, REPORTER, REPORTER_ID, ON_TICKET) is False
    assert rules.is_permitted(rule, ADMIN, REPORTER_ID, ON_TICKET) is True


# ---------- allowed_transitions: which buttons the UI shows ----------

@pytest.mark.parametrize(("user", "status", "expected"), [
    (ASSIGNED_ENGINEER, "open", ["in_progress", "blocked"]),
    (ASSIGNED_ENGINEER, "in_progress", ["blocked", "resolved"]),
    (ASSIGNED_ENGINEER, "blocked", ["in_progress"]),
    (ASSIGNED_ENGINEER, "resolved", []),  # closing is the reporter's call
    (REPORTER, "open", []),
    (REPORTER, "resolved", ["closed"]),
    (UNASSIGNED_ENGINEER, "open", []),
    (ADMIN, "in_progress", ["blocked", "resolved"]),
    (ADMIN, "resolved", ["closed"]),
    (ADMIN, "closed", []),  # nothing left through the status endpoint
])
def test_allowed_transitions(rules, user, status, expected):
    """Only the moves this user may make from this status are listed."""
    assert sorted(rules.allowed_transitions(user, status, REPORTER_ID, ON_TICKET)) == sorted(expected)


# ---------- can_view: who sees a ticket ----------

@pytest.mark.parametrize(("user", "engineer_ids", "is_archived", "expected"), [
    (ADMIN, ON_TICKET, False, True),
    (ADMIN, ON_TICKET, True, True),                    # admins see archived tickets too
    (REPORTER, ON_TICKET, False, True),                # own ticket
    (REPORTER, ON_TICKET, True, True),                 # own ticket, even archived
    (OTHER_EMPLOYEE, ON_TICKET, False, False),         # someone else's ticket
    (OTHER_EMPLOYEE, POOL, False, False),              # employees never see the pool
    (ASSIGNED_ENGINEER, ON_TICKET, False, True),       # on the ticket
    (ASSIGNED_ENGINEER, ON_TICKET, True, True),        # worked on it, so still sees it archived
    (UNASSIGNED_ENGINEER, POOL, False, True),          # unassigned pool
    (UNASSIGNED_ENGINEER, ON_TICKET, False, True),     # someone else's active ticket, read-only
    (UNASSIGNED_ENGINEER, ON_TICKET, True, False),     # someone else's archived ticket
    (UNASSIGNED_ENGINEER, POOL, True, False),
])
def test_can_view(rules, user, engineer_ids, is_archived, expected):
    """
    Visibility rules from DESIGN.md section 6: engineers see every active ticket,
    but archived ones only if they were on them.

    Voided tickets are hidden by the service, not here (see test_incidents_handler.py).
    """
    assert rules.can_view(user, REPORTER_ID, engineer_ids, is_archived) is expected


def test_can_view_defaults_to_active_ticket(rules):
    """is_archived defaults to False."""
    assert rules.can_view(UNASSIGNED_ENGINEER, REPORTER_ID, ON_TICKET) is True


@pytest.mark.parametrize(("user", "expected"), [
    (ADMIN, True),
    (REPORTER, True),
    (ASSIGNED_ENGINEER, True),
    (UNASSIGNED_ENGINEER, False),   # can see the ticket, but must join before adding notes
    (OTHER_EMPLOYEE, False),
])
def test_can_add_note(rules, user, expected):
    """The reporter, an admin, or an engineer on the ticket may add notes."""
    assert rules.can_add_note(user, REPORTER_ID, ON_TICKET) is expected


# ---------- can_edit_details: who edits title/description ----------

@pytest.mark.parametrize(("user", "expected"), [
    (ADMIN, True),
    (REPORTER, True),
    (OTHER_EMPLOYEE, False),
    (ASSIGNED_ENGINEER, False),  # engineers add notes, they don't rewrite the report
])
def test_can_edit_details(rules, user, expected):
    """Only the reporter or an admin may edit the title and description."""
    assert rules.can_edit_details(user, REPORTER_ID) is expected



# ---------- join / acknowledge / priority / requests / void / work logs ----------

@pytest.mark.parametrize(("user", "engineer_ids", "expected"), [
    (UNASSIGNED_ENGINEER, POOL, True),         # first engineer -> becomes primary
    (UNASSIGNED_ENGINEER, ON_TICKET, True),    # later engineers -> helpers
    (ASSIGNED_ENGINEER, ON_TICKET, False),     # already on it
    (REPORTER, POOL, False),                   # employees don't join tickets
    (ADMIN, POOL, False),                      # neither do admins
])
def test_can_join(rules, user, engineer_ids, expected):
    """Any engineer who is not already on the ticket may join it."""
    assert rules.can_join(user, engineer_ids) is expected


@pytest.mark.parametrize(("user", "status", "expected"), [
    (ASSIGNED_ENGINEER, "open", True),
    (ASSIGNED_ENGINEER, "in_progress", True),
    (ASSIGNED_ENGINEER, "blocked", True),
    (ASSIGNED_ENGINEER, "resolved", False),    # no longer active
    (ASSIGNED_ENGINEER, "closed", False),
    (UNASSIGNED_ENGINEER, "open", False),      # must join first
    (ADMIN, "open", False),                    # acknowledging is an engineer's shift commitment
])
def test_can_acknowledge(rules, user, status, expected):
    """Only an engineer on an active ticket may acknowledge it."""
    assert rules.can_acknowledge(user, status, ON_TICKET) is expected


@pytest.mark.parametrize(("user", "expected"), [
    (ADMIN, True), (REPORTER, True), (OTHER_EMPLOYEE, False), (ASSIGNED_ENGINEER, False),
])
def test_can_change_priority(rules, user, expected):
    """The reporter or an admin may change the priority."""
    assert rules.can_change_priority(user, REPORTER_ID) is expected


@pytest.mark.parametrize(("user", "status", "expected"), [
    (REPORTER, "resolved", True),
    (REPORTER, "closed", True),
    (REPORTER, "open", False),                 # nothing to reopen
    (REPORTER, "in_progress", False),
    (ADMIN, "resolved", True),
    (OTHER_EMPLOYEE, "resolved", False),
    (ASSIGNED_ENGINEER, "resolved", False),
])
def test_can_request_reopen(rules, user, status, expected):
    """The reporter (or an admin) may ask to reopen a resolved or closed ticket."""
    assert rules.can_request_reopen(user, status, REPORTER_ID) is expected


@pytest.mark.parametrize("check", ["can_decide_requests", "can_void"])
@pytest.mark.parametrize(("user", "expected"), [
    (ADMIN, True), (REPORTER, False), (ASSIGNED_ENGINEER, False),
])
def test_admin_only_actions(rules, check, user, expected):
    """Deciding requests and voiding tickets are admin-only."""
    assert getattr(rules, check)(user) is expected


@pytest.mark.parametrize(("user", "engineer_ids", "expected"), [
    (ASSIGNED_ENGINEER, ON_TICKET, True),
    (UNASSIGNED_ENGINEER, ON_TICKET, False),   # can see pool tickets, but not on this one
    (UNASSIGNED_ENGINEER, POOL, False),
    (ADMIN, ON_TICKET, False),                 # admins don't log hours
    (REPORTER, {REPORTER["id"]}, False),       # role is checked, not only the id
])
def test_can_log_work(rules, user, engineer_ids, expected):
    """Only engineers currently on the ticket may log work."""
    assert rules.can_log_work(user, engineer_ids) is expected


@pytest.mark.parametrize("hours", [0.25, 0.5, 1, 1.75, 8, 11.75, 12])
def test_hours_error_accepts_quarter_hours_in_range(rules, hours):
    """Quarter-hour steps from 0.25 to 12 inclusive are valid."""
    assert rules.hours_error(hours) is None


@pytest.mark.parametrize(("hours", "message"), [
    (0, "Must be between 0.25 and 12 hours"),
    (-1, "Must be between 0.25 and 12 hours"),
    (0.1, "Must be between 0.25 and 12 hours"),
    (12.25, "Must be between 0.25 and 12 hours"),
    (float("inf"), "Must be between 0.25 and 12 hours"),
    (1.1, "Must be in steps of 0.25 hours (15 minutes)"),
    (0.3, "Must be in steps of 0.25 hours (15 minutes)"),
    (7.9, "Must be in steps of 0.25 hours (15 minutes)"),
])
def test_hours_error_rejects_bad_values(rules, hours, message):
    """Out-of-range values and values that are not quarter hours are rejected with a reason."""
    assert rules.hours_error(hours) == message


# ---------- regression: NaN hours used to crash (see docs/TESTING.md) ----------

def test_hours_error_rejects_nan(rules):
    """A work log body of {"hours": NaN} should be a 400, not a crash."""
    assert rules.hours_error(float("nan")) is not None
