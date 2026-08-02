"""Unit tests for start_incident()/sync_incident() using monkeypatched
db.append_event/db.fetch_events and a fake httpx.AsyncClient (no real Postgres
or remediation-engine needed)."""

from unittest.mock import AsyncMock

import pytest

from app import db, orchestrator


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeHttpClient:
    def __init__(self, post_response=None, get_responses=None):
        self._post_response = post_response
        self._get_responses = get_responses or {}

    async def post(self, url, json=None, headers=None):
        return self._post_response

    async def get(self, url, params=None):
        return self._get_responses.get(url, _FakeResponse({}, status_code=404))


@pytest.mark.asyncio
async def test_start_incident_no_anomalies_returns_not_detected(monkeypatch):
    monkeypatch.setattr(db, "append_event", AsyncMock())

    result = await orchestrator.start_incident(
        pool=None,
        http_client=_FakeHttpClient(),
        root_cause_report={"incident_detected": False},
        lookback_minutes=None,
        max_traces=None,
    )

    assert result == {"incident_detected": False, "incident_id": None}
    db.append_event.assert_not_called()


@pytest.mark.asyncio
async def test_start_incident_persists_events_and_returns_remediation(monkeypatch):
    append_event_mock = AsyncMock()
    monkeypatch.setattr(db, "append_event", append_event_mock)

    remediation_payload = {
        "actions": [
            {
                "id": "a1",
                "service": "inventory-service",
                "action_type": "TRIP_CIRCUIT_BREAKER",
                "status": "EXECUTED",
                "reason": "error rate high",
            }
        ],
        "skipped": [{"service": "payments-service", "action_type": "RESTART_SERVICE", "reason": "blast radius"}],
    }
    client = _FakeHttpClient(post_response=_FakeResponse(remediation_payload))

    root_cause_report = {
        "incident_detected": True,
        "anomalies": [{"service": "inventory-service"}],
        "ranked_causes": [{"service": "inventory-service", "score": 2.0}],
    }

    result = await orchestrator.start_incident(
        pool=None,
        http_client=client,
        root_cause_report=root_cause_report,
        lookback_minutes=None,
        max_traces=None,
    )

    assert result["incident_detected"] is True
    assert result["remediation"] == remediation_payload
    # DETECTED, ROOT_CAUSE_RANKED, ACTION_PROPOSED, ACTION_EXECUTED, ACTION_SKIPPED
    assert append_event_mock.call_count == 5


@pytest.mark.asyncio
async def test_sync_incident_returns_none_when_no_events(monkeypatch):
    monkeypatch.setattr(db, "fetch_events", AsyncMock(return_value=[]))

    result = await orchestrator.sync_incident(pool=None, http_client=_FakeHttpClient(), incident_id="incident-1")

    assert result is None


@pytest.mark.asyncio
async def test_sync_incident_detects_status_transition(monkeypatch):
    existing_events = [
        {
            "event_type": "ACTION_PROPOSED",
            "payload": {"id": "a1", "status": "PENDING_APPROVAL"},
        }
    ]
    monkeypatch.setattr(db, "fetch_events", AsyncMock(return_value=existing_events))
    append_event_mock = AsyncMock(return_value={"event_type": "ACTION_EXECUTED"})
    monkeypatch.setattr(db, "append_event", append_event_mock)

    action_url = f"{orchestrator.config.REMEDIATION_URL}/actions/a1"
    client = _FakeHttpClient(
        get_responses={action_url: _FakeResponse({"id": "a1", "status": "EXECUTED"})}
    )

    result = await orchestrator.sync_incident(pool=None, http_client=client, incident_id="incident-1")

    assert result["all_actions_terminal"] is True
    assert len(result["new_events"]) == 1
    append_event_mock.assert_called_once()
