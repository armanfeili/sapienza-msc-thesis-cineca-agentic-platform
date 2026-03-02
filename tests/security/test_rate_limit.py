import asyncio
import importlib
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _isolate_rate_limit_module(monkeypatch):
    """
    Ensure we run tests against a fresh copy of the rate_limit module with a
    predictable configuration (enabled, memory backend).
    """
    # Make sure settings has the attributes the module expects
    settings_mod = importlib.import_module("src.config")
    # Set rate-limit settings to deterministic values
    monkeypatch.setattr(settings_mod, "RATE_LIMIT_ENABLED", True, raising=False)
    monkeypatch.setattr(settings_mod, "RATE_LIMIT_BACKEND", "memory", raising=False)
    monkeypatch.setattr(settings_mod, "RATE_LIMIT_DEFAULT_LIMIT", 5, raising=False)
    monkeypatch.setattr(settings_mod, "RATE_LIMIT_DEFAULT_WINDOW", 60, raising=False)

    # Reload the module under test to pick up config
    rl = importlib.import_module("src.security.rate_limit")
    importlib.reload(rl)

    # Clear any in-memory counters and reset backend cache flags
    rl._mem_counters.clear()
    rl._backend_forced = None
    rl._logged_degrade_once = False

    yield

    # Cleanup after each test
    rl._mem_counters.clear()


def _rl():
    """Convenience to re-import the module (fresh view after potential reloads)."""
    return importlib.import_module("src.security.rate_limit")


# ──────────────────────────────────────────────────────────────────────────────
# Basic behavior (memory backend)
# ──────────────────────────────────────────────────────────────────────────────
def test_memory_backend_allows_within_limit():
    rl = _rl()
    key = "user:alice"
    # Limit 3 per 10s window
    res1 = rl.rate_limit_check(key, limit=3, window=10, cost=1)
    res2 = rl.rate_limit_check(key, limit=3, window=10, cost=1)
    res3 = rl.rate_limit_check(key, limit=3, window=10, cost=1)
    res4 = rl.rate_limit_check(key, limit=3, window=10, cost=1)

    # First three allowed, remaining decreases; the 4th should be denied
    assert res1.allowed and res1.remaining == 2
    assert res2.allowed and res2.remaining == 1
    assert res3.allowed and res3.remaining == 0
    assert not res4.allowed
    assert res4.remaining == 0
    assert res4.backend == "memory"


def test_cost_greater_than_one_enforced():
    rl = _rl()
    key = "burst:op"
    # limit 5, cost 3 -> first ok, remaining 2; next cost 3 should deny
    r1 = rl.rate_limit_check(key, limit=5, window=30, cost=3)
    r2 = rl.rate_limit_check(key, limit=5, window=30, cost=3)
    assert r1.allowed and r1.count == 3 and r1.remaining == 2
    assert not r2.allowed
    # remaining remains 0 (can't go negative)
    assert r2.remaining == 0


def test_window_resets(monkeypatch):
    rl = _rl()

    # Freeze time by monkeypatching rate_limit.time.time
    base = 1_700_000_000  # arbitrary epoch
    tbox = {"now": base}

    def fake_time():
        return tbox["now"]

    monkeypatch.setattr(rl.time, "time", fake_time)

    key = "reset:test"
    # window=10s, limit=2
    r1 = rl.rate_limit_check(key, limit=2, window=10)
    r2 = rl.rate_limit_check(key, limit=2, window=10)
    r3 = rl.rate_limit_check(key, limit=2, window=10)
    assert r1.allowed and r2.allowed
    assert not r3.allowed  # exhausted within window

    # advance into next window
    tbox["now"] = base + 11
    r4 = rl.rate_limit_check(key, limit=2, window=10)
    assert r4.allowed, "New window should reset counters"


# ──────────────────────────────────────────────────────────────────────────────
# Backend selection
# ──────────────────────────────────────────────────────────────────────────────
def test_get_backend_forced_memory(monkeypatch):
    rl = _rl()
    # Force config to "memory"
    cfg = importlib.import_module("src.config")
    monkeypatch.setattr(cfg, "RATE_LIMIT_BACKEND", "memory", raising=False)

    # Reset cached decision
    rl._backend_forced = None
    rl._logged_degrade_once = False
    assert rl.get_backend() == "memory"


def test_get_backend_degrades_when_redis_unavailable(monkeypatch):
    rl = _rl()
    # Simulate config preferring redis, but no redis adapter available
    cfg = importlib.import_module("src.config")
    monkeypatch.setattr(cfg, "RATE_LIMIT_BACKEND", "redis", raising=False)

    # Ensure redis_available is missing / raises
    if "_redis_available" in rl.globals():
        del rl._redis_available  # type: ignore[attr-defined]
    rl._backend_forced = None
    rl._logged_degrade_once = False

    backend = rl.get_backend()
    assert backend == "memory", "Should gracefully degrade to memory when redis is unavailable"


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI dependency behavior (works with stubs if FastAPI isn't installed)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_rate_limiter_dependency_raises_429_on_exceed(monkeypatch):
    rl = _rl()

    # Ensure backend is memory and counters are clean
    rl._mem_counters.clear()
    rl._backend_forced = None
    assert rl.get_backend() == "memory"

    # Build dependency: limit 1 req / 60s
    dep = rl.rate_limiter(limit=1, window=60, cost=1)

    class _Client:
        host = "127.0.0.1"

    # Minimal Request-like object
    request = SimpleNamespace(client=_Client(), scope={})

    # First call should pass
    ok1 = await dep(request)  # user resolver defaults to None via stub
    assert ok1 is True

    # Second call should exceed → raise HTTP 429 (HTTPException or stub Exception)
    with pytest.raises(Exception):
        await dep(request)


@pytest.mark.asyncio
async def test_rate_limiter_custom_key_func(monkeypatch):
    rl = _rl()
    rl._mem_counters.clear()

    def key_func(request: Any, user: Any) -> str:
        return "k:tenant:123"

    dep = rl.rate_limiter(limit=2, window=60, cost=1, key_func=key_func)

    request = SimpleNamespace(client=SimpleNamespace(host="x"), scope={})
    assert await dep(request) is True
    assert await dep(request) is True
    with pytest.raises(Exception):
        await dep(request)
