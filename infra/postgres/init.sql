-- Creates one schema per bounded context inside the single "aic" database.
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS orders;
CREATE SCHEMA IF NOT EXISTS inventory;
CREATE SCHEMA IF NOT EXISTS payments;
CREATE SCHEMA IF NOT EXISTS notifications;
CREATE SCHEMA IF NOT EXISTS incidents;

-- Incident event store (event-sourcing style, append-only).
CREATE TABLE IF NOT EXISTS incidents.incident_events (
    id              BIGSERIAL PRIMARY KEY,
    incident_id     UUID NOT NULL,
    sequence_no      INT NOT NULL,
    event_type      VARCHAR(64) NOT NULL, -- e.g. DETECTED, ROOT_CAUSE_RANKED, ACTION_PROPOSED, ACTION_APPROVED, ACTION_EXECUTED, ACTION_VERIFIED, RESOLVED
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (incident_id, sequence_no)
);

CREATE INDEX IF NOT EXISTS idx_incident_events_incident_id
    ON incidents.incident_events (incident_id);
