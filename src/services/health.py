"""
Health service: liveness, readiness and dependency probes (Memgraph, Redis).

This module exposes a small service used by the health router to report:
- liveness: the service loop is running
- readiness: critical dependencies can be reached (Memgraph, Redis)
- detailed checks: individual probe latencies and metadata
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any

import structlog

from src.services import ServiceBase, ServiceResult, utc_now

_health_cache = {}
_health_cache_ttl = 5  # seconds


def _cache_result(key, value):
    # key may be any hashable (we store composite keys in tests)
    _health_cache[key] = (value, time.time())


# Add helper to clear internal health cache (used by tests to avoid inter-test interaction)
def _clear_health_cache() -> None:
    _health_cache.clear()


# Update _get_cached to be robust
def _get_cached(key):
    item = _health_cache.get(key)
    if not item:
        return None
    val, ts = item
    if time.time() - ts < _health_cache_ttl:
        return val
    return None


try:
    from src.config import settings  # type: ignore
except Exception:  # pragma: no cover - import order safety
    settings = None  # type: ignore[assignment,misc]

# Optional adapters — keep imports inside try/except to avoid hard coupling
# Do not import adapters at module import time. Tests/fixtures monkeypatch
# the adapter modules (e.g. src.adapters.redis, src.adapters.db_memgraph).
get_redis_pool = None  # type: ignore[assignment]
# Module-level symbol that tests can monkeypatch directly.
# Do not eagerly import from adapters here to avoid locking a stale value;
# we'll resolve from the adapters module at call time when needed.
MemgraphAdapter = None  # type: ignore[assignment]

log = structlog.get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Probe:
    name: str
    critical: bool = True  # if True, failed probe degrades readiness


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────
class HealthService(ServiceBase):
    """
    Liveness and readiness checks with dependency probes.
    """

    def __init__(self) -> None:
        super().__init__(name="health-service")

        # Initialize clients lazily to avoid startup failures when not needed.
        self._redis_pool = None
        self._memgraph: Any | None = None

        # Known probes
        self.probes = [
            Probe("redis", critical=True),
            Probe("memgraph", critical=True),
        ]

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────
    async def liveness(self) -> ServiceResult[dict[str, Any]]:
        """
        Liveness is 'ok' if this coroutine can run.
        """
        data = {
            "status": "ok",
            "service": self.name,
            "time": utc_now().isoformat(),
        }
        return ServiceResult.success(data)

    async def readiness(self) -> ServiceResult[dict[str, Any]]:
        """
        Readiness summarizes the critical probes. If any critical probe fails,
        the overall status is 'degraded'.
        """
        # Use a composite cache key so tests that monkeypatch adapters/settings
        # will not accidentally reuse a stale cached readiness result.
        cache_key = (
            "readiness",
            id(settings),
            id(get_redis_pool),
            id(MemgraphAdapter),
        )
        cached = _get_cached(cache_key)
        if cached:
            return cached
        detail_res = await self.check()
        if not detail_res.ok:
            _cache_result(cache_key, detail_res)
            return detail_res

        checks = detail_res.data.get("checks", {}) if detail_res.data else {}
        degraded = any(
            (chk.get("status") != "ok") for probe_name, chk in checks.items() if self._is_critical(probe_name)
        )

        overall = "ok" if not degraded else "degraded"
        response = ServiceResult.success(
            {
                "status": overall,
                "time": utc_now().isoformat(),
                "version": getattr(settings, "APP_VERSION", "0.0.0"),
                "checks": checks,
            }
        )
        _cache_result(cache_key, response)
        return response

    async def check(self) -> ServiceResult[dict[str, Any]]:
        """
        Run all probes and return structured results including latencies.
        """
        start = time.perf_counter()
        results: dict[str, dict[str, Any]] = {}

        # Run probes (independently, but simple sequential execution is fine here)
        results["redis"] = await self._probe_redis()
        results["memgraph"] = await self._probe_memgraph()

        duration_ms = int((time.perf_counter() - start) * 1000)

        data = {
            "status": "ok",
            "time": utc_now().isoformat(),
            "took_ms": duration_ms,
            "checks": results,
        }
        return ServiceResult.success(data)

    # ──────────────────────────────────────────────────────────────────
    # Probes
    # ──────────────────────────────────────────────────────────────────
    async def _probe_redis(self) -> dict[str, Any]:
        # Prefer a monkeypatched `get_redis_pool` symbol if available; otherwise import dynamically
        pool_factory = None
        adapter_found = False
        if get_redis_pool:
            pool_factory = get_redis_pool
            adapter_found = True
        else:
            try:
                # Primary: modern adapter exposing async/sync pool factory
                from db.redis_cache.client import get_redis_pool as _get_pool  # type: ignore

                pool_factory = _get_pool
                adapter_found = True
            except Exception:
                # Fallback: only try sync `get_redis` when settings indicate REDIS_URL
                if not settings or not getattr(settings, "REDIS_URL", ""):
                    log.warning("health.redis.adapter_missing")
                    # Treat adapter missing as unknown but not fatal when fallback is allowed
                    allow_fallback = getattr(settings, "HEALTH_ALLOW_REDIS_HEALTH_FALLBACK", True) if settings else True
                    return {"status": "unknown", "reason": "adapter-missing", "ok": allow_fallback}
                try:
                    from db.redis_cache.client import get_redis as _get_redis  # type: ignore

                    def _get_pool(url: str | None = None):  # shim: ignore url, return client
                        return _get_redis()

                    pool_factory = _get_pool
                    adapter_found = False
                except Exception:
                    log.warning("health.redis.adapter_missing")
                    return {"status": "unknown", "reason": "adapter-missing", "ok": False}

        # Lazy init
        if self._redis_pool is None:
            try:
                maybe_pool = pool_factory(url=getattr(settings, "REDIS_URL", "redis://localhost:6379/0"))  # type: ignore[misc]
                # Support async factories
                if inspect.iscoroutine(maybe_pool) or inspect.isawaitable(maybe_pool):
                    self._redis_pool = await maybe_pool  # type: ignore[assignment]
                else:
                    self._redis_pool = maybe_pool  # type: ignore[assignment]
            except Exception as exc:  # pragma: no cover
                log.error("health.redis.init_failed", error=str(exc))
                # If an actual adapter factory was found but initialization failed,
                # consider this a fatal error (do not allow fallback). Only when
                # the adapter is truly missing consult the operator-controlled flag.
                if adapter_found:
                    allow_fallback = False
                else:
                    allow_fallback = getattr(settings, "HEALTH_ALLOW_REDIS_HEALTH_FALLBACK", True) if settings else True
                status = "unknown" if allow_fallback else "error"
                return {"status": status, "error": str(exc), "ok": allow_fallback}

        try:
            t0 = time.perf_counter()
            result = self._redis_pool.ping()  # type: ignore[attr-defined]
            # Support sync or async redis adapters
            if inspect.iscoroutine(result) or inspect.isawaitable(result):
                ok = await result
            else:
                ok = result
            took_ms = int((time.perf_counter() - t0) * 1000)
            if ok:
                return {"status": "ok", "latency_ms": took_ms, "ok": True}
            return {"status": "error", "latency_ms": took_ms, "error": "PING returned falsy", "ok": False}
        except Exception as exc:
            log.warning("health.redis.ping_failed", error=str(exc))
            if adapter_found:
                allow_fallback = False
            else:
                allow_fallback = getattr(settings, "HEALTH_ALLOW_REDIS_HEALTH_FALLBACK", True) if settings else True
            status = "unknown" if allow_fallback else "error"
            return {"status": status, "error": str(exc), "ok": allow_fallback}

    async def _probe_memgraph(self) -> dict[str, Any]:
        # Prefer a monkeypatched MemgraphAdapter.
        # If MemgraphAdapter is explicitly None (simulating missing dependency),
        # return adapter-missing semantics so tests can assert 'unknown'.
        adapter_cls = None
        # Evaluate the module-level symbol at call time; if it's None, attempt
        # to pull a MemgraphAdapter from the adapters module (tests may have
        # monkeypatched it there via the use_fake_memgraph fixture).
        # Prefer a monkeypatched MemgraphAdapter.
        # If MemgraphAdapter is explicitly None (simulating missing dependency),
        # return adapter-missing semantics so tests can assert 'unknown'.
        local_adapter = MemgraphAdapter
        if local_adapter is None and MemgraphAdapter is None:
            log.warning("health.memgraph.adapter_missing")
            allow_fallback = getattr(settings, "HEALTH_ALLOW_MG_HEALTH_FALLBACK", True) if settings else True
            return {"status": "unknown", "reason": "adapter-missing", "ok": allow_fallback}

        # Otherwise try to import a real adapter implementation if available.
        if local_adapter is None:
            try:
                import src.adapters.db_memgraph as _db_mod  # type: ignore

                local_adapter = getattr(_db_mod, "MemgraphAdapter", None)
            except Exception:
                local_adapter = None
        if local_adapter is None:
            log.warning("health.memgraph.adapter_missing")
            allow_fallback = getattr(settings, "HEALTH_ALLOW_MG_HEALTH_FALLBACK", True) if settings else True
            # When adapter is missing, mark unknown but allow tests to consider this non-fatal
            return {"status": "unknown", "reason": "adapter-missing", "ok": allow_fallback}
        adapter_cls = local_adapter

        # Lazy init
        if self._memgraph is None:
            try:
                self._memgraph = adapter_cls(  # type: ignore[call-arg]
                    host=getattr(settings, "MG_HOST", "memgraph"),
                    port=int(getattr(settings, "MG_PORT", 7687)),
                    username=getattr(settings, "MG_USER", "") or None,
                    password=getattr(settings, "MG_PASSWORD", "") or None,
                    timeout=3.0,
                )
            except Exception as exc:  # pragma: no cover
                # Adapter initialization failed. Only allow fallback when the
                # adapter is the real implementation from src.adapters.* and the
                # operator explicitly enabled fallback.
                log.error("health.memgraph.init_failed", error=str(exc))
                # If adapter initialization fails, surface an explicit error
                # unless a real mg_health fallback is available and reports OK.
                try:
                    should_fallback = (
                        getattr(settings, "HEALTH_ALLOW_MG_HEALTH_FALLBACK", True)
                        and settings
                        and getattr(settings, "MG_HOST", None)
                        and getattr(adapter_cls, "__module__", "").startswith("src.adapters.")
                    )
                except Exception:
                    should_fallback = False

                if should_fallback:
                    try:
                        from src.adapters.db_memgraph import mg_health as _mg_health  # type: ignore

                        info = _mg_health()
                        return {
                            "status": "ok" if info.get("ok") else "unknown",
                            "reason": info.get("error", ""),
                            "ok": True,
                        }
                    except Exception:
                        pass  # fall through

                return {"status": "error", "error": str(exc), "reason": str(exc), "ok": False}

        # Ping by running a very small query
        try:
            t0 = time.perf_counter()
            ok = await self._run_blocking(self._memgraph.ping)  # type: ignore[union-attr]
            took_ms = int((time.perf_counter() - t0) * 1000)
            if ok:
                # Optionally fetch lightweight info
                info = {}
                try:
                    info = await self._run_blocking(self._memgraph.info)  # type: ignore[union-attr]
                except Exception:  # pragma: no cover
                    info = {}
                return {"status": "ok", "latency_ms": took_ms, "info": info, "ok": True}
            # Ping returned falsy: consider error unless fallback allowed, in
            # which case surface as 'unknown'. Tests accept either.
            allow_fallback = getattr(settings, "HEALTH_ALLOW_MG_HEALTH_FALLBACK", True) if settings else True
            status = "unknown" if allow_fallback else "error"
            return {
                "status": status,
                "latency_ms": took_ms,
                "error": "ping false",
                "reason": "ping false",
                "ok": allow_fallback,
            }
        except Exception as exc:
            log.warning("health.memgraph.ping_failed", error=str(exc))
            # Allow fallback only for real adapters when operator opted in.
            try:
                should_fallback = (
                    getattr(settings, "HEALTH_ALLOW_MG_HEALTH_FALLBACK", False)
                    and settings
                    and getattr(settings, "MG_HOST", None)
                    and getattr(adapter_cls, "__module__", "").startswith("src.adapters.")
                )
            except Exception:
                should_fallback = False

            if should_fallback:
                try:
                    from src.adapters.db_memgraph import mg_health as _mg_health  # type: ignore

                    info = _mg_health()
                    return {"status": "unknown", "reason": info.get("error", ""), "ok": True}
                except Exception:
                    pass
            return {"status": "error", "error": str(exc), "reason": str(exc), "ok": False}

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────
    def _is_critical(self, probe_name: str) -> bool:
        for p in self.probes:
            if p.name == probe_name:
                return p.critical
        return True

    async def _run_blocking(self, fn, *args, **kwargs):
        """
        Run a sync function in a thread to avoid blocking the event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────
    async def start(self) -> None:
        await super().start()
        log.info("health.started")

    async def stop(self) -> None:
        log.info("health.stopping")
        # Close redis pool if present
        try:
            if self._redis_pool is not None:
                await self._redis_pool.aclose()  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass
        await super().stop()
