"""
Dashboard business logic: which metrics each role sees. No SQL, no HTTP.

The admin dashboard answers the seven business questions (DESIGN.md section 7).
Engineers and employees get a short summary of their own work.
"""

import repository
from _shared.constants import (
    METRICS_WINDOW_DAYS,
    RECURRING_THRESHOLD,
    RECURRING_WINDOW_DAYS,
    STATUSES,
)


def _percent(part: int, whole: int) -> int | None:
    """Whole-number percentage, or None when there is nothing to divide by."""
    return round(100 * part / whole) if whole else None


def _status_counts(rows: list[dict]) -> dict[str, int]:
    """Turn GROUP BY rows into {status: count}, with 0 for statuses that have none."""
    counts = {status: 0 for status in STATUSES}
    counts.update({row["status"]: row["count"] for row in rows})
    return counts


def admin_dashboard() -> dict:
    """Everything a supervisor needs, grouped by business question."""
    issue_types = repository.issue_types(METRICS_WINDOW_DAYS)
    categories: dict[str, int] = {}
    for row in issue_types:
        categories[row["category"]] = categories.get(row["category"], 0) + row["count"]

    engineers = repository.engineer_workload(METRICS_WINDOW_DAYS)
    for engineer in engineers:
        # 13.4: an unavailable engineer who is still primary on active tickets needs cover.
        engineer["needs_reassignment"] = not engineer["is_available"] and engineer["active_primary"] > 0

    comms = repository.communication(METRICS_WINDOW_DAYS)
    pending = {row["type"]: row["count"] for row in repository.pending_requests()}

    return {
        "role": "admin",
        "window_days": METRICS_WINDOW_DAYS,
        # 1. What is open, and what is its status?
        "status_counts": _status_counts(repository.status_counts()),
        # 2. Where do issues keep coming back?
        "recurring": {
            "threshold": RECURRING_THRESHOLD,
            "window_days": RECURRING_WINDOW_DAYS,
            "seats": repository.recurring_seats(RECURRING_WINDOW_DAYS, RECURRING_THRESHOLD),
            "floors": repository.recurring_floors(RECURRING_WINDOW_DAYS, RECURRING_THRESHOLD),
            "buildings": repository.building_hotspots(RECURRING_WINDOW_DAYS),
        },
        # 3. How fast are incidents acknowledged, assigned and resolved?
        "response_times": repository.response_times(METRICS_WINDOW_DAYS),
        # 4. Who is available, and how is work spread?
        "engineers": engineers,
        # 5. What are the most common issues?
        "categories": [{"category": name, "count": count} for name, count in categories.items()],
        "issue_types": issue_types,
        # 6. What is escalated or blocked, and why?
        "needs_attention": {
            "blocked": repository.blocked_incidents(),
            "escalated": repository.escalated_by_reporters(),
        },
        # 7. Are employees kept informed?
        "communication": {
            "first_update_hours": comms["first_update_hours"],
            "resolved": comms["resolved"],
            "resolved_with_note_pct": _percent(comms["resolved_with_note"], comms["resolved"]),
            "reopen_rate_pct": _percent(comms["reopen_requested"], comms["resolved"]),
        },
        "pending_requests": {
            "close_approval": pending.get("close_approval", 0),
            "reopen": pending.get("reopen", 0),
        },
    }


def engineer_dashboard(user: dict) -> dict:
    """An engineer's own workload, the unassigned pool, and their shift record."""
    workload = repository.engineer_workload(METRICS_WINDOW_DAYS, engineer_id=user["id"])
    return {
        "role": "engineer",
        "window_days": METRICS_WINDOW_DAYS,
        "status_counts": _status_counts(repository.status_counts(engineer_id=user["id"])),
        "unassigned_pool": repository.unassigned_pool_count(),
        "me": workload[0] if workload else None,
    }


def employee_dashboard(user: dict) -> dict:
    """The employee's own tickets, and how many are waiting for them to confirm."""
    return {
        "role": "employee",
        "status_counts": _status_counts(repository.status_counts(user_id=user["id"])),
        "awaiting_your_confirmation": repository.awaiting_reporter_count(user["id"]),
    }


def get_dashboard(user: dict) -> dict:
    """Return the dashboard for the user's role."""
    if user["role"] == "admin":
        return admin_dashboard()
    if user["role"] == "engineer":
        return engineer_dashboard(user)
    return employee_dashboard(user)
