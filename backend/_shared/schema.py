"""
Database schema for the incident management app.

Every statement uses IF NOT EXISTS, so running it on each cold start is safe:
existing tables and data are left untouched.

The constraints here are a second line of defense behind the validation in
the services: NOT NULL, foreign keys, UNIQUE and CHECK for every enum.
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('employee', 'engineer', 'admin')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS engineer_profiles (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER NOT NULL UNIQUE REFERENCES users(id),
    specialty    TEXT NOT NULL CHECK (specialty IN ('facilities', 'IT', 'AV', 'security')),
    shift        TEXT NOT NULL CHECK (shift IN ('day', 'swing', 'night')),
    is_available BOOLEAN NOT NULL DEFAULT true,
    phone        TEXT
);

CREATE TABLE IF NOT EXISTS buildings (
    id      SERIAL PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    address TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS floors (
    id          SERIAL PRIMARY KEY,
    building_id INTEGER NOT NULL REFERENCES buildings(id),
    number      INTEGER NOT NULL,
    UNIQUE (building_id, number)
);

CREATE TABLE IF NOT EXISTS seats (
    id       SERIAL PRIMARY KEY,
    floor_id INTEGER NOT NULL REFERENCES floors(id),
    code     TEXT NOT NULL,
    UNIQUE (floor_id, code)
);

CREATE TABLE IF NOT EXISTS incidents (
    id              SERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN ('facilities', 'IT', 'AV', 'security')),
    issue_type      TEXT NOT NULL,
    priority        TEXT NOT NULL DEFAULT 'medium'
                    CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'in_progress', 'blocked', 'resolved', 'closed')),
    reporter_id     INTEGER NOT NULL REFERENCES users(id),
    building_id     INTEGER NOT NULL REFERENCES buildings(id),
    floor_id        INTEGER NOT NULL REFERENCES floors(id),
    seat_id         INTEGER REFERENCES seats(id),
    blocked_reason  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at TIMESTAMPTZ,
    assigned_at     TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    closed_at       TIMESTAMPTZ,
    is_archived     BOOLEAN NOT NULL DEFAULT false,
    archived_at     TIMESTAMPTZ,
    archived_by     INTEGER REFERENCES users(id),
    is_voided       BOOLEAN NOT NULL DEFAULT false,
    void_reason     TEXT,
    voided_by       INTEGER REFERENCES users(id),
    -- Optimistic locking: every update must send the version it loaded and bump it.
    version         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS incident_engineers (
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    engineer_id INTEGER NOT NULL REFERENCES users(id),
    role        TEXT NOT NULL CHECK (role IN ('primary', 'helper')),
    added_by    INTEGER NOT NULL REFERENCES users(id),
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (incident_id, engineer_id)
);

CREATE TABLE IF NOT EXISTS incident_acks (
    id              SERIAL PRIMARY KEY,
    incident_id     INTEGER NOT NULL REFERENCES incidents(id),
    engineer_id     INTEGER NOT NULL REFERENCES users(id),
    acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    shift_ends_at   TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS incident_requests (
    id            SERIAL PRIMARY KEY,
    incident_id   INTEGER NOT NULL REFERENCES incidents(id),
    type          TEXT NOT NULL CHECK (type IN ('reopen', 'close_approval')),
    reason        TEXT,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_by  INTEGER NOT NULL REFERENCES users(id),
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_by    INTEGER REFERENCES users(id),
    decided_at    TIMESTAMPTZ,
    decision_note TEXT
);

CREATE TABLE IF NOT EXISTS incident_notes (
    id          SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    author_id   INTEGER NOT NULL REFERENCES users(id),
    body        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    edited_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS incident_work_logs (
    id          SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    engineer_id INTEGER NOT NULL REFERENCES users(id),
    work_date   DATE NOT NULL,
    hours       NUMERIC(4, 2) NOT NULL CHECK (hours > 0 AND hours <= 12),
    description TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    edited_at   TIMESTAMPTZ
);

-- Audit log: one row for every change made to an incident.
CREATE TABLE IF NOT EXISTS incident_events (
    id          SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    actor_id    INTEGER NOT NULL REFERENCES users(id),
    type        TEXT NOT NULL,
    from_value  TEXT,
    to_value    TEXT,
    reason      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents (status);
CREATE INDEX IF NOT EXISTS idx_incidents_reporter ON incidents (reporter_id);
-- Recurring-issue lookups: same issue type at the same location within N days.
CREATE INDEX IF NOT EXISTS idx_incidents_location
    ON incidents (building_id, floor_id, seat_id, issue_type, created_at);
CREATE INDEX IF NOT EXISTS idx_incident_engineers_engineer ON incident_engineers (engineer_id);
CREATE INDEX IF NOT EXISTS idx_incident_events_incident ON incident_events (incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_notes_incident ON incident_notes (incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_work_logs_incident ON incident_work_logs (incident_id);

-- At most one pending request of each type (reopen / close_approval) per incident.
CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_requests_pending
    ON incident_requests (incident_id, type) WHERE status = 'pending';
-- An engineer acknowledges a ticket at most once per shift.
CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_acks_shift
    ON incident_acks (incident_id, engineer_id, shift_ends_at);
"""
