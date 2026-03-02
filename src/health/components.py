"""
Component check infrastructure for health system.

Provides:
- ComponentCheck dataclass for probe results
- ComponentStatus enum for standardized states
- Component registry with all system components
- Probe functions for each component
"""

import asyncio
import os
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from src.config import settings
from src.health.config import get_health_config

log = structlog.get_logger(__name__)

# Global Memgraph connection cache for health checks
_memgraph_connection = None
_memgraph_last_checked = 0.0
_memgraph_connection_lock = asyncio.Lock()
_redis_consecutive_failures = 0


class ComponentStatus(str, Enum):
    """Standardized component health status."""

    OK = "ok"  # Healthy and functional
    DEGRADED = "degraded"  # Functional with warnings
    ERROR = "error"  # Not functional
    UNKNOWN = "unknown"  # Not configured/unreachable


@dataclass
class ComponentCheck:
    """Result of a component health probe."""

    ok: bool
    status: ComponentStatus
    latency_ms: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        result = {
            "ok": self.ok,
            "status": self.status.value,
        }
        if self.latency_ms is not None:
            result["latency_ms"] = self.latency_ms
        if self.details:
            result["details"] = self.details
        return result


# ──────────────────────────────────────────────────────────────────────────────
# Component Probes
# ──────────────────────────────────────────────────────────────────────────────


async def probe_app() -> ComponentCheck:
    """
    Probe app component (process health).

    This is a liveness check - if we can run this code, the app is up.
    """
    return ComponentCheck(ok=True, status=ComponentStatus.OK, latency_ms=0, details={"process": "running"})


async def probe_postgres() -> ComponentCheck:
    """
    Probe PostgreSQL database connectivity.

    Tests connection with SELECT 1 query and reports pool statistics.
    """
    config = get_health_config()
    timeout_ms = getattr(config, "postgres_timeout_ms", config.db_timeout_ms)
    max_attempts = max(1, getattr(config, "postgres_retries", 2))
    backoff_ms = max(0, getattr(config, "postgres_retry_backoff_ms", 250))
    total_start = time.perf_counter()
    last_error: str | None = None

    from db.postgres_control.database import check_db_health

    for attempt in range(1, max_attempts + 1):
        attempt_start = time.perf_counter()
        try:
            # Apply timeout
            is_healthy, error_msg = await asyncio.wait_for(
                asyncio.to_thread(check_db_health), timeout=timeout_ms / 1000.0
            )

            latency_ms = int((time.perf_counter() - total_start) * 1000)

            if is_healthy:
                if attempt > 1:
                    log.info(
                        "health.postgres.recovered_after_retry",
                        attempts=attempt,
                        latency_ms=latency_ms,
                    )
                return ComponentCheck(
                    ok=True,
                    status=ComponentStatus.OK,
                    latency_ms=latency_ms,
                    details={"database": "postgresql", "attempts": attempt},
                )

            last_error = error_msg or "health check failed"
            log.warning(
                "health.postgres.failed",
                error=last_error,
                latency_ms=latency_ms,
                attempt=attempt,
            )
        except (asyncio.TimeoutError, TimeoutError):
            last_error = f"timeout after {timeout_ms}ms"
            latency_ms = int((time.perf_counter() - attempt_start) * 1000)
            log_func = log.info if settings.APP_ENV == "dev" and attempt == 1 else log.warning
            log_func(
                "health.postgres.timeout",
                timeout_ms=timeout_ms,
                attempt=attempt,
                max_attempts=max_attempts,
            )
        except Exception as e:
            last_error = str(e)
            latency_ms = int((time.perf_counter() - attempt_start) * 1000)
            log.warning("health.postgres.failed", error=str(e), latency_ms=latency_ms, attempt=attempt)

        if attempt < max_attempts and backoff_ms > 0:
            await asyncio.sleep(backoff_ms / 1000.0)

    total_latency_ms = int((time.perf_counter() - total_start) * 1000)
    return ComponentCheck(
        ok=False,
        status=ComponentStatus.ERROR,
        latency_ms=total_latency_ms,
        details={"error": last_error or "health check failed", "attempts": max_attempts},
    )


async def probe_redis() -> ComponentCheck:
    """
    Probe Redis connectivity and queue health.

    Tests PING command and reports queue depths for all job types.
    """
    config = get_health_config()
    start = time.perf_counter()
    timeout_ms = max(config.cache_timeout_ms, 2000)
    timeout_seconds = timeout_ms / 1000.0
    global _redis_consecutive_failures

    try:
        from db.redis_cache.async_client import get_async_redis

        client = await get_async_redis()

        # PING with timeout using shared async client
        pong = await asyncio.wait_for(client.ping(), timeout=timeout_seconds)

        latency_ms = int((time.perf_counter() - start) * 1000)

        if not pong:
            return ComponentCheck(
                ok=False, status=ComponentStatus.ERROR, latency_ms=latency_ms, details={"error": "PING returned falsy"}
            )

        # Get queue depths
        queues = {}
        try:
            allowed_types_str = getattr(settings, "ALLOWED_JOB_TYPES", "demo,test,long-running")
            allowed_types = [t.strip() for t in allowed_types_str.split(",")]

            for job_type in allowed_types:
                queue_key = f"jobs:queue:{job_type}"
                length = await asyncio.wait_for(client.llen(queue_key), timeout=timeout_seconds)
                queues[job_type] = length
        except Exception as e:
            log.warning("health.redis.queue_stats_failed", error=str(e))
        _redis_consecutive_failures = 0
        return ComponentCheck(
            ok=True, status=ComponentStatus.OK, latency_ms=latency_ms, details={"queues": queues} if queues else {}
        )

    except (asyncio.TimeoutError, TimeoutError):
        latency_ms = timeout_ms
        _redis_consecutive_failures += 1
        log_func = log.info if _redis_consecutive_failures == 1 else log.warning
        log_func("health.redis.timeout", timeout_ms=latency_ms, consecutive=_redis_consecutive_failures)
        status = ComponentStatus.DEGRADED if _redis_consecutive_failures == 1 else ComponentStatus.ERROR
        return ComponentCheck(
            ok=status != ComponentStatus.ERROR,
            status=status,
            latency_ms=latency_ms,
            details={"error": f"timeout after {latency_ms}ms", "consecutive_failures": _redis_consecutive_failures},
        )

    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        _redis_consecutive_failures += 1
        log_func = log.info if _redis_consecutive_failures == 1 else log.warning
        log_func("health.redis.failed", error=str(e), latency_ms=latency_ms, consecutive=_redis_consecutive_failures)

        # Apply fallback policy
        if config.allow_redis_health_fallback:
            return ComponentCheck(
                ok=True,  # Allow as degraded
                status=ComponentStatus.DEGRADED if _redis_consecutive_failures == 1 else ComponentStatus.ERROR,
                latency_ms=latency_ms,
                details={
                    "error": str(e),
                    "reason": "adapter-missing",
                    "consecutive_failures": _redis_consecutive_failures,
                },
            )

        return ComponentCheck(ok=False, status=ComponentStatus.ERROR, latency_ms=latency_ms, details={"error": str(e)})


async def probe_memgraph() -> ComponentCheck:
    """
    Probe Memgraph service.

    Note: Memgraph is fast (~6-60ms) in isolation, but may timeout during
    concurrent health checks due to asyncio thread pool contention.
    Marked as informational-only to not fail readiness checks.
    """
    get_health_config()
    start = time.perf_counter()

    try:
        from gqlalchemy import Memgraph

        # Create a fresh connection each time (simpler than pooling)
        mg = Memgraph(host="memgraph", port=7687)

        # Execute a simple test query with generous timeout for thread pool
        result = await asyncio.wait_for(
            asyncio.to_thread(lambda: list(mg.execute_and_fetch("RETURN 1 AS ok LIMIT 1"))),
            timeout=2.0,  # 2000ms to handle thread pool contention during concurrent checks
        )

        latency_ms = int((time.perf_counter() - start) * 1000)

        if result and result[0].get("ok") == 1:
            return ComponentCheck(
                ok=True, status=ComponentStatus.OK, latency_ms=latency_ms, details={"host": "memgraph:7687"}
            )

        # Query didn't return expected result
        return ComponentCheck(
            ok=True,  # Informational only
            status=ComponentStatus.DEGRADED,
            latency_ms=latency_ms,
            details={"error": "unexpected result", "note": "informational-only"},
        )

    except TimeoutError:
        latency_ms = 2000
        return ComponentCheck(
            ok=True,  # Informational only - doesn't fail readiness
            status=ComponentStatus.DEGRADED,
            latency_ms=latency_ms,
            details={"error": "timeout after 2000ms", "note": "informational-only"},
        )


async def probe_providers() -> ComponentCheck:
    """
    Probe provider registry health.

    Checks PostgreSQL provider registry accessibility and reports provider stats.
    """
    config = get_health_config()
    start = time.perf_counter()

    try:
        from db.postgres_control.repositories import provider_repo as pg_repo

        # Fetch providers with timeout
        providers = await asyncio.wait_for(
            asyncio.to_thread(pg_repo.list_providers, tenant_id=None), timeout=config.db_timeout_ms / 1000.0
        )

        latency_ms = int((time.perf_counter() - start) * 1000)

        # Aggregate statistics
        total = len(providers)
        by_type = {}
        healthy = 0
        unhealthy = 0
        provider_details = []  # List of individual provider details

        for provider in providers:
            ptype = provider.get("type", "unknown")
            by_type[ptype] = by_type.get(ptype, 0) + 1

            # Check provider health
            provider_healthy = False
            last_check = None
            try:
                health = pg_repo.get_provider_health(provider.get("name"))
                # Check "reachable" field, not "ok" (models_repo returns {"reachable": bool, "status": int})
                if health and health.get("reachable"):
                    healthy += 1
                    provider_healthy = True
                else:
                    unhealthy += 1
                
                # Extract last check timestamp if available
                last_check = health.get("last_check") if health else None
            except Exception:
                unhealthy += 1

            # Build individual provider detail
            model_name = provider.get("model")
            if model_name is None or model_name == "":
                model_name = "no default model loaded"
            
            provider_detail = {
                "name": provider.get("name", "unknown"),
                "type": ptype,
                "status": "healthy" if provider_healthy else "unhealthy",
                "model": model_name,
            }
            
            # Add last_check timestamp if available
            if last_check:
                provider_detail["last_check"] = last_check
            
            provider_details.append(provider_detail)

        # Degraded if some providers unhealthy, but registry accessible
        status = ComponentStatus.OK if unhealthy == 0 else ComponentStatus.DEGRADED

        return ComponentCheck(
            ok=True,  # Registry accessible
            status=status,
            latency_ms=latency_ms,
            details={
                "total": total,
                "healthy": healthy,
                "unhealthy": unhealthy,
                "by_type": by_type,
                "providers": provider_details,  # Add individual provider details
            },
        )

    except TimeoutError:
        latency_ms = config.db_timeout_ms
        log.warning("health.providers.timeout", timeout_ms=latency_ms)
        return ComponentCheck(
            ok=False,
            status=ComponentStatus.DEGRADED,  # Non-fatal
            latency_ms=latency_ms,
            details={"error": f"timeout after {latency_ms}ms"},
        )

    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        log.warning("health.providers.failed", error=str(e), latency_ms=latency_ms)
        return ComponentCheck(
            ok=False, status=ComponentStatus.DEGRADED, latency_ms=latency_ms, details={"error": str(e)}  # Non-fatal
        )


async def probe_workers() -> ComponentCheck:
    """
    Probe background workers health.

    Checks job queue depths and reports if backlog exceeds threshold.
    """
    config = get_health_config()
    start = time.perf_counter()

    try:
        import redis

        r = redis.Redis.from_url(settings.REDIS_URL)

        # Get queue depths
        allowed_types_str = getattr(settings, "ALLOWED_JOB_TYPES", "demo,test,long-running")
        allowed_types = [t.strip() for t in allowed_types_str.split(",")]

        total_depth = 0
        queue_depths = {}

        for job_type in allowed_types:
            queue_key = f"jobs:queue:{job_type}"
            length = await asyncio.wait_for(
                asyncio.to_thread(r.llen, queue_key), timeout=config.cache_timeout_ms / 1000.0
            )
            queue_depths[job_type] = length
            total_depth += length

        latency_ms = int((time.perf_counter() - start) * 1000)

        # Degraded if queue depth exceeds threshold
        status = ComponentStatus.OK if total_depth < config.worker_queue_max else ComponentStatus.DEGRADED

        return ComponentCheck(
            ok=True, status=status, latency_ms=latency_ms, details={"queue_depth": total_depth, "queues": queue_depths}
        )

    except TimeoutError:
        latency_ms = config.cache_timeout_ms
        log.warning("health.workers.timeout", timeout_ms=latency_ms)
        return ComponentCheck(
            ok=True,  # Non-fatal
            status=ComponentStatus.DEGRADED,
            latency_ms=latency_ms,
            details={"error": f"timeout after {latency_ms}ms"},
        )

    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        log.warning("health.workers.failed", error=str(e), latency_ms=latency_ms)
        return ComponentCheck(
            ok=True, status=ComponentStatus.DEGRADED, latency_ms=latency_ms, details={"error": str(e)}  # Non-fatal
        )


async def probe_ollama() -> ComponentCheck:
    """
    Probe Ollama service (informational only).

    Checks Ollama API availability. Failures are reported but don't affect readiness.
    """
    config = get_health_config()
    start = time.perf_counter()

    try:
        import httpx

        # Ollama API endpoint
        url = os.getenv("OLLAMA_URL", "http://ollama:11434")

        async with httpx.AsyncClient(timeout=config.timeout_ms / 1000.0) as client:
            # Use /api/tags endpoint which lists models
            response = await client.get(f"{url}/api/tags")

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code == 200:
            data = response.json()
            model_count = len(data.get("models", []))
            return ComponentCheck(
                ok=True, status=ComponentStatus.OK, latency_ms=latency_ms, details={"url": url, "models": model_count}
            )

        return ComponentCheck(
            ok=True,  # Informational only - don't fail health check
            status=ComponentStatus.DEGRADED,
            latency_ms=latency_ms,
            details={"status_code": response.status_code, "url": url},
        )

    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ComponentCheck(
            ok=True,  # Informational only - don't fail health check
            status=ComponentStatus.UNKNOWN,
            latency_ms=latency_ms,
            details={"error": str(e), "note": "informational-only"},
        )


async def probe_prometheus() -> ComponentCheck:
    """
    Probe Prometheus service (informational only).

    Prometheus is optional - failures are reported but don't affect readiness.
    """
    config = get_health_config()
    start = time.perf_counter()

    try:
        import httpx

        # Prometheus health endpoint
        url = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")

        async with httpx.AsyncClient(timeout=config.timeout_ms / 1000.0) as client:
            response = await client.get(f"{url}/-/healthy")

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code == 200:
            return ComponentCheck(ok=True, status=ComponentStatus.OK, latency_ms=latency_ms, details={"url": url})

        return ComponentCheck(
            ok=True,  # Informational only
            status=ComponentStatus.DEGRADED,
            latency_ms=latency_ms,
            details={"status_code": response.status_code, "url": url},
        )

    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ComponentCheck(
            ok=True,  # Informational only
            status=ComponentStatus.UNKNOWN,
            latency_ms=latency_ms,
            details={"error": str(e), "note": "informational-only"},
        )


async def probe_grafana() -> ComponentCheck:
    """
    Probe Grafana service (informational only).

    Grafana is optional - failures are reported but don't affect readiness.
    """
    config = get_health_config()
    start = time.perf_counter()

    try:
        import httpx

        # Grafana health endpoint
        url = os.getenv("GRAFANA_URL", "http://grafana:3000")

        async with httpx.AsyncClient(timeout=config.timeout_ms / 1000.0) as client:
            response = await client.get(f"{url}/api/health")

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code == 200:
            data = response.json()
            return ComponentCheck(
                ok=True,
                status=ComponentStatus.OK,
                latency_ms=latency_ms,
                details={"url": url, "database": data.get("database", "unknown")},
            )

        return ComponentCheck(
            ok=True,  # Informational only
            status=ComponentStatus.DEGRADED,
            latency_ms=latency_ms,
            details={"status_code": response.status_code, "url": url},
        )

    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ComponentCheck(
            ok=True,  # Informational only
            status=ComponentStatus.UNKNOWN,
            latency_ms=latency_ms,
            details={"error": str(e), "note": "informational-only"},
        )


# ──────────────────────────────────────────────────────────────────────────────
# Component Registry
# ──────────────────────────────────────────────────────────────────────────────


class ComponentRegistry:
    """Registry of all system components with their probe functions."""

    def __init__(self):
        self._components: dict[str, Callable[[], Coroutine[Any, Any, ComponentCheck]]] = {
            "app": probe_app,
            "postgres": probe_postgres,
            "redis": probe_redis,
            "memgraph": probe_memgraph,
            "providers": probe_providers,
            "workers": probe_workers,
            "ollama": probe_ollama,
            "prometheus": probe_prometheus,
            "grafana": probe_grafana,
        }

    def get_component_names(self) -> list[str]:
        """Get list of all component names."""
        return list(self._components.keys())

    async def probe(self, name: str) -> ComponentCheck:
        """
        Probe a single component by name.

        Returns ComponentCheck with error status if component not found.
        """
        probe_fn = self._components.get(name)
        if not probe_fn:
            return ComponentCheck(
                ok=False, status=ComponentStatus.ERROR, details={"error": f"unknown component: {name}"}
            )

        try:
            return await probe_fn()
        except Exception as e:
            log.error("health.probe.failed", component=name, error=str(e))
            return ComponentCheck(ok=False, status=ComponentStatus.ERROR, details={"error": f"probe failed: {e!s}"})

    async def probe_all(self) -> dict[str, ComponentCheck]:
        """
        Probe all components in parallel.

        Returns dictionary mapping component names to their check results.
        """
        tasks = {name: self.probe(name) for name in self._components}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        checks = {}
        for name, result in zip(tasks.keys(), results, strict=False):
            if isinstance(result, Exception):
                log.error("health.probe.exception", component=name, error=str(result))
                checks[name] = ComponentCheck(
                    ok=False, status=ComponentStatus.ERROR, details={"error": f"probe exception: {result!s}"}
                )
            else:
                checks[name] = result

        return checks


# Global registry instance
_registry: ComponentRegistry | None = None


def get_component_registry() -> ComponentRegistry:
    """Get or create the global component registry."""
    global _registry
    if _registry is None:
        _registry = ComponentRegistry()
    return _registry
