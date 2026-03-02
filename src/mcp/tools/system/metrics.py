"""
MCP Tool — system.metrics

Scrapes Prometheus metrics from the default registry and returns them either in
the Prometheus text exposition format or as structured JSON.

Actions
-------
- scrape (default): return a snapshot of the current Prometheus registry.
- info:             lightweight info about the registry (counts, names).

Payload
-------
{
  "action": "scrape" | "info",
  "format": "text" | "json",        # only for action=scrape (default: "text")
  "names": ["metric_a", "metric_b"] # optional allowlist filter
}

Return (scrape, text)
---------------------
{
  "ok": true,
  "action": "scrape",
  "format": "text",
  "content_type": "text/plain; version=0.0.4; charset=utf-8",
  "checked_at": "2025-08-09T10:42:00Z",
  "body": "# HELP ...\n# TYPE ...\n..."
}

Return (scrape, json)
---------------------
{
  "ok": true,
  "action": "scrape",
  "format": "json",
  "checked_at": "...",
  "metrics": [
    {
      "name": "python_gc_objects_collected_total",
      "type": "counter",
      "documentation": "Objects collected during gc",
      "samples": [
        { "name": "python_gc_objects_collected_total", "labels": {"generation": "0"}, "value": 123 }
      ]
    },
    ...
  ]
}

Return (info)
-------------
{
  "ok": true,
  "action": "info",
  "checked_at": "...",
  "registry": {
    "families": 42,
    "sample_series": 321,
    "names": ["process_cpu_seconds_total", "..."]
  }
}
"""

from __future__ import annotations

from collections.abc import Sequence
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

# ── P3 Pattern: ToolContext ───────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp.decorator import mcp_tool  # type: ignore
with suppress(Exception):
    from src.mcp.context import ToolContext  # type: ignore

# ── Prometheus client imports ─────────────────────────────────────────────────
try:
    from prometheus_client import REGISTRY, generate_latest  # type: ignore
    from prometheus_client.exposition import CONTENT_TYPE_LATEST  # type: ignore

    _PROM_AVAILABLE = True
except Exception as e:  # pragma: no cover
    _PROM_AVAILABLE = False
    _PROM_IMPORT_ERROR = str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _allowlist(names: Sequence[str] | None) -> set[str] | None:
    """Convert name sequence to set for filtering."""
    if not names:
        return None
    return {str(n).strip() for n in names if str(n).strip()}


def _filter_family(family, allowed: set[str] | None) -> bool:
    """Return True if the metric family or any of its samples match the allowlist."""
    if allowed is None:
        return True
    if family.name in allowed:
        return True
    return any(s.name in allowed for s in getattr(family, "samples", []) or [])


def _scrape_text(allowed_names: set[str] | None) -> dict[str, Any]:
    """Generate Prometheus text exposition format."""
    # Fast-path: if no filter, use generate_latest directly
    if allowed_names is None:
        body = generate_latest(REGISTRY).decode("utf-8")
        return {
            "ok": True,
            "action": "scrape",
            "format": "text",
            "content_type": CONTENT_TYPE_LATEST,
            "checked_at": _now_iso(),
            "body": body,
        }

    # Filtered path: rebuild a temporary text exposition with only selected families.
    # We keep this simple by generating JSON internally then re-serializing to text-like lines.
    data = _scrape_json(allowed_names)
    if not data.get("ok"):
        return data
    # Minimal text representation (not strictly identical to Prometheus exposition,
    # but sufficient for filtered debugging); prefer json for filtered use.
    lines: list[str] = []
    for fam in data.get("metrics", []):
        name = fam.get("name", "")
        mtype = fam.get("type", "untyped")
        doc = fam.get("documentation", "")
        if doc:
            lines.append(f"# HELP {name} {doc}")
        if mtype:
            lines.append(f"# TYPE {name} {mtype}")
        for s in fam.get("samples", []):
            lbls = s.get("labels") or {}
            if lbls:
                lbl_txt = ",".join(f'{k}="{v}"' for k, v in sorted(lbls.items()))
                lines.append(f'{s.get("name", name)}{{{lbl_txt}}} {s.get("value", 0)}')
            else:
                lines.append(f'{s.get("name", name)} {s.get("value", 0)}')
    body = "\n".join(lines) + ("\n" if lines else "")
    return {
        "ok": True,
        "action": "scrape",
        "format": "text",
        "content_type": CONTENT_TYPE_LATEST,
        "checked_at": _now_iso(),
        "body": body,
    }


def _scrape_json(allowed_names: set[str] | None) -> dict[str, Any]:
    """Generate JSON format metrics."""
    metrics: list[dict[str, Any]] = []
    for family in REGISTRY.collect():
        if not _filter_family(family, allowed_names):
            continue
        entry: dict[str, Any] = {
            "name": family.name,
            "type": family.type,
            "documentation": getattr(family, "documentation", "") or "",
            "samples": [],
        }
        for s in getattr(family, "samples", []) or []:
            if allowed_names is not None and (family.name not in allowed_names and s.name not in allowed_names):
                continue
            # prometheus_client uses Tuple[str, Dict[str,str], value, ...]
            entry["samples"].append(
                {
                    "name": s.name,
                    "labels": dict(s.labels) if getattr(s, "labels", None) else {},
                    "value": float(s.value),
                }
            )
        metrics.append(entry)

    return {
        "ok": True,
        "action": "scrape",
        "format": "json",
        "checked_at": _now_iso(),
        "metrics": metrics,
    }


# ─────────────────────────────────────────────────────────────────────────────
# P3 Internal Action Handlers
# ─────────────────────────────────────────────────────────────────────────────


def _act_scrape(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Scrape Prometheus metrics from the default registry.

    Args:
        ctx: ToolContext (unused for this action but kept for consistency)
        payload: Dict with optional "format" ("text"|"json") and "names" (allowlist filter)

    Returns:
        Dict with ok, action, format, and either "body" (text) or "metrics" (json)
    """
    fmt = str(payload.get("format", "text")).strip().lower()
    names = payload.get("names")
    allowed = _allowlist(names)

    if fmt == "json":
        return _scrape_json(allowed)
    # default -> text
    return _scrape_text(allowed)


def _act_info(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Return lightweight registry info without full metric values.

    Args:
        ctx: ToolContext (unused for this action but kept for consistency)
        payload: Dict (unused for this action)

    Returns:
        Dict with ok, action, checked_at, and registry stats
    """
    families = 0
    series = 0
    names: set[str] = set()
    for fam in REGISTRY.collect():
        families += 1
        names.add(fam.name)
        series += len(getattr(fam, "samples", []) or [])
        for s in getattr(fam, "samples", []) or []:
            names.add(s.name)
    return {
        "ok": True,
        "action": "info",
        "checked_at": _now_iso(),
        "registry": {
            "families": families,
            "sample_series": series,
            "names": sorted(names),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# P3 Decorated Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" in globals():

    @mcp_tool(tool_name="system.metrics", required_scope="tools:read")
    def system_metrics(
        ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs: Any  # type: ignore
    ) -> dict[str, Any]:
        """
        Entry function for system.metrics tool (P3 pattern).

        Args:
            ctx: Tool execution context with principal, tenant, trace_id
            payload: Optional dict with "action" ("scrape"|"info"), "format", "names"
            **kwargs: Additional arguments (ignored)

        Returns:
            Metrics data dict based on action
        """
        if not _PROM_AVAILABLE:  # pragma: no cover
            return {
                "ok": False,
                "action": (payload or {}).get("action", "scrape"),
                "error": f"prometheus_client not available: {_PROM_IMPORT_ERROR}",
                "checked_at": _now_iso(),
            }

        payload = payload or {}
        action = str(payload.get("action", "scrape")).strip().lower()

        try:
            if action == "scrape":
                return _act_scrape(ctx, payload)
            elif action == "info":
                return _act_info(ctx, payload)
            else:
                raise ValueError(f"unsupported action: {action}")
        except Exception as e:
            logger.exception("system.metrics action failed", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
                "checked_at": _now_iso(),
            }


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Entry Point (when decorator not available)
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" not in globals():

    def system_metrics(ctx: Any = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """
        Fallback entry function for system.metrics tool (no decorator).
        """
        if not _PROM_AVAILABLE:  # pragma: no cover
            return {
                "ok": False,
                "action": (payload or {}).get("action", "scrape"),
                "error": f"prometheus_client not available: {_PROM_IMPORT_ERROR}",
                "checked_at": _now_iso(),
            }

        payload = payload or {}
        action = str(payload.get("action", "scrape")).strip().lower()

        try:
            if action == "scrape":
                return _act_scrape(ctx, payload)
            elif action == "info":
                return _act_info(ctx, payload)
            else:
                raise ValueError(f"unsupported action: {action}")
        except Exception as e:
            logger.exception("system.metrics action failed", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
                "checked_at": _now_iso(),
            }


# ── Backward compatibility aliases ───────────────────────────────────────────
invoke = system_metrics
run = system_metrics
handle = system_metrics
