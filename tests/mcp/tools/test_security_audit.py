"""Tests for security.audit MCP tool.

Following P2 pattern - testing internal _act_* functions directly.

Coverage:
- Action: access (4 tests)
- Action: custom (3 tests)
- Action: list (7 tests)
- Action: stats (2 tests)
- Action: clear (3 tests)
- PII redaction (2 tests)
- Security (1 test)
Total: 22 tests
"""

import pytest
from unittest.mock import MagicMock, patch
from src.mcp.runtime import ToolContext
import src.mcp.tools.security.audit as audit_module


@pytest.fixture
def ctx():
    """Standard tool context."""
    return ToolContext(
        principal="admin@example.org",
        tenant="test-tenant",
        trace_id="trace-123",
        scopes={"tools:admin"},
        tool="security.audit",
        action="test",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Action: access (4 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_access_records_event(ctx):
    """access records an access control decision."""
    with patch.object(audit_module, "_SINK") as mock_sink:
        result = audit_module._act_access(
            ctx,
            {
                "principal": "user@example.org",
                "resource": "mcp.tools.graph.query",
                "allowed": True,
                "reason": "policy:allow",
            },
        )

    assert result["ok"] is True
    assert result["action"] == "access"
    assert "event" in result

    event = result["event"]
    assert event["principal"] == "user@example.org"
    assert event["resource"] == "mcp.tools.graph.query"
    assert event["allowed"] is True
    assert event["reason"] == "policy:allow"
    assert "id" in event
    assert "ts" in event

    mock_sink.emit.assert_called_once()


def test_access_includes_trace_id(ctx):
    """access events include trace_id for correlation."""
    with patch.object(audit_module, "_SINK"):
        result = audit_module._act_access(
            ctx,
            {
                "principal": "user@example.org",
                "resource": "test.resource",
            },
        )

    assert result["event"]["trace_id"] == "trace-123"


def test_access_defaults(ctx):
    """access uses defaults for optional fields."""
    with patch.object(audit_module, "_SINK"):
        result = audit_module._act_access(
            ctx,
            {
                "principal": "user@example.org",
                "resource": "test.resource",
            },
        )

    event = result["event"]
    assert event["allowed"] is True  # Default
    assert event["tenant"] == "test-tenant"  # From ctx


def test_access_includes_attributes(ctx):
    """access includes attributes dict."""
    with patch.object(audit_module, "_SINK"):
        result = audit_module._act_access(
            ctx,
            {
                "principal": "user@example.org",
                "resource": "test.resource",
                "attributes": {"route": "/api/test", "method": "POST"},
            },
        )

    event = result["event"]
    assert event["attributes"]["route"] == "/api/test"
    assert event["attributes"]["method"] == "POST"


# ──────────────────────────────────────────────────────────────────────────────
# Action: custom (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_custom_records_free_form_event(ctx):
    """custom records arbitrary events."""
    with patch.object(audit_module, "_SINK") as mock_sink:
        result = audit_module._act_custom(
            ctx,
            {
                "name": "model.updated",
                "data": {"model_id": "123", "version": 2},
            },
        )

    assert result["ok"] is True
    assert result["action"] == "custom"
    event = result["event"]
    assert event["name"] == "model.updated"
    assert event["data"]["model_id"] == "123"
    assert event["data"]["version"] == 2

    mock_sink.emit.assert_called_once()


def test_custom_defaults_name(ctx):
    """custom defaults name to 'custom'."""
    with patch.object(audit_module, "_SINK"):
        result = audit_module._act_custom(ctx, {"data": {"key": "value"}})

    assert result["event"]["name"] == "custom"


def test_custom_includes_trace_id(ctx):
    """custom events include trace_id."""
    with patch.object(audit_module, "_SINK"):
        result = audit_module._act_custom(
            ctx,
            {
                "name": "test.event",
                "data": {},
            },
        )

    assert result["event"]["trace_id"] == "trace-123"


# ──────────────────────────────────────────────────────────────────────────────
# Action: list (7 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_list_returns_events(ctx):
    """list returns paginated events."""
    mock_events = [
        {"id": "evt-1", "principal": "user1@example.org", "action": "read"},
        {"id": "evt-2", "principal": "user2@example.org", "action": "write"},
    ]

    with patch.object(audit_module._SINK, "list", return_value=(2, mock_events)):
        result = audit_module._act_list(ctx, {"limit": 100, "offset": 0})

    assert result["ok"] is True
    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert result["limit"] == 100
    assert result["offset"] == 0


def test_list_caps_limit(ctx):
    """list caps limit at 1000."""
    with patch.object(audit_module._SINK, "list", return_value=(0, [])) as mock_list:
        audit_module._act_list(ctx, {"limit": 5000})

    # Check that list was called with capped limit
    call_kwargs = mock_list.call_args[1]
    assert call_kwargs["limit"] == 1000


def test_list_respects_filters(ctx):
    """list passes filters to sink."""
    with patch.object(audit_module._SINK, "list", return_value=(0, [])) as mock_list:
        audit_module._act_list(
            ctx,
            {
                "tenant": "test-tenant",
                "principal": "user@example.org",
                "action": "read",
                "resource_substr": "graph",
                "allowed": False,
                "since": "2025-10-01T00:00:00Z",
                "until": "2025-10-31T23:59:59Z",
            },
        )

    call_kwargs = mock_list.call_args[1]
    assert call_kwargs["tenant"] == "test-tenant"
    assert call_kwargs["principal"] == "user@example.org"
    assert call_kwargs["action"] == "read"
    assert call_kwargs["resource_substr"] == "graph"
    assert call_kwargs["allowed"] is False
    assert call_kwargs["since"] == "2025-10-01T00:00:00Z"
    assert call_kwargs["until"] == "2025-10-31T23:59:59Z"


def test_list_redacts_pii_for_others(ctx):
    """list redacts PII when principal doesn't match."""
    mock_events = [
        {
            "id": "evt-1",
            "principal": "other@example.org",
            "ip": "203.0.113.5",
            "user_agent": "Mozilla/5.0",
        }
    ]

    with patch.object(audit_module._SINK, "list", return_value=(1, mock_events)):
        result = audit_module._act_list(ctx, {})

    item = result["items"][0]
    assert item["principal"] == "***@***.***"
    assert item["ip"] == "***.***.***.***"


def test_list_preserves_pii_for_self(ctx):
    """list preserves PII when principal matches."""
    mock_events = [
        {
            "id": "evt-1",
            "principal": "admin@example.org",  # Matches ctx.principal
            "ip": "203.0.113.5",
        }
    ]

    with patch.object(audit_module._SINK, "list", return_value=(1, mock_events)):
        result = audit_module._act_list(ctx, {})

    item = result["items"][0]
    assert item["principal"] == "admin@example.org"
    assert item["ip"] == "203.0.113.5"


def test_list_handles_error_gracefully(ctx):
    """list returns empty on error."""
    with patch.object(audit_module._SINK, "list", side_effect=Exception("Sink error")):
        result = audit_module._act_list(ctx, {})

    assert result["ok"] is True
    assert result["total"] == 0
    assert result["items"] == []


def test_list_pagination(ctx):
    """list respects offset and limit."""
    with patch.object(audit_module._SINK, "list", return_value=(100, [])) as mock_list:
        result = audit_module._act_list(ctx, {"limit": 50, "offset": 25})

    assert result["limit"] == 50
    assert result["offset"] == 25

    call_kwargs = mock_list.call_args[1]
    assert call_kwargs["limit"] == 50
    assert call_kwargs["offset"] == 25


# ──────────────────────────────────────────────────────────────────────────────
# Action: stats (2 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_stats_returns_aggregates(ctx):
    """stats returns aggregate statistics."""
    mock_stats = {
        "total": 100,
        "allowed": 80,
        "denied": 20,
        "by_action": {"read": 60, "write": 30, "delete": 10},
    }

    with patch.object(audit_module._SINK, "stats", return_value=mock_stats):
        result = audit_module._act_stats(ctx, {"tenant": "test-tenant"})

    assert result["ok"] is True
    assert result["stats"]["total"] == 100
    assert result["stats"]["allowed"] == 80
    assert result["stats"]["denied"] == 20
    assert result["stats"]["by_action"]["read"] == 60


def test_stats_handles_error_gracefully(ctx):
    """stats returns empty stats on error."""
    with patch.object(audit_module._SINK, "stats", side_effect=Exception("Error")):
        result = audit_module._act_stats(ctx, {})

    assert result["ok"] is True
    assert result["stats"] == {"total": 0, "allowed": 0, "denied": 0, "by_action": {}}


# ──────────────────────────────────────────────────────────────────────────────
# Action: clear (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_clear_requires_confirm(ctx):
    """clear requires confirm=true."""
    with pytest.raises(ValueError, match="clear requires 'confirm': true"):
        audit_module._act_clear(ctx, {})


def test_clear_removes_events(ctx):
    """clear removes events and returns count."""
    with patch.object(audit_module._SINK, "clear", return_value=42):
        result = audit_module._act_clear(
            ctx,
            {
                "confirm": True,
                "tenant": "test-tenant",
            },
        )

    assert result["ok"] is True
    assert result["cleared"] is True
    assert result["count"] == 42


def test_clear_handles_error_gracefully(ctx):
    """clear returns cleared=False on error."""
    with patch.object(audit_module._SINK, "clear", side_effect=Exception("Error")):
        result = audit_module._act_clear(ctx, {"confirm": True})

    assert result["ok"] is True
    assert result["cleared"] is False
    assert result["count"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# PII Redaction (2 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_pii_redaction_emails():
    """Email addresses are redacted."""
    text = "Contact user@example.org or admin@test.com"
    redacted = audit_module._redact_pii(text)
    assert "user@example.org" not in redacted
    assert "admin@test.com" not in redacted
    assert "***@***.***" in redacted


def test_pii_redaction_ips():
    """IP addresses are redacted."""
    text = "Request from 192.168.1.100 and 10.0.0.1"
    redacted = audit_module._redact_pii(text)
    assert "192.168.1.100" not in redacted
    assert "10.0.0.1" not in redacted
    assert "***.***.***.***" in redacted


# ──────────────────────────────────────────────────────────────────────────────
# Security & RBAC (1 test)
# ──────────────────────────────────────────────────────────────────────────────


def test_decorated_function_exists():
    """security.audit decorated function exists."""
    assert hasattr(audit_module, "security_audit")
    assert callable(audit_module.security_audit)
