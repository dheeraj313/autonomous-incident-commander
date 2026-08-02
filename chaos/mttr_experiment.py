"""MTTR reduction experiment.

Injects a real fault into inventory-service (error burst - circuit-breaker
capable, so remediation-engine auto-approves the fix with no human-approval
wait, giving a clean, fully-automated MTTR number), drives real traffic
through the gateway, and repeatedly calls incident-store's POST
/incidents/start (live, no override) until it detects the incident and the
remediation engine has executed an action. That measured, automated time is
compared against a documented manual-baseline formula (see config.py for the
named assumptions) grounded in the *actual* dependency-graph size fetched live
from causal-analysis-engine, rather than an arbitrary constant.

This does not claim to measure a real human's response time (there is no
human in this sandbox) - it measures what the automated pipeline actually
achieves, and compares it to a transparent, adjustable assumption about
typical manual response for this class of incident.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

import config
from http_helpers import clear_all_faults, clear_fault, generate_order_traffic, inject_fault, register_and_login

RESULTS_DIR = Path(__file__).parent / "results"
TARGET_SERVICE = "inventory-service"


def is_circuit_open(client: httpx.Client, service: str) -> bool:
    resp = client.get(f"{config.ORDERS_SERVICE_URL}/admin/circuit-breaker/{service}", headers=config.ADMIN_HEADERS)
    if resp.status_code != 200:
        return False
    return bool(resp.json().get("open"))


def run_trial(client: httpx.Client) -> dict:
    clear_all_faults(client)
    username = f"chaos_mttr_{int(time.time())}"
    token = register_and_login(client, username, "chaos-pass-123")

    t0 = time.monotonic()
    inject_fault(client, TARGET_SERVICE, errorRate=0.9, latencyMs=0)

    incident_id = None
    action = None
    deadline = t0 + config.DETECTION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        generate_order_traffic(client, token, 5)
        result = client.post(f"{config.INCIDENT_STORE_URL}/incidents/start").json()
        if result.get("incident_detected") and result.get("remediation", {}).get("actions"):
            incident_id = result["incident_id"]
            action = result["remediation"]["actions"][0]
            break
        time.sleep(config.DETECTION_POLL_INTERVAL_SECONDS)

    auto_mttr = time.monotonic() - t0

    mitigated = bool(
        action
        and action.get("action_type") == "TRIP_CIRCUIT_BREAKER"
        and action.get("status") == "EXECUTED"
        and is_circuit_open(client, TARGET_SERVICE)
    )

    graph = client.get(f"{config.CAUSAL_ANALYSIS_URL}/dependency-graph").json()
    num_services = max(len(graph.get("nodes", [])), 1)
    manual_mttr = (
        config.MANUAL_ALERT_ACK_SECONDS
        + num_services * config.MANUAL_PER_SERVICE_DIAGNOSIS_SECONDS
        + config.MANUAL_FIX_EXECUTION_SECONDS
    )
    reduction_pct = (manual_mttr - auto_mttr) / manual_mttr * 100 if manual_mttr else 0.0

    if incident_id:
        note = (
            "chaos experiment: circuit breaker mitigation confirmed"
            if mitigated
            else "chaos experiment: remediation attempted, mitigation not confirmed"
        )
        client.post(
            f"{config.INCIDENT_STORE_URL}/incidents/{incident_id}/resolve",
            params={"note": note},
            headers=config.ADMIN_HEADERS,
        )

    clear_fault(client, TARGET_SERVICE)

    return {
        "target_service": TARGET_SERVICE,
        "incident_id": incident_id,
        "incident_detected_and_remediated": incident_id is not None,
        "action_type": action.get("action_type") if action else None,
        "action_status": action.get("status") if action else None,
        "circuit_breaker_confirmed_open": mitigated,
        "auto_mttr_seconds": round(auto_mttr, 1),
        "num_services_in_topology": num_services,
        "manual_mttr_baseline_seconds": manual_mttr,
        "mttr_reduction_pct": round(reduction_pct, 1),
        "manual_baseline_assumptions": {
            "alert_ack_seconds": config.MANUAL_ALERT_ACK_SECONDS,
            "per_service_diagnosis_seconds": config.MANUAL_PER_SERVICE_DIAGNOSIS_SECONDS,
            "fix_execution_seconds": config.MANUAL_FIX_EXECUTION_SECONDS,
        },
    }


def main() -> dict:
    RESULTS_DIR.mkdir(exist_ok=True)
    with httpx.Client(timeout=20.0) as client:
        result = run_trial(client)

    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), **result}
    out_path = RESULTS_DIR / f"mttr_{int(time.time())}.json"
    out_path.write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print(f"\nSaved to {out_path}")
    return summary


if __name__ == "__main__":
    main()
