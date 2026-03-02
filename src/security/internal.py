"""
Internal endpoint security enforcement.

Provides FastAPI dependencies for enforcing internal-only access via service tokens
or special internal claims. Platform admins cannot bypass this restriction.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from src.security.jwt import Principal, bearer_required, validate_jwt


async def get_internal_principal(token: str = Depends(bearer_required)) -> Principal:
    """
    Get principal with enhanced validation for internal endpoints.

    Enforces:
    - TTL <= 3600 seconds (configurable via INTERNAL_TOKEN_MAX_TTL_SECONDS)
    - Proper aud/iss validation

    Returns:
        Principal with validated claims
    """
    # Validate JWT with short TTL enforcement for internal endpoints
    claims = await validate_jwt(token, enforce_short_ttl=True)

    sub = str(claims.get("sub") or "")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid or missing token")

    # Extract scopes from claims
    scopes = []
    if "scope" in claims:
        scope_str = claims["scope"]
        if isinstance(scope_str, str):
            scopes = tuple(scope_str.split())
    elif "scopes" in claims:
        scopes = tuple(claims["scopes"]) if isinstance(claims["scopes"], list) else ()
    elif "permissions" in claims:
        scopes = tuple(claims["permissions"]) if isinstance(claims["permissions"], list) else ()

    return Principal(sub=sub, scopes=scopes, raw=claims)


def has_internal_access(principal: Principal) -> bool:
    """
    Check if the principal has internal access.

    Internal access is granted ONLY if:
    - The principal has a special 'service' claim (custom claim in JWT), OR
    - The principal has 'internal:all' scope/permission

    Explicitly DENIES access to:
    - Admin tokens (admin:all) - admins cannot bypass internal-only access
    - User tokens (user:me, tools:invoke:*) - regular users have no internal access

    Args:
        principal: The authenticated principal

    Returns:
        True if has internal access, False otherwise
    """
    scopes = getattr(principal, "scopes", ())

    # Explicit deny: admin:all does NOT grant internal access
    if "admin:all" in scopes:
        return False

    # Explicit deny: user/tool scopes do NOT grant internal access
    user_patterns = ("user:me", "tools:invoke:basic", "tools:invoke:all")
    if any(scope in scopes for scope in user_patterns) and "internal:all" not in scopes:
        return False

    # Check for service token indicator (custom claim in JWT)
    # Access raw dict if Principal has it
    raw_claims = getattr(principal, "raw", {})
    if raw_claims.get("service") is True:
        return True

    # Alternative: check custom namespace claim (e.g., https://cineca.eu/service)
    if raw_claims.get("https://cineca.eu/service") is True:
        return True

    # Check for internal scope/permission
    if "internal:all" in scopes:
        return True

    # Default deny
    return False


def enforce_internal(principal: Principal) -> None:
    """
    Enforce that the principal has internal access.

    Raises HTTPException 403 if the principal lacks internal access.

    Args:
        principal: The authenticated principal

    Raises:
        HTTPException: 403 if not authorized for internal endpoints
    """
    scopes = getattr(principal, "scopes", ())

    if not has_internal_access(principal):
        # Provide specific error message based on token type
        error_detail = "Access denied: internal endpoints require service token with internal:all permission"

        if "admin:all" in scopes:
            error_detail = "Access denied: admin tokens cannot access internal endpoints. Use service token with internal:all permission."
        elif any(s.startswith("user:") or s.startswith("tools:") for s in scopes):
            error_detail = "Access denied: user tokens cannot access internal endpoints. Use service token with internal:all permission."

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "type": "https://cineca.example/errors/internal-access-denied",
                "title": "Forbidden - Internal Access Required",
                "status": 403,
                "detail": error_detail,
                "extensions": {"required_scopes": ["internal:all"], "provided_scopes": list(scopes) if scopes else []},
            },
        )


def require_internal():
    """
    FastAPI dependency that enforces internal access.

    Returns the authenticated principal if they have internal access,
    otherwise raises HTTPException 403.

    Enforces:
    - Token TTL <= 3600 seconds (short-lived tokens only)
    - Proper aud/iss validation
    - internal:all scope OR service claim
    - Explicit rejection of admin:all and user tokens

    Usage:
        @router.get("/internal/resource", dependencies=[Depends(require_internal())])
        async def internal_endpoint():
            ...

    Or to access the principal:
        @router.get("/internal/resource")
        async def internal_endpoint(user: Principal = Depends(require_internal())):
            ...

    Returns:
        FastAPI dependency function
    """

    async def _check_internal(principal: Principal = Depends(get_internal_principal)) -> Principal:
        enforce_internal(principal)
        return principal

    return _check_internal


__all__ = [
    "enforce_internal",
    "get_internal_principal",
    "has_internal_access",
    "require_internal",
]
