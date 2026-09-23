"""
Incident workflow rules (DESIGN.md section 5), kept in one dict.

These functions are pure: they take plain values and never touch the
database, so every allowed and forbidden transition is easy to unit test.
"""

# (from status, to status) -> who may do it and what the request must include.
#   who "assigned": an engineer on the ticket, or an admin
#   who "reporter": the person who reported it, or an admin
WORKFLOW = {
    ("open", "in_progress"): {"who": "assigned", "requires": None},
    ("open", "blocked"): {"who": "assigned", "requires": "reason"},
    ("in_progress", "blocked"): {"who": "assigned", "requires": "reason"},
    ("in_progress", "resolved"): {"who": "assigned", "requires": "resolution_note"},
    ("blocked", "in_progress"): {"who": "assigned", "requires": None},
    # Closing asks an admin to approve; approval archives the ticket.
    ("resolved", "closed"): {"who": "reporter", "requires": None},
}


def get_rule(current: str, target: str) -> dict | None:
    """Return the rule for moving from `current` to `target`, or None if that move is not allowed."""
    return WORKFLOW.get((current, target))


def is_permitted(rule: dict, user: dict, reporter_id: int, engineer_ids: set[int]) -> bool:
    """Return True if this user may perform a transition with this rule."""
    if user["role"] == "admin":
        return True
    if rule["who"] == "assigned":
        return user["role"] == "engineer" and user["id"] in engineer_ids
    if rule["who"] == "reporter":
        return user["id"] == reporter_id
    return False


def allowed_transitions(user: dict, status: str, reporter_id: int, engineer_ids: set[int]) -> list[str]:
    """List the statuses this user can move the ticket to right now (used to show only valid buttons)."""
    return [
        target
        for (current, target), rule in WORKFLOW.items()
        if current == status and is_permitted(rule, user, reporter_id, engineer_ids)
    ]


def can_view(user: dict, reporter_id: int, engineer_ids: set[int], is_archived: bool = False) -> bool:
    """
    Visibility (DESIGN.md section 6):
    - employees see only tickets they reported (anything else is a 404, so they
      can't find out what exists);
    - engineers see every active ticket read-only, because helping each other is
      a core requirement, plus archived tickets they reported or worked on;
    - admins see everything.
    Voided tickets are hidden from non-admins by the service layer.
    """
    if user["role"] == "admin" or user["id"] == reporter_id:
        return True
    if user["role"] == "engineer":
        return user["id"] in engineer_ids or not is_archived
    return False


def can_add_note(user: dict, reporter_id: int, engineer_ids: set[int]) -> bool:
    """
    The reporter, an admin, or an engineer on the ticket may add notes. Engineers
    who can only see the ticket must join it first (otherwise 403).
    """
    return user["role"] == "admin" or user["id"] == reporter_id or user["id"] in engineer_ids


def can_edit_details(user: dict, reporter_id: int) -> bool:
    """Only the reporter or an admin may edit a ticket's title and description."""
    return user["role"] == "admin" or user["id"] == reporter_id


# ---------- step 6: join, acknowledge, priority, requests, void, work logs ----------

ACTIVE_STATUSES = ("open", "in_progress", "blocked")
REOPENABLE_STATUSES = ("resolved", "closed")

# Work logs: quarter-hour steps from 15 minutes to 12 hours.
HOURS_STEP = 0.25
HOURS_MIN = 0.25
HOURS_MAX = 12


def can_join(user: dict, engineer_ids: set[int]) -> bool:
    """Any engineer may join a ticket they are not already on."""
    return user["role"] == "engineer" and user["id"] not in engineer_ids


def can_acknowledge(user: dict, status: str, engineer_ids: set[int]) -> bool:
    """An engineer on the ticket may commit to it for their shift while it is still active."""
    return user["role"] == "engineer" and user["id"] in engineer_ids and status in ACTIVE_STATUSES


def can_change_priority(user: dict, reporter_id: int) -> bool:
    """The reporter or an admin may change the priority (DESIGN.md section 6)."""
    return user["role"] == "admin" or user["id"] == reporter_id


def can_request_reopen(user: dict, status: str, reporter_id: int) -> bool:
    """The reporter (or an admin) may ask to reopen a resolved or closed ticket."""
    return (user["role"] == "admin" or user["id"] == reporter_id) and status in REOPENABLE_STATUSES


def can_decide_requests(user: dict) -> bool:
    """Only admins approve or reject close and reopen requests."""
    return user["role"] == "admin"


def can_void(user: dict) -> bool:
    """Only admins may void an erroneous incident."""
    return user["role"] == "admin"


def can_log_work(user: dict, engineer_ids: set[int]) -> bool:
    """Only engineers currently on the ticket may log work (13.4: otherwise 403)."""
    return user["role"] == "engineer" and user["id"] in engineer_ids


def hours_error(hours: float) -> str | None:
    """Return why an hours value is invalid, or None if it is valid (0.25 steps, 0.25 to 12)."""
    if hours < HOURS_MIN or hours > HOURS_MAX:
        return f"Must be between {HOURS_MIN} and {HOURS_MAX} hours"
    if round(hours / HOURS_STEP) * HOURS_STEP != hours:
        return f"Must be in steps of {HOURS_STEP} hours (15 minutes)"
    return None
