"""
MCP Tool: tenancy.manage

Lightweight tenancy administration surface for agents and operators.

Supported actions
-----------------
- list
    Payload: {}
    Returns: { ok, action, tenants:[...], tenant:{current} }

- current
    Payload: {}
    Returns: { ok, action, tenant:{current} }

- switch
    Payload: { "tenant_id": "..." }
    Switches active tenant context. Updates tenant's active flag and timestamp.

- create
    Payload: { "tenant_id": "...", "name"?, "metadata"? }
    Creates a new tenant. **Idempotent**: returns existing tenant if already exists.

- delete
    Payload: { "tenant_id": "...", "force"? }
    Soft delete by default (marks deleted_at). Use force=true for hard delete.
    **Soft delete guard**: prevents accidental deletion of active/default tenant.

- set-default
    Payload: { "tenant_id": "..." }
    Sets the default tenant used when no context is provided.

Notes
-----
- Idempotent create: calling create on existing tenant returns that tenant (no error)
- Soft delete guard: prevents deletion of default tenant or currently active tenant
- Active tenant context: switch updates active flag and timestamp automatically
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

# ── Logging (structlog-aware if configured) ───────────────────────────────────
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

# ── Settings ──────────────────────────────────────────────────────────────────
with suppress(Exception):
    from src.config import settings  # type: ignore
if "settings" not in globals():

    class _FallbackSettings:
        APP_ENV = "dev"
        DEFAULT_TENANT = "public"

    settings = _FallbackSettings()  # type: ignore

# ── Tenancy Manager (from security package if available) ──────────────────────
_TENANCY_AVAILABLE = True
with suppress(Exception):
    from src.security.tenants import TenancyManager as _SecTenancyManager  # type: ignore
if "_SecTenancyManager" not in globals():
    _TENANCY_AVAILABLE = False

# Global fallback manager instance (for tests)
_GLOBAL_FALLBACK_MANAGER: _InMemoryTenancyManager | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Fallback In-Memory Tenancy Manager
# ─────────────────────────────────────────────────────────────────────────────


class _InMemoryTenancyManager:
    """Fallback in-memory tenancy manager with soft delete support."""

    def __init__(self, default_tenant: str = "public") -> None:
        self._tenants: dict[str, dict[str, Any]] = {}
        self._current: str | None = None
        self._default: str | None = default_tenant
        # Ensure default tenant exists
        self.create_tenant(default_tenant, name="Default", metadata={"system": True})
        self.set_current_tenant(default_tenant)

    def list_tenants(self, include_deleted: bool = False) -> list[dict[str, Any]]:
        """List tenants, optionally including soft-deleted ones."""
        tenants = []
        for tid in sorted(self._tenants):
            t = self._tenants[tid]
            if not include_deleted and t.get("deleted_at"):
                continue  # Skip soft-deleted
            tenants.append(t)
        return tenants

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        """Get tenant by ID, None if not found or soft-deleted."""
        t = self._tenants.get(tenant_id)
        if t and not t.get("deleted_at"):
            return t
        return None

    def get_current_tenant(self) -> dict[str, Any] | None:
        """Get currently active tenant."""
        tid = self._current or self._default
        return self.get_tenant(tid) if tid else None

    def get_default_tenant(self) -> str | None:
        """Get default tenant ID."""
        return self._default

    def set_current_tenant(self, tenant_id: str) -> dict[str, Any]:
        """Switch to tenant. Raises KeyError if not found."""
        t = self.get_tenant(tenant_id)
        if not t:
            raise KeyError(f"tenant '{tenant_id}' not found or deleted")
        # Update previous tenant's active flag
        if self._current and self._current in self._tenants:
            self._tenants[self._current]["active"] = False
        # Set new tenant as active
        self._current = tenant_id
        self._tenants[tenant_id]["active"] = True
        self._tenants[tenant_id]["updated_at"] = _now_iso()
        return self._tenants[tenant_id]

    def set_default_tenant(self, tenant_id: str) -> None:
        """Set default tenant. Raises KeyError if not found."""
        t = self.get_tenant(tenant_id)
        if not t:
            raise KeyError(f"tenant '{tenant_id}' not found or deleted")
        self._default = tenant_id

    def create_tenant(
        self, tenant_id: str, name: str | None = None, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create tenant. Idempotent: returns existing if already exists."""
        # Idempotent: if exists and not deleted, return it
        existing = self.get_tenant(tenant_id)
        if existing:
            return existing

        # Check if soft-deleted (resurrect it)
        if tenant_id in self._tenants and self._tenants[tenant_id].get("deleted_at"):
            t = self._tenants[tenant_id]
            t["deleted_at"] = None
            t["updated_at"] = _now_iso()
            # Update name/metadata if provided
            if name:
                t["name"] = name
            if metadata:
                t["metadata"] = metadata
            return t

        # Create new tenant
        doc = {
            "id": tenant_id,
            "name": name or tenant_id,
            "metadata": metadata or {},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "active": False,
            "deleted_at": None,
        }
        self._tenants[tenant_id] = doc
        return doc

    def delete_tenant(self, tenant_id: str, force: bool = False) -> bool:
        """
        Delete tenant.

        Soft delete by default (marks deleted_at).
        Hard delete if force=True (removes from storage).

        Soft delete guard: prevents deletion of default or active tenant.
        """
        t = self._tenants.get(tenant_id)
        if not t:
            return False

        # Soft delete guard
        if tenant_id == self._default:
            raise ValueError("cannot delete default tenant (soft delete guard)")
        if tenant_id == self._current:
            raise ValueError("cannot delete currently active tenant (soft delete guard)")

        if force:
            # Hard delete
            self._tenants.pop(tenant_id)
        else:
            # Soft delete
            t["deleted_at"] = _now_iso()
            t["updated_at"] = _now_iso()
            t["active"] = False

        return True


# ─────────────────────────────────────────────────────────────────────────────
# Helper Utilities
# ─────────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _manager():
    """Return the active tenancy manager, preferring security.tenants."""
    global _GLOBAL_FALLBACK_MANAGER

    if _TENANCY_AVAILABLE:
        try:
            if hasattr(_SecTenancyManager, "instance"):
                return _SecTenancyManager.instance()  # type: ignore[attr-defined]
            return _SecTenancyManager()  # type: ignore[call-arg]
        except Exception as e:
            logger.warning(f"Falling back to in-memory tenancy manager: {e}")

    # Use global fallback manager for test persistence
    if _GLOBAL_FALLBACK_MANAGER is None:
        default_tid = getattr(settings, "DEFAULT_TENANT", "public")
        _GLOBAL_FALLBACK_MANAGER = _InMemoryTenancyManager(default_tenant=default_tid)

    return _GLOBAL_FALLBACK_MANAGER


def _tenant_to_dict(t: Any) -> dict[str, Any]:
    """Convert tenant object to dict."""
    if t is None:
        return {}
    if isinstance(t, dict):
        return t
    if is_dataclass(t):
        return asdict(t)
    # Generic object: extract common attributes
    out = {}
    for k in ("id", "name", "metadata", "created_at", "updated_at", "active", "deleted_at"):
        if hasattr(t, k):
            out[k] = getattr(t, k)
    if not out:
        out = {"repr": repr(t)}
    return out


# ─────────────────────────────────────────────────────────────────────────────
# P3 Internal Action Handlers
# ─────────────────────────────────────────────────────────────────────────────


def _act_list(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """List all tenants."""
    mgr = _manager()
    include_deleted = payload.get("include_deleted", False)

    with suppress(Exception):
        tenants = mgr.list_tenants(include_deleted=include_deleted)
        [_tenant_to_dict(t) for t in tenants]

    tenants_list = []
    with suppress(Exception):
        if hasattr(mgr, "list_tenants"):
            items = mgr.list_tenants()
            tenants_list = [_tenant_to_dict(x) for x in items]

    current = {}
    with suppress(Exception):
        t = mgr.get_current_tenant()
        current = _tenant_to_dict(t)

    default = None
    with suppress(Exception):
        default = mgr.get_default_tenant()

    return {
        "ok": True,
        "action": "list",
        "tenants": tenants_list,
        "tenant": current,
        "default_tenant": default,
    }


def _act_current(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Get current tenant."""
    mgr = _manager()

    current = {}
    with suppress(Exception):
        t = mgr.get_current_tenant()
        current = _tenant_to_dict(t)

    return {
        "ok": True,
        "action": "current",
        "tenant": current,
    }


def _act_switch(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Switch active tenant context."""
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise ValueError("tenant_id is required")

    mgr = _manager()

    # Get previous tenant
    prev = {}
    with suppress(Exception):
        t = mgr.get_current_tenant()
        prev = _tenant_to_dict(t)

    # Switch to new tenant
    t = mgr.set_current_tenant(tenant_id)

    return {
        "ok": True,
        "action": "switch",
        "tenant": _tenant_to_dict(t),
        "previous": prev,
    }


def _act_create(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Create tenant (idempotent).

    If tenant already exists, returns it without error.
    If tenant was soft-deleted, resurrects it.
    """
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise ValueError("tenant_id is required")

    name = payload.get("name")
    metadata = payload.get("metadata") or {}

    mgr = _manager()
    t = mgr.create_tenant(tenant_id, name=name, metadata=metadata)

    return {
        "ok": True,
        "action": "create",
        "tenant": _tenant_to_dict(t),
        "idempotent": True,  # Signal that this operation is idempotent
    }


def _act_delete(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Delete tenant with soft delete guard.

    Soft delete by default (marks deleted_at).
    Hard delete if force=true.

    Soft delete guard prevents deletion of:
    - Default tenant
    - Currently active tenant
    """
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise ValueError("tenant_id is required")

    force = payload.get("force", False)

    mgr = _manager()
    ok = mgr.delete_tenant(tenant_id, force=force)

    return {
        "ok": True,
        "action": "delete",
        "deleted": ok,
        "soft_delete": not force,
    }


def _act_set_default(ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Set default tenant."""
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise ValueError("tenant_id is required")

    mgr = _manager()
    mgr.set_default_tenant(tenant_id)

    return {
        "ok": True,
        "action": "set-default",
        "default_tenant": tenant_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# P3 Decorated Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" in globals():

    @mcp_tool(tool_name="tenancy.manage", required_scope="tools:admin")
    def tenancy_manage(
        ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs: Any  # type: ignore
    ) -> dict[str, Any]:
        """
        Entry function for tenancy.manage tool (P3 pattern).

        Args:
            ctx: Tool execution context with principal, tenant, trace_id
            payload: Optional dict with "action" and action-specific params
            **kwargs: Additional arguments (ignored)

        Returns:
            Action result dict with ok, action, and action-specific data
        """
        payload = payload or {}
        action = str(payload.get("action", "list")).strip().lower()

        if action not in {"list", "current", "switch", "create", "delete", "set-default"}:
            raise ValueError("action must be one of: list, current, switch, create, delete, set-default")

        try:
            if action == "list":
                return _act_list(ctx, payload)
            elif action == "current":
                return _act_current(ctx, payload)
            elif action == "switch":
                return _act_switch(ctx, payload)
            elif action == "create":
                return _act_create(ctx, payload)
            elif action == "delete":
                return _act_delete(ctx, payload)
            else:  # set-default
                return _act_set_default(ctx, payload)
        except ValueError as e:
            # Validation/guard errors
            logger.warning(f"tenancy.manage validation error: {e}", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
            }
        except Exception as e:
            logger.exception("tenancy.manage action failed", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
            }


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Entry Point (when decorator not available)
# ─────────────────────────────────────────────────────────────────────────────

if "mcp_tool" not in globals():

    def tenancy_manage(ctx: Any = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """
        Fallback entry function for tenancy.manage tool (no decorator).
        """
        payload = payload or {}
        action = str(payload.get("action", "list")).strip().lower()

        if action not in {"list", "current", "switch", "create", "delete", "set-default"}:
            raise ValueError("action must be one of: list, current, switch, create, delete, set-default")

        try:
            if action == "list":
                return _act_list(ctx, payload)
            elif action == "current":
                return _act_current(ctx, payload)
            elif action == "switch":
                return _act_switch(ctx, payload)
            elif action == "create":
                return _act_create(ctx, payload)
            elif action == "delete":
                return _act_delete(ctx, payload)
            else:  # set-default
                return _act_set_default(ctx, payload)
        except ValueError as e:
            logger.warning(f"tenancy.manage validation error: {e}", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
            }
        except Exception as e:
            logger.exception("tenancy.manage action failed", extra={"action": action})
            return {
                "ok": False,
                "action": action,
                "error": str(e),
            }


# ── Backward compatibility aliases ───────────────────────────────────────────
invoke = tenancy_manage
run = tenancy_manage
handle = tenancy_manage


def describe() -> dict[str, Any]:
    """Static descriptor for discovery/UX."""
    return {
        "name": "tenancy.manage",
        "summary": "Tenant administration with idempotent create and soft delete guard",
        "actions": ["list", "current", "switch", "create", "delete", "set-default"],
        "features": ["idempotent_create", "soft_delete_guard", "active_context_tracking"],
    }
