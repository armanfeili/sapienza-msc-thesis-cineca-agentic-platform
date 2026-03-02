"""
Service package bootstrap for the Cineca Agentic Platform.

This module intentionally keeps imports *lazy* to avoid heavy startup cost
and circular dependencies between services. It also exposes a couple of
shared types used across service implementations.

Typical usage
-------------
from src.services import get_orchestrator

Orchestrator = get_orchestrator()
orch = Orchestrator(...)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Generic, TypeVar

__all__ = [
    "ServiceBase",
    # shared types
    "ServiceError",
    "ServiceResult",
    "ServiceStatus",
    "get_archive_service",
    "get_etl_service",
    "get_health_service",
    # typed getters (lazy imports)
    "get_orchestrator",
    "get_service_metrics",
    "get_session_service",
    "get_status_service",
    "load_service",
    # helpers
    "utc_now",
]

T = TypeVar("T")


# ──────────────────────────────────────────────────────────────────────────────
# Shared types
# ──────────────────────────────────────────────────────────────────────────────
class ServiceError(RuntimeError):
    """Generic service-level error."""


@dataclass(slots=True)
class ServiceResult(Generic[T]):
    ok: bool
    data: T | None = None
    error: str | None = None
    code: str | None = None

    @staticmethod
    def success(data: T | None = None) -> ServiceResult[T]:
        return ServiceResult(True, data=data, error=None, code=None)

    @staticmethod
    def failure(msg: str, code: str | None = None) -> ServiceResult[Any]:
        return ServiceResult(False, data=None, error=msg, code=code)


@dataclass(slots=True)
class ServiceStatus:
    name: str
    ok: bool
    detail: str = ""
    timestamp: datetime = datetime.now(UTC)


class ServiceBase:
    """
    Minimal base class for services used across the codebase.

    Concrete services may override lifecycle hooks and readiness checks.
    This lightweight implementation provides default async start/stop and
    simple liveness/readiness/check methods returning ServiceResult objects.
    """

    def __init__(self, name: str = "service") -> None:
        self.name = name
        self._started = False

    async def start(self) -> None:
        """Called during app startup."""
        self._started = True

    async def stop(self) -> None:
        """Called during app shutdown."""
        self._started = False

    async def liveness(self) -> ServiceResult[dict[str, Any]]:
        return ServiceResult.success({"status": "ok", "service": self.name})

    async def readiness(self) -> ServiceResult[dict[str, Any]]:
        # default: assume always ready unless overridden
        return ServiceResult.success({"status": "ok", "service": self.name})

    async def check(self) -> ServiceResult[dict[str, Any]]:
        return ServiceResult.success({"service": self.name, "started": self._started})


def utc_now() -> datetime:
    return datetime.now(UTC)


# ──────────────────────────────────────────────────────────────────────────────
# Lazy import helpers
# ──────────────────────────────────────────────────────────────────────────────
def load_service(module_name: str) -> Any:
    """
    Import a service module under `src.services.<module_name>` lazily.
    Raises ServiceError with a helpful message if import fails.
    """
    fqmn = f"{__name__}.{module_name}"
    try:
        return import_module(fqmn)
    except Exception as exc:  # pragma: no cover - thin wrapper
        raise ServiceError(f"Failed to load service module '{fqmn}': {exc}") from exc


# Typed getters (so callers don't pay import cost unless they opt-in)
def get_orchestrator() -> type[Any]:
    """
    Returns the Orchestrator class from src.services.orchestrator.
    """
    mod = load_service("orchestrator")
    return mod.Orchestrator


def get_session_service() -> type[Any]:
    """
    Returns the SessionService class from src.services.session.
    """
    mod = load_service("session")
    return mod.SessionService


def get_etl_service() -> type[Any]:
    """
    Returns the EtlService class from src.services.etl.
    """
    mod = load_service("etl")
    return mod.EtlService


def get_archive_service() -> type[Any]:
    """
    Returns the ArchiveService class from src.services.archive.
    """
    mod = load_service("archive")
    return mod.ArchiveService


def get_health_service() -> type[Any]:
    """
    Returns the HealthService class from src.services.health.
    """
    mod = load_service("health")
    return mod.HealthService


def get_service_metrics() -> type[Any]:
    """
    Returns the ServiceMetrics class from src.services.service_metrics.
    """
    mod = load_service("service_metrics")
    return mod.ServiceMetrics


def get_status_service() -> type[Any]:
    """
    Returns the StatusService class from src.services.status.
    """
    mod = load_service("status")
    return mod.StatusService
