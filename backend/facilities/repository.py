"""
Facilities service data access: buildings, floors and seats. SQL only, always parameterized.

Names are unique (building name, floor number per building, seat code per
floor). Inserts use ON CONFLICT DO NOTHING and updates catch the unique
violation, so both return None for a duplicate instead of raising.
"""

import psycopg

from _shared import db

# Every read returns incident_count: how many incidents (any status, including
# voided) point at the place. A place with incidents can't be deleted, because
# the incident keeps its location.


# ---------- buildings ----------

def list_buildings(page: int, page_size: int) -> tuple[list[dict], int]:
    """Return one page of buildings, by name, and the total number of buildings."""
    rows = db.fetch_all(
        "SELECT b.id, b.name, b.address,"
        "       (SELECT count(*) FROM incidents i WHERE i.building_id = b.id) AS incident_count,"
        "       count(*) OVER () AS total"
        "  FROM buildings b ORDER BY b.name LIMIT %s OFFSET %s",
        (page_size, (page - 1) * page_size),
    )
    total = rows[0]["total"] if rows else 0
    for row in rows:
        del row["total"]
    return rows, total


def get_building(building_id: int) -> dict | None:
    """Return one building with its incident count, or None."""
    return db.fetch_one(
        "SELECT b.id, b.name, b.address,"
        "       (SELECT count(*) FROM incidents i WHERE i.building_id = b.id) AS incident_count"
        "  FROM buildings b WHERE b.id = %s",
        (building_id,),
    )


def create_building(name: str, address: str) -> dict | None:
    """Insert a building. Returns None if the name is taken."""
    return db.fetch_one(
        "INSERT INTO buildings (name, address) VALUES (%s, %s)"
        " ON CONFLICT (name) DO NOTHING RETURNING id, name, address",
        (name, address),
    )


def update_building(building_id: int, name: str, address: str) -> dict | None:
    """Rename or re-address a building. Returns None if the new name is taken."""
    try:
        return db.fetch_one(
            "UPDATE buildings SET name = %s, address = %s WHERE id = %s RETURNING id, name, address",
            (name, address, building_id),
        )
    except psycopg.errors.UniqueViolation:
        return None


def delete_building(building_id: int) -> bool:
    """
    Delete a building with its floors and seats, in one transaction.

    Returns:
        False if an incident still points at any of them. The foreign keys
        decide this, so an incident reported a moment ago can't slip through.
    """
    try:
        with db.transaction() as conn:
            conn.execute(
                "DELETE FROM seats WHERE floor_id IN (SELECT id FROM floors WHERE building_id = %s)",
                (building_id,),
            )
            conn.execute("DELETE FROM floors WHERE building_id = %s", (building_id,))
            conn.execute("DELETE FROM buildings WHERE id = %s", (building_id,))
    except psycopg.errors.ForeignKeyViolation:
        return False
    return True


# ---------- floors ----------

def list_floors(building_ids: list[int]) -> list[dict]:
    """Return the floors of these buildings, lowest first, with incident counts."""
    return db.fetch_all(
        "SELECT f.id, f.building_id, f.number,"
        "       (SELECT count(*) FROM incidents i WHERE i.floor_id = f.id) AS incident_count"
        "  FROM floors f WHERE f.building_id = ANY(%s) ORDER BY f.number",
        (building_ids,),
    )


def get_floor(floor_id: int) -> dict | None:
    """Return one floor with its incident count, or None."""
    return db.fetch_one(
        "SELECT f.id, f.building_id, f.number,"
        "       (SELECT count(*) FROM incidents i WHERE i.floor_id = f.id) AS incident_count"
        "  FROM floors f WHERE f.id = %s",
        (floor_id,),
    )


def create_floor(building_id: int, number: int) -> dict | None:
    """Add a floor to a building. Returns None if the building already has that floor number."""
    return db.fetch_one(
        "INSERT INTO floors (building_id, number) VALUES (%s, %s)"
        " ON CONFLICT (building_id, number) DO NOTHING RETURNING id, building_id, number",
        (building_id, number),
    )


def update_floor(floor_id: int, number: int) -> dict | None:
    """Renumber a floor. Returns None if the building already has that number."""
    try:
        return db.fetch_one(
            "UPDATE floors SET number = %s WHERE id = %s RETURNING id, building_id, number",
            (number, floor_id),
        )
    except psycopg.errors.UniqueViolation:
        return None


def delete_floor(floor_id: int) -> bool:
    """Delete a floor and its seats in one transaction. False if an incident points at them."""
    try:
        with db.transaction() as conn:
            conn.execute("DELETE FROM seats WHERE floor_id = %s", (floor_id,))
            conn.execute("DELETE FROM floors WHERE id = %s", (floor_id,))
    except psycopg.errors.ForeignKeyViolation:
        return False
    return True


# ---------- seats ----------

def list_seats(floor_ids: list[int]) -> list[dict]:
    """Return the seats on these floors, by code, with incident counts."""
    return db.fetch_all(
        "SELECT s.id, s.floor_id, s.code,"
        "       (SELECT count(*) FROM incidents i WHERE i.seat_id = s.id) AS incident_count"
        "  FROM seats s WHERE s.floor_id = ANY(%s) ORDER BY s.code",
        (floor_ids,),
    )


def get_seat(seat_id: int) -> dict | None:
    """Return one seat with its incident count, or None."""
    return db.fetch_one(
        "SELECT s.id, s.floor_id, s.code,"
        "       (SELECT count(*) FROM incidents i WHERE i.seat_id = s.id) AS incident_count"
        "  FROM seats s WHERE s.id = %s",
        (seat_id,),
    )


def create_seat(floor_id: int, code: str) -> dict | None:
    """Add a seat to a floor. Returns None if the floor already has that code."""
    return db.fetch_one(
        "INSERT INTO seats (floor_id, code) VALUES (%s, %s)"
        " ON CONFLICT (floor_id, code) DO NOTHING RETURNING id, floor_id, code",
        (floor_id, code),
    )


def update_seat(seat_id: int, code: str) -> dict | None:
    """Rename a seat. Returns None if the floor already has that code."""
    try:
        return db.fetch_one(
            "UPDATE seats SET code = %s WHERE id = %s RETURNING id, floor_id, code",
            (code, seat_id),
        )
    except psycopg.errors.UniqueViolation:
        return None


def delete_seat(seat_id: int) -> bool:
    """Delete a seat. False if an incident points at it."""
    try:
        db.execute("DELETE FROM seats WHERE id = %s", (seat_id,))
    except psycopg.errors.ForeignKeyViolation:
        return False
    return True
