"""Rule-based policy engine: maps a root-cause report's ranked anomalous services
to a candidate remediation action each, in priority order.

Rules (deterministic, in priority order per service):
1. Elevated error rate + service has an owned circuit breaker (inventory-service,
   payments-service) -> TRIP_CIRCUIT_BREAKER. Safest option: fails fast on the
   caller side without touching the struggling service at all.
2. Elevated error rate, no circuit breaker available -> CLEAR_FAULT_INJECTION.
   This sandbox has no real config-version history to roll back, so "clear any
   active fault-injection override" is the stand-in for a config rollback action.
3. Elevated latency only (no elevated error rate) -> RESTART_SERVICE. Assumes a
   stuck/leaking resource; most disruptive action, gated behind approval by config.

Only the top `config.BLAST_RADIUS_MAX_SERVICES` ranked services are considered at
all - remaining ranked services are reported back as blast-radius-skipped.
"""

from . import config
from .models import ActionType, SkippedCandidate


def _has_error_reason(reasons: list[str]) -> bool:
    return any("error rate" in r for r in reasons)


def _has_latency_reason(reasons: list[str]) -> bool:
    return any("latency" in r and "baseline" in r for r in reasons)


def decide_actions(root_cause_report: dict) -> tuple[list[dict], list[SkippedCandidate]]:
    ranked_causes = root_cause_report.get("ranked_causes", [])
    candidates: list[dict] = []
    skipped: list[SkippedCandidate] = []

    for cause in ranked_causes:
        service = cause["service"]
        reasons = cause.get("reasons", [])

        if len(candidates) >= config.BLAST_RADIUS_MAX_SERVICES:
            skipped.append(
                SkippedCandidate(
                    service=service,
                    action_type=ActionType.RESTART_SERVICE,
                    reason=f"blast radius limit reached ({config.BLAST_RADIUS_MAX_SERVICES} services already selected this incident)",
                )
            )
            continue

        has_error = _has_error_reason(reasons)
        has_latency = _has_latency_reason(reasons)

        if has_error and service in config.CIRCUIT_BREAKER_CAPABLE_SERVICES:
            action_type = ActionType.TRIP_CIRCUIT_BREAKER
            reason = next(r for r in reasons if "error rate" in r)
        elif has_error and service in config.FAULT_INJECTION_PORTS:
            action_type = ActionType.CLEAR_FAULT_INJECTION
            reason = next(r for r in reasons if "error rate" in r)
        elif has_latency:
            action_type = ActionType.RESTART_SERVICE
            reason = next(r for r in reasons if "latency" in r and "baseline" in r)
        else:
            skipped.append(
                SkippedCandidate(
                    service=service,
                    action_type=ActionType.RESTART_SERVICE,
                    reason="anomalous but no rule matched its reasons: " + "; ".join(reasons),
                )
            )
            continue

        candidates.append({"service": service, "action_type": action_type, "reason": reason})

    return candidates, skipped
