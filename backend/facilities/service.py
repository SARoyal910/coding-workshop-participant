"""
Facilities service business logic: buildings, floors and seats. No SQL, no HTTP.

Only admins manage locations. Nothing that an incident points at can be
deleted (409 with the reason), so every incident keeps its location history.
"""

import repository
from _shared.errors import Conflict, NotFound
from _shared.validation import (
    NAME_MAX,
    get_int,
    get_pagination,
    get_string,
    raise_if_errors,
    reject_unknown_fields,
)

BUILDING_FIELDS = {"name", "address"}
FLOOR_FIELDS = {"number"}
SEAT_FIELDS = {"code"}
LIST_PARAMS = {"page", "page_size"}

ADDRESS_MAX = 200
SEAT_CODE_MAX = 20
# Basements are negative floor numbers.
FLOOR_MIN = -10
FLOOR_MAX = 200


def _plural(count: int, word: str) -> str:
    """'1 incident', '3 incidents'."""
    return f"{count} {word}{'' if count == 1 else 's'}"


def _ensure_unused(place: dict, what: str) -> None:
    """Refuse to delete a place that incidents point at, and say why."""
    if place["incident_count"]:
        raise Conflict(
            f"This {what} has {_plural(place['incident_count'], 'incident')}, so it can't be deleted."
            " Incidents keep their location history."
        )


# ---------- buildings ----------

def list_buildings(params: dict) -> dict:
    """
    Return one page of buildings, each with its floors and their seats.

    Returns:
        {"items", "total", "page", "page_size"}; every building, floor and seat
        has an incident_count.
    """
    errors: dict[str, str] = {}
    reject_unknown_fields(params, LIST_PARAMS, errors)
    raise_if_errors(errors)
    page, page_size = get_pagination(params)

    buildings, total = repository.list_buildings(page, page_size)
    floors = repository.list_floors([building["id"] for building in buildings]) if buildings else []
    seats = repository.list_seats([floor["id"] for floor in floors]) if floors else []

    # Nest seats under floors and floors under buildings.
    for floor in floors:
        floor["seats"] = [seat for seat in seats if seat["floor_id"] == floor["id"]]
    for building in buildings:
        building["floors"] = [floor for floor in floors if floor["building_id"] == building["id"]]
    return {"items": buildings, "total": total, "page": page, "page_size": page_size}


def _read_building(data: dict) -> tuple[str, str]:
    """Validate a building body."""
    errors: dict[str, str] = {}
    reject_unknown_fields(data, BUILDING_FIELDS, errors)
    name = get_string(data, "name", errors, NAME_MAX)
    address = get_string(data, "address", errors, ADDRESS_MAX)
    raise_if_errors(errors)
    return name, address


def _building_name_taken() -> Conflict:
    """The 409 for a duplicate building name."""
    return Conflict("A building with this name already exists", {"name": "This name is already used"})


def create_building(data: dict) -> dict:
    """
    Add a building.

    Raises:
        ValidationError: missing or invalid fields.
        Conflict: the name is taken.
    """
    name, address = _read_building(data)
    building = repository.create_building(name, address)
    if building is None:
        raise _building_name_taken()
    return building


def update_building(building_id: int, data: dict) -> dict:
    """Change a building's name and address (404 if missing, 409 if the name is taken)."""
    if repository.get_building(building_id) is None:
        raise NotFound("Building not found")
    name, address = _read_building(data)
    building = repository.update_building(building_id, name, address)
    if building is None:
        raise _building_name_taken()
    return building


def delete_building(building_id: int) -> None:
    """
    Delete a building together with its floors and seats.

    Raises:
        NotFound: no such building.
        Conflict: an incident was reported somewhere in the building.
    """
    building = repository.get_building(building_id)
    if building is None:
        raise NotFound("Building not found")
    _ensure_unused(building, "building")
    if not repository.delete_building(building_id):
        # An incident was reported between the check and the delete.
        raise Conflict("This building now has incidents, so it can't be deleted")


# ---------- floors ----------

def _read_floor(data: dict) -> int:
    """Validate a floor body."""
    errors: dict[str, str] = {}
    reject_unknown_fields(data, FLOOR_FIELDS, errors)
    number = get_int(data, "number", errors, minimum=FLOOR_MIN)
    if number is not None and number > FLOOR_MAX:
        errors["number"] = f"Must be at most {FLOOR_MAX}"
    raise_if_errors(errors)
    return number


def _floor_taken() -> Conflict:
    """The 409 for a duplicate floor number."""
    return Conflict("This building already has a floor with that number", {"number": "Already used in this building"})


def create_floor(building_id: int, data: dict) -> dict:
    """Add a floor to a building (404 if the building is missing, 409 if the number is taken)."""
    if repository.get_building(building_id) is None:
        raise NotFound("Building not found")
    floor = repository.create_floor(building_id, _read_floor(data))
    if floor is None:
        raise _floor_taken()
    return floor


def update_floor(floor_id: int, data: dict) -> dict:
    """Renumber a floor (404 if missing, 409 if the number is taken)."""
    if repository.get_floor(floor_id) is None:
        raise NotFound("Floor not found")
    floor = repository.update_floor(floor_id, _read_floor(data))
    if floor is None:
        raise _floor_taken()
    return floor


def delete_floor(floor_id: int) -> None:
    """Delete a floor and its seats (404 if missing, 409 if it has incidents)."""
    floor = repository.get_floor(floor_id)
    if floor is None:
        raise NotFound("Floor not found")
    _ensure_unused(floor, "floor")
    if not repository.delete_floor(floor_id):
        raise Conflict("This floor now has incidents, so it can't be deleted")


# ---------- seats ----------

def _read_seat(data: dict) -> str:
    """Validate a seat body."""
    errors: dict[str, str] = {}
    reject_unknown_fields(data, SEAT_FIELDS, errors)
    code = get_string(data, "code", errors, SEAT_CODE_MAX)
    raise_if_errors(errors)
    return code


def _seat_taken() -> Conflict:
    """The 409 for a duplicate seat code."""
    return Conflict("This floor already has a seat with that code", {"code": "Already used on this floor"})


def create_seat(floor_id: int, data: dict) -> dict:
    """Add a seat to a floor (404 if the floor is missing, 409 if the code is taken)."""
    if repository.get_floor(floor_id) is None:
        raise NotFound("Floor not found")
    seat = repository.create_seat(floor_id, _read_seat(data))
    if seat is None:
        raise _seat_taken()
    return seat


def update_seat(seat_id: int, data: dict) -> dict:
    """Rename a seat (404 if missing, 409 if the code is taken)."""
    if repository.get_seat(seat_id) is None:
        raise NotFound("Seat not found")
    seat = repository.update_seat(seat_id, _read_seat(data))
    if seat is None:
        raise _seat_taken()
    return seat


def delete_seat(seat_id: int) -> None:
    """Delete a seat (404 if missing, 409 if it has incidents)."""
    seat = repository.get_seat(seat_id)
    if seat is None:
        raise NotFound("Seat not found")
    _ensure_unused(seat, "seat")
    if not repository.delete_seat(seat_id):
        raise Conflict("This seat now has incidents, so it can't be deleted")
