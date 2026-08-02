from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class EventType(str, Enum):
    DETECTED = "DETECTED"
    ROOT_CAUSE_RANKED = "ROOT_CAUSE_RANKED"
    ACTION_PROPOSED = "ACTION_PROPOSED"
    ACTION_SKIPPED = "ACTION_SKIPPED"
    ACTION_APPROVED = "ACTION_APPROVED"
    ACTION_EXECUTED = "ACTION_EXECUTED"
    ACTION_REJECTED = "ACTION_REJECTED"
    ACTION_FAILED = "ACTION_FAILED"
    RESOLVED = "RESOLVED"


class IncidentEvent(BaseModel):
    sequence_no: int
    event_type: str
    payload: dict
    created_at: datetime


class IncidentSummary(BaseModel):
    incident_id: UUID
    started_at: datetime
    last_event_at: datetime
    event_count: int
    status: str
    top_root_cause: str | None = None


class StartIncidentRequest(BaseModel):
    # Optional: pass a root-cause report directly (e.g. for testing/replay) instead
    # of having this engine fetch a live one from the causal-analysis engine.
    root_cause_report: dict | None = None
    lookback_minutes: int | None = None
    max_traces: int | None = None


class IncidentDetail(BaseModel):
    incident_id: UUID
    events: list[IncidentEvent]
