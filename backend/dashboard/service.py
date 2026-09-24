"""
Dashboard business logic: which metrics each role sees. No SQL, no HTTP.

The admin dashboard answers the seven business questions (DESIGN.md section 7).
Engineers and employees get a short summary of their own work.
"""

from datetime import datetime, timezone

import repository
from _shared.constants import (
    METRICS_WINDOW_DAYS,
    RECURRING_THRESHOLD,
    RECURRING_WINDOW_DAYS,
    SHIFTS,
    STATUSES,
)
from _shared.errors import Forbidden, NotFound
from _shared.shifts import is_on_shift
from _shared.validation import get_int, raise_if_errors, reject_unknown_fields

MISSED_PARAMS = {"engineer_id"}


def _percent(part: int, whole: int) -> int | None:
    """Whole-number percentage, or None when there is nothing to divide by."""
    return round(100 * part / whole) if whole else None


def _status_counts(rows: list[dict]) -> dict[str, int]:
    """Turn GROUP BY rows into {status: count}, with 0 for statuses that have none."""
    counts = {status: 0 for status in STATUSES}
    counts.update({row["status"]: row["count"] for row in rows})
    return counts


def _shift_coverage(engineers: list[dict]) -> list[dict]:
    """Per shift: how many engineers work it, how many are available, and whether it is running now."""
    coverage = []
    for shift in SHIFTS:
        on_shift = [engineer for engineer in engineers if engineer["shift"] == shift]
        coverage.append({
            "shift": shift,
            "engineers": len(on_shift),
            "available": sum(1 for engineer in on_shift if engineer["is_available"]),
            "active_primary": sum(engineer["active_primary"] for engineer in on_shift),
            "missed_shifts": sum(engineer["missed_shifts"] for engineer in on_shift),
            "is_current": any(engineer["on_shift_now"] for engineer in on_shift),
        })
    return coverage


def admin_dashboard() -> dict:
    """Everything a supervisor needs, grouped by business question."""
    issue_types = repository.issue_types(METRICS_WINDOW_DAYS)
    categories: dict[str, int] = {}
    for row in issue_types:
        categories[row["category"]] = categories.get(row["category"], 0) + row["count"]

    engineers = repository.engineer_workload(METRICS_WINDOW_DAYS)
    now = datetime.now(timezone.utc)
    for engineer in engineers:
        del engineer["total"]  # paging count, not needed here
        engineer["on_shift_now"] = is_on_shift(engineer["shift"], now)
        # 13.4: an unavailable engineer who is still primary on active tickets needs cover.
        engineer["needs_reassignment"] = not engineer["is_available"] and engineer["active_primary"] > 0

    comms = repository.communication(METRICS_WINDOW_DAYS)
    pending = {row["type"]: row["count"] for row in repository.pending_requests()}

    return {
        "role": "admin",
        "window_days": METRICS_WINDOW_DAYS,
        # 1. What is open, and what is its status?
        "status_counts": _status_counts(repository.status_counts()),
        "totals": repository.incident_totals(),
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
        "shift_coverage": _shift_coverage(engineers),
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
    for row in workload:
        del row["total"]
        row["on_shift_now"] = is_on_shift(row["shift"], datetime.now(timezone.utc))
    return {
        "role": "engineer",
        "window_days": METRICS_WINDOW_DAYS,
        "status_counts": _status_counts(repository.status_counts(engineer_id=user["id"])),
        "totals": repository.incident_totals(engineer_id=user["id"]),
        "unassigned_pool": repository.unassigned_pool_count(),
        "me": workload[0] if workload else None,
    }


def employee_dashboard(user: dict) -> dict:
    """The employee's own tickets by status."""
    return {
        "role": "employee",
        "status_counts": _status_counts(repository.status_counts(user_id=user["id"])),
        "totals": repository.incident_totals(user_id=user["id"]),
    }


def missed_shifts(user: dict, params: dict) -> dict:
    """
    The missed shift commitments behind the dashboard counts, one row each with
    the ticket and the shift. Admins see everyone (or one engineer with
    engineer_id); engineers see their own.

    Raises:
        Forbidden: an employee, or an engineer asking about someone else.
        NotFound: engineer_id is not an engineer.
    """
    if user["role"] not in ("admin", "engineer"):
        raise Forbidden("Only engineers and admins can see missed shift commitments")
    errors: dict[str, str] = {}
    reject_unknown_fields(params, MISSED_PARAMS, errors)
    engineer_id = get_int(params, "engineer_id", errors, required=False)
    raise_if_errors(errors)
    if user["role"] == "engineer":
        if engineer_id not in (None, user["id"]):
            raise Forbidden("Engineers can only see their own missed shift commitments")
        engineer_id = user["id"]

    engineer = None
    if engineer_id is not None:
        rows = repository.engineer_workload(METRICS_WINDOW_DAYS, engineer_id=engineer_id)
        if not rows:
            raise NotFound("Engineer not found")
        engineer = {"id": engineer_id, "name": rows[0]["name"]}
    items = repository.missed_commitments(engineer_id)
    return {"engineer": engineer, "total": len(items), "items": items}


def get_dashboard(user: dict) -> dict:
    """Return the dashboard for the user's role."""
    if user["role"] == "admin":
        return admin_dashboard()
    if user["role"] == "engineer":
        return engineer_dashboard(user)
    return employee_dashboard(user)
