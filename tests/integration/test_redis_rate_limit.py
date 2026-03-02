import time
from typing import Dict, Tuple

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.security import rate_limit as rl


# ──────────────────────────────────────────────────────────────────────────────
# Helpers: fake Redis primitives for the rate_limit module
# ──────────────────────────────────────────────────────────────────────────────
class _FakeRedis:
    """
    Minimal in-memory stand-in for:
      - incr_with_ttl(key, ttl_seconds) -> int
      - ttl(key) -> int
      - redis_available() -> bool
    """

    def __init__(self):
        # store: k -> (count:int, expire_at:int_epoch)
        self.store: Dict[str, Tuple[int, int]] = {}

    def incr_with_ttl(self, key: str, ttl: int, now: int) -> int:
        # create/refresh window if expired or missing
        count, exp = self.store.get(key, (0, 0))
        if now >= exp:
            count, exp = 0, now + int(ttl)
        count += 1
        self.store[key] = (count, exp)
        return count

    def ttl(self, key: str, now: int) -> int:
        if key not in self.store:
            return -2  # Redis: key does not exist
        _, exp = self.store[key]
        return max(0, exp - now)

    @staticmethod
    def available() -> bool:
        return True


def _reset_backend(monkeypatch):
    # Reset cached backend resolution in the module
    monkeypatch.setattr(rl, "_backend_forced", None, raising=False)
    monkeypatch.setattr(rl, "_logged_degrade_once", False, raising=False)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_rate_limit_redis_allows_then_blocks(monkeypatch):
    """
    With Redis backend available:
      - first N requests within window are allowed
      - N+1 is rejected
      - backend reported as 'redis'
    """
    fake = _FakeRedis()
    now_holder = {"t": 1_700_000_000}

    # Patch time in the module to a stable value
    monkeypatch.setattr(rl.time, "time", lambda: now_holder["t"], raising=False)

    # Configure settings to prefer redis
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_ENABLED", True, raising=False)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_BACKEND", "redis", raising=False)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_DEFAULT_LIMIT", 60, raising=False)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_DEFAULT_WINDOW", 60, raising=False)

    # Patch redis adapter shims into the module namespace
    monkeypatch.setattr(
        rl, "_redis_incr_with_ttl", lambda k, ttl: fake.incr_with_ttl(k, ttl, int(now_holder["t"])), raising=False
    )
    monkeypatch.setattr(rl, "_redis_ttl", lambda k: fake.ttl(k, int(now_holder["t"])), raising=False)
    monkeypatch.setattr(rl, "_redis_available", fake.available, raising=False)

    _reset_backend(monkeypatch)

    key = "user:alice"
    limit, window = 3, 10

    r1 = rl.rate_limit_check(key, limit=limit, window=window)
    assert r1.allowed is True and r1.count == 1 and r1.backend == "redis"
    r2 = rl.rate_limit_check(key, limit=limit, window=window)
    assert r2.allowed is True and r2.count == 2 and r2.remaining == 1 and r2.backend == "redis"
    r3 = rl.rate_limit_check(key, limit=limit, window=window)
    assert r3.allowed is True and r3.count == 3 and r3.remaining == 0

    # Next one in same window should be blocked
    r4 = rl.rate_limit_check(key, limit=limit, window=window)
    assert r4.allowed is False
    assert r4.remaining == 0
    assert r4.reset_seconds <= window

    # Advance time into next window → counter resets
    now_holder["t"] += window
    r5 = rl.rate_limit_check(key, limit=limit, window=window)
    assert r5.allowed is True and r5.count == 1 and r5.remaining == limit - 1


@pytest.mark.anyio
async def test_rate_limiter_dependency_sets_headers(monkeypatch):
    """
    Use FastAPI dependency with redis-backed limiter to verify 429 and headers.
    """
    fake = _FakeRedis()
    now_holder = {"t": 1_700_000_000}
    monkeypatch.setattr(rl.time, "time", lambda: now_holder["t"], raising=False)

    monkeypatch.setattr(rl.settings, "RATE_LIMIT_ENABLED", True, raising=False)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_BACKEND", "redis", raising=False)

    monkeypatch.setattr(
        rl, "_redis_incr_with_ttl", lambda k, ttl: fake.incr_with_ttl(k, ttl, int(now_holder["t"])), raising=False
    )
    monkeypatch.setattr(rl, "_redis_ttl", lambda k: fake.ttl(k, int(now_holder["t"])), raising=False)
    monkeypatch.setattr(rl, "_redis_available", fake.available, raising=False)
    _reset_backend(monkeypatch)

    app = FastAPI()

    # Use fixed key to avoid reliance on client IP extraction
    limiter = rl.rate_limiter(limit=2, window=30, key="test:key")

    @app.get("/expensive", dependencies=[limiter])
    async def expensive():
        return {"ok": True}

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Two allowed
        r1 = await client.get("/expensive")
        assert r1.status_code == 200
        r2 = await client.get("/expensive")
        assert r2.status_code == 200

        # Third should be 429 with headers
        r3 = await client.get("/expensive")
        assert r3.status_code == 429
        assert r3.headers.get("Retry-After") is not None
        assert r3.headers.get("X-RateLimit-Limit") == "2"
        assert r3.headers.get("X-RateLimit-Remaining") == "0"
        assert r3.headers.get("X-RateLimit-Reset") is not None


@pytest.mark.anyio
async def test_rate_limit_degrades_to_memory_when_redis_unavailable(monkeypatch):
    """
    When redis is configured but unavailable, the module should degrade to memory backend.
    """
    # Ensure no redis primitives present / available
    monkeypatch.setattr(rl, "_redis_available", lambda: False, raising=False)
    # Remove potential incr/ttl attributes so code path can't use them
    for name in ("_redis_incr_with_ttl", "_redis_ttl"):
        if hasattr(rl, name):
            monkeypatch.delattr(rl, name, raising=False)

    monkeypatch.setattr(rl.settings, "RATE_LIMIT_ENABLED", True, raising=False)
    monkeypatch.setattr(rl.settings, "RATE_LIMIT_BACKEND", "redis", raising=False)

    _reset_backend(monkeypatch)

    res = rl.rate_limit_check("ip:1.2.3.4", limit=1, window=60)
    assert res.backend == "memory"
    assert res.allowed is True

    # Second hit within same window should be blocked (memory path)
    res2 = rl.rate_limit_check("ip:1.2.3.4", limit=1, window=60)
    assert res2.backend == "memory"
    assert res2.allowed is False
