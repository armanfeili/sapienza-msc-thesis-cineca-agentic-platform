import pytest

from db.redis_cache import rate_limit as rl


@pytest.mark.asyncio
async def test_check_rate_limit_local_fallback_blocks_after_limit(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("no redis")

    monkeypatch.setattr(rl, "get_async_redis", boom)

    key = "ratelimit:test:user"
    limit = 2
    window = 60

    await rl.reset_rate_limit(key)

    allowed, remaining, retry = await rl.check_rate_limit(key, limit, window)
    assert allowed
    assert remaining == limit - 1
    assert retry == 0

    allowed, remaining, retry = await rl.check_rate_limit(key, limit, window)
    assert allowed
    assert remaining == limit - 2

    allowed, remaining, retry = await rl.check_rate_limit(key, limit, window)
    assert not allowed
    assert remaining == 0
    assert retry > 0

    await rl.reset_rate_limit(key)


@pytest.mark.asyncio
async def test_get_rate_limit_status_local_fallback_reports_usage(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("no redis")

    monkeypatch.setattr(rl, "get_async_redis", boom)

    key = "ratelimit:test-status:user"
    limit = 5
    window = 60

    await rl.reset_rate_limit(key)
    await rl.check_rate_limit(key, limit, window)

    current, remaining, reset_in = await rl.get_rate_limit_status(key, limit, window)
    assert current == 1
    assert remaining == limit - 1
    assert reset_in >= 0

    await rl.reset_rate_limit(key)


@pytest.mark.asyncio
async def test_check_rate_limit_fallback_on_runtime_error(monkeypatch):
    class BoomPipeline:
        def zremrangebyscore(self, *args, **kwargs):
            return self

        def zcard(self, *args, **kwargs):
            return self

        def zrange(self, *args, **kwargs):
            return self

        async def execute(self):
            raise RuntimeError("pipeline exploded")

    class BoomRedis:
        def __init__(self):
            self._pipe = BoomPipeline()

        def pipeline(self):
            return self._pipe

        async def zadd(self, *args, **kwargs):  # pragma: no cover - should never run
            raise AssertionError("zadd should not be called when pipeline fails")

        async def expire(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("expire should not be called when pipeline fails")

    async def fake_get_async_redis():
        return BoomRedis()

    monkeypatch.setattr(rl, "get_async_redis", fake_get_async_redis)

    key = "ratelimit:test:pipeline"
    limit = 2
    window = 60

    await rl.reset_rate_limit(key)

    allowed, _, _ = await rl.check_rate_limit(key, limit, window)
    assert allowed

    allowed, _, _ = await rl.check_rate_limit(key, limit, window)
    assert allowed

    allowed, _, retry = await rl.check_rate_limit(key, limit, window)
    assert not allowed
    assert retry > 0

    await rl.reset_rate_limit(key)
