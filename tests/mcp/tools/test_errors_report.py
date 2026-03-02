"""Minimal tests for errors.report MCP tool - verifies modernization is working.

These tests verify:
1. The tool is callable
2. @mcp_tool decorator is working  
3. Authentication is enforced
4. Basic error reporting works
"""

import pytest
from src.mcp.tools.errors.report import invoke


def test_invoke_requires_authentication():
    """Verify that tool requires principal (authentication)."""
    payload = {"message": "Test error"}
    result = invoke(payload)

    # Should fail due to missing principal
    assert result["ok"] is False
    assert result["code"] == "E_PERMISSION"


def test_invoke_with_auth_works():
    """Verify that tool works with proper authentication."""
    payload = {
        "message": "Test error",
        "principal": "user@example.org",
        "tenant": "test-tenant",
    }

    result = invoke(payload)

    # Should succeed with auth
    assert result["ok"] is True
    assert "event" in result


def test_schema_validation():
    """Verify Pydantic schema validation is working."""
    payload = {
        "severity": "invalid_severity",  # Not a valid severity
        "principal": "user@example.org",
    }

    result = invoke(payload)

    # Should fail validation (message is required)
    assert result["ok"] is False
