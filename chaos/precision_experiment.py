"""Root-cause localization precision experiment.

Runs each scenario in scenarios.py against the live stack: injects a real
fault, generates real traffic through the gateway, and polls
causal-analysis-engine's /root-cause until it reports an incident, checking
whether the #1 ranked cause matches the service the fault was actually
injected into. Aggregates a top-1 precision percentage across all scenarios.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

import config
from http_helpers import clear_all_faults, clear_fault, generate_order_traffic, inject_fault, login_burst, register_and_login
from scenarios import SCENARIOS

RESULTS_DIR = Path(__file__).parent / "results"


def run_scenario(client: httpx.Client, scenario: dict, token: str, username: str, password: str) -> dict:
    clear_all_faults(client)
    print(f"  cooling down {config.INTER_SCENARIO_COOLDOWN_SECONDS}s so the previous scenario's "
          f"signal fully leaves the detection window...")
    time.sleep(config.INTER_SCENARIO_COOLDOWN_SECONDS)
    inject_fault(client, scenario["target_service"], **scenario["fault"])

    start = time.monotonic()
    deadline = start + config.DETECTION_TIMEOUT_SECONDS
    detected = False
    ranked: list = []

    while time.monotonic() < deadline:
        if scenario["traffic"] == "orders":
            generate_order_traffic(client, token, 5)
        else:
            login_burst(client, username, password, 5)

        report = client.get(f"{config.CAUSAL_ANALYSIS_URL}/root-cause").json()
        if report.get("incident_detected"):
            ranked = report.get("ranked_causes", [])
            detected = True
            break
        time.sleep(config.DETECTION_POLL_INTERVAL_SECONDS)

    elapsed = time.monotonic() - start
    clear_fault(client, scenario["target_service"])

    top_cause = ranked[0]["service"] if ranked else None
    return {
        "scenario": scenario["name"],
        "target_service": scenario["target_service"],
        "detected": detected,
        "detection_seconds": round(elapsed, 1),
        "top_cause": top_cause,
        "correct_top1": bool(detected and top_cause == scenario["target_service"]),
        "detected_anywhere_in_ranking": bool(
            detected and any(c["service"] == scenario["target_service"] for c in ranked)
        ),
        "ranked_causes": ranked,
    }


def main() -> dict:
    RESULTS_DIR.mkdir(exist_ok=True)
    with httpx.Client(timeout=15.0) as client:
        username = f"chaos_precision_{int(time.time())}"
        password = "chaos-pass-123"
        token = register_and_login(client, username, password)

        results = []
        for s in SCENARIOS:
            print(f"--- scenario: {s['name']} (target={s['target_service']}) ---")
            results.append(run_scenario(client, s, token, username, password))

    total = len(results)
    detected_count = sum(1 for r in results if r["detected"])
    correct_top1 = sum(1 for r in results if r["correct_top1"])

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": total,
        "detected_count": detected_count,
        "correct_top1_count": correct_top1,
        "top1_precision_pct": round(correct_top1 / total * 100, 1) if total else 0.0,
        "precision_given_detected_pct": round(correct_top1 / detected_count * 100, 1) if detected_count else 0.0,
        "results": results,
    }

    out_path = RESULTS_DIR / f"precision_{int(time.time())}.json"
    out_path.write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print(f"\nSaved to {out_path}")
    return summary


if __name__ == "__main__":
    main()
