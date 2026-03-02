"""
MCP Tool: security.allowed_operations

List operations allowed for the current principal.

This tool provides a clear inventory of what the current user can and cannot do,
useful for answering questions like "Do I have permission to run write queries?"

Actions
-------
- list (default)
    Return list of allowed and disallowed operations.
    
    Payload:
      {
        "principal": {...}  # Principal dict from context
      }
    Returns:
      {
        "ok": true,
        "action": "list",
        "read_operations": ["MATCH", "RETURN", "WITH", "UNWIND", "CALL (read-only)"],
        "write_operations": [],  # Empty if not admin
        "admin_operations": [],  # Empty if not admin
        "can_execute_reads": true,
        "can_execute_writes": false,
        "can_manage_schema": false,
        "dangerous_queries_allowed": false,
        "restrictions": ["Write operations require admin role", "Schema changes require admin role"],
        "summary": "You have read-only access to the graph database"
      }

Notes
-----
- Requires tools:basic scope
- Provides clear guidance on permission boundaries
- Helps users understand what they can/cannot do
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
# Operation Definitions
# ─────────────────────────────────────────────────────────────────────────────

# Read-only operations (available to all authenticated users)
READ_OPERATIONS = [
    "MATCH",
    "RETURN",
    "WHERE",
    "WITH",
    "UNWIND",
    "ORDER BY",
    "SKIP",
    "LIMIT",
    "EXPLAIN",
    "PROFILE",
    "CALL (read-only procedures)",
]

# Write operations (require admin or write permission)
WRITE_OPERATIONS = [
    "CREATE",
    "MERGE",
    "SET",
    "REMOVE",
    "DELETE",
    "DETACH DELETE",
]

# Admin/schema operations (require admin role)
ADMIN_OPERATIONS = [
    "CREATE INDEX",
    "DROP INDEX",
    "CREATE CONSTRAINT",
    "DROP CONSTRAINT",
    "LOAD CSV",
]

# Dangerous operations (always require explicit approval or denied)
DANGEROUS_OPERATIONS = [
    "DROP DATABASE",
    "DROP GRAPH",
    "TERMINATE",
    "SHUTDOWN",
    "AUTH",
]


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

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


def _has_write_permission(principal: dict[str, Any] | None) -> bool:
    """Check if principal has write permission."""
    if not principal:
        return False
    
    # RBAC bypass
    if principal.get("rbac_enforced") is False:
        return True
    
    permissions = principal.get("permissions") or []
    scopes = principal.get("scopes") or []
    
    if isinstance(permissions, str):
        permissions = [permissions]
    if isinstance(scopes, str):
        scopes = scopes.split()
    
    write_indicators = [
        "tools:all",
        "tools:write",
        "graph:write",
        "admin:all",
    ]
    
    return any(
        perm in permissions or perm in scopes
        for perm in write_indicators
    )


def _build_restrictions(
    can_write: bool,
    can_admin: bool,
) -> list[str]:
    """Build list of restrictions for non-privileged users."""
    restrictions = []
    
    if not can_write:
        restrictions.append("Write operations (CREATE, SET, DELETE) require admin role")
    
    if not can_admin:
        restrictions.append("Schema changes (CREATE INDEX, DROP INDEX) require admin role")
    
    restrictions.append("Dangerous operations (DROP DATABASE) are never allowed via this interface")
    restrictions.append("Heavy queries (unbounded traversals) require LIMIT or EXPLAIN")
    
    return restrictions


def _build_summary(
    can_read: bool,
    can_write: bool,
    can_admin: bool,
) -> str:
    """Build a human-readable summary."""
    if can_admin:
        return "You have full administrative access including schema management"
    elif can_write:
        return "You have read and write access to the graph database"
    elif can_read:
        return "You have read-only access to the graph database"
    else:
        return "You have limited or no access to the graph database"


# ─────────────────────────────────────────────────────────────────────────────
# Action Handlers
# ─────────────────────────────────────────────────────────────────────────────

def _act_list(payload: dict[str, Any]) -> dict[str, Any]:
    """List allowed operations for the principal."""
    principal = payload.get("principal") or {}
    
    # Determine access levels
    is_admin = _is_admin(principal)
    can_write = _has_write_permission(principal) or is_admin
    
    # Build operation lists
    allowed_read = list(READ_OPERATIONS)
    allowed_write = list(WRITE_OPERATIONS) if can_write else []
    allowed_admin = list(ADMIN_OPERATIONS) if is_admin else []
    
    # Dangerous operations are NEVER allowed via normal interface
    # (even admins must use a special escape hatch)
    allowed_dangerous = []
    
    # Build response
    restrictions = _build_restrictions(can_write, is_admin)
    summary = _build_summary(True, can_write, is_admin)
    
    return {
        "ok": True,
        "action": "list",
        "read_operations": allowed_read,
        "write_operations": allowed_write,
        "admin_operations": allowed_admin,
        "dangerous_operations": allowed_dangerous,
        "can_execute_reads": True,  # Always true for authenticated users
        "can_execute_writes": can_write,
        "can_manage_schema": is_admin,
        "dangerous_queries_allowed": False,  # Always false
        "restrictions": restrictions,
        "summary": summary,
        "is_admin": is_admin,
    }


def _act_check(payload: dict[str, Any]) -> dict[str, Any]:
    """Check if a specific operation is allowed."""
    principal = payload.get("principal") or {}
    operation = (payload.get("operation") or "").upper().strip()
    
    if not operation:
        raise ValueError("'operation' is required for action 'check'")
    
    is_admin = _is_admin(principal)
    can_write = _has_write_permission(principal) or is_admin
    
    # Determine if operation is allowed
    allowed = False
    reason = "Unknown operation"
    
    if operation in READ_OPERATIONS or operation.startswith("MATCH") or operation.startswith("RETURN"):
        allowed = True
        reason = "Read operations are allowed for all authenticated users"
    elif operation in WRITE_OPERATIONS or operation.startswith("CREATE") or operation.startswith("DELETE"):
        allowed = can_write
        reason = "Allowed for admin/write users" if allowed else "Write operations require admin role"
    elif operation in ADMIN_OPERATIONS or "INDEX" in operation or "CONSTRAINT" in operation:
        allowed = is_admin
        reason = "Allowed for admin users" if allowed else "Schema operations require admin role"
    elif operation in DANGEROUS_OPERATIONS or "DROP DATABASE" in operation or "SHUTDOWN" in operation:
        allowed = False
        reason = "Dangerous operations are not allowed via this interface"
    else:
        # Unknown operation - default to read-only check
        allowed = True
        reason = "Unknown operation; assuming read-only"
    
    return {
        "ok": True,
        "action": "check",
        "operation": operation,
        "allowed": allowed,
        "reason": reason,
        "is_admin": is_admin,
        "can_write": can_write,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

@mcp_tool(tool_name="security.allowed_operations", required_scope="tools:basic")
def invoke(
    ctx: ToolContext | dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """
    List operations allowed for the current principal.
    
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
    
    action = payload.get("action", "list")
    
    if action == "list":
        return _act_list(payload)
    elif action == "check":
        return _act_check(payload)
    
    # Default to list for any unknown action
    return _act_list(payload)


# Back-compat aliases
run = invoke
handle = invoke
