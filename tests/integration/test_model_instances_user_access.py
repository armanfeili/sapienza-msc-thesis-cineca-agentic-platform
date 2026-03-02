"""
Integration tests for model instances user access (Phase 10).

Tests cover:
- User token access to /v1/models/* endpoints
- Admin token access to both /v1/models/* and /v1/admin/models/* (deprecated)
- Filtering behavior (enabled-only for users)
- Permission enforcement (user vs admin operations)
- Default model precedence resolution (user → tenant → global)
- Scope-based default writes (user/tenant/global)
- 404 hiding for disabled instances
- X-Default-Scope header behavior
"""

import pytest
from fastapi import status


# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def user_token(mint_token):
    """Regular user token with user-level model permissions."""
    return mint_token(
        sub="user123",
        scopes=[
            "models:read",
            "models:test",
            "models:defaults:read",
            "models:defaults:write:self",
        ],
    )


@pytest.fixture
def admin_token(mint_token):
    """Admin token with all permissions."""
    return mint_token(sub="admin", scopes=["admin:all"])


@pytest.fixture
def tenant_admin_token(mint_token):
    """Tenant admin token with tenant-level default write permission."""
    return mint_token(
        sub="tenant-admin",
        scopes=[
            "models:read",
            "models:test",
            "models:write",
            "models:delete",
            "models:defaults:read",
            "models:defaults:write:self",
            "models:defaults:write:tenant",
        ],
    )


@pytest.fixture
def limited_user_token(mint_token):
    """User token with only read permission (no defaults write)."""
    return mint_token(sub="limited-user", scopes=["models:read"])


@pytest.fixture
def user_headers(user_token):
    """Authorization headers for regular user."""
    return {
        "Authorization": f"Bearer {user_token}",
        "X-Tenant-Id": "tenant-test",
    }


@pytest.fixture
def admin_headers(admin_token):
    """Authorization headers for admin."""
    return {
        "Authorization": f"Bearer {admin_token}",
        "X-Tenant-Id": "tenant-test",
    }


@pytest.fixture
def tenant_admin_headers(tenant_admin_token):
    """Authorization headers for tenant admin."""
    return {
        "Authorization": f"Bearer {tenant_admin_token}",
        "X-Tenant-Id": "tenant-test",
    }


@pytest.fixture
def limited_user_headers(limited_user_token):
    """Authorization headers for limited user."""
    return {
        "Authorization": f"Bearer {limited_user_token}",
        "X-Tenant-Id": "tenant-test",
    }


# ==============================================================================
# User Token Tests - List Instances
# ==============================================================================


@pytest.mark.asyncio
async def test_user_can_list_enabled_instances(async_client, user_headers, monkeypatch):
    """User token can list model instances, but only sees enabled ones."""
    instances = [
        {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"},
        {"id": "model-2", "name": "Model 2", "enabled": False, "tenant_id": "tenant-test"},
        {"id": "model-3", "name": "Model 3", "enabled": True, "tenant_id": "tenant-test"},
    ]

    def _mock_list(**kwargs):
        # Verify filtering is applied for non-admin
        if kwargs.get("enabled") is True:
            filtered = [i for i in instances if i["enabled"]]
        else:
            filtered = instances
        # Return tuple: (instances, etag, next_token)
        return filtered, "test-etag", None

    monkeypatch.setattr("src.routers.model_instances.model_instance_repo.list_instances", _mock_list)

    response = await async_client.get("/v1/models/instances", headers=user_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 2  # Only enabled instances
    assert all(item["enabled"] for item in data["items"])


@pytest.mark.asyncio
async def test_user_cannot_see_disabled_in_list(async_client, user_headers, monkeypatch):
    """User token does not see disabled instances in list response."""
    instances = [
        {"id": "disabled-model", "name": "Disabled", "enabled": False, "tenant_id": "tenant-test"},
    ]

    def _mock_list(**kwargs):
        filtered = [] if kwargs.get("enabled") is True else instances
        return filtered, "test-etag", None

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.list_instances",
        _mock_list,
    )

    response = await async_client.get("/v1/models/instances", headers=user_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 0


# ==============================================================================
# User Token Tests - Get Instance
# ==============================================================================


@pytest.mark.asyncio
async def test_user_can_get_enabled_instance(async_client, user_headers, monkeypatch):
    """User token can get an enabled instance."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )

    response = await async_client.get("/v1/models/instances/model-1", headers=user_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == "model-1"


@pytest.mark.asyncio
async def test_user_gets_404_for_disabled_instance(async_client, user_headers, monkeypatch):
    """User token gets 404 for disabled instance (existence hidden)."""
    instance = {"id": "disabled", "name": "Disabled", "enabled": False, "tenant_id": "tenant-test"}

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "disabled" else None,
    )

    response = await async_client.get("/v1/models/instances/disabled", headers=user_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    body = response.json()
    assert "not found" in body.get("title", "").lower() or "not found" in body.get("detail", "").lower()


@pytest.mark.asyncio
async def test_user_gets_404_for_nonexistent_instance(async_client, user_headers, monkeypatch):
    """User token gets 404 for truly nonexistent instance."""
    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: None,
    )

    response = await async_client.get("/v1/models/instances/nonexistent", headers=user_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ==============================================================================
# User Token Tests - Test Instance
# ==============================================================================


@pytest.mark.asyncio
async def test_user_can_test_enabled_instance(async_client, user_headers, monkeypatch):
    """User token can test an enabled instance."""
    instance = {
        "id": "model-1",
        "name": "Model 1",
        "enabled": True,
        "tenant_id": "tenant-test",
        "provider_id": "provider-1",
        "model_id": "gpt-4",
    }

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )

    # Mock provider and test execution
    from types import SimpleNamespace

    provider = SimpleNamespace(id="provider-1", type="openai_compatible", base_url="http://test:11434", config={})
    monkeypatch.setattr("src.routers.model_instances._repo.get_provider_internal", lambda _pid: provider)
    monkeypatch.setattr("src.routers.model_instances._provider_preflight", lambda _client: None)

    class _DummyResponse:
        status_code = status.HTTP_200_OK

        def json(self):
            return {"choices": [{"message": {"content": "test"}}], "usage": {"total_tokens": 10}}

    class _DummyClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def post(self, *_, **__):
            return _DummyResponse()

    monkeypatch.setattr("httpx.AsyncClient", _DummyClient)

    response = await async_client.post(
        "/v1/models/instances/model-1/tests",
        headers=user_headers,
        json={"prompt": "test"},
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_user_gets_409_testing_disabled_instance(async_client, user_headers, monkeypatch):
    """User token gets 409 Conflict when testing disabled instance."""
    instance = {
        "id": "disabled",
        "name": "Disabled",
        "enabled": False,
        "tenant_id": "tenant-test",
        "provider_id": "provider-1",
    }

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "disabled" else None,
    )

    response = await async_client.post(
        "/v1/models/instances/disabled/tests",
        headers=user_headers,
        json={"prompt": "test"},
    )

    assert response.status_code == status.HTTP_409_CONFLICT


# ==============================================================================
# User Token Tests - Create/Delete (Should Fail)
# ==============================================================================


@pytest.mark.asyncio
async def test_user_cannot_create_instance(async_client, user_headers):
    """User token cannot create model instances (403 Forbidden)."""
    response = await async_client.post(
        "/v1/models/instances",
        headers=user_headers,
        json={"name": "New Model", "provider_id": "provider-1", "model_id": "gpt-4"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_user_cannot_delete_instance(async_client, user_headers, monkeypatch):
    """User token cannot delete model instances (403 Forbidden)."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )

    response = await async_client.delete("/v1/models/instances/model-1", headers=user_headers)

    assert response.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# Admin Token Tests - Full Access
# ==============================================================================


@pytest.mark.asyncio
async def test_admin_can_see_all_instances(async_client, admin_headers, monkeypatch):
    """Admin token sees all instances (enabled and disabled)."""
    instances = [
        {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"},
        {"id": "model-2", "name": "Model 2", "enabled": False, "tenant_id": "tenant-test"},
    ]

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.list_instances",
        lambda **kwargs: instances,
    )

    response = await async_client.get("/v1/models/instances", headers=admin_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2  # Both enabled and disabled


@pytest.mark.asyncio
async def test_admin_can_get_disabled_instance(async_client, admin_headers, monkeypatch):
    """Admin token can get disabled instances."""
    instance = {"id": "disabled", "name": "Disabled", "enabled": False, "tenant_id": "tenant-test"}

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "disabled" else None,
    )

    response = await async_client.get("/v1/models/instances/disabled", headers=admin_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["enabled"] is False


@pytest.mark.asyncio
async def test_admin_can_create_instance(async_client, admin_headers, monkeypatch):
    """Admin token can create model instances."""
    created = {
        "id": "new-model",
        "name": "New Model",
        "provider_id": "provider-1",
        "model_id": "gpt-4",
        "enabled": True,
        "tenant_id": "tenant-test",
    }

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.create_instance",
        lambda **kwargs: created,
    )
    monkeypatch.setattr("src.routers.model_instances.record_provenance", lambda **_: None)

    response = await async_client.post(
        "/v1/models/instances",
        headers=admin_headers,
        json={"name": "New Model", "provider_id": "provider-1", "model_id": "gpt-4"},
    )

    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.asyncio
async def test_admin_can_delete_instance(async_client, admin_headers, monkeypatch):
    """Admin token can delete model instances."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )
    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.delete_instance",
        lambda _id, **kwargs: True,
    )
    monkeypatch.setattr(
        "src.routers.model_instances.user_default_repo.cascade_clear_defaults",
        lambda _id, **kwargs: None,
    )
    monkeypatch.setattr("src.routers.model_instances.record_provenance", lambda **_: None)

    response = await async_client.delete("/v1/models/instances/model-1", headers=admin_headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT


# ==============================================================================
# Deprecated Path Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_deprecated_admin_path_still_works(async_client, admin_headers, monkeypatch):
    """Deprecated /v1/admin/models/* path still works for backward compatibility."""
    instances = [
        {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"},
    ]

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.list_instances",
        lambda **kwargs: instances,
    )

    response = await async_client.get("/v1/admin/models/instances", headers=admin_headers)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_user_can_use_new_path(async_client, user_headers, monkeypatch):
    """User token works with new /v1/models/* path."""
    instances = [
        {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"},
    ]

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.list_instances",
        lambda **kwargs: [i for i in instances if i["enabled"]] if kwargs.get("enabled") else instances,
    )

    response = await async_client.get("/v1/models/instances", headers=user_headers)

    assert response.status_code == status.HTTP_200_OK


# ==============================================================================
# Default Model Tests - Precedence Resolution
# ==============================================================================


@pytest.mark.asyncio
async def test_get_defaults_user_precedence(async_client, user_headers, monkeypatch):
    """GET /defaults returns user-level default when it exists."""
    user_default = {
        "id": "user-default-1",
        "user_id": "user123",
        "tenant_id": "tenant-test",
        "chat_instance_id": "model-user",
        "instance": {"id": "model-user", "name": "User Model"},
    }

    monkeypatch.setattr(
        "src.routers.model_instances.user_default_repo.get_user_default",
        lambda user_id, tenant_id: user_default,
    )

    response = await async_client.get("/v1/models/defaults", headers=user_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == "model-user"
    assert response.headers.get("X-Default-Scope") == "user"


@pytest.mark.asyncio
async def test_get_defaults_tenant_precedence(async_client, user_headers, monkeypatch):
    """GET /defaults returns tenant default when no user default exists."""
    tenant_default = {"id": "model-tenant", "name": "Tenant Model", "scope": "tenant"}

    monkeypatch.setattr(
        "src.routers.model_instances.user_default_repo.get_user_default",
        lambda user_id, tenant_id: None,
    )
    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_default_model",
        lambda tenant_id=None, scope=None: tenant_default if scope == "tenant" else None,
    )

    response = await async_client.get("/v1/models/defaults", headers=user_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == "model-tenant"
    assert response.headers.get("X-Default-Scope") == "tenant"


@pytest.mark.asyncio
async def test_get_defaults_global_precedence(async_client, user_headers, monkeypatch):
    """GET /defaults returns global default when no user/tenant defaults exist."""
    global_default = {"id": "model-global", "name": "Global Model", "scope": "global"}

    monkeypatch.setattr(
        "src.routers.model_instances.user_default_repo.get_user_default",
        lambda user_id, tenant_id: None,
    )

    def _get_default(tenant_id=None, scope=None):
        if scope == "tenant":
            return None
        elif scope == "global":
            return global_default
        return None

    monkeypatch.setattr("src.routers.model_instances.model_instance_repo.get_default_model", _get_default)

    response = await async_client.get("/v1/models/defaults", headers=user_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == "model-global"
    assert response.headers.get("X-Default-Scope") == "global"


@pytest.mark.asyncio
async def test_get_defaults_404_when_none_exist(async_client, user_headers, monkeypatch):
    """GET /defaults returns 404 when no defaults exist at any level."""
    monkeypatch.setattr(
        "src.routers.model_instances.user_default_repo.get_user_default",
        lambda user_id, tenant_id: None,
    )
    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_default_model",
        lambda tenant_id=None, scope=None: None,
    )

    response = await async_client.get("/v1/models/defaults", headers=user_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ==============================================================================
# Default Model Tests - Scope-Based Writes
# ==============================================================================


@pytest.mark.asyncio
async def test_user_can_set_own_default(async_client, user_headers, monkeypatch):
    """User token can set own default (user scope)."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}
    user_default = {
        "id": "user-default-1",
        "user_id": "user123",
        "tenant_id": "tenant-test",
        "chat_instance_id": "model-1",
        "etag": "etag-123",
    }

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )
    monkeypatch.setattr(
        "src.routers.model_instances.user_default_repo.set_user_default",
        lambda user_id, tenant_id, instance_id: user_default,
    )
    monkeypatch.setattr("src.routers.model_instances.record_provenance", lambda **_: None)

    response = await async_client.patch(
        "/v1/models/defaults",
        headers={**user_headers, "X-Default-Scope": "user"},
        json={"chat_instance_id": "model-1"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("X-Default-Scope") == "user"
    assert response.headers.get("ETag") == '"etag-123"'


@pytest.mark.asyncio
async def test_user_cannot_set_tenant_default(async_client, user_headers, monkeypatch):
    """User token cannot set tenant-level defaults (403 Forbidden)."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )

    response = await async_client.patch(
        "/v1/models/defaults",
        headers={**user_headers, "X-Default-Scope": "tenant"},
        json={"chat_instance_id": "model-1"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_user_cannot_set_global_default(async_client, user_headers, monkeypatch):
    """User token cannot set global defaults (403 Forbidden)."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )

    response = await async_client.patch(
        "/v1/models/defaults",
        headers={**user_headers, "X-Default-Scope": "global"},
        json={"chat_instance_id": "model-1"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_tenant_admin_can_set_tenant_default(async_client, tenant_admin_headers, monkeypatch):
    """Tenant admin can set tenant-level defaults."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )
    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.set_default_model",
        lambda instance_id, scope, tenant_id=None: {**instance, "scope": scope, "etag": "etag-tenant"},
    )
    monkeypatch.setattr("src.routers.model_instances.record_provenance", lambda **_: None)

    response = await async_client.patch(
        "/v1/models/defaults",
        headers={**tenant_admin_headers, "X-Default-Scope": "tenant"},
        json={"chat_instance_id": "model-1"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("X-Default-Scope") == "tenant"


@pytest.mark.asyncio
async def test_admin_can_set_global_default(async_client, admin_headers, monkeypatch):
    """Admin token can set global defaults."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )
    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.set_default_model",
        lambda instance_id, scope, tenant_id=None: {**instance, "scope": scope, "etag": "etag-global"},
    )
    monkeypatch.setattr("src.routers.model_instances.record_provenance", lambda **_: None)

    response = await async_client.patch(
        "/v1/models/defaults",
        headers={**admin_headers, "X-Default-Scope": "global"},
        json={"chat_instance_id": "model-1"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("X-Default-Scope") == "global"


@pytest.mark.asyncio
async def test_patch_defaults_without_scope_defaults_to_user(async_client, user_headers, monkeypatch):
    """PATCH /defaults without X-Default-Scope header defaults to 'user' scope."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}
    user_default = {
        "id": "user-default-1",
        "user_id": "user123",
        "tenant_id": "tenant-test",
        "chat_instance_id": "model-1",
        "etag": "etag-123",
    }

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )
    monkeypatch.setattr(
        "src.routers.model_instances.user_default_repo.set_user_default",
        lambda user_id, tenant_id, instance_id: user_default,
    )
    monkeypatch.setattr("src.routers.model_instances.record_provenance", lambda **_: None)

    # No X-Default-Scope header
    response = await async_client.patch(
        "/v1/models/defaults",
        headers=user_headers,
        json={"chat_instance_id": "model-1"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("X-Default-Scope") == "user"


# ==============================================================================
# Permission Tests - Missing Scopes
# ==============================================================================


@pytest.mark.asyncio
async def test_limited_user_cannot_set_defaults(async_client, limited_user_headers, monkeypatch):
    """User without defaults:write:self cannot set own defaults."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )

    response = await async_client.patch(
        "/v1/models/defaults",
        headers=limited_user_headers,
        json={"chat_instance_id": "model-1"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_invalid_scope_returns_400(async_client, user_headers, monkeypatch):
    """Invalid X-Default-Scope value returns 400 Bad Request."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )

    response = await async_client.patch(
        "/v1/models/defaults",
        headers={**user_headers, "X-Default-Scope": "invalid-scope"},
        json={"chat_instance_id": "model-1"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# ETag and Caching Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_get_defaults_returns_etag(async_client, user_headers, monkeypatch):
    """GET /defaults returns ETag header for caching."""
    user_default = {
        "id": "user-default-1",
        "user_id": "user123",
        "tenant_id": "tenant-test",
        "chat_instance_id": "model-user",
        "etag": "etag-abc123",
        "instance": {"id": "model-user", "name": "User Model"},
    }

    monkeypatch.setattr(
        "src.routers.model_instances.user_default_repo.get_user_default",
        lambda user_id, tenant_id: user_default,
    )

    response = await async_client.get("/v1/models/defaults", headers=user_headers)

    assert response.status_code == status.HTTP_200_OK
    assert "ETag" in response.headers
    assert response.headers["ETag"] == '"etag-abc123"'


@pytest.mark.asyncio
async def test_patch_defaults_returns_etag(async_client, user_headers, monkeypatch):
    """PATCH /defaults returns ETag header."""
    instance = {"id": "model-1", "name": "Model 1", "enabled": True, "tenant_id": "tenant-test"}
    user_default = {
        "id": "user-default-1",
        "user_id": "user123",
        "tenant_id": "tenant-test",
        "chat_instance_id": "model-1",
        "etag": "etag-xyz789",
    }

    monkeypatch.setattr(
        "src.routers.model_instances.model_instance_repo.get_instance",
        lambda _id, **kwargs: instance if _id == "model-1" else None,
    )
    monkeypatch.setattr(
        "src.routers.model_instances.user_default_repo.set_user_default",
        lambda user_id, tenant_id, instance_id: user_default,
    )
    monkeypatch.setattr("src.routers.model_instances.record_provenance", lambda **_: None)

    response = await async_client.patch(
        "/v1/models/defaults",
        headers=user_headers,
        json={"chat_instance_id": "model-1"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert "ETag" in response.headers
    assert response.headers["ETag"] == '"etag-xyz789"'
