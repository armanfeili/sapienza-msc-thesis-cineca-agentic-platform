"""
MCP Tool: agent.context

Assemble a lightweight execution context for agents, including (optionally)
available MCP tools, model inventory, loaded policies, tenancy, and a few
runtime facts. This is meant for orchestration layers that want a quick,
structured snapshot to ground planning and capability selection.

Actions
-------
- assemble (default):
    Payload (all optional; booleans default shown):
    {
      "include_tools": true,
      "include_models": true,
      "include_policies": false,
      "include_env": true,
      "include_tenant": true,
      "include_user_scopes": true
    }

    **P6 Features**:
    - Context counts tracking (tools, models, etc.)
    - Caching with invalidation (10-second TTL)
"""

from __future__ import annotations

import os
import platform
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

# ── App version ───────────────────────────────────────────────────────────────
with suppress(Exception):
    from src import __version__ as _APP_VERSION  # type: ignore[attr-defined]
if "_APP_VERSION" not in globals():
    _APP_VERSION = "0.1.0"

# ── MCP manifest & policies ───────────────────────────────────────────────────
with suppress(Exception):
    from src.mcp import (  # type: ignore
        describe as mcp_describe,
        get_manifest,
        get_policies,
        list_tool_names,
    )
if "get_manifest" not in globals():

    def get_manifest(**_: Any) -> dict[str, Any]:  # type: ignore
        return {"tools": [], "categories": []}

    def get_policies(**_: Any) -> dict[str, Any]:  # type: ignore
        return {}

    def list_tool_names(_: dict[str, Any] | None = None) -> list[str]:  # type: ignore
        return []

    def mcp_describe() -> dict[str, Any]:  # type: ignore
        return {"tools_count": 0, "tool_names": []}


# ── Models ────────────────────────────────────────────────────────────────────
with suppress(Exception):
    from src.adapters.llm import (  # type: ignore
        get_default_model as _llm_default,
        list_models as _llm_list_models,
    )
if "_llm_list_models" not in globals():

    def _llm_list_models() -> list[str]:
        return []

    def _llm_default() -> str | None:
        return None


# ── Security helpers ──────────────────────────────────────────────────────────
with suppress(Exception):
    from src.security.policies_loader import get_scopes_for_role  # type: ignore
if "get_scopes_for_role" not in globals():

    def get_scopes_for_role(role: str) -> list[str]:  # type: ignore
        return []


with suppress(Exception):
    from src.security.tenants import get_current_tenant  # type: ignore
if "get_current_tenant" not in globals():

    def get_current_tenant() -> str | None:  # type: ignore
        return None


with suppress(Exception):
    from src.security.rate_limit import get_backend as _rl_backend  # type: ignore
if "_rl_backend" not in globals():

    def _rl_backend() -> str:
        return "memory"


with suppress(Exception):
    from src.security.audit import audit_access  # type: ignore
if "audit_access" not in globals():

    def audit_access(**_: Any) -> None:  # type: ignore
        return


with suppress(Exception):
    from src.security.pii_scrubber import scrub_dict  # type: ignore
if "scrub_dict" not in globals():

    def scrub_dict(d: dict[str, Any], mode: str | None = None) -> dict[str, Any]:  # type: ignore
        return d


# ─────────────────────────────────────────────────────────────────────────────
# P6 Feature: Context caching with invalidation (10-second TTL)
# ─────────────────────────────────────────────────────────────────────────────
_CONTEXT_CACHE: dict[str, Any] | None = None
_CONTEXT_CACHE_TIME: float = 0
_CONTEXT_CACHE_TTL: float = 10.0  # seconds


def invalidate_cache() -> None:
    """Invalidate context cache (P6 Feature: cache invalidation)."""
    global _CONTEXT_CACHE, _CONTEXT_CACHE_TIME
    _CONTEXT_CACHE = None
    _CONTEXT_CACHE_TIME = 0
    logger.debug("Agent context cache invalidated")


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _collect_env() -> dict[str, Any]:
    """Collect environment metadata."""
    return {
        "app_version": _APP_VERSION,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pid": os.getpid(),
        "time": int(time.time()),
    }


def _collect_tools() -> dict[str, Any]:
    """
    Collect MCP tools metadata.

    P6 Feature: Returns context counts for tracking.
    """
    manifest = get_manifest()
    names = list_tool_names(manifest)
    cats = manifest.get("categories") or []
    return {
        "count": len(names),  # P6: Context count
        "names": names,
        "categories": cats,
        "categories_count": len(cats),  # P6: Context count
        "manifest": {
            "id": manifest.get("id"),
            "version": manifest.get("version"),
            "schema_version": manifest.get("schema_version"),
        },
        "info": mcp_describe(),
    }


def _collect_models() -> dict[str, Any]:
    """
    Collect LLM models metadata.

    P6 Feature: Returns context counts for tracking.
    """
    models = _llm_list_models() or []
    default = _llm_default()
    return {
        "count": len(models),  # P6: Context count
        "default": default,
        "names": models,
    }


def _collect_policies() -> dict[str, Any]:
    """Collect policy metadata."""
    pol = get_policies() or {}
    guards = pol.get("guards") or {}
    roles = pol.get("roles") or {}
    ratelimit = pol.get("ratelimit") or {}
    tenancy = pol.get("tenancy") or {}
    return {
        "version": pol.get("version"),
        "guards": guards,
        "roles": roles,
        "ratelimit": ratelimit,
        "tenancy": tenancy,
    }


def _summarize_user(raw_user: Any, include_scopes: bool) -> dict[str, Any]:
    """
    Best-effort, privacy-aware user summary.
    Accepts dict-like or simple object with attributes.
    """
    if raw_user is None:
        return {}

    def _get(k: str) -> str | None:
        v = raw_user.get(k) if isinstance(raw_user, dict) else getattr(raw_user, k, None)
        return str(v) if v is not None else None

    username = _get("username") or _get("name") or _get("sub")
    email = _get("email")
    role = _get("role") or "user"

    summary = {"username": username, "email": email, "role": role}
    summary = scrub_dict(summary)

    if include_scopes and role:
        with suppress(Exception):
            summary["scopes"] = get_scopes_for_role(role) or []

    return {k: v for k, v in summary.items() if v not in (None, "", [], {})}


# ─────────────────────────────────────────────────────────────────────────────
# P3 Internal Action Handler
# ─────────────────────────────────────────────────────────────────────────────


def _act_assemble(ctx: Any, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """
    Assemble agent execution context.

    P6 Features:
    - Context counts tracking (tools count, models count, etc.)
    - Caching with 10-second TTL
    """
    global _CONTEXT_CACHE, _CONTEXT_CACHE_TIME

    include_tools = bool(payload.get("include_tools", True))
    include_models = bool(payload.get("include_models", True))
    include_policies = bool(payload.get("include_policies", False))
    include_env = bool(payload.get("include_env", True))
    include_tenant = bool(payload.get("include_tenant", True))
    include_user_scopes = bool(payload.get("include_user_scopes", True))

    user = kwargs.get("user") or payload.get("user")

    # P6 Feature: Use cached context if fresh (10s TTL)
    now = time.time()
    cache_key = f"{include_tools}:{include_models}:{include_policies}"

    if _CONTEXT_CACHE and (now - _CONTEXT_CACHE_TIME) <= _CONTEXT_CACHE_TTL:
        if _CONTEXT_CACHE.get("cache_key") == cache_key:
            logger.debug("Using cached agent context")
            result = _CONTEXT_CACHE.copy()
            result["time"] = int(now)
            result["cached"] = True

            # Update user if provided
            if user is not None:
                result["agent_context"]["user"] = _summarize_user(user, include_scopes=include_user_scopes)

            return result

    # Build fresh context
    ctx_data: dict[str, Any] = {
        "ok": True,
        "time": int(now),
        "cached": False,
        "cache_key": cache_key,
        "agent_context": {},
    }

    if include_env:
        ctx_data["agent_context"]["env"] = _collect_env()
        ctx_data["agent_context"]["rate_limit_backend"] = _rl_backend()

    if include_tools:
        ctx_data["agent_context"]["tools"] = _collect_tools()

    if include_models:
        ctx_data["agent_context"]["models"] = _collect_models()

    if include_policies:
        ctx_data["agent_context"]["policies"] = _collect_policies()

    if include_tenant:
        with suppress(Exception):
            ctx_data["agent_context"]["tenant"] = get_current_tenant()

    ctx_data["agent_context"]["user"] = _summarize_user(user, include_scopes=include_user_scopes)

    # P6 Feature: Cache the result
    _CONTEXT_CACHE = ctx_data.copy()
    _CONTEXT_CACHE_TIME = now

    # Audit
    with suppress(Exception):
        principal = None
        if isinstance(user, dict):
            principal = user.get("username") or user.get("email") or user.get("sub")
        else:
            principal = getattr(user, "username", None) or getattr(user, "email", None) or getattr(user, "sub", None)
        audit_access(
            principal=principal,
            resource="mcp.tools.agent.context",
            action="read",
            allowed=True,
            reason=None,
            attributes={
                "include_tools": include_tools,
                "include_models": include_models,
                "include_policies": include_policies,
            },
        )

    return ctx_data


# ─────────────────────────────────────────────────────────────────────────────
# P3 Decorated Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" in globals():

    @mcp_tool(tool_name="agent.context", required_scope="tools:agent")
    def agent_context(
        ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs: Any  # type: ignore
    ) -> dict[str, Any]:
        """Entry function for agent.context tool (P3 pattern)."""
        payload = payload or {}
        try:
            return _act_assemble(ctx, payload, **kwargs)
        except Exception as e:
            logger.exception("agent.context failed")
            return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" not in globals():

    def agent_context(ctx: Any = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Fallback entry function for agent.context tool."""
        payload = payload or {}
        try:
            return _act_assemble(ctx, payload, **kwargs)
        except Exception as e:
            logger.exception("agent.context failed")
            return {"ok": False, "error": str(e)}


# Aliases
invoke = agent_context
run = agent_context
handle = agent_context


def describe() -> dict[str, Any]:
    """Static descriptor for discovery/UX."""
    return {
        "name": "agent.context",
        "summary": "Assemble agent execution context with caching",
        "features": ["context_counts", "caching", "cache_invalidation"],
    }
