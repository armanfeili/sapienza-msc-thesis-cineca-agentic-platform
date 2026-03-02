"""
Permission utilities built on top of OIDC Principal claims.

Model
-----
- Roles: "user", "admin" (if present in `roles` claim)
- Permissions: small set of strings like "user:me", "tools:basic", "tools:all", "admin:all".

Rules
-----
- If `roles` contains "admin", grant implicit permission "admin:all".
- If token has `permissions` claim (array[str]), use those as-is.
- Else, fall back to `scope` (space-separated) or `scopes` (array) claims.

API
---
- current_permissions(user) -> set[str]
- has_perms(user, any_of=[...]) -> bool
- enforce_perms(user, any_of=[...]) -> None (raise 403)
- require_perms(any_of=[...]) -> FastAPI dependency that returns the user
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException, Security, status

from .jwt import get_current_principal


def _as_set(values: Iterable[str] | str | None) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        return {values}
    return {str(v) for v in values}


def current_permissions(user) -> set[str]:
    """Extract effective permissions from a Principal-like object.

    Precedence: permissions (array) -> scope/scopes -> roles mapping.
    If role "admin" present, include implicit "admin:all".
    """
    perms: set[str] = set()
    raw: dict[str, Any] = {}
    try:
        raw = getattr(user, "raw", {}) or {}
    except Exception:
        raw = {}

    def _ingest(values: Any) -> None:
        if isinstance(values, (list, tuple, set)):
            perms.update(_as_set(values))
        elif isinstance(values, str):
            # Treat space-delimited scopes as individual permissions
            for token in values.split():
                if token:
                    perms.add(token)

    # 1) explicit permissions claim (Auth0-style)
    _ingest(raw.get("permissions"))

    # 2) scope (space-delimited) or scopes (array)
    _ingest(raw.get("scope"))
    _ingest(raw.get("scopes"))

    # 3) roles -> implicit mapping
    roles = raw.get("roles")
    if isinstance(roles, (list, tuple)):
        if any(str(r).lower() == "admin" for r in roles):
            perms.add("admin:all")

    # 4) dict principals: merge top-level permissions/scopes/roles
    if isinstance(user, dict):
        _ingest(user.get("permissions"))
        _ingest(user.get("scope"))
        _ingest(user.get("scopes"))
        roles_top = user.get("roles")
        if isinstance(roles_top, (list, tuple)):
            if any(str(r).lower() == "admin" for r in roles_top):
                perms.add("admin:all")
    # Normalize common Auth0-style permission names to internal ones
    # Accept: tools:invoke:basic -> tools:basic; tools:invoke:all -> tools:all; tools:invoke -> tools:basic
    norm: set[str] = set()
    for p in list(perms):
        pp = str(p)
        low = pp.lower()
        if low in {"tools:basic", "tools:all", "admin:all", "user:me"}:
            norm.add(pp)
            continue
        if low == "tools:invoke":
            norm.add("tools:basic")
            continue
        if low.endswith(":basic") and low.startswith("tools:invoke"):
            norm.add("tools:basic")
            continue
        if low.endswith(":all") and low.startswith("tools:invoke"):
            norm.add("tools:all")
            continue
        # pass-through unknown permissions as-is
        norm.add(pp)
    # ensure admin:all remains if present in either set
    if "admin:all" in perms:
        norm.add("admin:all")
    return norm


def has_perms(user, any_of: Iterable[str] | str) -> bool:
    req = _as_set(any_of)
    if not req:
        return True
    eff = current_permissions(user)
    # admin:all is a super permission
    if "admin:all" in eff:
        return True
    return any(r in eff for r in req)


def enforce_perms(user, any_of: Iterable[str] | str) -> None:
    if not has_perms(user, any_of):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: missing permission")


def require_perms(any_of: Iterable[str] | str):
    """FastAPI dependency that ensures the caller has at least one permission from the set.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_perms(["admin:all"]))])
    """

    async def _dep(user=Security(get_current_principal)):
        enforce_perms(user, any_of)
        return user

    return _dep


__all__ = [
    "current_permissions",
    "enforce_perms",
    "infer_role_from_principal",
    "has_perms",
    "require_perms",
]


def infer_role_from_principal(principal) -> str | None:
    """Best-effort role inference from principal scopes/permissions."""
    try:
        scopes: set[str] = set()
        perms: set[str] = set()
        roles: set[str] = set()

        if hasattr(principal, "raw"):
            raw = principal.raw or {}
            raw_scopes = raw.get("scope") or raw.get("scopes") or []
            if isinstance(raw_scopes, str):
                scopes |= {s for s in raw_scopes.split() if s}
            elif isinstance(raw_scopes, (list, tuple, set)):
                scopes |= {str(s) for s in raw_scopes}
            raw_perms = raw.get("permissions") or []
            if isinstance(raw_perms, (list, tuple, set)):
                perms |= {str(p) for p in raw_perms}
            raw_roles = raw.get("roles") or []
            if isinstance(raw_roles, (list, tuple, set)):
                roles |= {str(r) for r in raw_roles}
        if isinstance(principal, dict):
            scopes_val = principal.get("scopes") or principal.get("scope") or []
            if isinstance(scopes_val, str):
                scopes |= {s for s in scopes_val.split() if s}
            elif isinstance(scopes_val, (list, tuple, set)):
                scopes |= {str(s) for s in scopes_val}
            perms_val = principal.get("permissions") or []
            if isinstance(perms_val, (list, tuple, set)):
                perms |= {str(p) for p in perms_val}
            roles_val = principal.get("roles") or []
            if isinstance(roles_val, (list, tuple, set)):
                roles |= {str(r) for r in roles_val}
        elif hasattr(principal, "scopes"):
            scopes_val = principal.scopes or []
            if isinstance(scopes_val, str):
                scopes |= {s for s in scopes_val.split() if s}
            elif isinstance(scopes_val, (list, tuple, set)):
                scopes |= {str(s) for s in scopes_val}

        tokens = {t.lower() for t in (scopes | perms | roles)}
        if "admin:all" in tokens or "admin" in tokens:
            return "admin"
        if any(t in tokens for t in ("tools:all", "tools:invoke:all")):
            return "power_user"
        if any(t in tokens for t in ("tools:basic", "tools:invoke:basic", "tools:invoke")):
            return "basic"
    except Exception:
        return None
    return None
