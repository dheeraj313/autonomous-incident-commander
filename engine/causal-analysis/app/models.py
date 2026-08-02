from typing import Optional

from pydantic import BaseModel


class DependencyEdge(BaseModel):
    caller: str
    callee: str
    call_count: int
    error_count: int
    avg_latency_ms: float


class DependencyGraph(BaseModel):
    nodes: list[str]
    edges: list[DependencyEdge]
    traces_inspected: int


class ServiceAnomaly(BaseModel):
    service: str
    recent_request_rate: float
    recent_error_rate: float
    baseline_error_rate: float
    recent_avg_latency_ms: Optional[float] = None
    baseline_avg_latency_ms: Optional[float] = None
    latency_ratio: Optional[float] = None
    is_anomalous: bool
    severity: float
    reasons: list[str]


class RootCauseCandidate(BaseModel):
    service: str
    score: float
    reasons: list[str]


class RootCauseReport(BaseModel):
    incident_detected: bool
    ranked_causes: list[RootCauseCandidate]
    anomalies: list[ServiceAnomaly]
    graph: DependencyGraph
