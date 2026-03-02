"""
Multi-tenancy helpers.

What this module provides
-------------------------
- Canonical **tenant selection** from FastAPI `Request` and/or `user` objects.
- A per-request **context variable** so lower layers can fetch the current tenant
  without threading it through every call.
- Simple **allowlist enforcement** (deny unknown tenants when configured).
- Tiny helpers for namespacing cache/DB keys.

Configuration (all optional; safe defaults)
-------------------------------------------
- TENANCY_ENABLED: bool (default: False)
- TENANCY_DEFAULT: str | None (default: None)
- TENANT_HEADER: str (default: "X-Tenant-Id")
- TENANT_QUERY_PARAM: str (default: "tenant")   # also recognizes "tid", "tenant_id"
- TENANCY_ALLOWED: list[str] | comma-separated str | "*" (default: empty = allow any)

Usage
-----
    from src.security.tenants import require_tenant, get_current_tenant, tenantize_key

    @router.get("/items", dependencies=[Depends(require_tenant())])
    async def list_items(tenant: str = Depends(get_current_tenant)):
        key = tenantize_key("items:list", tenant)
        ...

Notes
-----
- If TENANCY_ENABLED is False, selection functions return either the provided
  tenant, or TENANCY_DEFAULT, or None; enforcement is a no-op.
- Tenant identifiers are validated by a conservative regex: ^[A-Za-z][A-Za-z0-9._-]{0,63}$
"""

from __future__ import annotations

import contextvars
import re
from dataclasses import dataclass
from typing import Any

# FastAPI imports are optional at import-time to avoid hard dependency here.
try:  # pragma: no cover
    from fastapi import Depends, HTTPException, Request, status
except Exception:  # pragma: no cover
    Request = Any  # type: ignore
    def Depends(x):
        return x  # type: ignore
    HTTPException = Exception  # type: ignore
    status = type("S", (), {"HTTP_400_BAD_REQUEST": 400, "HTTP_403_FORBIDDEN": 403})()  # type: ignore

from contextlib import suppress

from src.config import settings

from .audit import audit_policy_decision

# Logging (structlog if available)
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Context
# ──────────────────────────────────────────────────────────────────────────────
_current_tenant: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_tenant", default=None)


def set_current_tenant(tenant_id: str | None) -> None:
    """Set the current tenant in a context variable."""
    _current_tenant.set(tenant_id)


def get_current_tenant() -> str | None:
    """Return the current tenant id from context (or None)."""
    return _current_tenant.get()


# ──────────────────────────────────────────────────────────────────────────────
# Config helpers & validation
# ──────────────────────────────────────────────────────────────────────────────
TENANT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")


def _enabled() -> bool:
    return bool(getattr(settings, "TENANCY_ENABLED", False))


def _default_tenant() -> str | None:
    t = getattr(settings, "TENANCY_DEFAULT", None)
    return str(t) if t else None


def _header_name() -> str:
    return str(getattr(settings, "TENANT_HEADER", "X-Tenant-Id"))


def _query_param() -> str:
    return str(getattr(settings, "TENANT_QUERY_PARAM", "tenant"))


def _allowed_set() -> set[str] | None:
    """
    Parse TENANCY_ALLOWED from settings; returns:
      - None   → no restriction (allow any)
      - {"*"}  → wildcard (allow any)
      - set(...) of allowed tenants
    """
    raw = getattr(settings, "TENANCY_ALLOWED", None)
    vals: list[str] = []
    if raw is None:
        return set()  # empty set means "no explicit allowlist configured"
    if isinstance(raw, (list, tuple, set)):
        vals = [str(x).strip() for x in raw if str(x).strip()]
    else:
        # split on comma/semicolon/space
        vals = [v.strip() for v in str(raw).replace(";", ",").replace(" ", ",").split(",") if v.strip()]
    if not vals:
        return set()
    if any(v == "*" for v in vals):
        return {"*"}
    # Normalize to lowercase for consistent comparisons
    return {v.lower() for v in vals}


def _is_allowed(tenant_id: str) -> bool:
    allowed = _allowed_set()
    if allowed is None or "*" in allowed:
        return True
    if len(allowed) == 0:
        return True  # no allowlist configured
    return tenant_id.lower() in allowed


def _normalize(tenant_id: str) -> str:
    return tenant_id.strip()


def _validate(tenant_id: str) -> None:
    if not tenant_id:
        raise ValueError("tenant id must not be empty")
    if not TENANT_RE.fullmatch(tenant_id):
        raise ValueError("tenant id must match ^[A-Za-z][A-Za-z0-9._-]{0,63}$")


# ──────────────────────────────────────────────────────────────────────────────
# Extraction
# ──────────────────────────────────────────────────────────────────────────────
def _extract_from_user(user: Any) -> str | None:
    for key in ("tenant_id", "tid", "tenant", "org", "organization"):
        # attr or dict key
        if hasattr(user, key) and getattr(user, key):
            return str(getattr(user, key))
        if isinstance(user, dict) and user.get(key):
            return str(user[key])
    # Token-like dict nested?
    if isinstance(user, dict):
        token = user.get("token") or user.get("claims") or {}
        if isinstance(token, dict):
            for key in ("tid", "tenant", "tenant_id", "org"):
                if token.get(key):
                    return str(token[key])
    return None


def _extract_from_request(request: Request) -> str | None:  # type: ignore[valid-type]
    # 1) Header
    header = request.headers.get(_header_name()) if hasattr(request, "headers") else None
    if header:
        return str(header)

    # 2) Query param (supports aliases)
    qp = None
    if hasattr(request, "query_params"):
        qp = (
            request.query_params.get(_query_param())
            or request.query_params.get("tid")
            or request.query_params.get("tenant_id")
        )
    if qp:
        return str(qp)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Selection / enforcement
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TenantContext:
    id: str | None
    source: str  # "header" | "query" | "user" | "default" | "none"
    allowed: bool


def select_tenant(
    request: Request | None = None,  # type: ignore[valid-type]
    user: Any | None = None,
    *,
    fallback_to_default: bool = True,
    set_context: bool = True,
) -> TenantContext:
    """
    Resolve the tenant id using (in order): header → query → user → default.
    Validates the identifier and applies allowlist if configured.

    Returns a TenantContext; may set the contextvar if set_context=True.
    """
    tenant_id: str | None = None
    source = "none"

    if request is not None:
        with suppress(Exception):
            t = _extract_from_request(request)
            if t:
                tenant_id, source = t, "header" if request.headers.get(_header_name(), None) else "query"

    if not tenant_id and user is not None:
        with suppress(Exception):
            t = _extract_from_user(user)
            if t:
                tenant_id, source = t, "user"

    if not tenant_id and fallback_to_default:
        tenant_id, source = _default_tenant(), "default" if _default_tenant() else "none"

    # Normalize & validate (only if present)
    if tenant_id:
        tenant_id = _normalize(tenant_id)
        try:
            _validate(tenant_id)
        except ValueError as e:
            # Bad tenant ID -> 400 in enforce mode, but here we only return context
            if set_context:
                set_current_tenant(None)
            # Audit as deny
            with suppress(Exception):
                audit_policy_decision(
                    policy="tenancy",
                    subject=getattr(user, "username", None) if user else None,
                    action="select",
                    resource="tenant",
                    allowed=False,
                    reason=f"invalid tenant id: {e}",
                    attributes={"source": source, "value": tenant_id},
                )
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"message": str(e)})

    allowed = True
    if tenant_id:
        # Only enforce allowlist when tenancy is enabled
        allowed = _is_allowed(tenant_id) if _enabled() else True

    if set_context:
        set_current_tenant(tenant_id)

    # Audit decision (best effort)
    with suppress(Exception):
        audit_policy_decision(
            policy="tenancy",
            subject=getattr(user, "username", None) if user else None,
            action="select",
            resource=f"tenant:{tenant_id or 'none'}",
            allowed=allowed or not _enabled(),
            reason=None if allowed else "tenant not in allowlist",
            attributes={"enabled": _enabled(), "source": source},
        )

    return TenantContext(id=tenant_id, source=source, allowed=allowed or not _enabled())


def enforce_tenant(
    request: Request,  # type: ignore[valid-type]
    user: Any | None = None,
) -> str:
    """
    Resolve and enforce tenant selection. Raises 403 if TENANCY_ENABLED and the
    tenant is not allowed; raises 400 for invalid IDs. Returns the tenant id
    (or empty string if none).
    """
    ctx = select_tenant(request, user=user, fallback_to_default=True, set_context=True)
    if _enabled() and ctx.id and not ctx.allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"message": "Tenant not allowed", "tenant": ctx.id},
        )
    return ctx.id or ""


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI dependency
# ──────────────────────────────────────────────────────────────────────────────
def require_tenant():
    """
    Ensure a tenant is selected and (if enabled) allowed.
    Returns the resolved tenant id (may be empty string if not set and tenancy disabled).
    """
    # Lazy import to avoid a dependency cycle
    with suppress(Exception):
        pass  # type: ignore

    async def _dep(request: Request, user=Depends(globals().get("get_current_user", lambda: None))):  # type: ignore
        return enforce_tenant(request, user=user)

    return _dep


# ──────────────────────────────────────────────────────────────────────────────
# Key namespacing helpers
# ──────────────────────────────────────────────────────────────────────────────
def tenantize_key(key: str, tenant_id: str | None = None) -> str:
    """
    Prefix a cache/DB key with the tenant to avoid collisions.
    Example: tenantize_key("rate:count") -> "t:acme:rate:count"
    """
    t = tenant_id if tenant_id is not None else get_current_tenant()
    t = t or "global"
    return f"t:{t}:{key}"


__all__ = [
    "TenantContext",
    "enforce_tenant",
    "get_current_tenant",
    "require_tenant",
    "select_tenant",
    "set_current_tenant",
    "tenantize_key",
]
