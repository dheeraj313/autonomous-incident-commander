import os

# Upstream engines this service orchestrates into a persisted incident timeline.
CAUSAL_ANALYSIS_URL = os.getenv("CAUSAL_ANALYSIS_URL", "http://causal-analysis-engine:8090")
REMEDIATION_URL = os.getenv("REMEDIATION_URL", "http://remediation-engine:8091")

# Same Postgres instance/credentials the Java services use, "incidents" schema
# (see infra/postgres/init.sql).
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://aic:aic@postgres:5432/aic")

# Shared secret required (via X-Admin-Api-Key header) to call state-changing
# endpoints (currently just POST /incidents/{id}/resolve). Not a real auth
# system (no users/roles) - a minimal guard so this isn't wide open, matching
# the same header/env-var convention used by every other service's /admin/**
# endpoints in this stack.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "dev-admin-key-change-me")

# Dashboard (static UI, chaos/**/README) reads this API from the browser -
# permissive CORS is fine here since this is a local, credential-free sandbox
# project, not a production deployment.
CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
