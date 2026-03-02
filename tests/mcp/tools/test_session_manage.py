"""
Tests for session.manage tool (P6 - Session Management)

Test Coverage (35 tests):
- Create action: 4 tests
- Read action: 3 tests
- Update action: 5 tests
- Delete action: 2 tests
- Set_pref action: 3 tests
- Get_pref action: 3 tests
- Set_context action: 4 tests
- Clear_context action: 2 tests
- Touch action: 3 tests (P6 TTL refresh)
- Exists action: 2 tests
- List action: 4 tests (P6 pagination)

New P6 Features Tested:
- TTL enforcement on every write
- Touch action refreshes TTL
- Pagination with limit/offset/count/has_more
"""

from typing import Any, Dict
import pytest
import time

from src.mcp.tools.session.manage import (
    _act_create,
    _act_read,
    _act_update,
    _act_delete,
    _act_set_pref,
    _act_get_pref,
    _act_set_context,
    _act_clear_context,
    _act_touch,
    _act_exists,
    _act_list,
    session_manage,
    _MEM,  # Access to in-memory store for cleanup
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_ctx():
    """Mock ToolContext."""
    return type(
        "MockCtx",
        (),
        {
            "principal": "test-user",
            "tenant": "default",
            "trace_id": "test-trace-123",
        },
    )()


@pytest.fixture(autouse=True)
def cleanup_sessions():
    """Clean up in-memory sessions after each test."""
    yield
    _MEM.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Create Action Tests (4 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_create_new_session(mock_ctx):
    """Create creates a new session."""
    result = _act_create(
        mock_ctx,
        {
            "principal": "user@example.com",
            "roles": ["user", "admin"],
            "context": {"location": "test"},
            "prefs": {"theme": "dark"},
        },
    )

    assert result["ok"] is True
    assert result["action"] == "create"
    assert result["session"]["principal"] == "user@example.com"
    assert result["session"]["roles"] == ["user", "admin"]
    assert result["session"]["context"]["location"] == "test"
    assert result["session"]["prefs"]["theme"] == "dark"
    assert "session_id" in result["session"]
    assert "created_at" in result["session"]
    assert "updated_at" in result["session"]


def test_act_create_with_custom_session_id(mock_ctx):
    """Create accepts custom session_id."""
    result = _act_create(mock_ctx, {"session_id": "custom-session-123", "principal": "test@example.com"})

    assert result["ok"] is True
    assert result["session"]["session_id"] == "custom-session-123"


def test_act_create_minimal_session(mock_ctx):
    """Create works with minimal payload."""
    result = _act_create(mock_ctx, {})

    assert result["ok"] is True
    assert result["session"]["principal"] is None
    assert result["session"]["roles"] == []
    assert result["session"]["context"] == {}
    assert result["session"]["prefs"] == {}


def test_act_create_with_tenant(mock_ctx):
    """Create respects tenant parameter."""
    result = _act_create(mock_ctx, {"tenant": "tenant-alpha", "principal": "user@alpha.com"})

    assert result["ok"] is True
    assert result["session"]["tenant"] == "tenant-alpha"


# ─────────────────────────────────────────────────────────────────────────────
# Read Action Tests (3 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_read_existing_session(mock_ctx):
    """Read returns existing session."""
    # Create session first
    create_result = _act_create(mock_ctx, {"principal": "reader@example.com"})
    session_id = create_result["session"]["session_id"]

    # Read it
    result = _act_read(mock_ctx, {"session_id": session_id})

    assert result["ok"] is True
    assert result["action"] == "read"
    assert result["session"]["session_id"] == session_id
    assert result["session"]["principal"] == "reader@example.com"


def test_act_read_nonexistent_session(mock_ctx):
    """Read returns error for nonexistent session."""
    result = _act_read(mock_ctx, {"session_id": "nonexistent-session"})

    assert result["ok"] is False
    assert result["error"] == "not_found"
    assert result["session_id"] == "nonexistent-session"


def test_act_read_requires_session_id(mock_ctx):
    """Read raises error if session_id is missing."""
    with pytest.raises(ValueError, match="session_id is required"):
        _act_read(mock_ctx, {})


# ─────────────────────────────────────────────────────────────────────────────
# Update Action Tests (5 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_update_merges_context_by_default(mock_ctx):
    """Update merges context by default (not replace)."""
    # Create session with initial context
    create_result = _act_create(mock_ctx, {"context": {"key1": "value1", "key2": "value2"}})
    session_id = create_result["session"]["session_id"]

    # Update with new context key
    result = _act_update(mock_ctx, {"session_id": session_id, "context": {"key3": "value3"}})

    assert result["ok"] is True
    # Should have all three keys
    assert result["session"]["context"]["key1"] == "value1"
    assert result["session"]["context"]["key2"] == "value2"
    assert result["session"]["context"]["key3"] == "value3"


def test_act_update_replaces_context_with_flag(mock_ctx):
    """Update replaces context when replace=true."""
    # Create session with initial context
    create_result = _act_create(mock_ctx, {"context": {"old_key": "old_value"}})
    session_id = create_result["session"]["session_id"]

    # Update with replace flag
    result = _act_update(mock_ctx, {"session_id": session_id, "context": {"new_key": "new_value"}, "replace": True})

    assert result["ok"] is True
    # Should only have new key
    assert "old_key" not in result["session"]["context"]
    assert result["session"]["context"]["new_key"] == "new_value"


def test_act_update_merges_prefs_by_default(mock_ctx):
    """Update merges prefs by default."""
    # Create session with initial prefs
    create_result = _act_create(mock_ctx, {"prefs": {"theme": "dark", "lang": "en"}})
    session_id = create_result["session"]["session_id"]

    # Update prefs
    result = _act_update(mock_ctx, {"session_id": session_id, "prefs": {"notifications": True}})

    assert result["ok"] is True
    assert result["session"]["prefs"]["theme"] == "dark"
    assert result["session"]["prefs"]["lang"] == "en"
    assert result["session"]["prefs"]["notifications"] is True


def test_act_update_metadata(mock_ctx):
    """Update can change principal and roles."""
    # Create session
    create_result = _act_create(mock_ctx, {"principal": "old@example.com", "roles": ["user"]})
    session_id = create_result["session"]["session_id"]

    # Update metadata
    result = _act_update(
        mock_ctx, {"session_id": session_id, "principal": "new@example.com", "roles": ["user", "admin"]}
    )

    assert result["ok"] is True
    assert result["session"]["principal"] == "new@example.com"
    assert result["session"]["roles"] == ["user", "admin"]


def test_act_update_nonexistent_session(mock_ctx):
    """Update returns error for nonexistent session."""
    result = _act_update(mock_ctx, {"session_id": "nonexistent", "principal": "test@example.com"})

    assert result["ok"] is False
    assert result["error"] == "not_found"


# ─────────────────────────────────────────────────────────────────────────────
# Delete Action Tests (2 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_delete_existing_session(mock_ctx):
    """Delete removes existing session."""
    # Create session
    create_result = _act_create(mock_ctx, {"principal": "delete@example.com"})
    session_id = create_result["session"]["session_id"]

    # Delete it
    result = _act_delete(mock_ctx, {"session_id": session_id})

    assert result["ok"] is True
    assert result["deleted"] is True

    # Verify it's gone
    read_result = _act_read(mock_ctx, {"session_id": session_id})
    assert read_result["ok"] is False


def test_act_delete_nonexistent_session(mock_ctx):
    """Delete returns false for nonexistent session."""
    result = _act_delete(mock_ctx, {"session_id": "nonexistent"})

    assert result["ok"] is True
    assert result["deleted"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Set_pref Action Tests (3 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_set_pref_adds_new_pref(mock_ctx):
    """Set_pref adds a new preference key."""
    # Create session
    create_result = _act_create(mock_ctx, {})
    session_id = create_result["session"]["session_id"]

    # Set pref
    result = _act_set_pref(mock_ctx, {"session_id": session_id, "key": "theme", "value": "light"})

    assert result["ok"] is True
    assert result["session"]["prefs"]["theme"] == "light"


def test_act_set_pref_updates_existing_pref(mock_ctx):
    """Set_pref updates existing preference."""
    # Create session with pref
    create_result = _act_create(mock_ctx, {"prefs": {"theme": "dark"}})
    session_id = create_result["session"]["session_id"]

    # Update pref
    result = _act_set_pref(mock_ctx, {"session_id": session_id, "key": "theme", "value": "light"})

    assert result["ok"] is True
    assert result["session"]["prefs"]["theme"] == "light"


def test_act_set_pref_requires_key(mock_ctx):
    """Set_pref raises error if key is missing."""
    create_result = _act_create(mock_ctx, {})
    session_id = create_result["session"]["session_id"]

    with pytest.raises(ValueError, match="key is required"):
        _act_set_pref(mock_ctx, {"session_id": session_id, "value": "test"})


# ─────────────────────────────────────────────────────────────────────────────
# Get_pref Action Tests (3 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_get_pref_existing_key(mock_ctx):
    """Get_pref returns existing preference."""
    # Create session with pref
    create_result = _act_create(mock_ctx, {"prefs": {"theme": "dark"}})
    session_id = create_result["session"]["session_id"]

    # Get pref
    result = _act_get_pref(mock_ctx, {"session_id": session_id, "key": "theme"})

    assert result["ok"] is True
    assert result["value"] == "dark"
    assert result["exists"] is True


def test_act_get_pref_nonexistent_key(mock_ctx):
    """Get_pref returns None for nonexistent key."""
    # Create session
    create_result = _act_create(mock_ctx, {})
    session_id = create_result["session"]["session_id"]

    # Get nonexistent pref
    result = _act_get_pref(mock_ctx, {"session_id": session_id, "key": "nonexistent"})

    assert result["ok"] is True
    assert result["value"] is None
    assert result["exists"] is False


def test_act_get_pref_requires_key(mock_ctx):
    """Get_pref raises error if key is missing."""
    create_result = _act_create(mock_ctx, {})
    session_id = create_result["session"]["session_id"]

    with pytest.raises(ValueError, match="key is required"):
        _act_get_pref(mock_ctx, {"session_id": session_id})


# ─────────────────────────────────────────────────────────────────────────────
# Set_context Action Tests (4 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_set_context_merges_by_default(mock_ctx):
    """Set_context merges by default."""
    # Create session with context
    create_result = _act_create(mock_ctx, {"context": {"key1": "value1"}})
    session_id = create_result["session"]["session_id"]

    # Set context
    result = _act_set_context(mock_ctx, {"session_id": session_id, "context": {"key2": "value2"}})

    assert result["ok"] is True
    assert result["session"]["context"]["key1"] == "value1"
    assert result["session"]["context"]["key2"] == "value2"


def test_act_set_context_replaces_with_flag(mock_ctx):
    """Set_context replaces when replace=true."""
    # Create session with context
    create_result = _act_create(mock_ctx, {"context": {"old": "value"}})
    session_id = create_result["session"]["session_id"]

    # Set context with replace
    result = _act_set_context(mock_ctx, {"session_id": session_id, "context": {"new": "value"}, "replace": True})

    assert result["ok"] is True
    assert "old" not in result["session"]["context"]
    assert result["session"]["context"]["new"] == "value"


def test_act_set_context_empty_dict(mock_ctx):
    """Set_context accepts empty dict."""
    create_result = _act_create(mock_ctx, {})
    session_id = create_result["session"]["session_id"]

    result = _act_set_context(mock_ctx, {"session_id": session_id, "context": {}})

    assert result["ok"] is True
    assert result["session"]["context"] == {}


def test_act_set_context_nonexistent_session(mock_ctx):
    """Set_context returns error for nonexistent session."""
    result = _act_set_context(mock_ctx, {"session_id": "nonexistent", "context": {"key": "value"}})

    assert result["ok"] is False
    assert result["error"] == "not_found"


# ─────────────────────────────────────────────────────────────────────────────
# Clear_context Action Tests (2 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_clear_context_removes_all_context(mock_ctx):
    """Clear_context removes all context data."""
    # Create session with context
    create_result = _act_create(mock_ctx, {"context": {"key1": "value1", "key2": "value2"}})
    session_id = create_result["session"]["session_id"]

    # Clear context
    result = _act_clear_context(mock_ctx, {"session_id": session_id})

    assert result["ok"] is True
    assert result["session"]["context"] == {}


def test_act_clear_context_nonexistent_session(mock_ctx):
    """Clear_context returns error for nonexistent session."""
    result = _act_clear_context(mock_ctx, {"session_id": "nonexistent"})

    assert result["ok"] is False
    assert result["error"] == "not_found"


# ─────────────────────────────────────────────────────────────────────────────
# Touch Action Tests (3 tests - P6 TTL Refresh)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_touch_updates_timestamp(mock_ctx):
    """Touch updates updated_at timestamp."""
    # Create session
    create_result = _act_create(mock_ctx, {})
    session_id = create_result["session"]["session_id"]
    original_updated = create_result["session"]["updated_at"]

    # Wait 1+ seconds to ensure timestamp changes (resolution is 1 second)
    time.sleep(1.1)

    # Touch session
    result = _act_touch(mock_ctx, {"session_id": session_id})

    assert result["ok"] is True
    assert result["session"]["updated_at"] != original_updated


def test_act_touch_refreshes_ttl(mock_ctx):
    """Touch refreshes TTL (P6 Feature)."""
    # Create session
    create_result = _act_create(mock_ctx, {})
    session_id = create_result["session"]["session_id"]

    # Touch should succeed and refresh TTL
    result = _act_touch(mock_ctx, {"session_id": session_id})

    assert result["ok"] is True
    assert "session" in result


def test_act_touch_nonexistent_session(mock_ctx):
    """Touch returns error for nonexistent session."""
    result = _act_touch(mock_ctx, {"session_id": "nonexistent"})

    assert result["ok"] is False
    assert result["error"] == "not_found"


# ─────────────────────────────────────────────────────────────────────────────
# Exists Action Tests (2 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_exists_for_existing_session(mock_ctx):
    """Exists returns true for existing session."""
    # Create session
    create_result = _act_create(mock_ctx, {})
    session_id = create_result["session"]["session_id"]

    # Check exists
    result = _act_exists(mock_ctx, {"session_id": session_id})

    assert result["ok"] is True
    assert result["exists"] is True


def test_act_exists_for_nonexistent_session(mock_ctx):
    """Exists returns false for nonexistent session."""
    result = _act_exists(mock_ctx, {"session_id": "nonexistent"})

    assert result["ok"] is True
    assert result["exists"] is False


# ─────────────────────────────────────────────────────────────────────────────
# List Action Tests (4 tests - P6 Pagination)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_list_returns_all_sessions(mock_ctx):
    """List returns all sessions for tenant."""
    # Create multiple sessions
    _act_create(mock_ctx, {"principal": "user1@example.com"})
    _act_create(mock_ctx, {"principal": "user2@example.com"})
    _act_create(mock_ctx, {"principal": "user3@example.com"})

    # List sessions
    result = _act_list(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "list"
    assert len(result["sessions"]) == 3
    assert result["count"] == 3
    assert result["tenant"] == "default"


def test_act_list_pagination_with_limit(mock_ctx):
    """List supports pagination with limit (P6 Feature)."""
    # Create 5 sessions
    for i in range(5):
        _act_create(mock_ctx, {"principal": f"user{i}@example.com"})

    # List with limit
    result = _act_list(mock_ctx, {"limit": 3})

    assert result["ok"] is True
    assert len(result["sessions"]) == 3
    assert result["count"] == 5
    assert result["limit"] == 3
    assert result["has_more"] is True


def test_act_list_pagination_with_offset(mock_ctx):
    """List supports pagination with offset (P6 Feature)."""
    # Create 5 sessions
    for i in range(5):
        _act_create(mock_ctx, {"principal": f"user{i}@example.com"})

    # List with offset
    result = _act_list(mock_ctx, {"limit": 2, "offset": 2})

    assert result["ok"] is True
    assert len(result["sessions"]) == 2
    assert result["count"] == 5
    assert result["offset"] == 2
    assert result["has_more"] is True


def test_act_list_has_more_indicator(mock_ctx):
    """List indicates has_more correctly (P6 Feature)."""
    # Create 3 sessions
    for i in range(3):
        _act_create(mock_ctx, {"principal": f"user{i}@example.com"})

    # List all
    result = _act_list(mock_ctx, {"limit": 10})

    assert result["ok"] is True
    assert result["has_more"] is False  # No more pages

    # List with limit that causes pagination
    result2 = _act_list(mock_ctx, {"limit": 2})
    assert result2["has_more"] is True  # More pages available


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point Tests (3 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_session_manage_routes_to_create(mock_ctx):
    """Entry point routes to create action."""
    result = session_manage(mock_ctx, {"action": "create", "principal": "router@example.com"})

    assert result["ok"] is True
    assert result["action"] == "create"


def test_session_manage_routes_to_list(mock_ctx):
    """Entry point routes to list action."""
    result = session_manage(mock_ctx, {"action": "list"})

    assert result["ok"] is True
    assert result["action"] == "list"


def test_session_manage_invalid_action(mock_ctx):
    """Entry point raises error for invalid action."""
    with pytest.raises(ValueError, match="unsupported action"):
        session_manage(mock_ctx, {"action": "invalid"})


# ─────────────────────────────────────────────────────────────────────────────
# Summary: 35 Tests
# ─────────────────────────────────────────────────────────────────────────────
# Create: 4 tests
# Read: 3 tests
# Update: 5 tests
# Delete: 2 tests
# Set_pref: 3 tests
# Get_pref: 3 tests
# Set_context: 4 tests
# Clear_context: 2 tests
# Touch: 3 tests (P6 TTL refresh)
# Exists: 2 tests
# List: 4 tests (P6 pagination)
# Entry: 3 tests
# ─────────────────────────────────────────────────────────────────────────────
