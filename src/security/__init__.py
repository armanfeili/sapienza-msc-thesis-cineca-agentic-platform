"""
Security package — centralized access to authN/Z, guards, PII scrubbing, policies,
rate limiting, and tenancy helpers.

This package exposes a thin, **lazy-imported** facade so callers can write:

    from src.security import create_access_token, authorize, guard_cypher
    from src.security import scrub_text, rate_limiter, require_tenant

Nothing is imported until you first access an attribute, which keeps startup
fast and avoids circular imports.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict

# Map public names -> (module, attribute)
_EXPORTS: dict[str, tuple[str, str]] = {
    # ── Audit ─────────────────────────────────────────────────────────────────
    "AuditEvent": ("src.security.audit", "AuditEvent"),
    "audit_event": ("src.security.audit", "audit_event"),
    "audit_auth_success": ("src.security.audit", "audit_auth_success"),
    "audit_auth_failure": ("src.security.audit", "audit_auth_failure"),
    "audit_access": ("src.security.audit", "audit_access"),
    "audit_policy_decision": ("src.security.audit", "audit_policy_decision"),
    "audit_rate_limit": ("src.security.audit", "audit_rate_limit"),
    "audit_model_usage": ("src.security.audit", "audit_model_usage"),
    "audit_data_access": ("src.security.audit", "audit_data_access"),
    # ── Auth (OIDC JWT) ──────────────────────────────────────────────────────
    "bearer_required": ("src.security.jwt", "bearer_required"),
    "validate_jwt": ("src.security.jwt", "validate_jwt"),
    "get_current_principal": ("src.security.jwt", "get_current_principal"),
    # Note: `require_scopes` is exported from authorization below to keep a single source
    # ── Authorization ─────────────────────────────────────────────────────────
    "AuthzDecision": ("src.security.authorization", "AuthzDecision"),
    "check_scopes": ("src.security.authorization", "check_scopes"),
    "authorize": ("src.security.authorization", "authorize"),
    "authorize_or_403": ("src.security.authorization", "authorize_or_403"),
    "require_scopes": ("src.security.authorization", "require_scopes"),
    # ── Permissions (Auth0-style) ───────────────────────────────────────────
    "current_permissions": ("src.security.perm", "current_permissions"),
    "has_perms": ("src.security.perm", "has_perms"),
    "enforce_perms": ("src.security.perm", "enforce_perms"),
    "require_perms": ("src.security.perm", "require_perms"),
    # ── Validators ────────────────────────────────────────────────────────────
    "Issue": ("src.security.validators", "Issue"),
    "ValidationProblem": ("src.security.validators", "ValidationProblem"),
    "raise_http_422": ("src.security.validators", "raise_http_422"),
    "http_400": ("src.security.validators", "http_400"),
    "normalize_whitespace": ("src.security.validators", "normalize_whitespace"),
    "ensure_str": ("src.security.validators", "ensure_str"),
    "ensure_int": ("src.security.validators", "ensure_int"),
    "ensure_float": ("src.security.validators", "ensure_float"),
    "ensure_bool": ("src.security.validators", "ensure_bool"),
    "ensure_list": ("src.security.validators", "ensure_list"),
    "ensure_dict": ("src.security.validators", "ensure_dict"),
    "validate_identifier": ("src.security.validators", "validate_identifier"),
    "validate_pagination": ("src.security.validators", "validate_pagination"),
    "validate_sort": ("src.security.validators", "validate_sort"),
    "safe_json_loads": ("src.security.validators", "safe_json_loads"),
    "validate_result_limits": ("src.security.validators", "validate_result_limits"),
    "validate_query_cost": ("src.security.validators", "validate_query_cost"),
    "validate_fields": ("src.security.validators", "validate_fields"),
    # ── Intent filter ─────────────────────────────────────────────────────────
    "IntentResult": ("src.security.intent_filter", "IntentResult"),
    "analyze_intent": ("src.security.intent_filter", "analyze_intent"),
    "enforce_intent": ("src.security.intent_filter", "enforce_intent"),
    # ── Output guard ──────────────────────────────────────────────────────────
    "CypherAnalysis": ("src.security.output_guard", "CypherAnalysis"),
    "OutputGuardResult": ("src.security.output_guard", "OutputGuardResult"),
    "analyze_cypher": ("src.security.output_guard", "analyze_cypher"),
    "guard_cypher": ("src.security.output_guard", "guard_cypher"),
    "ensure_cypher_limit": ("src.security.output_guard", "ensure_cypher_limit"),
    "guard_text": ("src.security.output_guard", "guard_text"),
    # ── PII scrubber ──────────────────────────────────────────────────────────
    "scrub_text": ("src.security.pii_scrubber", "scrub_text"),
    "scrub": ("src.security.pii_scrubber", "scrub"),
    "scrub_dict": ("src.security.pii_scrubber", "scrub_dict"),
    "find_pii": ("src.security.pii_scrubber", "find_pii"),
    "contains_pii": ("src.security.pii_scrubber", "contains_pii"),
    # ── Policies loader ───────────────────────────────────────────────────────
    "PolicyBundle": ("src.security.policies_loader", "PolicyBundle"),
    "get_bundle": ("src.security.policies_loader", "get_bundle"),
    "refresh_if_changed": ("src.security.policies_loader", "refresh_if_changed"),
    "get_roles": ("src.security.policies_loader", "get_roles"),
    "get_scopes_for_role": ("src.security.policies_loader", "get_scopes_for_role"),
    "get": ("src.security.policies_loader", "get"),
    "describe": ("src.security.policies_loader", "describe"),
    # ── Rate limit ────────────────────────────────────────────────────────────
    "RateLimitResult": ("src.security.rate_limit", "RateLimitResult"),
    "rate_limit_check": ("src.security.rate_limit", "rate_limit_check"),
    "rate_limiter": ("src.security.rate_limit", "rate_limiter"),
    "get_backend": ("src.security.rate_limit", "get_backend"),
    # ── Tenancy ───────────────────────────────────────────────────────────────
    "TenantContext": ("src.security.tenants", "TenantContext"),
    "set_current_tenant": ("src.security.tenants", "set_current_tenant"),
    "get_current_tenant": ("src.security.tenants", "get_current_tenant"),
    "select_tenant": ("src.security.tenants", "select_tenant"),
    "enforce_tenant": ("src.security.tenants", "enforce_tenant"),
    "require_tenant": ("src.security.tenants", "require_tenant"),
    "tenantize_key": ("src.security.tenants", "tenantize_key"),
}

__all__ = list(_EXPORTS.keys())


def __getattr__(name: str) -> Any:
    """PEP 562: lazily import security symbols on first access."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod_name, attr = _EXPORTS[name]
    module = importlib.import_module(mod_name)
    value = getattr(module, attr)
    globals()[name] = value  # cache for future lookups
    return value


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
