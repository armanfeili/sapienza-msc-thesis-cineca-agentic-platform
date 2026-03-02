"""
MCP Tool: errors.report

Accepts a structured error payload, sanitizes it, logs it, and emits an audit
event (best-effort). Returns a normalized error event object with a generated
event_id so callers can correlate logs.

Payload (all optional except `message`)
---------------------------------------
{
  "message": "Human-readable description of the error",  # required
  "code": "E_GRAPH_TIMEOUT",                             # optional short code
  "severity": "error",                                   # info|warning|error|critical (default: error)
  "category": "application",                             # application|mcp|graph|security|system|external
  "resource": "graph.query",                             # logical target
  "principal": "alice",                                  # user/subject if known
  "trace_id": "req-12345",                               # correlation id
  "context": { ... },                                    # arbitrary dict; will be PII-scrubbed
  "exception": { "type": "...", "message": "...", "stack": "..." },  # optional structured exception
  "capture_stack": false                                 # if true, include current stack (no exception)
}

Response
--------
{
  "ok": true,
  "event": {
    "id": "<uuid>",
    "timestamp": <epoch_seconds>,
    "message": "...",
    "code": "E_...",
    "severity": "...",
    "category": "...",
    "resource": "...",
    "principal": "...",
    "trace_id": "...",
    "context": { ... },       # scrubbed
    "exception": { ... }      # if present
  }
}
"""

from __future__ import annotations

import time
import traceback
import uuid
from contextlib import suppress
from typing import Any

# ── P0 Infrastructure ────────────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import ErrorsReportPayload

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── PII scrubber (best-effort) ───────────────────────────────────────────────
with suppress(Exception):
    from src.security.pii_scrubber import scrub_dict  # type: ignore
if "scrub_dict" not in globals():

    def scrub_dict(d: dict[str, Any], mode: str | None = None) -> dict[str, Any]:  # type: ignore
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
_SEVERITY_LEVEL = {
    "info": "info",
    "warning": "warning",
    "warn": "warning",
    "error": "error",
    "critical": "critical",
    "fatal": "critical",
}


def _normalize_severity(s: str | None) -> str:
    if not s:
        return "error"
    return _SEVERITY_LEVEL.get(str(s).lower(), "error")


def _truncate(val: Any, max_len: int = 4000) -> Any:
    if isinstance(val, str) and len(val) > max_len:
        return val[: max_len - 1] + "…"
    return val


def _current_stack() -> str:
    # Exclude this helper and invoke() call frame for readability
    stack = traceback.format_stack()
    if len(stack) >= 2:
        stack = stack[:-2]
    return "".join(stack)


def _log_event(ev: dict[str, Any]) -> None:
    sev = ev.get("severity", "error")
    ev.get("message", "")
    # Map to logger method
    if sev == "info":
        logger.info("error_report", **ev)
    elif sev == "warning":
        logger.warning("error_report", **ev)
    elif sev == "critical":
        logger.critical("error_report", **ev)
    else:
        logger.error("error_report", **ev)


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="errors.report", required_scope="tools:basic")
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Report a structured error. See module docstring for payload format.

    This tool is wrapped with @mcp_tool which provides:
    - Automatic RBAC enforcement (requires tools:basic scope)
    - Audit logging (all error reports tracked)
    - Metrics collection
    - Structured error handling
    """
    payload = payload or {}

    # Pydantic validation
    validated = ErrorsReportPayload(**payload)

    # Use validated fields
    message = validated.message

    # Use validated fields
    message = validated.message

    # Normalize fields
    code = _truncate(validated.code)
    severity = _normalize_severity(validated.severity)
    category = _truncate(validated.category)
    resource = _truncate(validated.resource)
    principal = _truncate(validated.principal)
    trace_id = _truncate(validated.trace_id)

    # Scrub arbitrary context
    raw_ctx = validated.context or {}
    context = scrub_dict(raw_ctx) if isinstance(raw_ctx, dict) else {}

    # Exception detail (optional)
    exc = validated.exception
    capture_stack = validated.capture_stack
    exception: dict[str, Any] | None = None
    if isinstance(exc, dict) and (exc.get("type") or exc.get("message") or exc.get("stack")):
        exception = {
            "type": _truncate(exc.get("type")),
            "message": _truncate(exc.get("message")),
            "stack": _truncate(exc.get("stack")),
        }
    elif capture_stack:
        exception = {"type": "StackSnapshot", "message": "Captured current stack", "stack": _truncate(_current_stack())}

    # Build normalized event
    event = {
        "id": str(uuid.uuid4()),
        "timestamp": int(time.time()),
        "message": _truncate(str(message)),
        "code": code,
        "severity": severity,
        "category": category,
        "resource": resource,
        "principal": principal,
        "trace_id": trace_id,
        "context": context,
    }
    if exception:
        event["exception"] = exception

    # Log
    with suppress(Exception):
        _log_event(event)

    # Audit handled by @mcp_tool decorator

    return {"ok": True, "event": event}


# Back-compat aliases
run = invoke
handle = invoke
