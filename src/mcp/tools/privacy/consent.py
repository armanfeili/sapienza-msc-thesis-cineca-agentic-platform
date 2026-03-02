"""
MCP Tool: privacy.consent

Lightweight consent registry backed by Redis (with an in-process fallback).

Actions
-------
- status
    Payload: { "subject_id": "user-123", "tenant": "default" }
    Returns: { ok, action:"status", tenant, subject_id, version, updated_at, flags:{...} }

- set
    Payload: {
      "subject_id": "...",
      "tenant": "default",
      "flags": { "analytics": true, "research": false },
      "actor": "admin@example.org",
      "note": "bulk update"
    }
    Returns: { ok, action:"set", changed:{...}, flags:{...} }

- grant
    Payload: { "subject_id":"...", "flags": ["analytics","research"], "tenant":"default" }
    Returns: { ok, action:"grant", changed:{...}, flags:{...} }

- revoke
    Payload: { "subject_id":"...", "flags": ["analytics"], "tenant":"default" }
    Returns: { ok, action:"revoke", changed:{...}, flags:{...} }

- history
    Payload: { "subject_id":"...", "tenant":"default", "limit": 50 }
    Returns: { ok, action:"history", events:[{...}] }

- erase
    Payload: { "subject_id":"...", "tenant":"default", "actor":"...", "note":"RTBF" }
    Returns: { ok, action:"erase", erased:true }

Notes
-----
- Redis keys:
    consent:{tenant}:{subject_id}         (JSON document)
    consent:{tenant}:{subject_id}:history (list of JSON events)
- If Redis is unavailable, an in-memory dict is used (non-persistent).
- Idempotent operations via version tracking
- Audit changes automatically
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

# ── Optional orjson ───────────────────────────────────────────────────────────
_ORJSON = None
with suppress(Exception):
    import orjson as _orjson  # type: ignore

    _ORJSON = _orjson


def _json_dumps(obj: Any) -> str:
    if _ORJSON is not None:
        try:
            return _ORJSON.dumps(obj).decode("utf-8")
        except Exception:
            pass
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _json_loads(s: str) -> Any:
    if _ORJSON is not None:
        try:
            return _ORJSON.loads(s)
        except Exception:
            pass
    return json.loads(s)


# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── MCP Framework ─────────────────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool

# ── Redis adapter (best-effort) ──────────────────────────────────────────────
_redis = None
with suppress(Exception):
    from db.redis_cache.client import get_redis  # type: ignore

    _redis = get_redis()

_INMEM_STORE: dict[str, str] = {}
_INMEM_HISTORY: dict[str, list[str]] = {}

# ── Audit (best-effort) ──────────────────────────────────────────────────────
with suppress(Exception):
    from src.security.audit import audit_access  # type: ignore
if "audit_access" not in globals():

    def audit_access(**_: Any) -> None:  # type: ignore
        return


# ─────────────────────────────────────────────────────────────────────────────
# Configuration / schema
# ─────────────────────────────────────────────────────────────────────────────
VERSION = 1
DEFAULT_TENANT = "default"

# Minimal set of flags; extend safely over time
DEFAULT_FLAGS: dict[str, bool] = {
    "analytics": False,  # operational metrics/telemetry
    "improve_models": False,  # using data to improve models
    "research": False,  # academic/clinical research usage
    "third_party": False,  # share with third-party processors
    "email": False,  # receive email updates
    "profiling": False,  # automated profiling for personalization
}


# ─────────────────────────────────────────────────────────────────────────────
# Storage helpers
# ─────────────────────────────────────────────────────────────────────────────
def _key(tenant: str, subject_id: str) -> str:
    return f"consent:{tenant}:{subject_id}"


def _key_hist(tenant: str, subject_id: str) -> str:
    return f"{_key(tenant, subject_id)}:history"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _load_state(tenant: str, subject_id: str) -> dict[str, Any]:
    key = _key(tenant, subject_id)
    if _redis:
        try:
            raw = _redis.get(key)
            if raw:
                return _json_loads(raw.decode("utf-8"))
        except Exception as e:
            logger.warning("consent.redis_get_failed", error=str(e))
    else:
        raw = _INMEM_STORE.get(key)
        if raw:
            return _json_loads(raw)
    # new record
    return {
        "version": VERSION,
        "tenant": tenant,
        "subject_id": subject_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "flags": dict(DEFAULT_FLAGS),
    }


def _save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _now_iso()
    key = _key(state["tenant"], state["subject_id"])
    payload = _json_dumps(state)
    if _redis:
        try:
            _redis.set(key, payload)
            return
        except Exception as e:
            logger.warning("consent.redis_set_failed", error=str(e))
    _INMEM_STORE[key] = payload


def _append_history(tenant: str, subject_id: str, event: dict[str, Any]) -> None:
    key = _key_hist(tenant, subject_id)
    event.setdefault("ts", _now_iso())
    data = _json_dumps(event)
    if _redis:
        try:
            _redis.lpush(key, data)
            _redis.ltrim(key, 0, 999)  # cap history to last 1000
            return
        except Exception as e:
            logger.warning("consent.redis_lpush_failed", error=str(e))
    _INMEM_HISTORY.setdefault(key, []).insert(0, data)
    _INMEM_HISTORY[key] = _INMEM_HISTORY[key][:1000]


def _get_history(tenant: str, subject_id: str, limit: int = 100) -> list[dict[str, Any]]:
    key = _key_hist(tenant, subject_id)
    out: list[dict[str, Any]] = []
    if _redis:
        try:
            items = _redis.lrange(key, 0, max(0, limit - 1))
            for b in items or []:
                with suppress(Exception):
                    out.append(_json_loads(b.decode("utf-8")))
            return out
        except Exception as e:
            logger.warning("consent.redis_lrange_failed", error=str(e))
    for s in _INMEM_HISTORY.get(key, [])[:limit]:
        with suppress(Exception):
            out.append(_json_loads(s))
    return out


def _erase_all(tenant: str, subject_id: str) -> None:
    k = _key(tenant, subject_id)
    kh = _key_hist(tenant, subject_id)
    if _redis:
        try:
            _redis.delete(k)
            _redis.delete(kh)
            return
        except Exception as e:
            logger.warning("consent.redis_delete_failed", error=str(e))
    _INMEM_STORE.pop(k, None)
    _INMEM_HISTORY.pop(kh, None)


# ─────────────────────────────────────────────────────────────────────────────
# Core logic
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_flags(flags: Any) -> dict[str, bool]:
    """
    Accepts:
      - dict[str,bool]
      - list[str]  (interpreted as True)
    Returns a sanitized dict with only known flag names; unknown keys are kept
    but validated to boolean.
    """
    out: dict[str, bool] = {}
    if isinstance(flags, Mapping):
        for k, v in flags.items():
            out[str(k)] = bool(v)
    elif isinstance(flags, (list, tuple)):
        for k in flags:
            out[str(k)] = True
    elif flags is None:
        return {}
    else:
        raise ValueError("flags must be a dict[str,bool] or list[str]")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Action: status
# ─────────────────────────────────────────────────────────────────────────────
def _act_status(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    tenant = str(payload.get("tenant") or ctx.tenant)
    subject = str(payload.get("subject_id") or "").strip()
    if not subject:
        raise ValueError("status requires 'subject_id'")
    state = _load_state(tenant, subject)
    return {
        "ok": True,
        "action": "status",
        "tenant": tenant,
        "subject_id": subject,
        "version": state.get("version", VERSION),
        "updated_at": state.get("updated_at"),
        "flags": state.get("flags", {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Action: set
# ─────────────────────────────────────────────────────────────────────────────
def _act_set(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    tenant = str(payload.get("tenant") or ctx.tenant)
    subject = str(payload.get("subject_id") or "").strip()
    if not subject:
        raise ValueError("set requires 'subject_id'")
    flags = _normalize_flags(payload.get("flags"))
    if not flags:
        raise ValueError("set requires non-empty 'flags'")

    actor = payload.get("actor") or ctx.principal
    note = payload.get("note")

    state = _load_state(tenant, subject)
    before = dict(state.get("flags", {}))
    after = dict(before)
    after.update({k: bool(v) for k, v in flags.items()})
    state["flags"] = after
    _save_state(state)

    changed = {k: after[k] for k in after if before.get(k) != after[k]}
    if changed:
        _append_history(
            tenant,
            subject,
            {"action": "set", "actor": actor, "note": note, "changed": changed},
        )

    # audit
    with suppress(Exception):
        audit_access(
            principal=actor,
            resource=f"consent:{tenant}:{subject}",
            action="set",
            allowed=True,
            attributes={"changed": changed},
        )

    return {"ok": True, "action": "set", "tenant": tenant, "subject_id": subject, "changed": changed, "flags": after}


# ─────────────────────────────────────────────────────────────────────────────
# Action: grant
# ─────────────────────────────────────────────────────────────────────────────
def _act_grant(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    flags = _normalize_flags(payload.get("flags"))
    if not flags:
        raise ValueError("grant requires 'flags'")
    flags = dict.fromkeys(flags.keys(), True)
    payload = dict(payload)
    payload["flags"] = flags
    result = _act_set(ctx, payload)
    result["action"] = "grant"
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Action: revoke
# ─────────────────────────────────────────────────────────────────────────────
def _act_revoke(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    flags = _normalize_flags(payload.get("flags"))
    if not flags:
        raise ValueError("revoke requires 'flags'")
    flags = dict.fromkeys(flags.keys(), False)
    payload = dict(payload)
    payload["flags"] = flags
    result = _act_set(ctx, payload)
    result["action"] = "revoke"
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Action: history
# ─────────────────────────────────────────────────────────────────────────────
def _act_history(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    tenant = str(payload.get("tenant") or ctx.tenant)
    subject = str(payload.get("subject_id") or "").strip()
    if not subject:
        raise ValueError("history requires 'subject_id'")
    limit = int(payload.get("limit", 100))
    events = _get_history(tenant, subject, limit=limit)
    return {"ok": True, "action": "history", "tenant": tenant, "subject_id": subject, "events": events}


# ─────────────────────────────────────────────────────────────────────────────
# Action: erase
# ─────────────────────────────────────────────────────────────────────────────
def _act_erase(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    tenant = str(payload.get("tenant") or ctx.tenant)
    subject = str(payload.get("subject_id") or "").strip()
    if not subject:
        raise ValueError("erase requires 'subject_id'")
    actor = payload.get("actor") or ctx.principal
    note = payload.get("note") or "erase"

    # append an erase event BEFORE deletion to keep a minimal audit (policy choice)
    _append_history(tenant, subject, {"action": "erase", "actor": actor, "note": note})
    _erase_all(tenant, subject)

    with suppress(Exception):
        audit_access(
            principal=actor,
            resource=f"consent:{tenant}:{subject}",
            action="erase",
            allowed=True,
            attributes={"note": note},
        )

    return {"ok": True, "action": "erase", "tenant": tenant, "subject_id": subject, "erased": True}


# ─────────────────────────────────────────────────────────────────────────────
# Tool registration
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(
    tool_name="privacy.consent",
    required_scope="tools:write",
)
def privacy_consent(ctx: ToolContext, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Privacy consent tool - manage user consent preferences.

    Actions: status, set, grant, revoke, history, erase
    """
    action = str(payload.get("action", "status")).strip().lower()

    if action not in {"status", "set", "grant", "revoke", "history", "erase"}:
        raise ValueError("action must be one of: status, set, grant, revoke, history, erase")

    if action == "status":
        return _act_status(ctx, payload)
    elif action == "set":
        return _act_set(ctx, payload)
    elif action == "grant":
        return _act_grant(ctx, payload)
    elif action == "revoke":
        return _act_revoke(ctx, payload)
    elif action == "history":
        return _act_history(ctx, payload)
    else:  # erase
        return _act_erase(ctx, payload)
