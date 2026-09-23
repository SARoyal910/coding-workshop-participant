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


def can_view(user: dict, reporter_id: int, engineer_ids: set[int]) -> bool:
    """
    Visibility (DESIGN.md section 6):
    everyone -> tickets they reported; engineer -> also tickets they're on plus the
    unassigned pool; admin -> all.
    """
    if user["role"] == "admin" or user["id"] == reporter_id:
        return True
    if user["role"] == "engineer":
        return user["id"] in engineer_ids or not engineer_ids
    return False


def can_edit_details(user: dict, reporter_id: int) -> bool:
    """Only the reporter or an admin may edit a ticket's title and description."""
    return user["role"] == "admin" or user["id"] == reporter_id
