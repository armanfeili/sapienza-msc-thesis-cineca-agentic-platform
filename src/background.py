"""
Background subsystem bootstrapper.

This module wires up a lightweight APScheduler-based manager that can:
  - run periodic health checks,
  - run scheduled backups,
  - run periodic cleanup,
while recording metrics and logging outcomes.

It is intentionally framework-agnostic; FastAPI can import and use
`lifespan()` for app startup/shutdown, or call `BackgroundManager.start/stop`
manually and stash the instance in `app.state`.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.config import settings
from src.services.archive import ArchiveService
from src.services.health import HealthService
from src.services.service_metrics import ServiceMetrics

log = structlog.get_logger(__name__)


@dataclass
class BackgroundConfig:
    enabled: bool = getattr(settings, "BACKGROUND_ENABLED", True)

    # Health probe interval (seconds)
    health_enabled: bool = getattr(settings, "BACKGROUND_HEALTH_ENABLED", True)
    health_interval_seconds: int = getattr(settings, "BACKGROUND_HEALTH_INTERVAL_SECONDS", 30)

    # Backups via cron (crontab format, UTC)
    backup_enabled: bool = getattr(settings, "BACKGROUND_BACKUPS_ENABLED", False)
    backup_cron: str = getattr(settings, "BACKGROUND_BACKUPS_CRON", "30 2 * * *")  # 02:30 UTC daily

    # Cleanup via cron (crontab format, UTC)
    cleanup_enabled: bool = getattr(settings, "BACKGROUND_CLEANUP_ENABLED", False)
    cleanup_cron: str = getattr(settings, "BACKGROUND_CLEANUP_CRON", "15 3 * * 0")  # 03:15 UTC Sundays

    # Redis job store index cleanup (hourly interval)
    redis_cleanup_enabled: bool = getattr(settings, "BACKGROUND_REDIS_CLEANUP_ENABLED", True)
    redis_cleanup_interval_seconds: int = getattr(settings, "BACKGROUND_REDIS_CLEANUP_INTERVAL", 3600)  # 1 hour
    redis_cleanup_batch_size: int = getattr(settings, "BACKGROUND_REDIS_CLEANUP_BATCH_SIZE", 500)


class BackgroundManager:
    """Coordinates background jobs with metrics and logging."""

    def __init__(
        self,
        *,
        health: HealthService | None = None,
        archive: ArchiveService | None = None,
        metrics: ServiceMetrics | None = None,
        config: BackgroundConfig | None = None,
    ) -> None:
        self.config = config or BackgroundConfig()
        self.scheduler: AsyncIOScheduler | None = None
        self.health = health or HealthService()
        self.archive = archive or ArchiveService()
        self.metrics = metrics or ServiceMetrics()
        self._started = False

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────
    async def start(self) -> None:
        """Start the underlying scheduler and register jobs."""
        if not self.config.enabled:
            log.info("background.disabled")
            return

        if self._started:
            log.debug("background.already_started")
            return

        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._register_jobs()
        self.scheduler.start()
        self._started = True
        log.info(
            "background.started",
            health_enabled=self.config.health_enabled,
            backups_enabled=self.config.backup_enabled,
            cleanup_enabled=self.config.cleanup_enabled,
        )

    async def stop(self) -> None:
        """Stop scheduler and wait for any running jobs to finish."""
        if not self._started or not self.scheduler:
            return
        try:
            self.scheduler.shutdown(wait=True)
            log.info("background.stopped")
        finally:
            self._started = False
            self.scheduler = None

    # ──────────────────────────────────────────────────────────────────
    # Scheduling
    # ──────────────────────────────────────────────────────────────────
    def _register_jobs(self) -> None:
        assert self.scheduler is not None

        if self.config.health_enabled:
            self.scheduler.add_job(
                self._wrap_job(self._job_health, "health"),
                IntervalTrigger(seconds=max(1, int(self.config.health_interval_seconds))),
                id="background.health",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
            )

        if self.config.backup_enabled:
            with contextlib.suppress(ValueError):
                self.scheduler.add_job(
                    self._wrap_job(self._job_backup, "backup"),
                    CronTrigger.from_crontab(self.config.backup_cron),
                    id="background.backup",
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                )

        if self.config.cleanup_enabled:
            with contextlib.suppress(ValueError):
                self.scheduler.add_job(
                    self._wrap_job(self._job_cleanup, "cleanup"),
                    CronTrigger.from_crontab(self.config.cleanup_cron),
                    id="background.cleanup",
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                )

        # Redis job store index cleanup (only if using Redis backend)
        if self.config.redis_cleanup_enabled and settings.JOB_STORE_BACKEND == "redis":
            self.scheduler.add_job(
                self._wrap_job(self._job_redis_cleanup, "redis_cleanup"),
                IntervalTrigger(seconds=max(60, int(self.config.redis_cleanup_interval_seconds))),
                id="background.redis_cleanup",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
            )

    def _wrap_job(self, func: Callable[[], Awaitable[Any]], job_name: str) -> Callable[[], Awaitable[None]]:
        async def runner() -> None:
            start = time.perf_counter()
            status = "ok"
            try:
                await func()
            except Exception as e:  # pragma: no cover
                status = "error"
                log.warning("background.job.error", job=job_name, err=str(e))
            finally:
                dur = time.perf_counter() - start
                # Record metrics if available
                with contextlib.suppress(Exception):
                    # Prefer a custom method if exposed by ServiceMetrics
                    if hasattr(self.metrics, "record_bg_job"):
                        self.metrics.record_bg_job(job_name, status=status, duration_seconds=dur)  # type: ignore[attr-defined]
                    elif hasattr(self.metrics, "observe_job"):
                        self.metrics.observe_job(job_name, status=status, duration_seconds=dur)  # type: ignore[attr-defined]
                log.debug("background.job.done", job=job_name, status=status, duration=f"{dur:.3f}s")

        return runner

    # ──────────────────────────────────────────────────────────────────
    # Jobs
    # ──────────────────────────────────────────────────────────────────
    async def _job_health(self) -> None:
        """Periodic health check sweep."""
        res = await self.health.check()
        if not res.ok:
            log.warning("background.health.unhealthy", error=res.error)
        else:
            log.info("background.health.ok")

    async def _job_backup(self) -> None:
        """Create a snapshot/backup via ArchiveService."""
        fn = None
        # Support multiple method names to avoid tight coupling.
        for candidate in ("backup", "run_backup", "create_backup"):
            if hasattr(self.archive, candidate):
                fn = getattr(self.archive, candidate)
                break
        if fn is None:  # pragma: no cover
            log.warning("background.backup.skipped", reason="no_method")
            return

        maybe_awaitable = fn()  # type: ignore[misc]
        if asyncio.iscoroutine(maybe_awaitable):
            await maybe_awaitable  # type: ignore[func-returns-value]
        log.info("background.backup.completed")

    async def _job_cleanup(self) -> None:
        """Run retention/cleanup via ArchiveService if available."""
        fn = None
        for candidate in ("cleanup", "run_cleanup", "prune"):
            if hasattr(self.archive, candidate):
                fn = getattr(self.archive, candidate)
                break
        if fn is None:  # pragma: no cover
            log.info("background.cleanup.skipped", reason="no_method")
            return

        maybe_awaitable = fn()  # type: ignore[misc]
        if asyncio.iscoroutine(maybe_awaitable):
            await maybe_awaitable  # type: ignore[func-returns-value]
        log.info("background.cleanup.completed")

    async def _job_redis_cleanup(self) -> None:
        """Clean orphaned ZSET members from Redis job store indexes."""
        # Only run if Redis backend is active
        if settings.JOB_STORE_BACKEND != "redis":
            return

        try:
            from db.redis_cache.async_client import get_async_redis
            from db.redis_cache.job_store import RedisJobStore
        except ImportError:  # pragma: no cover
            log.warning("background.redis_cleanup.skipped", reason="import_error")
            return

        store = RedisJobStore()
        redis = await get_async_redis()
        batch_size = self.config.redis_cleanup_batch_size
        total_removed = 0

        try:
            # 1. Clean global index
            removed = await store.cleanup_orphaned_index_members("jobs:all", batch_size=batch_size)
            total_removed += removed

            # 2. Clean status indexes
            for status in ["queued", "running", "finished", "failed", "cancelled"]:
                index_key = f"jobs:status:{status}"
                removed = await store.cleanup_orphaned_index_members(index_key, batch_size=batch_size)
                total_removed += removed

            # 3. Clean owner indexes (scan with cursor)
            cursor = 0
            owner_indexes_cleaned = 0

            while True:
                cursor, keys = await redis.scan(cursor=cursor, match="jobs:owner:*", count=100)
                for key_bytes in keys:
                    key = key_bytes.decode("utf-8") if isinstance(key_bytes, bytes) else key_bytes
                    removed = await store.cleanup_orphaned_index_members(key, batch_size=batch_size)
                    total_removed += removed
                    owner_indexes_cleaned += 1
                if cursor == 0:
                    break

            log.info(
                "background.redis_cleanup.completed",
                total_orphans_removed=total_removed,
                owner_indexes_cleaned=owner_indexes_cleaned,
            )

            # Record metric if available
            try:
                from src.jobs.metrics import record_index_cleanup

                record_index_cleanup(total_removed)
            except ImportError:
                pass

        except Exception as e:
            log.error("background.redis_cleanup.error", err=str(e))
            raise


# ─────────────────────────────────────────────────────────────────────
# FastAPI lifespan helper (optional)
# ─────────────────────────────────────────────────────────────────────
try:
    from contextlib import asynccontextmanager

    from fastapi import FastAPI
except Exception:  # pragma: no cover
    FastAPI = Any  # type: ignore
    asynccontextmanager = None  # type: ignore


def build_default_manager() -> BackgroundManager:
    """Create a BackgroundManager with default services and config."""
    return BackgroundManager(
        health=HealthService(),
        archive=ArchiveService(),
        metrics=ServiceMetrics(),
        config=BackgroundConfig(),
    )


if asynccontextmanager is not None:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Attach a default BackgroundManager to `app.state.bg`."""
        manager = build_default_manager()
        app.state.bg = manager
        await manager.start()
        try:
            yield
        finally:
            await manager.stop()


# Convenience named exports
__all__ = ["BackgroundConfig", "BackgroundManager", "build_default_manager", "lifespan"]
