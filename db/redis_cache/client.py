"""
Redis adapter: connection factory, health check, and tiny cache helpers.

This module centralizes Redis access so other parts of the app (rate limiting,
caching, queues) can use a shared client with consistent configuration.

Usage:
    from src.adapters.redis import get_redis, redis_health, cache_get, cache_set

    r = get_redis()
    r.incr("counter")

    ok = redis_health()["ok"]

JSON helpers:
    cache_set_json("user:123", {"name": "Ada"}, ex=3600)
    obj = cache_get_json("user:123")

Notes:
- Uses `redis>=5` which includes `redis.asyncio`. We intentionally return the
  synchronous client (`redis.Redis`) to avoid event loop coupling. If you need
  asyncio, you may import and use `redis.asyncio.Redis.from_url` separately.
"""

from __future__ import annotations

import dataclasses
import json
import time
from contextlib import suppress
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from src.config import settings

# Logging (structlog if available; stdlib otherwise)
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# Try importing redis; allow graceful degradation if not installed.
try:  # pragma: no cover - import path varies by environment
    import redis  # type: ignore
except Exception as exc:  # pragma: no cover
    redis = None  # type: ignore
    logger.warning("redis package not available: %s", exc)


# ---------------- Internal state ----------------
_client: redis.Redis | None = None  # type: ignore[name-defined]
_last_ping_ok: bool | None = None
_LOCAL_IDEMPOTENCY: dict[str, tuple[str, float | None]] = {}


def _json_default(value: Any) -> Any:
    """Best-effort serializer for Redis JSON helpers."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()  # type: ignore[attr-defined]
            if isinstance(dumped, (dict, list)):
                return dumped
        except Exception:  # pragma: no cover - defensive
            return str(value)
    return str(value)


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def _build_client(url: str | None = None) -> redis.Redis | None:  # type: ignore[name-defined]
    if redis is None:
        return None
    url = (url or settings.REDIS_URL or "").strip()
    if not url:
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        return client
    except Exception as exc:  # pragma: no cover - depends on env
        logger.warning("failed to create Redis client from %r: %s", url, exc)
        return None


def get_redis() -> redis.Redis:  # type: ignore[name-defined]
    """
    Return a process-wide Redis client. If Redis is not configured or import
    failed, this raises RuntimeError (callers can catch and degrade gracefully).
    """
    global _client
    if _client is None:
        _client = _build_client()
    if _client is None:
        raise RuntimeError("Redis client is not available (missing package or REDIS_URL unset)")
    return _client


def redis_available() -> bool:
    """Return True if a Redis client can be created and a ping succeeds once."""
    global _last_ping_ok
    if _last_ping_ok is True:
        return True
    client = _build_client()
    if client is None:
        _last_ping_ok = False
        return False
    try:
        _last_ping_ok = bool(client.ping())
    except Exception:
        _last_ping_ok = False
    return bool(_last_ping_ok)


def redis_health() -> dict[str, Any]:
    """Return a health dict compatible with readiness checks."""
    url = (settings.REDIS_URL or "").strip()
    info: dict[str, Any] = {"ok": False, "url": url}
    if not url or redis is None:
        info["error"] = "redis package missing or REDIS_URL unset"
        return info
    try:
        client = get_redis()
        info["ok"] = bool(client.ping())
    except Exception as exc:  # pragma: no cover
        info["error"] = str(exc)
    return info


# ---------------- Small cache helpers ----------------
def cache_set(key: str, value: str, ex: int | None = None) -> bool:
    """
    Set a string value with optional TTL (seconds).
    Returns True on success, False if Redis is unavailable.
    """
    try:
        r = get_redis()
        return bool(r.set(name=key, value=value, ex=ex))
    except Exception as exc:  # pragma: no cover
        logger.debug("cache_set failed for %r: %s", key, exc)
        return False


def cache_get(key: str) -> str | None:
    """Get a string value or None if missing/unavailable."""
    try:
        r = get_redis()
        return r.get(name=key)
    except Exception as exc:  # pragma: no cover
        logger.debug("cache_get failed for %r: %s", key, exc)
        return None


def cache_delete(key: str) -> int:
    """Delete a key; returns the number of keys removed (0/1)."""
    try:
        r = get_redis()
        return int(r.delete(key))
    except Exception as exc:  # pragma: no cover
        logger.debug("cache_delete failed for %r: %s", key, exc)
        return 0


def cache_set_json(key: str, obj: Any, ex: int | None = None) -> bool:
    """
    Serialize `obj` as compact JSON (UTF-8, sorted keys) and store under `key`.
    """
    try:
        data = _json_dumps(obj)
        return cache_set(key, data, ex=ex)
    except Exception as exc:  # pragma: no cover
        logger.debug("cache_set_json failed for %r: %s", key, exc)
        return False


def cache_get_json(key: str, default: Any = None) -> Any:
    """Fetch JSON value and parse; return `default` if missing or invalid."""
    raw = cache_get(key)
    if raw is None:
        return default
    with suppress(Exception):
        return json.loads(raw)
    return default


# ---------------- Idempotency helpers (with local fallback) ----------------
def idem_get(key: str, default: Any = None) -> Any:
    """Get a JSON-stored idempotency value. Falls back to an in-memory store
    when Redis is unavailable or the key is not found remotely.
    """
    try:
        val = cache_get_json(key)
        if val is not None:
            return val
    except Exception:
        # continue to local fallback
        pass

    # Local fallback: tuple of (json_str, expires_at)
    entry = _LOCAL_IDEMPOTENCY.get(key)
    if not entry:
        return default
    data_str, expires_at = entry
    if expires_at is not None and time.time() > expires_at:
        # expired
        _LOCAL_IDEMPOTENCY.pop(key, None)
        return default
    with suppress(Exception):
        return json.loads(data_str)
    return default


def idem_set(key: str, obj: Any, ex: int | None = None) -> bool:
    """Set an idempotency value (JSON) in Redis if available, otherwise in
    a local in-memory store with an expiry.
    """
    try:
        ok = cache_set_json(key, obj, ex=ex)
        if ok:
            return True
    except Exception:
        pass

    # Fallback to in-memory store
    try:
        data = _json_dumps(obj)
        expires_at = time.time() + ex if ex else None
        _LOCAL_IDEMPOTENCY[key] = (data, expires_at)
        return True
    except Exception:
        logger.debug("idem_set local fallback failed for %r", key)
        return False


# ---------------- Rate limit primitives (optional helpers) ----------------
def incr_with_ttl(key: str, ttl_seconds: int) -> int:
    """
    Increment a counter and ensure a TTL (useful for simple fixed-window limits).

    Returns the counter value after increment, or -1 if Redis is unavailable.
    """
    try:
        r = get_redis()
        # Use a pipeline to make INCR+EXPIRE atomic-ish within the same connection.
        with r.pipeline() as p:
            p.incr(key)
            p.expire(key, ttl_seconds)
            res = p.execute()
        return int(res[0])  # incr result
    except Exception as exc:  # pragma: no cover
        logger.debug("incr_with_ttl failed for %r: %s", key, exc)
        return -1


def ttl(key: str) -> int:
    """
    Return key TTL in seconds, or -2 if the key does not exist, or -1 if no TTL,
    or -999 if Redis unavailable.
    """
    try:
        r = get_redis()
        return int(r.ttl(key))
    except Exception as exc:  # pragma: no cover
        logger.debug("ttl failed for %r: %s", key, exc)
        return -999


__all__ = [
    "cache_delete",
    "cache_get",
    "cache_get_json",
    "cache_set",
    "cache_set_json",
    "get_redis",
    "idem_get",
    "idem_set",
    "incr_with_ttl",
    "redis_available",
    "redis_health",
    "ttl",
]
