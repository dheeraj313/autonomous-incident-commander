"""Unit tests for decide_actions(): a pure function operating on plain
dict/list input, so these need no mocking."""

from app.models import ActionType
from app.policy import decide_actions


def _cause(service: str, reasons: list[str]) -> dict:
    return {"service": service, "reasons": reasons}


def test_error_rate_on_circuit_breaker_capable_service_trips_breaker():
    report = {"ranked_causes": [_cause("inventory-service", ["error rate 90% >= threshold 10%"])]}

    candidates, skipped = decide_actions(report)

    assert skipped == []
    assert len(candidates) == 1
    assert candidates[0]["service"] == "inventory-service"
    assert candidates[0]["action_type"] == ActionType.TRIP_CIRCUIT_BREAKER


def test_error_rate_on_non_circuit_breaker_service_clears_fault_injection():
    report = {"ranked_causes": [_cause("auth-service", ["error rate 90% >= threshold 10%"])]}

    candidates, skipped = decide_actions(report)

    assert skipped == []
    assert candidates[0]["action_type"] == ActionType.CLEAR_FAULT_INJECTION


def test_latency_only_restarts_service():
    report = {"ranked_causes": [_cause("notifications-service", ["latency 3.0x baseline (>= 2.0x)"])]}

    candidates, skipped = decide_actions(report)

    assert skipped == []
    assert candidates[0]["action_type"] == ActionType.RESTART_SERVICE


def test_no_matching_reason_is_skipped():
    report = {"ranked_causes": [_cause("payments-service", ["something unrelated"])]}

    candidates, skipped = decide_actions(report)

    assert candidates == []
    assert len(skipped) == 1
    assert skipped[0].service == "payments-service"


def test_blast_radius_limit_skips_extra_services():
    # BLAST_RADIUS_MAX_SERVICES defaults to 2 - a 3rd ranked cause should be
    # reported as skipped regardless of whether it would otherwise match a rule.
    report = {
        "ranked_causes": [
            _cause("inventory-service", ["error rate 90% >= threshold 10%"]),
            _cause("payments-service", ["error rate 80% >= threshold 10%"]),
            _cause("auth-service", ["error rate 70% >= threshold 10%"]),
        ]
    }

    candidates, skipped = decide_actions(report)

    assert len(candidates) == 2
    assert len(skipped) == 1
    assert skipped[0].service == "auth-service"
    assert "blast radius limit" in skipped[0].reason


def test_empty_ranked_causes_returns_nothing():
    candidates, skipped = decide_actions({"ranked_causes": []})

    assert candidates == []
    assert skipped == []
