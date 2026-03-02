"""
MCP Tool: security.audit - Record and retrieve security audit events with PII redaction.
"""
from __future__ import annotations

import re
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

with suppress(Exception):
    from src.logging_setup import get_logger

    logger = get_logger(__name__)
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

import builtins

from src.mcp.runtime import ToolContext, mcp_tool


class _MemoryAuditSink:
    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def emit(self, event: dict[str, Any]) -> None:
        self._events.append(dict(event))

    def list(
        self,
        *,
        tenant: str | None = None,
        principal: str | None = None,
        action: str | None = None,
        resource_substr: str | None = None,
        allowed: bool | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, builtins.list[dict[str, Any]]]:
        items = self._events[:]
        if tenant is not None:
            items = [e for e in items if e.get("tenant") == tenant]
        if principal is not None:
            items = [e for e in items if e.get("principal") == principal]
        if action is not None:
            items = [e for e in items if e.get("action") == action]
        if resource_substr:
            items = [e for e in items if resource_substr.lower() in str(e.get("resource", "")).lower()]
        if allowed is not None:
            items = [e for e in items if e.get("allowed") is allowed]
        if since:
            items = [e for e in items if str(e.get("ts", "")) >= since]
        if until:
            items = [e for e in items if str(e.get("ts", "")) <= until]
        total = len(items)
        return total, items[offset : offset + max(0, limit)]

    def stats(self, *, tenant: str | None = None) -> dict[str, Any]:
        total, items = self.list(tenant=tenant, limit=10_000_000, offset=0)
        by_action: dict[str, int] = {}
        allow = deny = 0
        for e in items:
            a = str(e.get("action", ""))
            by_action[a] = by_action.get(a, 0) + 1
            if e.get("allowed") is True:
                allow += 1
            elif e.get("allowed") is False:
                deny += 1
        return {"total": total, "allowed": allow, "denied": deny, "by_action": by_action}

    def clear(self, *, tenant: str | None = None) -> int:
        if tenant is None:
            n = len(self._events)
            self._events.clear()
            return n
        before = len(self._events)
        self._events = [e for e in self._events if e.get("tenant") != tenant]
        return before - len(self._events)


_SINK = _MemoryAuditSink()

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _redact_pii(value: str) -> str:
    if not isinstance(value, str):
        return value
    value = _EMAIL_PATTERN.sub("***@***.***", value)
    value = _IP_PATTERN.sub("***.***.***.***", value)
    return value


def _redact_event(event: dict[str, Any], requesting_principal: str | None = None) -> dict[str, Any]:
    event = dict(event)
    if requesting_principal and event.get("principal") == requesting_principal:
        return event
    for field in ["ip", "user_agent", "principal"]:
        if event.get(field):
            event[field] = _redact_pii(str(event[field]))
    if "attributes" in event and isinstance(event["attributes"], dict):
        event["attributes"] = {
            k: _redact_pii(str(v)) if isinstance(v, str) else v for k, v in event["attributes"].items()
        }
    return event


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _act_access(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    event = {
        "id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "trace_id": ctx.trace_id,
        "tenant": payload.get("tenant", ctx.tenant),
        "principal": payload.get("principal", ctx.principal),
        "resource": payload.get("resource"),
        "action": payload.get("action") or "access",
        "allowed": bool(payload.get("allowed", True)),
        "reason": payload.get("reason"),
        "attributes": payload.get("attributes") or {},
        "ip": payload.get("ip"),
        "user_agent": payload.get("user_agent"),
        "kind": "access",
    }
    with suppress(Exception):
        _SINK.emit(event)
    return {"ok": True, "action": "access", "event": event}


def _act_custom(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    event = {
        "id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "trace_id": ctx.trace_id,
        "tenant": payload.get("tenant", ctx.tenant),
        "principal": payload.get("principal", ctx.principal),
        "name": payload.get("name") or "custom",
        "data": payload.get("data") or {},
        "kind": "custom",
    }
    with suppress(Exception):
        _SINK.emit(event)
    return {"ok": True, "action": "custom", "event": event}


def _act_list(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    limit = min(int(payload.get("limit", 100)), 1000)
    offset = max(int(payload.get("offset", 0)), 0)
    with suppress(Exception):
        total, items = _SINK.list(
            tenant=payload.get("tenant"),
            principal=payload.get("principal"),
            action=payload.get("action"),
            resource_substr=payload.get("resource_substr"),
            allowed=payload.get("allowed"),
            since=payload.get("since"),
            until=payload.get("until"),
            limit=limit,
            offset=offset,
        )
        redacted_items = [_redact_event(item, ctx.principal) for item in items]
        return {
            "ok": True,
            "action": "list",
            "total": int(total),
            "items": redacted_items,
            "limit": limit,
            "offset": offset,
        }
    return {"ok": True, "action": "list", "total": 0, "items": [], "limit": limit, "offset": offset}


def _act_stats(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    with suppress(Exception):
        stats = _SINK.stats(tenant=payload.get("tenant"))
        return {"ok": True, "action": "stats", "stats": stats}
    return {"ok": True, "action": "stats", "stats": {"total": 0, "allowed": 0, "denied": 0, "by_action": {}}}


def _act_clear(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    if not bool(payload.get("confirm")):
        raise ValueError("clear requires 'confirm': true")
    with suppress(Exception):
        n = _SINK.clear(tenant=payload.get("tenant"))
        return {"ok": True, "action": "clear", "cleared": True, "count": int(n)}
    return {"ok": True, "action": "clear", "cleared": False, "count": 0}


@mcp_tool(tool_name="security.audit", required_scope="tools:admin")
def security_audit(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "list")).strip().lower()
    if action not in {"access", "custom", "list", "stats", "clear"}:
        raise ValueError("action must be one of: access, custom, list, stats, clear")
    if action == "access":
        return _act_access(ctx, payload)
    elif action == "custom":
        return _act_custom(ctx, payload)
    elif action == "list":
        return _act_list(ctx, payload)
    elif action == "stats":
        return _act_stats(ctx, payload)
    else:
        return _act_clear(ctx, payload)


invoke = security_audit
run = security_audit
handle = security_audit
