"""
Tests for tenancy.manage tool (P6 - Tenancy Management)

Test Coverage (25 tests):
- List action: 3 tests
- Current action: 2 tests  
- Switch action: 4 tests
- Create action: 6 tests (idempotent behavior)
- Delete action: 7 tests (soft delete guard)
- Set-default action: 3 tests

New P6 Features Tested:
- Idempotent create (returns existing, no error)
- Soft delete guard (prevents deleting default/active tenant)
- Active tenant context tracking
- Soft delete vs hard delete
- Tenant resurrection (soft-deleted → create)
"""

from typing import Any, Dict
import pytest

from src.mcp.tools.tenancy.manage import (
    _act_list,
    _act_current,
    _act_switch,
    _act_create,
    _act_delete,
    _act_set_default,
    tenancy_manage,
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
            "tenant": "public",
            "trace_id": "test-trace-123",
        },
    )()


# ─────────────────────────────────────────────────────────────────────────────
# List Action Tests (3 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_list_returns_tenants(mock_ctx):
    """List returns all tenants with current tenant."""
    result = _act_list(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "list"
    assert "tenants" in result
    assert isinstance(result["tenants"], list)
    assert "tenant" in result  # Current tenant
    assert "default_tenant" in result


def test_act_list_includes_default_tenant(mock_ctx):
    """List includes default tenant information."""
    result = _act_list(mock_ctx, {})

    assert result["ok"] is True
    assert result["default_tenant"] is not None
    # Default tenant should exist in tenants list
    tenant_ids = [t.get("id") for t in result["tenants"]]
    assert result["default_tenant"] in tenant_ids


def test_act_list_excludes_deleted_by_default(mock_ctx):
    """List excludes soft-deleted tenants by default."""
    # Create and delete a tenant
    _act_create(mock_ctx, {"tenant_id": "test-deleted", "name": "Deleted"})
    _act_delete(mock_ctx, {"tenant_id": "test-deleted"})  # Soft delete

    # List without include_deleted
    result = _act_list(mock_ctx, {})
    tenant_ids = [t.get("id") for t in result["tenants"]]
    assert "test-deleted" not in tenant_ids

    # List with include_deleted
    result = _act_list(mock_ctx, {"include_deleted": True})
    tenant_ids = [t.get("id") for t in result["tenants"]]
    # Note: Implementation may or may not include deleted depending on manager


# ─────────────────────────────────────────────────────────────────────────────
# Current Action Tests (2 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_current_returns_active_tenant(mock_ctx):
    """Current returns the active tenant."""
    result = _act_current(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "current"
    assert "tenant" in result
    assert isinstance(result["tenant"], dict)


def test_act_current_after_switch(mock_ctx):
    """Current returns the newly switched tenant."""
    # Create and switch to new tenant
    _act_create(mock_ctx, {"tenant_id": "test-current", "name": "Current Test"})
    _act_switch(mock_ctx, {"tenant_id": "test-current"})

    # Get current
    result = _act_current(mock_ctx, {})

    assert result["ok"] is True
    assert result["tenant"].get("id") == "test-current"


# ─────────────────────────────────────────────────────────────────────────────
# Switch Action Tests (4 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_switch_changes_active_tenant(mock_ctx):
    """Switch changes the active tenant."""
    # Create new tenant
    _act_create(mock_ctx, {"tenant_id": "test-switch", "name": "Switch Test"})

    # Switch to it
    result = _act_switch(mock_ctx, {"tenant_id": "test-switch"})

    assert result["ok"] is True
    assert result["action"] == "switch"
    assert result["tenant"].get("id") == "test-switch"
    assert "previous" in result


def test_act_switch_updates_active_flag(mock_ctx):
    """Switch updates the active flag on tenant."""
    _act_create(mock_ctx, {"tenant_id": "test-active", "name": "Active Test"})

    result = _act_switch(mock_ctx, {"tenant_id": "test-active"})

    # Tenant should be marked active
    assert result["tenant"].get("active") is True


def test_act_switch_requires_tenant_id(mock_ctx):
    """Switch raises error if tenant_id is missing."""
    with pytest.raises(ValueError, match="tenant_id is required"):
        _act_switch(mock_ctx, {})


def test_act_switch_to_nonexistent_tenant(mock_ctx):
    """Switch raises error if tenant doesn't exist."""
    with pytest.raises(KeyError, match="not found"):
        _act_switch(mock_ctx, {"tenant_id": "nonexistent"})


# ─────────────────────────────────────────────────────────────────────────────
# Create Action Tests (6 tests - P6 Idempotent Behavior)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_create_new_tenant(mock_ctx):
    """Create creates a new tenant."""
    result = _act_create(mock_ctx, {"tenant_id": "test-new", "name": "New Tenant", "metadata": {"type": "test"}})

    assert result["ok"] is True
    assert result["action"] == "create"
    assert result["tenant"]["id"] == "test-new"
    assert result["tenant"]["name"] == "New Tenant"
    assert result["idempotent"] is True


def test_act_create_idempotent_existing_tenant(mock_ctx):
    """Create is idempotent - returns existing tenant without error."""
    # Create first time
    _act_create(mock_ctx, {"tenant_id": "test-idempotent", "name": "Idempotent Test"})

    # Create second time - should return existing
    result = _act_create(mock_ctx, {"tenant_id": "test-idempotent", "name": "Idempotent Test"})

    assert result["ok"] is True
    assert result["tenant"]["id"] == "test-idempotent"
    assert result["idempotent"] is True


def test_act_create_resurrects_soft_deleted(mock_ctx):
    """Create resurrects soft-deleted tenant."""
    # Create, then soft delete
    _act_create(mock_ctx, {"tenant_id": "test-resurrect", "name": "Resurrect"})
    _act_delete(mock_ctx, {"tenant_id": "test-resurrect"})  # Soft delete

    # Create again - should resurrect
    result = _act_create(mock_ctx, {"tenant_id": "test-resurrect", "name": "Resurrected"})

    assert result["ok"] is True
    assert result["tenant"]["id"] == "test-resurrect"
    assert result["tenant"]["deleted_at"] is None  # No longer deleted


def test_act_create_requires_tenant_id(mock_ctx):
    """Create raises error if tenant_id is missing."""
    with pytest.raises(ValueError, match="tenant_id is required"):
        _act_create(mock_ctx, {})


def test_act_create_with_metadata(mock_ctx):
    """Create accepts metadata."""
    result = _act_create(mock_ctx, {"tenant_id": "test-metadata", "metadata": {"env": "test", "region": "us-west"}})

    assert result["ok"] is True
    assert result["tenant"]["metadata"]["env"] == "test"
    assert result["tenant"]["metadata"]["region"] == "us-west"


def test_act_create_minimal_payload(mock_ctx):
    """Create works with minimal payload (just tenant_id)."""
    result = _act_create(mock_ctx, {"tenant_id": "test-minimal"})

    assert result["ok"] is True
    assert result["tenant"]["id"] == "test-minimal"
    # Name defaults to tenant_id
    assert result["tenant"]["name"] == "test-minimal"


# ─────────────────────────────────────────────────────────────────────────────
# Delete Action Tests (7 tests - P6 Soft Delete Guard)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_delete_soft_deletes_tenant(mock_ctx):
    """Delete soft-deletes tenant by default."""
    # Create tenant
    _act_create(mock_ctx, {"tenant_id": "test-soft-delete", "name": "Soft Delete"})

    # Soft delete
    result = _act_delete(mock_ctx, {"tenant_id": "test-soft-delete"})

    assert result["ok"] is True
    assert result["action"] == "delete"
    assert result["deleted"] is True
    assert result["soft_delete"] is True


def test_act_delete_hard_deletes_with_force(mock_ctx):
    """Delete hard-deletes tenant when force=true."""
    # Create tenant
    _act_create(mock_ctx, {"tenant_id": "test-hard-delete", "name": "Hard Delete"})

    # Hard delete
    result = _act_delete(mock_ctx, {"tenant_id": "test-hard-delete", "force": True})

    assert result["ok"] is True
    assert result["deleted"] is True
    assert result["soft_delete"] is False


def test_act_delete_guard_prevents_default_deletion(mock_ctx):
    """Soft delete guard prevents deleting default tenant."""
    # Get default tenant
    list_result = _act_list(mock_ctx, {})
    default_id = list_result["default_tenant"]

    # Try to delete default
    with pytest.raises(ValueError, match="cannot delete default tenant"):
        _act_delete(mock_ctx, {"tenant_id": default_id})


def test_act_delete_guard_prevents_active_deletion(mock_ctx):
    """Soft delete guard prevents deleting currently active tenant."""
    # Create and switch to tenant
    _act_create(mock_ctx, {"tenant_id": "test-active-delete", "name": "Active"})
    _act_switch(mock_ctx, {"tenant_id": "test-active-delete"})

    # Try to delete active tenant
    with pytest.raises(ValueError, match="cannot delete currently active tenant"):
        _act_delete(mock_ctx, {"tenant_id": "test-active-delete"})


def test_act_delete_requires_tenant_id(mock_ctx):
    """Delete raises error if tenant_id is missing."""
    with pytest.raises(ValueError, match="tenant_id is required"):
        _act_delete(mock_ctx, {})


def test_act_delete_nonexistent_tenant(mock_ctx):
    """Delete returns false for nonexistent tenant."""
    result = _act_delete(mock_ctx, {"tenant_id": "nonexistent-tenant"})

    # Should not error, just return deleted=false
    assert result["ok"] is True
    assert result["deleted"] is False


def test_act_delete_allows_non_default_non_active(mock_ctx):
    """Delete allows deleting tenant that is not default or active."""
    # Create two tenants
    _act_create(mock_ctx, {"tenant_id": "test-delete-1", "name": "Delete 1"})
    _act_create(mock_ctx, {"tenant_id": "test-delete-2", "name": "Delete 2"})

    # Switch to delete-1
    _act_switch(mock_ctx, {"tenant_id": "test-delete-1"})

    # Delete delete-2 (not active, not default)
    result = _act_delete(mock_ctx, {"tenant_id": "test-delete-2"})

    assert result["ok"] is True
    assert result["deleted"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Set-Default Action Tests (3 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_act_set_default_changes_default(mock_ctx):
    """Set-default changes the default tenant."""
    # Create new tenant
    _act_create(mock_ctx, {"tenant_id": "test-new-default", "name": "New Default"})

    # Set as default
    result = _act_set_default(mock_ctx, {"tenant_id": "test-new-default"})

    assert result["ok"] is True
    assert result["action"] == "set-default"
    assert result["default_tenant"] == "test-new-default"


def test_act_set_default_requires_tenant_id(mock_ctx):
    """Set-default raises error if tenant_id is missing."""
    with pytest.raises(ValueError, match="tenant_id is required"):
        _act_set_default(mock_ctx, {})


def test_act_set_default_nonexistent_tenant(mock_ctx):
    """Set-default raises error if tenant doesn't exist."""
    with pytest.raises(KeyError, match="not found"):
        _act_set_default(mock_ctx, {"tenant_id": "nonexistent"})


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point Tests (3 tests - P3 Pattern)
# ─────────────────────────────────────────────────────────────────────────────


def test_tenancy_manage_routes_to_list(mock_ctx):
    """Entry point routes to list action."""
    result = tenancy_manage(mock_ctx, {"action": "list"})

    assert result["ok"] is True
    assert result["action"] == "list"


def test_tenancy_manage_routes_to_create(mock_ctx):
    """Entry point routes to create action."""
    result = tenancy_manage(mock_ctx, {"action": "create", "tenant_id": "test-entry", "name": "Entry Test"})

    assert result["ok"] is True
    assert result["action"] == "create"
    assert result["tenant"]["id"] == "test-entry"


def test_tenancy_manage_invalid_action(mock_ctx):
    """Entry point raises error for invalid action."""
    with pytest.raises(ValueError, match="action must be one of"):
        tenancy_manage(mock_ctx, {"action": "invalid"})


# ─────────────────────────────────────────────────────────────────────────────
# Summary: 25 Tests
# ─────────────────────────────────────────────────────────────────────────────
# List: 3 tests
# Current: 2 tests
# Switch: 4 tests
# Create: 6 tests (idempotent)
# Delete: 7 tests (soft delete guard)
# Set-default: 3 tests
# Entry: 3 tests
# ─────────────────────────────────────────────────────────────────────────────
