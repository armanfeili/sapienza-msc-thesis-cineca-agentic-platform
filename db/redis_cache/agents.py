"""
Redis helpers for agent sessions, steps, and runs.

Provides:
- Session state caching
- Step sequence allocation
- Distributed locks
- Cancellation flags
- ETag computation and caching
- Idempotency support
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from db.redis_cache.client import (
    cache_delete,
    cache_get,
    cache_get_json,
    cache_set,
    cache_set_json,
    get_redis,
)
from src.config import settings

logger = logging.getLogger(__name__)


# ============ Session State Cache ============


def get_session_cache_key(session_id: UUID | str) -> str:
    """Get Redis key for session state cache."""
    return f"agent:session:{session_id}"


def get_session_state(session_id: UUID | str) -> dict[str, Any] | None:
    """
    Retrieve cached session state from Redis.

    Returns:
        Dict with status, last_seq, last_step_id, heartbeat_ts, etc. or None
    """
    key = get_session_cache_key(session_id)
    return cache_get_json(key)


def set_session_state(session_id: UUID | str, state: dict[str, Any], ttl: int = 3600) -> bool:
    """
    Cache session state in Redis with TTL.

    Args:
        session_id: Session UUID
        state: State dict (status, last_seq, etc.)
        ttl: Time-to-live in seconds (default 1 hour)

    Returns:
        True if successful
    """
    key = get_session_cache_key(session_id)
    return cache_set_json(key, state, ex=ttl)


def delete_session_state(session_id: UUID | str) -> int:
    """Delete cached session state."""
    key = get_session_cache_key(session_id)
    return cache_delete(key)


def update_session_heartbeat(session_id: UUID | str) -> bool:
    """Update session heartbeat timestamp in cache."""
    state = get_session_state(session_id)
    if state is None:
        return False
    state["heartbeat_ts"] = time.time()
    return set_session_state(session_id, state)


# ============ Step Sequencing ============


def get_step_seq_key(session_id: UUID | str) -> str:
    """Get Redis key for step sequence counter."""
    return f"agent:seq:{session_id}"


def allocate_next_seq(session_id: UUID | str) -> int:
    """
    Allocate next sequence number for a step in this session.

    Uses Redis INCR for atomic allocation.

    Returns:
        Next sequence number (1-indexed)
    """
    key = get_step_seq_key(session_id)
    try:
        r = get_redis()
        seq = r.incr(key)
        # Set TTL on first increment (to prevent orphan counters)
        if seq == 1:
            r.expire(key, 7 * 24 * 3600)  # 7 days
        return int(seq)
    except Exception as exc:
        logger.error(f"Failed to allocate seq for session {session_id}: {exc}")
        raise


# ============ Distributed Locks ============


@contextmanager
def session_lock(session_id: UUID | str, timeout: int = 10) -> Generator[bool, None, None]:
    """
    Acquire distributed lock for session mutations.

    Usage:
        with session_lock(session_id):
            # perform atomic operations

    Args:
        session_id: Session UUID
        timeout: Lock timeout in seconds

    Yields:
        True if lock acquired, raises RuntimeError otherwise
    """
    lock_key = f"lock:session:{session_id}"
    lock_value = f"{time.time()}"

    try:
        r = get_redis()
        acquired = r.set(lock_key, lock_value, nx=True, ex=timeout)
        if not acquired:
            raise RuntimeError(f"Failed to acquire lock for session {session_id}")

        yield True

    finally:
        try:
            # Release lock (only if we still own it)
            r = get_redis()
            current = r.get(lock_key)
            if current == lock_value:
                r.delete(lock_key)
        except Exception as exc:
            logger.warning(f"Failed to release lock for session {session_id}: {exc}")


@contextmanager
def step_lock(session_id: UUID | str, seq: int, timeout: int = 5) -> Generator[bool, None, None]:
    """
    Acquire distributed lock for a specific step (for idempotent writes).

    Args:
        session_id: Session UUID
        seq: Step sequence number
        timeout: Lock timeout in seconds

    Yields:
        True if lock acquired
    """
    lock_key = f"lock:step:{session_id}:{seq}"
    lock_value = f"{time.time()}"

    try:
        r = get_redis()
        acquired = r.set(lock_key, lock_value, nx=True, ex=timeout)
        if not acquired:
            raise RuntimeError(f"Failed to acquire lock for step {session_id}:{seq}")

        yield True

    finally:
        try:
            r = get_redis()
            current = r.get(lock_key)
            if current == lock_value:
                r.delete(lock_key)
        except Exception as exc:
            logger.warning(f"Failed to release step lock {session_id}:{seq}: {exc}")


# ============ Cancellation Flags ============


def get_cancel_key(session_id: UUID | str) -> str:
    """Get Redis key for session cancellation flag."""
    return f"cancel:session:{session_id}"


def is_session_cancelled(session_id: UUID | str) -> bool:
    """Check if session has been cancelled."""
    key = get_cancel_key(session_id)
    value = cache_get(key)
    return value == "1"


def set_session_cancelled(session_id: UUID | str, ttl: int = 3600) -> bool:
    """
    Mark session as cancelled.

    Args:
        session_id: Session UUID
        ttl: How long to keep the flag (seconds)

    Returns:
        True if successful
    """
    key = get_cancel_key(session_id)
    return cache_set(key, "1", ex=ttl)


def clear_session_cancelled(session_id: UUID | str) -> int:
    """Clear cancellation flag."""
    key = get_cancel_key(session_id)
    return cache_delete(key)


# ============ ETag Support ============


def compute_list_etag(user_id: str, items: list, extra: str | None = None) -> str:
    """
    Compute ETag for a list response.

    Args:
        user_id: User identifier (for scoping)
        items: List of items (will be serialized)
        extra: Optional extra data to include in hash

    Returns:
        MD5 hex digest
    """
    components = [user_id, json.dumps(items, sort_keys=True, default=str)]
    if extra:
        components.append(extra)
    data = ":".join(components)
    return hashlib.md5(data.encode()).hexdigest()


def get_sessions_etag_key(user_id: str) -> str:
    """Get Redis key for sessions list ETag."""
    return f"etag:sessions:{user_id}"


def get_sessions_etag(user_id: str) -> str | None:
    """Get cached ETag for user's sessions list."""
    key = get_sessions_etag_key(user_id)
    return cache_get(key)


def set_sessions_etag(user_id: str, etag: str, ttl: int = 60) -> bool:
    """
    Cache ETag for user's sessions list.

    Args:
        user_id: User identifier
        etag: ETag value
        ttl: Time-to-live in seconds (default 60s)
    """
    key = get_sessions_etag_key(user_id)
    return cache_set(key, etag, ex=ttl)


def invalidate_sessions_etag(user_id: str) -> int:
    """Invalidate cached sessions list ETag."""
    key = get_sessions_etag_key(user_id)
    return cache_delete(key)


def get_steps_etag_key(session_id: UUID | str) -> str:
    """Get Redis key for steps list ETag."""
    return f"etag:steps:{session_id}"


def get_steps_etag(session_id: UUID | str) -> str | None:
    """Get cached ETag for session's steps list."""
    key = get_steps_etag_key(session_id)
    return cache_get(key)


def set_steps_etag(session_id: UUID | str, etag: str, ttl: int = 60) -> bool:
    """Cache ETag for session's steps list."""
    key = get_steps_etag_key(session_id)
    return cache_set(key, etag, ex=ttl)


def invalidate_steps_etag(session_id: UUID | str) -> int:
    """Invalidate cached steps list ETag."""
    key = get_steps_etag_key(session_id)
    return cache_delete(key)


# ============ Idempotency Support ============


def get_idempotency_cache_key(idem_key: str) -> str:
    """Get Redis key for idempotency cache."""
    return f"idem:agent:{idem_key}"


def get_idempotent_response(idem_key: str) -> dict[str, Any] | None:
    """
    Retrieve cached response for idempotency key.

    Returns:
        Dict with keys 'body' (response body) and 'status_code' (HTTP status),
        or None if not found
    """
    key = get_idempotency_cache_key(idem_key)
    return cache_get_json(key)


def cache_idempotent_response(
    idem_key: str,
    response_body: dict[str, Any],
    status_code: int = 200,
    ttl: int | None = None,
) -> bool:
    """
    Cache response for idempotency replay.

    Args:
        idem_key: Idempotency key
        response_body: Response dict to cache
        status_code: HTTP status code of the response
        ttl: Time-to-live in seconds (default from settings)

    Returns:
        True if cached successfully
    """
    key = get_idempotency_cache_key(idem_key)
    if ttl is None:
        ttl = settings.IDEMPOTENCY_TTL_SECONDS

    # Cache both response body and status code
    cached_response = {
        "body": response_body,
        "status_code": status_code,
    }

    return cache_set_json(key, cached_response, ex=ttl)


__all__ = [
    "allocate_next_seq",
    "cache_idempotent_response",
    "clear_session_cancelled",
    "compute_list_etag",
    "delete_session_state",
    "get_idempotent_response",
    "get_session_state",
    "get_sessions_etag",
    "get_steps_etag",
    "invalidate_sessions_etag",
    "invalidate_steps_etag",
    "is_session_cancelled",
    "session_lock",
    "set_session_cancelled",
    "set_session_state",
    "set_sessions_etag",
    "set_steps_etag",
    "step_lock",
    "update_session_heartbeat",
]
