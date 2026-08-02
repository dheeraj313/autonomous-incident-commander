"""Builds a caller -> callee service dependency graph by mining recent Tempo traces.

Tempo's `/api/traces/{traceID}` endpoint returns the trace as OTLP-JSON: a list
of `batches`, each with a `resource` (attributes incl. `service.name`) and one
or more `scopeSpans[].spans[]`. Span IDs are base64 strings, unique within a
trace, and a span's `parentSpanId` (absent on the root span) lets us walk the
call tree. We infer a cross-service edge whenever a span's parent belongs to a
*different* service than the span itself (i.e. a network hop, not an in-process
child span).
"""

import time
from collections import defaultdict

import httpx

from . import config
from .models import DependencyEdge, DependencyGraph


def _attr_value(value: dict):
    for key in ("stringValue", "intValue", "boolValue", "doubleValue"):
        if key in value:
            return value[key]
    return None


def _resource_service_name(resource: dict) -> str:
    for attr in resource.get("attributes", []):
        if attr.get("key") == "service.name":
            return _attr_value(attr.get("value", {})) or "unknown"
    return "unknown"


def _is_error(span: dict) -> bool:
    return span.get("status", {}).get("code") == "STATUS_CODE_ERROR"


def _duration_ms(span: dict) -> float:
    try:
        start = int(span["startTimeUnixNano"])
        end = int(span["endTimeUnixNano"])
        return max(0.0, (end - start) / 1_000_000.0)
    except (KeyError, ValueError, TypeError):
        return 0.0


def _iter_spans(trace: dict):
    """Yields (service_name, span_dict) for every span in a Tempo trace document."""
    for batch in trace.get("batches", []):
        service_name = _resource_service_name(batch.get("resource", {}))
        # OTLP field was renamed instrumentationLibrarySpans -> scopeSpans; accept either.
        scope_spans = batch.get("scopeSpans") or batch.get("instrumentationLibrarySpans") or []
        for scope in scope_spans:
            for span in scope.get("spans", []):
                yield service_name, span


async def search_recent_trace_ids(client: httpx.AsyncClient, lookback_minutes: int, limit: int) -> list[str]:
    end = int(time.time())
    start = end - lookback_minutes * 60
    # A plain, unfiltered /api/search returns the most-recent-N traces across the whole
    # stack. Prometheus's ~15s health-check scrapes of every service generate far more
    # traces than real business traffic, so an unfiltered search of the top N is almost
    # entirely actuator noise and misses real cross-service call chains. Restrict to
    # traces that pass through the gateway on a real (non-actuator) route instead.
    resp = await client.get(
        f"{config.TEMPO_URL}/api/search",
        params={
            "q": config.DEPENDENCY_GRAPH_TRACEQL_FILTER,
            "limit": limit,
            "start": start,
            "end": end,
        },
    )
    resp.raise_for_status()
    return [t["traceID"] for t in resp.json().get("traces", [])]


async def fetch_trace(client: httpx.AsyncClient, trace_id: str) -> dict | None:
    resp = await client.get(f"{config.TEMPO_URL}/api/traces/{trace_id}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def build_dependency_graph_from_traces(traces: list[dict]) -> DependencyGraph:
    span_index: dict[str, str] = {}  # spanId -> service_name
    for trace in traces:
        for service_name, span in _iter_spans(trace):
            span_id = span.get("spanId")
            if span_id:
                span_index[span_id] = service_name

    edge_stats: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"call_count": 0, "error_count": 0, "total_latency_ms": 0.0}
    )
    nodes: set[str] = set()

    for trace in traces:
        for service_name, span in _iter_spans(trace):
            nodes.add(service_name)
            parent_id = span.get("parentSpanId")
            if not parent_id or parent_id not in span_index:
                continue
            parent_service = span_index[parent_id]
            if parent_service == service_name:
                continue  # in-process parent/child span, not a network hop
            stats = edge_stats[(parent_service, service_name)]
            stats["call_count"] += 1
            if _is_error(span):
                stats["error_count"] += 1
            stats["total_latency_ms"] += _duration_ms(span)

    edges = [
        DependencyEdge(
            caller=caller,
            callee=callee,
            call_count=stats["call_count"],
            error_count=stats["error_count"],
            avg_latency_ms=round(stats["total_latency_ms"] / stats["call_count"], 2) if stats["call_count"] else 0.0,
        )
        for (caller, callee), stats in edge_stats.items()
    ]

    return DependencyGraph(nodes=sorted(nodes), edges=edges, traces_inspected=len(traces))


async def build_dependency_graph(lookback_minutes: int | None = None, max_traces: int | None = None) -> DependencyGraph:
    lookback_minutes = lookback_minutes or config.DEPENDENCY_GRAPH_LOOKBACK_MINUTES
    max_traces = max_traces or config.DEPENDENCY_GRAPH_MAX_TRACES
    async with httpx.AsyncClient(timeout=10.0) as client:
        trace_ids = await search_recent_trace_ids(client, lookback_minutes, max_traces)
        traces = []
        for trace_id in trace_ids:
            trace = await fetch_trace(client, trace_id)
            if trace:
                traces.append(trace)
    return build_dependency_graph_from_traces(traces)
