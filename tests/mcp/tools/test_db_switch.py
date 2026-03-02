"""Minimal tests for db.switch MCP tool - verifies modernization is working.

These tests verify:
1. The tool is callable
2. @mcp_tool decorator is working
3. Authentication is enforced
4. Basic actions work
"""

import pytest
from src.mcp.tools.db.switch import invoke


def test_invoke_requires_authentication():
    """Verify that tool requires principal (authentication)."""
    payload = {"action": "get"}
    result = invoke(payload)

    # Should fail due to missing principal
    assert result["ok"] is False
    assert result["code"] == "E_PERMISSION"


def test_invoke_with_auth_works():
    """Verify that tool works with proper authentication."""
    payload = {
        "action": "get",
        "principal": "admin@example.org",
        "tenant": "test-tenant",
    }

    result = invoke(payload)

    # Should succeed with auth
    assert result["ok"] is True
    assert result["action"] == "get"
    assert "host" in result


def test_schema_validation():
    """Verify Pydantic schema validation is working."""
    payload = {
        "action": "invalid_action",  # Not a valid DbSwitchAction
        "principal": "admin@example.org",
    }

    result = invoke(payload)

    # Should fail validation
    assert result["ok"] is False
