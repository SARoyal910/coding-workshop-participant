"""
Engineer workload and shift statistics, used by the dashboard and engineers services.

This is the one query shared between services, so "missed shift commitment"
is defined in exactly one place (DESIGN.md section 6). Like a repository, it is
SQL only and fully parameterized.
"""

from _shared import db


def engineer_workload(days: int, engineer_id: int | None = None,
                      limit: int | None = None, offset: int = 0) -> list[dict]:
    """
    Per engineer: profile, availability, active tickets as primary/helper, tickets
    helped on, hours logged in the last `days` days, and missed shift commitments.

    A missed shift commitment: the acknowledged shift is over, the ticket was not
    resolved by then, and it was not moved to blocked during the shift.

    Args:
        engineer_id: Only this engineer (None = all engineers).
        limit, offset: One page of engineers (limit None = no limit).

    Returns:
        Rows ordered by most active primary tickets; each has "total", the number
        of engineers matched before paging.
    """
    return db.fetch_all(
        "SELECT u.id, u.name, u.email, p.specialty, p.shift, p.is_available, p.phone,"
        "       count(*) FILTER (WHERE ie.role = 'primary' AND i.status IN ('open', 'in_progress', 'blocked')"
        "                        AND NOT i.is_voided AND NOT i.is_archived) AS active_primary,"
        "       count(*) FILTER (WHERE ie.role = 'helper' AND i.status IN ('open', 'in_progress', 'blocked')"
        "                        AND NOT i.is_voided AND NOT i.is_archived) AS active_helper,"
        "       count(*) FILTER (WHERE ie.role = 'helper' AND NOT i.is_voided) AS helped_others,"
        "       (SELECT coalesce(sum(w.hours), 0) FROM incident_work_logs w"
        "         WHERE w.engineer_id = u.id AND w.work_date >= current_date - %(days)s) AS hours_logged,"
        "       (SELECT count(*) FROM incident_acks a JOIN incidents ai ON ai.id = a.incident_id"
        "         WHERE a.engineer_id = u.id AND NOT ai.is_voided"
        "           AND a.shift_ends_at < now()"
        "           AND (ai.resolved_at IS NULL OR ai.resolved_at > a.shift_ends_at)"
        "           AND NOT EXISTS (SELECT 1 FROM incident_events e"
        "                WHERE e.incident_id = ai.id AND e.type = 'status_changed' AND e.to_value = 'blocked'"
        "                  AND e.created_at BETWEEN a.acknowledged_at AND a.shift_ends_at)"
        "       ) AS missed_shifts,"
        "       count(*) OVER () AS total"
        "  FROM users u"
        "  JOIN engineer_profiles p ON p.user_id = u.id"
        "  LEFT JOIN incident_engineers ie ON ie.engineer_id = u.id"
        "  LEFT JOIN incidents i ON i.id = ie.incident_id"
        " WHERE u.role = 'engineer' AND (%(engineer_id)s::int IS NULL OR u.id = %(engineer_id)s)"
        " GROUP BY u.id, u.name, u.email, p.specialty, p.shift, p.is_available, p.phone"
        " ORDER BY active_primary DESC, u.name"
        " LIMIT %(limit)s OFFSET %(offset)s",
        {"days": days, "engineer_id": engineer_id, "limit": limit, "offset": offset},
    )
