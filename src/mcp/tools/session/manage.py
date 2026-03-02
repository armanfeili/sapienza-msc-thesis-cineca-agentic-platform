"""
MCP Tool: session.manage

Lightweight session store with optional Redis backend.

Supported actions
-----------------
- create:
    payload: { "session_id"?: str, "principal"?: str, "roles"?: [str], "tenant"?: str,
               "context"?: {..}, "prefs"?: {..} }
    returns: { ok, action:"create", session:{...} }

- read / get:
    payload: { "session_id": str, "tenant"?: str }
    returns: { ok, action:"read", session:{...} }  (404 -> ok:false, error)

- update:
    payload: { "session_id": str, "tenant"?: str,
               "context"?: {...}, "prefs"?: {...}, "principal"?: str, "roles"?: [str],
               "replace"?: bool }
    returns: { ok, action:"update", session:{...} }

- delete:
    payload: { "session_id": str, "tenant"?: str }
    returns: { ok, action:"delete", deleted: bool }

- set_pref:
    payload: { "session_id": str, "key": str, "value": any, "tenant"?: str }
    returns: { ok, action:"set_pref", session:{...} }

- get_pref:
    payload: { "session_id": str, "key": str, "tenant"?: str }
    returns: { ok, action:"get_pref", value: any, exists: bool }

- set_context:
    payload: { "session_id": str, "context": {...}, "tenant"?: str, "replace"?: bool }
    returns: { ok, action:"set_context", session:{...} }

- clear_context:
    payload: { "session_id": str, "tenant"?: str }
    returns: { ok, action:"clear_context", session:{...} }

- touch:
    payload: { "session_id": str, "tenant"?: str }
    returns: { ok, action:"touch", session:{...} }
    Updates session's updated_at timestamp and refreshes TTL.

- exists:
    payload: { "session_id": str, "tenant"?: str }
    returns: { ok, action:"exists", exists: bool }

- list:
    payload: { "tenant"?: str, "limit"?: int, "offset"?: int }
    returns: { ok, action:"list", sessions: [session_id,...], tenant, count, has_more }
    **P6 Feature**: Pagination with limit/offset, count, has_more indicator.

Notes
-----
- If Redis is enabled (via db.redis_cache.client.get_redis), sessions are stored
  under keys: session:{tenant}:{session_id} as JSON.
- Otherwise, an in-memory dictionary is used (process-local).
- **P6 Feature**: TTL is enforced on every write when settings.SESSION_TTL_SECONDS > 0.
- **P6 Feature**: Touch action refreshes TTL, extending session lifetime.
- **P6 Feature**: List action supports pagination (limit/offset/has_more).
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import suppress
from typing import Any

# ── JSON (prefer orjson for speed) ────────────────────────────────────────────
try:
    import orjson as _json  # type: ignore

    def _dumps(obj: Any) -> bytes:
        return _json.dumps(obj)

    def _loads(b: bytes | str) -> Any:
        if isinstance(b, bytes):
            return _json.loads(b)
        return _json.loads(b.encode("utf-8"))

except Exception:
    import json as _json  # type: ignore

    def _dumps(obj: Any) -> bytes:
        return _json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def _loads(b: bytes | str) -> Any:
        if isinstance(b, (bytes, bytearray)):
            b = b.decode("utf-8")
        return _json.loads(b)


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

# ── Optional config / redis ───────────────────────────────────────────────────
with suppress(Exception):
    from src.config import settings  # type: ignore
with suppress(Exception):
    from db.redis_cache.client import get_redis  # type: ignore

# Fallbacks if settings not available
if "settings" not in globals():

    class _S:
        SESSION_TTL_SECONDS: int = int(os.getenv("SESSION_TTL_SECONDS", "3600"))  # Default 1 hour

    settings = _S()  # type: ignore

DEFAULT_TENANT = os.getenv("DEFAULT_TENANT", "default")

# In-memory fallback store (process-local)
_MEM: dict[str, dict[str, Any]] = {}  # key -> session dict


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _key(tenant: str, session_id: str) -> str:
    return f"session:{tenant}:{session_id}"


def _validate_session_id(session_id: str | None) -> str:
    if not session_id:
        raise ValueError("session_id is required")
    return str(session_id)


def _get_tenant(payload: dict[str, Any]) -> str:
    return str(payload.get("tenant") or DEFAULT_TENANT)


def _redis_client():
    try:
        return get_redis()  # type: ignore[name-defined]
    except Exception:
        return None


def _apply_ttl(redis, key: str) -> None:
    """Apply TTL to session key (P6 Feature: TTL enforcement on every write)."""
    ttl = int(getattr(settings, "SESSION_TTL_SECONDS", 3600) or 3600)
    if ttl > 0 and redis:
        try:
            redis.expire(key, ttl)
        except Exception:
            logger.warning("session.manage: failed to set TTL", extra={"key": key, "ttl": ttl})


# ─────────────────────────────────────────────────────────────────────────────
# Storage primitives
# ─────────────────────────────────────────────────────────────────────────────
def _store_get(tenant: str, session_id: str) -> dict[str, Any] | None:
    key = _key(tenant, session_id)
    r = _redis_client()
    if r:
        try:
            raw = r.get(key)
            if not raw:
                return None
            return _loads(raw)
        except Exception:
            logger.exception("session.manage: redis get failed", extra={"key": key})
            return None
    return _MEM.get(key)


def _store_set(tenant: str, session_id: str, doc: dict[str, Any]) -> None:
    """Store session and apply TTL (P6 Feature: TTL on every write)."""
    key = _key(tenant, session_id)
    r = _redis_client()
    if r:
        try:
            r.set(key, _dumps(doc))
            _apply_ttl(r, key)  # P6: Apply TTL on every write
            return
        except Exception:
            logger.exception("session.manage: redis set failed", extra={"key": key})
    _MEM[key] = doc


def _store_del(tenant: str, session_id: str) -> bool:
    key = _key(tenant, session_id)
    r = _redis_client()
    if r:
        try:
            return bool(r.delete(key))
        except Exception:
            logger.exception("session.manage: redis delete failed", extra={"key": key})
    return _MEM.pop(key, None) is not None


def _store_exists(tenant: str, session_id: str) -> bool:
    key = _key(tenant, session_id)
    r = _redis_client()
    if r:
        try:
            return bool(r.exists(key))
        except Exception:
            logger.exception("session.manage: redis exists failed", extra={"key": key})
    return key in _MEM


def _store_list(tenant: str, limit: int = 100, offset: int = 0) -> tuple[list[str], int, bool]:
    """
    List sessions with pagination (P6 Feature).

    Returns:
        (sessions, count, has_more)
    """
    prefix = f"session:{tenant}:"
    r = _redis_client()

    if r:
        try:
            all_sessions: list[str] = []
            for k in r.scan_iter(match=prefix + "*", count=1000):
                k_str = k.decode("utf-8") if isinstance(k, (bytes, bytearray)) else str(k)
                sid = k_str.split(":", 2)[-1]
                all_sessions.append(sid)

            # Apply pagination
            count = len(all_sessions)
            paginated = all_sessions[offset : offset + limit]
            has_more = (offset + limit) < count
            return (paginated, count, has_more)
        except Exception:
            logger.exception("session.manage: redis list failed", extra={"tenant": tenant})

    # Memory fallback
    all_sessions = []
    for k in _MEM:
        if k.startswith(prefix):
            all_sessions.append(k.split(":", 2)[-1])

    count = len(all_sessions)
    paginated = all_sessions[offset : offset + limit]
    has_more = (offset + limit) < count
    return (paginated, count, has_more)


# ─────────────────────────────────────────────────────────────────────────────
# P3 Internal Action Handlers
# ─────────────────────────────────────────────────────────────────────────────


def _act_create(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create new session."""
    tenant = _get_tenant(payload)
    session_id = str(payload.get("session_id") or uuid.uuid4())
    now = _now_iso()
    session = {
        "session_id": session_id,
        "tenant": tenant,
        "principal": payload.get("principal"),
        "roles": list(payload.get("roles") or []),
        "context": dict(payload.get("context") or {}),
        "prefs": dict(payload.get("prefs") or {}),
        "created_at": now,
        "updated_at": now,
    }
    _store_set(tenant, session_id, session)
    return {"ok": True, "action": "create", "session": session}


def _act_read(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Read session by ID."""
    tenant = _get_tenant(payload)
    session_id = _validate_session_id(payload.get("session_id"))
    doc = _store_get(tenant, session_id)
    if not doc:
        return {"ok": False, "action": "read", "error": "not_found", "session_id": session_id, "tenant": tenant}
    return {"ok": True, "action": "read", "session": doc}


def _act_update(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Update session metadata, context, or prefs."""
    tenant = _get_tenant(payload)
    session_id = _validate_session_id(payload.get("session_id"))
    replace = bool(payload.get("replace", False))
    doc = _store_get(tenant, session_id)
    if not doc:
        return {"ok": False, "action": "update", "error": "not_found", "session_id": session_id, "tenant": tenant}

    # Metadata
    if "principal" in payload:
        doc["principal"] = payload.get("principal")
    if "roles" in payload:
        doc["roles"] = list(payload.get("roles") or [])

    # Context
    if "context" in payload:
        new_ctx = dict(payload.get("context") or {})
        if replace:
            doc["context"] = new_ctx
        else:
            doc.setdefault("context", {}).update(new_ctx)

    # Prefs
    if "prefs" in payload:
        new_p = dict(payload.get("prefs") or {})
        if replace:
            doc["prefs"] = new_p
        else:
            doc.setdefault("prefs", {}).update(new_p)

    doc["updated_at"] = _now_iso()
    _store_set(tenant, session_id, doc)
    return {"ok": True, "action": "update", "session": doc}


def _act_delete(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Delete session."""
    tenant = _get_tenant(payload)
    session_id = _validate_session_id(payload.get("session_id"))
    deleted = _store_del(tenant, session_id)
    return {"ok": True, "action": "delete", "deleted": bool(deleted), "session_id": session_id, "tenant": tenant}


def _act_set_pref(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Set single preference key."""
    tenant = _get_tenant(payload)
    session_id = _validate_session_id(payload.get("session_id"))
    key = payload.get("key")
    if not key:
        raise ValueError("key is required")
    doc = _store_get(tenant, session_id)
    if not doc:
        return {"ok": False, "action": "set_pref", "error": "not_found", "session_id": session_id, "tenant": tenant}
    doc.setdefault("prefs", {})[str(key)] = payload.get("value")
    doc["updated_at"] = _now_iso()
    _store_set(tenant, session_id, doc)
    return {"ok": True, "action": "set_pref", "session": doc}


def _act_get_pref(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Get single preference key."""
    tenant = _get_tenant(payload)
    session_id = _validate_session_id(payload.get("session_id"))
    key = payload.get("key")
    if not key:
        raise ValueError("key is required")
    doc = _store_get(tenant, session_id)
    if not doc:
        return {"ok": False, "action": "get_pref", "error": "not_found", "session_id": session_id, "tenant": tenant}
    prefs = doc.get("prefs") or {}
    exists = str(key) in prefs
    return {"ok": True, "action": "get_pref", "value": prefs.get(str(key)), "exists": exists}


def _act_set_context(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Set session context."""
    tenant = _get_tenant(payload)
    session_id = _validate_session_id(payload.get("session_id"))
    replace = bool(payload.get("replace", False))
    new_ctx = dict(payload.get("context") or {})
    doc = _store_get(tenant, session_id)
    if not doc:
        return {"ok": False, "action": "set_context", "error": "not_found", "session_id": session_id, "tenant": tenant}
    if replace:
        doc["context"] = new_ctx
    else:
        doc.setdefault("context", {}).update(new_ctx)
    doc["updated_at"] = _now_iso()
    _store_set(tenant, session_id, doc)
    return {"ok": True, "action": "set_context", "session": doc}


def _act_clear_context(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Clear session context."""
    tenant = _get_tenant(payload)
    session_id = _validate_session_id(payload.get("session_id"))
    doc = _store_get(tenant, session_id)
    if not doc:
        return {
            "ok": False,
            "action": "clear_context",
            "error": "not_found",
            "session_id": session_id,
            "tenant": tenant,
        }
    doc["context"] = {}
    doc["updated_at"] = _now_iso()
    _store_set(tenant, session_id, doc)
    return {"ok": True, "action": "clear_context", "session": doc}


def _act_touch(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Touch session (P6 Feature: refresh TTL).

    Updates updated_at timestamp and reapplies TTL to extend session lifetime.
    """
    tenant = _get_tenant(payload)
    session_id = _validate_session_id(payload.get("session_id"))
    doc = _store_get(tenant, session_id)
    if not doc:
        return {"ok": False, "action": "touch", "error": "not_found", "session_id": session_id, "tenant": tenant}
    doc["updated_at"] = _now_iso()
    _store_set(tenant, session_id, doc)  # Reapplies TTL
    return {"ok": True, "action": "touch", "session": doc}


def _act_exists(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Check if session exists."""
    tenant = _get_tenant(payload)
    session_id = _validate_session_id(payload.get("session_id"))
    return {"ok": True, "action": "exists", "exists": _store_exists(tenant, session_id)}


def _act_list(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    List sessions with pagination (P6 Feature).

    Returns sessions, count, and has_more indicator.
    """
    tenant = _get_tenant(payload)
    limit = int(payload.get("limit", 100))
    offset = int(payload.get("offset", 0))

    sessions, count, has_more = _store_list(tenant, limit=limit, offset=offset)

    return {
        "ok": True,
        "action": "list",
        "sessions": sessions,
        "tenant": tenant,
        "count": count,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


# ─────────────────────────────────────────────────────────────────────────────
# P3 Decorated Entry Point
# ─────────────────────────────────────────────────────────────────────────────

_ACTIONS = {
    "create": _act_create,
    "read": _act_read,
    "get": _act_read,
    "update": _act_update,
    "delete": _act_delete,
    "set_pref": _act_set_pref,
    "get_pref": _act_get_pref,
    "set_context": _act_set_context,
    "clear_context": _act_clear_context,
    "touch": _act_touch,
    "exists": _act_exists,
    "list": _act_list,
}

if "mcp_tool" in globals():

    @mcp_tool(tool_name="session.manage", required_scope="tools:session")
    def session_manage(
        ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs: Any  # type: ignore
    ) -> dict[str, Any]:
        """
        Entry function for session.manage tool (P3 pattern).

        Args:
            ctx: Tool execution context
            payload: Action payload
            **kwargs: Additional arguments (ignored)

        Returns:
            Action result dict
        """
        payload = payload or {}
        action = str(payload.get("action") or "read").strip().lower()
        handler = _ACTIONS.get(action)
        if not handler:
            raise ValueError(f"unsupported action: {action} (must be one of: {', '.join(_ACTIONS.keys())})")
        try:
            return handler(ctx, payload)
        except ValueError as e:
            logger.warning(f"session.manage validation error: {e}", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}
        except Exception as e:
            logger.exception("session.manage action failed", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Entry Point (when decorator not available)
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" not in globals():

    def session_manage(ctx: Any = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Fallback entry function for session.manage tool (no decorator)."""
        payload = payload or {}
        action = str(payload.get("action") or "read").strip().lower()
        handler = _ACTIONS.get(action)
        if not handler:
            raise ValueError(f"unsupported action: {action} (must be one of: {', '.join(_ACTIONS.keys())})")
        try:
            return handler(ctx, payload)
        except ValueError as e:
            logger.warning(f"session.manage validation error: {e}", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}
        except Exception as e:
            logger.exception("session.manage action failed", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}


# Aliases
invoke = session_manage
run = session_manage
handle = session_manage


def describe() -> dict[str, Any]:
    """Static descriptor for discovery/UX."""
    return {
        "name": "session.manage",
        "summary": "Session lifecycle with TTL + touch and pagination",
        "actions": list(_ACTIONS.keys()),
        "features": ["ttl_enforcement", "touch_refresh", "pagination"],
    }
