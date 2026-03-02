"""
RBAC Integration Tests

Verifies role-based access control and permission enforcement.
Tests that admin endpoints are properly guarded.

Acceptance Checklist Item: #12
"""
import pytest


class TestRoleBasedAccessControl:
    """Test RBAC enforcement across endpoints."""

    def test_user_cannot_access_admin_endpoints(self, client, mint_token):
        """Users without admin scopes should not access admin endpoints."""
        # Get user token (read:own, write:own only)
        user_token = mint_token(scopes=["read:own", "write:own"])
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # Try to access admin endpoints
        admin_endpoints = [
            "/v1/admin/users",
            "/v1/admin/providers",
            "/v1/admin/processes",
            "/v1/admin/manifests",
        ]

        for endpoint in admin_endpoints:
            response = client.get(endpoint, headers=user_headers)
            assert response.status_code == 403, f"User should not access {endpoint} (got {response.status_code})"

    def test_admin_can_access_admin_endpoints(self, client, bearer_headers):
        """Admins with proper scopes should access admin endpoints."""
        # bearer_headers fixture includes admin scopes (read:all, write:all)

        response = client.get("/v1/admin/users", headers=bearer_headers)
        assert response.status_code in [
            200,
            201,
            204,
        ], f"Admin should access admin endpoints (got {response.status_code})"

    def test_user_can_access_own_resources(self, client, mint_token):
        """Users should access their own resources."""
        user_token = mint_token(scopes=["read:own", "write:own"])
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # User should access their own sessions
        response = client.get("/v1/sessions", headers=user_headers)
        assert response.status_code == 200, "User should access their own sessions"

    def test_insufficient_scopes_returns_403(self, client, mint_token):
        """Requests with insufficient scopes should return 403."""
        # Token with only read:own (no write)
        read_only_token = mint_token(scopes=["read:own"])
        read_headers = {"Authorization": f"Bearer {read_only_token}"}

        # Try to create resource (requires write)
        response = client.post("/v1/sessions", headers=read_headers, json={"title": "Test"})

        assert response.status_code == 403, "Insufficient scopes should return 403"

    def test_no_token_returns_401(self, client):
        """Requests without authentication should return 401."""
        response = client.get("/v1/sessions")

        assert response.status_code == 401, "Missing authentication should return 401"

    def test_invalid_token_returns_401(self, client):
        """Requests with invalid token should return 401."""
        invalid_headers = {"Authorization": "Bearer invalid-token-12345"}

        response = client.get("/v1/sessions", headers=invalid_headers)

        assert response.status_code == 401, "Invalid token should return 401"
