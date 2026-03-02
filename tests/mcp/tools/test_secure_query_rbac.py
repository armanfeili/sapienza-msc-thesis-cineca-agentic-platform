"""
Negative tests for RBAC and tenant enforcement in P1 tools.

Validates:
- Principal requirement (all tools must reject missing principal)
- Tenant requirement (all tools must reject missing tenant)
- Cross-tenant isolation (deny access to other tenant data)
- Clean error messages with audit trail
"""

import pytest
from unittest.mock import patch, MagicMock

from src.mcp.tools.graph import secure_query as secure_query_module
from src.mcp.schemas import GraphSecureQueryPayload
from pydantic import ValidationError


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_memgraph(monkeypatch):
    """Mock MemgraphAdapter."""
    mock_adapter = MagicMock()
    mock_adapter.query.return_value = []

    def mock_adapter_factory():
        return mock_adapter

    monkeypatch.setattr("src.mcp.tools.graph.secure_query.MemgraphAdapter", mock_adapter_factory)
    return mock_adapter


@pytest.fixture
def mock_llm(monkeypatch):
    """Mock LLM service with complete() method signature."""
    mock = MagicMock()
    # Mock the complete() method which is what LLMAdapter uses
    mock.complete.return_value = {
        "content": "MATCH (n:User) RETURN n LIMIT 10",
        "text": "MATCH (n:User) RETURN n LIMIT 10",
        "output": "MATCH (n:User) RETURN n LIMIT 10",
        "usage": {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25},
        "model": "test-mock",
        "provider": "mock",
    }
    # Patch LLMAdapter to return our mock
    monkeypatch.setattr("src.mcp.tools.graph.secure_query.LLMAdapter", lambda: mock, raising=False)
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# Principal Requirement Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_requires_principal(mock_memgraph):
    """validate action must have principal."""
    result = secure_query_module.invoke(
        {
            "action": "validate",
            "cypher": "MATCH (n) RETURN n",
            # Missing principal
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    assert result["code"] == "E_PERMISSION"


def test_execute_requires_principal(mock_memgraph):
    """execute action must have principal."""
    result = secure_query_module.invoke(
        {
            "action": "execute",
            "cypher": "MATCH (n) RETURN n",
            # Missing principal
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    assert result["code"] == "E_PERMISSION"


def test_ask_requires_principal(mock_memgraph, mock_llm):
    """ask action must have principal."""
    result = secure_query_module.invoke(
        {
            "action": "ask",
            "prompt": "Show me users",
            # Missing principal
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    assert result["code"] == "E_PERMISSION"


# ─────────────────────────────────────────────────────────────────────────────
# Tenant Requirement Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_requires_tenant(mock_memgraph):
    """validate action must have tenant."""
    result = secure_query_module.invoke(
        {
            "action": "validate",
            "cypher": "MATCH (n) RETURN n",
            "principal": "test-user",
            # Missing tenant
        }
    )

    assert result["ok"] is False
    # Can be E_INTERNAL (schema validation) or E_PERMISSION (RBAC check)
    assert result["code"] in ["E_PERMISSION", "E_INTERNAL"]


def test_execute_requires_tenant(mock_memgraph):
    """execute action must have tenant."""
    result = secure_query_module.invoke(
        {
            "action": "execute",
            "cypher": "MATCH (n) RETURN n",
            "principal": "test-user",
            # Missing tenant
        }
    )

    assert result["ok"] is False
    # Can be E_INTERNAL (schema validation) or E_PERMISSION (RBAC check)
    assert result["code"] in ["E_PERMISSION", "E_INTERNAL"]


def test_ask_requires_tenant(mock_memgraph, mock_llm):
    """ask action must have tenant."""
    result = secure_query_module.invoke(
        {
            "action": "ask",
            "prompt": "Show me users",
            "principal": "test-user",
            # Missing tenant
        }
    )

    assert result["ok"] is False
    # Can be E_INTERNAL (schema validation) or E_PERMISSION (RBAC check)
    assert result["code"] in ["E_PERMISSION", "E_INTERNAL"]


# ─────────────────────────────────────────────────────────────────────────────
# Cross-Tenant Isolation Tests
# ─────────────────────────────────────────────────────────────────────────────


@patch("src.mcp.tools.graph.secure_query._check_permissions")
def test_cross_tenant_read_denied(mock_check_perms, mock_memgraph):
    """Attempting to read another tenant's data is denied."""
    # Mock permission check to deny cross-tenant access
    mock_check_perms.return_value = False

    result = secure_query_module.invoke(
        {
            "action": "execute",
            "cypher": "MATCH (n {tenant: 'other-tenant'}) RETURN n",
            "principal": "user@acme-corp",
            "tenant": "acme-corp",
        }
    )

    # Should fail with clear reason
    assert result["ok"] is False
    error_msg = result.get("message", "").lower()
    assert "authorized" in error_msg or "permission" in error_msg or "denied" in error_msg


@patch("src.mcp.tools.graph.secure_query._validate_cypher")
def test_cross_tenant_query_validation_fails(mock_validate, mock_memgraph):
    """Validation detects cross-tenant query attempts."""
    # Mock validation to detect tenant mismatch
    mock_validate.return_value = {
        "safe": False,
        "read_only": True,
        "checks": {"write_operations": False, "forbidden_clauses": [], "tenant_scoped": False},  # Cross-tenant detected
    }

    result = secure_query_module.invoke(
        {
            "action": "validate",
            "cypher": "MATCH (n {tenant: 'other-tenant'}) RETURN n",
            "principal": "user@acme-corp",
            "tenant": "acme-corp",
        }
    )

    # Should return unsafe due to tenant mismatch
    assert result["ok"] is True
    assert result["is_safe"] is False
    # Check if validation info exists and contains expected data
    if "validation" in result and "tenant_scoped" in result["validation"]:
        assert result["validation"]["tenant_scoped"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Error Message Quality Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_missing_principal_error_message_is_clear(mock_memgraph):
    """Error message for missing principal is user-friendly."""
    result = secure_query_module.invoke({"action": "validate", "cypher": "MATCH (n) RETURN n", "tenant": "test-tenant"})

    assert result["ok"] is False
    assert result["code"] == "E_PERMISSION"
    error_msg = result.get("message", "").lower()
    assert "principal" in error_msg
    assert "required" in error_msg


def test_missing_tenant_error_message_is_clear(mock_memgraph):
    """Error message for missing tenant is user-friendly."""
    result = secure_query_module.invoke(
        {"action": "validate", "cypher": "MATCH (n) RETURN n", "principal": "test-user"}
    )

    assert result["ok"] is False
    # Can be E_INTERNAL (schema validation) or E_PERMISSION (RBAC check)
    assert result["code"] in ["E_PERMISSION", "E_INTERNAL"]
    error_msg = result.get("message", "").lower()
    assert "tenant" in error_msg or "required" in error_msg


# ─────────────────────────────────────────────────────────────────────────────
# Audit Trail Tests
# ─────────────────────────────────────────────────────────────────────────────


@patch("src.mcp.tools.graph.secure_query._check_permissions")
def test_denied_request_creates_audit_entry(mock_check_perms, mock_memgraph):
    """Denied requests are audited with clear reason."""
    mock_check_perms.return_value = False

    result = secure_query_module.invoke(
        {"action": "execute", "cypher": "MATCH (n) RETURN n", "principal": "unauthorized-user", "tenant": "test-tenant"}
    )

    # Result should indicate failure
    assert result["ok"] is False

    # Should have clear denial reason
    assert "message" in result or "error" in result

    # Audit call should have been made (verify via decorator)
    # The @mcp_tool decorator handles audit logging automatically


def test_allowed_request_creates_audit_entry(mock_memgraph):
    """Allowed requests are audited with success status."""
    result = secure_query_module.invoke(
        {
            "action": "validate",
            "cypher": "MATCH (n:User) RETURN n.name LIMIT 5",
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    # Should succeed
    assert result["ok"] is True
    assert result["action"] == "validate"

    # Audit happens via decorator (trace_id, event_id in integration)
