"""
Redis caching helpers for tools invocations.

Provides key-value operations for:
- Tool invocation queue management
- Execution state tracking
- Result caching with TTL
- Idempotency key mapping
- SSE cursor tracking
- Rate limiting per tool/tenant

Key Design:
- tools:queue:{name} - List: queue of pending execution IDs for tool {name}
- tools:inv:{eid}:state - String: current state (pending/running/finished/failed/cancelled)
- tools:inv:{eid}:result - JSON: cached result with TTL (default 1 hour)
- tools:inv:{eid}:error - JSON: cached error details with TTL
- tools:idempotency:{key} - String: maps idempotency key to eid (TTL 24 hours)
- tools:sse:{eid}:cursor - String: SSE event cursor for streaming
- tools:rate:{name}:{tenant} - String: rate limit counter with TTL
"""

from __future__ import annotations

from typing import Any

from db.redis_cache.client import cache_get, cache_get_json, cache_set, cache_set_json, get_redis

# Default TTLs (in seconds)
DEFAULT_RESULT_TTL = 3600  # 1 hour
DEFAULT_ERROR_TTL = 3600  # 1 hour
DEFAULT_IDEMPOTENCY_TTL = 86400  # 24 hours
DEFAULT_STATE_TTL = 7200  # 2 hours
DEFAULT_CURSOR_TTL = 300  # 5 minutes
DEFAULT_RATE_TTL = 60  # 1 minute


# ===== Queue Management =====


def queue_push_invocation(tool_name: str, eid: str) -> int:
    """
    Push execution ID to tool's pending queue.

    Args:
        tool_name: Tool name
        eid: Execution ID to queue

    Returns:
        Queue length after push
    """
    r = get_redis()
    key = f"tools:queue:{tool_name}"
    return r.rpush(key, eid)


def queue_pop_invocation(tool_name: str, timeout: int = 0) -> str | None:
    """
    Pop execution ID from tool's queue (FIFO).

    Args:
        tool_name: Tool name
        timeout: Block timeout in seconds (0 = non-blocking)

    Returns:
        Execution ID or None if queue empty
    """
    r = get_redis()
    key = f"tools:queue:{tool_name}"

    if timeout > 0:
        # Blocking pop
        result = r.blpop(key, timeout=timeout)
        return result[1] if result else None
    else:
        # Non-blocking pop
        return r.lpop(key)


def queue_length(tool_name: str) -> int:
    """
    Get current queue length for tool.

    Args:
        tool_name: Tool name

    Returns:
        Number of pending invocations
    """
    r = get_redis()
    key = f"tools:queue:{tool_name}"
    return r.llen(key)


def queue_peek(tool_name: str, count: int = 10) -> list[str]:
    """
    Peek at pending invocations without removing them.

    Args:
        tool_name: Tool name
        count: Number of items to peek

    Returns:
        List of execution IDs (oldest first)
    """
    r = get_redis()
    key = f"tools:queue:{tool_name}"
    return r.lrange(key, 0, count - 1)


def queue_remove_invocation(tool_name: str, eid: str) -> int:
    """
    Remove specific execution ID from queue (e.g., for cancellation).

    Args:
        tool_name: Tool name
        eid: Execution ID to remove

    Returns:
        Number of items removed (0 or 1)
    """
    r = get_redis()
    key = f"tools:queue:{tool_name}"
    return r.lrem(key, 0, eid)


# ===== State Tracking =====


def set_invocation_state(eid: str, state: str, ttl: int = DEFAULT_STATE_TTL) -> bool:
    """
    Set invocation state in Redis.

    Args:
        eid: Execution ID
        state: State value (pending/running/finished/failed/cancelled)
        ttl: TTL in seconds

    Returns:
        True if set successfully
    """
    key = f"tools:inv:{eid}:state"
    return cache_set(key, state, ex=ttl)


def get_invocation_state(eid: str) -> str | None:
    """
    Get invocation state from Redis.

    Args:
        eid: Execution ID

    Returns:
        State string or None if not found
    """
    key = f"tools:inv:{eid}:state"
    return cache_get(key)


def delete_invocation_state(eid: str) -> bool:
    """
    Delete invocation state from Redis.

    Args:
        eid: Execution ID

    Returns:
        True if deleted
    """
    r = get_redis()
    key = f"tools:inv:{eid}:state"
    return bool(r.delete(key))


# ===== Result Caching =====


def cache_invocation_result(eid: str, result: dict[str, Any], ttl: int = DEFAULT_RESULT_TTL) -> bool:
    """
    Cache invocation result in Redis.

    Args:
        eid: Execution ID
        result: Result data (will be JSON-serialized)
        ttl: TTL in seconds

    Returns:
        True if cached successfully
    """
    key = f"tools:inv:{eid}:result"
    return cache_set_json(key, result, ex=ttl)


def get_cached_result(eid: str) -> dict[str, Any] | None:
    """
    Get cached invocation result from Redis.

    Args:
        eid: Execution ID

    Returns:
        Result dict or None if not cached
    """
    key = f"tools:inv:{eid}:result"
    return cache_get_json(key)


def delete_cached_result(eid: str) -> bool:
    """
    Delete cached result from Redis.

    Args:
        eid: Execution ID

    Returns:
        True if deleted
    """
    r = get_redis()
    key = f"tools:inv:{eid}:result"
    return bool(r.delete(key))


def cache_invocation_error(eid: str, error: dict[str, Any], ttl: int = DEFAULT_ERROR_TTL) -> bool:
    """
    Cache invocation error details in Redis.

    Args:
        eid: Execution ID
        error: Error data (will be JSON-serialized)
        ttl: TTL in seconds

    Returns:
        True if cached successfully
    """
    key = f"tools:inv:{eid}:error"
    return cache_set_json(key, error, ex=ttl)


def get_cached_error(eid: str) -> dict[str, Any] | None:
    """
    Get cached invocation error from Redis.

    Args:
        eid: Execution ID

    Returns:
        Error dict or None if not cached
    """
    key = f"tools:inv:{eid}:error"
    return cache_get_json(key)


# ===== Idempotency Key Mapping =====


def set_idempotency_mapping(idempotency_key: str, eid: str, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> bool:
    """
    Map idempotency key to execution ID.

    Args:
        idempotency_key: Client-provided idempotency key
        eid: Execution ID
        ttl: TTL in seconds (default 24 hours)

    Returns:
        True if set successfully
    """
    key = f"tools:idempotency:{idempotency_key}"
    return cache_set(key, eid, ex=ttl)


def get_idempotency_mapping(idempotency_key: str) -> str | None:
    """
    Get execution ID for idempotency key.

    Args:
        idempotency_key: Client-provided idempotency key

    Returns:
        Execution ID or None if not found
    """
    key = f"tools:idempotency:{idempotency_key}"
    return cache_get(key)


def delete_idempotency_mapping(idempotency_key: str) -> bool:
    """
    Delete idempotency mapping.

    Args:
        idempotency_key: Client-provided idempotency key

    Returns:
        True if deleted
    """
    r = get_redis()
    key = f"tools:idempotency:{idempotency_key}"
    return bool(r.delete(key))


# ===== SSE Cursor Tracking =====


def set_sse_cursor(eid: str, cursor: str, ttl: int = DEFAULT_CURSOR_TTL) -> bool:
    """
    Set SSE cursor for invocation streaming.

    Args:
        eid: Execution ID
        cursor: Event cursor/offset
        ttl: TTL in seconds

    Returns:
        True if set successfully
    """
    key = f"tools:sse:{eid}:cursor"
    return cache_set(key, cursor, ex=ttl)


def get_sse_cursor(eid: str) -> str | None:
    """
    Get SSE cursor for invocation.

    Args:
        eid: Execution ID

    Returns:
        Cursor string or None if not found
    """
    key = f"tools:sse:{eid}:cursor"
    return cache_get(key)


def delete_sse_cursor(eid: str) -> bool:
    """
    Delete SSE cursor.

    Args:
        eid: Execution ID

    Returns:
        True if deleted
    """
    r = get_redis()
    key = f"tools:sse:{eid}:cursor"
    return bool(r.delete(key))


# ===== Rate Limiting =====


def check_rate_limit(
    tool_name: str, tenant_id: str, max_count: int, window_secs: int = DEFAULT_RATE_TTL
) -> tuple[bool, int]:
    """
    Check and increment rate limit counter for tool/tenant.

    Args:
        tool_name: Tool name
        tenant_id: Tenant ID
        max_count: Maximum invocations allowed in window
        window_secs: Time window in seconds

    Returns:
        Tuple of (allowed, current_count)
    """
    r = get_redis()
    key = f"tools:rate:{tool_name}:{tenant_id}"

    # Get current count
    current = r.get(key)
    count = int(current) if current else 0

    if count >= max_count:
        return False, count

    # Increment with TTL
    pipe = r.pipeline()
    pipe.incr(key)
    if count == 0:
        # Set TTL on first increment
        pipe.expire(key, window_secs)
    pipe.execute()

    return True, count + 1


def get_rate_limit_count(tool_name: str, tenant_id: str) -> int:
    """
    Get current rate limit count without incrementing.

    Args:
        tool_name: Tool name
        tenant_id: Tenant ID

    Returns:
        Current count
    """
    r = get_redis()
    key = f"tools:rate:{tool_name}:{tenant_id}"
    current = r.get(key)
    return int(current) if current else 0


def reset_rate_limit(tool_name: str, tenant_id: str) -> bool:
    """
    Reset rate limit counter for tool/tenant.

    Args:
        tool_name: Tool name
        tenant_id: Tenant ID

    Returns:
        True if deleted
    """
    r = get_redis()
    key = f"tools:rate:{tool_name}:{tenant_id}"
    return bool(r.delete(key))


# ===== Bulk Operations =====


def cleanup_invocation_cache(eid: str) -> int:
    """
    Delete all Redis keys for an invocation.

    Args:
        eid: Execution ID

    Returns:
        Number of keys deleted
    """
    r = get_redis()
    keys = [
        f"tools:inv:{eid}:state",
        f"tools:inv:{eid}:result",
        f"tools:inv:{eid}:error",
        f"tools:sse:{eid}:cursor",
    ]
    return r.delete(*keys)


def get_all_queue_lengths() -> dict[str, int]:
    """
    Get queue lengths for all tools.

    Returns:
        Dict mapping tool_name to queue length
    """
    r = get_redis()
    pattern = "tools:queue:*"
    queues = {}

    for key in r.scan_iter(match=pattern, count=100):
        tool_name = key.split(":", 2)[2]  # Extract tool name from key
        queues[tool_name] = r.llen(key)

    return queues


__all__ = [
    "cache_invocation_error",
    # Result caching
    "cache_invocation_result",
    # Rate limiting
    "check_rate_limit",
    # Bulk operations
    "cleanup_invocation_cache",
    "delete_cached_result",
    "delete_idempotency_mapping",
    "delete_invocation_state",
    "delete_sse_cursor",
    "get_all_queue_lengths",
    "get_cached_error",
    "get_cached_result",
    "get_idempotency_mapping",
    "get_invocation_state",
    "get_rate_limit_count",
    "get_sse_cursor",
    "queue_length",
    "queue_peek",
    "queue_pop_invocation",
    # Queue management
    "queue_push_invocation",
    "queue_remove_invocation",
    "reset_rate_limit",
    # Idempotency
    "set_idempotency_mapping",
    # State tracking
    "set_invocation_state",
    # SSE cursors
    "set_sse_cursor",
]
