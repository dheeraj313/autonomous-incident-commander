"""Anomaly detection against Prometheus: compares a short "recent" window
against a longer "baseline" window per service, for both error rate and
average latency, using the same `http_server_requests_seconds_{count,sum}`
Micrometer/Actuator metrics every Spring Boot service already exposes.
"""

import httpx

from . import config
from .models import ServiceAnomaly

_ERROR_RATE_QUERY = (
    'sum(rate(http_server_requests_seconds_count{{service="{service}",outcome="SERVER_ERROR"}}[{window}])) '
    '/ sum(rate(http_server_requests_seconds_count{{service="{service}"}}[{window}]))'
)
_TOTAL_RATE_QUERY = 'sum(rate(http_server_requests_seconds_count{{service="{service}"}}[{window}]))'
_AVG_LATENCY_QUERY = (
    'sum(rate(http_server_requests_seconds_sum{{service="{service}"}}[{window}])) '
    '/ sum(rate(http_server_requests_seconds_count{{service="{service}"}}[{window}]))'
)


async def _instant_query(client: httpx.AsyncClient, promql: str) -> float | None:
    resp = await client.get(f"{config.PROMETHEUS_URL}/api/v1/query", params={"query": promql})
    resp.raise_for_status()
    result = resp.json().get("data", {}).get("result", [])
    if not result:
        return None
    try:
        value = float(result[0]["value"][1])
    except (TypeError, ValueError, KeyError, IndexError):
        return None
    return value if value == value else None  # filter out NaN (0/0 division in PromQL)


async def detect_service_anomaly(client: httpx.AsyncClient, service: str) -> ServiceAnomaly:
    recent_window = config.ANOMALY_RECENT_WINDOW
    baseline_window = config.ANOMALY_BASELINE_WINDOW

    recent_rate = await _instant_query(client, _TOTAL_RATE_QUERY.format(service=service, window=recent_window)) or 0.0
    recent_err = await _instant_query(client, _ERROR_RATE_QUERY.format(service=service, window=recent_window)) or 0.0
    baseline_err = await _instant_query(client, _ERROR_RATE_QUERY.format(service=service, window=baseline_window)) or 0.0
    recent_lat = await _instant_query(client, _AVG_LATENCY_QUERY.format(service=service, window=recent_window))
    baseline_lat = await _instant_query(client, _AVG_LATENCY_QUERY.format(service=service, window=baseline_window))

    latency_ratio = None
    if recent_lat is not None and baseline_lat:
        latency_ratio = recent_lat / baseline_lat

    has_traffic = recent_rate >= config.ANOMALY_MIN_REQUEST_RATE
    reasons: list[str] = []
    severity = 0.0

    if has_traffic and recent_err >= config.ANOMALY_ERROR_RATE_THRESHOLD:
        reasons.append(f"error rate {recent_err:.0%} >= threshold {config.ANOMALY_ERROR_RATE_THRESHOLD:.0%}")
        severity += recent_err * 10

    if has_traffic and latency_ratio is not None and latency_ratio >= config.ANOMALY_LATENCY_RATIO_THRESHOLD:
        reasons.append(f"latency {latency_ratio:.1f}x baseline (>= {config.ANOMALY_LATENCY_RATIO_THRESHOLD}x)")
        severity += latency_ratio

    return ServiceAnomaly(
        service=service,
        recent_request_rate=round(recent_rate, 4),
        recent_error_rate=round(recent_err, 4),
        baseline_error_rate=round(baseline_err, 4),
        recent_avg_latency_ms=round(recent_lat * 1000, 2) if recent_lat is not None else None,
        baseline_avg_latency_ms=round(baseline_lat * 1000, 2) if baseline_lat is not None else None,
        latency_ratio=round(latency_ratio, 3) if latency_ratio is not None else None,
        is_anomalous=bool(reasons),
        severity=round(severity, 3),
        reasons=reasons,
    )


async def detect_anomalies(services: list[str] | None = None) -> list[ServiceAnomaly]:
    services = services or config.KNOWN_SERVICES
    async with httpx.AsyncClient(timeout=10.0) as client:
        return [await detect_service_anomaly(client, service) for service in services]
