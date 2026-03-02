"""
Tests for src/mcp/tools/user/profile.py

Validates JSONB merge semantics, input sanitation, and all profile actions.
"""

import pytest
from typing import Any, Dict

# Import the internal action handlers
from src.mcp.tools.user.profile import (
    _act_get,
    _act_set,
    _act_update,
    _act_delete,
    _sanitize_dict,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_get
# ─────────────────────────────────────────────────────────────────────────────


def test_act_get_existing_profile():
    """Get existing profile returns full document."""
    # Setup: Create profile first
    _act_set(None, {"user_id": "u1", "profile": {"name": "Alice", "age": 30}})

    # Test: Get profile
    result = _act_get(None, {"user_id": "u1"})

    assert result["ok"] is True
    assert result["action"] == "get"
    assert result["profile"]["name"] == "Alice"
    assert result["profile"]["age"] == 30
    assert "created_at" in result["profile"]


def test_act_get_nonexistent_profile():
    """Get nonexistent profile returns empty dict."""
    result = _act_get(None, {"user_id": "nonexistent"})

    assert result["ok"] is True
    assert result["action"] == "get"
    assert result["profile"] == {}


def test_act_get_default_anonymous():
    """Get without user_id uses 'anonymous'."""
    # Setup: Create anonymous profile
    _act_set(None, {"profile": {"name": "Anonymous"}})

    # Test: Get without user_id
    result = _act_get(None, {})

    assert result["ok"] is True
    assert result["profile"]["name"] == "Anonymous"


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_set
# ─────────────────────────────────────────────────────────────────────────────


def test_act_set_new_profile():
    """Set creates new profile with created_at timestamp."""
    result = _act_set(None, {"user_id": "u2", "profile": {"name": "Bob"}})

    assert result["ok"] is True
    assert result["action"] == "set"
    assert result["profile"]["name"] == "Bob"
    assert "created_at" in result["profile"]
    assert "updated_at" in result["profile"]


def test_act_set_replace_existing():
    """Set replaces existing profile completely."""
    # Setup: Create initial profile
    _act_set(None, {"user_id": "u3", "profile": {"name": "Charlie", "age": 25}})

    # Test: Replace profile
    result = _act_set(None, {"user_id": "u3", "profile": {"name": "Charles"}})

    assert result["ok"] is True
    assert result["profile"]["name"] == "Charles"
    assert "age" not in result["profile"]  # Old key removed


def test_act_set_preserves_created_at():
    """Set preserves created_at when replacing profile."""
    # Setup: Create initial profile
    result1 = _act_set(None, {"user_id": "u4", "profile": {"name": "Dave"}})
    created = result1["profile"]["created_at"]

    # Test: Replace profile
    result2 = _act_set(None, {"user_id": "u4", "profile": {"name": "David"}})

    assert result2["profile"]["created_at"] == created


def test_act_set_validates_profile_is_dict():
    """Set rejects non-dict profile."""
    with pytest.raises(ValueError, match="must be a dict"):
        _act_set(None, {"user_id": "u5", "profile": "not_a_dict"})


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_update (JSONB Merge Semantics)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_update_merges_existing():
    """Update merges patch into existing profile (P6 Feature: JSONB merge)."""
    # Setup: Create profile
    _act_set(None, {"user_id": "u6", "profile": {"name": "Eve", "age": 28}})

    # Test: Update with patch
    result = _act_update(None, {"user_id": "u6", "patch": {"city": "NYC"}})

    assert result["ok"] is True
    assert result["action"] == "update"
    assert result["profile"]["name"] == "Eve"  # Preserved
    assert result["profile"]["age"] == 28  # Preserved
    assert result["profile"]["city"] == "NYC"  # Added


def test_act_update_creates_if_nonexistent():
    """Update creates new profile if none exists."""
    result = _act_update(None, {"user_id": "u7", "patch": {"name": "Frank"}})

    assert result["ok"] is True
    assert result["profile"]["name"] == "Frank"
    assert "created_at" in result["profile"]


def test_act_update_overwrites_existing_keys():
    """Update overwrites existing keys with patch values."""
    # Setup: Create profile
    _act_set(None, {"user_id": "u8", "profile": {"name": "Grace", "age": 30}})

    # Test: Update age
    result = _act_update(None, {"user_id": "u8", "patch": {"age": 31}})

    assert result["profile"]["age"] == 31


def test_act_update_preserves_unmentioned_keys():
    """Update preserves keys not mentioned in patch (P6 Feature: JSONB merge)."""
    # Setup: Create profile with multiple keys
    _act_set(None, {"user_id": "u9", "profile": {"name": "Henry", "age": 35, "city": "LA"}})

    # Test: Update only age
    result = _act_update(None, {"user_id": "u9", "patch": {"age": 36}})

    assert result["profile"]["name"] == "Henry"  # Preserved
    assert result["profile"]["city"] == "LA"  # Preserved
    assert result["profile"]["age"] == 36  # Updated


def test_act_update_validates_patch_is_dict():
    """Update rejects non-dict patch (P6 Feature: input sanitation)."""
    with pytest.raises(ValueError, match="must be a dict"):
        _act_update(None, {"user_id": "u10", "patch": "not_a_dict"})


def test_act_update_updates_timestamp():
    """Update refreshes updated_at timestamp."""
    # Setup: Create profile
    result1 = _act_set(None, {"user_id": "u11", "profile": {"name": "Ivy"}})
    updated1 = result1["profile"]["updated_at"]

    import time

    time.sleep(1)  # Ensure timestamp changes

    # Test: Update profile
    result2 = _act_update(None, {"user_id": "u11", "patch": {"age": 25}})
    updated2 = result2["profile"]["updated_at"]

    assert updated2 > updated1


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_delete
# ─────────────────────────────────────────────────────────────────────────────


def test_act_delete_existing_profile():
    """Delete removes existing profile."""
    # Setup: Create profile
    _act_set(None, {"user_id": "u12", "profile": {"name": "Jack"}})

    # Test: Delete profile
    result = _act_delete(None, {"user_id": "u12"})

    assert result["ok"] is True
    assert result["action"] == "delete"
    assert result["deleted"] is True

    # Verify: Profile gone
    get_result = _act_get(None, {"user_id": "u12"})
    assert get_result["profile"] == {}


def test_act_delete_nonexistent_profile():
    """Delete nonexistent profile returns deleted=False."""
    result = _act_delete(None, {"user_id": "nonexistent"})

    assert result["ok"] is True
    assert result["deleted"] is False


def test_act_delete_from_both_backends():
    """Delete removes profile from both memory and Redis (if available)."""
    # Setup: Create profile
    _act_set(None, {"user_id": "u13", "profile": {"name": "Kate"}})

    # Test: Delete
    result = _act_delete(None, {"user_id": "u13"})

    assert result["deleted"] is True

    # Verify: Cannot retrieve
    get_result = _act_get(None, {"user_id": "u13"})
    assert get_result["profile"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# Test Input Sanitation
# ─────────────────────────────────────────────────────────────────────────────


def test_sanitize_dict_accepts_valid_dict():
    """_sanitize_dict accepts valid dict."""
    result = _sanitize_dict({"key": "value"}, "test")
    assert result == {"key": "value"}


def test_sanitize_dict_rejects_string():
    """_sanitize_dict rejects string."""
    with pytest.raises(ValueError, match="must be a dict"):
        _sanitize_dict("string", "test")


def test_sanitize_dict_rejects_list():
    """_sanitize_dict rejects list."""
    with pytest.raises(ValueError, match="must be a dict"):
        _sanitize_dict(["list"], "test")


def test_sanitize_dict_rejects_none():
    """_sanitize_dict rejects None."""
    with pytest.raises(ValueError, match="must be a dict"):
        _sanitize_dict(None, "test")


# ─────────────────────────────────────────────────────────────────────────────
# Test Entry Point Routing
# ─────────────────────────────────────────────────────────────────────────────


def test_entry_point_routes_get():
    """Entry point routes 'get' action."""
    from src.mcp.tools.user.profile import invoke

    # Setup: Create profile
    invoke(None, {"action": "set", "user_id": "u14", "profile": {"name": "Leo"}})

    # Test: Route to get
    result = invoke(None, {"action": "get", "user_id": "u14"})

    assert result["action"] == "get"
    assert result["profile"]["name"] == "Leo"


def test_entry_point_routes_set():
    """Entry point routes 'set' action."""
    from src.mcp.tools.user.profile import invoke

    result = invoke(None, {"action": "set", "user_id": "u15", "profile": {"name": "Mia"}})

    assert result["action"] == "set"
    assert result["profile"]["name"] == "Mia"


def test_entry_point_routes_update():
    """Entry point routes 'update' action."""
    from src.mcp.tools.user.profile import invoke

    # Setup: Create profile
    invoke(None, {"action": "set", "user_id": "u16", "profile": {"name": "Nina"}})

    # Test: Route to update
    result = invoke(None, {"action": "update", "user_id": "u16", "patch": {"age": 27}})

    assert result["action"] == "update"
    assert result["profile"]["age"] == 27


def test_entry_point_routes_delete():
    """Entry point routes 'delete' action."""
    from src.mcp.tools.user.profile import invoke

    # Setup: Create profile
    invoke(None, {"action": "set", "user_id": "u17", "profile": {"name": "Oscar"}})

    # Test: Route to delete
    result = invoke(None, {"action": "delete", "user_id": "u17"})

    assert result["action"] == "delete"
    assert result["deleted"] is True
