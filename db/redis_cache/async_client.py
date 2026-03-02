"""
Async Redis client for job storage.

This module provides an async Redis client specifically for the job store,
separate from the synchronous client used for rate limiting and caching.

The client is lazy-initialized and includes:
- Health checks
- Graceful shutdown
- Sensible timeouts and retries
- Connection pooling
"""

from __future__ import annotations

import logging
from typing import Any

from src.config import settings

# Try importing redis.asyncio
try:
    from redis.asyncio import ConnectionPool, Redis
    from redis.exceptions import RedisError, TimeoutError as RedisTimeoutError
except ImportError:
    Redis = None  # type: ignore
    ConnectionPool = None  # type: ignore
    RedisError = Exception  # type: ignore
    RedisTimeoutError = Exception  # type: ignore

logger = logging.getLogger(__name__)

# ---------------- Global async Redis client ----------------
_async_client: Redis | None = None  # type: ignore
_async_pool: ConnectionPool | None = None  # type: ignore


async def get_async_redis() -> Redis:  # type: ignore
    """
    Get or create the global async Redis client for job storage.

    This client is shared across the application and includes:
    - Connection pooling (max 10 connections)
    - Socket timeout: 5s
    - Decode responses to str (not bytes)
    - Lazy initialization

    Raises:
        RuntimeError: If Redis package not installed or URL not configured
    """
    global _async_client, _async_pool

    if _async_client is not None:
        return _async_client

    if Redis is None:
        raise RuntimeError("redis.asyncio not available. Install redis>=5.0: pip install 'redis>=5.0'")

    url = settings.REDIS_URL.strip() if settings.REDIS_URL else ""
    if not url:
        raise RuntimeError("REDIS_URL not configured in settings")

    try:
        # Create connection pool with sensible defaults
        _async_pool = ConnectionPool.from_url(
            url,
            decode_responses=True,  # Return str, not bytes
            max_connections=10,  # Pool size
            socket_timeout=5.0,  # Socket read/write timeout
            socket_connect_timeout=5.0,  # Connection timeout
            retry_on_timeout=True,  # Auto-retry on timeout
        )

        _async_client = Redis(connection_pool=_async_pool)

        # Test connection
        await _async_client.ping()
        logger.info("Async Redis client initialized successfully", extra={"url": url})

        return _async_client

    except Exception as exc:
        logger.error("Failed to initialize async Redis client", extra={"url": url, "error": str(exc)}, exc_info=True)
        raise RuntimeError(f"Failed to connect to Redis at {url}: {exc}") from exc


async def close_async_redis() -> None:
    """
    Gracefully close the async Redis client and connection pool.

    Call this during application shutdown to ensure clean disconnection.
    """
    global _async_client, _async_pool

    if _async_client is not None:
        try:
            await _async_client.aclose()
            logger.info("Async Redis client closed")
        except Exception as exc:
            logger.warning(f"Error closing async Redis client: {exc}")
        finally:
            _async_client = None

    if _async_pool is not None:
        try:
            await _async_pool.disconnect()
            logger.info("Async Redis connection pool disconnected")
        except Exception as exc:
            logger.warning(f"Error disconnecting Redis pool: {exc}")
        finally:
            _async_pool = None


async def async_redis_health() -> dict[str, Any]:
    """
    Check async Redis health.

    Returns:
        Dict with keys:
        - ok (bool): True if Redis is reachable
        - latency_ms (float): Ping latency in milliseconds
        - error (str): Error message if not ok
    """
    import time

    url = settings.REDIS_URL.strip() if settings.REDIS_URL else ""
    info: dict[str, Any] = {"ok": False, "url": url}

    if not url or Redis is None:
        info["error"] = "redis.asyncio not available or REDIS_URL not set"
        return info

    try:
        start = time.perf_counter()
        client = await get_async_redis()
        pong = await client.ping()
        latency_ms = (time.perf_counter() - start) * 1000

        info["ok"] = bool(pong)
        info["latency_ms"] = round(latency_ms, 2)

    except (RedisError, RedisTimeoutError) as exc:
        info["error"] = f"Redis error: {exc}"
    except Exception as exc:
        info["error"] = str(exc)

    return info


async def async_redis_available() -> bool:
    """
    Quick check if async Redis is available.

    Returns:
        True if Redis is reachable, False otherwise
    """
    try:
        client = await get_async_redis()
        return await client.ping()
    except Exception:
        return False


__all__ = [
    "async_redis_available",
    "async_redis_health",
    "close_async_redis",
    "get_async_redis",
]
