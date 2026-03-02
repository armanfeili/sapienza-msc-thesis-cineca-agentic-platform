"""
Permission helpers for model instance access control.

This module defines fine-grained permissions for model instances and provides
helper functions for permission checking with flexible OR logic.

Permission Hierarchy:
--------------------
User Scopes (regular authenticated users):
- models:read                      -> List and get model instances
- models:test                      -> Test model instances
- models:defaults:read             -> Read default model configuration
- models:defaults:write:self       -> Set own default model (user-scoped)

Admin Scopes (elevated privileges):
- models:write                     -> Create model instances
- models:delete                    -> Delete model instances
- models:defaults:write:tenant     -> Set tenant-scoped defaults
- models:defaults:write:global     -> Set global defaults
- admin:all                        -> Legacy admin scope (grants all permissions)

Usage Examples:
--------------
```python
# Check if user has any of multiple permissions (OR logic)
from src.security.model_perms import require_any_perms

@router.get("/models/instances")
async def list_instances(
    user: UserInfo = Depends(require_any_perms(["models:read", "admin:all"]))
):
    pass

# Check permissions programmatically
from src.security.model_perms import has_any_permission

if has_any_permission(user, ["models:write", "admin:all"]):
    # User is admin
    pass
```
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from src.schemas.auth import UserInfo
from src.routers.auth import get_current_user

# ========== Permission Constants ==========

# Admin permission (full access to all model operations)
ADMIN_ALL = "admin:all"

# User permission (authenticated users can read/test models, set their own defaults)
USER_ME = "user:me"

# Tools permissions (not used for models, but exist in token)
TOOLS_ALL = "tools:all"
TOOLS_BASIC = "tools:basic"

# Legacy: These are deprecated and no longer required (kept for documentation)
# MODELS_READ = "models:read"  # Now covered by user:me
# MODELS_TEST = "models:test"  # Now covered by user:me
# MODELS_DEFAULTS_READ = "models:defaults:read"  # Now covered by user:me
# MODELS_DEFAULTS_WRITE_SELF = "models:defaults:write:self"  # Now covered by user:me
# MODELS_WRITE = "models:write"  # Now covered by admin:all
# MODELS_DELETE = "models:delete"  # Now covered by admin:all
# MODELS_DEFAULTS_WRITE_TENANT = "models:defaults:write:tenant"  # Now covered by admin:all
# MODELS_DEFAULTS_WRITE_GLOBAL = "models:defaults:write:global"  # Now covered by admin:all

# ========== Permission Groups ==========

# All user-level permissions (authenticated users)
USER_PERMISSIONS = [USER_ME]

# All admin-level permissions
ADMIN_PERMISSIONS = [ADMIN_ALL]

# All model-related permissions
ALL_MODEL_PERMISSIONS = [USER_ME, ADMIN_ALL]


# ========== Permission Checking Functions ==========


def has_permission(user: UserInfo, permission: str) -> bool:
    """
    Check if user has a specific permission.

    Args:
        user: UserInfo object containing user claims and permissions
        permission: Permission string to check (e.g., "models:read")

    Returns:
        True if user has the permission or admin:all, False otherwise
    """
    if not user:
        return False

    user_perms = getattr(user, "permissions", None) or []

    # admin:all grants all permissions
    if ADMIN_ALL in user_perms:
        return True

    return permission in user_perms


def has_any_permission(user: UserInfo, permissions: list[str]) -> bool:
    """
    Check if user has ANY of the specified permissions (OR logic).

    Args:
        user: UserInfo object containing user claims and permissions
        permissions: List of permission strings to check

    Returns:
        True if user has at least one of the permissions or admin:all

    Example:
        >>> has_any_permission(user, ["models:read", "admin:all"])
        True  # if user has either permission
    """
    if not user:
        return False

    user_perms = getattr(user, "permissions", None) or []

    # admin:all grants all permissions
    if ADMIN_ALL in user_perms:
        return True

    # Check if user has any of the requested permissions
    return any(perm in user_perms for perm in permissions)


def has_all_permissions(user: UserInfo, permissions: list[str]) -> bool:
    """
    Check if user has ALL of the specified permissions (AND logic).

    Args:
        user: UserInfo object containing user claims and permissions
        permissions: List of permission strings to check

    Returns:
        True if user has all of the permissions or admin:all

    Example:
        >>> has_all_permissions(user, ["models:read", "models:test"])
        True  # only if user has both permissions
    """
    if not user:
        return False

    user_perms = getattr(user, "permissions", None) or []

    # admin:all grants all permissions
    if ADMIN_ALL in user_perms:
        return True

    # Check if user has all requested permissions
    return all(perm in user_perms for perm in permissions)


def is_admin(user: UserInfo) -> bool:
    """
    Check if user has admin privileges.

    A user is considered an admin if they have:
    - admin:all (full admin access)

    Args:
        user: UserInfo object containing user claims and permissions

    Returns:
        True if user has admin privileges
    """
    return has_permission(user, ADMIN_ALL)


def check_permission(user: UserInfo, permissions: str | list[str], error_message: str | None = None) -> None:
    """
    Check if user has required permission(s) and raise HTTPException if not.

    If a list of permissions is provided, checks if user has ANY (OR logic).

    Args:
        user: UserInfo object containing user claims and permissions
        permissions: Single permission string or list of permissions (OR logic)
        error_message: Optional custom error message

    Raises:
        HTTPException: 403 Forbidden if user lacks required permission(s)

    Example:
        >>> check_permission(user, "models:read")
        >>> check_permission(user, ["models:read", "admin:all"])
    """
    if isinstance(permissions, str):
        permissions = [permissions]

    if not has_any_permission(user, permissions):
        if error_message is None:
            perm_str = " or ".join(f"'{p}'" for p in permissions)
            error_message = f"Insufficient permissions. Required: {perm_str}"

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=error_message, headers={"WWW-Authenticate": "Bearer"}
        )


# ========== FastAPI Dependencies ==========


def require_any_perms(permissions: list[str]):
    """
    FastAPI dependency that requires user to have ANY of the specified permissions.

    Args:
        permissions: List of permission strings (OR logic)

    Returns:
        FastAPI dependency that checks permissions and returns UserInfo

    Raises:
        HTTPException: 401 if not authenticated, 403 if missing permissions

    Example:
        ```python
        @router.get("/models/instances")
        async def list_instances(
            user: UserInfo = Depends(require_any_perms(["models:read", "admin:all"]))
        ):
            pass
        ```
    """

    async def dependency(user: UserInfo = Depends(get_current_user)) -> UserInfo:
        check_permission(user, permissions)
        return user

    return dependency


def require_all_perms(permissions: list[str]):
    """
    FastAPI dependency that requires user to have ALL of the specified permissions.

    Args:
        permissions: List of permission strings (AND logic)

    Returns:
        FastAPI dependency that checks permissions and returns UserInfo

    Raises:
        HTTPException: 401 if not authenticated, 403 if missing permissions

    Example:
        ```python
        @router.post("/models/instances/batch")
        async def batch_create(
            user: UserInfo = Depends(require_all_perms(["models:write", "models:test"]))
        ):
            pass
        ```
    """

    async def dependency(user: UserInfo = Depends(get_current_user)) -> UserInfo:
        if not has_all_permissions(user, permissions):
            perm_str = " and ".join(f"'{p}'" for p in permissions)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {perm_str}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    return dependency


def require_admin():
    """
    FastAPI dependency that requires admin privileges.

    Returns:
        FastAPI dependency that checks for admin permissions

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin

    Example:
        ```python
        @router.post("/models/instances")
        async def create_instance(
            user: UserInfo = Depends(require_admin())
        ):
            pass
        ```
    """

    async def dependency(user: UserInfo = Depends(get_current_user)) -> UserInfo:
        if not is_admin(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    return dependency


# ========== Scope Resolution Helpers ==========


def can_set_default_scope(user: UserInfo, scope: str) -> bool:
    """
    Check if user can set defaults at the specified scope level.

    Simplified permission model:
    - "user" scope: Any authenticated user (user:me) can set their own defaults
    - "tenant" scope: Only admins (admin:all) can set tenant defaults
    - "global" scope: Only admins (admin:all) can set global defaults

    Args:
        user: UserInfo object
        scope: One of "user", "tenant", or "global"

    Returns:
        True if user has permission to set defaults at that scope
    """
    if scope == "user":
        # Any authenticated user can set their own defaults
        return has_any_permission(user, [USER_ME, ADMIN_ALL])
    elif scope == "tenant":
        # Only admins can set tenant defaults
        return has_permission(user, ADMIN_ALL)
    elif scope == "global":
        # Only admins can set global defaults
        return has_permission(user, ADMIN_ALL)
    else:
        return False


def get_allowed_default_scopes(user: UserInfo) -> list[str]:
    """
    Get list of default scopes the user can modify.

    Args:
        user: UserInfo object

    Returns:
        List of scope strings: ["user"], ["user", "tenant"], or ["user", "tenant", "global"]
    """
    scopes = []

    # All authenticated users can set their own defaults
    if has_any_permission(user, [USER_ME, ADMIN_ALL]):
        scopes.append("user")

    # Only admins can set tenant and global defaults
    if has_permission(user, ADMIN_ALL):
        scopes.append("tenant")
        scopes.append("global")

    return scopes
