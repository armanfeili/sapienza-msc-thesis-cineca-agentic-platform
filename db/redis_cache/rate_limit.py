"""Redis-based rate limiting using sliding window algorithm."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict

from db.redis_cache.async_client import get_async_redis

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, limit: int, window: int, retry_after: int):
        self.limit = limit
        self.window = window
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded: {limit} requests per {window}s. " f"Retry after {retry_after}s.")


_LOCAL_RATE_DATA: dict[str, list[float]] = defaultdict(list)
_LOCAL_DATA_LOCK: asyncio.Lock | None = None
_LOCAL_WARNING_EMITTED = False


async def _get_local_lock() -> asyncio.Lock:
    global _LOCAL_DATA_LOCK
    if _LOCAL_DATA_LOCK is None:
        _LOCAL_DATA_LOCK = asyncio.Lock()
    return _LOCAL_DATA_LOCK


def _record_rate_limit_metrics(key: str, current_count: int, limit: int) -> None:
    from contextlib import suppress

    allowed = current_count < limit

    with suppress(Exception):
        from src.observability.rate_limit_metrics import record_rate_limit_check

        key_parts = key.split(":")
        scope = "tenant" if "tenant" in key else "user"
        action_idx = 1 if scope == "user" else 2
        action = key_parts[action_idx] if len(key_parts) > action_idx else key
        record_rate_limit_check(
            action=action,
            scope=scope,
            allowed=allowed,
            current=current_count,
            limit=limit,
        )


def _log_local_fallback(exc: Exception) -> None:
    global _LOCAL_WARNING_EMITTED
    if not _LOCAL_WARNING_EMITTED:
        logger.warning(
            "Redis unavailable for rate limiting; using in-memory fallback",
            extra={"error": str(exc)},
        )
        _LOCAL_WARNING_EMITTED = True


async def _check_rate_limit_local(key: str, limit: int, window: int) -> tuple[bool, int, int]:
    lock = await _get_local_lock()
    now = time.time()
    window_start = now - window

    async with lock:
        entries = [ts for ts in _LOCAL_RATE_DATA.get(key, []) if ts >= window_start]
        current_count = len(entries)
        if current_count >= limit:
            oldest_timestamp = entries[0] if entries else now
            retry_after = int(oldest_timestamp + window - now) + 1
            _LOCAL_RATE_DATA[key] = entries
            _record_rate_limit_metrics(key, current_count, limit)
            return False, 0, retry_after

        entries.append(now)
        _LOCAL_RATE_DATA[key] = entries
        remaining = max(0, limit - len(entries))

    _record_rate_limit_metrics(key, current_count, limit)
    return True, remaining, 0


async def check_rate_limit(
    key: str,
    limit: int,
    window: int,
) -> tuple[bool, int, int]:
    """
    Check if rate limit is exceeded using sliding window algorithm.

    This implementation uses Redis sorted sets to track timestamps of requests
    within a sliding window. Old entries are automatically cleaned up.

    Args:
        key: Redis key for this rate limit (e.g., "ratelimit:sessions:user123")
        limit: Maximum number of requests allowed in the window
        window: Time window in seconds

    Returns:
        Tuple of (allowed, remaining, retry_after):
        - allowed: True if request is allowed, False if rate limit exceeded
        - remaining: Number of requests remaining in current window
        - retry_after: Seconds to wait before retry (0 if allowed)

    Example:
        >>> allowed, remaining, retry = await check_rate_limit(
        ...     "ratelimit:sessions:user123",
        ...     limit=10,
        ...     window=60
        ... )
        >>> if not allowed:
        ...     raise RateLimitExceeded(10, 60, retry)
    """
    try:
        redis = await get_async_redis()
    except Exception as exc:
        _log_local_fallback(exc)
        return await _check_rate_limit_local(key, limit, window)

    now = time.time()
    window_start = now - window

    try:
        # Use pipeline for atomic operations
        pipe = redis.pipeline()

        # Remove old entries outside the window
        pipe.zremrangebyscore(key, 0, window_start)

        # Count current entries in the window
        pipe.zcard(key)

        # Get oldest entry timestamp for retry_after calculation
        pipe.zrange(key, 0, 0, withscores=True)

        # Execute pipeline
        results = await pipe.execute()
        current_count = results[1]
        oldest_entries = results[2]

        _record_rate_limit_metrics(key, current_count, limit)

        if current_count >= limit:
            # Rate limit exceeded
            if oldest_entries:
                oldest_timestamp = oldest_entries[0][1]
                retry_after = int(oldest_timestamp + window - now) + 1
            else:
                retry_after = window

            return False, 0, retry_after

        # Add current request timestamp
        await redis.zadd(key, {str(now): now})

        # Set expiration to window duration (cleanup)
        await redis.expire(key, window)

        remaining = limit - current_count - 1
        return True, remaining, 0
    except Exception as exc:
        _log_local_fallback(exc)
        return await _check_rate_limit_local(key, limit, window)


async def increment_rate_limit(
    key: str,
    limit: int,
    window: int,
) -> tuple[int, int]:
    """
    Increment rate limit counter and check if exceeded.

    Simplified version that doesn't pre-check, just increments and validates.
    Useful when you want to track usage unconditionally.

    Args:
        key: Redis key for this rate limit
        limit: Maximum requests allowed
        window: Time window in seconds

    Returns:
        Tuple of (current_count, retry_after):
        - current_count: Current number of requests in window
        - retry_after: Seconds to wait if exceeded (0 if not)
    """
    try:
        redis = await get_async_redis()
    except Exception as exc:
        _log_local_fallback(exc)
        return await _increment_rate_limit_local(key, limit, window)

    now = time.time()
    window_start = now - window

    try:
        pipe = redis.pipeline()

        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)

        # Add current request
        pipe.zadd(key, {str(now): now})

        # Count current entries
        pipe.zcard(key)

        # Get oldest entry for retry calculation
        pipe.zrange(key, 0, 0, withscores=True)

        # Set expiration
        pipe.expire(key, window)

        results = await pipe.execute()
        current_count = results[2]
        oldest_entries = results[3]

        if current_count > limit:
            if oldest_entries:
                oldest_timestamp = oldest_entries[0][1]
                retry_after = int(oldest_timestamp + window - now) + 1
            else:
                retry_after = window
        else:
            retry_after = 0

        return current_count, retry_after
    except Exception as exc:
        _log_local_fallback(exc)
        return await _increment_rate_limit_local(key, limit, window)


async def get_rate_limit_status(
    key: str,
    limit: int,
    window: int,
) -> tuple[int, int, int]:
    """
    Get current rate limit status without incrementing.

    Args:
        key: Redis key for this rate limit
        limit: Maximum requests allowed
        window: Time window in seconds

    Returns:
        Tuple of (current, remaining, reset_in):
        - current: Current request count in window
        - remaining: Requests remaining before limit
        - reset_in: Seconds until window resets (oldest entry expires)
    """
    try:
        redis = await get_async_redis()
    except Exception as exc:
        _log_local_fallback(exc)
        return await _get_rate_limit_status_local(key, limit, window)

    now = time.time()
    window_start = now - window

    try:
        pipe = redis.pipeline()

        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)

        # Count current entries
        pipe.zcard(key)

        # Get oldest entry
        pipe.zrange(key, 0, 0, withscores=True)

        results = await pipe.execute()
        current_count = results[1]
        oldest_entries = results[2]

        remaining = max(0, limit - current_count)

        if oldest_entries:
            oldest_timestamp = oldest_entries[0][1]
            reset_in = int(oldest_timestamp + window - now)
        else:
            reset_in = 0

        return current_count, remaining, reset_in
    except Exception as exc:
        _log_local_fallback(exc)
        return await _get_rate_limit_status_local(key, limit, window)


async def reset_rate_limit(key: str) -> None:
    """
    Reset rate limit by deleting the key.

    Useful for testing or admin override.

    Args:
        key: Redis key to reset
    """
    try:
        redis = await get_async_redis()
    except Exception as exc:
        _log_local_fallback(exc)
        await _reset_rate_limit_local(key)
        return

    try:
        await redis.delete(key)
    except Exception as exc:
        _log_local_fallback(exc)
        await _reset_rate_limit_local(key)


async def _increment_rate_limit_local(key: str, limit: int, window: int) -> tuple[int, int]:
    lock = await _get_local_lock()
    now = time.time()
    window_start = now - window

    async with lock:
        entries = [ts for ts in _LOCAL_RATE_DATA.get(key, []) if ts >= window_start]
        entries.append(now)
        _LOCAL_RATE_DATA[key] = entries
        current_count = len(entries)

        if current_count > limit:
            oldest_timestamp = entries[0]
            retry_after = int(oldest_timestamp + window - now) + 1
        else:
            retry_after = 0

    return current_count, retry_after


async def _get_rate_limit_status_local(key: str, limit: int, window: int) -> tuple[int, int, int]:
    lock = await _get_local_lock()
    now = time.time()
    window_start = now - window

    async with lock:
        entries = [ts for ts in _LOCAL_RATE_DATA.get(key, []) if ts >= window_start]
        _LOCAL_RATE_DATA[key] = entries
        current_count = len(entries)
        remaining = max(0, limit - current_count)
        if entries:
            reset_in = max(0, int(entries[0] + window - now))
        else:
            reset_in = 0

    return current_count, remaining, reset_in


async def _reset_rate_limit_local(key: str) -> None:
    lock = await _get_local_lock()
    async with lock:
        _LOCAL_RATE_DATA.pop(key, None)


# Rate limit mode configuration
RATE_LIMIT_MODE = os.environ.get("RATE_LIMIT_MODE", "prod").lower()

# Production vs Test rate limit configurations
_RATE_LIMIT_CONFIGS = {
    "prod": {
        # Per-user limits
        "sessions:create": {"limit": 10, "window": 60},
        "steps:create": {"limit": 100, "window": 60},
        "runs:create": {"limit": 20, "window": 60},
        "sessions:list": {"limit": 100, "window": 60},
        "steps:list": {"limit": 100, "window": 60},
        # Per-tenant quotas (higher limits for organizational use)
        "tenant:sessions:create": {"limit": 1000, "window": 3600},  # 1000/hour per tenant
        "tenant:steps:create": {"limit": 10000, "window": 3600},  # 10000/hour per tenant
        "tenant:runs:create": {"limit": 2000, "window": 3600},  # 2000/hour per tenant
    },
    "test": {
        "sessions:create": {"limit": 10000, "window": 60},
        "steps:create": {"limit": 10000, "window": 60},
        "runs:create": {"limit": 10000, "window": 60},
        "sessions:list": {"limit": 10000, "window": 60},
        "steps:list": {"limit": 10000, "window": 60},
        "tenant:sessions:create": {"limit": 100000, "window": 3600},
        "tenant:steps:create": {"limit": 100000, "window": 3600},
        "tenant:runs:create": {"limit": 100000, "window": 3600},
    },
}


def _get_rate_limits():
    """Get rate limits based on RATE_LIMIT_MODE."""
    mode = RATE_LIMIT_MODE
    if mode not in _RATE_LIMIT_CONFIGS:
        raise ValueError(f"Invalid RATE_LIMIT_MODE: {mode}. Must be 'prod' or 'test'")
    return _RATE_LIMIT_CONFIGS[mode]


RATE_LIMITS = {}


def get_rate_limit_config(action: str) -> tuple[int, int]:
    """
    Get rate limit configuration for an action.

    Args:
        action: Action name (e.g., "sessions:create")

    Returns:
        Tuple of (limit, window)

    Raises:
        KeyError: If action not found
    """
    rate_limits = _get_rate_limits()
    if action not in rate_limits:
        raise KeyError(f"Unknown rate limit action: {action}")
    config = rate_limits[action]
    return config["limit"], config["window"]


def make_rate_limit_key(action: str, user_id: str, resource_id: str | None = None) -> str:
    """
    Create Redis key for rate limiting.

    Args:
        action: Action being rate limited (e.g., "sessions:create")
        user_id: User ID performing the action
        resource_id: Optional resource ID (e.g., session_id for steps)

    Returns:
        Redis key string

    Examples:
        >>> make_rate_limit_key("sessions:create", "user123")
        'ratelimit:sessions:create:user123'

        >>> make_rate_limit_key("steps:create", "user123", "session456")
        'ratelimit:steps:create:user123:session456'
    """
    if resource_id:
        return f"ratelimit:{action}:{user_id}:{resource_id}"
    return f"ratelimit:{action}:{user_id}"


def make_tenant_quota_key(action: str, tenant_id: str) -> str:
    """
    Create Redis key for tenant-level quotas.

    Per-tenant quotas enforce organization-wide limits across all users.
    These are checked in addition to per-user rate limits.

    Args:
        action: Action being quota-limited (e.g., "sessions:create")
        tenant_id: Tenant ID for the quota

    Returns:
        Redis key string

    Examples:
        >>> make_tenant_quota_key("sessions:create", "tenant-acme")
        'ratelimit:tenant:sessions:create:tenant-acme'
    """
    return f"ratelimit:tenant:{action}:{tenant_id}"


async def check_tenant_quota(
    action: str,
    tenant_id: str,
) -> tuple[bool, int, int]:
    """
    Check if tenant quota is exceeded.

    This is similar to check_rate_limit but applies to entire tenants.
    Should be checked alongside per-user limits.

    Args:
        action: Action being quota-limited
        tenant_id: Tenant ID

    Returns:
        Tuple of (allowed, remaining, retry_after)

    Example:
        >>> allowed, remaining, retry = await check_tenant_quota(
        ...     "sessions:create",
        ...     "tenant-acme"
        ... )
    """
    tenant_action = f"tenant:{action}"
    limit, window = get_rate_limit_config(tenant_action)
    key = make_tenant_quota_key(action, tenant_id)

    allowed, remaining, retry_after = await check_rate_limit(key, limit, window)

    # Record tenant quota exceeded metric
    if not allowed:
        from contextlib import suppress

        with suppress(Exception):
            from src.observability.rate_limit_metrics import record_tenant_quota_exceeded

            record_tenant_quota_exceeded(action, tenant_id)

    return allowed, remaining, retry_after
