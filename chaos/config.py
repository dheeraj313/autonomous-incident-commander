import os

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
CAUSAL_ANALYSIS_URL = os.getenv("CAUSAL_ANALYSIS_URL", "http://localhost:8090")
REMEDIATION_URL = os.getenv("REMEDIATION_URL", "http://localhost:8091")
INCIDENT_STORE_URL = os.getenv("INCIDENT_STORE_URL", "http://localhost:8092")
ORDERS_SERVICE_URL = os.getenv("ORDERS_SERVICE_URL", "http://localhost:8082")

FAULT_INJECTION_PORTS = {
    "auth-service": 8081,
    "orders-service": 8082,
    "inventory-service": 8083,
    "payments-service": 8084,
    "notifications-service": 8085,
}

# Shared secret required by every service's /admin/** endpoints and by
# remediation-engine/incident-store's mutating endpoints (see docs/architecture.md
# Phase 7 "bugs found" - these had no auth at all before). Must match the
# ADMIN_API_KEY the stack was started with (docker-compose.yml default is the
# same dev value below).
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "dev-admin-key-change-me")
ADMIN_HEADERS = {"X-Admin-Api-Key": ADMIN_API_KEY}

# causal-analysis-engine's anomaly detection uses a 1-minute "recent" rate() window
# (see engine/causal-analysis/app/config.py ANOMALY_RECENT_WINDOW) - the fault
# injection, traffic burst, and detection poll all need to land within roughly this
# window or the burst rolls out of range before it's queried (see docs/architecture.md
# Phase 4 "bug found" note - the same timing constraint applies here).
DETECTION_POLL_INTERVAL_SECONDS = 3
DETECTION_TIMEOUT_SECONDS = 75

# Cooldown observed live during Phase 7 testing: a short (2s) gap between
# scenarios was NOT enough - the previous scenario's fault signal was still
# inside the 1-minute "recent" rate() window, so the next scenario's first few
# polls picked up stale/leftover anomalies instead of the newly injected fault
# (2 of 4 scenarios in the first live run incorrectly reported "gateway" as the
# top cause, matching a leftover signal, not the actual injected service). The
# cooldown must be longer than DETECTION_TIMEOUT_SECONDS/the recent window so
# the previous burst fully ages out before the next fault is injected.
INTER_SCENARIO_COOLDOWN_SECONDS = int(os.getenv("INTER_SCENARIO_COOLDOWN_SECONDS", "70"))

# --- Manual-baseline MTTR assumptions ---
# These are NOT measured from a real on-call engineer (there's no human in this
# sandbox) - they're named, documented assumptions representing a typical manual
# response to this class of incident *without* an automated root-cause ranking
# system: get paged, then check each service in the dependency graph one at a time
# (since you don't know yet which one is the real cause) before finding and
# executing the fix by hand. See docs/architecture.md Phase 7 section for the
# full reasoning. Kept as named constants specifically so the assumption is
# explicit and easy to challenge/adjust, rather than a magic number in a formula.
MANUAL_ALERT_ACK_SECONDS = int(os.getenv("MANUAL_ALERT_ACK_SECONDS", "120"))
MANUAL_PER_SERVICE_DIAGNOSIS_SECONDS = int(os.getenv("MANUAL_PER_SERVICE_DIAGNOSIS_SECONDS", "90"))
MANUAL_FIX_EXECUTION_SECONDS = int(os.getenv("MANUAL_FIX_EXECUTION_SECONDS", "60"))
