"""Unit tests for generate(): a pure function over a list of plain event
dicts, so these need no mocking - just constructed fixtures."""

from datetime import datetime, timedelta, timezone

from app.postmortem import generate

_T0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _event(seq, event_type, payload, offset_seconds=0):
    return {
        "sequence_no": seq,
        "event_type": event_type,
        "payload": payload,
        "created_at": _T0 + timedelta(seconds=offset_seconds),
    }


def test_no_events_returns_placeholder():
    result = generate("incident-1", [])

    assert "No events recorded." in result
    assert "incident-1" in result


def test_full_sequence_renders_all_sections():
    events = [
        _event(1, "DETECTED", {"anomalies": [{"service": "inventory-service"}]}, 0),
        _event(
            2,
            "ROOT_CAUSE_RANKED",
            {"ranked_causes": [{"service": "inventory-service", "score": 2.5, "reasons": ["error rate high"]}]},
            1,
        ),
        _event(
            3,
            "ACTION_EXECUTED",
            {
                "id": "a1",
                "action_type": "TRIP_CIRCUIT_BREAKER",
                "service": "inventory-service",
                "status": "EXECUTED",
                "result": "breaker tripped",
                "reason": "error rate high",
            },
            2,
        ),
        _event(
            4,
            "ACTION_SKIPPED",
            {"action_type": "RESTART_SERVICE", "service": "payments-service", "reason": "blast radius limit reached"},
            3,
        ),
        _event(5, "RESOLVED", {"note": "breaker cleared manually"}, 30),
    ]

    result = generate("incident-2", events)

    assert "**Status:** RESOLVED" in result
    assert "`inventory-service` \u2014 score 2.50 **(top cause)**" in result
    assert "TRIP_CIRCUIT_BREAKER` on `inventory-service`: **EXECUTED** \u2014 breaker tripped" in result
    assert "RESTART_SERVICE` on `payments-service` skipped: blast radius limit reached" in result
    assert "Resolved at" in result
    assert result.count("| 1 |") == 1
    assert result.count("| 5 |") == 1


def test_unresolved_incident_shows_last_event_as_status():
    events = [
        _event(1, "DETECTED", {"anomalies": []}, 0),
        _event(
            2,
            "ACTION_PROPOSED",
            {
                "id": "a1",
                "action_type": "RESTART_SERVICE",
                "service": "notifications-service",
                "status": "PENDING_APPROVAL",
                "reason": "latency spike",
            },
            1,
        ),
    ]

    result = generate("incident-3", events)

    assert "**Status:** ACTION_PROPOSED" in result
    assert "Not yet resolved." in result


def test_no_root_cause_or_actions_renders_fallback_text():
    events = [_event(1, "DETECTED", {"anomalies": []}, 0), _event(2, "RESOLVED", {}, 5)]

    result = generate("incident-4", events)

    assert "No root cause candidates were ranked." in result
    assert "No remediation actions were proposed." in result
    assert "- None." in result
