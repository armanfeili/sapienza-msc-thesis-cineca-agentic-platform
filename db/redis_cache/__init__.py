"""
Redis cache module for Cineca Agentic Platform.

This module provides Redis connectivity and caching functionality including:
- Synchronous Redis client for rate limiting and caching
- Asynchronous Redis client for job storage
- Job store implementation with TTL-based management
- Background maintenance tasks
- Lua scripts for atomic operations

All Redis-related functionality is centralized here following best practices.

Public API:
    from db.redis_cache import (
        # Sync client
        get_redis, redis_available, redis_health,
        cache_get, cache_set, cache_delete,
        cache_get_json, cache_set_json,
        idem_get, idem_set,
        incr_with_ttl, ttl,

        # Async client
        get_async_redis, close_async_redis,
        async_redis_health, async_redis_available,

        # Job storage
        RedisJobStore, RedisIdempotencyStore, RedisEventStore,
        RedisMaintenanceScheduler,
    )
"""

from __future__ import annotations

__version__ = "1.0.0"

# Re-export public API from client modules
# Tools cache helpers
from db.redis_cache import tools_cache
from db.redis_cache.async_client import (
    async_redis_available,
    async_redis_health,
    close_async_redis,
    get_async_redis,
)
from db.redis_cache.client import (
    cache_delete,
    cache_get,
    cache_get_json,
    cache_set,
    cache_set_json,
    get_redis,
    idem_get,
    idem_set,
    incr_with_ttl,
    redis_available,
    redis_health,
    ttl,
)
from db.redis_cache.job_store import (
    RedisEventStore,
    RedisIdempotencyStore,
    RedisJobStore,
)
from db.redis_cache.maintenance import RedisMaintenanceScheduler

__all__ = [
    "RedisEventStore",
    "RedisIdempotencyStore",
    # Job storage
    "RedisJobStore",
    # Maintenance
    "RedisMaintenanceScheduler",
    "async_redis_available",
    "async_redis_health",
    "cache_delete",
    "cache_get",
    "cache_get_json",
    "cache_set",
    "cache_set_json",
    "close_async_redis",
    # Async client
    "get_async_redis",
    # Sync client
    "get_redis",
    "idem_get",
    "idem_set",
    "incr_with_ttl",
    "redis_available",
    "redis_health",
    # Tools cache
    "tools_cache",
    "ttl",
]
