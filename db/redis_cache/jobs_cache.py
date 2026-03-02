"""Redis caching and queue helpers for jobs system."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import redis
from redis import Redis

from src.config import settings


def _get_redis() -> Redis:
    """Get Redis client instance."""
    return redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )


# ============================================================================
# Queue Operations (jobs:queue:{type})
# ============================================================================


def queue_push_job(job_type: str, job_id: UUID, priority: int = 0) -> int:
    """
    Push job ID to the queue for the given type.

    Args:
        job_type: Type of job (e.g., 'agent.run')
        job_id: Job UUID
        priority: Job priority (higher = more urgent, for future ZPUSH)

    Returns:
        New queue length
    """
    r = _get_redis()
    key = f"jobs:queue:{job_type}"
    # Using LPUSH for FIFO with RPOP (or RPUSH+LPOP)
    # For priority, would use ZADD with score=priority
    return r.lpush(key, str(job_id))


def queue_pop_job(job_type: str, timeout: int = 0) -> str | None:
    """
    Pop (claim) a job ID from the queue.

    Args:
        job_type: Type of job
        timeout: Blocking timeout in seconds (0 = non-blocking)

    Returns:
        Job ID string or None if queue empty
    """
    r = _get_redis()
    key = f"jobs:queue:{job_type}"

    if timeout > 0:
        result = r.brpop(key, timeout=timeout)
        return result[1] if result else None
    else:
        return r.rpop(key)


def queue_length(job_type: str) -> int:
    """
    Get current queue depth for a job type.

    Args:
        job_type: Type of job

    Returns:
        Number of jobs in queue
    """
    r = _get_redis()
    key = f"jobs:queue:{job_type}"
    return r.llen(key)


def queue_peek(job_type: str, count: int = 10) -> list[str]:
    """
    Peek at jobs in queue without popping.

    Args:
        job_type: Type of job
        count: Number of jobs to peek at

    Returns:
        List of job IDs (newest first)
    """
    r = _get_redis()
    key = f"jobs:queue:{job_type}"
    return r.lrange(key, 0, count - 1)


# ============================================================================
# Job State (jobs:{id}:state)
# ============================================================================


def set_job_state(
    job_id: UUID,
    status: str,
    owner_sub: str,
    *,
    progress: int | None = None,
    worker_id: str | None = None,
    ttl_seconds: int = 7200,  # 2 hours default
) -> None:
    """
    Set job state in Redis hash.

    Args:
        job_id: Job UUID
        status: Current status
        owner_sub: Job owner
        progress: Progress percentage (0-100)
        worker_id: Worker processing the job
        ttl_seconds: TTL for the state key
    """
    r = _get_redis()
    key = f"jobs:{job_id}:state"

    state = {
        "status": status,
        "owner_sub": owner_sub,
        "heartbeat_ts": datetime.utcnow().isoformat(),
    }

    if progress is not None:
        state["progress"] = str(progress)
    if worker_id:
        state["worker_id"] = worker_id

    r.hset(key, mapping=state)
    r.expire(key, ttl_seconds)


def get_job_state(job_id: UUID) -> dict[str, str] | None:
    """
    Get job state from Redis.

    Args:
        job_id: Job UUID

    Returns:
        State dictionary or None if not found
    """
    r = _get_redis()
    key = f"jobs:{job_id}:state"
    state = r.hgetall(key)
    return state if state else None


def update_heartbeat(job_id: UUID) -> bool:
    """
    Update heartbeat timestamp for a running job.

    Args:
        job_id: Job UUID

    Returns:
        True if updated, False if key doesn't exist
    """
    r = _get_redis()
    key = f"jobs:{job_id}:state"

    if r.exists(key):
        r.hset(key, "heartbeat_ts", datetime.utcnow().isoformat())
        return True
    return False


# ============================================================================
# Job Result Cache (jobs:{id}:result)
# ============================================================================


def cache_job_result(job_id: UUID, result_data: dict[str, Any], ttl_days: int = 1) -> None:
    """
    Cache job result in Redis.

    Args:
        job_id: Job UUID
        result_data: Result data to cache
        ttl_days: TTL in days (default 1 day)
    """
    r = _get_redis()
    key = f"jobs:{job_id}:result"
    ttl_seconds = ttl_days * 86400

    r.setex(key, ttl_seconds, json.dumps(result_data))


def get_cached_result(job_id: UUID) -> dict[str, Any] | None:
    """
    Get cached job result from Redis.

    Args:
        job_id: Job UUID

    Returns:
        Result data or None if not cached
    """
    r = _get_redis()
    key = f"jobs:{job_id}:result"

    data = r.get(key)
    return json.loads(data) if data else None


# ============================================================================
# Job Events Stream (jobs:{id}:events)
# ============================================================================


def append_job_event(
    job_id: UUID, event_type: str, event_data: dict[str, Any], seq_id: int, maxlen: int = 1000
) -> None:
    """
    Append event to job's event stream.

    Args:
        job_id: Job UUID
        event_type: Event type (status, log, progress, heartbeat, end)
        event_data: Event data
        seq_id: Sequence ID from PostgreSQL
        maxlen: Maximum events to retain
    """
    r = _get_redis()
    key = f"jobs:{job_id}:events"

    # Store as list with capped length
    event = {
        "seq_id": seq_id,
        "event_type": event_type,
        "event_data": event_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    r.lpush(key, json.dumps(event))
    r.ltrim(key, 0, maxlen - 1)  # Keep only last maxlen events


def get_job_events(job_id: UUID, after_seq_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """
    Get events for a job from Redis stream.

    Args:
        job_id: Job UUID
        after_seq_id: Only return events after this seq_id
        limit: Maximum events to return

    Returns:
        List of event dictionaries
    """
    r = _get_redis()
    key = f"jobs:{job_id}:events"

    # Get all events (they're in reverse order - newest first)
    events_raw = r.lrange(key, 0, -1)
    events = [json.loads(e) for e in events_raw]

    # Reverse to get chronological order
    events.reverse()

    # Filter by seq_id if specified
    if after_seq_id is not None:
        events = [e for e in events if e["seq_id"] > after_seq_id]

    return events[:limit]


# ============================================================================
# Idempotency Mapping (jobs:idemp:{owner}:{key})
# ============================================================================


def set_idempotency_mapping(owner_sub: str, idempotency_key: str, job_id: UUID, ttl_hours: int = 24) -> None:
    """
    Set idempotency key mapping.

    Args:
        owner_sub: Owner identifier
        idempotency_key: Idempotency key
        job_id: Job UUID
        ttl_hours: TTL in hours (default 24 hours)
    """
    r = _get_redis()
    key = f"jobs:idemp:{owner_sub}:{idempotency_key}"
    ttl_seconds = ttl_hours * 3600

    r.setex(key, ttl_seconds, str(job_id))


def get_idempotency_mapping(owner_sub: str, idempotency_key: str) -> str | None:
    """
    Get job ID from idempotency key mapping.

    Args:
        owner_sub: Owner identifier
        idempotency_key: Idempotency key

    Returns:
        Job ID string or None if not found
    """
    r = _get_redis()
    key = f"jobs:idemp:{owner_sub}:{idempotency_key}"
    return r.get(key)


# ============================================================================
# Cancel Flag (jobs:cancel:{id})
# ============================================================================


def set_cancel_flag(job_id: UUID, ttl_seconds: int = 3600) -> bool:
    """
    Set cancel flag for a job (atomic operation).

    Uses Lua script to only set flag if job is not already cancelled.

    Args:
        job_id: Job UUID
        ttl_seconds: TTL for cancel flag

    Returns:
        True if flag was set, False if already set
    """
    r = _get_redis()
    cancel_key = f"jobs:cancel:{job_id}"

    # Atomic set-if-not-exists
    result = r.set(cancel_key, "1", ex=ttl_seconds, nx=True)
    return result is not None


def check_cancel_flag(job_id: UUID) -> bool:
    """
    Check if cancel flag is set for a job.

    Args:
        job_id: Job UUID

    Returns:
        True if cancel flag is set
    """
    r = _get_redis()
    cancel_key = f"jobs:cancel:{job_id}"
    return r.exists(cancel_key) > 0


def clear_cancel_flag(job_id: UUID) -> None:
    """
    Clear cancel flag for a job.

    Args:
        job_id: Job UUID
    """
    r = _get_redis()
    cancel_key = f"jobs:cancel:{job_id}"
    r.delete(cancel_key)


# ============================================================================
# Atomic Cancel Script
# ============================================================================

ATOMIC_CANCEL_SCRIPT = """
local state_key = KEYS[1]
local cancel_key = KEYS[2]
local ttl = ARGV[1]

-- Get current status from state hash
local status = redis.call('HGET', state_key, 'status')

-- Only set cancel if not in terminal state
if status and (status == 'queued' or status == 'running') then
    redis.call('SETEX', cancel_key, ttl, '1')
    return 1
else
    return 0
end
"""


def atomic_cancel_if_not_terminal(job_id: UUID, ttl_seconds: int = 3600) -> bool:
    """
    Atomically set cancel flag only if job is not in terminal state.

    Uses Lua script to check state and set flag in single operation.

    Args:
        job_id: Job UUID
        ttl_seconds: TTL for cancel flag

    Returns:
        True if cancel flag was set, False if job is terminal
    """
    r = _get_redis()
    state_key = f"jobs:{job_id}:state"
    cancel_key = f"jobs:cancel:{job_id}"

    # Execute Lua script
    result = r.eval(ATOMIC_CANCEL_SCRIPT, 2, state_key, cancel_key, ttl_seconds)  # Number of keys

    return result == 1


# ============================================================================
# Cleanup Helpers
# ============================================================================


def cleanup_job_keys(job_id: UUID) -> int:
    """
    Clean up all Redis keys for a job.

    Args:
        job_id: Job UUID

    Returns:
        Number of keys deleted
    """
    r = _get_redis()
    keys = [
        f"jobs:{job_id}:state",
        f"jobs:{job_id}:result",
        f"jobs:{job_id}:events",
        f"jobs:cancel:{job_id}",
    ]

    return r.delete(*keys)
