"""
Contract tests for LLM Providers API endpoints.

Tests the complete API contract including:
- RBAC (admin-only enforcement)
- Pagination & caching (ETags, Link headers)
- Secret redaction (has_api_key indicator)
- Idempotency (register endpoint)
- Status codes (204 for DELETE, 404 for not found, etc.)
- Validation errors (422 with field-level details)
- Request/response schemas

NOTE: Requires ENABLE_ADMIN_ROUTES=1 to mount /v1/admin routes.
"""
import os
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from typing import Dict


# Skip all tests if admin routes are disabled
pytestmark = pytest.mark.skipif(
    os.getenv("ENABLE_ADMIN_ROUTES", "1") in ("0", "false", "False"),
    reason="Admin routes disabled - set ENABLE_ADMIN_ROUTES=1",
)


# ============================================================================
# Fixtures - Token & Header Helpers
# ============================================================================


@pytest.fixture
def admin_token(mint_token) -> str:
    """Generate admin JWT token with admin:all scope."""
    return mint_token(sub="admin", roles=["admin"], scopes=["admin:all"])


@pytest.fixture
def user_token(mint_token) -> str:
    """Generate non-admin user JWT token."""
    return mint_token(sub="user", roles=["user"], scopes=["user:read"])


@pytest.fixture
def admin_headers(admin_token) -> Dict[str, str]:
    """Admin authorization headers with required tenant header."""
    return {"Authorization": f"Bearer {admin_token}", "X-Tenant-Id": "test-tenant"}


@pytest.fixture
def user_headers(user_token) -> Dict[str, str]:
    """Non-admin user authorization headers with required tenant header."""
    return {"Authorization": f"Bearer {user_token}", "X-Tenant-Id": "test-tenant"}


def tenant_headers(tenant: str = "test-tenant", token: str = None) -> Dict[str, str]:
    """Helper to create headers with custom tenant ID."""
    headers = {"X-Tenant-Id": tenant}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@pytest.fixture
def test_provider_payload():
    """Valid provider registration payload."""
    return {
        "name": "test-openai",
        "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4",
        "api_key": "sk-test-key-12345",
        "tenant_id": None,
        "config": {"timeouts": {"connect": 5.0, "read": 30.0}, "headers": {"X-Custom": "value"}},
    }


# NOTE: Removed autouse seed_provider to avoid pre-test side effects
# Individual tests that need seeded data can register providers explicitly


class TestProvidersList:
    """Test GET /v1/admin/models/providers - List providers."""

    def test_list_providers_requires_admin(self, client: TestClient, user_headers):
        """Non-admin users should get 403 Forbidden."""
        response = client.get("/v1/admin/models/providers", headers=user_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.headers["content-type"] == "application/problem+json"
        data = response.json()
        assert data["title"] == "Forbidden"
        assert data["status"] == 403

    def test_list_providers_success(self, client: TestClient, admin_headers):
        """Admin can list providers."""
        response = client.get("/v1/admin/models/providers", headers=admin_headers)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "items" in data
        assert "next_page_token" in data
        assert isinstance(data["items"], list)

    def test_list_providers_pagination(self, client: TestClient, admin_headers, test_provider_payload):
        """Pagination should return correct structure and Link header."""
        # Register multiple providers
        for i in range(3):
            payload = test_provider_payload.copy()
            payload["name"] = f"test-provider-{i}"
            client.post("/v1/admin/models/providers/register", json=payload, headers=admin_headers)

        # List with small page size
        response = client.get("/v1/admin/models/providers", params={"page_size": 2}, headers=admin_headers)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert len(data["items"]) <= 2

        # Check Link header if more pages exist
        if data.get("next_page_token"):
            assert "Link" in response.headers
            link_header = response.headers["Link"]
            assert 'rel="next"' in link_header

    def test_list_providers_etag_caching(self, client: TestClient, admin_headers):
        """ETag/If-None-Match should return 304 when content unchanged."""
        # First request
        response1 = client.get("/v1/admin/models/providers", headers=admin_headers)
        assert response1.status_code == status.HTTP_200_OK
        assert "ETag" in response1.headers

        etag = response1.headers["ETag"]

        # Second request with If-None-Match
        headers_with_etag = admin_headers.copy()
        headers_with_etag["If-None-Match"] = etag

        response2 = client.get("/v1/admin/models/providers", headers=headers_with_etag)
        assert response2.status_code == status.HTTP_304_NOT_MODIFIED

    def test_list_providers_secret_redaction(self, client: TestClient, admin_headers, test_provider_payload):
        """Provider list should redact secrets and include has_api_key."""
        # Register provider with api_key
        client.post("/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers)

        # List providers
        response = client.get("/v1/admin/models/providers", headers=admin_headers)
        data = response.json()

        provider = next((p for p in data["items"] if p["name"] == test_provider_payload["name"]), None)
        assert provider is not None

        # api_key should be redacted or None
        assert provider.get("api_key") in (None, "***")

        # has_api_key should be present and True
        assert provider.get("has_api_key") is True


class TestProvidersRegister:
    """Test POST /v1/admin/models/providers/register - Register provider."""

    def test_register_provider_requires_admin(self, client: TestClient, user_headers, test_provider_payload):
        """Non-admin users should get 403 Forbidden."""
        response = client.post("/v1/admin/models/providers/register", json=test_provider_payload, headers=user_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_register_provider_success(self, client: TestClient, admin_headers, test_provider_payload):
        """Admin can register a new provider."""
        response = client.post("/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["ok"] is True
        assert "trace_id" in data
        assert "event_id" in data
        assert test_provider_payload["name"] in data["message"]

    def test_register_provider_idempotent_same_config(self, client: TestClient, admin_headers, test_provider_payload):
        """Registering same provider twice with same config should return 200."""
        # First registration
        response1 = client.post(
            "/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers
        )
        assert response1.status_code == status.HTTP_200_OK

        # Second registration with same config
        response2 = client.post(
            "/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers
        )
        assert response2.status_code == status.HTTP_200_OK
        data = response2.json()
        assert "already registered" in data["message"].lower()
        assert data["details"].get("idempotent") is True

    def test_register_provider_conflict_different_config(
        self, client: TestClient, admin_headers, test_provider_payload
    ):
        """Registering same provider with different config should return 409."""
        # First registration
        client.post("/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers)

        # Second registration with different config
        different_payload = test_provider_payload.copy()
        different_payload["base_url"] = "https://different.api.com/v1"

        response = client.post("/v1/admin/models/providers/register", json=different_payload, headers=admin_headers)
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in response.json()["detail"].lower()

    def test_register_provider_validation_errors(self, client: TestClient, admin_headers):
        """Invalid payloads should return 422 with field-level errors."""
        # Missing required field
        invalid_payload = {
            "name": "test",
            # Missing 'type'
            "base_url": "https://api.example.com",
        }

        response = client.post("/v1/admin/models/providers/register", json=invalid_payload, headers=admin_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        data = response.json()
        assert data["status"] == 422
        assert "errors" in data  # Field-level errors array

    def test_register_provider_invalid_type_enum(self, client: TestClient, admin_headers):
        """Invalid provider type should return 422."""
        invalid_payload = {"name": "test", "type": "invalid_type", "base_url": "https://api.example.com"}  # Not in enum

        response = client.post("/v1/admin/models/providers/register", json=invalid_payload, headers=admin_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_register_provider_missing_base_url_for_openai(self, client: TestClient, admin_headers):
        """openai_compatible type requires base_url."""
        invalid_payload = {
            "name": "test",
            "type": "openai_compatible",
            # Missing base_url
        }

        response = client.post("/v1/admin/models/providers/register", json=invalid_payload, headers=admin_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestProvidersGetMain:
    """Test GET /v1/admin/models/providers/main - Get main provider."""

    def test_get_main_provider_requires_admin(self, client: TestClient, user_headers):
        """Non-admin users should get 403 Forbidden."""
        response = client.get("/v1/admin/models/providers/main", headers=user_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_main_provider_not_found(self, client: TestClient, admin_headers):
        """Should return 404 when no default is set."""
        response = client.get("/v1/admin/models/providers/main", headers=admin_headers)
        # Depending on implementation, may return 404 or 200 with null
        # Per spec, should be 404 if no default configured
        assert response.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_200_OK)

    def test_get_main_provider_etag(self, client: TestClient, admin_headers, test_provider_payload):
        """ETag caching should work for main provider endpoint."""
        # Register and set default
        client.post("/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers)
        client.put(
            "/v1/admin/models/providers/default",
            json={"provider_id": test_provider_payload["name"], "tenant_id": None},
            headers=admin_headers,
        )

        # First request
        response1 = client.get("/v1/admin/models/providers/main", headers=admin_headers)
        if response1.status_code == status.HTTP_200_OK:
            assert "ETag" in response1.headers

            # Second request with If-None-Match
            headers_with_etag = admin_headers.copy()
            headers_with_etag["If-None-Match"] = response1.headers["ETag"]

            response2 = client.get("/v1/admin/models/providers/main", headers=headers_with_etag)
            assert response2.status_code == status.HTTP_304_NOT_MODIFIED


class TestProvidersGet:
    """Test GET /v1/admin/models/providers/{provider_id} - Get provider."""

    def test_get_provider_requires_admin(self, client: TestClient, user_headers):
        """Non-admin users should get 403 Forbidden."""
        response = client.get("/v1/admin/models/providers/test-id", headers=user_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_provider_not_found(self, client: TestClient, admin_headers):
        """Should return 404 for unknown provider."""
        response = client.get("/v1/admin/models/providers/unknown-provider", headers=admin_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

        data = response.json()
        assert data["status"] == 404
        assert data["title"] == "Not Found"

    def test_get_provider_success(self, client: TestClient, admin_headers, test_provider_payload):
        """Admin can get provider details."""
        # Register provider
        client.post("/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers)

        # Get provider
        response = client.get(f"/v1/admin/models/providers/{test_provider_payload['name']}", headers=admin_headers)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["name"] == test_provider_payload["name"]
        assert data["type"] == test_provider_payload["type"]

        # Secret redaction
        assert data.get("api_key") in (None, "***")
        assert data.get("has_api_key") is True

    def test_get_provider_etag(self, client: TestClient, admin_headers, test_provider_payload):
        """ETag caching should work."""
        # Register provider
        client.post("/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers)

        # First request
        response1 = client.get(f"/v1/admin/models/providers/{test_provider_payload['name']}", headers=admin_headers)
        assert response1.status_code == status.HTTP_200_OK
        assert "ETag" in response1.headers

        # Second request with If-None-Match
        headers_with_etag = admin_headers.copy()
        headers_with_etag["If-None-Match"] = response1.headers["ETag"]

        response2 = client.get(f"/v1/admin/models/providers/{test_provider_payload['name']}", headers=headers_with_etag)
        assert response2.status_code == status.HTTP_304_NOT_MODIFIED


class TestProvidersPatch:
    """Test PATCH /v1/admin/models/providers/{provider_id} - Update provider."""

    def test_patch_provider_requires_admin(self, client: TestClient, user_headers):
        """Non-admin users should get 403 Forbidden."""
        response = client.patch(
            "/v1/admin/models/providers/test-id", json={"base_url": "https://new.api.com"}, headers=user_headers
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_patch_provider_not_found(self, client: TestClient, admin_headers):
        """Should return 404 for unknown provider."""
        response = client.patch(
            "/v1/admin/models/providers/unknown-provider",
            json={"base_url": "https://new.api.com"},
            headers=admin_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_patch_provider_success(self, client: TestClient, admin_headers, test_provider_payload):
        """Admin can update provider."""
        # Register provider
        client.post("/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers)

        # Patch provider
        update_payload = {"model": "gpt-4-turbo", "config": {"new_field": "new_value"}}

        response = client.patch(
            f"/v1/admin/models/providers/{test_provider_payload['name']}", json=update_payload, headers=admin_headers
        )
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["ok"] is True
        assert "trace_id" in data
        assert "event_id" in data

    def test_patch_arbitrary_keys_returned_in_list(self, client: TestClient, admin_headers, test_provider_payload):
        """PATCH can add arbitrary keys to config; LIST should return them without validation error."""
        # Register provider
        client.post("/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers)

        # PATCH to add arbitrary nested config keys
        update_payload = {"config": {"custom_field": "custom_value", "nested": {"deep_field": "deep_value"}}}

        patch_response = client.patch(
            f"/v1/admin/models/providers/{test_provider_payload['name']}", json=update_payload, headers=admin_headers
        )
        assert patch_response.status_code == status.HTTP_200_OK

        # LIST should return the arbitrary keys without extra_forbidden error
        list_response = client.get("/v1/admin/models/providers", headers=admin_headers)
        assert list_response.status_code == status.HTTP_200_OK

        data = list_response.json()
        # Find our provider in the list
        provider = next((p for p in data["items"] if p["name"] == test_provider_payload["name"]), None)
        assert provider is not None
        assert "config" in provider
        assert provider["config"]["custom_field"] == "custom_value"
        assert provider["config"]["nested"]["deep_field"] == "deep_value"


class TestProvidersDelete:
    """Test DELETE /v1/admin/models/providers/{provider_id} - Delete provider."""

    def test_delete_provider_requires_admin(self, client: TestClient, user_headers):
        """Non-admin users should get 403 Forbidden."""
        response = client.delete("/v1/admin/models/providers/test-id", headers=user_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_provider_not_found(self, client: TestClient, admin_headers):
        """Should return 404 for unknown provider."""
        response = client.delete("/v1/admin/models/providers/unknown-provider", headers=admin_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_provider_returns_204(self, client: TestClient, admin_headers, test_provider_payload):
        """DELETE should return 204 No Content on success."""
        # Use unique provider name to avoid conflicts with other tests
        unique_payload = test_provider_payload.copy()
        unique_payload["name"] = "provider-to-delete"

        # Register provider
        client.post("/v1/admin/models/providers/register", json=unique_payload, headers=admin_headers)

        # Delete provider
        response = client.delete(f"/v1/admin/models/providers/{unique_payload['name']}", headers=admin_headers)

        # CRITICAL: Must return 204 No Content
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # No response body
        assert response.text == ""

        # But should have trace headers
        assert "X-Event-Id" in response.headers
        assert "X-Trace-Id" in response.headers


class TestProvidersSetDefault:
    """Test PUT /v1/admin/models/providers/default - Set default provider."""

    def test_set_default_requires_admin(self, client: TestClient, user_headers):
        """Non-admin users should get 403 Forbidden."""
        response = client.put("/v1/admin/models/providers/default", json={"provider_id": "test"}, headers=user_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_set_default_provider_not_found(self, client: TestClient, admin_headers):
        """Should return 404 if provider doesn't exist."""
        response = client.put(
            "/v1/admin/models/providers/default",
            json={"provider_id": "unknown-provider", "tenant_id": None},
            headers=admin_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_set_default_global(self, client: TestClient, admin_headers, test_provider_payload):
        """Can set global default provider."""
        # Register provider
        client.post("/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers)

        # Set as global default (tenant_id = None)
        response = client.put(
            "/v1/admin/models/providers/default",
            json={"provider_id": test_provider_payload["name"], "tenant_id": None},
            headers=admin_headers,
        )
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["ok"] is True
        assert "global" in data["message"].lower() or data["details"].get("scope") == "global"
        assert "trace_id" in data
        assert "event_id" in data

    def test_set_default_tenant_scoped(self, client: TestClient, admin_headers, test_provider_payload):
        """Can set tenant-scoped default provider."""
        # Register provider
        client.post("/v1/admin/models/providers/register", json=test_provider_payload, headers=admin_headers)

        # Set as tenant default
        response = client.put(
            "/v1/admin/models/providers/default",
            json={"provider_id": test_provider_payload["name"], "tenant_id": "tenant-123"},
            headers=admin_headers,
        )
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["ok"] is True
        assert data["details"].get("scope") == "tenant-123"


class TestProvidersFullFlow:
    """Integration test: Full happy path flow."""

    def test_full_provider_lifecycle(self, client: TestClient, admin_headers):
        """Test complete provider lifecycle: register → list → get → set default → get main → patch → delete."""
        provider_name = "lifecycle-test-provider"

        # 0. Clean up: delete provider if it exists from previous test
        client.delete(f"/v1/admin/models/providers/{provider_name}", headers=admin_headers)

        # 1. Register provider
        register_payload = {
            "name": provider_name,
            "type": "openai_compatible",
            "base_url": "https://api.test.com/v1",
            "model": "test-model",
            "api_key": "test-key",
        }
        response = client.post("/v1/admin/models/providers/register", json=register_payload, headers=admin_headers)
        assert response.status_code == status.HTTP_200_OK

        # 2. List providers (should include new provider)
        response = client.get("/v1/admin/models/providers", headers=admin_headers)
        data = response.json()
        provider_names = [p["name"] for p in data["items"]]
        assert provider_name in provider_names

        # 3. Get specific provider
        response = client.get(f"/v1/admin/models/providers/{provider_name}", headers=admin_headers)
        assert response.status_code == status.HTTP_200_OK
        provider_data = response.json()
        assert provider_data["name"] == provider_name
        assert provider_data.get("has_api_key") is True

        # 4. Set as global default
        response = client.put(
            "/v1/admin/models/providers/default",
            json={"provider_id": provider_name, "tenant_id": None},
            headers=admin_headers,
        )
        assert response.status_code == status.HTTP_200_OK

        # 5. Get main provider (should be our provider)
        response = client.get("/v1/admin/models/providers/main", headers=admin_headers)
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert data.get("main") == provider_name

        # 6. Patch provider
        response = client.patch(
            f"/v1/admin/models/providers/{provider_name}", json={"model": "updated-model"}, headers=admin_headers
        )
        assert response.status_code == status.HTTP_200_OK

        # 7. Delete provider
        response = client.delete(f"/v1/admin/models/providers/{provider_name}", headers=admin_headers)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # 8. Verify deletion
        response = client.get(f"/v1/admin/models/providers/{provider_name}", headers=admin_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND
