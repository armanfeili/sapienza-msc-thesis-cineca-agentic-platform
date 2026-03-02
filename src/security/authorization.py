"""
Authorization utilities (roles → scopes expansion, scope matching, and FastAPI helpers).

Key ideas
---------
- Tokens often carry *roles* like ["user", "admin"] instead of granular *scopes*.
  This module expands roles into scopes using a simple policy mapping, and then
  evaluates authorization requests against the resulting scope set.
- Supports wildcard scopes:
    "*"            -> allow everything
    "tools.*"      -> allow any scope under "tools."
    "models.read"  -> allow an exact scope
- Graceful policy loading:
    - Default built-in mapping is used if no external policy file is present.
    - If available, we best-effort merge scopes from `src/agent_policies/roles.yaml`
      or `src/mcp/policies.yaml` via PyYAML (optional).

API surface
-----------
- check_scopes(user_scopes, required, mode="any") -> bool
- authorize(user, required_scopes, *, resource=None, action=None, mode="any") -> bool
- authorize_or_403(user, required_scopes, **kwargs) -> None (raises HTTPException on deny)
- require_scopes(required_scopes, mode="any"): FastAPI dependency factory

Terminology
-----------
- "roles" are coarse labels (e.g., "user", "admin") that expand to scopes.
- "scopes" are permission strings like "tools.invoke" or "agent.run".
- "mode" can be:
    - "any": at least one required scope must be satisfied
    - "all": all required scopes must be satisfied
"""

from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, status

# Optional YAML-powered policy merging
try:  # pragma: no cover
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

from .audit import audit_policy_decision

# ---------------- Defaults & policy loading ----------------
# Built-in, conservative defaults (safe to run without external policy files)
_DEFAULT_ROLE_SCOPES: dict[str, list[str]] = {
    "user": [
        "read",
        "agent.run",
        "tools.invoke",
        "models.complete",
        "system.health",
    ],
    "admin": [
        "*",  # full access
    ],
}


def _load_yaml_roles(file_path: str) -> dict[str, list[str]]:
    """
    Load role->scopes mapping from a YAML file with structure:
        roles:
          admin:
            - "*"
          user:
            - "tools.invoke"
    Returns {} if file missing or YAML unavailable.
    """
    if yaml is None or not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        roles = data.get("roles") or data.get("role_scopes") or {}
        out: dict[str, list[str]] = {}
        for k, v in roles.items():
            if isinstance(v, (list, tuple)):
                out[str(k)] = [str(x) for x in v]
        return out
    except Exception:
        return {}


def _merge_role_policies() -> dict[str, list[str]]:
    """
    Merge defaults with any external policy files if present.
    Precedence: defaults < src/agent_policies/roles.yaml < src/mcp/policies.yaml
    """
    merged: dict[str, list[str]] = {k: list(v) for k, v in _DEFAULT_ROLE_SCOPES.items()}

    for candidate in (
        os.path.join("src", "agent_policies", "roles.yaml"),
        os.path.join("src", "mcp", "policies.yaml"),
    ):
        ext = _load_yaml_roles(candidate)
        for role, scopes in ext.items():
            merged.setdefault(role, [])
            # Merge with de-duplication while preserving order
            seen = set(merged[role])
            for s in scopes:
                if s not in seen:
                    merged[role].append(s)
                    seen.add(s)
    return merged


# Cache the merged policy (simple module-level cache)
_ROLE_TO_SCOPES: dict[str, list[str]] = _merge_role_policies()


# ---------------- Data structures ----------------
@dataclass(frozen=True)
class AuthzDecision:
    allowed: bool
    reason: str
    required: tuple[str, ...]
    effective_scopes: tuple[str, ...]


# ---------------- Helpers ----------------
def _as_list(required: str | Iterable[str]) -> list[str]:
    if isinstance(required, str):
        return [required]
    return [str(x) for x in required]


def _principal(user: Any) -> str:
    """
    Extract principal identifier from a user-like object or dict.
    """
    if user is None:
        return "anonymous"
    for key in ("username", "user_name", "email", "sub"):
        if hasattr(user, key):
            val = getattr(user, key)
            if val:
                return str(val)
        if isinstance(user, dict) and key in user and user[key]:
            return str(user[key])
    # fallback: string repr
    return str(getattr(user, "username", None) or getattr(user, "sub", None) or "unknown")


def _extract_scopes(user: Any) -> list[str]:
    """
    Extract scopes/roles from a user-like object or dict.
    """
    if user is None:
        return []
    if hasattr(user, "scopes"):
        s = user.scopes
        if isinstance(s, (list, tuple, set)):
            return [str(x) for x in s]
    if isinstance(user, dict) and "scopes" in user:
        s = user["scopes"]
        if isinstance(s, (list, tuple, set)):
            return [str(x) for x in s]
    return []


def _expand_roles_to_scopes(scopes_or_roles: Iterable[str]) -> list[str]:
    """
    Expand each token scope/role using the role→scopes mapping.
    If a token isn't a role name, keep it as a literal scope.
    """
    expanded: list[str] = []
    seen = set()
    for token in scopes_or_roles:
        # role expansion
        if token in _ROLE_TO_SCOPES:
            for s in _ROLE_TO_SCOPES[token]:
                if s not in seen:
                    expanded.append(s)
                    seen.add(s)
        elif token not in seen:
            expanded.append(token)
            seen.add(token)
    return expanded


def _wildcard_to_regex(pattern: str) -> str:
    # Escape then replace literal \* sequences with '.*' for wildcard matching
    return r"^" + re.escape(pattern).replace(r"\*", ".*") + r"$"


def _scope_satisfies(candidate: str, required: str) -> bool:
    """
    Return True if candidate scope covers required:
      - "*" covers everything
      - "tools.*" covers "tools.invoke", etc.
      - exact string match covers itself
    """
    if candidate == "*":
        return True
    try:
        pattern = _wildcard_to_regex(candidate)
        return bool(re.fullmatch(pattern, required))
    except Exception:
        # fallback to fnmatch only if regex building or match fails
        return fnmatch.fnmatch(required, candidate)


def check_scopes(
    user_scopes_or_roles: Iterable[str],
    required: str | Iterable[str],
    *,
    mode: str = "any",
) -> bool:
    """
    Evaluate whether the user's scopes satisfy the required scope set.

    Args:
        user_scopes_or_roles: Iterable of token scopes/roles from the user.
        required: scope string or iterable of scope strings.
        mode: "any" (default) or "all".

    Returns:
        True if authorized according to the selected mode.
    """
    req = _as_list(required)
    eff = _expand_roles_to_scopes(user_scopes_or_roles)

    if "*" in eff:
        return True

    if mode not in {"any", "all"}:
        mode = "any"

    if mode == "any":
        for r in req:
            for c in eff:
                if _scope_satisfies(c, r):
                    return True
        return False

    # mode == "all"
    return all(any(_scope_satisfies(c, r) for c in eff) for r in req)


def authorize(
    user: Any,
    required_scopes: str | Iterable[str],
    *,
    resource: str | None = None,
    action: str | None = None,
    mode: str = "any",
    attributes: dict[str, Any] | None = None,
) -> AuthzDecision:
    """
    Make an authorization decision and emit an audit event.

    Returns an AuthzDecision with reasoning and the user's effective scopes.
    """
    req = tuple(_as_list(required_scopes))
    raw = _extract_scopes(user)
    eff = tuple(_expand_roles_to_scopes(raw))
    allowed = check_scopes(raw, req, mode=mode)
    principal = _principal(user)

    reason = (
        "granted by wildcard"
        if "*" in eff
        else (
            "all scopes satisfied"
            if allowed and mode == "all"
            else ("one scope satisfied" if allowed else "insufficient scopes")
        )
    )

    audit_policy_decision(
        policy="role_scope_policy",
        subject=principal,
        action=action or (req[0] if req else "access"),
        resource=resource or "unknown",
        allowed=allowed,
        reason=reason,
        attributes=(attributes or {}) | {"required": list(req), "effective_scopes": list(eff), "mode": mode},
    )

    return AuthzDecision(allowed=allowed, reason=reason, required=req, effective_scopes=eff)


def authorize_or_403(
    user: Any,
    required_scopes: str | Iterable[str],
    *,
    resource: str | None = None,
    action: str | None = None,
    mode: str = "any",
    attributes: dict[str, Any] | None = None,
) -> None:
    """
    Raise HTTP 403 if the authorization decision denies access.
    """
    decision = authorize(
        user,
        required_scopes,
        resource=resource,
        action=action,
        mode=mode,
        attributes=attributes,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not authorized: requires {list(decision.required)}",
        )


# ---------------- FastAPI dependency factory ----------------
def require_scopes(
    required_scopes: str | Iterable[str],
    *,
    mode: str = "any",
    resource: str | None = None,
    action: str | None = None,
):
    """
    Create a dependency that ensures the current user has the required scopes.

    Example:
        @router.get("/admin")
        async def admin_only(user=Depends(require_scopes("admin"))):
            return {"ok": True}
    """
    from src.routers.auth import get_current_user  # lazy import to avoid cycles

    async def _dep(user=Depends(get_current_user)):
        authorize_or_403(
            user,
            required_scopes,
            resource=resource or "route",
            action=action or "access",
            mode=mode,
        )
        return user

    return _dep


__all__ = [
    "AuthzDecision",
    "authorize",
    "authorize_or_403",
    "check_scopes",
    "require_scopes",
]
