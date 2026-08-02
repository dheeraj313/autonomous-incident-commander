"""Unit tests for check_and_record() using a lightweight hand-written fake
async Redis client (get/incr/expire) instead of adding a fakeredis dependency."""

import pytest

from app import config
from app.guardrails import check_and_record


class _FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.expired_keys: list[str] = []

    async def get(self, key):
        value = self.counts.get(key)
        return str(value) if value is not None else None

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, seconds):
        self.expired_keys.append(key)


@pytest.mark.asyncio
async def test_first_action_is_allowed_and_sets_ttl():
    client = _FakeRedis()

    allowed, reason = await check_and_record(client, "inventory-service")

    assert allowed is True
    assert reason is None
    assert client.counts["remediation:inventory-service:action-count"] == 1
    assert client.expired_keys == ["remediation:inventory-service:action-count"]


@pytest.mark.asyncio
async def test_subsequent_actions_below_limit_do_not_reset_ttl():
    client = _FakeRedis()
    await check_and_record(client, "inventory-service")

    allowed, reason = await check_and_record(client, "inventory-service")

    assert allowed is True
    assert reason is None
    assert client.counts["remediation:inventory-service:action-count"] == 2
    # expire() is only called on the very first increment.
    assert client.expired_keys == ["remediation:inventory-service:action-count"]


@pytest.mark.asyncio
async def test_action_blocked_once_limit_reached():
    client = _FakeRedis()
    for _ in range(config.MAX_ACTIONS_PER_SERVICE):
        await check_and_record(client, "payments-service")

    allowed, reason = await check_and_record(client, "payments-service")

    assert allowed is False
    assert "rate limit" in reason
    # A blocked attempt must not itself count against the window.
    assert client.counts["remediation:payments-service:action-count"] == config.MAX_ACTIONS_PER_SERVICE


@pytest.mark.asyncio
async def test_different_services_have_independent_counters():
    client = _FakeRedis()
    await check_and_record(client, "inventory-service")

    allowed, reason = await check_and_record(client, "payments-service")

    assert allowed is True
    assert client.counts["remediation:payments-service:action-count"] == 1
