"""
Status service: aggregates app/runtime/dep status into a single payload.

This is intended to back a `/status` endpoint and internal diagnostics.
It composes health checks, build info, and lightweight metrics snapshots.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.services import ServiceBase, ServiceResult, utc_now

try:
    from src.config import settings  # type: ignore
except Exception:  # pragma: no cover
    settings = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from src.observability.metrics import ServiceMetrics
    from src.services.health import HealthService

log = structlog.get_logger(__name__)


class StatusService(ServiceBase):
    """
    Aggregate status across subsystems.

    Combines:
      - App/build metadata (name, version, environment)
      - Health checks (from HealthService)
      - Metrics snapshot (from ServiceMetrics)
    """

    def __init__(
        self,
        *,
        health: HealthService | None = None,
        metrics: ServiceMetrics | None = None,
        extra_info: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name="status-service")
        self.health = health
        self.metrics = metrics
        self.extra_info = extra_info or {}

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────
    async def start(self) -> None:
        await super().start()
        log.info("status.started")

    async def stop(self) -> None:
        await super().stop()
        log.info("status.stopped")

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────
    async def get_status(self) -> ServiceResult[dict[str, Any]]:
        """Return a consolidated JSON-able status payload."""
        app_name = getattr(settings, "APP_NAME", "Cineca Agentic Platform")
        version = getattr(settings, "APP_VERSION", "0.0.0")
        env = getattr(settings, "APP_ENV", getattr(settings, "ENV", "dev"))

        # Health details (optional)
        health_payload: dict[str, Any] | None = None
        health_ok: bool | None = None
        if self.health:
            try:
                hres = await self.health.readiness()
                health_ok = hres.ok
                health_payload = hres.data if hres.ok else {"error": hres.error}
            except Exception as e:  # pragma: no cover
                log.warning("status.health_error", err=str(e))
                health_ok = False
                health_payload = {"error": str(e)}

        # Metrics snapshot (optional)
        metrics_snapshot: dict[str, Any] | None = None
        if self.metrics:
            try:
                metrics_snapshot = self.metrics.snapshot()
            except Exception as e:  # pragma: no cover
                log.warning("status.metrics_error", err=str(e))
                metrics_snapshot = {"error": str(e)}

        data: dict[str, Any] = {
            "time": utc_now().isoformat(),
            "app": {
                "name": app_name,
                "version": str(version),
                "environment": env,
            },
            "services": {
                "health": {"available": self.health is not None, "ok": health_ok},
                "metrics": {"available": self.metrics is not None},
            },
            "health": health_payload,
            "metrics": metrics_snapshot,
            "extras": self.extra_info,
        }
        return ServiceResult.success(data)

    # ──────────────────────────────────────────────────────────────────
    # ServiceBase contract
    # ──────────────────────────────────────────────────────────────────
    async def liveness(self) -> ServiceResult[dict[str, Any]]:
        # Liveness: the service event loop is responsive
        return ServiceResult.success({"status": "ok", "service": self.name})

    async def readiness(self) -> ServiceResult[dict[str, Any]]:
        # Readiness: depend on health checks if available
        if not self.health:
            return ServiceResult.success({"status": "unknown", "note": "no-health-service"})
        h = await self.health.readiness()
        return ServiceResult.success({"status": "ok"}) if h.ok else ServiceResult.failure(h.error or "unready")

    async def check(self) -> ServiceResult[dict[str, Any]]:
        # Full status payload
        return await self.get_status()


__all__ = ["StatusService"]
