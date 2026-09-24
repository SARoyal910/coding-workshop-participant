"""
Incident workflow rules (DESIGN.md section 5), kept in one dict.

These functions are pure: they take plain values and never touch the
database, so every allowed and forbidden transition is easy to unit test.
"""

import math

# (from status, to status) -> who may do it and what the request must include.
#   who "assigned": an engineer on the ticket, or an admin
# Reporters don't move tickets through the workflow; they can ask to reopen one.
WORKFLOW = {
    ("open", "in_progress"): {"who": "assigned", "requires": None},
    ("open", "blocked"): {"who": "assigned", "requires": "reason"},
    ("in_progress", "blocked"): {"who": "assigned", "requires": "reason"},
    ("in_progress", "resolved"): {"who": "assigned", "requires": "resolution_note"},
    ("blocked", "in_progress"): {"who": "assigned", "requires": None},
    # The engineer (or an admin) closes a resolved ticket; closing asks an admin
    # to approve, and approval archives the ticket.
    ("resolved", "closed"): {"who": "assigned", "requires": None},
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
    return False


def allowed_transitions(user: dict, status: str, reporter_id: int, engineer_ids: set[int]) -> list[str]:
    """List the statuses this user can move the ticket to right now (used to show only valid buttons)."""
    return [
        target
        for (current, target), rule in WORKFLOW.items()
        if current == status and is_permitted(rule, user, reporter_id, engineer_ids)
    ]


def is_site_alert(priority: str, status: str, is_archived: bool) -> bool:
    """An active critical incident affects the whole site, so everyone may see it (read-only)."""
    return priority == "critical" and status in ACTIVE_STATUSES and not is_archived


def can_view(user: dict, reporter_id: int, engineer_ids: set[int], is_archived: bool = False,
             site_alert: bool = False) -> bool:
    """
    Visibility (DESIGN.md section 6):
    - everyone sees active critical incidents (site alerts), read-only unless
      they have another role on the ticket;
    - employees otherwise see only tickets they reported (anything else is a
      404, so they can't find out what exists);
    - engineers see every active ticket read-only, because helping each other is
      a core requirement, plus archived tickets they reported or worked on;
    - admins see everything.
    Voided tickets are hidden from non-admins by the service layer.
    """
    if user["role"] == "admin" or user["id"] == reporter_id or site_alert:
        return True
    if user["role"] == "engineer":
        return user["id"] in engineer_ids or not is_archived
    return False


def can_add_note(user: dict, engineer_ids: set[int]) -> bool:
    """
    An admin or an engineer on the ticket may add notes (for example a repair
    note). Reporters don't add notes after reporting; engineers who can only
    see the ticket must join it first (otherwise 403).
    """
    return user["role"] == "admin" or user["id"] in engineer_ids


def can_edit_details(user: dict, reporter_id: int, status: str, has_pending: bool) -> bool:
    """
    Admins may always edit a ticket's title and description. The reporter may
    only while it is still open (no engineer has started) and nothing is
    waiting for an admin's approval.
    """
    if user["role"] == "admin":
        return True
    return user["id"] == reporter_id and status == "open" and not has_pending


# ---------- step 6: join, acknowledge, priority, requests, void, work logs ----------

ACTIVE_STATUSES = ("open", "in_progress", "blocked")
REOPENABLE_STATUSES = ("resolved", "closed")

# Work logs: quarter-hour steps from 15 minutes to 12 hours.
HOURS_STEP = 0.25
HOURS_MIN = 0.25
HOURS_MAX = 12
DAY_HOURS_MAX = 12  # one engineer, one day, all tickets together


def can_join(user: dict, engineer_ids: set[int]) -> bool:
    """Any engineer may join a ticket they are not already on."""
    return user["role"] == "engineer" and user["id"] not in engineer_ids


def can_acknowledge(user: dict, status: str, engineer_ids: set[int]) -> bool:
    """An engineer on the ticket may commit to it for their shift while it is still active."""
    return user["role"] == "engineer" and user["id"] in engineer_ids and status in ACTIVE_STATUSES


def can_change_priority(user: dict, engineer_ids: set[int]) -> bool:
    """
    An admin or an engineer on the ticket may change its priority, to any level.
    (Reporting a new ticket as critical is still admin-only: can_report_priority.)
    """
    return user["role"] == "admin" or (user["role"] == "engineer" and user["id"] in engineer_ids)


def can_report_priority(user: dict, priority: str) -> bool:
    """Critical incidents are shown to everyone on site, so only admins may report one as critical."""
    return priority != "critical" or user["role"] == "admin"


def can_request_reopen(user: dict, status: str, reporter_id: int, has_pending: bool = False) -> bool:
    """
    The reporter (or an admin) may ask to reopen a resolved or closed ticket.
    The reporter can't while another request is waiting for an admin.
    """
    if status not in REOPENABLE_STATUSES:
        return False
    if user["role"] == "admin":
        return True
    return user["id"] == reporter_id and not has_pending


def can_decide_requests(user: dict) -> bool:
    """Only admins approve or reject close and reopen requests."""
    return user["role"] == "admin"


def can_assign(user: dict, status: str) -> bool:
    """Only admins assign or reassign the primary engineer, while the ticket is active."""
    return user["role"] == "admin" and status in ACTIVE_STATUSES


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
    # NaN fails every comparison, so it gets past the range check; catch it here.
    if not math.isfinite(hours):
        return "Must be a number"
    if round(hours / HOURS_STEP) * HOURS_STEP != hours:
        return f"Must be in steps of {HOURS_STEP} hours (15 minutes)"
    return None


def day_total_error(logged_that_day: float, hours: float) -> str | None:
    """Return why adding `hours` would take one engineer's day past DAY_HOURS_MAX across all tickets, or None."""
    if logged_that_day + hours > DAY_HOURS_MAX:
        left = max(DAY_HOURS_MAX - logged_that_day, 0)
        return (f"You already have {logged_that_day:g} hours logged on this day across your tickets; "
                f"the limit is {DAY_HOURS_MAX} a day, so at most {left:g} more")
    return None


def recurring_level(seat_count: int, floor_count: int, floor_seats: int, threshold: int) -> str | None:
    """
    Decide whether incidents of one issue type form a recurring pattern (DESIGN.md section 6).

    Args:
        seat_count: incidents of this issue type at the same seat in the window.
        floor_count: incidents of this issue type anywhere on the same floor in the window.
        floor_seats: how many different seats those floor incidents are at.
        threshold: RECURRING_THRESHOLD (3).

    Returns:
        "seat" if the seat alone reaches the threshold, "floor" if the floor does
        across more than one seat (the dashboard uses the same split), else None.
    """
    if seat_count >= threshold:
        return "seat"
    if floor_count >= threshold and floor_seats > 1:
        return "floor"
    return None
