"""Root-cause ranking: combines the Tempo-derived dependency graph with the
Prometheus-derived anomaly list to guess which anomalous service is the true
root cause vs. a downstream victim of some other service's failure.

Heuristic: if service B calls anomalous service A, B often *also* looks
anomalous (elevated latency/errors) purely because A is failing underneath
it. So a node scores higher the more anomalous *upstream callers* it has
(evidence the failure is propagating outward from it) and lower the more
anomalous *downstream callees* it has (evidence it's more likely a victim of
something deeper in the call chain, not the source).
"""

from .models import DependencyGraph, RootCauseCandidate, ServiceAnomaly


def rank_root_causes(graph: DependencyGraph, anomalies: list[ServiceAnomaly]) -> list[RootCauseCandidate]:
    anomalous = {a.service: a for a in anomalies if a.is_anomalous}
    if not anomalous:
        return []

    callers_of: dict[str, set[str]] = {}
    callees_of: dict[str, set[str]] = {}
    for edge in graph.edges:
        callees_of.setdefault(edge.caller, set()).add(edge.callee)
        callers_of.setdefault(edge.callee, set()).add(edge.caller)

    candidates = []
    for service, anomaly in anomalous.items():
        upstream_anomalous = sorted(c for c in callers_of.get(service, set()) if c in anomalous)
        downstream_anomalous = sorted(c for c in callees_of.get(service, set()) if c in anomalous)

        propagation_bonus = 1.0 + 0.5 * len(upstream_anomalous)
        downstream_penalty = 1.0 + len(downstream_anomalous)
        score = (anomaly.severity * propagation_bonus) / downstream_penalty

        reasons = list(anomaly.reasons)
        if upstream_anomalous:
            reasons.append(
                f"{len(upstream_anomalous)} upstream caller(s) also anomalous: {', '.join(upstream_anomalous)}"
            )
        if downstream_anomalous:
            reasons.append(
                f"{len(downstream_anomalous)} downstream callee(s) also anomalous "
                f"(likely the deeper root cause instead): {', '.join(downstream_anomalous)}"
            )

        candidates.append(RootCauseCandidate(service=service, score=round(score, 3), reasons=reasons))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
