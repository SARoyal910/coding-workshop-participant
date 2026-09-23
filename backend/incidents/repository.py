"""
Incidents service data access. SQL only, always parameterized.

The service layer decides transaction boundaries with `transaction()`; every
function here runs on the same shared connection, so calls made inside a
`with transaction():` block commit or roll back together.
"""

from typing import Any

from psycopg import sql

from _shared import db
from _shared.db import transaction  # noqa: F401  (re-exported for service.py)

# Columns shown in lists, plus names for the location, reporter and primary engineer.
LIST_SELECT = """
    SELECT i.id, i.title, i.category, i.issue_type, i.priority, i.status,
           i.created_at, i.updated_at, i.is_archived, i.version,
           b.name AS building_name, f.number AS floor_number, s.code AS seat_code,
           r.name AS reporter_name,
           (SELECT u.name FROM incident_engineers ie JOIN users u ON u.id = ie.engineer_id
             WHERE ie.incident_id = i.id AND ie.role = 'primary') AS primary_engineer_name,
           count(*) OVER () AS total
      FROM incidents i
      JOIN buildings b ON b.id = i.building_id
      JOIN floors f ON f.id = i.floor_id
      LEFT JOIN seats s ON s.id = i.seat_id
      JOIN users r ON r.id = i.reporter_id
"""

ON_TICKET = "EXISTS (SELECT 1 FROM incident_engineers ie WHERE ie.incident_id = i.id AND ie.engineer_id = %s)"
UNASSIGNED = "NOT EXISTS (SELECT 1 FROM incident_engineers ie WHERE ie.incident_id = i.id)"


def list_incidents(user: dict, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]:
    """
    Return one page of incidents the user may see, newest first, and the total count.

    Only fixed SQL fragments are combined; every value is passed as a parameter.
    """
    conditions = [sql.SQL("NOT i.is_voided"), sql.SQL("i.is_archived = %s")]
    params: list[Any] = [filters.get("archived", False)]

    # Visibility (see rules.can_view).
    if user["role"] == "engineer":
        conditions.append(sql.SQL(f"(i.reporter_id = %s OR {ON_TICKET} OR {UNASSIGNED})"))
        params += [user["id"], user["id"]]
    elif user["role"] != "admin":
        conditions.append(sql.SQL("i.reporter_id = %s"))
        params.append(user["id"])

    if filters.get("scope") == "mine":
        conditions.append(sql.SQL(ON_TICKET))
        params.append(user["id"])
    elif filters.get("scope") == "pool":
        conditions.append(sql.SQL(UNASSIGNED))
    for column in ("status", "priority", "category", "building_id"):
        if filters.get(column) is not None:
            conditions.append(sql.SQL("{} = %s").format(sql.Identifier("i", column)))
            params.append(filters[column])
    if filters.get("q"):
        conditions.append(sql.SQL("(i.title ILIKE %s OR i.description ILIKE %s)"))
        params += [f"%{filters['q']}%"] * 2

    query = sql.SQL(LIST_SELECT + " WHERE {} ORDER BY i.created_at DESC, i.id DESC LIMIT %s OFFSET %s").format(
        sql.SQL(" AND ").join(conditions)
    )
    rows = db.fetch_all(query, (*params, page_size, (page - 1) * page_size))
    total = rows[0]["total"] if rows else 0
    for row in rows:
        del row["total"]
    return rows, total


def get_incident(incident_id: int) -> dict | None:
    """Return one incident with location and reporter names, or None."""
    return db.fetch_one(
        "SELECT i.*, b.name AS building_name, f.number AS floor_number, s.code AS seat_code,"
        "       r.name AS reporter_name"
        "  FROM incidents i"
        "  JOIN buildings b ON b.id = i.building_id"
        "  JOIN floors f ON f.id = i.floor_id"
        "  LEFT JOIN seats s ON s.id = i.seat_id"
        "  JOIN users r ON r.id = i.reporter_id"
        " WHERE i.id = %s",
        (incident_id,),
    )


def get_engineers(incident_id: int) -> list[dict]:
    """Return the engineers on a ticket, primary first."""
    return db.fetch_all(
        "SELECT u.id, u.name, ie.role, ie.added_at FROM incident_engineers ie"
        "  JOIN users u ON u.id = ie.engineer_id"
        " WHERE ie.incident_id = %s ORDER BY ie.role = 'primary' DESC, ie.added_at",
        (incident_id,),
    )


def get_notes(incident_id: int) -> list[dict]:
    """Return a ticket's notes, oldest first, with each author's name and role."""
    return db.fetch_all(
        "SELECT n.id, n.body, n.created_at, n.edited_at, n.author_id,"
        "       u.name AS author_name, u.role AS author_role"
        "  FROM incident_notes n JOIN users u ON u.id = n.author_id"
        " WHERE n.incident_id = %s ORDER BY n.created_at, n.id",
        (incident_id,),
    )


def get_events(incident_id: int) -> list[dict]:
    """Return a ticket's audit history, oldest first, with each actor's name."""
    return db.fetch_all(
        "SELECT e.id, e.type, e.from_value, e.to_value, e.reason, e.created_at,"
        "       e.actor_id, u.name AS actor_name"
        "  FROM incident_events e JOIN users u ON u.id = e.actor_id"
        " WHERE e.incident_id = %s ORDER BY e.created_at, e.id",
        (incident_id,),
    )


def floor_in_building(floor_id: int, building_id: int) -> bool:
    """Return True if the floor exists and belongs to the building."""
    return db.fetch_one(
        "SELECT 1 AS ok FROM floors WHERE id = %s AND building_id = %s", (floor_id, building_id)
    ) is not None


def seat_on_floor(seat_id: int, floor_id: int) -> bool:
    """Return True if the seat exists and is on the floor."""
    return db.fetch_one(
        "SELECT 1 AS ok FROM seats WHERE id = %s AND floor_id = %s", (seat_id, floor_id)
    ) is not None


def create_incident(fields: dict, reporter_id: int) -> int:
    """Insert a new open incident and return its id."""
    row = db.fetch_one(
        "INSERT INTO incidents (title, description, category, issue_type, priority,"
        "                       reporter_id, building_id, floor_id, seat_id)"
        " VALUES (%(title)s, %(description)s, %(category)s, %(issue_type)s, %(priority)s,"
        "         %(reporter_id)s, %(building_id)s, %(floor_id)s, %(seat_id)s)"
        " RETURNING id",
        {**fields, "reporter_id": reporter_id},
    )
    return row["id"]


def update_details(incident_id: int, version: int, changes: dict[str, str]) -> bool:
    """
    Update title and/or description if the version still matches (optimistic locking).

    Returns:
        False if someone else changed the ticket first (version mismatch).
    """
    assignments = [sql.SQL("{} = %s").format(sql.Identifier(column)) for column in changes]
    query = sql.SQL(
        "UPDATE incidents SET {}, updated_at = now(), version = version + 1 WHERE id = %s AND version = %s"
    ).format(sql.SQL(", ").join(assignments))
    return db.execute(query, (*changes.values(), incident_id, version)) == 1


def update_status(incident_id: int, version: int, status: str, blocked_reason: str | None) -> bool:
    """
    Change status if the version still matches (optimistic locking).
    Sets resolved_at / closed_at when the ticket reaches those statuses.

    Returns:
        False if someone else changed the ticket first (version mismatch).
    """
    return db.execute(
        "UPDATE incidents"
        "   SET status = %(status)s,"
        "       blocked_reason = %(blocked_reason)s,"
        "       resolved_at = CASE WHEN %(status)s = 'resolved' THEN now() ELSE resolved_at END,"
        "       closed_at = CASE WHEN %(status)s = 'closed' THEN now() ELSE closed_at END,"
        "       updated_at = now(),"
        "       version = version + 1"
        " WHERE id = %(id)s AND version = %(version)s",
        {"status": status, "blocked_reason": blocked_reason, "id": incident_id, "version": version},
    ) == 1


def touch(incident_id: int) -> None:
    """Bump updated_at without changing the version (used when a note is added)."""
    db.execute("UPDATE incidents SET updated_at = now() WHERE id = %s", (incident_id,))


def add_event(incident_id: int, actor_id: int, event_type: str, from_value: str | None = None,
              to_value: str | None = None, reason: str | None = None) -> None:
    """Append one row to the audit log."""
    db.execute(
        "INSERT INTO incident_events (incident_id, actor_id, type, from_value, to_value, reason)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        (incident_id, actor_id, event_type, from_value, to_value, reason),
    )


def add_note(incident_id: int, author_id: int, body: str) -> dict:
    """Insert a note and return it."""
    return db.fetch_one(
        "INSERT INTO incident_notes (incident_id, author_id, body) VALUES (%s, %s, %s)"
        " RETURNING id, body, created_at, edited_at, author_id",
        (incident_id, author_id, body),
    )


def get_note(incident_id: int, note_id: int) -> dict | None:
    """Return a note if it belongs to this incident, or None."""
    return db.fetch_one(
        "SELECT id, body, created_at, edited_at, author_id FROM incident_notes"
        " WHERE id = %s AND incident_id = %s",
        (note_id, incident_id),
    )


def update_note(note_id: int, body: str) -> dict:
    """Replace a note's text, set edited_at and return the note."""
    return db.fetch_one(
        "UPDATE incident_notes SET body = %s, edited_at = now() WHERE id = %s"
        " RETURNING id, body, created_at, edited_at, author_id",
        (body, note_id),
    )


def create_close_request(incident_id: int, requested_by: int) -> bool:
    """
    Create a pending close-approval request.

    Returns:
        False if one is already pending (the partial unique index prevents duplicates).
    """
    return db.execute(
        "INSERT INTO incident_requests (incident_id, type, requested_by) VALUES (%s, 'close_approval', %s)"
        " ON CONFLICT (incident_id, type) WHERE status = 'pending' DO NOTHING",
        (incident_id, requested_by),
    ) == 1


def list_locations() -> list[dict]:
    """Return every seat position as flat rows: building, floor and (optional) seat."""
    return db.fetch_all(
        "SELECT b.id AS building_id, b.name AS building_name, f.id AS floor_id, f.number AS floor_number,"
        "       s.id AS seat_id, s.code AS seat_code"
        "  FROM buildings b"
        "  JOIN floors f ON f.building_id = b.id"
        "  LEFT JOIN seats s ON s.floor_id = f.id"
        " ORDER BY b.name, f.number, s.code"
    )
