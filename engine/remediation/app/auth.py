"""Shared-secret guard for state-changing endpoints. Not a real auth system
(no users/roles/sessions) - just a minimal check so this engine's ability to
trip circuit breakers, restart containers, etc. isn't reachable by anyone who
can reach the port, consistent with every service's /admin/** endpoints."""

from fastapi import Header, HTTPException, status

from . import config


async def require_admin_key(x_admin_api_key: str = Header(default="")) -> None:
    if x_admin_api_key != config.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid X-Admin-Api-Key header",
        )
