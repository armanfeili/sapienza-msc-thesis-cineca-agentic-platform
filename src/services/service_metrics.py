"""
Service metrics: Prometheus counters/gauges/histograms with simple helpers.

This module provides a small metrics service used across the app & background
workers. It exposes convenience methods to mark dependency health, time jobs,
and count requests. It relies on the default Prometheus registry; the FastAPI
app should mount `/metrics` (see src/app.py) to expose them.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

import structlog
from prometheus_client import Counter, Gauge, Histogram

from src.services import ServiceBase, ServiceResult, utc_now

try:  # Settings are optional for this module
    from src.config import settings  # type: ignore
except Exception:  # pragma: no cover
    settings = None  # type: ignore[assignment]

log = structlog.get_logger(__name__)


def _status_class(code: int | str) -> str:
    """Return '2xx', '4xx', etc."""
    try:
        c = int(code)
        return f"{c // 100}xx"
    except Exception:  # pragma: no cover
        return "unknown"


class ServiceMetrics(ServiceBase):
    """
    Centralized metrics service.

    Metrics (all prefixed with `cineca_`):
      - api_requests_total{route,method,status_class}
      - api_request_duration_seconds{route,method}
      - service_events_total{service,event}
      - job_duration_seconds{job,status}
      - dependency_up{name} (1/0)
      - dependency_latency_seconds{name}
      - service_up{service} (1/0)
      - build_info{version} (constant 1.0)
    """

    def __init__(self) -> None:
        super().__init__(name="metrics-service")
        # API request metrics
        self.api_requests = Counter(
            "cineca_api_requests_total",
            "Count of API requests by route/method/status.",
            labelnames=("route", "method", "status_class"),
        )
        self.api_request_duration = Histogram(
            "cineca_api_request_duration_seconds",
            "Duration of API requests in seconds.",
            labelnames=("route", "method"),
        )

        # Generic service metrics
        self.service_events = Counter(
            "cineca_service_events_total",
            "Service events (custom, low-card).",
            labelnames=("service", "event"),
        )
        self.job_duration = Histogram(
            "cineca_job_duration_seconds",
            "Duration of background jobs in seconds.",
            labelnames=("job", "status"),
        )

        # Dependency health
        self.dependency_up = Gauge(
            "cineca_dependency_up",
            "Dependency health: 1=up, 0=down",
            labelnames=("name",),
        )
        self.dependency_latency = Gauge(
            "cineca_dependency_latency_seconds",
            "Latest observed latency for dependency probes in seconds.",
            labelnames=("name",),
        )

        # Service/process state
        self.service_up = Gauge(
            "cineca_service_up",
            "Service up flag.",
            labelnames=("service",),
        )
        self.build_info = Gauge(
            "cineca_build_info",
            "Build/version info; constant 1 with version label.",
            labelnames=("version",),
        )

        self._started_at: float | None = None

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────
    async def start(self) -> None:
        await super().start()
        self._started_at = time.time()
        ver = getattr(settings, "APP_VERSION", "0.0.0")
        # set to 1 once (idempotent)
        self.build_info.labels(version=str(ver)).set(1.0)
        self.service_up.labels(self.name).set(1.0)
        log.info("metrics.started", version=ver)

    async def stop(self) -> None:
        self.service_up.labels(self.name).set(0.0)
        await super().stop()
        log.info("metrics.stopped")

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────
    def mark_event(self, service: str, event: str, inc: int = 1) -> None:
        """Increment a custom service event counter."""
        self.service_events.labels(service=service, event=event).inc(inc)

    def mark_dependency(self, name: str, up: bool, latency_seconds: float | None = None) -> None:
        """Set dependency gauge and (optionally) record latest latency."""
        self.dependency_up.labels(name=name).set(1.0 if up else 0.0)
        if latency_seconds is not None:
            self.dependency_latency.labels(name=name).set(float(latency_seconds))

    def record_request(self, route: str, method: str, status_code: int, duration_seconds: float | None = None) -> None:
        """Record an API request; optionally observe latency."""
        self.api_requests.labels(route=route, method=method.upper(), status_class=_status_class(status_code)).inc()
        if duration_seconds is not None:
            self.api_request_duration.labels(route=route, method=method.upper()).observe(float(duration_seconds))

    def observe_job(self, job: str, status: str, duration_seconds: float) -> None:
        """Observe a background job run."""
        self.job_duration.labels(job=job, status=status).observe(float(duration_seconds))

    def update_from_health(self, health_payload: dict[str, Any]) -> None:
        """
        Convenience to update dependency gauges from HealthService payload:
          { checks: { redis: {status: 'ok', latency_ms: 3}, ... } }
        """
        checks = (health_payload or {}).get("checks", {})
        for dep_name, chk in checks.items():
            st = chk.get("status", "unknown")
            up = st == "ok"
            latency_ms = chk.get("latency_ms")
            latency_s = (latency_ms / 1000.0) if isinstance(latency_ms, (int, float)) else None
            self.mark_dependency(dep_name, up=up, latency_seconds=latency_s)

    def snapshot(self) -> dict[str, Any]:
        """Return a small JSON-able snapshot for diagnostic endpoints."""
        return {
            "service": self.name,
            "time": utc_now().isoformat(),
            "uptime_s": (time.time() - self._started_at) if self._started_at else None,
        }

    # ──────────────────────────────────────────────────────────────────
    # Timers / context managers
    # ──────────────────────────────────────────────────────────────────
    @contextlib.contextmanager
    def time_request(self, route: str, method: str):
        """
        Context manager: time an API request.

        Usage:
            with metrics.time_request(route="/health", method="GET") as done:
                # ... handler work
                done(status_code=200)
        """
        t0 = time.perf_counter()
        status_holder = {"status": None}

        def _done(*, status_code: int) -> None:
            status_holder["status"] = status_code

        try:
            yield _done
        finally:
            dur = time.perf_counter() - t0
            status = status_holder["status"] if status_holder["status"] is not None else 0
            self.record_request(route=route, method=method, status_code=int(status), duration_seconds=dur)

    @contextlib.contextmanager
    def time_job(self, job: str, *, status_on_error: str = "error", status_on_success: str = "ok"):
        """
        Context manager: time a background job and record status/duration.
        """
        t0 = time.perf_counter()
        status = status_on_success
        try:
            yield
        except Exception:
            status = status_on_error
            raise
        finally:
            dur = time.perf_counter() - t0
            self.observe_job(job=job, status=status, duration_seconds=dur)

    # ──────────────────────────────────────────────────────────────────
    # ServiceBase API (lightweight)
    # ──────────────────────────────────────────────────────────────────
    async def liveness(self) -> ServiceResult[dict[str, Any]]:
        return ServiceResult.success({"status": "ok", "service": self.name})

    async def readiness(self) -> ServiceResult[dict[str, Any]]:
        # Metrics service has no critical external deps on its own
        return ServiceResult.success({"status": "ok", "service": self.name})

    async def check(self) -> ServiceResult[dict[str, Any]]:
        return ServiceResult.success(self.snapshot())


# Global instance (import and use)
metrics = ServiceMetrics()

__all__ = ["ServiceMetrics", "metrics"]
