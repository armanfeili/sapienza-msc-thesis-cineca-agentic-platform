from __future__ import annotations

from typing import Any

from src.security.perm import current_permissions


def principal_identity(p: Any) -> str:
    """Return a safe, human-friendly principal identifier.

    Preference order:
    - sub (subject)
    - email
    - name
    - username
    - subject (alias seen in some libs)
    - "unknown"
    """
    try:
        return (
            getattr(p, "sub", None)
            or getattr(p, "email", None)
            or getattr(p, "name", None)
            or getattr(p, "username", None)
            or getattr(p, "subject", None)
            or "unknown"
        )
    except Exception:
        return "unknown"


def serialize_principal(user: Any, tenant_id: str | None = None) -> dict[str, Any]:
    """Return a JSON-serializable principal payload for downstream services."""

    raw_claims: dict[str, Any] = {}
    try:
        raw_claims = dict(getattr(user, "raw", {}) or {})
    except Exception:
        raw_claims = {}

    subject = (
        getattr(user, "sub", None)
        or raw_claims.get("sub")
        or getattr(user, "id", None)
        or getattr(user, "subject", None)
    )

    scopes = []
    try:
        scopes = list(getattr(user, "scopes", []) or [])
    except Exception:
        scopes = []

    permissions = sorted(current_permissions(user)) if user is not None else []

    resolved_tenant = tenant_id or raw_claims.get("tenant_id")
    roles = raw_claims.get("roles")
    if isinstance(roles, (list, tuple)):
        roles_list = [str(role) for role in roles]
    elif roles is None:
        roles_list = []
    else:
        roles_list = [str(roles)]

    payload = {
        "id": subject,
        "sub": subject,
        "scopes": [str(scope) for scope in scopes],
        "permissions": permissions,
        "tenant_id": resolved_tenant,
        "roles": roles_list,
        "raw": raw_claims,
    }

    return payload


__all__ = ["principal_identity", "serialize_principal"]
