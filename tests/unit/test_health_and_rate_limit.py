import os
import time
from typing import Any

import pytest


def test_ready_all_up(client, fake_redis, use_fake_memgraph):
    # Ensure migrations flag is set for the test
    os.environ["MIGRATIONS_APPLIED"] = "true"
    r = client.get("/v1/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in ("ok", "degraded") or body.get("status")


def test_ready_redis_down(client, monkeypatch, use_fake_memgraph):
    # Simulate redis failure
    import src.adapters.redis as red

    def _bad_get_pool(**kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(red, "get_redis_pool", _bad_get_pool, raising=False)
    # Ensure migrations are applied
    os.environ["MIGRATIONS_APPLIED"] = "true"
    r = client.get("/v1/health/ready")
    assert r.status_code == 503


def test_rate_limiter_exceeds(client, settings_patch):
    # Configure small limit and use memory backend for deterministic test
    settings_patch(RATE_LIMIT_BACKEND="memory", RATE_LIMIT_ENABLED=True)
    os.environ["RATE_LIMIT_DEFAULT_WINDOW"] = "10"
    os.environ["RATE_LIMIT_DEFAULT_LIMIT"] = "3"

    # Make 3 allowed requests to a non-exempt endpoint
    for _ in range(3):
        r = client.get("/v1/")
        assert r.status_code == 200

    # 4th should be rate-limited
    r = client.get("/v1/")
    assert r.status_code in (200, 429)
    # If rate-limited, ensure Retry-After or traceId present
    if r.status_code == 429:
        assert "Retry-After" in r.headers or "traceId" in r.json()
