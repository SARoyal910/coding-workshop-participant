"""
Incidents service business logic: validation, permissions and workflow.
No SQL, no HTTP.

Every change that writes more than one row (e.g. status + audit event) runs
inside one repository.transaction(), so it is saved completely or not at all.
"""

import repository
import rules
from _shared.constants import ISSUE_TYPES, PRIORITIES, STATUSES
from _shared.errors import Conflict, Forbidden, NotFound, ValidationError
from _shared.validation import (
    DESCRIPTION_MAX,
    NOTE_MAX,
    REASON_MAX,
    TITLE_MAX,
    get_choice,
    get_int,
    get_pagination,
    get_string,
    raise_if_errors,
    reject_unknown_fields,
)

CREATE_FIELDS = {"title", "description", "category", "issue_type", "priority", "building_id", "floor_id", "seat_id"}
UPDATE_FIELDS = {"version", "title", "description"}
STATUS_FIELDS = {"version", "status", "reason", "resolution_note"}
NOTE_FIELDS = {"body"}
LIST_FILTERS = {"page", "page_size", "status", "priority", "category", "building_id", "q", "archived", "scope"}

STALE_VERSION = "This ticket was updated by someone else. Refresh to see the latest."


# ---------- helpers ----------

def _load_visible(user: dict, incident_id: int) -> tuple[dict, set[int]]:
    """
    Load an incident and its engineer ids, checking the user may see it.

    Raises:
        NotFound: it does not exist, is voided (non-admins), or the user may not see it.
            404 rather than 403 so ids of other people's tickets are not revealed.
    """
    incident = repository.get_incident(incident_id)
    if incident is None:
        raise NotFound("Incident not found")
    engineer_ids = {engineer["id"] for engineer in repository.get_engineers(incident_id)}
    if incident["is_voided"] and user["role"] != "admin":
        raise NotFound("Incident not found")
    if not rules.can_view(user, incident["reporter_id"], engineer_ids):
        raise NotFound("Incident not found")
    return incident, engineer_ids


def _ensure_changeable(incident: dict) -> None:
    """Archived and voided tickets are read-only."""
    if incident["is_archived"]:
        raise Conflict("This ticket is archived and can no longer be changed")
    if incident["is_voided"]:
        raise Conflict("This ticket was voided and can no longer be changed")


def _read_version(data: dict, errors: dict) -> int | None:
    """Every update must send the version it loaded (optimistic locking)."""
    return get_int(data, "version", errors)


# ---------- queries ----------

def list_incidents(user: dict, params: dict) -> dict:
    """Return one page of incidents the user may see: {"items", "total", "page", "page_size"}."""
    errors: dict[str, str] = {}
    reject_unknown_fields(params, LIST_FILTERS, errors)
    raise_if_errors(errors)
    page, page_size = get_pagination(params)

    filters = {
        "status": get_choice(params, "status", STATUSES, errors, required=False),
        "priority": get_choice(params, "priority", PRIORITIES, errors, required=False),
        "category": get_choice(params, "category", tuple(ISSUE_TYPES), errors, required=False),
        "building_id": get_int(params, "building_id", errors, required=False),
        "q": get_string(params, "q", errors, TITLE_MAX, required=False),
        "archived": get_choice(params, "archived", ("true", "false"), errors, default="false") == "true",
        "scope": get_choice(params, "scope", ("mine", "pool"), errors, required=False),
    }
    if filters["scope"] and user["role"] != "engineer":
        errors["scope"] = "Only engineers can filter by scope"
    raise_if_errors(errors)

    items, total = repository.list_incidents(user, filters, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_incident(user: dict, incident_id: int) -> dict:
    """
    Return one incident with its engineers, notes and history, plus what this
    user is allowed to do next (so the UI only shows valid actions).
    """
    incident, engineer_ids = _load_visible(user, incident_id)
    read_only = incident["is_archived"] or incident["is_voided"]
    return {
        **incident,
        "engineers": repository.get_engineers(incident_id),
        "notes": repository.get_notes(incident_id),
        "events": repository.get_events(incident_id),
        "allowed_actions": {
            "transitions": [] if read_only else rules.allowed_transitions(
                user, incident["status"], incident["reporter_id"], engineer_ids
            ),
            "can_edit": not read_only and rules.can_edit_details(user, incident["reporter_id"]),
            "can_add_note": not read_only,
        },
    }


def form_options() -> dict:
    """Everything the create form needs: categories -> issue types, priorities, and the location tree."""
    buildings: dict[int, dict] = {}
    for row in repository.list_locations():
        building = buildings.setdefault(row["building_id"], {
            "id": row["building_id"], "name": row["building_name"], "floors": {},
        })
        floor = building["floors"].setdefault(row["floor_id"], {
            "id": row["floor_id"], "number": row["floor_number"], "seats": [],
        })
        if row["seat_id"] is not None:
            floor["seats"].append({"id": row["seat_id"], "code": row["seat_code"]})
    for building in buildings.values():
        building["floors"] = list(building["floors"].values())

    return {
        "issue_types": {category: list(types) for category, types in ISSUE_TYPES.items()},
        "priorities": list(PRIORITIES),
        "buildings": list(buildings.values()),
    }


# ---------- commands ----------

def create_incident(user: dict, data: dict) -> dict:
    """
    Report a new incident. Anyone logged in can report one.

    Raises:
        ValidationError: missing/invalid fields, an issue type from another
            category, or a floor/seat that doesn't belong to the chosen building/floor.
    """
    errors: dict[str, str] = {}
    reject_unknown_fields(data, CREATE_FIELDS, errors)
    fields = {
        "title": get_string(data, "title", errors, TITLE_MAX),
        "description": get_string(data, "description", errors, DESCRIPTION_MAX),
        "category": get_choice(data, "category", tuple(ISSUE_TYPES), errors),
        "priority": get_choice(data, "priority", PRIORITIES, errors, default="medium"),
        "building_id": get_int(data, "building_id", errors),
        "floor_id": get_int(data, "floor_id", errors),
        "seat_id": get_int(data, "seat_id", errors, required=False),
    }
    if fields["category"]:
        fields["issue_type"] = get_choice(data, "issue_type", ISSUE_TYPES[fields["category"]], errors)
    elif "issue_type" not in data:
        errors["issue_type"] = "This field is required"
    raise_if_errors(errors)

    # Referenced ids must exist and fit together (13.3).
    if not repository.floor_in_building(fields["floor_id"], fields["building_id"]):
        errors["floor_id"] = "Floor not found in this building"
    elif fields["seat_id"] and not repository.seat_on_floor(fields["seat_id"], fields["floor_id"]):
        errors["seat_id"] = "Seat not found on this floor"
    raise_if_errors(errors)

    with repository.transaction():
        incident_id = repository.create_incident(fields, user["id"])
        repository.add_event(incident_id, user["id"], "created", to_value="open")
    return get_incident(user, incident_id)


def update_incident(user: dict, incident_id: int, data: dict) -> dict:
    """
    Edit the title and/or description. Only the reporter or an admin may do this.

    Raises:
        Forbidden: not the reporter or an admin.
        Conflict: archived/voided ticket, or it changed since the client loaded it.
    """
    incident, _ = _load_visible(user, incident_id)
    if not rules.can_edit_details(user, incident["reporter_id"]):
        raise Forbidden("Only the reporter or an admin can edit this ticket")
    _ensure_changeable(incident)

    errors: dict[str, str] = {}
    reject_unknown_fields(data, UPDATE_FIELDS, errors)
    version = _read_version(data, errors)
    limits = {"title": TITLE_MAX, "description": DESCRIPTION_MAX}
    new_values = {
        field: get_string(data, field, errors, limit) for field, limit in limits.items() if field in data
    }
    if not new_values and not errors:
        errors["title"] = "Send a new title and/or description"
    raise_if_errors(errors)

    changes = {field: value for field, value in new_values.items() if value != incident[field]}
    if not changes:
        return get_incident(user, incident_id)  # Nothing changed: no update, no event.

    with repository.transaction():
        if not repository.update_details(incident_id, version, changes):
            raise Conflict(STALE_VERSION)
        for field, value in changes.items():
            repository.add_event(incident_id, user["id"], f"{field}_changed", incident[field], value)
    return get_incident(user, incident_id)


def change_status(user: dict, incident_id: int, data: dict) -> dict:
    """
    Move a ticket through the workflow in rules.WORKFLOW.

    Blocking needs a reason; resolving needs a resolution note (saved as a note);
    closing creates a close-approval request for an admin.

    Raises:
        ValidationError: bad input or a required reason/note is missing.
        Forbidden: the user may not make this transition.
        Conflict: the transition is not allowed from the current status, the
            ticket is archived/voided, or it changed since the client loaded it.
    """
    incident, engineer_ids = _load_visible(user, incident_id)
    _ensure_changeable(incident)

    errors: dict[str, str] = {}
    reject_unknown_fields(data, STATUS_FIELDS, errors)
    version = _read_version(data, errors)
    target = get_choice(data, "status", STATUSES, errors)
    reason = get_string(data, "reason", errors, REASON_MAX, required=False)
    resolution_note = get_string(data, "resolution_note", errors, NOTE_MAX, required=False)
    raise_if_errors(errors)

    current = incident["status"]
    rule = rules.get_rule(current, target)
    if rule is None:
        raise Conflict(f"A ticket can't move from {current} to {target}")
    if not rules.is_permitted(rule, user, incident["reporter_id"], engineer_ids):
        raise Forbidden("You don't have permission to make this change")
    if rule["requires"] == "reason" and not reason:
        raise ValidationError("Validation failed", {"reason": "A reason is required to block a ticket"})
    if rule["requires"] == "resolution_note" and not resolution_note:
        raise ValidationError("Validation failed", {"resolution_note": "Describe how the issue was resolved"})

    with repository.transaction():
        blocked_reason = reason if target == "blocked" else None
        if not repository.update_status(incident_id, version, target, blocked_reason):
            raise Conflict(STALE_VERSION)
        repository.add_event(incident_id, user["id"], "status_changed", current, target, reason)
        if target == "resolved":
            repository.add_note(incident_id, user["id"], resolution_note)
            repository.add_event(incident_id, user["id"], "note_added")
        if target == "closed":
            if not repository.create_close_request(incident_id, user["id"]):
                raise Conflict("A close approval is already pending for this ticket")
            repository.add_event(incident_id, user["id"], "request_created", to_value="close_approval")
    return get_incident(user, incident_id)


def add_note(user: dict, incident_id: int, data: dict) -> dict:
    """Add a note. Anyone who can see the ticket may add one; notes are append-only."""
    incident, _ = _load_visible(user, incident_id)
    _ensure_changeable(incident)

    errors: dict[str, str] = {}
    reject_unknown_fields(data, NOTE_FIELDS, errors)
    body = get_string(data, "body", errors, NOTE_MAX)
    raise_if_errors(errors)

    with repository.transaction():
        note = repository.add_note(incident_id, user["id"], body)
        repository.add_event(incident_id, user["id"], "note_added")
        repository.touch(incident_id)
    return {**note, "author_name": user["name"], "author_role": user["role"]}


def edit_note(user: dict, incident_id: int, note_id: int, data: dict) -> dict:
    """
    Edit a note. Only its author may; the old text is kept in the audit log.

    Raises:
        NotFound: the note is not on this ticket.
        Forbidden: the user is not the author.
        Conflict: the ticket is archived/voided.
    """
    incident, _ = _load_visible(user, incident_id)
    note = repository.get_note(incident_id, note_id)
    if note is None:
        raise NotFound("Note not found")
    if note["author_id"] != user["id"]:
        raise Forbidden("Only the author can edit this note")
    _ensure_changeable(incident)

    errors: dict[str, str] = {}
    reject_unknown_fields(data, NOTE_FIELDS, errors)
    body = get_string(data, "body", errors, NOTE_MAX)
    raise_if_errors(errors)

    old_body = note["body"]
    if body != old_body:
        with repository.transaction():
            note = repository.update_note(note_id, body)
            repository.add_event(incident_id, user["id"], "note_edited", from_value=old_body, to_value=body)
    return {**note, "author_name": user["name"], "author_role": user["role"]}
