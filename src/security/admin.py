"""
Admin permission enforcement utilities.

Provides convenience functions and FastAPI dependencies for checking admin permissions.
Integrates with the existing security.perm module and JWT principal extraction.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from src.security.jwt import Principal, get_current_principal
from src.security.perm import current_permissions


def is_admin(principal: Principal) -> bool:
    """
    Check if the principal has admin permissions.

    Returns True if the principal has the 'admin:all' permission.

    Args:
        principal: The authenticated principal

    Returns:
        True if admin, False otherwise
    """
    perms = current_permissions(principal)
    return "admin:all" in perms


def enforce_admin(principal: Principal) -> None:
    """
    Enforce that the principal has admin permissions.

    Raises HTTPException 403 if the principal lacks admin:all permission.

    Args:
        principal: The authenticated principal

    Raises:
        HTTPException: 403 Forbidden if not admin
    """
    if not is_admin(principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: admin:all permission required")


def require_admin():
    """
    FastAPI dependency that enforces admin permissions.

    Returns the authenticated principal if they have admin:all permission,
    otherwise raises HTTPException 403.

    Usage:
        @router.get("/admin/resource", dependencies=[Depends(require_admin())])
        async def admin_endpoint():
            ...

    Or to access the principal:
        @router.get("/admin/resource")
        async def admin_endpoint(user: Principal = Depends(require_admin())):
            ...

    Returns:
        FastAPI dependency function
    """

    async def _check_admin(principal: Principal = Depends(get_current_principal)) -> Principal:
        enforce_admin(principal)
        return principal

    return _check_admin


__all__ = [
    "enforce_admin",
    "is_admin",
    "require_admin",
]
