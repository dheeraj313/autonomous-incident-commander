"""Thin helpers around the stack's existing HTTP surface (gateway + each
service's /admin/fault-injection controller) - no new endpoints, this just
drives real requests against real running containers."""

import httpx

import config


def clear_all_faults(client: httpx.Client) -> None:
    for port in config.FAULT_INJECTION_PORTS.values():
        try:
            client.delete(f"http://localhost:{port}/admin/fault-injection", headers=config.ADMIN_HEADERS)
        except httpx.HTTPError:
            pass


def inject_fault(client: httpx.Client, service: str, errorRate: float = 0.0, latencyMs: int = 0) -> dict:
    port = config.FAULT_INJECTION_PORTS[service]
    resp = client.post(
        f"http://localhost:{port}/admin/fault-injection",
        json={"errorRate": errorRate, "latencyMs": latencyMs},
        headers=config.ADMIN_HEADERS,
    )
    resp.raise_for_status()
    return resp.json()


def clear_fault(client: httpx.Client, service: str) -> dict:
    port = config.FAULT_INJECTION_PORTS[service]
    resp = client.delete(f"http://localhost:{port}/admin/fault-injection", headers=config.ADMIN_HEADERS)
    resp.raise_for_status()
    return resp.json()


def register_and_login(client: httpx.Client, username: str, password: str) -> str:
    client.post(f"{config.GATEWAY_URL}/api/auth/register", json={"username": username, "password": password})
    resp = client.post(f"{config.GATEWAY_URL}/api/auth/login", json={"username": username, "password": password})
    resp.raise_for_status()
    return resp.json()["token"]


def login_burst(client: httpx.Client, username: str, password: str, count: int) -> None:
    for _ in range(count):
        try:
            client.post(f"{config.GATEWAY_URL}/api/auth/login", json={"username": username, "password": password})
        except httpx.HTTPError:
            pass


def generate_order_traffic(client: httpx.Client, token: str, count: int) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(count):
        try:
            client.post(
                f"{config.GATEWAY_URL}/api/orders",
                headers=headers,
                json={"item": "widget", "quantity": 1},
            )
        except httpx.HTTPError:
            pass
