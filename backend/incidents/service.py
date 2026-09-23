"""
Incidents service business logic: validation, permissions and workflow.
No SQL, no HTTP.

Every change that writes more than one row (e.g. status + audit event) runs
inside one repository.transaction(), so it is saved completely or not at all.
"""

from datetime import datetime, timezone

import repository
import rules
from _shared.constants import (
    ISSUE_TYPES,
    PRIORITIES,
    RECURRING_THRESHOLD,
    RECURRING_WINDOW_DAYS,
    REQUEST_TYPES,
    STATUSES,
)
from _shared.errors import Conflict, Forbidden, NotFound, ValidationError
from _shared.shifts import OFFICE_TZ, current_or_next_shift
from _shared.validation import (
    DESCRIPTION_MAX,
    NOTE_MAX,
    REASON_MAX,
    TITLE_MAX,
    get_choice,
    get_date,
    get_int,
    get_number,
    get_pagination,
    get_string,
    raise_if_errors,
    reject_unknown_fields,
)

CREATE_FIELDS = {"title", "description", "category", "issue_type", "priority", "building_id", "floor_id", "seat_id"}
UPDATE_FIELDS = {"version", "title", "description"}
STATUS_FIELDS = {"version", "status", "reason", "resolution_note"}
NOTE_FIELDS = {"body"}
PRIORITY_FIELDS = {"version", "priority", "reason"}
REOPEN_FIELDS = {"reason"}
DECISION_FIELDS = {"decision", "note"}
VOID_FIELDS = {"version", "reason"}
WORK_LOG_FIELDS = {"work_date", "hours", "description"}
REQUEST_LIST_PARAMS = {"page", "page_size", "type"}
SIMILAR_PARAMS = {"issue_type", "floor_id", "seat_id"}
ALL_ISSUE_TYPES = tuple(issue for issues in ISSUE_TYPES.values() for issue in issues)
SIMILAR_LIMIT = 5
LIST_FILTERS = {
    "page", "page_size", "status", "priority", "category", "building_id", "q", "archived", "scope", "pending",
}

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
    if not rules.can_view(user, incident["reporter_id"], engineer_ids, incident["is_archived"]):
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


def _recurring_levels(incident_ids: list[int]) -> dict[int, str | None]:
    """Recurring level ("seat", "floor" or None) for each incident, from one grouped query."""
    counts = repository.recurring_counts(incident_ids, RECURRING_WINDOW_DAYS) if incident_ids else {}
    return {
        incident_id: rules.recurring_level(**counts[incident_id], threshold=RECURRING_THRESHOLD)
        if incident_id in counts else None
        for incident_id in incident_ids
    }


def _recurring_detail(user: dict, incident: dict) -> dict | None:
    """
    The recurring badge for one incident, or None.

    Staff also get the related tickets (engineers only active ones they can
    open). Employees get the count only: they never see other people's tickets.
    """
    counts = repository.recurring_counts([incident["id"]], RECURRING_WINDOW_DAYS).get(incident["id"])
    level = rules.recurring_level(**counts, threshold=RECURRING_THRESHOLD) if counts else None
    if level is None:
        return None
    related = []
    if user["role"] in ("admin", "engineer"):
        related = repository.related_incidents(
            incident["id"], same_seat=level == "seat", days=RECURRING_WINDOW_DAYS,
            include_archived=user["role"] == "admin",
        )
    return {
        "level": level,
        "count": counts["seat_count"] if level == "seat" else counts["floor_count"],
        "window_days": RECURRING_WINDOW_DAYS,
        "related": related,
    }


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
        "scope": get_choice(params, "scope", ("mine", "pool", "all"), errors, required=False),
        "pending": get_choice(params, "pending", REQUEST_TYPES, errors, required=False),
    }
    if filters["scope"] and user["role"] != "engineer":
        errors["scope"] = "Only engineers can filter by scope"
    raise_if_errors(errors)

    items, total = repository.list_incidents(user, filters, page, page_size)
    levels = _recurring_levels([item["id"] for item in items])
    for item in items:
        item["recurring"] = levels[item["id"]]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_incident(user: dict, incident_id: int) -> dict:
    """
    Return one incident with its engineers, notes, work logs, requests and
    history, plus what this user is allowed to do next (so the UI only shows
    valid actions).
    """
    incident, engineer_ids = _load_visible(user, incident_id)
    read_only = incident["is_archived"] or incident["is_voided"]
    requests = repository.get_requests(incident_id)
    pending_types = {request["type"] for request in requests if request["status"] == "pending"}
    reporter_id = incident["reporter_id"]
    status = incident["status"]

    def allowed(check: bool) -> bool:
        """Nothing is allowed on archived or voided tickets."""
        return not read_only and check

    return {
        **incident,
        "engineers": repository.get_engineers(incident_id),
        "notes": repository.get_notes(incident_id),
        "work_logs": repository.get_work_logs(incident_id),
        "requests": requests,
        "acks": repository.get_acks(incident_id),
        "events": repository.get_events(incident_id),
        "recurring": _recurring_detail(user, incident),
        "allowed_actions": {
            "transitions": [] if read_only else rules.allowed_transitions(user, status, reporter_id, engineer_ids),
            "can_edit": allowed(rules.can_edit_details(user, reporter_id)),
            "can_add_note": allowed(rules.can_add_note(user, reporter_id, engineer_ids)),
            "can_join": allowed(rules.can_join(user, engineer_ids)),
            "can_acknowledge": allowed(rules.can_acknowledge(user, status, engineer_ids)),
            "can_change_priority": allowed(rules.can_change_priority(user, reporter_id)),
            "can_request_reopen": allowed(
                rules.can_request_reopen(user, status, reporter_id) and "reopen" not in pending_types
            ),
            "can_decide_requests": allowed(rules.can_decide_requests(user) and bool(pending_types)),
            "can_void": allowed(rules.can_void(user)),
            "can_log_work": allowed(rules.can_log_work(user, engineer_ids)),
        },
    }


def list_pending_requests(user: dict, params: dict) -> dict:
    """
    The admin's approvals queue: pending close approvals and reopen requests,
    oldest first. ?type=close_approval|reopen narrows it to one kind.

    Raises:
        Forbidden: not an admin.
    """
    if not rules.can_decide_requests(user):
        raise Forbidden("Only an admin can see the approvals queue")
    errors: dict[str, str] = {}
    reject_unknown_fields(params, REQUEST_LIST_PARAMS, errors)
    raise_if_errors(errors)
    page, page_size = get_pagination(params)
    request_type = get_choice(params, "type", REQUEST_TYPES, errors, required=False)
    raise_if_errors(errors)

    items, total = repository.list_pending_requests(request_type, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def similar_incidents(user: dict, params: dict) -> dict:
    """
    For the report form: active incidents of the same issue type at the chosen
    seat (or floor, without a seat), and whether this place already has a
    recurring pattern in the last RECURRING_WINDOW_DAYS days.

    Employees see only their own matching tickets in "items" (plus a count of
    everyone's), so they can't browse other people's reports.

    Returns:
        {"open_count", "items", "recurring": {"level", "count", "window_days"} | None}
    """
    errors: dict[str, str] = {}
    reject_unknown_fields(params, SIMILAR_PARAMS, errors)
    issue_type = get_choice(params, "issue_type", ALL_ISSUE_TYPES, errors)
    floor_id = get_int(params, "floor_id", errors)
    seat_id = get_int(params, "seat_id", errors, required=False)
    raise_if_errors(errors)

    active = repository.open_at_location(issue_type, floor_id, seat_id, limit=100)
    visible = active if user["role"] in ("admin", "engineer") else [
        item for item in active if item["reporter_id"] == user["id"]
    ]
    counts = repository.recent_counts_at_location(issue_type, floor_id, seat_id, RECURRING_WINDOW_DAYS)
    level = rules.recurring_level(**counts, threshold=RECURRING_THRESHOLD)
    return {
        "open_count": len(active),
        "items": visible[:SIMILAR_LIMIT],
        "recurring": None if level is None else {
            "level": level,
            "count": counts["seat_count"] if level == "seat" else counts["floor_count"],
            "window_days": RECURRING_WINDOW_DAYS,
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
            if not repository.create_request(incident_id, "close_approval", None, user["id"]):
                raise Conflict("A close approval is already pending for this ticket")
            repository.add_event(incident_id, user["id"], "request_created", to_value="close_approval")
    return get_incident(user, incident_id)


def add_note(user: dict, incident_id: int, data: dict) -> dict:
    """
    Add a note (append-only). The reporter, an admin or an engineer on the
    ticket may add one; an engineer who can only see it gets 403 (join first).
    """
    incident, engineer_ids = _load_visible(user, incident_id)
    _ensure_changeable(incident)
    if not rules.can_add_note(user, incident["reporter_id"], engineer_ids):
        raise Forbidden("Join this ticket before adding notes")

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


# ---------- step 6: join, acknowledge, priority, requests, void, work logs ----------

def join_incident(user: dict, incident_id: int) -> dict:
    """
    Put the calling engineer on the ticket: the first engineer is primary, later
    ones are helpers. Any engineer may join any active ticket (a colleague can
    share the link), so this does not use the normal visibility check.

    Joining a ticket you are already on returns it unchanged (13.4).

    Raises:
        NotFound: no such ticket, or it was voided.
        Forbidden: the caller is not an engineer.
        Conflict: the ticket is archived.
    """
    incident = repository.get_incident(incident_id)
    if incident is None or incident["is_voided"]:
        raise NotFound("Incident not found")
    if user["role"] != "engineer":
        raise Forbidden("Only engineers can join tickets")
    _ensure_changeable(incident)

    engineer_ids = {engineer["id"] for engineer in repository.get_engineers(incident_id)}
    if user["id"] not in engineer_ids:
        role = "helper" if engineer_ids else "primary"
        with repository.transaction():
            if repository.add_engineer(incident_id, user["id"], role):
                if role == "primary":
                    repository.mark_assigned(incident_id)
                repository.add_event(incident_id, user["id"], "engineer_joined", to_value=role)
    return get_incident(user, incident_id)


def acknowledge_incident(user: dict, incident_id: int) -> dict:
    """
    The engineer commits to handling the ticket this shift. The shift end comes
    from their profile (day 07-15, swing 15-23, night 23-07, office time).
    Acknowledging twice in the same shift keeps the first acknowledgement (13.4).

    Raises:
        Forbidden: not an engineer on this ticket.
        Conflict: archived/voided, or the ticket is no longer active.
    """
    incident, engineer_ids = _load_visible(user, incident_id)
    _ensure_changeable(incident)
    if user["role"] != "engineer" or user["id"] not in engineer_ids:
        raise Forbidden("Join the ticket before acknowledging it")
    if not rules.can_acknowledge(user, incident["status"], engineer_ids):
        raise Conflict("Only open, in-progress or blocked tickets can be acknowledged")
    profile = repository.get_engineer_profile(user["id"])
    if profile is None:
        raise Forbidden("Your engineer profile is missing; ask an admin")

    _, shift_ends_at = current_or_next_shift(profile["shift"], datetime.now(timezone.utc))
    with repository.transaction():
        if repository.add_ack(incident_id, user["id"], shift_ends_at):
            repository.mark_acknowledged(incident_id)
            repository.add_event(incident_id, user["id"], "acknowledged", to_value=shift_ends_at.isoformat())
    return get_incident(user, incident_id)


def change_priority(user: dict, incident_id: int, data: dict) -> dict:
    """
    Change the priority (reporter or admin) with a reason; always logged.
    Setting the same priority again is a no-op with no event (13.4).

    Raises:
        Forbidden: not the reporter or an admin.
        ValidationError: bad priority or missing reason.
        Conflict: archived/voided, or the ticket changed since it was loaded.
    """
    incident, _ = _load_visible(user, incident_id)
    if not rules.can_change_priority(user, incident["reporter_id"]):
        raise Forbidden("Only the reporter or an admin can change the priority")
    _ensure_changeable(incident)

    errors: dict[str, str] = {}
    reject_unknown_fields(data, PRIORITY_FIELDS, errors)
    version = _read_version(data, errors)
    priority = get_choice(data, "priority", PRIORITIES, errors)
    reason = get_string(data, "reason", errors, REASON_MAX)
    raise_if_errors(errors)

    if priority == incident["priority"]:
        return get_incident(user, incident_id)
    with repository.transaction():
        if not repository.update_priority(incident_id, version, priority):
            raise Conflict(STALE_VERSION)
        repository.add_event(incident_id, user["id"], "priority_changed", incident["priority"], priority, reason)
    return get_incident(user, incident_id)


def request_reopen(user: dict, incident_id: int, data: dict) -> dict:
    """
    The reporter asks an admin to reopen a resolved or closed ticket, with a reason.

    Raises:
        Forbidden: not the reporter or an admin.
        ValidationError: missing reason.
        Conflict: archived/voided, not resolved or closed, or a reopen request is already pending.
    """
    incident, _ = _load_visible(user, incident_id)
    if user["role"] != "admin" and user["id"] != incident["reporter_id"]:
        raise Forbidden("Only the reporter can ask to reopen this ticket")
    _ensure_changeable(incident)
    if not rules.can_request_reopen(user, incident["status"], incident["reporter_id"]):
        raise Conflict("Only resolved or closed tickets can be reopened")

    errors: dict[str, str] = {}
    reject_unknown_fields(data, REOPEN_FIELDS, errors)
    reason = get_string(data, "reason", errors, REASON_MAX)
    raise_if_errors(errors)

    with repository.transaction():
        if not repository.create_request(incident_id, "reopen", reason, user["id"]):
            raise Conflict("A reopen request is already pending for this ticket")
        repository.add_event(incident_id, user["id"], "request_created", to_value="reopen", reason=reason)
    return get_incident(user, incident_id)


def decide_request(user: dict, incident_id: int, request_id: int, data: dict) -> dict:
    """
    An admin approves or rejects a pending request. A rejection needs a note.

    - close approval approved -> ticket archived (read-only, hidden from active lists)
    - close approval rejected -> ticket goes back to resolved
    - reopen approved -> ticket back to in_progress (a pending close approval is cancelled)
    - reopen rejected -> nothing else changes

    Raises:
        Forbidden: not an admin.
        NotFound: the request is not on this ticket.
        ValidationError: bad decision or missing note on a rejection.
        Conflict: archived/voided, or the request was already decided.
    """
    incident, _ = _load_visible(user, incident_id)
    if not rules.can_decide_requests(user):
        raise Forbidden("Only an admin can approve or reject requests")
    _ensure_changeable(incident)
    request = repository.get_request(incident_id, request_id)
    if request is None:
        raise NotFound("Request not found")

    errors: dict[str, str] = {}
    reject_unknown_fields(data, DECISION_FIELDS, errors)
    decision = get_choice(data, "decision", ("approved", "rejected"), errors)
    note = get_string(data, "note", errors, REASON_MAX, required=decision == "rejected")
    raise_if_errors(errors)

    with repository.transaction():
        if not repository.decide_request(request_id, decision, user["id"], note):
            raise Conflict("This request has already been decided")
        repository.add_event(incident_id, user["id"], "request_decided", request["type"], decision, note)

        if request["type"] == "close_approval" and decision == "approved":
            repository.archive(incident_id, user["id"])
            repository.add_event(incident_id, user["id"], "archived")
        elif request["type"] == "close_approval":
            repository.return_to_resolved(incident_id)
            repository.add_event(incident_id, user["id"], "status_changed", incident["status"], "resolved", note)
        elif decision == "approved":
            repository.cancel_pending_requests(incident_id, "close_approval", user["id"], "Superseded by reopen")
            repository.reopen(incident_id)
            repository.add_event(incident_id, user["id"], "status_changed", incident["status"], "in_progress",
                                 request["reason"])
    return get_incident(user, incident_id)


def void_incident(user: dict, incident_id: int, data: dict) -> None:
    """
    An admin voids an erroneous ticket (soft delete): it disappears from lists
    and metrics but stays in the database and audit trail.

    Raises:
        Forbidden: not an admin.
        ValidationError: missing reason.
        Conflict: already archived/voided, or the ticket changed since it was loaded.
    """
    incident, _ = _load_visible(user, incident_id)
    if not rules.can_void(user):
        raise Forbidden("Only an admin can void a ticket")
    _ensure_changeable(incident)

    errors: dict[str, str] = {}
    reject_unknown_fields(data, VOID_FIELDS, errors)
    version = _read_version(data, errors)
    reason = get_string(data, "reason", errors, REASON_MAX)
    raise_if_errors(errors)

    with repository.transaction():
        if not repository.void(incident_id, version, reason, user["id"]):
            raise Conflict(STALE_VERSION)
        repository.add_event(incident_id, user["id"], "voided", reason=reason)


def _read_work_log(incident: dict, data: dict) -> tuple:
    """
    Validate a work log body: hours in 0.25 steps (0.25 to 12), a work date not
    in the future and not before the ticket was reported (office time).

    Returns:
        (work_date, hours, description)
    """
    errors: dict[str, str] = {}
    reject_unknown_fields(data, WORK_LOG_FIELDS, errors)
    work_date = get_date(data, "work_date", errors)
    hours = get_number(data, "hours", errors)
    description = get_string(data, "description", errors, NOTE_MAX)
    if hours is not None and rules.hours_error(hours):
        errors["hours"] = rules.hours_error(hours)
    if work_date is not None:
        today = datetime.now(OFFICE_TZ).date()
        reported_on = incident["created_at"].astimezone(OFFICE_TZ).date()
        if work_date > today:
            errors["work_date"] = "Can't log work in the future"
        elif work_date < reported_on:
            errors["work_date"] = "Can't log work from before the ticket was reported"
    raise_if_errors(errors)
    return work_date, hours, description


def add_work_log(user: dict, incident_id: int, data: dict) -> dict:
    """
    Log time spent. Only engineers currently on the ticket may do this; logs
    are locked once the ticket is archived.

    Raises:
        Forbidden: not an engineer on this ticket (13.4).
        ValidationError: bad date, hours or description.
        Conflict: archived/voided.
    """
    incident, engineer_ids = _load_visible(user, incident_id)
    _ensure_changeable(incident)
    if not rules.can_log_work(user, engineer_ids):
        raise Forbidden("Only engineers on this ticket can log work")
    work_date, hours, description = _read_work_log(incident, data)

    with repository.transaction():
        repository.add_work_log(incident_id, user["id"], work_date, hours, description)
        repository.add_event(incident_id, user["id"], "work_logged", to_value=f"{hours:g} h on {work_date}")
    return get_incident(user, incident_id)


def edit_work_log(user: dict, incident_id: int, log_id: int, data: dict) -> dict:
    """
    Edit a work log. Only its author may; the old values are kept in the audit log.

    Raises:
        NotFound: the log is not on this ticket.
        Forbidden: not the author.
        ValidationError: bad date, hours or description.
        Conflict: archived/voided.
    """
    incident, _ = _load_visible(user, incident_id)
    log = repository.get_work_log(incident_id, log_id)
    if log is None:
        raise NotFound("Work log not found")
    if log["engineer_id"] != user["id"]:
        raise Forbidden("Only the engineer who logged this work can edit it")
    _ensure_changeable(incident)
    work_date, hours, description = _read_work_log(incident, data)

    old = f"{float(log['hours']):g} h on {log['work_date']}: {log['description']}"
    new = f"{hours:g} h on {work_date}: {description}"
    if old != new:
        with repository.transaction():
            repository.update_work_log(log_id, work_date, hours, description)
            repository.add_event(incident_id, user["id"], "work_log_edited", old, new)
    return get_incident(user, incident_id)
