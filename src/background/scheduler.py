"""
APScheduler-based background scheduler.

This module wires periodic jobs for:
- health checks
- backups (optional)
- cleanup (optional)

It is designed to be started/stopped from the FastAPI lifespan hooks
(see `src.background:init_background(app)` or `src.app`), but it can
also be used standalone.

Environment & settings are read from `src.config.settings`.
"""

from __future__ import annotations

import contextlib

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.config import settings

# Optional job functions — we add them conditionally if importable
with contextlib.suppress(Exception):
    from .health_checks import run_all_health_checks as _health_job  # type: ignore

with contextlib.suppress(Exception):
    from .provider_health import run_provider_health_check as _provider_health_job  # type: ignore

with contextlib.suppress(Exception):
    from .backups import run_backup as _backup_job  # type: ignore
with contextlib.suppress(Exception):
    from .backups import prune_backups as _prune_backups_job  # type: ignore

with contextlib.suppress(Exception):
    from .cleanup import run_cleanup as _cleanup_job  # type: ignore

log = structlog.get_logger(__name__)

_SCHEDULER: AsyncIOScheduler | None = None


# ─────────────────────────────────────────────────────────────────────
# Trigger helpers
# ─────────────────────────────────────────────────────────────────────
def _interval_trigger(seconds: int | None, fallback: int) -> IntervalTrigger:
    return IntervalTrigger(seconds=int(seconds or fallback))


def _cron_or_interval(
    cron_expr: str | None,
    interval_seconds: int | None,
    default_seconds: int,
):
    """
    Prefer cron if provided; otherwise use interval with sensible default.
    """
    if cron_expr and cron_expr.strip():
        return CronTrigger.from_crontab(cron_expr.strip())
    return _interval_trigger(interval_seconds, default_seconds)


# ─────────────────────────────────────────────────────────────────────
# Scheduler lifecycle
# ─────────────────────────────────────────────────────────────────────
def get_scheduler() -> AsyncIOScheduler:
    """
    Return a singleton AsyncIOScheduler with basic job defaults.
    """
    global _SCHEDULER
    if _SCHEDULER is None:
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": int(getattr(settings, "SCHEDULER_MISFIRE_GRACE_SECONDS", 60)),
        }
        _SCHEDULER = AsyncIOScheduler(job_defaults=job_defaults)
        log.info("scheduler.created", job_defaults=job_defaults)
    return _SCHEDULER


def _add_health_job(sched: AsyncIOScheduler) -> None:
    if "_health_job" not in globals():  # health job not importable
        log.warning("scheduler.health.unavailable")
        return

    cron = getattr(settings, "HEALTHCHECK_CRON", None)
    every = getattr(settings, "HEALTHCHECK_INTERVAL_SECONDS", 30)
    trigger = _cron_or_interval(cron, every, default_seconds=30)

    sched.add_job(
        func=_health_job,  # type: ignore[arg-type]
        trigger=trigger,
        id="health-checks",
        replace_existing=True,
        name="Periodic health checks",
    )
    log.info("scheduler.job.added", job="health-checks", trigger=str(trigger))


def _add_provider_health_job(sched: AsyncIOScheduler) -> None:
    if "_provider_health_job" not in globals():  # provider health job not importable
        log.warning("scheduler.provider_health.unavailable")
        return

    cron = getattr(settings, "PROVIDER_HEALTH_CHECK_CRON", None)
    every = getattr(settings, "PROVIDER_HEALTH_CHECK_INTERVAL", 60)
    trigger = _cron_or_interval(cron, every, default_seconds=60)

    sched.add_job(
        func=_provider_health_job,  # type: ignore[arg-type]
        trigger=trigger,
        id="provider-health-checks",
        replace_existing=True,
        name="Provider health checks",
    )
    log.info("scheduler.job.added", job="provider-health-checks", trigger=str(trigger))


def _add_backup_jobs(sched: AsyncIOScheduler) -> None:
    enabled = bool(getattr(settings, "BACKUP_ENABLED", False))
    if not enabled:
        log.info("scheduler.backup.disabled")
        return

    if "_backup_job" not in globals():
        log.warning("scheduler.backup.unavailable")
        return

    # Backup run
    cron = getattr(settings, "BACKUP_CRON", None)  # e.g. "0 2 * * *"
    every = getattr(settings, "BACKUP_INTERVAL_SECONDS", None)  # optional
    trigger = _cron_or_interval(cron, every, default_seconds=24 * 3600)

    sched.add_job(
        func=_backup_job,  # type: ignore[arg-type]
        trigger=trigger,
        id="backup-run",
        replace_existing=True,
        name="Database/filesystem backup",
    )
    log.info("scheduler.job.added", job="backup-run", trigger=str(trigger))

    # Optional prune job (usually shortly after backup)
    prune_enabled = bool(getattr(settings, "BACKUP_PRUNE_ENABLED", True))
    if prune_enabled and "_prune_backups_job" in globals():
        prune_cron = getattr(settings, "BACKUP_PRUNE_CRON", None)  # e.g. "30 2 * * *"
        prune_every = getattr(settings, "BACKUP_PRUNE_INTERVAL_SECONDS", None)
        prune_trigger = _cron_or_interval(prune_cron, prune_every, default_seconds=24 * 3600)

        sched.add_job(
            func=_prune_backups_job,  # type: ignore[arg-type]
            trigger=prune_trigger,
            id="backup-prune",
            replace_existing=True,
            name="Prune old backups",
        )
        log.info("scheduler.job.added", job="backup-prune", trigger=str(prune_trigger))


def _add_cleanup_job(sched: AsyncIOScheduler) -> None:
    enabled = bool(getattr(settings, "CLEANUP_ENABLED", True))
    if not enabled:
        log.info("scheduler.cleanup.disabled")
        return

    if "_cleanup_job" not in globals():
        log.warning("scheduler.cleanup.unavailable")
        return

    cron = getattr(settings, "CLEANUP_CRON", None)  # e.g. "0 3 * * *"
    every = getattr(settings, "CLEANUP_INTERVAL_SECONDS", None)
    trigger = _cron_or_interval(cron, every, default_seconds=6 * 3600)

    sched.add_job(
        func=_cleanup_job,  # type: ignore[arg-type]
        trigger=trigger,
        id="cleanup-run",
        replace_existing=True,
        name="Cleanup temp & old artifacts",
    )
    log.info("scheduler.job.added", job="cleanup-run", trigger=str(trigger))


def add_default_jobs(sched: AsyncIOScheduler | None = None) -> AsyncIOScheduler:
    """
    Register the built-in jobs based on configuration flags.
    """
    sched = sched or get_scheduler()
    _add_health_job(sched)
    _add_provider_health_job(sched)
    _add_backup_jobs(sched)
    _add_cleanup_job(sched)
    return sched


def start_scheduler() -> AsyncIOScheduler:
    """
    Create (if needed), register default jobs, and start the scheduler.
    """
    sched = add_default_jobs(get_scheduler())
    if not sched.running:
        sched.start()
        log.info("scheduler.started", jobs=[j.id for j in sched.get_jobs()])
    else:
        log.info("scheduler.already_running", jobs=[j.id for j in sched.get_jobs()])
    return sched


def shutdown_scheduler(wait: bool = False) -> None:
    """
    Stop the scheduler if running.
    """
    global _SCHEDULER
    if _SCHEDULER is None:
        return
    if _SCHEDULER.running:
        with contextlib.suppress(Exception):
            _SCHEDULER.shutdown(wait=wait)
            log.info("scheduler.stopped")
    _SCHEDULER = None


__all__ = [
    "add_default_jobs",
    "get_scheduler",
    "shutdown_scheduler",
    "start_scheduler",
]
