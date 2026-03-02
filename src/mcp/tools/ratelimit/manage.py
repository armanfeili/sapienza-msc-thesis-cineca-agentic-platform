"""
MCP Tool: ratelimit.manage

Administrative entrypoints to inspect and tune the global rate limiter at runtime.

Actions
-------
- status
    Inspect the current limiter configuration and counters.
    Payload: { "verbose": false }
    Returns: {
      ok, action:"status",
      enabled, dry_run, backend, window, rate, burst,
      approx_keys, stats? (if verbose)
    }

- enable / disable
    Toggle enforcement.
    Payload: {}
    Returns: { ok, action:"enable"|"disable", enabled }

- set
    Update global limits. Any field omitted is left unchanged.
    Payload: { "rate": 5.0, "burst": 20, "window": 60, "dry_run": false }
    Returns: { ok, action:"set", applied:{...}, config:{...} }

- reset
    Clear all counters/buckets.
    Payload: {}
    Returns: { ok, action:"reset" }

- check
    Probe the limiter for a given key.
    Payload: { "key": "user:123", "cost": 1 }
    Returns: { ok, action:"check", key, allowed, remaining?, retry_after? }

Notes
-----
This tool is defensive: it adapts to whichever API the runtime limiter exposes.
It expects something like `src.security.rate_limit` to provide one of:

    get_rate_limiter() -> limiter
or  GLOBAL / global_rate_limiter / rate_limiter object

And the limiter to support a subset of:
    .allow(key:str, cost:int=1) -> (allowed:bool, meta:dict)
    .get_stats(verbose:bool=False) -> dict
    .set_enabled(bool) / .enabled (attr)
    .set_dry_run(bool)  / .dry_run (attr)
    .set_limits(rate:float|None, burst:int|None, window:int|None)
    .reset()

If a capability is missing, the tool will best-effort fallback and still return ok.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

# ── P0 Infrastructure ────────────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import RateLimitManagePayload

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Limiter resolution & shims
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_limiter() -> Any:
    """
    Try multiple import paths to find the global limiter instance/factory.
    """
    with suppress(Exception):
        from src.security.rate_limit import get_rate_limiter  # type: ignore

        rl = get_rate_limiter()
        if rl:
            return rl
    with suppress(Exception):
        from src.security import rate_limit as rlmod  # type: ignore

        for name in ("GLOBAL", "global_rate_limiter", "rate_limiter", "limiter"):
            rl = getattr(rlmod, name, None)
            if rl is not None:
                return rl
        # Fallback: construct if a class is exposed
        RLCls = getattr(rlmod, "RateLimiter", None)
        if RLCls:
            try:
                return RLCls()
            except Exception:
                pass

    # Last resort: a no-op shim that always allows
    class _NoopLimiter:
        enabled = False
        dry_run = True
        window = 60
        rate = 1000.0
        burst = 1000
        backend = "noop"

        def allow(self, key: str, cost: int = 1):
            return True, {"remaining": self.burst, "retry_after": 0.0}

        def get_stats(self, verbose: bool = False):
            return {
                "enabled": self.enabled,
                "dry_run": self.dry_run,
                "backend": self.backend,
                "window": self.window,
                "rate": self.rate,
                "burst": self.burst,
                "approx_keys": 0,
                "buckets": {} if verbose else None,
            }

        def set_enabled(self, v: bool):
            self.enabled = bool(v)

        def set_dry_run(self, v: bool):
            self.dry_run = bool(v)

        def set_limits(self, *, rate: float | None = None, burst: int | None = None, window: int | None = None):
            if rate is not None:
                self.rate = float(rate)
            if burst is not None:
                self.burst = int(burst)
            if window is not None:
                self.window = int(window)

        def reset(self):
            return

    return _NoopLimiter()


_RL = _resolve_limiter()


def _rl_get_config() -> dict[str, Any]:
    # Try generic attribute access
    cfg = {
        "enabled": bool(getattr(_RL, "enabled", True)),
        "dry_run": bool(getattr(_RL, "dry_run", False)),
        "backend": str(getattr(_RL, "backend", getattr(_RL, "mode", "memory"))),
        "window": int(getattr(_RL, "window", getattr(_RL, "default_window", 60))),
        "rate": float(getattr(_RL, "rate", getattr(_RL, "default_rate", 5.0))),
        "burst": int(getattr(_RL, "burst", getattr(_RL, "default_burst", 20))),
    }
    # If a stats call exists, prefer it for approx_keys
    approx_keys = None
    with suppress(Exception):
        stats = _RL.get_stats(False)
        approx_keys = stats.get("approx_keys")
    cfg["approx_keys"] = approx_keys if approx_keys is not None else int(getattr(_RL, "approx_keys", 0))
    return cfg


def _rl_set_enabled(v: bool) -> None:
    with suppress(Exception):
        return _RL.set_enabled(bool(v))
    _RL.enabled = bool(v)


def _rl_set_dry_run(v: bool) -> None:
    with suppress(Exception):
        return _RL.set_dry_run(bool(v))
    _RL.dry_run = bool(v)


def _rl_set_limits(rate: float | None = None, burst: int | None = None, window: int | None = None) -> None:
    with suppress(Exception):
        return _RL.set_limits(rate=rate, burst=burst, window=window)
    # Fallback: set attributes directly if present
    if rate is not None:
        with suppress(Exception):
            _RL.rate = float(rate)
        with suppress(Exception):
            _RL.default_rate = float(rate)
    if burst is not None:
        with suppress(Exception):
            _RL.burst = int(burst)
        with suppress(Exception):
            _RL.default_burst = int(burst)
    if window is not None:
        with suppress(Exception):
            _RL.window = int(window)
        with suppress(Exception):
            _RL.default_window = int(window)


def _rl_reset() -> None:
    with suppress(Exception):
        return _RL.reset()


def _rl_allow(key: str, cost: int = 1):
    with suppress(Exception):
        ok, meta = _RL.allow(key, cost=cost)
        return bool(ok), (meta or {})
    # Fallback: always allow
    return True, {"remaining": None, "retry_after": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# Actions
# ─────────────────────────────────────────────────────────────────────────────
def _act_status(payload: dict[str, Any]) -> dict[str, Any]:
    verbose = bool(payload.get("verbose", False))
    cfg = _rl_get_config()

    stats = None
    if verbose:
        with suppress(Exception):
            stats = _RL.get_stats(True)

    return {
        "ok": True,
        "action": "status",
        **{k: cfg[k] for k in ("enabled", "dry_run", "backend", "window", "rate", "burst", "approx_keys")},
        "stats": stats,
    }


def _act_enable(_: dict[str, Any]) -> dict[str, Any]:
    _rl_set_enabled(True)
    return {"ok": True, "action": "enable", "enabled": True}


def _act_disable(_: dict[str, Any]) -> dict[str, Any]:
    _rl_set_enabled(False)
    return {"ok": True, "action": "disable", "enabled": False}


def _act_set(payload: dict[str, Any]) -> dict[str, Any]:
    rate = payload.get("rate")
    burst = payload.get("burst")
    window = payload.get("window")
    dry_run = payload.get("dry_run")
    applied: dict[str, Any] = {}

    if rate is not None:
        _rl_set_limits(rate=float(rate))
        applied["rate"] = float(rate)
    if burst is not None:
        _rl_set_limits(burst=int(burst))
        applied["burst"] = int(burst)
    if window is not None:
        _rl_set_limits(window=int(window))
        applied["window"] = int(window)
    if dry_run is not None:
        _rl_set_dry_run(bool(dry_run))
        applied["dry_run"] = bool(dry_run)

    cfg = _rl_get_config()
    return {"ok": True, "action": "set", "applied": applied, "config": cfg}


def _act_reset(_: dict[str, Any]) -> dict[str, Any]:
    _rl_reset()
    return {"ok": True, "action": "reset"}


def _act_check(payload: dict[str, Any]) -> dict[str, Any]:
    key = str(payload.get("key") or "").strip()
    if not key:
        raise ValueError("check requires 'key'")
    cost = int(payload.get("cost", 1))
    allowed, meta = _rl_allow(key, cost=cost)
    out = {"ok": True, "action": "check", "key": key, "allowed": bool(allowed)}
    if isinstance(meta, dict):
        if "remaining" in meta:
            out["remaining"] = meta.get("remaining")
        if "retry_after" in meta:
            out["retry_after"] = meta.get("retry_after")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="ratelimit.manage", required_scope="tools:admin")
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Entry for ratelimit.manage tool.

    This tool is wrapped with @mcp_tool which provides:
    - Automatic RBAC enforcement (requires tools:admin scope)
    - Audit logging (all rate limit changes tracked)
    - Metrics collection
    - Structured error handling
    """
    payload = payload or {}

    # Pydantic validation
    validated = RateLimitManagePayload(**payload)

    # Merge validated payload back
    payload = {**payload, **validated.model_dump(exclude_none=True)}

    action = validated.action

    if action == "status":
        result = _act_status(payload)
    elif action == "enable":
        result = _act_enable(payload)
    elif action == "disable":
        result = _act_disable(payload)
    elif action == "set":
        result = _act_set(payload)
    elif action == "reset":
        result = _act_reset(payload)
    else:  # check
        result = _act_check(payload)

    # Audit handled by @mcp_tool decorator

    return result


# Back-compat aliases
run = invoke
handle = invoke
