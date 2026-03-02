"""
Tests for src/mcp/tools/cache/manage.py

Validates TTL policy enforcement, pattern matching, and all cache actions.
"""

import pytest
import time
from typing import Any, Dict

# Import the internal action handlers
from src.mcp.tools.cache.manage import (
    _act_get,
    _act_set,
    _act_delete,
    _act_keys,
    _enforce_ttl_policy,
    DEFAULT_CACHE_TTL,
    MAX_CACHE_TTL,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_get
# ─────────────────────────────────────────────────────────────────────────────


def test_act_get_existing_key():
    """Get existing cache key returns value."""
    # Setup: Set cache key
    _act_set(None, {"key": "k1", "value": "v1"})

    # Test: Get key
    result = _act_get(None, {"key": "k1"})

    assert result["ok"] is True
    assert result["action"] == "get"
    assert result["value"] == "v1"
    assert "backend" in result


def test_act_get_nonexistent_key():
    """Get nonexistent key returns None."""
    result = _act_get(None, {"key": "nonexistent"})

    assert result["ok"] is True
    assert result["value"] is None


def test_act_get_requires_key():
    """Get without key raises ValueError."""
    with pytest.raises(ValueError, match="key is required"):
        _act_get(None, {})


def test_act_get_tenant_namespacing():
    """Get isolates keys by tenant."""
    # Setup: Set key for two tenants
    _act_set(None, {"key": "k2", "value": "v2_global", "tenant": None})
    _act_set(None, {"key": "k2", "value": "v2_t1", "tenant": "t1"})

    # Test: Get returns tenant-specific value
    result_global = _act_get(None, {"key": "k2", "tenant": None})
    result_t1 = _act_get(None, {"key": "k2", "tenant": "t1"})

    assert result_global["value"] == "v2_global"
    assert result_t1["value"] == "v2_t1"


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_set (TTL Policy Enforcement)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_set_new_key():
    """Set creates new cache key with default TTL."""
    result = _act_set(None, {"key": "k3", "value": "v3"})

    assert result["ok"] is True
    assert result["action"] == "set"
    assert result["set"] is True
    assert result["ttl"] == DEFAULT_CACHE_TTL  # Default enforced


def test_act_set_with_explicit_ttl():
    """Set accepts explicit TTL within allowed range."""
    result = _act_set(None, {"key": "k4", "value": "v4", "ttl": 1800})

    assert result["ok"] is True
    assert result["ttl"] == 1800


def test_act_set_enforces_default_ttl():
    """Set enforces default TTL if not specified (P6 Feature: TTL policy)."""
    result = _act_set(None, {"key": "k5", "value": "v5"})

    assert result["ttl"] == DEFAULT_CACHE_TTL


def test_act_set_validates_ttl_positive():
    """Set rejects non-positive TTL."""
    with pytest.raises(ValueError, match="TTL must be positive"):
        _act_set(None, {"key": "k6", "value": "v6", "ttl": 0})

    with pytest.raises(ValueError, match="TTL must be positive"):
        _act_set(None, {"key": "k7", "value": "v7", "ttl": -1})


def test_act_set_validates_ttl_max():
    """Set rejects TTL exceeding maximum."""
    with pytest.raises(ValueError, match="exceeds maximum"):
        _act_set(None, {"key": "k8", "value": "v8", "ttl": MAX_CACHE_TTL + 1})


def test_act_set_requires_key():
    """Set without key raises ValueError."""
    with pytest.raises(ValueError, match="key is required"):
        _act_set(None, {"value": "v9"})


def test_act_set_requires_value():
    """Set without value raises ValueError."""
    with pytest.raises(ValueError, match="value is required"):
        _act_set(None, {"key": "k10"})


def test_act_set_tenant_namespacing():
    """Set isolates keys by tenant."""
    # Setup: Set same key for two tenants
    _act_set(None, {"key": "k11", "value": "v11_global", "tenant": None})
    _act_set(None, {"key": "k11", "value": "v11_t1", "tenant": "t1"})

    # Test: Each tenant gets their own value
    result_global = _act_get(None, {"key": "k11", "tenant": None})
    result_t1 = _act_get(None, {"key": "k11", "tenant": "t1"})

    assert result_global["value"] == "v11_global"
    assert result_t1["value"] == "v11_t1"


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_delete
# ─────────────────────────────────────────────────────────────────────────────


def test_act_delete_existing_key():
    """Delete removes existing cache key."""
    # Setup: Set key
    _act_set(None, {"key": "k12", "value": "v12"})

    # Test: Delete key
    result = _act_delete(None, {"key": "k12"})

    assert result["ok"] is True
    assert result["action"] == "delete"
    assert result["deleted"] is True

    # Verify: Key gone
    get_result = _act_get(None, {"key": "k12"})
    assert get_result["value"] is None


def test_act_delete_nonexistent_key():
    """Delete nonexistent key returns deleted=False."""
    result = _act_delete(None, {"key": "nonexistent"})

    assert result["ok"] is True
    assert result["deleted"] is False


def test_act_delete_requires_key():
    """Delete without key raises ValueError."""
    with pytest.raises(ValueError, match="key is required"):
        _act_delete(None, {})


def test_act_delete_tenant_namespacing():
    """Delete only affects specified tenant."""
    # Setup: Set same key for two tenants
    _act_set(None, {"key": "k13", "value": "v13_global", "tenant": None})
    _act_set(None, {"key": "k13", "value": "v13_t1", "tenant": "t1"})

    # Test: Delete from one tenant
    result = _act_delete(None, {"key": "k13", "tenant": "t1"})

    assert result["deleted"] is True

    # Verify: Global tenant key still exists
    result_global = _act_get(None, {"key": "k13", "tenant": None})
    assert result_global["value"] == "v13_global"

    # Verify: t1 tenant key gone
    result_t1 = _act_get(None, {"key": "k13", "tenant": "t1"})
    assert result_t1["value"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_keys (Pattern Matching)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_keys_wildcard_pattern():
    """Keys with wildcard returns all matching keys (P6 Feature: pattern matching)."""
    # Setup: Set multiple keys
    _act_set(None, {"key": "prefix:k1", "value": "v1"})
    _act_set(None, {"key": "prefix:k2", "value": "v2"})
    _act_set(None, {"key": "other:k3", "value": "v3"})

    # Test: Get keys matching pattern
    result = _act_keys(None, {"pattern": "prefix:*"})

    assert result["ok"] is True
    assert result["action"] == "keys"
    assert "prefix:k1" in result["keys"]
    assert "prefix:k2" in result["keys"]
    assert "other:k3" not in result["keys"]
    assert result["count"] == 2


def test_act_keys_exact_pattern():
    """Keys with exact pattern returns only exact match."""
    # Setup: Set keys
    _act_set(None, {"key": "exact", "value": "v1"})
    _act_set(None, {"key": "exact2", "value": "v2"})

    # Test: Get exact key
    result = _act_keys(None, {"pattern": "exact"})

    assert "exact" in result["keys"]
    assert "exact2" not in result["keys"]


def test_act_keys_empty_result():
    """Keys with no matches returns empty list."""
    result = _act_keys(None, {"pattern": "nonexistent:*"})

    assert result["ok"] is True
    assert result["keys"] == []
    assert result["count"] == 0


def test_act_keys_tenant_namespacing():
    """Keys only returns keys for specified tenant."""
    # Setup: Set keys for two tenants
    _act_set(None, {"key": "k14", "value": "v14_global", "tenant": None})
    _act_set(None, {"key": "k14", "value": "v14_t1", "tenant": "t1"})

    # Test: Get keys for t1
    result = _act_keys(None, {"pattern": "*", "tenant": "t1"})

    # Verify: Only t1 keys returned (namespace prefix stripped)
    assert "k14" in result["keys"]
    assert result["tenant"] == "t1"


# ─────────────────────────────────────────────────────────────────────────────
# Test TTL Policy Enforcement
# ─────────────────────────────────────────────────────────────────────────────


def test_enforce_ttl_policy_default():
    """_enforce_ttl_policy applies default for non-session keys."""
    ttl = _enforce_ttl_policy(None, "regular:key")
    assert ttl == DEFAULT_CACHE_TTL


def test_enforce_ttl_policy_session_exempt():
    """_enforce_ttl_policy allows session keys without TTL."""
    ttl = _enforce_ttl_policy(None, "session:abc123")
    assert ttl == DEFAULT_CACHE_TTL  # Gets default, not rejected


def test_enforce_ttl_policy_validates_range():
    """_enforce_ttl_policy validates TTL within allowed range."""
    ttl = _enforce_ttl_policy(1800, "regular:key")
    assert ttl == 1800


def test_enforce_ttl_policy_rejects_negative():
    """_enforce_ttl_policy rejects negative TTL."""
    with pytest.raises(ValueError, match="must be positive"):
        _enforce_ttl_policy(-1, "regular:key")


def test_enforce_ttl_policy_rejects_exceeds_max():
    """_enforce_ttl_policy rejects TTL exceeding maximum."""
    with pytest.raises(ValueError, match="exceeds maximum"):
        _enforce_ttl_policy(MAX_CACHE_TTL + 1, "regular:key")


# ─────────────────────────────────────────────────────────────────────────────
# Test Entry Point Routing
# ─────────────────────────────────────────────────────────────────────────────


def test_entry_point_routes_get():
    """Entry point routes 'get' action."""
    from src.mcp.tools.cache.manage import invoke

    # Setup: Set key
    invoke(None, {"action": "set", "key": "k15", "value": "v15"})

    # Test: Route to get
    result = invoke(None, {"action": "get", "key": "k15"})

    assert result["action"] == "get"
    assert result["value"] == "v15"


def test_entry_point_routes_set():
    """Entry point routes 'set' action."""
    from src.mcp.tools.cache.manage import invoke

    result = invoke(None, {"action": "set", "key": "k16", "value": "v16"})

    assert result["action"] == "set"
    assert result["set"] is True


def test_entry_point_routes_delete():
    """Entry point routes 'delete' action."""
    from src.mcp.tools.cache.manage import invoke

    # Setup: Set key
    invoke(None, {"action": "set", "key": "k17", "value": "v17"})

    # Test: Route to delete
    result = invoke(None, {"action": "delete", "key": "k17"})

    assert result["action"] == "delete"
    assert result["deleted"] is True


def test_entry_point_routes_keys():
    """Entry point routes 'keys' action."""
    from src.mcp.tools.cache.manage import invoke

    # Setup: Set keys
    invoke(None, {"action": "set", "key": "test:k1", "value": "v1"})
    invoke(None, {"action": "set", "key": "test:k2", "value": "v2"})

    # Test: Route to keys
    result = invoke(None, {"action": "keys", "pattern": "test:*"})

    assert result["action"] == "keys"
    assert result["count"] >= 2


def test_entry_point_handles_validation_error():
    """Entry point handles validation errors gracefully."""
    from src.mcp.tools.cache.manage import invoke

    result = invoke(None, {"action": "set", "value": "v18"})  # Missing key

    assert result["ok"] is False
    assert "error" in result
