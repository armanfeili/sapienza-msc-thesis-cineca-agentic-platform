"""
MCP Tool: security.permissions

Policy-aware permission helper for the Cineca Agentic Platform.

Actions
-------
- check
    Evaluate whether a principal with a set of roles may perform an action
    on a resource, using the loaded policy set.

    Payload:
      {
        "principal": "user@example.org",
        "roles": ["analyst"],
        "action": "invoke",
        "resource": "mcp.tools.graph.query",
        "context": {"tenant": "default"}
      }
    Returns:
      {
        "ok": true,
        "action": "check",
        "allowed": true,
        "decision": {...},      # engine, reason, matched rules, role sources
        "policy_version": "...",
        "principal": "...",
        "roles": [...]
      }

- resolve
    Compute an *effective* permission preview for the provided roles.
    Payload:
      { "roles": ["viewer","analyst"], "resources": ["mcp.tools.*","/api/*"], "actions": ["invoke","read"] }
    Returns: { ok, action:"resolve", summary:{...}, details:[...] }

- list_roles
    List roles defined in the current policy set and their rule counts.
    Returns: { ok, action:"list_roles", roles:[{name, allow, deny, description?}] }

- reload
    Reload policies from disk (if supported) and report the version/hash.
    Returns: { ok, action:"reload", policy_version:"..." }

Notes
-----
This tool integrates with `src.security.authorization` (if present). If that
module exposes an `authorize` / `is_allowed` / `check_access` function, we
delegate to it. Otherwise, we fall back to a built-in evaluator that supports a
simple `roles -> {allow:[], deny:[]}` model with fnmatch-style patterns.

Patterns
--------
Each rule string can be one of:
- "mcp.tools.graph.query"        (matches by resource)
- "mcp.tools.*"                  (glob resource)
- "action:invoke resource:mcp.*" (field-aware; both must match)
- "action:read"                  (action-only; resource wildcard)

Deny rules override allow rules.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
from collections.abc import Iterable
from contextlib import suppress
from typing import Any

# ── P0 Runtime Infrastructure ─────────────────────────────────────────────────
from src.mcp.runtime import ToolContext, mcp_tool
from src.mcp.schemas import SecurityPermissionsPayload

# ── Logging (structlog-aware if configured) ───────────────────────────────────
with suppress(Exception):
    from src.logging_setup import get_logger  # type: ignore

    logger = get_logger(__name__)  # type: ignore[assignment]
if "logger" not in globals():
    import logging

    logger = logging.getLogger(__name__)

# ── Optional integrations ─────────────────────────────────────────────────────
_AUTH_MOD = None
_AUTHORIZE_FN = None
with suppress(Exception):
    import src.security.authorization as _AUTH_MOD  # type: ignore

    _AUTHORIZE_FN = (
        getattr(_AUTH_MOD, "authorize", None)
        or getattr(_AUTH_MOD, "is_allowed", None)
        or getattr(_AUTH_MOD, "check_access", None)
    )

_PL = None
_GET_POLICIES = None
_RELOAD_POLICIES = None
with suppress(Exception):
    import src.security.policies_loader as _PL  # type: ignore

    _GET_POLICIES = getattr(_PL, "get_policies", None) or getattr(_PL, "load_policies", None)
    _RELOAD_POLICIES = getattr(_PL, "reload_policies", None)

# Fallback policy path
_DEFAULT_POLICY_PATHS = (
    os.environ.get("POLICIES_FILE") or "src/mcp/policies.yaml",
    "mcp/policies.yaml",
    "./policies.yaml",
)


# ─────────────────────────────────────────────────────────────────────────────
# Policy loading
# ─────────────────────────────────────────────────────────────────────────────
def _load_policies() -> dict[str, Any]:
    """Return the active policy dict."""
    if callable(_GET_POLICIES):
        with suppress(Exception):
            pol = _GET_POLICIES()
            if isinstance(pol, dict):
                return pol
            # Some loaders return (policy, version)
            if isinstance(pol, tuple) and isinstance(pol[0], dict):
                return pol[0]

    # Fallback: load YAML directly
    with suppress(Exception):
        import yaml  # type: ignore

        for path in _DEFAULT_POLICY_PATHS:
            if path and os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
    return {}


def _policy_version(policy: dict[str, Any]) -> str:
    raw = repr(policy).encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────────────────
# Built-in evaluator (fallback if no authorization module)
# ─────────────────────────────────────────────────────────────────────────────
def _parse_rule(rule: str) -> tuple[str | None, str | None]:
    """
    Parse a rule string into (action_pattern, resource_pattern).

    Examples:
        "mcp.tools.graph.query" -> (None, "mcp.tools.graph.query")
        "action:invoke resource:mcp.tools.*" -> ("invoke", "mcp.tools.*")
        "action:read" -> ("read", "*")
    """
    r = rule.strip()
    if not r:
        return None, None

    # Fielded form
    parts = [p.strip() for p in r.split() if p.strip()]
    action_pat: str | None = None
    resource_pat: str | None = None
    seen_field = False
    for p in parts:
        if ":" in p:
            seen_field = True
            k, v = p.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            if k == "action":
                action_pat = v
            elif k in {"res", "resource"}:
                resource_pat = v
        # non-field token: treat as resource fragment if mixed
        elif resource_pat is None:
            resource_pat = p

    if not seen_field:
        # Pure resource pattern
        return None, r
    if resource_pat is None:
        resource_pat = "*"
    return action_pat, resource_pat


def _rule_matches(rule: str, action: str, resource: str) -> bool:
    a_pat, r_pat = _parse_rule(rule)
    a_ok = True if a_pat is None else fnmatch.fnmatchcase(action, a_pat)
    r_ok = True if r_pat is None else fnmatch.fnmatchcase(resource, r_pat)
    return a_ok and r_ok


def _eval_roles(
    roles: Iterable[str],
    action: str,
    resource: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    roles = list(roles or [])
    p_roles = (policy.get("roles") or {}) if isinstance(policy, dict) else {}
    matched_allow: list[dict[str, Any]] = []
    matched_deny: list[dict[str, Any]] = []

    for role in roles:
        spec = p_roles.get(role, {}) or {}
        allow_rules = list(spec.get("allow") or [])
        deny_rules = list(spec.get("deny") or [])

        for rule in deny_rules:
            if isinstance(rule, str) and _rule_matches(rule, action, resource):
                matched_deny.append({"role": role, "rule": rule})
        for rule in allow_rules:
            if isinstance(rule, str) and _rule_matches(rule, action, resource):
                matched_allow.append({"role": role, "rule": rule})

    # Deny overrides allow if any deny matched
    if matched_deny:
        reason = "deny:matched"
        return {
            "engine": "builtin",
            "allowed": False,
            "reason": reason,
            "matched": {"deny": matched_deny, "allow": matched_allow},
        }

    allowed = bool(matched_allow)  # at least one allow
    reason = "allow:matched" if allowed else "no-match"
    return {
        "engine": "builtin",
        "allowed": allowed,
        "reason": reason,
        "matched": {"deny": matched_deny, "allow": matched_allow},
    }


def _check_with_engine(
    *,
    principal: str | None,
    roles: Iterable[str],
    action: str,
    resource: str,
    context: dict[str, Any] | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    # Prefer platform authorization module
    if callable(_AUTHORIZE_FN):
        with suppress(Exception):
            res = _AUTHORIZE_FN(  # type: ignore[misc,call-arg]
                principal=principal,
                roles=list(roles or []),
                action=action,
                resource=resource,
                context=context or {},
                policy=policy,
            )
            # Expect either a dict or an object with .allowed/.reason
            if isinstance(res, dict):
                return {"engine": "authorization", **res}
            allowed = bool(getattr(res, "allowed", False))
            reason = getattr(res, "reason", None) or ("allow" if allowed else "deny")
            matched = getattr(res, "matched", None)
            return {"engine": "authorization", "allowed": allowed, "reason": reason, "matched": matched}

    # Fallback
    return _eval_roles(roles=roles, action=action, resource=resource, policy=policy)


# ─────────────────────────────────────────────────────────────────────────────
# Action handlers
# ─────────────────────────────────────────────────────────────────────────────
def _act_check(payload: dict[str, Any]) -> dict[str, Any]:
    policy = _load_policies()
    principal = payload.get("principal")
    roles = payload.get("roles") or payload.get("role") or []
    if isinstance(roles, str):
        roles = [roles]
    # Use 'op' for the permission operation to avoid conflict with tool 'action'
    op = str(payload.get("op") or payload.get("context", {}).get("action") or "invoke")
    resource = str(payload.get("resource") or "")
    context = payload.get("context") or {}

    if not resource:
        raise ValueError("resource is required")

    decision = _check_with_engine(
        principal=principal,
        roles=roles,
        action=op,  # permission action (invoke, read, write, etc.)
        resource=resource,
        context=context,
        policy=policy,
    )
    return {
        "ok": True,
        "action": "check",
        "allowed": bool(decision.get("allowed", False)),
        "decision": decision,
        "policy_version": _policy_version(policy),
        "principal": principal,
        "roles": list(roles),
        "resource": resource,
        "op": op,
    }


def _act_resolve(payload: dict[str, Any]) -> dict[str, Any]:
    policy = _load_policies()
    roles = payload.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    resources = payload.get("resources") or ["*"]
    actions = payload.get("actions") or ["invoke"]

    details: list[dict[str, Any]] = []
    for res in resources:
        for act in actions:
            dec = _check_with_engine(
                principal=None, roles=roles, action=str(act), resource=str(res), context={}, policy=policy
            )
            details.append(
                {
                    "resource": res,
                    "action": act,
                    "allowed": bool(dec.get("allowed", False)),
                    "reason": dec.get("reason"),
                    "matched": dec.get("matched"),
                }
            )
    total = len(details)
    allowed = sum(1 for d in details if d["allowed"])
    summary = {
        "total": total,
        "allowed": allowed,
        "denied": total - allowed,
        "ratio_allowed": (allowed / total if total else 0.0),
    }

    return {
        "ok": True,
        "action": "resolve",
        "summary": summary,
        "details": details,
        "roles": list(roles),
        "policy_version": _policy_version(policy),
    }


def _act_list_roles(payload: dict[str, Any]) -> dict[str, Any]:
    policy = _load_policies()
    roles_spec = (policy.get("roles") or {}) if isinstance(policy, dict) else {}
    out: list[dict[str, Any]] = []
    for name, spec in roles_spec.items():
        allow = list((spec or {}).get("allow") or [])
        deny = list((spec or {}).get("deny") or [])
        desc = (spec or {}).get("description")
        out.append({"name": name, "allow": len(allow), "deny": len(deny), "description": desc})
    return {"ok": True, "action": "list_roles", "roles": out, "policy_version": _policy_version(policy)}


def _act_reload(_: dict[str, Any]) -> dict[str, Any]:
    if callable(_RELOAD_POLICIES):
        with suppress(Exception):
            pol = _RELOAD_POLICIES()
            if isinstance(pol, dict):
                return {"ok": True, "action": "reload", "policy_version": _policy_version(pol)}
            if isinstance(pol, tuple) and isinstance(pol[0], dict):
                return {"ok": True, "action": "reload", "policy_version": _policy_version(pol[0])}
    # Best-effort: re-read via loader
    pol = _load_policies()
    return {"ok": True, "action": "reload", "policy_version": _policy_version(pol)}


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────
@mcp_tool(tool_name="security.permissions", required_scope="tools:basic")
def invoke(ctx: ToolContext, payload: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
    """
    Entry for security.permissions tool.
    """
    payload = payload or {}

    # Pydantic validation
    validated = SecurityPermissionsPayload(**payload)
    action = validated.action

    # Merge: start with original payload, overlay with validated defaults for fields with defaults
    validated_dict = {**payload}
    for field_name, field_info in SecurityPermissionsPayload.model_fields.items():
        if field_info.default is not None and field_info.default != ...:
            if field_name not in payload:
                validated_dict[field_name] = getattr(validated, field_name)

    if action == "check":
        return _act_check(validated_dict)
    if action == "resolve":
        return _act_resolve(validated_dict)
    if action == "list_roles":
        return _act_list_roles(validated_dict)
    if action == "reload":
        return _act_reload(validated_dict)

    raise ValueError("action must be one of: check, resolve, list_roles, reload")


# Back-compat aliases
run = invoke
handle = invoke
