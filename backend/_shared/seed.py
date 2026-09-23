"""
Demo data, inserted once when the users table is empty.

The data is deterministic (fixed random seed) and contains the patterns the
dashboards need to show: a seat with repeated Wi-Fi failures, a floor with
repeated HVAC issues, an overloaded engineer, an engineer with missed shift
commitments, blocked tickets, and pending approval / reopen requests.

All seed accounts share one password, read from SEED_PASSWORD. If it is not
set, seeding is skipped so no password is ever hardcoded.
"""

import logging
import os
import random
from datetime import datetime, timedelta, timezone

import psycopg

from _shared.auth import hash_password
from _shared.constants import ISSUE_TYPES
from _shared.shifts import current_or_next_shift

logger = logging.getLogger(__name__)

# Any fixed number works; it stops two cold starts from seeding at the same time.
SEED_LOCK_ID = 4815162342

ADMIN = ("Alex Morgan", "admin@acme.inc")

# (name, email, specialty, shift, phone)
ENGINEERS = [
    ("Priya Nair", "priya.nair@acme.inc", "IT", "day", "555-0101"),       # overloaded
    ("Tom Becker", "tom.becker@acme.inc", "facilities", "day", "555-0102"),
    ("Lena Ortiz", "lena.ortiz@acme.inc", "AV", "swing", "555-0103"),     # missed shifts
    ("Sam Okafor", "sam.okafor@acme.inc", "security", "night", "555-0104"),
    ("Jordan Lee", "jordan.lee@acme.inc", "IT", "swing", "555-0105"),
]

EMPLOYEES = [
    ("Dana Whitfield", "dana.whitfield@acme.inc"),
    ("Luis Romero", "luis.romero@acme.inc"),
    ("Mei Chen", "mei.chen@acme.inc"),
    ("Omar Haddad", "omar.haddad@acme.inc"),
    ("Grace Kim", "grace.kim@acme.inc"),
    ("Ben Carter", "ben.carter@acme.inc"),
    ("Aisha Patel", "aisha.patel@acme.inc"),
    ("Noah Fischer", "noah.fischer@acme.inc"),
    ("Sofia Rossi", "sofia.rossi@acme.inc"),
    ("Ethan Brooks", "ethan.brooks@acme.inc"),
]

# (building name, address, {floor number: seat codes}). 40 seats in total.
BUILDINGS = [
    ("HQ Tower", "100 Market Street", {
        10: [f"10-A-{n:03d}" for n in range(1, 7)],
        11: [f"11-A-{n:03d}" for n in range(1, 7)],
        12: [f"12-A-{n:03d}" for n in range(30, 37)],
    }),
    ("Riverside", "25 River Road", {
        1: [f"1-R-{n:03d}" for n in range(1, 6)],
        2: [f"2-R-{n:03d}" for n in range(1, 7)],
    }),
    ("Innovation Lab", "7 Research Park", {
        1: [f"1-L-{n:03d}" for n in range(1, 6)],
        2: [f"2-L-{n:03d}" for n in range(1, 6)],
    }),
]

# Default title and description for each issue type.
ISSUE_TEXT = {
    "Wi-Fi": ("Wi-Fi keeps dropping", "Laptop loses the Wi-Fi connection every few minutes."),
    "Monitor": ("Monitor not turning on", "External monitor shows no signal."),
    "Docking station": ("Docking station not charging", "Laptop does not charge on the dock."),
    "Printer": ("Printer jammed", "Floor printer shows a paper jam error."),
    "Badge reader": ("Badge reader not responding", "Badge reader light stays red."),
    "HVAC": ("Area too hot", "Temperature around the desk is above 28°C."),
    "Lighting": ("Lights flickering", "Ceiling lights flicker constantly."),
    "Plumbing": ("Leaking sink", "Kitchenette sink is leaking under the cabinet."),
    "Furniture": ("Broken chair", "Chair height adjustment is broken."),
    "Cleaning": ("Spill needs cleaning", "Coffee spilled on the carpet."),
    "Projector": ("Projector won't start", "Meeting room projector does not power on."),
    "Video conferencing": ("Video call system down", "Room video system cannot join calls."),
    "Speakers": ("No audio in room", "Room speakers produce no sound."),
    "Door access": ("Door won't unlock", "Side door does not open with a valid badge."),
    "Camera": ("Security camera offline", "Hallway camera feed is black."),
    "Lock": ("Cabinet lock stuck", "Filing cabinet lock will not turn."),
}


def _incident(issue_type: str, seat: str, reporter: str, days_ago: float, status: str = "open", **extra) -> dict:
    """Build one incident spec. `extra` may hold: priority, engineers, acked_by,
    blocked_reason, request, archived, void_reason, priority_raise."""
    return {"issue_type": issue_type, "seat": seat, "reporter": reporter,
            "days_ago": days_ago, "status": status, **extra}


# Engineers are referenced by first name, employees by first name too.
INCIDENTS = [
    # Seat 12-A-034: five Wi-Fi incidents in 30 days (recurring issue).
    _incident("Wi-Fi", "12-A-034", "dana", 27, "closed", engineers=["priya"], request=("close_approval", "approved")),
    _incident("Wi-Fi", "12-A-034", "dana", 20, "closed", engineers=["jordan"], acked_by="jordan",
              request=("close_approval", "approved")),
    _incident("Wi-Fi", "12-A-034", "dana", 13, "resolved", engineers=["priya"], request=("reopen", "pending")),
    _incident("Wi-Fi", "12-A-034", "dana", 6, "in_progress", engineers=["priya", "jordan"]),
    _incident("Wi-Fi", "12-A-034", "dana", 1, "open", priority_raise=("medium", "high", "Third time this month")),

    # Riverside floor 2: four HVAC incidents on different seats (recurring issue).
    _incident("HVAC", "2-R-001", "luis", 12, "resolved", engineers=["tom"], acked_by="tom"),
    _incident("HVAC", "2-R-002", "mei", 9, "blocked", engineers=["tom"],
              blocked_reason="Waiting on replacement compressor from HVAC contractor"),
    _incident("HVAC", "2-R-004", "omar", 4, "in_progress", engineers=["tom"]),
    _incident("HVAC", "2-R-006", "luis", 2, "open", priority_raise=("medium", "high", "Whole row is affected")),

    # Blocked tickets with reasons.
    _incident("Door access", "1-L-002", "grace", 7, "blocked", engineers=["sam"], acked_by="sam", priority="high",
              blocked_reason="Badge vendor must reprogram the door controller; visit scheduled"),
    _incident("Projector", "11-A-003", "ben", 6, "blocked", engineers=["lena"], acked_by="lena",
              blocked_reason="Replacement lamp on order"),
    _incident("Printer", "10-A-002", "aisha", 5, "blocked", engineers=["priya"],
              blocked_reason="Waiting on fuser unit from supplier"),
    _incident("Plumbing", "2-L-003", "noah", 8, "blocked", engineers=["tom"], priority="high",
              blocked_reason="Building management must shut off the water main this weekend"),

    # Lena acknowledged these but the shift ended without resolving or blocking (missed commitments).
    _incident("Video conferencing", "12-A-031", "sofia", 5, "in_progress", engineers=["lena"], acked_by="lena",
              priority_raise=("high", "critical", "Board meeting in this room tomorrow")),
    _incident("Speakers", "11-A-005", "ethan", 4, "in_progress", engineers=["lena"], acked_by="lena"),
    _incident("Projector", "1-L-004", "grace", 3, "in_progress", engineers=["lena"], acked_by="lena"),
    _incident("Video conferencing", "1-R-002", "mei", 2, "in_progress", engineers=["lena"], acked_by="lena"),

    # Priya is primary on many active tickets (overloaded engineer).
    _incident("Monitor", "10-A-004", "ben", 10, "in_progress", engineers=["priya"]),
    _incident("Docking station", "11-A-001", "aisha", 8, "in_progress", engineers=["priya"]),
    _incident("Badge reader", "1-R-003", "luis", 7, "in_progress", engineers=["priya"], priority="high"),
    _incident("Printer", "2-L-001", "noah", 5, "in_progress", engineers=["priya"]),
    _incident("Wi-Fi", "1-L-005", "sofia", 4, "in_progress", engineers=["priya"]),
    _incident("Monitor", "12-A-035", "dana", 3, "in_progress", engineers=["priya"]),
    _incident("Docking station", "2-R-005", "omar", 1.5, "in_progress", engineers=["priya"]),

    # Closed by the reporter and waiting for admin approval.
    _incident("Lighting", "10-A-005", "ethan", 8, "closed", engineers=["tom"], request=("close_approval", "pending")),
    _incident("Monitor", "11-A-006", "grace", 7, "closed", engineers=["jordan"], acked_by="jordan",
              request=("close_approval", "pending")),
    _incident("Camera", "2-L-005", "ben", 6, "closed", engineers=["sam"], request=("close_approval", "pending")),

    # Reopen requested, and one close that the admin rejected.
    _incident("Furniture", "1-R-001", "mei", 10, "resolved", engineers=["tom"], request=("reopen", "pending")),
    _incident("Speakers", "10-A-001", "omar", 9, "resolved", engineers=["lena"], request=("close_approval", "rejected")),

    # Archived (closed and approved).
    _incident("Lighting", "11-A-002", "luis", 29, "closed", engineers=["tom"], acked_by="tom",
              request=("close_approval", "approved")),
    _incident("Printer", "12-A-032", "aisha", 26, "closed", engineers=["jordan"], request=("close_approval", "approved")),
    _incident("Lock", "1-L-001", "noah", 24, "closed", engineers=["sam"], acked_by="sam",
              request=("close_approval", "approved")),
    _incident("Cleaning", "2-R-003", "sofia", 22, "closed", engineers=["tom"], request=("close_approval", "approved")),
    _incident("Projector", "2-L-002", "ethan", 21, "closed", engineers=["lena"], request=("close_approval", "approved")),
    _incident("Badge reader", "10-A-003", "dana", 19, "closed", engineers=["priya"], acked_by="priya",
              request=("close_approval", "approved")),
    _incident("Door access", "1-R-004", "grace", 17, "closed", engineers=["sam"], request=("close_approval", "approved")),
    _incident("Docking station", "12-A-036", "ben", 16, "closed", engineers=["jordan"], acked_by="jordan",
              request=("close_approval", "approved")),

    # Voided by the admin (duplicate report).
    _incident("Cleaning", "12-A-033", "dana", 3, "open", void_reason="Duplicate of an existing cleaning request"),

    # Unassigned pool: open tickets nobody has picked up.
    _incident("Monitor", "10-A-006", "luis", 0.5, "open"),
    _incident("Lighting", "1-L-003", "mei", 1, "open", priority="low"),
    _incident("Furniture", "11-A-004", "omar", 2, "open", priority="low"),
    _incident("Printer", "1-R-005", "grace", 0.3, "open"),
    _incident("Speakers", "2-L-004", "ben", 1.2, "open"),
    _incident("Cleaning", "10-A-002", "aisha", 0.2, "open", priority="low"),
    _incident("Badge reader", "12-A-030", "noah", 2.5, "open", priority="high"),
    _incident("Plumbing", "11-A-003", "sofia", 3, "open"),

    # Resolved within the shift they were acknowledged.
    _incident("Wi-Fi", "10-A-001", "ethan", 14, "resolved", engineers=["jordan"], acked_by="jordan"),
    _incident("Camera", "1-L-002", "dana", 12, "resolved", engineers=["sam"], acked_by="sam"),
    _incident("Lighting", "2-R-004", "luis", 11, "resolved", engineers=["tom"], acked_by="tom"),
    _incident("Docking station", "1-L-004", "mei", 9, "resolved", engineers=["jordan"], acked_by="jordan"),
    _incident("Lock", "2-L-003", "omar", 7, "resolved", engineers=["sam"], acked_by="sam"),
    _incident("Monitor", "1-R-002", "grace", 6, "resolved", engineers=["priya"], acked_by="priya"),
    _incident("Furniture", "10-A-004", "ben", 5, "resolved", engineers=["tom"], acked_by="tom"),
    _incident("Video conferencing", "11-A-001", "aisha", 3, "resolved", engineers=["lena", "jordan"]),

    # In progress with a helper engineer.
    _incident("Door access", "2-R-002", "noah", 6, "in_progress", engineers=["sam", "tom"]),
    _incident("Printer", "12-A-034", "sofia", 4, "in_progress", engineers=["jordan", "priya"]),
    _incident("HVAC", "10-A-003", "ethan", 3, "in_progress", engineers=["tom", "sam"]),
    _incident("Projector", "12-A-031", "dana", 1, "in_progress", engineers=["lena", "jordan"]),

    # New high-priority security reports.
    _incident("Lock", "11-A-005", "luis", 0.4, "open", priority="high"),
    _incident("Camera", "1-R-001", "mei", 0.1, "open", priority="critical"),
]


def _category_for(issue_type: str) -> str:
    """Return the category that an issue type belongs to."""
    for category, types in ISSUE_TYPES.items():
        if issue_type in types:
            return category
    raise ValueError(f"Unknown issue type: {issue_type}")


def _first_name_key(name: str) -> str:
    """Turn "Priya Nair" into "priya", the key used in INCIDENTS."""
    return name.split()[0].lower()


class _Seeder:
    """Inserts the demo data inside one open transaction."""

    def __init__(self, conn: psycopg.Connection, password_hash: str) -> None:
        """Store the connection, the shared password hash and a fixed clock."""
        self.conn = conn
        self.password_hash = password_hash
        self.now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        # Only picks demo values, never used for security (Bandit B311).
        self.rng = random.Random(42)  # nosec B311
        self.users: dict[str, int] = {}          # first name -> user id
        self.shifts: dict[str, str] = {}         # engineer first name -> shift
        self.seats: dict[str, tuple[int, int, int]] = {}  # code -> (building, floor, seat)
        self.admin_id = 0

    def insert(self, sql: str, params: tuple) -> int:
        """Run an INSERT ... RETURNING id and return the new id."""
        return self.conn.execute(sql, params).fetchone()["id"]

    def add_user(self, name: str, email: str, role: str) -> int:
        """Insert one user and remember them by first name."""
        user_id = self.insert(
            "INSERT INTO users (name, email, password_hash, role, created_at)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (name, email, self.password_hash, role, self.now - timedelta(days=45)),
        )
        self.users[_first_name_key(name)] = user_id
        return user_id

    def add_people(self) -> None:
        """Insert the admin, the engineers (with profiles) and the employees."""
        self.admin_id = self.add_user(*ADMIN, "admin")
        for name, email, specialty, shift, phone in ENGINEERS:
            user_id = self.add_user(name, email, "engineer")
            self.shifts[_first_name_key(name)] = shift
            self.conn.execute(
                "INSERT INTO engineer_profiles (user_id, specialty, shift, phone) VALUES (%s, %s, %s, %s)",
                (user_id, specialty, shift, phone),
            )
        for name, email in EMPLOYEES:
            self.add_user(name, email, "employee")

    def add_locations(self) -> None:
        """Insert buildings, floors and seats."""
        for building_name, address, floors in BUILDINGS:
            building_id = self.insert(
                "INSERT INTO buildings (name, address) VALUES (%s, %s) RETURNING id", (building_name, address)
            )
            for number, codes in floors.items():
                floor_id = self.insert(
                    "INSERT INTO floors (building_id, number) VALUES (%s, %s) RETURNING id", (building_id, number)
                )
                for code in codes:
                    seat_id = self.insert(
                        "INSERT INTO seats (floor_id, code) VALUES (%s, %s) RETURNING id", (floor_id, code)
                    )
                    self.seats[code] = (building_id, floor_id, seat_id)

    def event(self, incident_id: int, actor_id: int, event_type: str, at: datetime,
              from_value: str | None = None, to_value: str | None = None, reason: str | None = None) -> None:
        """Insert one audit event."""
        self.conn.execute(
            "INSERT INTO incident_events (incident_id, actor_id, type, from_value, to_value, reason, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (incident_id, actor_id, event_type, from_value, to_value, reason, at),
        )

    def note(self, incident_id: int, author_id: int, body: str, at: datetime) -> None:
        """Insert one note and its audit event."""
        self.conn.execute(
            "INSERT INTO incident_notes (incident_id, author_id, body, created_at) VALUES (%s, %s, %s, %s)",
            (incident_id, author_id, body, at),
        )
        self.event(incident_id, author_id, "note_added", at)

    def work_log(self, incident_id: int, engineer_id: int, at: datetime) -> None:
        """Insert one work log entry (0.5 to 4 hours, in 0.25 steps) and its audit event."""
        hours = self.rng.randint(2, 16) * 0.25
        self.conn.execute(
            "INSERT INTO incident_work_logs (incident_id, engineer_id, work_date, hours, description, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (incident_id, engineer_id, at.date(), hours, "Diagnosed and worked on the issue", at),
        )
        self.event(incident_id, engineer_id, "work_logged", at, to_value=str(hours))

    def ack_window(self, engineer: str, created_at: datetime) -> tuple[datetime, datetime]:
        """Return (ack time, shift end) for an engineer acknowledging a new ticket.

        The ack happens in the engineer's current or next shift, early enough
        that the ticket can be resolved (3 hours later) before the shift ends.
        """
        start, end = current_or_next_shift(self.shifts[engineer], created_at)
        acknowledged_at = max(start, created_at) + timedelta(minutes=30)
        if acknowledged_at + timedelta(hours=3) >= end:
            start, end = current_or_next_shift(self.shifts[engineer], end)
            acknowledged_at = start + timedelta(minutes=30)
        return acknowledged_at, end

    def add_incident(self, spec: dict) -> None:
        """Insert one incident plus the engineers, acks, notes, logs, requests and events it implies."""
        status = spec["status"]
        engineers = spec.get("engineers", [])
        acked_by = spec.get("acked_by")
        reporter_id = self.users[spec["reporter"]]
        building_id, floor_id, seat_id = self.seats[spec["seat"]]
        title, description = ISSUE_TEXT[spec["issue_type"]]
        priority_raise = spec.get("priority_raise")
        priority = priority_raise[1] if priority_raise else spec.get("priority", "medium")

        # Timeline. When acknowledged, work happens inside that shift so it is not a missed commitment.
        created_at = self.now - timedelta(days=spec["days_ago"], hours=self.rng.randint(0, 3))
        acknowledged_at = shift_ends_at = None
        if acked_by:
            acknowledged_at, shift_ends_at = self.ack_window(acked_by, created_at)
            assigned_at = acknowledged_at - timedelta(minutes=30)
            blocked_at = acknowledged_at + timedelta(hours=2)
            resolved_at = acknowledged_at + timedelta(hours=3)
        else:
            assigned_at = created_at + timedelta(hours=2)
            blocked_at = created_at + timedelta(hours=5)
            resolved_at = created_at + timedelta(days=1, hours=self.rng.randint(0, 20))
        closed_at = resolved_at + timedelta(days=1)

        if status == "open":
            assigned_at = None
        reached_resolved = status in ("resolved", "closed")
        request = spec.get("request")
        is_archived = request == ("close_approval", "approved")
        archived_at = closed_at + timedelta(hours=4) if is_archived else None
        void_reason = spec.get("void_reason")

        incident_id = self.insert(
            "INSERT INTO incidents (title, description, category, issue_type, priority, status, reporter_id,"
            " building_id, floor_id, seat_id, blocked_reason, created_at, updated_at, acknowledged_at,"
            " assigned_at, resolved_at, closed_at, is_archived, archived_at, archived_by,"
            " is_voided, void_reason, voided_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " RETURNING id",
            (title, description, _category_for(spec["issue_type"]), spec["issue_type"], priority, status,
             reporter_id, building_id, floor_id, seat_id, spec.get("blocked_reason"), created_at, created_at,
             acknowledged_at, assigned_at, resolved_at if reached_resolved else None,
             closed_at if status == "closed" else None, is_archived, archived_at,
             self.admin_id if is_archived else None, void_reason is not None, void_reason,
             self.admin_id if void_reason else None),
        )
        self.event(incident_id, reporter_id, "created", created_at, to_value="open")

        if priority_raise:
            self.event(incident_id, reporter_id, "priority_changed", created_at + timedelta(minutes=20),
                       from_value=priority_raise[0], to_value=priority_raise[1], reason=priority_raise[2])
        if void_reason:
            self.event(incident_id, self.admin_id, "voided", created_at + timedelta(hours=1), reason=void_reason)

        # Engineers join: the first is primary, the rest are helpers.
        for position, engineer in enumerate(engineers):
            engineer_id = self.users[engineer]
            joined_at = assigned_at + timedelta(hours=position)
            role = "primary" if position == 0 else "helper"
            self.conn.execute(
                "INSERT INTO incident_engineers (incident_id, engineer_id, role, added_by, added_at)"
                " VALUES (%s, %s, %s, %s, %s)",
                (incident_id, engineer_id, role, engineer_id, joined_at),
            )
            self.event(incident_id, engineer_id, "engineer_joined", joined_at, to_value=role)
        if engineers:
            primary_id = self.users[engineers[0]]
            self.event(incident_id, primary_id, "status_changed", assigned_at, "open", "in_progress")
            self.note(incident_id, primary_id, "I'm looking into this now.", assigned_at + timedelta(minutes=15))
            for position, engineer in enumerate(engineers):
                self.work_log(incident_id, self.users[engineer], assigned_at + timedelta(hours=position + 1))

        if acked_by:
            self.conn.execute(
                "INSERT INTO incident_acks (incident_id, engineer_id, acknowledged_at, shift_ends_at)"
                " VALUES (%s, %s, %s, %s)",
                (incident_id, self.users[acked_by], acknowledged_at, shift_ends_at),
            )
            self.event(incident_id, self.users[acked_by], "acknowledged", acknowledged_at)

        if status == "blocked":
            self.event(incident_id, primary_id, "status_changed", blocked_at, "in_progress", "blocked",
                       reason=spec["blocked_reason"])

        if reached_resolved:
            self.note(incident_id, primary_id, "Resolved: fixed the issue and tested it with the reporter.",
                      resolved_at)
            self.event(incident_id, primary_id, "status_changed", resolved_at, "in_progress", "resolved")

        if request:
            self.add_request(incident_id, reporter_id, request, resolved_at, closed_at, archived_at)

        last_event = self.conn.execute(
            "SELECT max(created_at) AS at FROM incident_events WHERE incident_id = %s", (incident_id,)
        ).fetchone()["at"]
        self.conn.execute("UPDATE incidents SET updated_at = %s WHERE id = %s", (last_event, incident_id))

    def add_request(self, incident_id: int, reporter_id: int, request: tuple[str, str],
                    resolved_at: datetime, closed_at: datetime, archived_at: datetime | None) -> None:
        """Insert a close-approval or reopen request and the events around it."""
        request_type, request_status = request
        if request_type == "reopen":
            requested_at = resolved_at + timedelta(days=1)
            reason = "The problem came back."
        else:
            # The reporter closes the ticket, which asks the admin for approval.
            requested_at = closed_at
            reason = None
            self.event(incident_id, reporter_id, "status_changed", closed_at, "resolved", "closed")

        decided = request_status != "pending"
        decided_at = requested_at + timedelta(hours=4) if decided else None
        decision_note = "Please confirm the audio is stable with the team first." if request_status == "rejected" else None
        self.conn.execute(
            "INSERT INTO incident_requests (incident_id, type, reason, status, requested_by, requested_at,"
            " decided_by, decided_at, decision_note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (incident_id, request_type, reason, request_status, reporter_id, requested_at,
             self.admin_id if decided else None, decided_at, decision_note),
        )
        self.event(incident_id, reporter_id, "request_created", requested_at, to_value=request_type, reason=reason)

        if decided:
            self.event(incident_id, self.admin_id, "request_decided", decided_at, request_type, request_status,
                       reason=decision_note)
        if request_status == "rejected":
            self.event(incident_id, self.admin_id, "status_changed", decided_at, "closed", "resolved",
                       reason=decision_note)
        if archived_at:
            self.event(incident_id, self.admin_id, "archived", archived_at)


def seed_if_empty(conn: psycopg.Connection) -> None:
    """
    Insert all demo data if the users table is empty.

    Runs in a single transaction with an advisory lock, so a partial seed is
    never left behind and two containers never seed at the same time.
    """
    password = os.getenv("SEED_PASSWORD", "")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (SEED_LOCK_ID,))
        if conn.execute("SELECT EXISTS (SELECT 1 FROM users) AS has_users").fetchone()["has_users"]:
            return
        if not password:
            logger.warning("Users table is empty but SEED_PASSWORD is not set; skipping seed data")
            return

        logger.info("Seeding demo data")
        # All seed users share one password, so hash it once (bcrypt is slow on purpose).
        seeder = _Seeder(conn, hash_password(password))
        seeder.add_people()
        seeder.add_locations()
        for spec in INCIDENTS:
            seeder.add_incident(spec)
        logger.info("Seeded %d users and %d incidents", len(seeder.users), len(INCIDENTS))
