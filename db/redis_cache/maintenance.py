"""
Background maintenance tasks for Redis job store.

Periodic tasks to prevent resource leaks and maintain index hygiene.
"""

import asyncio
import contextlib
import logging

from db.redis_cache.async_client import get_async_redis
from db.redis_cache.job_store import RedisJobStore
from src.config import settings

logger = logging.getLogger(__name__)


class RedisMaintenanceScheduler:
    """
    Schedules periodic maintenance tasks for Redis job store.

    Tasks:
    - Index orphan cleanup: Remove stale ZSET members whose jobs expired
    - Health checks: Verify Redis connectivity and index consistency
    """

    def __init__(
        self,
        cleanup_interval_seconds: int = 3600,  # 1 hour default
        batch_size: int = 500,
    ):
        self._cleanup_interval = cleanup_interval_seconds
        self._batch_size = batch_size
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        """Start maintenance scheduler."""
        if self._running:
            logger.warning("redis.maintenance.already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._maintenance_loop())
        logger.info(
            "redis.maintenance.started",
            extra={
                "cleanup_interval_seconds": self._cleanup_interval,
                "batch_size": self._batch_size,
            },
        )

    async def stop(self):
        """Stop maintenance scheduler gracefully."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            logger.info("redis.maintenance.stopped")

    async def _maintenance_loop(self):
        """Main loop: run cleanup tasks periodically."""
        while self._running:
            try:
                await self._run_cleanup_cycle()
                await asyncio.sleep(self._cleanup_interval)
            except asyncio.CancelledError:
                logger.info("redis.maintenance.cancelled")
                break
            except Exception as e:
                logger.error(f"redis.maintenance.cycle_failed: {e}", exc_info=True)
                # Continue loop even if one cycle fails
                await asyncio.sleep(self._cleanup_interval)

    async def _run_cleanup_cycle(self):
        """Execute one cleanup cycle: scan all indexes and remove orphans."""
        store = RedisJobStore()
        redis = await get_async_redis()

        try:
            start_time = asyncio.get_event_loop().time()
            total_removed = 0

            # 1. Clean global index
            removed = await store.cleanup_orphaned_index_members("jobs:all", batch_size=self._batch_size)
            total_removed += removed

            # 2. Clean status indexes
            for status in ["queued", "running", "finished", "failed", "cancelled"]:
                index_key = f"jobs:status:{status}"
                removed = await store.cleanup_orphaned_index_members(index_key, batch_size=self._batch_size)
                total_removed += removed

            # 3. Clean owner indexes (scan with SCAN cursor)
            cursor = 0
            owner_indexes_cleaned = 0

            while True:
                # Find jobs:owner:* keys
                cursor, keys = await redis.scan(cursor=cursor, match="jobs:owner:*", count=100)

                for key_bytes in keys:
                    key = key_bytes.decode("utf-8") if isinstance(key_bytes, bytes) else key_bytes
                    removed = await store.cleanup_orphaned_index_members(key, batch_size=self._batch_size)
                    total_removed += removed
                    owner_indexes_cleaned += 1

                if cursor == 0:
                    break

            elapsed = asyncio.get_event_loop().time() - start_time

            logger.info(
                "redis.maintenance.cleanup_complete",
                extra={
                    "total_orphans_removed": total_removed,
                    "owner_indexes_cleaned": owner_indexes_cleaned,
                    "elapsed_seconds": round(elapsed, 2),
                },
            )

            # Record metric (if metrics module exists)
            try:
                from src.jobs.metrics import record_index_cleanup

                record_index_cleanup(total_removed)
            except ImportError:
                pass

        except Exception as e:
            logger.error(f"redis.maintenance.cleanup_failed: {e}", exc_info=True)
            raise


# Global scheduler instance (initialized in app startup)
_maintenance_scheduler: RedisMaintenanceScheduler | None = None


async def start_redis_maintenance(
    cleanup_interval_seconds: int = 3600,
    batch_size: int = 500,
):
    """
    Start Redis maintenance scheduler (called from app startup).

    Args:
        cleanup_interval_seconds: How often to run cleanup (default 1 hour)
        batch_size: Max members to check per index scan (default 500)
    """
    global _maintenance_scheduler

    if settings.JOB_STORE_BACKEND != "redis":
        logger.info("redis.maintenance.skipped: not using Redis backend")
        return

    if _maintenance_scheduler is None:
        _maintenance_scheduler = RedisMaintenanceScheduler(
            cleanup_interval_seconds=cleanup_interval_seconds,
            batch_size=batch_size,
        )
        await _maintenance_scheduler.start()
    else:
        logger.warning("redis.maintenance.already_initialized")


async def stop_redis_maintenance():
    """Stop Redis maintenance scheduler (called from app shutdown)."""
    global _maintenance_scheduler

    if _maintenance_scheduler:
        await _maintenance_scheduler.stop()
        _maintenance_scheduler = None
