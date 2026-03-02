"""
Factory pattern for job storage backends.

Provides clean dependency injection of storage implementations
based on JOB_STORE_BACKEND configuration flag.

Enables dual-mode operation:
- memory: In-memory dict (default, for testing/development)
- redis: Redis with TTL-based auto-expiry (production)
"""

from __future__ import annotations

import logging

from src.config import settings
from src.jobs.interfaces import EventStore, IdempotencyStore, JobStore
from src.jobs.memory_store import (
    MemoryEventStore,
    MemoryIdempotencyStore,
    MemoryJobStore,
)

logger = logging.getLogger(__name__)


def get_stores() -> tuple[JobStore, IdempotencyStore, EventStore]:
    """
    Factory function for job storage backends.

    Returns appropriate store implementations based on
    settings.JOB_STORE_BACKEND configuration.

    Returns:
        Tuple of (JobStore, IdempotencyStore, EventStore)

    Raises:
        ValueError: If JOB_STORE_BACKEND has invalid value

    Example:
        >>> job_store, idem_store, event_store = get_stores()
        >>> job_id = str(uuid.uuid4())
        >>> await job_store.create(job_doc, ttl_seconds=864000)
    """
    backend = settings.JOB_STORE_BACKEND.lower()

    if backend == "memory":
        logger.info("Using in-memory job storage (no TTL)")
        return (
            MemoryJobStore(),
            MemoryIdempotencyStore(),
            MemoryEventStore(ring_size=settings.SSE_RING_SIZE),
        )

    elif backend == "redis":
        # Import here to avoid Redis dependency when using memory mode
        try:
            from db.redis_cache.job_store import (
                RedisEventStore,
                RedisIdempotencyStore,
                RedisJobStore,
            )
        except ImportError as e:
            logger.error(f"Redis store not available: {e}")
            logger.warning("Falling back to in-memory storage")
            return (
                MemoryJobStore(),
                MemoryIdempotencyStore(),
                MemoryEventStore(ring_size=settings.SSE_RING_SIZE),
            )

        logger.info(
            "Using Redis job storage " f"(TTL={settings.JOB_TTL_DAYS} days, " f"ring_size={settings.SSE_RING_SIZE})"
        )
        return (
            RedisJobStore(),
            RedisIdempotencyStore(),
            RedisEventStore(ring_size=settings.SSE_RING_SIZE),
        )

    else:
        raise ValueError(f"Invalid JOB_STORE_BACKEND: {backend!r}. " "Must be 'memory' or 'redis'.")


__all__ = ["get_stores"]
