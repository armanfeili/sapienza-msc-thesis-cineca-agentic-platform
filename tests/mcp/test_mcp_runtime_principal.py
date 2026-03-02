import pytest

from src.mcp.runtime import PermissionError_, ToolContext, check_permissions


@pytest.fixture()
def dict_principal_payload():
    return {
        "sub": "user-123",
        "tenant_id": "tenant-xyz",
        "permissions": ["tools:basic", "user:me"],
        "scopes": ["tools:basic"],
        "raw": {
            "tenant_id": "tenant-xyz",
            "sub": "user-123",
            "permissions": ["tools:basic", "user:me"],
        },
    }


def test_check_permissions_accepts_dict_principal(dict_principal_payload):
    ctx = ToolContext(
        tool="memgraph",
        action="fetch",
        principal=dict_principal_payload,
        tenant="tenant-xyz",
    )

    # Should not raise
    check_permissions(ctx, required_scope="tools:basic")


def test_check_permissions_rejects_missing_scope(dict_principal_payload):
    ctx = ToolContext(
        tool="memgraph",
        action="fetch",
        principal=dict_principal_payload,
        tenant="tenant-xyz",
    )

    with pytest.raises(PermissionError_) as exc:
        check_permissions(ctx, required_scope="tools:admin")

    assert exc.value.details["required_scope"] == "tools:admin"


def test_check_permissions_enforces_tenant(dict_principal_payload):
    ctx = ToolContext(
        tool="memgraph",
        action="fetch",
        principal=dict_principal_payload,
        tenant="tenant-different",
    )

    with pytest.raises(PermissionError_) as exc:
        check_permissions(ctx, required_scope="tools:basic")

    assert exc.value.details["code"] == "E_PERMISSION"
    assert exc.value.details["context_tenant"] == "tenant-different"
