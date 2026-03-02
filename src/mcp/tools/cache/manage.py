"""
MCP Tool: cache.manage

Simple cache operations with Redis backend (when available) and an
in-memory fallback. Namespaces all keys by tenant.

Supported actions
-----------------
- get:
    payload: { "key": str, "tenant"?: str }
    returns: { ok, action:"get", key, value, backend }

- set:
    payload: { "key": str, "value": any, "ttl"?: int, "tenant"?: str }
    returns: { ok, action:"set", key, ttl, set:bool }
    **P6 Feature**: TTL policy enforcement - validates TTL is within allowed range.

- delete:
    payload: { "key": str, "tenant"?: str }
    returns: { ok, action:"delete", key, deleted:bool }

- keys:
    payload: { "pattern"?: str, "tenant"?: str }
    returns: { ok, action:"keys", pattern, keys:[...] }
    **P6 Feature**: Pattern matching for key discovery.

Notes
-----
- **P6 Feature**: TTL policy enforcement - non-session cache items must have TTL.
- Keys are automatically namespaced by tenant.
- Uses Redis when available; falls back to in-memory store with TTL.
"""

from __future__ import annotations

import fnmatch
import os
import time
from contextlib import suppress
from typing import Any

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

# ── Redis adapter (optional) ──────────────────────────────────────────────────
_REDIS_OK = False
with suppress(Exception):
    from src.adapters import redis as redis_adapt  # type: ignore

    _REDIS_OK = bool(redis_adapt.redis_available())

# ── Tenancy namespacing (optional) ────────────────────────────────────────────
with suppress(Exception):
    from src.security.tenants import get_current_tenant, tenantize_key  # type: ignore
if "tenantize_key" not in globals():

    def tenantize_key(key: str, tenant_id: str | None = None) -> str:  # type: ignore
        return f"t:{(tenant_id or 'global')}:{key}"


if "get_current_tenant" not in globals():

    def get_current_tenant() -> str | None:  # type: ignore
        return None


# ── TTL Policy Settings ───────────────────────────────────────────────────────
DEFAULT_CACHE_TTL = int(os.getenv("DEFAULT_CACHE_TTL", "3600"))  # 1 hour
MAX_CACHE_TTL = int(os.getenv("MAX_CACHE_TTL", "86400"))  # 24 hours

# ── In-memory fallback store with TTL ─────────────────────────────────────────
_MEM: dict[str, tuple[str, int | None]] = {}


def _mem_set(key: str, value: str, ttl: int | None = None) -> None:
    exp = int(time.time()) + int(ttl) if ttl else None
    _MEM[key] = (value, exp)


def _mem_get(key: str) -> str | None:
    val = _MEM.get(key)
    if not val:
        return None
    v, exp = val
    if exp is not None and exp <= int(time.time()):
        _MEM.pop(key, None)
        return None
    return v


def _mem_del(key: str) -> bool:
    return _MEM.pop(key, None) is not None


def _mem_keys(pattern: str) -> list[str]:
    now = int(time.time())
    stale = [k for k, (_, exp) in _MEM.items() if exp is not None and exp <= now]
    for k in stale:
        _MEM.pop(k, None)
    return [k for k in _MEM if fnmatch.fnmatch(k, pattern)]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _backend() -> str:
    return "redis" if _REDIS_OK else "memory"


def _ns_key(raw_key: str, tenant: str | None) -> str:
    return tenantize_key(raw_key, tenant)


def _enforce_ttl_policy(ttl: int | None, key: str) -> int:
    """
    Enforce TTL policy for cache items (P6 Feature).

    - Non-session cache items should have TTL
    - TTL must be within allowed range (0 < ttl <= MAX_CACHE_TTL)
    - Returns validated TTL or default
    """
    # Session keys exempt from policy
    if key.startswith("session:"):
        return ttl or DEFAULT_CACHE_TTL

    # Non-session keys should have TTL
    if ttl is None:
        logger.info(f"Applying default TTL to cache key: {key}")
        return DEFAULT_CACHE_TTL

    # Validate TTL range
    if ttl <= 0:
        raise ValueError(f"TTL must be positive, got {ttl}")
    if ttl > MAX_CACHE_TTL:
        raise ValueError(f"TTL exceeds maximum ({MAX_CACHE_TTL}s), got {ttl}")

    return ttl


# ─────────────────────────────────────────────────────────────────────────────
# P3 Internal Action Handlers
# ─────────────────────────────────────────────────────────────────────────────


def _act_get(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Get cached value by key."""
    key = payload.get("key")
    if not key:
        raise ValueError("cache.manage action 'get' requires 'key' parameter")

    tenant = payload.get("tenant") or get_current_tenant()
    nsk = _ns_key(str(key), tenant)

    value = None
    if _REDIS_OK:
        with suppress(Exception):
            value = redis_adapt.get(nsk)  # type: ignore[attr-defined]
    else:
        value = _mem_get(nsk)

    return {
        "ok": True,
        "action": "get",
        "key": key,
        "value": value,
        "backend": _backend(),
        "tenant": tenant or "global",
    }


def _act_set(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Set cached value with TTL policy enforcement (P6 Feature).

    Enforces TTL policy: non-session cache items should have TTL.
    """
    key = payload.get("key")
    if not key:
        raise ValueError("cache.manage action 'set' requires 'key' parameter")

    value = payload.get("value")
    if value is None:
        raise ValueError("cache.manage action 'set' requires 'value' parameter")

    tenant = payload.get("tenant") or get_current_tenant()
    nsk = _ns_key(str(key), tenant)

    # Enforce TTL policy
    raw_ttl = int(payload["ttl"]) if payload.get("ttl") not in (None, "") else None
    ttl = _enforce_ttl_policy(raw_ttl, str(key))

    if _REDIS_OK:
        with suppress(Exception):
            redis_adapt.set(nsk, str(value), ex=ttl)  # type: ignore[attr-defined]
    else:
        _mem_set(nsk, str(value), ttl=ttl)

    return {
        "ok": True,
        "action": "set",
        "key": key,
        "ttl": ttl,
        "set": True,
        "backend": _backend(),
        "tenant": tenant or "global",
    }


def _act_delete(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Delete cached value."""
    key = payload.get("key")
    if not key:
        raise ValueError("cache.manage action 'delete' requires 'key' parameter")

    tenant = payload.get("tenant") or get_current_tenant()
    nsk = _ns_key(str(key), tenant)

    deleted = False
    if _REDIS_OK:
        with suppress(Exception):
            deleted = bool(redis_adapt.delete(nsk))  # type: ignore[attr-defined]
    else:
        deleted = _mem_del(nsk)

    return {
        "ok": True,
        "action": "delete",
        "key": key,
        "deleted": deleted,
        "backend": _backend(),
        "tenant": tenant or "global",
    }


def _act_keys(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    List keys matching pattern (P6 Feature: pattern matching).

    Returns keys matching the pattern for the given tenant.
    """
    pattern = str(payload.get("pattern") or payload.get("key") or "*")
    tenant = payload.get("tenant") or get_current_tenant()
    nspat = _ns_key(pattern, tenant)

    matches = []
    if _REDIS_OK:
        with suppress(Exception):
            matches = redis_adapt.keys(nspat)  # type: ignore[attr-defined]
    else:
        matches = _mem_keys(nspat)

    # Strip namespace prefix
    prefix = f"t:{tenant or 'global'}:"
    logical = [m[len(prefix) :] if m.startswith(prefix) else m for m in matches]

    return {
        "ok": True,
        "action": "keys",
        "pattern": pattern,
        "keys": logical,
        "count": len(logical),
        "backend": _backend(),
        "tenant": tenant or "global",
    }


# ─────────────────────────────────────────────────────────────────────────────
# P3 Decorated Entry Point
# ─────────────────────────────────────────────────────────────────────────────

_ACTIONS = {
    "get": _act_get,
    "set": _act_set,
    "delete": _act_delete,
    "keys": _act_keys,
}

if "mcp_tool" in globals():

    @mcp_tool(tool_name="cache.manage", required_scope="tools:cache")
    def cache_manage(
        ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs: Any  # type: ignore
    ) -> dict[str, Any]:
        """Entry function for cache.manage tool (P3 pattern)."""
        payload = payload or {}
        action = str(payload.get("action", "get")).strip().lower()
        handler = _ACTIONS.get(action)
        if not handler:
            raise ValueError(f"unsupported action: {action} (must be one of: {', '.join(_ACTIONS.keys())})")
        try:
            return handler(ctx, payload)
        except ValueError as e:
            logger.warning(f"cache.manage validation error: {e}", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}
        except Exception as e:
            logger.exception("cache.manage action failed", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" not in globals():

    def cache_manage(ctx: Any = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Fallback entry function for cache.manage tool."""
        payload = payload or {}
        action = str(payload.get("action", "get")).strip().lower()
        handler = _ACTIONS.get(action)
        if not handler:
            raise ValueError(f"unsupported action: {action} (must be one of: {', '.join(_ACTIONS.keys())})")
        try:
            return handler(ctx, payload)
        except ValueError as e:
            logger.warning(f"cache.manage validation error: {e}", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}
        except Exception as e:
            logger.exception("cache.manage action failed", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}


# Aliases
invoke = cache_manage
run = cache_manage
handle = cache_manage


def describe() -> dict[str, Any]:
    """Static descriptor for discovery/UX."""
    return {
        "name": "cache.manage",
        "summary": "Cache operations with TTL policy enforcement",
        "actions": list(_ACTIONS.keys()),
        "features": ["ttl_policy", "pattern_matching", "tenant_namespacing"],
    }
