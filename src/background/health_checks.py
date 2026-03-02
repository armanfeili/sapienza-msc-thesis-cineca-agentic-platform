"""
Background health checks.

Runs periodic liveness/latency probes against core dependencies and the API
itself. Designed to be scheduled by `src.background.scheduler` (APS-scheduler),
but can also be invoked ad-hoc.

Checks implemented
- HTTP probe against the API `/health` (configurable list of URLs)
- Memgraph connectivity + trivial query
- Redis PING (optional)

Metrics (Prometheus)
- healthcheck_up{target}        → 1|0
- healthcheck_latency_seconds{target} (histogram)

Configuration (via `src.config.settings`)
- HEALTHCHECK_INTERVAL_SECONDS: int (default: 30)
- HEALTHCHECK_TIMEOUT_SECONDS:  float (default: 2.5)
- HEALTHCHECK_HTTP_URLS:        list[str] or comma-sep string
- HEALTHCHECK_ENABLE_REDIS:     bool (default: True if redis configured)
- HEALTHCHECK_ENABLE_MEMGRAPH:  bool (default: True)

Notes
- All checks are best-effort; failures are logged and surfaced via metrics.
- This module is pure “runner”; scheduling is in `background.scheduler`.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from src.config import settings

# Optional adapters (we degrade gracefully if missing)
with contextlib.suppress(Exception):
    from src.adapters.db_memgraph import MemgraphAdapter
with contextlib.suppress(Exception):
    from db.redis_cache.client import get_redis

# Optional metrics
HEALTH_GAUGE = None
HEALTH_HIST = None
with contextlib.suppress(Exception):
    from src.services.service_metrics import (
        HEALTHCHECK_LATENCY_SECONDS as HEALTH_HIST,  # Histogram("healthcheck_latency_seconds", ..., ["target"])
        HEALTHCHECK_UP as HEALTH_GAUGE,  # Gauge("healthcheck_up", ..., ["target"])
    )

log = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _csv_or_list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value).strip()
    if not s:
        return list(default)
    return [p.strip() for p in s.split(",") if p.strip()]


def _default_http_targets() -> list[str]:
    host = getattr(settings, "APP_HOST", "127.0.0.1")
    port = int(getattr(settings, "APP_PORT", 8000))
    return [f"http://{host}:{port}/health"]


def _timeout() -> float:
    try:
        return float(getattr(settings, "HEALTHCHECK_TIMEOUT_SECONDS", 2.5))
    except Exception:
        return 2.5


def _interval() -> int:
    try:
        return int(getattr(settings, "HEALTHCHECK_INTERVAL_SECONDS", 30))
    except Exception:
        return 30


def _bool_setting(name: str, default: bool) -> bool:
    try:
        return bool(getattr(settings, name, default))
    except Exception:
        return default


# ─────────────────────────────────────────────────────────────────────
# Core probes
# ─────────────────────────────────────────────────────────────────────
async def probe_http(url: str, timeout: float | None = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    ok = False
    status = None
    detail: str | None = None
    try:
        async with httpx.AsyncClient(timeout=timeout or _timeout(), follow_redirects=True) as client:
            res = await client.get(url)
            status = res.status_code
            ok = 200 <= res.status_code < 300
            if not ok:
                detail = f"unexpected_status:{res.status_code}"
    except Exception as e:
        detail = f"error:{type(e).__name__}:{e}"
    latency = time.perf_counter() - t0
    _emit_metrics(f"http:{url}", ok, latency)
    log.bind(target=url).info("health.http", up=ok, status=status, latency=f"{latency:.4f}", detail=detail)
    return {"target": url, "up": ok, "latency": latency, "status": status, "detail": detail}


async def probe_memgraph() -> dict[str, Any]:
    t0 = time.perf_counter()
    ok = False
    detail: str | None = None
    try:
        # Prefer adapter if available
        if "MemgraphAdapter" in globals():
            # MemgraphAdapter doesn't support context manager protocol
            mg = MemgraphAdapter()  # type: ignore[name-defined]
            try:
                # gqlalchemy Memgraph supports .execute or execute_and_fetch
                list(mg.execute_and_fetch("RETURN 1 AS ok LIMIT 1"))  # type: ignore[attr-defined]
                ok = True
            finally:
                # Clean up connection if possible
                with contextlib.suppress(Exception):
                    if hasattr(mg, "close"):
                        mg.close()  # type: ignore[attr-defined]
        else:
            # Fallback: import mgclient dynamically
            import mgclient  # type: ignore

            kwargs = {"host": settings.MG_HOST, "port": int(settings.MG_PORT)}
            if getattr(settings, "MG_USER", ""):
                kwargs["username"] = settings.MG_USER
            if getattr(settings, "MG_PASSWORD", ""):
                kwargs["password"] = settings.MG_PASSWORD
            conn = mgclient.connect(**kwargs)
            try:
                cur = conn.cursor()
                cur.execute("RETURN 1")
                list(cur.fetchall())
                ok = True
            finally:
                with contextlib.suppress(Exception):
                    conn.close()
    except Exception as e:
        detail = f"error:{type(e).__name__}:{e}"
    latency = time.perf_counter() - t0
    _emit_metrics("memgraph", ok, latency)
    log.info("health.memgraph", up=ok, latency=f"{latency:.4f}", detail=detail)
    return {"target": "memgraph", "up": ok, "latency": latency, "detail": detail}


async def probe_redis() -> dict[str, Any]:
    t0 = time.perf_counter()
    ok = False
    detail: str | None = None
    try:
        if "get_redis" in globals():
            r = get_redis()  # type: ignore[name-defined]
            # redis-py v5 returns bool for ping()
            ok = bool(r.ping())
        else:
            # Best-effort fallback
            import redis  # type: ignore

            url = getattr(settings, "REDIS_URL", None) or getattr(settings, "UPSTASH_REDIS_URL", None) or None
            if url:
                r = redis.from_url(url, decode_responses=True)
            else:
                host = getattr(settings, "REDIS_HOST", "redis")
                port = int(getattr(settings, "REDIS_PORT", 6379))
                db = int(getattr(settings, "REDIS_DB", 0))
                r = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            ok = bool(r.ping())
    except Exception as e:
        detail = f"error:{type(e).__name__}:{e}"
    latency = time.perf_counter() - t0
    _emit_metrics("redis", ok, latency)
    log.info("health.redis", up=ok, latency=f"{latency:.4f}", detail=detail)
    return {"target": "redis", "up": ok, "latency": latency, "detail": detail}


def _emit_metrics(label: str, up: bool, latency: float) -> None:
    # Prometheus client objects are optional; noop if not present
    try:
        if HEALTH_GAUGE is not None:
            HEALTH_GAUGE.labels(target=label).set(1 if up else 0)
        if HEALTH_HIST is not None:
            HEALTH_HIST.labels(target=label).observe(latency)
    except Exception:
        # Metrics failures should never crash the scheduler
        pass


# ─────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────
@dataclass
class HealthSummary:
    results: list[dict[str, Any]]

    @property
    def up_ratio(self) -> float:
        if not self.results:
            return 0.0
        ups = sum(1 for r in self.results if r.get("up"))
        return ups / len(self.results)

    def as_dict(self) -> dict[str, Any]:
        return {"results": self.results, "up_ratio": self.up_ratio}


async def run_all_health_checks() -> HealthSummary:
    """
    Executes all configured checks in parallel and returns a HealthSummary.
    """
    # HTTP targets
    http_urls = _csv_or_list(getattr(settings, "HEALTHCHECK_HTTP_URLS", None), _default_http_targets())

    want_memgraph = _bool_setting("HEALTHCHECK_ENABLE_MEMGRAPH", True)
    want_redis = _bool_setting(
        "HEALTHCHECK_ENABLE_REDIS",
        bool(getattr(settings, "REDIS_URL", None) or getattr(settings, "REDIS_HOST", None)),
    )

    tasks: list[asyncio.Task] = []

    for url in http_urls:
        tasks.append(asyncio.create_task(probe_http(url)))

    if want_memgraph:
        tasks.append(asyncio.create_task(probe_memgraph()))

    if want_redis:
        tasks.append(asyncio.create_task(probe_redis()))

    results: list[dict[str, Any]] = []
    for coro in asyncio.as_completed(tasks):
        with contextlib.suppress(Exception):
            res = await coro
            if isinstance(res, dict):
                results.append(res)

    summary = HealthSummary(results=results)
    log.info("health.run_all_done", summary=summary.as_dict())
    return summary


async def health_checks_loop(stop_event: asyncio.Event | None = None) -> None:
    """
    Simple loop suitable for background task runner without APScheduler.
    Use `background.scheduler` if you want proper cron-like scheduling.
    """
    interval = _interval()
    stop = stop_event or asyncio.Event()
    log.info("health.loop.start", interval_seconds=interval)

    try:
        while not stop.is_set():
            try:
                await run_all_health_checks()
            except Exception as e:  # pragma: no cover
                log.warning("health.loop.error", err=str(e))
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval)
    finally:
        log.info("health.loop.stop")


# ─────────────────────────────────────────────────────────────────────
# CLI for ad-hoc execution
# ─────────────────────────────────────────────────────────────────────
def _run_sync(coro):
    return asyncio.run(coro)


def main() -> None:  # pragma: no cover
    summary = _run_sync(run_all_health_checks())
    print(summary.as_dict())


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = [
    "HealthSummary",
    "health_checks_loop",
    "probe_http",
    "probe_memgraph",
    "probe_redis",
    "run_all_health_checks",
]
