"""
Background subsystem package entrypoint.

Exports a lightweight APScheduler-based manager that can:
  - run periodic health checks,
  - run scheduled backups,
  - run periodic cleanup,
while recording metrics and logging outcomes.

This mirrors the interface exposed by `src/background.py` so that
imports like `from src.background import lifespan` work whether
`src/background.py` or this package is used.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Optional

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


# Public API
__all__ = ["BackgroundConfig", "BackgroundManager", "build_default_manager", "lifespan"]
