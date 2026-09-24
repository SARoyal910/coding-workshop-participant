"""
Dashboard data access. Every metric is aggregated in SQL (GROUP BY / FILTER),
never by loading rows into Python (DESIGN.md 13.5). Voided incidents are
excluded everywhere; archived ones only count toward historical metrics.
"""

from _shared import db
from _shared.engineer_stats import engineer_workload  # noqa: F401  (re-exported for service.py)

# Conditions repeated in the queries below (kept as literal SQL so no query is
# ever built from strings):
#   active:    NOT i.is_voided AND NOT i.is_archived
#   in window: NOT i.is_voided AND i.created_at >= now() - make_interval(days => %(days)s)
# A missed shift commitment: the shift is over, the ticket was not resolved by
# then, and it was not moved to blocked during the shift.


def status_counts(user_id: int | None = None, engineer_id: int | None = None) -> list[dict]:
    """Active incidents per status, optionally only one reporter's or one engineer's."""
    return db.fetch_all(
        "SELECT i.status, count(*) AS count FROM incidents i WHERE NOT i.is_voided AND NOT i.is_archived"
        "   AND (%(user_id)s::int IS NULL OR i.reporter_id = %(user_id)s)"
        "   AND (%(engineer_id)s::int IS NULL OR EXISTS (SELECT 1 FROM incident_engineers ie"
        "        WHERE ie.incident_id = i.id AND ie.engineer_id = %(engineer_id)s))"
        " GROUP BY i.status",
        {"user_id": user_id, "engineer_id": engineer_id},
    )


def incident_totals(user_id: int | None = None, engineer_id: int | None = None) -> dict:
    """
    Every incident ever reported, in one pass: total (not voided), split into
    active and archived, plus voided separately (errors, so not in the total).
    Optionally only one reporter's or one engineer's.
    """
    return db.fetch_one(
        "SELECT count(*) FILTER (WHERE NOT i.is_voided) AS total,"
        "       count(*) FILTER (WHERE NOT i.is_voided AND NOT i.is_archived) AS active,"
        "       count(*) FILTER (WHERE NOT i.is_voided AND i.is_archived) AS archived,"
        "       count(*) FILTER (WHERE i.is_voided) AS voided"
        "  FROM incidents i"
        " WHERE (%(user_id)s::int IS NULL OR i.reporter_id = %(user_id)s)"
        "   AND (%(engineer_id)s::int IS NULL OR EXISTS (SELECT 1 FROM incident_engineers ie"
        "        WHERE ie.incident_id = i.id AND ie.engineer_id = %(engineer_id)s))",
        {"user_id": user_id, "engineer_id": engineer_id},
    )


def response_times(days: int) -> dict:
    """Average hours from report to acknowledge / assign / resolve, for incidents reported in the window."""
    return db.fetch_one(
        "SELECT round(avg(extract(epoch FROM i.acknowledged_at - i.created_at)) / 3600, 1) AS acknowledge_hours,"
        "       round(avg(extract(epoch FROM i.assigned_at - i.created_at)) / 3600, 1) AS assign_hours,"
        "       round(avg(extract(epoch FROM i.resolved_at - i.created_at)) / 3600, 1) AS resolve_hours,"
        "       count(*) AS reported,"
        "       count(i.resolved_at) AS resolved"
        "  FROM incidents i WHERE NOT i.is_voided AND i.created_at >= now() - make_interval(days => %(days)s)",
        {"days": days},
    )


def issue_types(days: int) -> list[dict]:
    """Incident count and average logged hours per category and issue type, most common first."""
    return db.fetch_all(
        "SELECT i.category, i.issue_type, count(*) AS count,"
        "       round(avg(coalesce(w.hours, 0)), 2) AS avg_hours"
        "  FROM incidents i"
        "  LEFT JOIN (SELECT incident_id, sum(hours) AS hours FROM incident_work_logs GROUP BY incident_id) w"
        "    ON w.incident_id = i.id"
        " WHERE NOT i.is_voided AND i.created_at >= now() - make_interval(days => %(days)s)"
        " GROUP BY i.category, i.issue_type ORDER BY count DESC, i.issue_type",
        {"days": days},
    )


def recurring_seats(days: int, threshold: int) -> list[dict]:
    """Seats with at least `threshold` incidents of the same issue type in the window."""
    return db.fetch_all(
        "SELECT b.name AS building_name, f.number AS floor_number, s.code AS seat_code,"
        "       i.issue_type, count(*) AS count, max(i.created_at) AS last_reported_at"
        "  FROM incidents i"
        "  JOIN seats s ON s.id = i.seat_id"
        "  JOIN floors f ON f.id = i.floor_id"
        "  JOIN buildings b ON b.id = i.building_id"
        " WHERE NOT i.is_voided AND i.created_at >= now() - make_interval(days => %(days)s)"
        " GROUP BY b.name, f.number, s.code, i.issue_type"
        " HAVING count(*) >= %(threshold)s ORDER BY count DESC",
        {"days": days, "threshold": threshold},
    )


def recurring_floors(days: int, threshold: int) -> list[dict]:
    """
    Floors with at least `threshold` incidents of the same issue type in the window,
    spread over more than one seat (a single-seat pattern is already in recurring_seats).
    """
    return db.fetch_all(
        "SELECT b.name AS building_name, f.number AS floor_number, i.issue_type,"
        "       count(*) AS count, count(DISTINCT i.seat_id) AS seats, max(i.created_at) AS last_reported_at"
        "  FROM incidents i"
        "  JOIN floors f ON f.id = i.floor_id"
        "  JOIN buildings b ON b.id = i.building_id"
        " WHERE NOT i.is_voided AND i.created_at >= now() - make_interval(days => %(days)s)"
        " GROUP BY b.name, f.number, i.issue_type"
        " HAVING count(*) >= %(threshold)s AND count(DISTINCT i.seat_id) > 1 ORDER BY count DESC",
        {"days": days, "threshold": threshold},
    )


def building_hotspots(days: int) -> list[dict]:
    """Incident counts per building in the window, busiest first."""
    return db.fetch_all(
        "SELECT b.name AS building_name, count(*) AS count,"
        "       count(*) FILTER (WHERE i.status IN ('open', 'in_progress', 'blocked') AND NOT i.is_archived) AS active"
        "  FROM incidents i JOIN buildings b ON b.id = i.building_id"
        " WHERE NOT i.is_voided AND i.created_at >= now() - make_interval(days => %(days)s)"
        " GROUP BY b.name ORDER BY count DESC",
        {"days": days},
    )


def blocked_incidents() -> list[dict]:
    """Active blocked incidents with the reason and when they were blocked, most urgent first."""
    return db.fetch_all(
        "SELECT i.id, i.title, i.priority, i.blocked_reason, b.name AS building_name,"
        "       (SELECT max(e.created_at) FROM incident_events e WHERE e.incident_id = i.id"
        "          AND e.type = 'status_changed' AND e.to_value = 'blocked') AS blocked_at"
        "  FROM incidents i JOIN buildings b ON b.id = i.building_id"
        " WHERE NOT i.is_voided AND NOT i.is_archived AND i.status = 'blocked'"
        " ORDER BY array_position(ARRAY['critical', 'high', 'medium', 'low'], i.priority), blocked_at",
    )


def escalated_by_reporters() -> list[dict]:
    """Active incidents whose reporter raised the priority, with their reason."""
    return db.fetch_all(
        "SELECT DISTINCT ON (i.id) i.id, i.title, i.status, e.from_value, e.to_value, e.reason, e.created_at"
        "  FROM incident_events e JOIN incidents i ON i.id = e.incident_id"
        " WHERE NOT i.is_voided AND NOT i.is_archived AND e.type = 'priority_changed' AND e.actor_id = i.reporter_id"
        "   AND array_position(ARRAY['low', 'medium', 'high', 'critical'], e.to_value)"
        "     > array_position(ARRAY['low', 'medium', 'high', 'critical'], e.from_value)"
        " ORDER BY i.id, e.created_at DESC",
    )


def communication(days: int) -> dict:
    """
    How well reporters are kept informed, for incidents reported in the window:
    hours until the first engineer/admin note, share of resolved tickets with an
    engineer/admin note, and the share of resolved tickets that were asked to be reopened.
    """
    return db.fetch_one(
        "WITH window_incidents AS ("
        "  SELECT i.id, i.created_at, i.resolved_at FROM incidents i WHERE NOT i.is_voided AND i.created_at >= now() - make_interval(days => %(days)s)"
        "), first_notes AS ("
        "  SELECT w.id, w.resolved_at, min(n.created_at) - w.created_at AS wait"
        "    FROM window_incidents w"
        "    JOIN incident_notes n ON n.incident_id = w.id"
        "    JOIN users u ON u.id = n.author_id AND u.role IN ('engineer', 'admin')"
        "   GROUP BY w.id, w.created_at, w.resolved_at"
        ")"
        " SELECT round(avg(extract(epoch FROM f.wait)) / 3600, 1) AS first_update_hours,"
        "        (SELECT count(*) FROM window_incidents WHERE resolved_at IS NOT NULL) AS resolved,"
        "        count(*) FILTER (WHERE f.resolved_at IS NOT NULL) AS resolved_with_note,"
        "        (SELECT count(DISTINCT r.incident_id) FROM incident_requests r"
        "          JOIN window_incidents w ON w.id = r.incident_id WHERE r.type = 'reopen') AS reopen_requested"
        "   FROM first_notes f",
        {"days": days},
    )


def pending_requests() -> list[dict]:
    """Number of pending requests per type (close approvals and reopen requests)."""
    return db.fetch_all(
        "SELECT r.type, count(*) AS count FROM incident_requests r"
        "  JOIN incidents i ON i.id = r.incident_id"
        " WHERE r.status = 'pending' AND NOT i.is_voided GROUP BY r.type",
    )


def unassigned_pool_count() -> int:
    """Active incidents nobody has joined yet."""
    row = db.fetch_one(
        "SELECT count(*) AS count FROM incidents i WHERE NOT i.is_voided AND NOT i.is_archived"
        "   AND NOT EXISTS (SELECT 1 FROM incident_engineers ie WHERE ie.incident_id = i.id)",
    )
    return row["count"]
