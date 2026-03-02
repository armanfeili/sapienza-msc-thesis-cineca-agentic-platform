import importlib
from types import SimpleNamespace
from typing import Any, Dict

import pytest


@pytest.mark.asyncio
async def test_health_liveness_simple():
    health_mod = importlib.import_module("src.services.health")
    svc = health_mod.HealthService()
    res = await svc.liveness()
    assert res.ok
    assert isinstance(res.data, dict)
    assert res.data.get("status") == "ok"
    assert res.data.get("service") == "health-service"
    assert "time" in res.data


@pytest.mark.asyncio
async def test_health_checks_unknown_when_adapters_missing(monkeypatch):
    """
    If Redis and Memgraph adapters (or settings) are not available,
    probes should report 'unknown' with reason 'adapter-missing'.
    """
    health_mod = importlib.import_module("src.services.health")

    # Force adapters & settings to be missing
    monkeypatch.setattr(health_mod, "get_redis_pool", None, raising=False)
    monkeypatch.setattr(health_mod, "MemgraphAdapter", None, raising=False)
    monkeypatch.setattr(health_mod, "settings", None, raising=False)

    svc = health_mod.HealthService()
    res = await svc.check()
    assert res.ok
    checks = res.data.get("checks", {})
    assert checks["redis"]["status"] == "unknown"
    assert checks["redis"].get("reason") == "adapter-missing"
    assert checks["memgraph"]["status"] == "unknown"
    assert checks["memgraph"].get("reason") == "adapter-missing"

    # Readiness should not degrade when adapters are completely unavailable
    # (it summarizes 'unknown' as not-ok but we only assert envelope is success)
    ready = await svc.readiness()
    assert ready.ok
    assert ready.data["status"] in ("ok", "degraded")  # conservative assertion
    assert "checks" in ready.data


@pytest.mark.asyncio
async def test_health_readiness_ok_with_mocks(monkeypatch):
    """
    With working fake Redis + Memgraph, readiness should be 'ok'
    and report latencies.
    """
    health_mod = importlib.import_module("src.services.health")

    # Fake settings for both deps
    fake_settings = SimpleNamespace(
        REDIS_URL="redis://localhost:6379/0",
        MG_HOST="localhost",
        MG_PORT=7687,
        MG_USER="",
        MG_PASSWORD="",
        APP_VERSION="1.2.3",
    )
    monkeypatch.setattr(health_mod, "settings", fake_settings, raising=False)

    # Fake Redis pool & factory
    class FakeRedisPool:
        async def ping(self) -> bool:
            return True

        async def close(self) -> None:
            return None

    async def fake_get_redis_pool(url: str) -> FakeRedisPool:  # type: ignore[override]
        return FakeRedisPool()

    monkeypatch.setattr(health_mod, "get_redis_pool", fake_get_redis_pool, raising=False)

    # Fake Memgraph adapter
    class FakeMemgraphAdapter:
        def __init__(self, host: str, port: int, username=None, password=None, timeout: float = 3.0) -> None:
            self.host = host
            self.port = port
            self.username = username
            self.password = password
            self.timeout = timeout

        def ping(self) -> bool:
            return True

        def info(self) -> Dict[str, Any]:
            return {"version": "memgraph-2.x", "host": self.host, "port": self.port}

    monkeypatch.setattr(health_mod, "MemgraphAdapter", FakeMemgraphAdapter, raising=False)

    svc = health_mod.HealthService()
    res = await svc.readiness()
    assert res.ok
    assert res.data["status"] == "ok"
    checks = res.data["checks"]
    assert checks["redis"]["status"] == "ok"
    assert isinstance(checks["redis"].get("latency_ms"), int)
    assert checks["memgraph"]["status"] == "ok"
    assert isinstance(checks["memgraph"].get("latency_ms"), int)
    assert isinstance(checks["memgraph"].get("info"), dict)
    assert res.data.get("version") == "1.2.3"


@pytest.mark.asyncio
async def test_health_readiness_degraded_on_failure(monkeypatch):
    """
    If a critical probe fails (e.g., Memgraph ping false/exception),
    readiness should be 'degraded'.
    """
    health_mod = importlib.import_module("src.services.health")

    # Minimal settings
    fake_settings = SimpleNamespace(
        REDIS_URL="redis://localhost:6379/0",
        MG_HOST="localhost",
        MG_PORT=7687,
        MG_USER="",
        MG_PASSWORD="",
        APP_VERSION="test",
    )
    monkeypatch.setattr(health_mod, "settings", fake_settings, raising=False)

    # Redis OK
    class FakeRedisPoolOK:
        async def ping(self) -> bool:
            return True

        async def close(self) -> None:
            return None

    async def fake_get_redis_pool(url: str) -> FakeRedisPoolOK:
        return FakeRedisPoolOK()

    monkeypatch.setattr(health_mod, "get_redis_pool", fake_get_redis_pool, raising=False)

    # Memgraph FAIL (ping returns False)
    class FakeMemgraphAdapterBad:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def ping(self) -> bool:
            return False

    monkeypatch.setattr(health_mod, "MemgraphAdapter", FakeMemgraphAdapterBad, raising=False)

    svc = health_mod.HealthService()
    res = await svc.readiness()
    assert res.ok
    assert res.data["status"] == "degraded"
    checks = res.data["checks"]
    assert checks["redis"]["status"] == "ok"
    assert checks["memgraph"]["status"] in ("error", "unknown")  # depending on path
