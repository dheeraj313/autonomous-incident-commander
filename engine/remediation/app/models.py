from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    TRIP_CIRCUIT_BREAKER = "TRIP_CIRCUIT_BREAKER"
    CLEAR_FAULT_INJECTION = "CLEAR_FAULT_INJECTION"
    RESTART_SERVICE = "RESTART_SERVICE"


class ActionStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class RemediationAction(BaseModel):
    id: str
    service: str
    action_type: ActionType
    reason: str
    requires_approval: bool
    status: ActionStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: datetime | None = None
    result: str | None = None


class SkippedCandidate(BaseModel):
    service: str
    action_type: ActionType
    reason: str


class RemediateRequest(BaseModel):
    # Optional: pass a root-cause report directly (e.g. for testing/replay) instead
    # of having this engine fetch a live one from the causal-analysis engine.
    root_cause_report: dict | None = None
    lookback_minutes: int | None = None
    max_traces: int | None = None


class RemediationResponse(BaseModel):
    incident_detected: bool
    actions: list[RemediationAction]
    skipped: list[SkippedCandidate]
