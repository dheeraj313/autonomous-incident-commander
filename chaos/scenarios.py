"""Fault-injection scenarios used by precision_experiment.py. Each targets a
different service with a fault signature (error-heavy vs latency-heavy) that
reaches it via real traffic through the gateway, so the causal-analysis engine
has to localize the root cause from genuine Prometheus/trace signal - nothing
here is faked or fed directly into the engine."""

SCENARIOS = [
    {
        "name": "inventory_error_burst",
        "target_service": "inventory-service",
        "fault": {"errorRate": 0.9, "latencyMs": 0},
        # orders-service calls inventory-service to reserve stock on every order.
        "traffic": "orders",
    },
    {
        "name": "payments_error_burst",
        "target_service": "payments-service",
        "fault": {"errorRate": 0.9, "latencyMs": 0},
        # orders-service calls payments-service to charge the order after reserving stock.
        "traffic": "orders",
    },
    {
        "name": "auth_latency_spike",
        "target_service": "auth-service",
        "fault": {"errorRate": 0.0, "latencyMs": 800},
        # gateway calls auth-service on every login.
        "traffic": "logins",
    },
    {
        "name": "orders_latency_spike",
        "target_service": "orders-service",
        "fault": {"errorRate": 0.0, "latencyMs": 600},
        # gateway calls orders-service directly on every order.
        "traffic": "orders",
    },
]
