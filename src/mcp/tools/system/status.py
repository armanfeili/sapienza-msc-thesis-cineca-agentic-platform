"""
MCP Tool — system.status

Returns a snapshot of the running service: version/build info, process details,
configured endpoints, and the health status of core dependencies (Memgraph, Redis,
OTEL exporter).

Action: status (only action)
----------------------------

Payload (optional)
------------------
{
  "action": "status",         # default (only action available)
  "detail": "basic" | "full"  # default: "full"
}

Return
------
{
  "ok": true,
  "action": "status",
  "checked_at": "2025-08-09T10:42:00Z",
  "service": {
    "name": "Cineca Agentic Platform",
    "version": "0.1.0",
    "env": "dev",
    "debug": false,
    "log_level": "INFO",
    "uptime_sec": 123.45,
    "process": { ... },
    "build":   { ... }
  },
  "endpoints": {
    "http": {
      "health": "/health",
      "ready": "/ready",
      "metrics": "/metrics",
      "docs": "/docs"
    }
  },
  "components": {
    "memgraph": { "enabled": true, "ok": true,  "host": "memgraph", "port": 7687 },
    "redis":    { "enabled": true, "ok": true,  "host": "redis",    "port": 6379, "db": 0 },
    "otel":     { "enabled": false, "endpoint": null }
  },
  "warnings": []
}
"""

from __future__ import annotations

import os
import platform
import socket
import sys
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

# ── Optional: psutil for accurate process start time ──────────────────────────
try:  # pragma: no cover
    import psutil  # type: ignore

    _PSUTIL_AVAILABLE = True
except Exception:  # pragma: no cover
    psutil = None  # type: ignore
    _PSUTIL_AVAILABLE = False

# ── Logging ───────────────────────────────────────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

# ── P3 Pattern: ToolContext ──────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp.decorator import mcp_tool  # type: ignore
with suppress(Exception):
    from src.mcp.context import ToolContext  # type: ignore

# ── App/version/config ────────────────────────────────────────────────────────
with suppress(Exception):
    from src import __version__  # type: ignore
if "__version__" not in globals():
    __version__ = "0.1.0"

try:
    from src.config import settings  # type: ignore
except Exception as e:  # pragma: no cover
    # Minimal fallback if settings cannot be imported
    class _FallbackSettings:
        APP_NAME = "Cineca Agentic Platform"
        APP_ENV = os.getenv("APP_ENV", "dev")
        DEBUG = bool(int(os.getenv("DEBUG", "0") or "0"))
        LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        MG_HOST = os.getenv("MG_HOST", "memgraph")
        MG_PORT = int(os.getenv("MG_PORT", "7687"))
        MG_USER = os.getenv("MG_USER", "")
        MG_PASSWORD = os.getenv("MG_PASSWORD", "")
        REDIS_HOST = os.getenv("REDIS_HOST", "redis")
        REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
        REDIS_DB = int(os.getenv("REDIS_DB", "0"))
        OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    settings = _FallbackSettings()  # type: ignore
    logger.warning("Using fallback settings in system.status: %s", e)

# ── Adapters (optional) ───────────────────────────────────────────────────────
with suppress(Exception):
    from src.adapters.db_memgraph import MemgraphAdapter  # type: ignore
with suppress(Exception):
    from db.redis_cache.client import get_redis  # type: ignore

# ── Local boot timestamp (fallback if psutil isn't available) ─────────────────
_MODULE_LOADED_AT = datetime.now(UTC)


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uptime_seconds() -> float:
    """Calculate process uptime in seconds."""
    try:
        if _PSUTIL_AVAILABLE and psutil is not None:
            p = psutil.Process()
            started = datetime.fromtimestamp(p.create_time(), tz=UTC)
            return max(0.0, (datetime.now(UTC) - started).total_seconds())
    except Exception:  # pragma: no cover
        pass
    # Fallback to module import time
    return max(0.0, (datetime.now(UTC) - _MODULE_LOADED_AT).total_seconds())


def _memgraph_status(detail: bool = True) -> dict[str, Any]:
    """Check Memgraph connection and status."""
    info: dict[str, Any] = {
        "enabled": True,
        "ok": False,
        "host": getattr(settings, "MG_HOST", "memgraph"),
        "port": int(getattr(settings, "MG_PORT", 7687)),
    }
    if "MemgraphAdapter" not in globals():
        info["enabled"] = True
        info["ok"] = False
        info["error"] = "adapter_not_available"
        return info
    try:
        adapter = MemgraphAdapter(
            host=info["host"],
            port=info["port"],
            username=getattr(settings, "MG_USER", "") or None,
            password=getattr(settings, "MG_PASSWORD", "") or None,
        )
        ok, err = adapter.healthcheck(timeout=1.5)
        info["ok"] = bool(ok)
        if err:
            info["error"] = err
        if detail and info["ok"]:
            # A tiny sample to prove query path works
            with adapter.cursor() as cur:
                cur.execute("RETURN 1 AS one")
                row = cur.fetchone()
                info["sample"] = {"RETURN 1": row[0] if row else None}
        return info
    except Exception as e:  # pragma: no cover
        info["ok"] = False
        info["error"] = str(e)
        return info


def _redis_status(detail: bool = True) -> dict[str, Any]:
    """Check Redis connection and status."""
    host = getattr(settings, "REDIS_HOST", "redis")
    port = int(getattr(settings, "REDIS_PORT", 6379))
    db = int(getattr(settings, "REDIS_DB", 0))
    info: dict[str, Any] = {
        "enabled": True,
        "host": host,
        "port": port,
        "db": db,
        "ok": False,
    }
    if "get_redis" not in globals():
        info["enabled"] = True
        info["ok"] = False
        info["error"] = "adapter_not_available"
        return info
    try:
        r = get_redis(host=host, port=port, db=db)
        pong = r.ping()
        info["ok"] = bool(pong)
        if detail and info["ok"]:
            r.set("__status_probe", "ok", ex=5)
            val = r.get("__status_probe")
            info["sample"] = {"__status_probe": (val.decode("utf-8") if val else None)}
        return info
    except Exception as e:  # pragma: no cover
        info["ok"] = False
        info["error"] = str(e)
        return info


def _otel_status() -> dict[str, Any]:
    """Check OpenTelemetry configuration."""
    endpoint = getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    enabled = bool(endpoint)
    return {"enabled": enabled, "endpoint": endpoint or None}


def _process_info() -> dict[str, Any]:
    """Gather process/runtime information."""
    exe = sys.executable or ""
    return {
        "pid": os.getpid(),
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "executable": exe,
        "argv": sys.argv[:],
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "hostname": socket.gethostname(),
    }


def _build_info() -> dict[str, Any]:
    """Gather build/deployment information."""
    return {
        "commit": os.getenv("GIT_COMMIT") or getattr(settings, "BUILD_COMMIT", None),
        "tag": os.getenv("GIT_TAG") or getattr(settings, "BUILD_TAG", None),
        "timestamp": os.getenv("BUILD_TIMESTAMP") or getattr(settings, "BUILD_TIMESTAMP", None),
        "image": os.getenv("IMAGE_REF") or getattr(settings, "IMAGE_REF", None),
    }


def _service_info() -> dict[str, Any]:
    """Gather service/application information."""
    return {
        "name": getattr(settings, "APP_NAME", "Cineca Agentic Platform"),
        "version": __version__,
        "env": getattr(settings, "APP_ENV", "dev"),
        "debug": bool(getattr(settings, "DEBUG", False)),
        "log_level": str(getattr(settings, "LOG_LEVEL", "INFO")),
        "uptime_sec": _uptime_seconds(),
        "process": _process_info(),
        "build": _build_info(),
    }


def _endpoints() -> dict[str, Any]:
    """Return configured HTTP endpoints."""
    return {
        "http": {
            "health": "/health",
            "ready": "/ready",
            "metrics": "/metrics",
            "docs": "/docs",
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# P3 Internal Action Handler
# ─────────────────────────────────────────────────────────────────────────────


def _act_status(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Return comprehensive system status including service info, endpoints, and component health.

    Args:
        ctx: ToolContext (unused for this action but kept for consistency)
        payload: Optional dict with "detail" key ("basic" or "full")

    Returns:
        Dict with ok, action, checked_at, service, endpoints, components, warnings
    """
    detail = str(payload.get("detail", "full")).strip().lower()
    detailed = detail != "basic"

    components = {
        "memgraph": _memgraph_status(detail=detailed),
        "redis": _redis_status(detail=detailed),
        "otel": _otel_status(),
    }

    warnings = []
    if not components["memgraph"].get("ok", False):
        warnings.append("memgraph_unhealthy")
    if components["redis"]["enabled"] and not components["redis"].get("ok", False):
        warnings.append("redis_unhealthy")
    if components["otel"]["enabled"] and not components["otel"].get("endpoint"):
        warnings.append("otel_endpoint_missing")

    result: dict[str, Any] = {
        "ok": len([w for w in warnings if "unhealthy" in w]) == 0,
        "action": "status",
        "checked_at": _now_iso(),
        "service": _service_info(),
        "endpoints": _endpoints(),
        "components": components,
        "warnings": warnings,
    }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# P3 Decorated Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" in globals():

    @mcp_tool(tool_name="system.status", required_scope="tools:read")
    def system_status(
        ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs: Any  # type: ignore
    ) -> dict[str, Any]:
        """
        Entry function for system.status tool (P3 pattern).

        Args:
            ctx: Tool execution context with principal, tenant, trace_id
            payload: Optional dict with "detail" key
            **kwargs: Additional arguments (ignored)

        Returns:
            System status dict with service/component info
        """
        payload = payload or {}

        try:
            return _act_status(ctx, payload)
        except Exception as e:
            logger.exception("system.status failed", extra={"error": str(e)})
            return {
                "ok": False,
                "action": "status",
                "error": str(e),
                "checked_at": _now_iso(),
            }


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Entry Point (when decorator not available)
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" not in globals():

    def system_status(ctx: Any = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """
        Fallback entry function for system.status tool (no decorator).
        """
        payload = payload or {}

        try:
            return _act_status(ctx, payload)
        except Exception as e:
            logger.exception("system.status failed", extra={"error": str(e)})
            return {
                "ok": False,
                "action": "status",
                "error": str(e),
                "checked_at": _now_iso(),
            }


# ── Backward compatibility aliases ──────────────────────────────────────────
invoke = system_status
run = system_status
handle = system_status
