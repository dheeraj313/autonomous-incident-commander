from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .metrics_client import detect_anomalies
from .models import DependencyGraph, RootCauseReport, ServiceAnomaly
from .root_cause import rank_root_causes
from .tempo_client import build_dependency_graph

app = FastAPI(title="AIC Causal Analysis Engine", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "UP"}


@app.get("/dependency-graph", response_model=DependencyGraph)
async def dependency_graph(lookback_minutes: int | None = None, max_traces: int | None = None):
    """Service dependency graph mined from recent Tempo traces."""
    return await build_dependency_graph(lookback_minutes, max_traces)


@app.get("/anomalies", response_model=list[ServiceAnomaly])
async def anomalies():
    """Per-service anomaly detection (error rate / latency vs. rolling baseline)."""
    return await detect_anomalies()


@app.get("/root-cause", response_model=RootCauseReport)
async def root_cause(lookback_minutes: int | None = None, max_traces: int | None = None):
    """Combines the dependency graph + anomaly detection into a ranked root-cause report."""
    graph = await build_dependency_graph(lookback_minutes, max_traces)
    service_anomalies = await detect_anomalies(graph.nodes or None)
    ranked = rank_root_causes(graph, service_anomalies)
    return RootCauseReport(
        incident_detected=any(a.is_anomalous for a in service_anomalies),
        ranked_causes=ranked,
        anomalies=service_anomalies,
        graph=graph,
    )
