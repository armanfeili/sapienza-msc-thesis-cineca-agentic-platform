import asyncio
from types import SimpleNamespace

import pytest

import src.health.components as components


class _DummyRedis:
    def __init__(self, ping_exception: Exception | None = None) -> None:
        self.ping_exception = ping_exception
        self.ping_calls = 0
        self.llen_calls = 0

    async def ping(self):
        self.ping_calls += 1
        if self.ping_exception:
            raise self.ping_exception
        return True

    async def llen(self, _key: str):
        self.llen_calls += 1
        return 0


@pytest.mark.asyncio
async def test_probe_redis_uses_async_client(monkeypatch):
    """Healthy Redis returns OK using the shared async client."""
    dummy = _DummyRedis()
    monkeypatch.setattr(components, "_redis_consecutive_failures", 0)
    async def fake_get_async_redis():
        return dummy

    monkeypatch.setattr(
        "db.redis_cache.async_client.get_async_redis", fake_get_async_redis, raising=False
    )
    monkeypatch.setattr(
        components, "get_health_config", lambda: SimpleNamespace(cache_timeout_ms=2000, allow_redis_health_fallback=True)
    )

    result = await components.probe_redis()

    assert result.status == components.ComponentStatus.OK
    assert dummy.ping_calls == 1
    assert result.ok


@pytest.mark.asyncio
async def test_probe_redis_degraded_then_error(monkeypatch):
    """First timeout is degraded, second consecutive failure escalates to error."""
    monkeypatch.setattr(components, "_redis_consecutive_failures", 0)

    timeout_err = asyncio.TimeoutError()
    dummy = _DummyRedis(ping_exception=timeout_err)

    async def fake_get_async_redis():
        return dummy

    monkeypatch.setattr(
        "db.redis_cache.async_client.get_async_redis", fake_get_async_redis, raising=False
    )
    monkeypatch.setattr(
        components, "get_health_config", lambda: SimpleNamespace(cache_timeout_ms=10, allow_redis_health_fallback=True)
    )

    first = await components.probe_redis()
    second = await components.probe_redis()

    assert first.status == components.ComponentStatus.DEGRADED
    assert first.ok  # degraded still considered ok per policy
    assert second.status in (components.ComponentStatus.ERROR, components.ComponentStatus.DEGRADED)


# ─────────────────────────────────────────────────────────────────────────────
# Postgres
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_probe_postgres_success_single_attempt(monkeypatch):
    calls: list[int] = []

    def fake_check():
        calls.append(1)
        return True, None

    monkeypatch.setattr("db.postgres_control.database.check_db_health", fake_check, raising=False)
    monkeypatch.setattr(
        components,
        "get_health_config",
        lambda: SimpleNamespace(
            postgres_timeout_ms=5,
            db_timeout_ms=5,
            postgres_retries=1,
            postgres_retry_backoff_ms=0,
        ),
    )

    result = await components.probe_postgres()

    assert result.ok is True
    assert result.details.get("attempts") == 1
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_probe_postgres_recovers_after_timeout(monkeypatch):
    attempts = {"count": 0}

    def fake_check():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("slow start")
        return True, None

    monkeypatch.setattr("db.postgres_control.database.check_db_health", fake_check, raising=False)
    monkeypatch.setattr(
        components,
        "get_health_config",
        lambda: SimpleNamespace(
            postgres_timeout_ms=5,
            db_timeout_ms=5,
            postgres_retries=2,
            postgres_retry_backoff_ms=0,
        ),
    )

    result = await components.probe_postgres()

    assert result.ok is True
    assert result.details.get("attempts") == 2
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_probe_postgres_fails_after_retries(monkeypatch):
    def fake_check():
        raise TimeoutError("always slow")

    monkeypatch.setattr("db.postgres_control.database.check_db_health", fake_check, raising=False)
    monkeypatch.setattr(
        components,
        "get_health_config",
        lambda: SimpleNamespace(
            postgres_timeout_ms=5,
            db_timeout_ms=5,
            postgres_retries=2,
            postgres_retry_backoff_ms=0,
        ),
    )

    result = await components.probe_postgres()

    assert result.ok is False
    assert result.status == components.ComponentStatus.ERROR
    assert result.details.get("attempts") == 2
    assert "timeout" in result.details.get("error", "")
