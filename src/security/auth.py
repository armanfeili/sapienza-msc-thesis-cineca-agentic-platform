"""
Authentication utilities (JWT + password hashing).

This module centralizes auth primitives so the rest of the app (routers, services)
can share consistent behavior without duplicating logic.

Features:
- Password hashing & verification via passlib[bcrypt]
- JWT creation & decoding via python-jose
- Pydantic models for token payload & user info
- Optional FastAPI dependency (`oauth2_scheme`) and helper `get_current_user`
- A minimal demo authenticator (`authenticate_demo`) that accepts any non-empty
  credentials and assigns scopes (admin for username "admin", otherwise "user")

Note:
Routers may still provide their own auth flows; this module is side-effect free
and can be adopted incrementally.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

from src.config import settings

# Password hashing (bcrypt via passlib)
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def bearer_required(request: Request) -> str:
    """Small dependency to enforce Authorization: Bearer <token> without OpenAPI exposure."""
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return authorization.split(None, 1)[1]


# ---------------- Pydantic models ----------------
class TokenPayload(BaseModel):
    sub: str | None = None
    scopes: list[str] = Field(default_factory=list)
    exp: int | None = None
    iat: int | None = None
    # Optional multi-tenancy & extra claims
    tid: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class UserInfo(BaseModel):
    username: str
    scopes: list[str] = Field(default_factory=list)
    tenant_id: str | None = None


# ---------------- Password helpers ----------------
def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _pwd_ctx.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return _pwd_ctx.verify(plain_password, hashed_password)
    except Exception:
        return False


# ---------------- JWT helpers ----------------
def _now() -> datetime:
    return datetime.now(tz=UTC)


def create_access_token(
    *,
    subject: str,
    scopes: list[str] | None = None,
    expires_delta: timedelta | None = None,
    extra: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> str:
    """
    Create a signed JWT access token.
    """
    to_encode: dict[str, Any] = {
        "sub": subject,
        "scopes": scopes or [],
        "iat": int(_now().timestamp()),
    }
    if tenant_id:
        to_encode["tid"] = tenant_id
    if extra:
        # keep additional structured claims under "extra" to avoid collisions
        to_encode["extra"] = extra

    expire = _now() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = int(expire.timestamp())

    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT access token. Raises JWTError on invalid tokens.
    """
    data = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    return TokenPayload(**data)


# ---------------- Demo authenticator ----------------
def authenticate_demo(username: str, password: str) -> UserInfo:
    """
    Minimal demo authentication:
      - any non-empty username & password are accepted
      - username == "admin" receives scopes ["user", "admin"]
      - otherwise scopes ["user"]
    Replace with real user lookup + password verification in production.

    SECURITY: This function is ONLY for local development/testing.
    It is automatically disabled in production environments.
    """
    # Production guard: Fail fast if demo auth is used in production
    from src.config import settings

    if settings.APP_ENV == "prod":
        raise RuntimeError(
            "Demo authenticator is disabled in production! "
            "Configure proper OIDC authentication via OIDC_JWKS_URL or use real user database."
        )

    if not username or not password:
        raise ValueError("username and password are required")
    scopes = ["user"] + (["admin"] if username.lower() == "admin" else [])
    return UserInfo(username=username, scopes=scopes)


__all__ = [
    "TokenPayload",
    "UserInfo",
    "authenticate_demo",
    "bearer_required",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]
