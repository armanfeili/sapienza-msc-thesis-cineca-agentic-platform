import types

import pytest

from src.utils.principal import principal_identity, serialize_principal


@pytest.fixture()
def fake_principal():
    payload = types.SimpleNamespace()
    payload.sub = "auth0|user-123"
    payload.scopes = ("tools:basic", "user:me")
    payload.raw = {
        "sub": "auth0|user-123",
        "permissions": ["tools:basic", "user:me"],
        "roles": ["admin"],
        "tenant_id": "tenant-alpha",
    }
    return payload


def test_principal_identity_prefers_sub(fake_principal):
    assert principal_identity(fake_principal) == "auth0|user-123"


def test_serialize_principal_includes_permissions(fake_principal):
    serialized = serialize_principal(fake_principal, tenant_id="tenant-beta")

    assert serialized["id"] == "auth0|user-123"
    assert serialized["tenant_id"] == "tenant-beta"
    assert "tools:basic" in serialized["permissions"]
    assert serialized["roles"] == ["admin"]
    assert serialized["raw"]["tenant_id"] == "tenant-alpha"


def test_serialize_principal_handles_missing_fields():
    anonymous = types.SimpleNamespace()
    anonymous.subject = "legacy-user"
    anonymous.scopes = None
    anonymous.raw = {}

    serialized = serialize_principal(anonymous, tenant_id=None)

    assert serialized["id"] == "legacy-user"
    assert serialized["tenant_id"] is None
    assert serialized["permissions"] == []
