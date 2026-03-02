"""
JWT validation against an external OIDC Identity Provider using JWKS.

Features
--------
- Fetch & cache JWKS by `kid` with TTL and on-miss refresh
- Validate RS256/ES256 JWT signatures and claims (iss, aud, exp/nbf/iat)
- Extract common claims (sub, scope/scopes/roles)
- FastAPI dependencies:
    * bearer_required(): extract raw Bearer token from Authorization header
    * validate_jwt(): decode+validate and return claims dict
    * get_current_principal(): return a lightweight principal object
    * require_scopes([...]): dependency for scope enforcement

Notes
-----
- JWKS URL is taken from `settings.OIDC_JWKS_URL`. For tests, it may be a
  `file://` path or an absolute path to a local JSON file.
- Audience may be a single string or an array in the token; we accept iff
  `settings.OIDC_AUDIENCE` is contained.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - optional structured logging
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

import httpx
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, SecurityScopes
from jose import jwk, jwt
from jose.utils import base64url_decode

from src.config import settings


# ---------------- Models ----------------
@dataclass(frozen=True)
class Principal:
    sub: str
    scopes: tuple[str, ...]
    raw: dict[str, Any]


# ---------------- Bearer extraction ----------------
_http_bearer = HTTPBearer(auto_error=False)


async def bearer_required(credentials: HTTPAuthorizationCredentials = Security(_http_bearer)) -> str:
    """Extract the raw Bearer token via FastAPI's documented HTTP bearer scheme."""
    if not credentials or not credentials.credentials or str(credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token")
    return credentials.credentials


# ---------------- JWKS cache ----------------
_JWKS_CACHE: dict[str, tuple[dict, float]] = {}
try:
    _JWKS_TTL_SECONDS = int(os.getenv("OIDC_JWKS_CACHE_TTL_SECONDS", "900"))
except ValueError:
    _JWKS_TTL_SECONDS = 900
try:
    _JWKS_MIN_TTL_SECONDS = int(os.getenv("OIDC_JWKS_CACHE_MIN_TTL_SECONDS", str(max(600, _JWKS_TTL_SECONDS))))
except ValueError:
    _JWKS_MIN_TTL_SECONDS = max(600, _JWKS_TTL_SECONDS)


def _clamp_ttl(ttl: int) -> int:
    """Apply floor/ceiling bounds to JWKS TTL."""
    ttl = max(ttl, _JWKS_MIN_TTL_SECONDS)
    ttl = min(ttl, _JWKS_TTL_SECONDS)
    return ttl


def _load_jwks_from_file(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def _fetch_jwks() -> tuple[dict, int]:
    url = settings.OIDC_JWKS_URL or ""
    if not url:
        raise HTTPException(status_code=500, detail="OIDC_JWKS_URL not configured")
    # Support local files for tests
    if url.startswith("file://"):
        return _load_jwks_from_file(url[len("file://") :]), _clamp_ttl(_JWKS_TTL_SECONDS)
    if url.startswith("/") and os.path.exists(url):
        return _load_jwks_from_file(url), _clamp_ttl(_JWKS_TTL_SECONDS)
    timeout = settings.OIDC_TIMEOUT_S or 5
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        ttl = _JWKS_TTL_SECONDS
        cache_control = r.headers.get("Cache-Control") or ""
        match = re.search(r"max-age=(\d+)", cache_control)
        if match:
            with contextlib.suppress(ValueError):
                ttl = int(match.group(1))
        return data, _clamp_ttl(ttl)


async def _get_key_for_kid(kid: str) -> dict:
    now = time.time()
    if kid in _JWKS_CACHE:
        key, exp = _JWKS_CACHE[kid]
        if exp > now:
            logger.debug("jwt.jwks.cache_hit", kid=kid, expires_in=int(exp - now))
            return key
    # refresh JWKS and cache keys by kid
    jwks_url = settings.OIDC_JWKS_URL or ""
    jwks, ttl = await _fetch_jwks()
    keys = jwks.get("keys") or []
    exp = now + ttl
    # Build cache entries for all keys
    for k in keys:
        k_kid = k.get("kid")
        if k_kid:
            _JWKS_CACHE[k_kid] = (k, exp)
    logger.info(
        "jwt.jwks.cache_refreshed",
        kid=kid,
        ttl_seconds=ttl,
        cache_size=len(_JWKS_CACHE),
        source=jwks_url,
    )
    if kid in _JWKS_CACHE:
        return _JWKS_CACHE[kid][0]
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token")


def _aud_contains(aud_claim: Any, expected: str) -> bool:
    if not expected:
        return True
    if isinstance(aud_claim, str):
        return aud_claim == expected
    if isinstance(aud_claim, (list, tuple)):
        return expected in aud_claim
    return False


def _extract_scopes_from_claims(claims: dict[str, Any]) -> list[str]:
    # Collect scopes/roles/permissions from common claim shapes and normalize.
    collected: set[str] = set()

    scope_val = claims.get("scope")
    if isinstance(scope_val, str):
        with contextlib.suppress(Exception):
            collected.update({s for s in scope_val.split() if s})

    for key in ("scopes", "roles", "permissions", "claims"):
        value = claims.get(key)
        if isinstance(value, (list, tuple)):
            collected.update(str(x) for x in value if x)

    # Roles often arrive without explicit admin:all. Derive it when admin role present.
    roles = claims.get("roles")
    if isinstance(roles, (list, tuple)) and any(str(r).lower() == "admin" for r in roles):
        collected.add("admin:all")

    permissions = claims.get("permissions")
    if isinstance(permissions, (list, tuple)) and any(str(p).lower() == "admin:all" for p in permissions):
        collected.add("admin:all")

    return sorted(collected)


async def validate_jwt(token: str, *, enforce_short_ttl: bool = False) -> dict[str, Any]:
    """Validate a JWT against configured OIDC issuer/audience using JWKS.

    Args:
        token: JWT token string
        enforce_short_ttl: If True, enforce TTL <= 3600 seconds (for internal endpoints)

    Returns decoded claims dict on success, else raises HTTPException 401.
    """
    try:
        # Parse headers to obtain kid and alg
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
        key_dict = await _get_key_for_kid(kid)
        public_key = jwk.construct(key_dict)

        # Verify signature manually (python-jose high-level can do it, but we also check iss/aud below)
        message, encoded_sig = token.rsplit(".", 1)
        decoded_sig = base64url_decode(encoded_sig.encode())
        if not public_key.verify(message.encode(), decoded_sig):
            raise HTTPException(status_code=401, detail="Invalid or missing token")

        # Decode claims without re-verifying signature (already done), but validate exp/nbf/iat
        claims = jwt.get_unverified_claims(token)

        # Time-based checks
        now = int(time.time())
        if "exp" in claims and int(claims["exp"]) < now:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
        if "nbf" in claims and int(claims["nbf"]) > now:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
        if "iat" in claims and int(claims["iat"]) > now + 60:
            # iat in future beyond small clock skew
            raise HTTPException(status_code=401, detail="Invalid or missing token")

        # TTL enforcement for internal endpoints (security requirement)
        if enforce_short_ttl:
            exp = claims.get("exp")
            iat = claims.get("iat")
            if exp and iat:
                ttl = int(exp) - int(iat)
                max_ttl = getattr(settings, "INTERNAL_TOKEN_MAX_TTL_SECONDS", 3600)
                if ttl > max_ttl:
                    raise HTTPException(
                        status_code=401,
                        detail={
                            "type": "https://cineca.example/errors/token-ttl-exceeded",
                            "title": "Token TTL Too Long",
                            "status": 401,
                            "detail": f"Internal endpoints require tokens with TTL <= {max_ttl}s (got {ttl}s)",
                            "extensions": {"token_ttl_seconds": ttl, "max_allowed_ttl_seconds": max_ttl},
                        },
                    )

        # iss/aud checks
        iss_expected = settings.OIDC_ISSUER or ""
        if iss_expected and claims.get("iss") != iss_expected:
            raise HTTPException(
                status_code=401,
                detail={
                    "type": "https://cineca.example/errors/invalid-issuer",
                    "title": "Invalid Token Issuer",
                    "status": 401,
                    "detail": "Token issuer does not match expected issuer",
                    "extensions": {"expected_issuer": iss_expected, "received_issuer": claims.get("iss")},
                },
            )

        aud_expected = settings.OIDC_AUDIENCE or ""
        if aud_expected and not _aud_contains(claims.get("aud"), aud_expected):
            raise HTTPException(
                status_code=401,
                detail={
                    "type": "https://cineca.example/errors/invalid-audience",
                    "title": "Invalid Token Audience",
                    "status": 401,
                    "detail": "Token audience does not match expected audience",
                    "extensions": {"expected_audience": aud_expected, "received_audience": claims.get("aud")},
                },
            )

        return claims
    except HTTPException:
        raise
    except Exception:
        # Generic invalid token
        raise HTTPException(status_code=401, detail="Invalid or missing token")


async def get_current_principal(token: str = Depends(bearer_required)) -> Principal:
    claims = await validate_jwt(token)
    sub = str(claims.get("sub") or "")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    scopes = tuple(_extract_scopes_from_claims(claims))
    return Principal(sub=sub, scopes=scopes, raw=claims)


# ---------------- Scope enforcement ----------------
from .authorization import authorize_or_403  # reuse existing scope logic


def _normalize_required_scopes(
    required: list[str] | tuple[str, ...] | str | None,
    security_scopes: SecurityScopes | None,
) -> list[str]:
    if required is None:
        if security_scopes:
            return list(security_scopes.scopes)
        return []
    if isinstance(required, str):
        return [required]
    return [str(scope) for scope in required]


def require_scopes(required: list[str] | tuple[str, ...] | str | None, *, mode: str = "any"):
    async def _dep(
        security_scopes: SecurityScopes,
        user: Principal = Security(get_current_principal),
    ) -> Principal:
        needed = _normalize_required_scopes(required, security_scopes)
        authorize_or_403({"sub": user.sub, "scopes": list(user.scopes)}, needed, mode=mode, resource="route")
        return user

    return _dep


__all__ = [
    "Principal",
    "bearer_required",
    "get_current_principal",
    "require_scopes",
    "validate_jwt",
]
