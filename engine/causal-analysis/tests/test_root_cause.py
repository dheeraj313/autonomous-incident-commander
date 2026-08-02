"""Unit tests for rank_root_causes(): a pure function, so these are
constructed directly against the Pydantic models with no mocking needed."""

from app.models import DependencyEdge, DependencyGraph, ServiceAnomaly
from app.root_cause import rank_root_causes


def _anomaly(service: str, is_anomalous: bool = True, severity: float = 1.0) -> ServiceAnomaly:
    return ServiceAnomaly(
        service=service,
        recent_request_rate=1.0,
        recent_error_rate=0.5,
        baseline_error_rate=0.01,
        is_anomalous=is_anomalous,
        severity=severity,
        reasons=["error rate elevated"] if is_anomalous else [],
    )


def test_no_anomalies_returns_empty_list():
    graph = DependencyGraph(nodes=["a", "b"], edges=[], traces_inspected=10)
    assert rank_root_causes(graph, []) == []


def test_single_anomalous_service_with_no_edges():
    graph = DependencyGraph(nodes=["inventory-service"], edges=[], traces_inspected=5)
    anomalies = [_anomaly("inventory-service", severity=2.0)]

    candidates = rank_root_causes(graph, anomalies)

    assert len(candidates) == 1
    assert candidates[0].service == "inventory-service"
    assert candidates[0].score == 2.0
    assert "error rate elevated" in candidates[0].reasons


def test_upstream_anomalous_caller_gets_propagation_bonus():
    # orders-service calls inventory-service; both are anomalous.
    # inventory-service (the callee, deeper in the chain) should score higher
    # than orders-service since it has an anomalous upstream caller boosting
    # its score, while orders-service has an anomalous downstream callee
    # penalizing its score.
    graph = DependencyGraph(
        nodes=["orders-service", "inventory-service"],
        edges=[
            DependencyEdge(
                caller="orders-service",
                callee="inventory-service",
                call_count=100,
                error_count=50,
                avg_latency_ms=200.0,
            )
        ],
        traces_inspected=100,
    )
    anomalies = [_anomaly("orders-service", severity=1.0), _anomaly("inventory-service", severity=1.0)]

    candidates = rank_root_causes(graph, anomalies)
    by_service = {c.service: c for c in candidates}

    assert by_service["inventory-service"].score > by_service["orders-service"].score
    assert any("upstream caller" in reason for reason in by_service["inventory-service"].reasons)
    assert any("downstream callee" in reason for reason in by_service["orders-service"].reasons)


def test_non_anomalous_services_excluded_from_candidates():
    graph = DependencyGraph(nodes=["a", "b"], edges=[], traces_inspected=1)
    anomalies = [_anomaly("a", is_anomalous=True), _anomaly("b", is_anomalous=False)]

    candidates = rank_root_causes(graph, anomalies)

    assert [c.service for c in candidates] == ["a"]


def test_candidates_sorted_by_score_descending():
    graph = DependencyGraph(nodes=["a", "b"], edges=[], traces_inspected=1)
    anomalies = [_anomaly("a", severity=1.0), _anomaly("b", severity=5.0)]

    candidates = rank_root_causes(graph, anomalies)

    assert [c.service for c in candidates] == ["b", "a"]
