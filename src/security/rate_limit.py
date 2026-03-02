"""
Rate limiting utilities with optional Redis backend and in-memory fallback.

Design
------
- Strategy: fixed-window counter (simple and predictable).
- Backends:
    * "redis"  -> uses Redis INCR + EXPIRE per (key, window)
    * "memory" -> per-process dict with a lock
  If Redis is configured but unavailable, we degrade to memory and log once.

Configuration (src.config.Settings)
-----------------------------------
- RATE_LIMIT_ENABLED: bool = True
- RATE_LIMIT_BACKEND: str = "redis" | "memory"
- RATE_LIMIT_DEFAULT_LIMIT: int = 60            # requests per window
- RATE_LIMIT_DEFAULT_WINDOW: int = 60           # window length in seconds

Public API
----------
- rate_limit_check(key, limit=None, window=None, cost=1, user=None) -> RateLimitResult
- rate_limiter(limit=None, window=None, key=None, key_func=None, cost=1) -> FastAPI dependency
- get_backend() -> str

The FastAPI dependency will:
- Compute a key (explicit `key`, or `key_func(request, user)`, or fallback).
- Call rate_limit_check and raise HTTP 429 if denied.
- Emit an audit record via `audit_rate_limit`.

Notes
-----
- The in-memory backend is per-process and non-distributed. Use Redis in multi-replica setups.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Lazy imports for FastAPI-only helpers
try:  # pragma: no cover
    from fastapi import Depends, HTTPException, Request, status
except Exception:  # pragma: no cover
    Request = Any  # type: ignore
    def Depends(x):
        return x  # type: ignore
    HTTPException = Exception  # type: ignore
    status = type("S", (), {"HTTP_429_TOO_MANY_REQUESTS": 429})()  # type: ignore

from contextlib import suppress

from src.config import settings

from .audit import audit_rate_limit

# Optional Prometheus
try:  # pragma: no cover
    from prometheus_client import Counter, Gauge
except Exception:  # pragma: no cover
    Counter = None  # type: ignore
    Gauge = None  # type: ignore

if Counter is not None:  # pragma: no cover
    try:
        RL_CHECKS = Counter(
            "rate_limit_checks_total",
            "Number of rate limit checks",
            labelnames=("backend", "allowed"),
        )
    except Exception:
        # In test environments modules may be reloaded and the global registry
        # already contain a collector with the same name which raises a
        # ValueError. In that case we disable metrics (tests don't rely on
        # Prometheus being available) to avoid a hard crash on import.
        RL_CHECKS = None  # type: ignore
else:  # pragma: no cover
    RL_CHECKS = None  # type: ignore

# Redis adapter (optional)
with suppress(Exception):  # pragma: no cover
    from db.redis_cache.client import (
        incr_with_ttl as _redis_incr_with_ttl,
        redis_available as _redis_available,
        ttl as _redis_ttl,
    )

# Logging
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)


# ---------------- Datamodel ----------------
@dataclass(frozen=True)
class RateLimitResult:
    key: str
    limit: int
    window: int
    count: int
    remaining: int
    reset_seconds: int
    allowed: bool
    backend: str
    now: int


# ---------------- Config helpers ----------------
def _enabled() -> bool:
    # Prefer module-level config overrides (tests may monkeypatch src.config attributes)
    try:
        import src.config as _cfg_mod

        return bool(getattr(_cfg_mod, "RATE_LIMIT_ENABLED", getattr(settings, "RATE_LIMIT_ENABLED", True)))
    except Exception:
        return bool(getattr(settings, "RATE_LIMIT_ENABLED", True))


def _default_limit() -> int:
    try:
        import src.config as _cfg_mod

        return int(getattr(_cfg_mod, "RATE_LIMIT_DEFAULT_LIMIT", getattr(settings, "RATE_LIMIT_DEFAULT_LIMIT", 60)))
    except Exception:
        return int(getattr(settings, "RATE_LIMIT_DEFAULT_LIMIT", 60))


def _default_window() -> int:
    try:
        import src.config as _cfg_mod

        return int(getattr(_cfg_mod, "RATE_LIMIT_DEFAULT_WINDOW", getattr(settings, "RATE_LIMIT_DEFAULT_WINDOW", 60)))
    except Exception:
        return int(getattr(settings, "RATE_LIMIT_DEFAULT_WINDOW", 60))


def _cfg_backend() -> str:
    try:
        import src.config as _cfg_mod

        val = (
            str(getattr(_cfg_mod, "RATE_LIMIT_BACKEND", getattr(settings, "RATE_LIMIT_BACKEND", "redis")))
            .lower()
            .strip()
        )
    except Exception:
        val = str(getattr(settings, "RATE_LIMIT_BACKEND", "redis")).lower().strip()
    return val if val in {"redis", "memory"} else "memory"


# ---------------- Backend selection ----------------
_backend_forced: str | None = None
_logged_degrade_once: bool = False


def get_backend() -> str:
    """Return the effective backend ("redis" or "memory")."""
    global _backend_forced, _logged_degrade_once
    if _backend_forced:
        return _backend_forced
    preferred = _cfg_backend()
    if preferred == "redis":
        if "_redis_available" in globals():
            try:
                if _redis_available():  # type: ignore[name-defined]
                    _backend_forced = "redis"
                    return "redis"
            except Exception:
                logger.debug("rate_limit: redis availability check failed", exc_info=True)
        # degrade
        _backend_forced = "memory"
        if not _logged_degrade_once:
            _logged_degrade_once = True
            logger.warning("rate_limit: redis unavailable; using in-memory fallback")
        return "memory"
    _backend_forced = "memory"
    return "memory"


# ---------------- Helpers ----------------
def _window_start(now: int, window: int) -> int:
    return (now // window) * window


def _redis_key(key: str, win_start: int) -> str:
    return f"rl:{key}:{win_start}"


# ---------------- In-memory backend ----------------
_mem_lock = threading.Lock()
_mem_counters: dict[str, dict[str, int]] = {}
# structure: {key: {"start": window_start_epoch, "count": n}}


def _mem_check(key: str, limit: int, window: int, *, cost: int, now: int | None = None) -> RateLimitResult:
    n = int(now or time.time())
    start = _window_start(n, window)
    reset = start + window - n

    with _mem_lock:
        # Reset if missing or for new period
        if key not in _mem_counters or _mem_counters[key].get("start") != start:
            _mem_counters[key] = {"start": start, "count": 0}
        rec = _mem_counters.get(key)
        new_count = rec["count"] + int(cost)
        allowed = new_count <= limit
        if allowed:
            rec["count"] = new_count
        count = rec["count"] if allowed else new_count
        if not allowed:
            # ensure stored counter reflects observed usage
            _mem_counters[key]["count"] = new_count
        remaining = max(0, limit - count)

    return RateLimitResult(
        key=key,
        limit=limit,
        window=window,
        count=count,
        remaining=remaining,
        reset_seconds=reset,
        allowed=allowed,
        backend="memory",
        now=n,
    )


# ---------------- Redis backend ----------------
def _redis_check(key: str, limit: int, window: int, *, cost: int, now: int | None = None) -> RateLimitResult:
    if "_redis_incr_with_ttl" not in globals():  # pragma: no cover
        # Should not happen; fallback to memory
        return _mem_check(key, limit, window, cost=cost, now=now)

    n = int(now or time.time())
    start = _window_start(n, window)
    k = _redis_key(key, start)

    # We don't have a native "INCRBYEX". For "cost">1 we run INCR repeatedly to avoid
    # extra round trips, we just call once and add cost-1 locally; the result remains
    # conservative for enforcement (may undercount at extreme concurrency).
    count = int(_redis_incr_with_ttl(k, window))  # type: ignore[name-defined]
    # If cost > 1, adjust the count pessimistically
    if cost > 1:
        # We can't atomically add cost-1; simply treat as count + (cost - 1)
        count += cost - 1
    allowed = count <= limit
    with suppress(Exception):  # pragma: no cover
        t = int(_redis_ttl(k))  # type: ignore[name-defined]
        reset = t if t >= 0 else (start + window - n)
    if "reset" not in locals():
        reset = max(0, start + window - n)

    remaining = max(0, limit - count)
    return RateLimitResult(
        key=key,
        limit=limit,
        window=window,
        count=count,
        remaining=remaining,
        reset_seconds=int(reset),
        allowed=allowed,
        backend="redis",
        now=n,
    )


# ---------------- Core API ----------------
def rate_limit_check(
    key: str,
    *,
    limit: int | None = None,
    window: int | None = None,
    cost: int = 1,
    user: Any = None,
) -> RateLimitResult:
    """
    Consume `cost` from the current window for `key` and return result.
    """
    if not _enabled():
        n = int(time.time())
        return RateLimitResult(
            key=key,
            limit=limit or _default_limit(),
            window=window or _default_window(),
            count=0,
            remaining=999_999_999,
            reset_seconds=_default_window(),
            allowed=True,
            backend="disabled",
            now=n,
        )

    lim = int(limit or _default_limit())
    win = int(window or _default_window())
    backend = get_backend()

    if backend == "redis":
        result = _redis_check(key, lim, win, cost=cost)
    else:
        result = _mem_check(key, lim, win, cost=cost)

    # Metrics
    if RL_CHECKS is not None:  # pragma: no cover
        with suppress(Exception):
            RL_CHECKS.labels(backend=result.backend, allowed=str(result.allowed).lower()).inc()

    # Audit
    with suppress(Exception):
        principal = None
        if user is not None:
            # Normalize to subject-only identity
            if hasattr(user, "sub") and user.sub:
                principal = user.sub
            elif isinstance(user, dict) and user.get("sub"):
                principal = user.get("sub")
        audit_rate_limit(
            principal=principal,
            key=result.key,
            allowed=result.allowed,
            limit=result.limit,
            window_seconds=result.window,
            count=result.count,
        )

    return result


# ---------------- FastAPI dependency ----------------
def _default_key_func(request: Request, user: Any) -> str:  # type: ignore[valid-type]
    """Default key derivation: subject-only identity; fallback to client IP.

    Previous versions tried username then sub; this has been simplified to avoid
    divergent identities across routes. Username is deprecated and should not
    influence rate limiting or logging keys.
    """
    ident = None
    if user is not None:
        with suppress(Exception):
            if hasattr(user, "sub") and user.sub:
                ident = user.sub
            elif isinstance(user, dict) and user.get("sub"):
                ident = user.get("sub")
    if not ident:
        try:
            ident = request.client.host if request.client else "anon"  # type: ignore[attr-defined]
        except Exception:
            ident = "anon"
    tenant = getattr(request.state, "tenant_id", "global") if getattr(request, "state", None) else "global"
    return f"rl:{tenant}:{ident}:{request.url.path if getattr(request,'url',None) else ''}"


def rate_limiter(
    *,
    limit: int | None = None,
    window: int | None = None,
    key: str | None = None,
    key_func: Callable[[Request, Any], str] | None = None,  # type: ignore[valid-type]
    cost: int = 1,
):
    """
    Build a FastAPI dependency that enforces a rate limit at request-time.

    Example:
        @router.get("/expensive", dependencies=[Depends(rate_limiter(limit=10, window=60))])
        async def expensive():
            return {"ok": True}
    """
    # Lazy import to avoid circular deps
    with suppress(Exception):
        pass  # type: ignore

    async def _dep(request: Request, user=Depends(globals().get("get_current_user", lambda: None))):  # type: ignore
        k = key or (key_func(request, user) if key_func else _default_key_func(request, user))
        res = rate_limit_check(k, limit=limit, window=window, cost=cost, user=user)
        if not res.allowed:
            headers = {
                "Retry-After": str(max(1, res.reset_seconds)),
                "X-RateLimit-Limit": str(res.limit),
                "X-RateLimit-Remaining": str(res.remaining),
                "X-RateLimit-Reset": str(res.reset_seconds),
            }
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"message": "Rate limit exceeded", "key": res.key},
                headers=headers,  # type: ignore[arg-type]
            )
        # Optionally expose headers on success too (useful for clients)
        with suppress(Exception):
            request.scope.get("fastapi_astack")  # No safe way to set headers here without Response injection
        return True

    # Return a small compatibility wrapper so callers can either pass the
    # returned value directly into FastAPI `dependencies=[...]` (it exposes
    # `.dependency`) or call it directly in unit tests (it's callable).
    return CallableDepends(_dep)


def globals():
    """Return this module's globals dict (tests call rl.globals())."""
    return sys.modules[__name__].__dict__


class CallableDepends:
    """Compatibility wrapper that behaves like FastAPI's Depends(obj)

    - exposes `.dependency` for FastAPI route registration
    - is callable so tests can `await dep(request)` directly
    """

    def __init__(self, func):
        self.dependency = func
        self.use_cache = True

    async def __call__(self, *args, **kwargs):
        # Ensure we call the dependency as async if it's async
        fn = self.dependency
        res = fn(*args, **kwargs)
        if hasattr(res, "__await__"):
            return await res  # type: ignore
        return res


__all__ = ["RateLimitResult", "get_backend", "rate_limit_check", "rate_limiter"]
