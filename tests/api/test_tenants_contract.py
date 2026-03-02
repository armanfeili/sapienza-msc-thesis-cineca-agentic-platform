"""
Contract tests for Tenants API endpoints.

Tests the complete API contract including:
- RBAC (admin:all enforcement)
- Pagination & caching (ETags, Link headers)
- Email validation (RFC 5322 compliance)
- Idempotency (create endpoint)
- Status codes (204 for DELETE, 404 for not found, etc.)
- Validation errors (422 with field-level details)
- Metadata deep-merge semantics
- Server-generated tenant IDs
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


@pytest.fixture
def test_tenant_payload():
    """Valid tenant creation payload."""
    return {
        "name": "Acme Corporation",
        "admin_email": "admin@acme.com",
        "metadata": {"region": "us-east-1", "tier": "enterprise", "billing_id": "ACME-2024-001"},
    }


# ============================================================================
# Test: LIST Tenants
# ============================================================================


class TestTenantsList:
    """Test GET /v1/admin/tenants - List tenants."""

    def test_list_tenants_requires_admin(self, client: TestClient, user_headers):
        """Non-admin users should get 403 Forbidden."""
        response = client.get("/v1/admin/tenants", headers=user_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.headers["content-type"] == "application/problem+json"
        data = response.json()
        assert data["title"] == "Forbidden"

    def test_list_tenants_returns_paginated_response(self, client: TestClient, admin_headers):
        """List endpoint returns TenantListResponse schema with items/total."""
        response = client.get("/v1/admin/tenants", headers=admin_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify TenantListResponse structure
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int)

        # Optional pagination field
        assert "next_page_token" in data or data.get("next_page_token") is None

    def test_list_tenants_with_pagination(self, client: TestClient, admin_headers):
        """Pagination works correctly with page_size and page_token."""
        # Create 15 tenants
        for i in range(15):
            client.post(
                "/v1/admin/tenants",
                json={"name": f"Tenant {i}", "admin_email": f"admin{i}@test.com", "metadata": {}},
                headers=admin_headers,
            )

        # First page
        r1 = client.get("/v1/admin/tenants?page_size=10", headers=admin_headers)
        assert r1.status_code == status.HTTP_200_OK
        page1 = r1.json()
        assert len(page1["items"]) == 10
        assert page1["total"] == 15
        assert "next_page_token" in page1
        assert page1["next_page_token"] is not None

        # Second page
        next_token = page1["next_page_token"]
        r2 = client.get(f"/v1/admin/tenants?page_size=10&page_token={next_token}", headers=admin_headers)
        assert r2.status_code == status.HTTP_200_OK
        page2 = r2.json()
        assert len(page2["items"]) == 5  # Remaining items
        assert page2["total"] == 15
        assert page2.get("next_page_token") is None  # Last page

    def test_list_tenants_link_header(self, client: TestClient, admin_headers):
        """Link header present when next page exists."""
        # Create 11 tenants
        for i in range(11):
            client.post(
                "/v1/admin/tenants",
                json={"name": f"Tenant {i}", "admin_email": f"admin{i}@test.com"},
                headers=admin_headers,
            )

        response = client.get("/v1/admin/tenants?page_size=10", headers=admin_headers)
        assert response.status_code == status.HTTP_200_OK
        assert "Link" in response.headers
        link_header = response.headers["Link"]
        assert 'rel="next"' in link_header
        assert "page_token=" in link_header

    def test_list_tenants_etag_caching(self, client: TestClient, admin_headers):
        """ETag header present and If-None-Match returns 304."""
        # First request
        r1 = client.get("/v1/admin/tenants", headers=admin_headers)
        assert r1.status_code == status.HTTP_200_OK
        assert "ETag" in r1.headers
        etag = r1.headers["ETag"]

        # Second request with If-None-Match
        headers_with_etag = {**admin_headers, "If-None-Match": etag}
        r2 = client.get("/v1/admin/tenants", headers=headers_with_etag)
        assert r2.status_code == status.HTTP_304_NOT_MODIFIED


# ============================================================================
# Test: CREATE Tenant
# ============================================================================


class TestTenantsCreate:
    """Test POST /v1/admin/tenants - Create tenant."""

    def test_create_tenant_requires_admin(self, client: TestClient, user_headers, test_tenant_payload):
        """Non-admin users should get 403 Forbidden."""
        response = client.post("/v1/admin/tenants", json=test_tenant_payload, headers=user_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_tenant_requires_x_tenant_id_header(self, client: TestClient, admin_token, test_tenant_payload):
        """Create endpoint requires X-Tenant-Id header (422 validation error)."""
        headers = {"Authorization": f"Bearer {admin_token}"}  # Missing X-Tenant-Id
        response = client.post("/v1/admin/tenants", json=test_tenant_payload, headers=headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        # FastAPI validation error should mention the header
        data = response.json()
        assert "detail" in data

    def test_create_tenant_success(self, client: TestClient, admin_headers, test_tenant_payload):
        """Valid tenant creation returns 201 with server-generated ID."""
        response = client.post("/v1/admin/tenants", json=test_tenant_payload, headers=admin_headers)
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        # Verify response structure
        assert "id" in data
        assert data["id"].startswith("tenant-")  # Server-generated ID format
        assert data["name"] == test_tenant_payload["name"]
        assert data["admin_email"] == test_tenant_payload["admin_email"]
        assert data["metadata"] == test_tenant_payload["metadata"]
        assert "created_at" in data
        assert "updated_at" in data

        # Verify headers
        assert "Location" in response.headers
        assert response.headers["Location"] == f"/v1/admin/tenants/{data['id']}"
        assert "X-Event-Id" in response.headers
        assert "X-Trace-Id" in response.headers

    def test_create_tenant_validates_email(self, client: TestClient, admin_headers):
        """Invalid email returns 422 validation error."""
        invalid_payload = {"name": "Bad Email Corp", "admin_email": "not-an-email", "metadata": {}}
        response = client.post("/v1/admin/tenants", json=invalid_payload, headers=admin_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert "detail" in data
        # Pydantic validation error for email field - RFC 7807 format has errors array
        assert "errors" in data
        assert any("admin_email" in err.get("loc", []) for err in data["errors"])

    def test_create_tenant_permissive_metadata(self, client: TestClient, admin_headers):
        """Metadata accepts arbitrary keys (permissive schema)."""
        payload = {
            "name": "Flexible Metadata Corp",
            "admin_email": "admin@flexible.com",
            "metadata": {
                "custom_field_1": "value1",
                "nested": {"key": "value"},
                "array": [1, 2, 3],
                "number": 42,
                "boolean": True,
            },
        }
        response = client.post("/v1/admin/tenants", json=payload, headers=admin_headers)
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["metadata"] == payload["metadata"]

    def test_create_tenant_idempotent(self, client: TestClient, admin_headers):
        """Creating tenant with same config returns 200 OK (idempotent)."""
        payload = {"name": "Idempotent Test Corp", "admin_email": "admin@idempotent.com", "metadata": {"key": "value"}}

        # First request: creates tenant (201)
        response1 = client.post("/v1/admin/tenants", json=payload, headers=admin_headers)
        assert response1.status_code == status.HTTP_201_CREATED
        data1 = response1.json()
        tenant_id1 = data1["id"]
        created_at1 = data1["created_at"]

        # Second request with identical payload: idempotent (200)
        response2 = client.post("/v1/admin/tenants", json=payload, headers=admin_headers)
        assert response2.status_code == status.HTTP_200_OK
        data2 = response2.json()

        # Should return same tenant
        assert data2["id"] == tenant_id1
        assert data2["name"] == payload["name"]
        assert data2["admin_email"] == payload["admin_email"]
        assert data2["metadata"] == payload["metadata"]

        # Timestamps should NOT change (idempotent)
        assert data2["created_at"] == created_at1
        assert data2["updated_at"] == data1["updated_at"]

        # Headers should still be present
        assert "Location" in response2.headers
        assert "ETag" in response2.headers
        assert "X-Event-Id" in response2.headers


# ============================================================================
# Test: GET Tenant by ID
# ============================================================================


class TestTenantsGet:
    """Test GET /v1/admin/tenants/{tenant_id} - Get tenant by ID."""

    def test_get_tenant_requires_admin(self, client: TestClient, user_headers):
        """Non-admin users should get 403 Forbidden."""
        response = client.get("/v1/admin/tenants/tenant-123", headers=user_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_tenant_not_found(self, client: TestClient, admin_headers):
        """Non-existent tenant returns 404."""
        response = client.get("/v1/admin/tenants/tenant-nonexistent", headers=admin_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.text.lower()

    def test_get_tenant_success(self, client: TestClient, admin_headers):
        """Retrieve existing tenant by ID."""
        # Create tenant
        create_resp = client.post(
            "/v1/admin/tenants",
            json={"name": "Get Test Corp", "admin_email": "admin@gettest.com"},
            headers=admin_headers,
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        tenant_id = create_resp.json()["id"]

        # Get tenant
        get_resp = client.get(f"/v1/admin/tenants/{tenant_id}", headers=admin_headers)
        assert get_resp.status_code == status.HTTP_200_OK
        data = get_resp.json()
        assert data["id"] == tenant_id
        assert data["name"] == "Get Test Corp"
        assert data["admin_email"] == "admin@gettest.com"


# ============================================================================
# Test: PATCH Tenant
# ============================================================================


class TestTenantsPatch:
    """Test PATCH /v1/admin/tenants/{tenant_id} - Update tenant."""

    def test_patch_tenant_requires_admin(self, client: TestClient, user_headers):
        """Non-admin users should get 403 Forbidden."""
        response = client.patch("/v1/admin/tenants/tenant-123", json={"name": "New Name"}, headers=user_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_patch_tenant_not_found(self, client: TestClient, admin_headers):
        """Patching non-existent tenant returns 404."""
        response = client.patch("/v1/admin/tenants/tenant-nonexistent", json={"name": "New"}, headers=admin_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_patch_tenant_empty_body(self, client: TestClient, admin_headers):
        """Empty PATCH body returns 400."""
        # Create tenant first
        create_resp = client.post(
            "/v1/admin/tenants", json={"name": "Patch Test", "admin_email": "admin@patch.com"}, headers=admin_headers
        )
        tenant_id = create_resp.json()["id"]

        # Empty PATCH
        response = client.patch(f"/v1/admin/tenants/{tenant_id}", json={}, headers=admin_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "at least one field" in response.text.lower()

    def test_patch_tenant_name(self, client: TestClient, admin_headers):
        """Partial update of name field."""
        # Create tenant
        create_resp = client.post(
            "/v1/admin/tenants",
            json={"name": "Old Name", "admin_email": "admin@oldname.com", "metadata": {"key": "value"}},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["id"]

        # Update name only
        patch_resp = client.patch(f"/v1/admin/tenants/{tenant_id}", json={"name": "New Name"}, headers=admin_headers)
        assert patch_resp.status_code == status.HTTP_200_OK
        data = patch_resp.json()
        assert data["name"] == "New Name"
        assert data["admin_email"] == "admin@oldname.com"  # Unchanged
        assert data["metadata"] == {"key": "value"}  # Unchanged

        # Verify headers
        assert "X-Event-Id" in patch_resp.headers
        assert "X-Trace-Id" in patch_resp.headers

    def test_patch_tenant_metadata_deep_merge(self, client: TestClient, admin_headers):
        """Metadata deep-merge preserves existing keys."""
        # Create tenant with initial metadata
        create_resp = client.post(
            "/v1/admin/tenants",
            json={
                "name": "Merge Test",
                "admin_email": "admin@merge.com",
                "metadata": {
                    "region": "us-east-1",
                    "tier": "enterprise",
                    "nested": {"key1": "value1", "key2": "value2"},
                },
            },
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["id"]

        # Update metadata (deep merge)
        patch_resp = client.patch(
            f"/v1/admin/tenants/{tenant_id}",
            json={
                "metadata": {
                    "tier": "premium",  # Override
                    "new_key": "new_value",  # Add
                    "nested": {"key2": "updated", "key3": "value3"},  # Merge nested
                }
            },
            headers=admin_headers,
        )
        assert patch_resp.status_code == status.HTTP_200_OK
        data = patch_resp.json()

        # Verify deep merge
        assert data["metadata"]["region"] == "us-east-1"  # Preserved
        assert data["metadata"]["tier"] == "premium"  # Updated
        assert data["metadata"]["new_key"] == "new_value"  # Added
        assert data["metadata"]["nested"]["key1"] == "value1"  # Preserved
        assert data["metadata"]["nested"]["key2"] == "updated"  # Updated
        assert data["metadata"]["nested"]["key3"] == "value3"  # Added

    def test_patch_tenant_metadata_remove_keys(self, client: TestClient, admin_headers):
        """Setting metadata keys to null removes them."""
        # Create tenant
        create_resp = client.post(
            "/v1/admin/tenants",
            json={
                "name": "Remove Test",
                "admin_email": "admin@remove.com",
                "metadata": {"key1": "value1", "key2": "value2", "key3": "value3"},
            },
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["id"]

        # Remove key2 by setting to null
        patch_resp = client.patch(
            f"/v1/admin/tenants/{tenant_id}", json={"metadata": {"key2": None}}, headers=admin_headers
        )
        assert patch_resp.status_code == status.HTTP_200_OK
        data = patch_resp.json()

        # Verify key removed
        assert "key1" in data["metadata"]
        assert "key2" not in data["metadata"]  # Removed
        assert "key3" in data["metadata"]


# ============================================================================
# Test: DELETE Tenant
# ============================================================================


class TestTenantsDelete:
    """Test DELETE /v1/admin/tenants/{tenant_id} - Delete tenant."""

    def test_delete_tenant_requires_admin(self, client: TestClient, user_headers):
        """Non-admin users should get 403 Forbidden."""
        response = client.delete("/v1/admin/tenants/tenant-123", headers=user_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_tenant_not_found(self, client: TestClient, admin_headers):
        """Deleting non-existent tenant returns 404."""
        response = client.delete("/v1/admin/tenants/tenant-nonexistent", headers=admin_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_tenant_success(self, client: TestClient, admin_headers):
        """Delete tenant returns 204 with proper headers."""
        # Create tenant
        create_resp = client.post(
            "/v1/admin/tenants", json={"name": "Delete Test", "admin_email": "admin@delete.com"}, headers=admin_headers
        )
        tenant_id = create_resp.json()["id"]

        # Delete tenant
        delete_resp = client.delete(f"/v1/admin/tenants/{tenant_id}", headers=admin_headers)
        assert delete_resp.status_code == status.HTTP_204_NO_CONTENT
        assert delete_resp.text == ""  # No body

        # Verify headers present
        assert "X-Event-Id" in delete_resp.headers
        assert "X-Trace-Id" in delete_resp.headers

        # Verify tenant deleted
        get_resp = client.get(f"/v1/admin/tenants/{tenant_id}", headers=admin_headers)
        assert get_resp.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_tenant_idempotent(self, client: TestClient, admin_headers):
        """Deleting same tenant twice returns 404 on second attempt."""
        # Create and delete tenant
        create_resp = client.post(
            "/v1/admin/tenants",
            json={"name": "Idempotent Delete", "admin_email": "admin@idempotent.com"},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["id"]

        # First delete
        delete1 = client.delete(f"/v1/admin/tenants/{tenant_id}", headers=admin_headers)
        assert delete1.status_code == status.HTTP_204_NO_CONTENT

        # Second delete - not idempotent, returns 404
        delete2 = client.delete(f"/v1/admin/tenants/{tenant_id}", headers=admin_headers)
        assert delete2.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_tenant_with_dependencies(self, client: TestClient, admin_headers):
        """Cannot delete tenant with dependent resources (409 Conflict)."""
        from src.services.tenants import set_test_dependencies, clear_test_dependencies

        # Create tenant
        create_resp = client.post(
            "/v1/admin/tenants",
            json={"name": "Has Dependencies", "admin_email": "admin@deps.com"},
            headers=admin_headers,
        )
        tenant_id = create_resp.json()["id"]

        # Inject test dependencies (mocking provider and job dependencies)
        blockers = [
            {"type": "provider", "id": "provider-abc", "name": "OpenAI GPT-4"},
            {"type": "job", "id": "job-xyz", "status": "running"},
        ]
        set_test_dependencies(tenant_id, blockers)

        try:
            # Attempt to delete should fail with 409
            delete_resp = client.delete(f"/v1/admin/tenants/{tenant_id}", headers=admin_headers)
            assert delete_resp.status_code == status.HTTP_409_CONFLICT

            # Verify error response structure (RFC 7807)
            data = delete_resp.json()
            assert data["type"] == "https://example.com/probs/conflict"
            assert data["title"] == "Conflict"
            assert data["status"] == 409
            assert "dependent resources" in data["detail"].lower()
            assert "extensions" in data
            assert "blockers" in data["extensions"]
            assert len(data["extensions"]["blockers"]) == 2

            # Verify tenant still exists
            get_resp = client.get(f"/v1/admin/tenants/{tenant_id}", headers=admin_headers)
            assert get_resp.status_code == status.HTTP_200_OK
        finally:
            # Cleanup: clear dependencies and delete tenant
            clear_test_dependencies()
            client.delete(f"/v1/admin/tenants/{tenant_id}", headers=admin_headers)


# ============================================================================
# Test: Full CRUD Workflow
# ============================================================================


class TestTenantsCRUDWorkflow:
    """Test complete CRUD lifecycle."""

    def test_full_crud_workflow(self, client: TestClient, admin_headers):
        """CREATE → GET → LIST → PATCH → DELETE → 404."""
        # 1. CREATE
        create_resp = client.post(
            "/v1/admin/tenants",
            json={"name": "Workflow Corp", "admin_email": "admin@workflow.com", "metadata": {"plan": "starter"}},
            headers=admin_headers,
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        tenant_id = create_resp.json()["id"]

        # 2. GET
        get_resp = client.get(f"/v1/admin/tenants/{tenant_id}", headers=admin_headers)
        assert get_resp.status_code == status.HTTP_200_OK
        assert get_resp.json()["name"] == "Workflow Corp"

        # 3. LIST (verify tenant appears)
        list_resp = client.get("/v1/admin/tenants", headers=admin_headers)
        assert list_resp.status_code == status.HTTP_200_OK
        tenant_ids = [t["id"] for t in list_resp.json()["items"]]
        assert tenant_id in tenant_ids

        # 4. PATCH
        patch_resp = client.patch(
            f"/v1/admin/tenants/{tenant_id}",
            json={"name": "Workflow Corp Updated", "metadata": {"plan": "enterprise"}},
            headers=admin_headers,
        )
        assert patch_resp.status_code == status.HTTP_200_OK
        assert patch_resp.json()["name"] == "Workflow Corp Updated"
        assert patch_resp.json()["metadata"]["plan"] == "enterprise"

        # 5. DELETE
        delete_resp = client.delete(f"/v1/admin/tenants/{tenant_id}", headers=admin_headers)
        assert delete_resp.status_code == status.HTTP_204_NO_CONTENT

        # 6. Verify 404
        get_after_delete = client.get(f"/v1/admin/tenants/{tenant_id}", headers=admin_headers)
        assert get_after_delete.status_code == status.HTTP_404_NOT_FOUND
