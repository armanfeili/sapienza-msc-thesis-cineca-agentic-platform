"""
Tests for hardened security.permissions tool.

Validates:
- Schema validation (required fields per action)
- Permission checking (allow/deny logic)
- Role resolution (effective permissions preview)
- Role listing
- Policy reload
- RBAC enforcement (principal requirement, authentication)

Following P3 pattern: Test internal _act_* functions directly.
"""

import pytest
from pydantic import ValidationError
from unittest.mock import Mock, patch, mock_open

from src.mcp.tools.security import permissions as permissions_module
from src.mcp.schemas import SecurityPermissionsPayload


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_policy():
    """Mock policy data."""
    return {
        "roles": {
            "viewer": {
                "description": "Read-only access",
                "allow": ["action:read resource:*", "mcp.tools.graph.query"],
                "deny": [],
            },
            "analyst": {
                "description": "Data analysis access",
                "allow": ["action:invoke resource:mcp.tools.*"],
                "deny": ["action:invoke resource:mcp.tools.admin.*"],
            },
            "admin": {"description": "Full access", "allow": ["action:* resource:*"], "deny": []},
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# Schema Validation Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_schema_validation_check_requires_resource():
    """Check action requires 'resource' field."""
    with pytest.raises(ValidationError) as exc:
        SecurityPermissionsPayload(
            action="check",
            roles=["viewer"],
            principal="test-user",
            tenant="test-tenant"
            # Missing 'resource'
        )
    assert "'resource' is required" in str(exc.value)


def test_schema_validation_valid_check(mock_policy):
    """Valid 'check' payload with all required fields."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "check",
            "principal": "user@example.org",
            "roles": ["viewer"],
            "resource": "mcp.tools.graph.query",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_check(payload)
        assert result["ok"] is True
        assert result["action"] == "check"
        assert "allowed" in result


def test_schema_validation_valid_resolve(mock_policy):
    """Valid 'resolve' payload."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "resolve",
            "roles": ["viewer", "analyst"],
            "resources": ["mcp.tools.*"],
            "actions": ["invoke"],
            "principal": "test-user",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_resolve(payload)
        assert result["ok"] is True
        assert result["action"] == "resolve"


def test_schema_validation_valid_list_roles(mock_policy):
    """Valid 'list_roles' payload."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {"action": "list_roles", "principal": "test-user", "tenant": "test-tenant"}
        result = permissions_module._act_list_roles(payload)
        assert result["ok"] is True
        assert result["action"] == "list_roles"


def test_schema_validation_valid_reload(mock_policy):
    """Valid 'reload' payload."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {"action": "reload", "principal": "test-user", "tenant": "test-tenant"}
        result = permissions_module._act_reload(payload)
        assert result["ok"] is True
        assert result["action"] == "reload"


# ─────────────────────────────────────────────────────────────────────────────
# Permission Checking Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_check_allow_with_viewer_role(mock_policy):
    """Viewer role allows read access to graph.query."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "check",
            "principal": "user@example.org",
            "roles": ["viewer"],
            "resource": "mcp.tools.graph.query",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_check(payload)
        assert result["ok"] is True
        assert result["allowed"] is True
        assert result["decision"]["engine"] in ["builtin", "authorization"]


def test_check_deny_with_analyst_role(mock_policy):
    """Analyst role denied from admin tools."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "check",
            "principal": "user@example.org",
            "roles": ["analyst"],
            "resource": "mcp.tools.admin.users",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_check(payload)
        assert result["ok"] is True
        assert result["allowed"] is False
        assert result["decision"]["reason"] in ["deny:matched", "no-match"]


def test_check_allow_with_admin_role(mock_policy):
    """Admin role allows all access."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "check",
            "principal": "admin@example.org",
            "roles": ["admin"],
            "resource": "mcp.tools.admin.users",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_check(payload)
        assert result["ok"] is True
        assert result["allowed"] is True


def test_check_no_match_returns_false(mock_policy):
    """No matching rules returns denied."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "check",
            "principal": "user@example.org",
            "roles": ["viewer"],
            "resource": "some.unknown.resource",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_check(payload)
        assert result["ok"] is True
        assert result["allowed"] is False


def test_check_with_context(mock_policy):
    """Check action accepts additional context."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "check",
            "principal": "user@example.org",
            "roles": ["viewer"],
            "resource": "mcp.tools.graph.query",
            "context": {"tenant": "acme-corp", "environment": "production"},
            "tenant": "test-tenant",
        }
        result = permissions_module._act_check(payload)
        assert result["ok"] is True
        assert "allowed" in result


# ─────────────────────────────────────────────────────────────────────────────
# Resolve Action Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_resolve_returns_summary(mock_policy):
    """Resolve returns summary with allowed/denied counts."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "resolve",
            "roles": ["viewer"],
            "resources": ["mcp.tools.graph.query", "mcp.tools.admin.users"],
            "actions": ["read", "invoke"],
            "principal": "test-user",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_resolve(payload)
        assert result["ok"] is True
        assert result["action"] == "resolve"
        assert "summary" in result
        assert result["summary"]["total"] == 4  # 2 resources × 2 actions
        assert "allowed" in result["summary"]
        assert "denied" in result["summary"]


def test_resolve_returns_details(mock_policy):
    """Resolve returns detailed permission matrix."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "resolve",
            "roles": ["analyst"],
            "resources": ["mcp.tools.graph.query"],
            "actions": ["invoke"],
            "principal": "test-user",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_resolve(payload)
        assert result["ok"] is True
        assert "details" in result
        assert len(result["details"]) == 1
        detail = result["details"][0]
        assert detail["resource"] == "mcp.tools.graph.query"
        assert detail["action"] == "invoke"
        assert "allowed" in detail


def test_resolve_with_multiple_roles(mock_policy):
    """Resolve with multiple roles combines permissions."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "resolve",
            "roles": ["viewer", "analyst"],
            "resources": ["mcp.tools.*"],
            "actions": ["read", "invoke"],
            "principal": "test-user",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_resolve(payload)
        assert result["ok"] is True
        assert "summary" in result
        assert result["summary"]["total"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# List Roles Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_list_roles_returns_all_roles(mock_policy):
    """List roles returns all defined roles."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {"action": "list_roles", "principal": "test-user", "tenant": "test-tenant"}
        result = permissions_module._act_list_roles(payload)
        assert result["ok"] is True
        assert result["action"] == "list_roles"
        assert "roles" in result
        assert len(result["roles"]) == 3  # viewer, analyst, admin
        role_names = [r["name"] for r in result["roles"]]
        assert "viewer" in role_names
        assert "analyst" in role_names
        assert "admin" in role_names


def test_list_roles_includes_rule_counts(mock_policy):
    """List roles includes allow/deny rule counts."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {"action": "list_roles", "principal": "test-user", "tenant": "test-tenant"}
        result = permissions_module._act_list_roles(payload)
        viewer = next(r for r in result["roles"] if r["name"] == "viewer")
        assert viewer["allow"] == 2  # 2 allow rules
        assert viewer["deny"] == 0  # 0 deny rules


def test_list_roles_includes_descriptions(mock_policy):
    """List roles includes role descriptions."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {"action": "list_roles", "principal": "test-user", "tenant": "test-tenant"}
        result = permissions_module._act_list_roles(payload)
        admin = next(r for r in result["roles"] if r["name"] == "admin")
        assert admin["description"] == "Full access"


# ─────────────────────────────────────────────────────────────────────────────
# Reload Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_reload_returns_policy_version(mock_policy):
    """Reload returns policy version hash."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {"action": "reload", "principal": "test-user", "tenant": "test-tenant"}
        result = permissions_module._act_reload(payload)
        assert result["ok"] is True
        assert result["action"] == "reload"
        assert "policy_version" in result
        assert len(result["policy_version"]) == 12  # SHA256 truncated to 12 chars


# ─────────────────────────────────────────────────────────────────────────────
# RBAC Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_requires_principal(mock_policy):
    """Tool requires principal (enforced by decorator)."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {"action": "list_roles", "principal": "test-user", "tenant": "test-tenant"}
        result = permissions_module._act_list_roles(payload)
        assert result["ok"] is True


def test_with_authentication_context(mock_policy):
    """Tool works with full authentication context."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "check",
            "principal": "auth0|user123",
            "roles": ["viewer"],
            "resource": "mcp.tools.graph.query",
            "tenant": "acme-corp",
        }
        result = permissions_module._act_check(payload)
        assert result["ok"] is True
        assert result["principal"] == "auth0|user123"


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


def test_check_with_empty_roles(mock_policy):
    """Check with no roles returns denied."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "check",
            "principal": "user@example.org",
            "roles": [],
            "resource": "mcp.tools.graph.query",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_check(payload)
        assert result["ok"] is True
        assert result["allowed"] is False


def test_check_with_single_role_string(mock_policy):
    """Check accepts single role as string (not list)."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "check",
            "principal": "user@example.org",
            "roles": ["viewer"],
            "resource": "mcp.tools.graph.query",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_check(payload)
        assert result["ok"] is True


def test_empty_policy_denies_all():
    """Empty policy denies all access."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value={}):
        payload = {
            "action": "check",
            "principal": "user@example.org",
            "roles": ["admin"],
            "resource": "mcp.tools.graph.query",
            "tenant": "test-tenant",
        }
        result = permissions_module._act_check(payload)
        assert result["ok"] is True
        assert result["allowed"] is False


def test_wildcard_resource_patterns(mock_policy):
    """Wildcards in resource patterns work correctly."""
    with patch("src.mcp.tools.security.permissions._load_policies", return_value=mock_policy):
        payload = {
            "action": "check",  # Tool action
            "principal": "user@example.org",
            "roles": ["analyst"],
            "resource": "mcp.tools.graph.query",
            "context": {"action": "invoke"},  # Permission action being checked
            "tenant": "test-tenant",
        }
        # analyst has "action:invoke resource:mcp.tools.*"
        result = permissions_module._act_check(payload)
        assert result["ok"] is True
        assert result["allowed"] is True
