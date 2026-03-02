"""
MCP Tool: security.describe_principal

Describe the current principal's identity, roles, permissions, and scopes.

This tool provides introspection capabilities for users to understand their
current access level and identity within the system.

Actions
-------
- describe (default)
    Return comprehensive information about the principal.
    
    Payload:
      {
        "principal": {...}  # Principal dict from context
      }
    Returns:
      {
        "ok": true,
        "action": "describe",
        "principal_id": "user@example.org",
        "email": "user@example.org",
        "tenant_id": "default",
        "roles": ["analyst", "viewer"],
        "permissions": ["tools:basic", "graph:read"],
        "scopes": ["tools:invoke:basic"],
        "is_admin": false,
        "is_service_account": false,
        "identity_summary": "Standard user with read-only graph access"
      }

Notes
-----
- Requires tools:basic scope (available to all authenticated users)
- Does not reveal sensitive information (tokens, secrets)
- Safe to call for permission introspection
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

# ── P0 Runtime Infrastructure ─────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.security.perm import infer_role_from_principal

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def _extract_principal_id(principal: dict[str, Any] | None) -> str | None:
    """Extract the primary identifier from a principal."""
    if not principal:
        return None
    return (
        principal.get("id")
        or principal.get("sub")
        or principal.get("user_id")
        or principal.get("email")
    )


def _is_admin(principal: dict[str, Any] | None) -> bool:
    """Check if principal has admin privileges."""
    if not principal:
        return False
    
    permissions = principal.get("permissions") or []
    roles = principal.get("roles") or []
    
    if isinstance(permissions, str):
        permissions = [permissions]
    if isinstance(roles, str):
        roles = [roles]
    
    return (
        "admin:all" in permissions
        or any(str(r).lower() == "admin" for r in roles)
    )


def _is_service_account(principal: dict[str, Any] | None) -> bool:
    """Check if principal appears to be a service account."""
    if not principal:
        return False
    
    # Check for service account indicators
    principal_id = _extract_principal_id(principal) or ""
    
    service_indicators = [
        "service",
        "machine",
        "bot",
        "system",
        "api-key",
        "client-credentials",
    ]
    
    id_lower = principal_id.lower()
    for indicator in service_indicators:
        if indicator in id_lower:
            return True
    
    # Check for explicit service flag
    if principal.get("is_service") or principal.get("service_account"):
        return True
    
    # Check grant type for machine tokens
    grant_type = principal.get("grant_type", "")
    if grant_type == "client_credentials":
        return True
    
    return False


def _build_identity_summary(
    principal: dict[str, Any] | None,
    is_admin: bool,
    is_service: bool,
) -> str:
    """Build a human-readable summary of the principal's identity."""
    if not principal:
        return "Anonymous user with no authenticated identity"
    
    parts = []
    
    if is_service:
        parts.append("Service account")
    elif is_admin:
        parts.append("Administrator")
    else:
        parts.append("Standard user")
    
    permissions = principal.get("permissions") or []
    if isinstance(permissions, str):
        permissions = [permissions]
    
    # Describe access level
    if "admin:all" in permissions:
        parts.append("with full administrative access")
    elif "tools:all" in permissions:
        parts.append("with full tool access")
    elif "tools:basic" in permissions:
        parts.append("with basic tool access")
    elif any("graph" in p for p in permissions):
        parts.append("with graph database access")
    else:
        parts.append("with limited access")
    
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Action Handlers
# ─────────────────────────────────────────────────────────────────────────────

def _act_describe(payload: dict[str, Any]) -> dict[str, Any]:
    """Describe the principal's identity and access."""
    principal = payload.get("principal") or {}
    
    # Normalize lists
    permissions = principal.get("permissions") or []
    roles = principal.get("roles") or []
    scopes = principal.get("scopes") or []
    
    if isinstance(permissions, str):
        permissions = [permissions]
    if isinstance(roles, str):
        roles = [roles]
    if isinstance(scopes, str):
        scopes = scopes.split()
    
    # Infer role if not explicitly set
    inferred_role = infer_role_from_principal(principal)
    if inferred_role and inferred_role not in roles:
        roles = list(roles) + [inferred_role]
    
    principal_id = _extract_principal_id(principal)
    admin = _is_admin(principal)
    service = _is_service_account(principal)
    summary = _build_identity_summary(principal, admin, service)
    
    return {
        "ok": True,
        "action": "describe",
        "principal_id": principal_id,
        "email": principal.get("email"),
        "tenant_id": principal.get("tenant_id"),
        "roles": sorted(set(roles)),
        "permissions": sorted(set(permissions)),
        "scopes": sorted(set(scopes)),
        "is_admin": admin,
        "is_service_account": service,
        "inferred_role": inferred_role,
        "identity_summary": summary,
        "rbac_enforced": principal.get("rbac_enforced", True),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

@mcp_tool(tool_name="security.describe_principal", required_scope="tools:basic")
def invoke(
    ctx: ToolContext | dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """
    Describe the current principal's identity and permissions.
    
    Supports multiple calling conventions:
    1. invoke(ctx, payload) - traditional MCP tool signature
    2. invoke(payload) - when called via router
    3. invoke(ctx, payload={}, **kwargs) - when called via MCP wrapper
    """
    # Handle different calling conventions
    if payload is None or (isinstance(payload, dict) and not payload):
        if kwargs:
            payload = kwargs
        elif isinstance(ctx, dict) and not isinstance(ctx, ToolContext):
            payload = ctx
        else:
            payload = {}
    else:
        payload = dict(payload)
    
    # If principal not in payload, try to get from context
    if "principal" not in payload and ctx and isinstance(ctx, ToolContext):
        with suppress(Exception):
            payload["principal"] = getattr(ctx, "principal", None)
    
    action = payload.get("action", "describe")
    
    if action == "describe":
        return _act_describe(payload)
    
    # Default to describe for any unknown action
    return _act_describe(payload)


# Back-compat aliases
run = invoke
handle = invoke
