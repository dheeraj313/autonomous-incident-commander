import os

TEMPO_URL = os.getenv("TEMPO_URL", "http://localhost:3200")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

# Dependency graph (Tempo trace mining)
DEPENDENCY_GRAPH_LOOKBACK_MINUTES = int(os.getenv("DEPENDENCY_GRAPH_LOOKBACK_MINUTES", "15"))
DEPENDENCY_GRAPH_MAX_TRACES = int(os.getenv("DEPENDENCY_GRAPH_MAX_TRACES", "200"))
# Prometheus scrapes GET /actuator/prometheus on every service every ~15s, which vastly
# outnumbers real business traffic and crowds it out of a "most recent N traces" search.
# This TraceQL query restricts the search to real entrypoint requests (gateway handling
# a non-actuator route), which is where every genuine cross-service call chain starts.
DEPENDENCY_GRAPH_TRACEQL_FILTER = os.getenv(
    "DEPENDENCY_GRAPH_TRACEQL_FILTER",
    '{resource.service.name="gateway" && span.http.route != "/actuator/prometheus"}',
)

# Anomaly detection (Prometheus metrics)
ANOMALY_RECENT_WINDOW = os.getenv("ANOMALY_RECENT_WINDOW", "1m")
ANOMALY_BASELINE_WINDOW = os.getenv("ANOMALY_BASELINE_WINDOW", "10m")
ANOMALY_ERROR_RATE_THRESHOLD = float(os.getenv("ANOMALY_ERROR_RATE_THRESHOLD", "0.1"))
ANOMALY_LATENCY_RATIO_THRESHOLD = float(os.getenv("ANOMALY_LATENCY_RATIO_THRESHOLD", "2.0"))
# Minimum request rate (req/s) a service must have before we trust its error/latency
# signal at all - avoids flagging near-idle services on noise.
ANOMALY_MIN_REQUEST_RATE = float(os.getenv("ANOMALY_MIN_REQUEST_RATE", "0.05"))

KNOWN_SERVICES = os.getenv(
    "KNOWN_SERVICES",
    "gateway,auth-service,orders-service,inventory-service,payments-service,notifications-service",
).split(",")

# Dashboard (static UI) reads this API from the browser - permissive CORS is
# fine here since this is a local, credential-free sandbox project, not a
# production deployment. This engine is read-only (no mutating endpoints), so
# no admin-key guard is needed here (unlike remediation-engine/incident-store).
CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
