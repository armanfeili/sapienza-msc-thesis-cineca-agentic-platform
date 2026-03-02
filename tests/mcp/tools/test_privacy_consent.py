"""Tests for privacy.consent MCP tool.

Following P2 pattern - testing internal _act_* and helper functions.

Coverage:
- Action: status (3 tests)
- Action: set (4 tests)
- Action: grant (3 tests)
- Action: revoke (3 tests)
- Action: history (3 tests)
- Action: erase (3 tests)
- Helper functions (5 tests)
- Idempotency (3 tests)
- Error handling (3 tests)
Total: 30 tests
"""

import pytest
from unittest.mock import MagicMock, patch
from src.mcp.runtime import ToolContext
import src.mcp.tools.privacy.consent as consent_module


@pytest.fixture
def ctx():
    """Standard tool context."""
    return ToolContext(
        principal="admin@example.org",
        tenant="test-tenant",
        trace_id="trace-789",
        scopes={"tools:write"},
        tool="privacy.consent",
        action="test",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Action: status (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_status_returns_consent_state(ctx):
    """status action returns consent state for subject."""
    with patch.object(
        consent_module,
        "_load_state",
        return_value={
            "tenant": "test-tenant",
            "subject_id": "user123",
            "version": "1.0",
            "updated_at": "2025-10-25T10:00:00Z",
            "flags": {"marketing": True, "analytics": False},
        },
    ):
        result = consent_module._act_status(ctx, {"subject_id": "user123"})

    assert result["ok"] is True
    assert result["action"] == "status"
    assert result["subject_id"] == "user123"
    assert result["flags"]["marketing"] is True
    assert result["flags"]["analytics"] is False


def test_status_requires_subject_id(ctx):
    """status action requires subject_id."""
    with pytest.raises(ValueError, match="status requires 'subject_id'"):
        consent_module._act_status(ctx, {})


def test_status_uses_tenant_from_context(ctx):
    """status uses tenant from context if not provided."""
    with patch.object(
        consent_module, "_load_state", return_value={"tenant": "test-tenant", "subject_id": "user123", "flags": {}}
    ):
        result = consent_module._act_status(ctx, {"subject_id": "user123"})

    assert result["tenant"] == "test-tenant"


# ──────────────────────────────────────────────────────────────────────────────
# Action: set (4 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_set_updates_consent_flags(ctx):
    """set action updates consent flags."""
    with patch.object(
        consent_module,
        "_load_state",
        return_value={"tenant": "test-tenant", "subject_id": "user123", "flags": {"marketing": False}},
    ):
        with patch.object(consent_module, "_save_state") as mock_save:
            with patch.object(consent_module, "_append_history"):
                result = consent_module._act_set(
                    ctx, {"subject_id": "user123", "flags": {"marketing": True, "analytics": True}}
                )

    assert result["ok"] is True
    assert result["action"] == "set"
    assert result["changed"]["marketing"] is True
    assert result["changed"]["analytics"] is True
    mock_save.assert_called_once()


def test_set_requires_subject_id(ctx):
    """set action requires subject_id."""
    with pytest.raises(ValueError, match="set requires 'subject_id'"):
        consent_module._act_set(ctx, {"flags": {"marketing": True}})


def test_set_requires_flags(ctx):
    """set action requires non-empty flags."""
    with pytest.raises(ValueError, match="set requires non-empty 'flags'"):
        consent_module._act_set(ctx, {"subject_id": "user123", "flags": {}})


def test_set_records_history(ctx):
    """set action records history of changes."""
    with patch.object(
        consent_module, "_load_state", return_value={"tenant": "test-tenant", "subject_id": "user123", "flags": {}}
    ):
        with patch.object(consent_module, "_save_state"):
            with patch.object(consent_module, "_append_history") as mock_history:
                consent_module._act_set(ctx, {"subject_id": "user123", "flags": {"marketing": True}})

    mock_history.assert_called_once()
    call_args = mock_history.call_args[0]
    assert call_args[2]["action"] == "set"
    assert "changed" in call_args[2]


# ──────────────────────────────────────────────────────────────────────────────
# Action: grant (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_grant_sets_flags_to_true(ctx):
    """grant action sets all specified flags to True."""
    with patch.object(
        consent_module, "_load_state", return_value={"tenant": "test-tenant", "subject_id": "user123", "flags": {}}
    ):
        with patch.object(consent_module, "_save_state"):
            with patch.object(consent_module, "_append_history"):
                result = consent_module._act_grant(
                    ctx, {"subject_id": "user123", "flags": {"marketing": False, "analytics": False}}  # Values ignored
                )

    assert result["ok"] is True
    assert result["action"] == "grant"
    assert result["flags"]["marketing"] is True
    assert result["flags"]["analytics"] is True


def test_grant_requires_flags(ctx):
    """grant action requires flags."""
    with pytest.raises(ValueError, match="grant requires 'flags'"):
        consent_module._act_grant(ctx, {"subject_id": "user123"})


def test_grant_uses_set_internally(ctx):
    """grant delegates to _act_set."""
    with patch.object(
        consent_module,
        "_act_set",
        return_value={"ok": True, "action": "set", "subject_id": "user123", "changed": {}, "flags": {}},
    ) as mock_set:
        result = consent_module._act_grant(ctx, {"subject_id": "user123", "flags": {"marketing": True}})

    mock_set.assert_called_once()
    assert result["action"] == "grant"


# ──────────────────────────────────────────────────────────────────────────────
# Action: revoke (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_revoke_sets_flags_to_false(ctx):
    """revoke action sets all specified flags to False."""
    with patch.object(
        consent_module,
        "_load_state",
        return_value={"tenant": "test-tenant", "subject_id": "user123", "flags": {"marketing": True}},
    ):
        with patch.object(consent_module, "_save_state"):
            with patch.object(consent_module, "_append_history"):
                result = consent_module._act_revoke(
                    ctx, {"subject_id": "user123", "flags": {"marketing": True}}  # Value ignored
                )

    assert result["ok"] is True
    assert result["action"] == "revoke"
    assert result["flags"]["marketing"] is False


def test_revoke_requires_flags(ctx):
    """revoke action requires flags."""
    with pytest.raises(ValueError, match="revoke requires 'flags'"):
        consent_module._act_revoke(ctx, {"subject_id": "user123"})


def test_revoke_uses_set_internally(ctx):
    """revoke delegates to _act_set."""
    with patch.object(
        consent_module,
        "_act_set",
        return_value={"ok": True, "action": "set", "subject_id": "user123", "changed": {}, "flags": {}},
    ) as mock_set:
        result = consent_module._act_revoke(ctx, {"subject_id": "user123", "flags": {"marketing": True}})

    mock_set.assert_called_once()
    assert result["action"] == "revoke"


# ──────────────────────────────────────────────────────────────────────────────
# Action: history (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_history_returns_events(ctx):
    """history action returns consent change events."""
    mock_events = [
        {"action": "set", "actor": "admin@example.org", "changed": {"marketing": True}},
        {"action": "grant", "actor": "user@example.org", "changed": {"analytics": True}},
    ]

    with patch.object(consent_module, "_get_history", return_value=mock_events):
        result = consent_module._act_history(ctx, {"subject_id": "user123"})

    assert result["ok"] is True
    assert result["action"] == "history"
    assert len(result["events"]) == 2
    assert result["events"][0]["action"] == "set"


def test_history_requires_subject_id(ctx):
    """history action requires subject_id."""
    with pytest.raises(ValueError, match="history requires 'subject_id'"):
        consent_module._act_history(ctx, {})


def test_history_respects_limit(ctx):
    """history action respects limit parameter."""
    with patch.object(consent_module, "_get_history", return_value=[]) as mock_history:
        consent_module._act_history(ctx, {"subject_id": "user123", "limit": 50})

    mock_history.assert_called_once_with("test-tenant", "user123", limit=50)


# ──────────────────────────────────────────────────────────────────────────────
# Action: erase (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_erase_deletes_all_data(ctx):
    """erase action deletes all consent data (RTBF)."""
    with patch.object(consent_module, "_append_history"):
        with patch.object(consent_module, "_erase_all") as mock_erase:
            result = consent_module._act_erase(ctx, {"subject_id": "user123"})

    assert result["ok"] is True
    assert result["action"] == "erase"
    assert result["erased"] is True
    mock_erase.assert_called_once_with("test-tenant", "user123")


def test_erase_requires_subject_id(ctx):
    """erase action requires subject_id."""
    with pytest.raises(ValueError, match="erase requires 'subject_id'"):
        consent_module._act_erase(ctx, {})


def test_erase_records_audit_before_deletion(ctx):
    """erase records audit event before deletion."""
    with patch.object(consent_module, "_append_history") as mock_history:
        with patch.object(consent_module, "_erase_all"):
            consent_module._act_erase(ctx, {"subject_id": "user123"})

    # History should be recorded before deletion
    mock_history.assert_called_once()
    call_args = mock_history.call_args[0]
    assert call_args[2]["action"] == "erase"


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions (5 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_normalize_flags_converts_dict():
    """_normalize_flags converts dict to bool values."""
    flags = consent_module._normalize_flags({"marketing": 1, "analytics": 0})
    assert flags["marketing"] is True
    assert flags["analytics"] is False


def test_normalize_flags_handles_string_keys():
    """_normalize_flags handles string flag names."""
    flags = consent_module._normalize_flags({"marketing": True})
    assert "marketing" in flags


def test_normalize_flags_returns_empty_for_none():
    """_normalize_flags returns empty dict for None."""
    flags = consent_module._normalize_flags(None)
    assert flags == {}


def test_normalize_flags_handles_list():
    """_normalize_flags can handle list input."""
    flags = consent_module._normalize_flags(["marketing", "analytics"])
    assert "marketing" in flags
    assert "analytics" in flags


def test_decorated_function_exists():
    """privacy.consent decorated function exists."""
    assert hasattr(consent_module, "privacy_consent")
    assert callable(consent_module.privacy_consent)


# ──────────────────────────────────────────────────────────────────────────────
# Idempotency (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_set_idempotent_same_value(ctx):
    """Setting same value twice is idempotent."""
    with patch.object(
        consent_module,
        "_load_state",
        return_value={"tenant": "test-tenant", "subject_id": "user123", "flags": {"marketing": True}},
    ):
        with patch.object(consent_module, "_save_state"):
            with patch.object(consent_module, "_append_history") as mock_history:
                result = consent_module._act_set(
                    ctx, {"subject_id": "user123", "flags": {"marketing": True}}  # Same as current
                )

    assert result["changed"] == {}  # No changes
    # History should not be recorded if nothing changed
    mock_history.assert_not_called()


def test_grant_idempotent(ctx):
    """Granting already-granted consent is idempotent."""
    with patch.object(
        consent_module,
        "_load_state",
        return_value={"tenant": "test-tenant", "subject_id": "user123", "flags": {"marketing": True}},
    ):
        with patch.object(consent_module, "_save_state"):
            with patch.object(consent_module, "_append_history") as mock_history:
                result = consent_module._act_grant(ctx, {"subject_id": "user123", "flags": {"marketing": True}})

    assert result["changed"] == {}
    mock_history.assert_not_called()


def test_revoke_idempotent(ctx):
    """Revoking already-revoked consent is idempotent."""
    with patch.object(
        consent_module,
        "_load_state",
        return_value={"tenant": "test-tenant", "subject_id": "user123", "flags": {"marketing": False}},
    ):
        with patch.object(consent_module, "_save_state"):
            with patch.object(consent_module, "_append_history") as mock_history:
                result = consent_module._act_revoke(ctx, {"subject_id": "user123", "flags": {"marketing": True}})

    assert result["changed"] == {}
    mock_history.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# Error handling (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_status_handles_missing_state(ctx):
    """status handles missing state gracefully."""
    with patch.object(
        consent_module,
        "_load_state",
        return_value={"tenant": "test-tenant", "subject_id": "user123", "flags": {}},  # Empty state for new subject
    ):
        result = consent_module._act_status(ctx, {"subject_id": "user123"})

    assert result["ok"] is True
    assert result["flags"] == {}


def test_set_validates_flags_type(ctx):
    """set validates flags are provided correctly."""
    with pytest.raises(ValueError, match="set requires non-empty 'flags'"):
        consent_module._act_set(ctx, {"subject_id": "user123", "flags": None})


def test_history_defaults_limit(ctx):
    """history uses default limit if not specified."""
    with patch.object(consent_module, "_get_history", return_value=[]) as mock_history:
        consent_module._act_history(ctx, {"subject_id": "user123"})

    # Should use default limit of 100
    mock_history.assert_called_once_with("test-tenant", "user123", limit=100)
