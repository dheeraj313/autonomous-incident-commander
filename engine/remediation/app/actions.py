"""Executes remediation actions against the real stack: Docker API (container
restart), and HTTP calls to services' existing admin endpoints (circuit breaker,
fault injection). No action here is simulated - every action performs a real,
verifiable change against the running stack."""

import asyncio

import docker
import httpx

from . import config
from .models import ActionType


async def execute(docker_client: docker.DockerClient, http_client: httpx.AsyncClient,
                   service: str, action_type: ActionType) -> str:
    """Returns a human-readable result string. Raises on failure (caller catches)."""
    if action_type == ActionType.TRIP_CIRCUIT_BREAKER:
        resp = await http_client.post(
            f"{config.CIRCUIT_BREAKER_OWNER_URL}/admin/circuit-breaker/{service}/trip",
            json={"ttlSeconds": config.CIRCUIT_BREAKER_TRIP_SECONDS},
            headers={"X-Admin-Api-Key": config.ADMIN_API_KEY},
        )
        resp.raise_for_status()
        return f"tripped circuit breaker for {service} via orders-service for {config.CIRCUIT_BREAKER_TRIP_SECONDS}s: {resp.json()}"

    if action_type == ActionType.CLEAR_FAULT_INJECTION:
        port = config.FAULT_INJECTION_PORTS[service]
        resp = await http_client.delete(
            f"http://{service}:{port}/admin/fault-injection",
            headers={"X-Admin-Api-Key": config.ADMIN_API_KEY},
        )
        resp.raise_for_status()
        return f"cleared fault-injection overrides on {service}: {resp.json()}"

    if action_type == ActionType.RESTART_SERVICE:
        container_name = f"{config.DOCKER_CONTAINER_PREFIX}{service}"
        return await asyncio.to_thread(_restart_container, docker_client, container_name)

    raise ValueError(f"no executor for action type {action_type}")


def _restart_container(docker_client: docker.DockerClient, container_name: str) -> str:
    container = docker_client.containers.get(container_name)
    container.restart(timeout=10)
    return f"restarted container {container_name}"
