"""
MCP Tool: user.profile

Lightweight profile/preferences store for users.
Backed by Redis when available; falls back to in-process memory.

Supported actions
-----------------
- get:
    payload: { "user_id": str }
    returns: { ok, action:"get", profile:{...} }

- set:
    payload: { "user_id": str, "profile": {...} }
    returns: { ok, action:"set", profile:{...} }
    Replaces entire profile.

- update:
    payload: { "user_id": str, "patch": {...} }
    returns: { ok, action:"update", profile:{...} }
    **P6 Feature**: JSONB merge semantics - preserves existing keys.

- delete:
    payload: { "user_id": str }
    returns: { ok, action:"delete", deleted: bool }

Notes
-----
- **P6 Feature**: JSONB merge semantics for update action - merges patch into existing profile.
- **P6 Feature**: Input sanitation - validates profile/patch are dicts.
- Timestamps (`created_at`, `updated_at`) are ISO-8601 UTC strings.
- Profiles are simple JSON documents with recommended keys, but any additional JSON-serializable fields are accepted.
"""

from __future__ import annotations

import json
from contextlib import suppress
from datetime import UTC, datetime
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

# ── Redis (optional) ──────────────────────────────────────────────────────────
_redis = None
with suppress(Exception):
    from db.redis_cache.client import get_redis  # type: ignore

    _redis = get_redis()

# ── In-memory fallback store (per-process) ────────────────────────────────────
_MEMORY: dict[str, dict[str, Any]] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _key(user_id: str) -> str:
    return f"user:profile:{user_id}"


def _sanitize_dict(value: Any, name: str) -> dict[str, Any]:
    """Sanitize input to ensure it's a dict (P6 Feature: input sanitation)."""
    if not isinstance(value, dict):
        raise ValueError(f"`{name}` must be a dict/object, got {type(value).__name__}")
    return value


def _load_from_redis(key: str) -> dict[str, Any] | None:
    if not _redis:
        return None
    raw = _redis.get(key)  # type: ignore[attr-defined]
    if not raw:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception:
        logger.warning("Invalid JSON in redis for key=%s", key)
        return None


def _save_to_redis(key: str, data: dict[str, Any]) -> None:
    if not _redis:
        return
    _redis.set(key, json.dumps(data, ensure_ascii=False))  # type: ignore[attr-defined]


def _delete_from_redis(key: str) -> bool:
    if not _redis:
        return False
    try:
        return bool(_redis.delete(key))  # type: ignore[attr-defined]
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# P3 Internal Action Handlers
# ─────────────────────────────────────────────────────────────────────────────


def _act_get(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Get user profile."""
    user_id = str(payload.get("user_id") or "anonymous").strip() or "anonymous"
    key = _key(user_id)

    # Try redis first
    profile = None
    if _redis:
        profile = _load_from_redis(key)

    # Fallback to memory
    if profile is None:
        profile = _MEMORY.get(key)

    return {
        "ok": True,
        "action": "get",
        "profile": profile or {},
        "source": "redis" if (_redis and profile) else "memory",
    }


def _act_set(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Set (replace) user profile."""
    user_id = str(payload.get("user_id") or "anonymous").strip() or "anonymous"
    profile_obj = _sanitize_dict(payload.get("profile") or {}, "profile")

    key = _key(user_id)
    now = _now_iso()

    # Keep existing created_at if present
    existing = _MEMORY.get(key) or (_load_from_redis(key) if _redis else None)
    created_at = (existing or {}).get("created_at", now)

    # Build stored profile
    stored = {
        "user_id": user_id,
        "created_at": created_at,
        "updated_at": now,
        **profile_obj,
    }

    _MEMORY[key] = stored
    _save_to_redis(key, stored)

    return {"ok": True, "action": "set", "profile": stored}


def _act_update(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Update user profile with JSONB merge semantics (P6 Feature).

    Merges patch into existing profile, preserving existing keys.
    """
    user_id = str(payload.get("user_id") or "anonymous").strip() or "anonymous"
    patch = _sanitize_dict(payload.get("patch") or {}, "patch")

    key = _key(user_id)

    # Get current profile
    current = _MEMORY.get(key) or (_load_from_redis(key) if _redis else None)
    if not current:
        # Create new profile if doesn't exist
        current = {
            "user_id": user_id,
            "created_at": _now_iso(),
        }

    # JSONB merge: update preserves existing keys
    current["updated_at"] = _now_iso()
    current.update(patch)

    _MEMORY[key] = current
    _save_to_redis(key, current)

    return {"ok": True, "action": "update", "profile": current}


def _act_delete(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Delete user profile."""
    user_id = str(payload.get("user_id") or "anonymous").strip() or "anonymous"
    key = _key(user_id)

    # Delete from memory
    was_in_memory = _MEMORY.pop(key, None) is not None

    # Delete from redis
    redis_deleted = _delete_from_redis(key)

    deleted = was_in_memory or redis_deleted

    return {"ok": True, "action": "delete", "deleted": deleted, "user_id": user_id}


# ─────────────────────────────────────────────────────────────────────────────
# P3 Decorated Entry Point
# ─────────────────────────────────────────────────────────────────────────────

_ACTIONS = {
    "get": _act_get,
    "set": _act_set,
    "update": _act_update,
    "delete": _act_delete,
}

if "mcp_tool" in globals():

    @mcp_tool(tool_name="user.profile", required_scope="tools:user")
    def user_profile(
        ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs: Any  # type: ignore
    ) -> dict[str, Any]:
        """
        Entry function for user.profile tool (P3 pattern).

        Args:
            ctx: Tool execution context
            payload: Action payload
            **kwargs: Additional arguments (ignored)

        Returns:
            Action result dict
        """
        payload = payload or {}
        action = str(payload.get("action", "get")).strip().lower()
        handler = _ACTIONS.get(action)
        if not handler:
            raise ValueError(f"unsupported action: {action} (must be one of: {', '.join(_ACTIONS.keys())})")
        try:
            return handler(ctx, payload)
        except ValueError as e:
            logger.warning(f"user.profile validation error: {e}", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}
        except Exception as e:
            logger.exception("user.profile action failed", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Entry Point (when decorator not available)
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" not in globals():

    def user_profile(ctx: Any = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Fallback entry function for user.profile tool (no decorator)."""
        payload = payload or {}
        action = str(payload.get("action", "get")).strip().lower()
        handler = _ACTIONS.get(action)
        if not handler:
            raise ValueError(f"unsupported action: {action} (must be one of: {', '.join(_ACTIONS.keys())})")
        try:
            return handler(ctx, payload)
        except ValueError as e:
            logger.warning(f"user.profile validation error: {e}", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}
        except Exception as e:
            logger.exception("user.profile action failed", extra={"action": action})
            return {"ok": False, "action": action, "error": str(e)}


# Aliases
invoke = user_profile
run = user_profile
handle = user_profile


def describe() -> dict[str, Any]:
    """Static descriptor for discovery/UX."""
    return {
        "name": "user.profile",
        "summary": "User profile with JSONB merge and input sanitation",
        "actions": list(_ACTIONS.keys()),
        "features": ["jsonb_merge", "input_sanitation"],
    }
