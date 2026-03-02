"""
Authentication convenience endpoints (OIDC resource server).

Endpoints (mounted under /v1/auth by the application):
- GET  /v1/auth/me        -> echo key claims from the presented Bearer JWT

Runtime model routes import a relaxed bearer validator from here (`get_current_user`) that ONLY validates
signature/iss/aud and exposes subject-based identity (.sub). Scope/role enforcement lives solely under
admin/internal routers which call dedicated permission dependencies.
"""

from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.schemas.auth import UserInfo
from src.config import settings
from src.security.jwt import validate_jwt  # reuse low-level validation
from src.security.perm import current_permissions, require_perms
from src.security.rate_limit import rate_limiter

router = APIRouter(tags=["auth"])


# Relaxed bearer scheme for runtime routes (no auto_error to allow explicit 401)
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request, credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> UserInfo:  # pragma: no cover - thin wrapper
    """Validate Bearer token and return identity with permissions.

    Validates token signature, iss, aud via OIDC/JWKS or legacy HS256.
    Extracts permissions from scope/scopes/permissions/roles claims.
    """
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token")
    token = credentials.credentials
    # Prefer existing OIDC (validate_jwt) path when configured. Fallback to legacy symmetric config if present.
    claims = None
    try:
        if settings.OIDC_JWKS_URL:
            # validate_jwt raises HTTPException on failure
            import anyio

            # validate_jwt is async; run in current loop
            claims = anyio.run(validate_jwt, token)  # type: ignore[arg-type]
        else:
            # Legacy HS256 path
            claims = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
                audience=settings.JWT_AUDIENCE if getattr(settings, "JWT_AUDIENCE", None) else None,
                issuer=settings.JWT_ISSUER if getattr(settings, "JWT_ISSUER", None) else None,
                options={"verify_aud": bool(getattr(settings, "JWT_AUDIENCE", None))},
            )
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token")
    sub = claims.get("sub") if isinstance(claims, dict) else None
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token")
    tenant_id = getattr(request.state, "tenant_id", None) or "global"

    # Extract permissions from token claims
    permissions_set: set = set()

    # 1. Check explicit permissions claim (Auth0 style)
    perm_claim = claims.get("permissions")
    if isinstance(perm_claim, (list, tuple)):
        permissions_set.update(str(p) for p in perm_claim if p)

    # 2. Check scope claim (space-separated string)
    scope_claim = claims.get("scope")
    if isinstance(scope_claim, str):
        permissions_set.update(s for s in scope_claim.split() if s)

    # 3. Check scopes claim (array)
    scopes_claim = claims.get("scopes")
    if isinstance(scopes_claim, (list, tuple)):
        permissions_set.update(str(s) for s in scopes_claim if s)

    # 4. Check roles claim - admin role grants admin:all
    roles_claim = claims.get("roles")
    roles_list = []
    if isinstance(roles_claim, (list, tuple)):
        roles_list = [str(r) for r in roles_claim if r]
        if any(r.lower() == "admin" for r in roles_list):
            permissions_set.add("admin:all")

    permissions_list = sorted(permissions_set)
    scopes_list = sorted(permissions_set)  # scopes and permissions are synonymous here

    # Do not populate username (deprecated); keep for backward compatibility in response model only
    return UserInfo(
        sub=sub, username=None, tenant_id=tenant_id, scopes=scopes_list, roles=roles_list, permissions=permissions_list
    )


# ---------------- Routes ----------------
@router.get(
    "/me",
    response_model=UserInfo,
    summary="Get current user claims from token",
    description=(
        "**GET /auth/me – Get your user information from token**\n\n"
        "**Why we need this endpoint:**\n"
        "- **User interface personalization**: Front-end apps need to display the current user's name and permissions to customize the UI.\n"
        "- **Permission checking**: Client apps verify what actions the user can perform before showing buttons or menu options.\n"
        "- **Token validation**: Developers can quickly check if their token is valid and contains the expected scopes.\n"
        "- **Debugging authentication**: When users report permission errors, this endpoint confirms what the token actually contains.\n"
        "- Without this endpoint, client apps would have to decode JWT tokens themselves (insecure) or show generic UIs that don't reflect user permissions.\n\n"
        "**What it does:**\n"
        "- Returns information extracted from your current Bearer token.\n"
        "- Shows your username (token subject), granted scopes, roles, and computed permissions.\n"
        "- Useful for client-side UI to display current user or for token inspection/debugging.\n\n"
        "**Access:**\n"
        "- Requires valid Bearer token in `Authorization` header.\n"
        "- Any authenticated user can call this to see their own token claims.\n"
        "- Requires `user:me` or `admin:all` scope.\n\n"
        "**Behavior:**\n"
        "- **Rate limited**: Max 30 requests per 60 seconds per user.\n"
        "- **Token parsing**: Extracts `sub`, `scopes`, `roles`, and computes effective `permissions`.\n"
        "- **No caching**: Always returns fresh token claims (no conditional GET).\n\n"
        "**Responses:**\n"
        "- **200 OK**: Returns `UserInfo` with token claims.\n"
        "- **401 Unauthorized**: Missing or invalid Bearer token.\n"
        "- **403 Forbidden**: Token lacks required scope (`user:me` or `admin:all`).\n"
        "- **429 Too Many Requests**: Rate limit exceeded (>30 requests/minute).\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Get your user info from token\n"
        "curl -H 'Authorization: Bearer YOUR_TOKEN' \\\n"
        "  https://api.example.com/v1/auth/me\n"
        '# → {"sub": "user123", "scopes": ["user:me", "jobs:read"], "roles": ["developer"], "permissions": ["jobs:read", "user:me"]}\n'
        "```"
    ),
)
async def read_users_me(
    current_user=Depends(require_perms(["user:me", "admin:all"])),
    _rl=Depends(rate_limiter(limit=30, window=60).dependency),
):
    """Return decoded token claims for the authenticated caller.

    Requires a valid Bearer token. Returns the username and granted scopes.
    """
    # Map Principal to public response
    try:
        sub = getattr(current_user, "sub", None)
        scopes = list(getattr(current_user, "scopes", []) or [])
        roles = list(getattr(current_user, "raw", {}).get("roles", []) or [])
        perms = sorted(current_permissions(current_user))
    except Exception:
        sub = None
        scopes = []
        roles = []
        perms = []
    return UserInfo(sub=sub, scopes=scopes, roles=roles, permissions=perms)
