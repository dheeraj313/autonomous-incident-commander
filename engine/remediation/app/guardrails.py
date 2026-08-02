"""Per-service action rate limiting, backed by Redis so it survives across
requests/process restarts (mirrors the same TTL-counter pattern orders-service's
CircuitBreakerService already uses)."""

import redis.asyncio as redis

from . import config


def _key(service: str) -> str:
    return f"remediation:{service}:action-count"


async def check_and_record(client: redis.Redis, service: str) -> tuple[bool, str | None]:
    """Returns (allowed, reason_if_blocked). Increments the counter as a side
    effect only when the action is allowed, so a blocked candidate doesn't
    itself count against the window."""
    count = await client.get(_key(service))
    count = int(count) if count is not None else 0

    if count >= config.MAX_ACTIONS_PER_SERVICE:
        return False, (
            f"rate limit: {count} actions already taken against {service} in the last "
            f"{config.ACTION_RATE_LIMIT_WINDOW_SECONDS}s (max {config.MAX_ACTIONS_PER_SERVICE})"
        )

    new_count = await client.incr(_key(service))
    if new_count == 1:
        await client.expire(_key(service), config.ACTION_RATE_LIMIT_WINDOW_SECONDS)
    return True, None
