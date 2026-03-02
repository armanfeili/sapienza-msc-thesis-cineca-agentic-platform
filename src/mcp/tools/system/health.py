"""
MCP Tool — system.health

Lightweight liveness/readiness checks used by MCP and by the REST /health, /ready
endpoints. Designed to be dependency-tolerant: if a dependency or adapter isn't
available, it reports that gracefully instead of crashing.

Actions
-------
- liveness (default): quick self-check that the process can execute code.
- readiness: deeper checks of external dependencies (Memgraph, Redis).
- details: same as readiness but includes version/env details.

Response shape
--------------
{
  "ok": bool,
  "action": "liveness" | "readiness" | "details",
  "checked_at": "2025-08-09T10:42:00Z",
  "summary": { "passed": 2, "failed": 0, "skipped": 1 },
  "components": {
      "app":   { "status": "up", "latency_ms": 0.1 },
      "db":    { "status": "up"/"down"/"skipped", ... },
      "redis": { "status": "up"/"down"/"skipped", ... }
  },
  "info": { ... }  # only for action=details
}

Following P3 pattern:
- Uses @mcp_tool decorator
- Internal _act_* functions
- Proper context handling
"""

from __future__ import annotations

import os
import socket
import time
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

# ── JSON (prefer orjson) ──────────────────────────────────────────────────────
try:
    import orjson as _json  # type: ignore

    def _dumps(obj: Any) -> bytes:
        return _json.dumps(obj)

except Exception:  # pragma: no cover
    import json as _json  # type: ignore

    def _dumps(obj: Any) -> bytes:
        return _json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# ── Logging ───────────────────────────────────────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── Settings / adapters (optional) ────────────────────────────────────────────
with suppress(Exception):
    from src import __version__ as _pkg_version  # type: ignore
with suppress(Exception):
    from src.config import settings  # type: ignore
with suppress(Exception):
    from src.adapters.db_memgraph import MemgraphAdapter  # type: ignore
with suppress(Exception):
    from db.redis_cache.client import RedisFactory  # type: ignore
with suppress(Exception):
    from src.mcp.decorator import mcp_tool  # type: ignore
with suppress(Exception):
    from src.mcp.context import ToolContext  # type: ignore


# Fallback lightweight settings if full config isn't importable
if "settings" not in globals():

    class _S:
        APP_NAME: str = os.getenv("APP_NAME", "cineca-agentic-platform")
        APP_ENV: str = os.getenv("APP_ENV", "dev")
        MG_HOST: str = os.getenv("MG_HOST", "memgraph")
        MG_PORT: int = int(os.getenv("MG_PORT", "7687"))
        MG_USER: str = os.getenv("MG_USER", "")
        MG_PASSWORD: str = os.getenv("MG_PASSWORD", "")
        REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "false").lower() in {"1", "true", "yes"}
        REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
        REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
        REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
        REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    settings = _S()  # type: ignore


APP_VERSION = "0.1.0"
if "_pkg_version" in globals():
    with suppress(Exception):
        APP_VERSION = _pkg_version  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _result(status: str, **extra: Any) -> dict[str, Any]:
    out = {"status": status}
    out.update(extra)
    return out


def _check_app() -> dict[str, Any]:
    t0 = time.perf_counter()
    # trivial work; if this runs, liveness is OK
    hostname = socket.gethostname()
    latency = (time.perf_counter() - t0) * 1000.0
    return _result("up", latency_ms=round(latency, 2), hostname=hostname)


def _check_memgraph() -> dict[str, Any]:
    # If adapter is not available, mark as skipped (still OK for liveness)
    if "MemgraphAdapter" not in globals():
        return _result("skipped", reason="adapter_unavailable")

    t0 = time.perf_counter()
    try:
        mg = MemgraphAdapter(  # type: ignore[call-arg]
            host=getattr(settings, "MG_HOST", "memgraph"),
            port=int(getattr(settings, "MG_PORT", 7687)),
            username=getattr(settings, "MG_USER", "") or None,
            password=getattr(settings, "MG_PASSWORD", "") or None,
        )
        # quick ping
        list(mg.execute("RETURN 1 AS ok"))
        latency = (time.perf_counter() - t0) * 1000.0
        with suppress(Exception):
            mg.close()  # type: ignore[attr-defined]
        return _result(
            "up",
            latency_ms=round(latency, 2),
            host=getattr(settings, "MG_HOST", "memgraph"),
            port=int(getattr(settings, "MG_PORT", 7687)),
        )
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000.0
        return _result(
            "down",
            latency_ms=round(latency, 2),
            error=str(e)[:500],
            host=getattr(settings, "MG_HOST", None),
            port=getattr(settings, "MG_PORT", None),
        )


def _check_redis() -> dict[str, Any]:
    # If redis is disabled, skip.
    enabled = bool(getattr(settings, "REDIS_ENABLED", False))
    if not enabled:
        return _result("skipped", reason="disabled")

    if "RedisFactory" not in globals():
        return _result("skipped", reason="adapter_unavailable")

    t0 = time.perf_counter()
    try:
        rf = RedisFactory(
            host=getattr(settings, "REDIS_HOST", "redis"),
            port=int(getattr(settings, "REDIS_PORT", 6379)),
            db=int(getattr(settings, "REDIS_DB", 0)),
            password=getattr(settings, "REDIS_PASSWORD", "") or None,
            decode_responses=True,
        )  # type: ignore[call-arg]
        r = rf.client()  # sync client
        pong = r.ping()
        latency = (time.perf_counter() - t0) * 1000.0
        return _result(
            "up" if pong else "down",
            latency_ms=round(latency, 2),
            host=getattr(settings, "REDIS_HOST", "redis"),
            port=int(getattr(settings, "REDIS_PORT", 6379)),
            db=int(getattr(settings, "REDIS_DB", 0)),
        )
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000.0
        return _result(
            "down",
            latency_ms=round(latency, 2),
            error=str(e)[:500],
            host=getattr(settings, "REDIS_HOST", None),
            port=getattr(settings, "REDIS_PORT", None),
            db=getattr(settings, "REDIS_DB", None),
        )


def _summarize(components: dict[str, dict[str, Any]]) -> dict[str, int]:
    passed = sum(1 for c in components.values() if c.get("status") == "up")
    failed = sum(1 for c in components.values() if c.get("status") == "down")
    skipped = sum(1 for c in components.values() if c.get("status") == "skipped")
    return {"passed": passed, "failed": failed, "skipped": skipped}


def _normalize_for_backward_compat(result: dict[str, Any]) -> dict[str, Any]:
    """
    Backward-compatible normalization for callers/tests that expect a top-level
    `status` string and/or a `checks` mapping.
    """
    if "status" not in result:
        result["status"] = "ok" if result.get("ok") else "error"
    if "checks" not in result and "components" in result:
        # tests expect 'checks' to be a dict mapping probe name -> probe payload
        checks = result.get("components")
        # Normalize probe status vocabulary to {'ok','error','unknown'}
        norm_map = {"up": "ok", "down": "error", "skipped": "unknown"}
        for _name, probe in list(checks.items()):
            if isinstance(probe, dict) and "status" in probe:
                probe_status = probe.get("status")
                if isinstance(probe_status, str):
                    probe["status"] = norm_map.get(probe_status.lower(), probe_status)
        result["checks"] = checks
    return result


# ─────────────────────────────────────────────────────────────────────────────
# P3 Internal Action Handlers
# ─────────────────────────────────────────────────────────────────────────────


def _act_liveness(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Liveness check: quick self-check that process can execute code."""
    comps = {"app": _check_app()}
    result = {
        "ok": comps["app"]["status"] == "up",
        "action": "liveness",
        "checked_at": _now_iso(),
        "summary": _summarize(comps),
        "components": comps,
    }
    return _normalize_for_backward_compat(result)


def _act_readiness(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Readiness check: deeper checks of external dependencies."""
    comps = {
        "app": _check_app(),
        "db": _check_memgraph(),
        "redis": _check_redis(),
    }
    ok = all(c.get("status") in {"up", "skipped"} for c in comps.values())
    result = {
        "ok": ok,
        "action": "readiness",
        "checked_at": _now_iso(),
        "summary": _summarize(comps),
        "components": comps,
    }
    return _normalize_for_backward_compat(result)


def _act_details(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Details check: same as readiness but includes version/env details."""
    comps = {
        "app": _check_app(),
        "db": _check_memgraph(),
        "redis": _check_redis(),
    }
    ok = all(c.get("status") in {"up", "skipped"} for c in comps.values())
    result = {
        "ok": ok,
        "action": "details",
        "checked_at": _now_iso(),
        "summary": _summarize(comps),
        "components": comps,
        "info": {
            "app": {
                "name": getattr(settings, "APP_NAME", "cineca-agentic-platform"),
                "env": getattr(settings, "APP_ENV", "dev"),
                "version": APP_VERSION,
            },
            "platform": {
                "python": "{}.{}.{}".format(*(__import__("sys").version_info[:3])),
            },
        },
    }
    return _normalize_for_backward_compat(result)


# ─────────────────────────────────────────────────────────────────────────────
# Decorated entry point (P3 pattern)
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" in globals():

    @mcp_tool(tool_name="system.health", required_scope="tools:read")
    def system_health(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
        """
        MCP tool for system health checks.

        Actions:
        - liveness: quick self-check
        - readiness: dependency checks
        - details: readiness + version info
        """
        payload = payload or {}
        action = str(payload.get("action", "liveness")).strip().lower()

        try:
            if action == "liveness":
                return _act_liveness(ctx, payload)
            elif action == "readiness":
                return _act_readiness(ctx, payload)
            elif action == "details":
                return _act_details(ctx, payload)
            else:
                raise ValueError(f"unsupported action: {action}")
        except Exception as e:
            logger.exception("system.health action failed", extra={"action": action})
            result = {"ok": False, "action": action, "error": str(e), "checked_at": _now_iso()}
            return _normalize_for_backward_compat(result)


# Fallback for environments without decorator
else:

    def system_health(payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
        """Fallback entry point without decorator."""
        payload = payload or {}
        action = str(payload.get("action", "liveness")).strip().lower()

        try:
            if action == "liveness":
                return _act_liveness(None, payload)
            elif action == "readiness":
                return _act_readiness(None, payload)
            elif action == "details":
                return _act_details(None, payload)
            else:
                raise ValueError(f"unsupported action: {action}")
        except Exception as e:
            logger.exception("system.health action failed", extra={"action": action})
            result = {"ok": False, "action": action, "error": str(e), "checked_at": _now_iso()}
            return _normalize_for_backward_compat(result)


# Aliases expected by the MCP loader
invoke = system_health
run = system_health
handle = system_health
