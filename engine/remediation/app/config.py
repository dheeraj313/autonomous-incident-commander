import os

CAUSAL_ANALYSIS_URL = os.getenv("CAUSAL_ANALYSIS_URL", "http://localhost:8090")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Docker containers in this stack are named "aic-{service}" (see docker-compose.yml).
DOCKER_CONTAINER_PREFIX = os.getenv("DOCKER_CONTAINER_PREFIX", "aic-")

# orders-service is the only service that owns downstream circuit breakers today
# (guarding its own calls to inventory-service/payments-service). Tripping a
# breaker for one of those services means calling *orders-service's* admin API,
# not the offending service itself.
CIRCUIT_BREAKER_OWNER_URL = os.getenv("CIRCUIT_BREAKER_OWNER_URL", "http://localhost:8082")
CIRCUIT_BREAKER_CAPABLE_SERVICES = ["inventory-service", "payments-service"]
CIRCUIT_BREAKER_TRIP_SECONDS = int(os.getenv("CIRCUIT_BREAKER_TRIP_SECONDS", "60"))

# Every backend service except gateway exposes POST/DELETE /admin/fault-injection.
FAULT_INJECTION_PORTS = {
    "auth-service": 8081,
    "orders-service": 8082,
    "inventory-service": 8083,
    "payments-service": 8084,
    "notifications-service": 8085,
}

# Actions in this list are executed immediately once guardrails pass. Actions NOT
# in this list are disruptive enough (e.g. dropping in-flight connections) that they
# are created as PENDING_APPROVAL and require a separate POST /actions/{id}/approve.
AUTO_APPROVED_ACTIONS = ["TRIP_CIRCUIT_BREAKER", "CLEAR_FAULT_INJECTION"]

# Guardrails
MAX_ACTIONS_PER_SERVICE = int(os.getenv("MAX_ACTIONS_PER_SERVICE", "3"))
ACTION_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("ACTION_RATE_LIMIT_WINDOW_SECONDS", "600"))
BLAST_RADIUS_MAX_SERVICES = int(os.getenv("BLAST_RADIUS_MAX_SERVICES", "2"))

# Shared secret required (via X-Admin-Api-Key header) to call any endpoint that
# actually triggers/approves/rejects a remediation action. Not a real auth
# system (no users/roles) - a minimal guard so this isn't wide open, matching
# the same header/env-var convention used by every service's /admin/**
# endpoints in this stack.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "dev-admin-key-change-me")

# Dashboard (static UI) reads this API from the browser - permissive CORS is
# fine here since this is a local, credential-free sandbox project, not a
# production deployment.
CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
