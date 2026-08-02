"""Unit tests for detect_service_anomaly() using a fake httpx.AsyncClient so no
real Prometheus is needed. Requests are told apart by inspecting the PromQL
query string for which metric/window they're asking about."""

import pytest

from app import config
from app.metrics_client import detect_service_anomaly


class _FakeResponse:
    def __init__(self, value):
        self._value = value

    def raise_for_status(self):
        pass

    def json(self):
        if self._value is None:
            return {"data": {"result": []}}
        return {"data": {"result": [{"value": [0, str(self._value)]}]}}


class _FakeClient:
    """Maps PromQL query substrings -> canned values, keyed by window."""

    def __init__(self, values: dict[str, float | None]):
        self._values = values

    async def get(self, url, params):
        query = params["query"]
        window = config.ANOMALY_RECENT_WINDOW if f"[{config.ANOMALY_RECENT_WINDOW}]" in query else config.ANOMALY_BASELINE_WINDOW
        if "SERVER_ERROR" in query:
            key = f"error_{window}"
        elif "_sum{" in query:
            key = f"latency_{window}"
        else:
            key = f"rate_{window}"
        return _FakeResponse(self._values.get(key))


@pytest.mark.asyncio
async def test_healthy_service_is_not_anomalous():
    recent, baseline = config.ANOMALY_RECENT_WINDOW, config.ANOMALY_BASELINE_WINDOW
    client = _FakeClient(
        {
            f"rate_{recent}": 10.0,
            f"error_{recent}": 0.01,
            f"error_{baseline}": 0.01,
            f"latency_{recent}": 0.05,
            f"latency_{baseline}": 0.05,
        }
    )

    anomaly = await detect_service_anomaly(client, "orders-service")

    assert anomaly.is_anomalous is False
    assert anomaly.severity == 0.0
    assert anomaly.reasons == []


@pytest.mark.asyncio
async def test_high_error_rate_flagged_as_anomalous():
    recent, baseline = config.ANOMALY_RECENT_WINDOW, config.ANOMALY_BASELINE_WINDOW
    client = _FakeClient(
        {
            f"rate_{recent}": 10.0,
            f"error_{recent}": 0.9,
            f"error_{baseline}": 0.01,
            f"latency_{recent}": 0.05,
            f"latency_{baseline}": 0.05,
        }
    )

    anomaly = await detect_service_anomaly(client, "inventory-service")

    assert anomaly.is_anomalous is True
    assert any("error rate" in reason for reason in anomaly.reasons)


@pytest.mark.asyncio
async def test_low_traffic_service_never_flagged_anomalous():
    # Below ANOMALY_MIN_REQUEST_RATE - even with a terrible error rate this
    # should be ignored as noise (too few requests to be meaningful).
    recent, baseline = config.ANOMALY_RECENT_WINDOW, config.ANOMALY_BASELINE_WINDOW
    client = _FakeClient(
        {
            f"rate_{recent}": 0.001,
            f"error_{recent}": 1.0,
            f"error_{baseline}": 1.0,
            f"latency_{recent}": None,
            f"latency_{baseline}": None,
        }
    )

    anomaly = await detect_service_anomaly(client, "payments-service")

    assert anomaly.is_anomalous is False


@pytest.mark.asyncio
async def test_latency_spike_flagged_as_anomalous():
    recent, baseline = config.ANOMALY_RECENT_WINDOW, config.ANOMALY_BASELINE_WINDOW
    client = _FakeClient(
        {
            f"rate_{recent}": 10.0,
            f"error_{recent}": 0.0,
            f"error_{baseline}": 0.0,
            f"latency_{recent}": 1.0,
            f"latency_{baseline}": 0.1,
        }
    )

    anomaly = await detect_service_anomaly(client, "notifications-service")

    assert anomaly.is_anomalous is True
    assert anomaly.latency_ratio == pytest.approx(10.0)
