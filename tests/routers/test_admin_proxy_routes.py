"""
Tests for admin-facing proxy routes (/v1/admin/ops/* and /v1/admin/db/*).

Verifies that:
- Admin tokens (admin:all) can access /v1/admin/* routes
- User tokens (tools:invoke:basic) get 403 on /v1/admin/* routes
- Admin tokens get 403 on /v1/internal/* routes (unchanged)
- Admin and internal routes share the same storage layer (Redis/PostgreSQL)
"""

import json
import pytest
from fastapi import status
from unittest.mock import AsyncMock, MagicMock, patch

from src.security.jwt import Principal


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def admin_principal():
    """Principal with admin:all scope."""
    return Principal(
        sub="auth0|admin123",
        scopes=("admin:all", "user:me"),
        raw={
            "iss": "https://cineca.eu.auth0.com/",
            "aud": "api://cineca-agentic-platform",
            "scope": "admin:all user:me",
        },
    )


@pytest.fixture
def user_principal():
    """Principal with basic user scope."""
    return Principal(
        sub="auth0|user456",
        scopes=("user:me", "tools:invoke:basic"),
        raw={
            "iss": "https://cineca.eu.auth0.com/",
            "aud": "api://cineca-agentic-platform",
            "scope": "user:me tools:invoke:basic",
        },
    )


@pytest.fixture
def mock_redis():
    """Mock async Redis client."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    return mock


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    mock = MagicMock()
    mock.add = MagicMock()
    mock.commit = MagicMock()
    mock.close = MagicMock()
    return mock


# ============================================================================
# Admin Ops Tests
# ============================================================================


class TestAdminOpsAutoStartOverride:
    """Tests for POST /v1/admin/ops/auto-start-override"""

    @patch("src.routers.admin_ops.get_async_redis")
    @patch("src.routers.admin_ops.SessionLocal")
    @patch("src.routers.admin_ops.settings")
    def test_admin_can_set_override(
        self, mock_settings, mock_session_local, mock_get_redis, client, admin_principal, mock_redis, mock_db_session
    ):
        """Admin token successfully sets auto-start override."""
        # Setup mocks
        mock_settings.INTERNAL_UI_OVERRIDE_ALLOWED = True
        mock_settings.INTERNAL_UI_OVERRIDE_TTL_SECONDS = 600
        mock_get_redis.return_value = mock_redis
        mock_session_local.return_value = mock_db_session

        # Mock authentication
        with patch("src.security.jwt.get_current_principal", return_value=admin_principal):
            response = client.post(
                "/v1/admin/ops/auto-start-override", json={"enabled": True, "note": "Testing admin override"}
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["allowed"] is True
        assert data["enabled"] is True
        assert data["ttl_seconds"] == 600
        assert data.get("error") is None

        # Verify Redis was called with correct key
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "internal:auto_start_override"
        assert call_args[0][1] == 600

    @patch("src.security.jwt.get_current_principal")
    def test_user_token_forbidden(self, mock_get_principal, client, user_principal):
        """User token gets 403 on admin override endpoint."""
        mock_get_principal.return_value = user_principal

        response = client.post("/v1/admin/ops/auto-start-override", json={"enabled": True})

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("src.routers.admin_ops.get_async_redis")
    @patch("src.routers.admin_ops.SessionLocal")
    @patch("src.routers.admin_ops.settings")
    def test_config_disabled_returns_graceful_response(
        self, mock_settings, mock_session_local, mock_get_redis, client, admin_principal, mock_redis, mock_db_session
    ):
        """Config disabled returns 200 with allowed=false."""
        mock_settings.INTERNAL_UI_OVERRIDE_ALLOWED = False
        mock_get_redis.return_value = mock_redis
        mock_session_local.return_value = mock_db_session

        with patch("src.security.jwt.get_current_principal", return_value=admin_principal):
            response = client.post("/v1/admin/ops/auto-start-override", json={"enabled": True})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["allowed"] is False
        assert data["enabled"] is False
        assert data["ttl_seconds"] == 0


class TestAdminOpsPreviewStaged:
    """Tests for GET /v1/admin/ops/preview-staged"""

    @patch("src.routers.admin_ops.get_async_redis")
    def test_admin_can_preview(self, mock_get_redis, client, admin_principal, mock_redis):
        """Admin token successfully previews staged manifests."""
        mock_get_redis.return_value = mock_redis

        with patch("src.security.jwt.get_current_principal", return_value=admin_principal):
            response = client.get("/v1/admin/ops/preview-staged")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert "count" in data
        assert "override_active" in data
        assert "timestamp" in data

    @patch("src.security.jwt.get_current_principal")
    def test_user_token_forbidden(self, mock_get_principal, client, user_principal):
        """User token gets 403 on preview endpoint."""
        mock_get_principal.return_value = user_principal

        response = client.get("/v1/admin/ops/preview-staged")

        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# Admin DB Tests
# ============================================================================


class TestAdminDbJobs:
    """Tests for /v1/admin/db/jobs endpoints"""

    @patch("src.routers.admin_db.get_async_redis")
    def test_admin_can_create_job(self, mock_get_redis, client, admin_principal, mock_redis):
        """Admin token successfully creates DB job."""
        mock_get_redis.return_value = mock_redis

        with patch("src.security.jwt.get_current_principal", return_value=admin_principal):
            response = client.post("/v1/admin/db/jobs", json={"kind": "migrate", "target": "postgres"})

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["ok"] is True
        assert "job_id" in data
        assert "Location" in response.headers

    @patch("src.routers.admin_db.get_async_redis")
    def test_idempotency_key_prevents_duplicate(self, mock_get_redis, client, admin_principal, mock_redis):
        """Idempotency-Key prevents duplicate job creation."""
        # First call creates job
        mock_redis.get = AsyncMock(return_value=None)
        mock_get_redis.return_value = mock_redis

        with patch("src.security.jwt.get_current_principal", return_value=admin_principal):
            response1 = client.post(
                "/v1/admin/db/jobs",
                json={"kind": "vacuum", "target": "postgres"},
                headers={"Idempotency-Key": "test-key-123"},
            )

        assert response1.status_code == status.HTTP_202_ACCEPTED
        job_id1 = response1.json()["job_id"]

        # Second call with same key returns cached job
        mock_redis.get = AsyncMock(return_value=job_id1.encode())

        with patch("src.security.jwt.get_current_principal", return_value=admin_principal):
            response2 = client.post(
                "/v1/admin/db/jobs",
                json={"kind": "vacuum", "target": "postgres"},
                headers={"Idempotency-Key": "test-key-123"},
            )

        assert response2.status_code == status.HTTP_202_ACCEPTED
        job_id2 = response2.json()["job_id"]
        assert job_id1 == job_id2

    @patch("src.routers.admin_db.get_async_redis")
    def test_admin_can_get_job_status(self, mock_get_redis, client, admin_principal, mock_redis):
        """Admin token can check job status."""
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_redis.get = AsyncMock(return_value=b'{"state": "running"}')
        mock_get_redis.return_value = mock_redis

        with patch("src.security.jwt.get_current_principal", return_value=admin_principal):
            response = client.get(f"/v1/admin/db/jobs/{job_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["job_id"] == job_id
        assert "state" in data

    @patch("src.routers.admin_db.get_async_redis")
    def test_job_not_found_returns_404(self, mock_get_redis, client, admin_principal, mock_redis):
        """Non-existent job returns 404."""
        mock_redis.get = AsyncMock(return_value=None)
        mock_get_redis.return_value = mock_redis

        with patch("src.security.jwt.get_current_principal", return_value=admin_principal):
            response = client.get("/v1/admin/db/jobs/nonexistent-job")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("src.routers.admin_db.get_async_redis")
    def test_admin_can_cancel_job(self, mock_get_redis, client, admin_principal, mock_redis):
        """Admin token can cancel job."""
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_get_redis.return_value = mock_redis

        with patch("src.security.jwt.get_current_principal", return_value=admin_principal):
            response = client.delete(f"/v1/admin/db/jobs/{job_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_redis.delete.assert_called_once()

    @patch("src.security.jwt.get_current_principal")
    def test_user_token_forbidden_on_jobs(self, mock_get_principal, client, user_principal):
        """User token gets 403 on all job endpoints."""
        mock_get_principal.return_value = user_principal

        # Create job
        response = client.post("/v1/admin/db/jobs", json={"kind": "migrate"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Get status
        response = client.get("/v1/admin/db/jobs/test-job")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Cancel
        response = client.delete("/v1/admin/db/jobs/test-job")
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestAdminDbCounts:
    """Tests for GET /v1/admin/db/counts"""

    @patch("src.security.jwt.get_current_principal")
    def test_admin_can_get_counts(self, mock_get_principal, client, admin_principal):
        """Admin token can get DB counts."""
        mock_get_principal.return_value = admin_principal

        response = client.get("/v1/admin/db/counts")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["ok"] is True
        assert "nodes" in data

    @patch("src.security.jwt.get_current_principal")
    def test_user_token_forbidden(self, mock_get_principal, client, user_principal):
        """User token gets 403 on counts endpoint."""
        mock_get_principal.return_value = user_principal

        response = client.get("/v1/admin/db/counts")

        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# RBAC Cross-Check: Admin tokens still blocked from /internal/*
# ============================================================================


class TestInternalRoutesStillBlocked:
    """Verify admin tokens still get 403 on /internal/* routes (unchanged behavior)."""

    @patch("src.security.jwt.get_current_principal")
    def test_admin_blocked_from_internal_ops(self, mock_get_principal, client, admin_principal):
        """Admin token gets 403 on internal ops endpoints."""
        mock_get_principal.return_value = admin_principal

        response = client.post("/v1/internal/ops/auto-start-override", json={"enabled": True})

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("src.security.jwt.get_current_principal")
    def test_admin_blocked_from_internal_db(self, mock_get_principal, client, admin_principal):
        """Admin token gets 403 on internal DB endpoints."""
        mock_get_principal.return_value = admin_principal

        # Try to create job
        response = client.post("/v1/internal/db/jobs", json={"kind": "migrate"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Try to get counts
        response = client.get("/v1/internal/db/counts")
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# Storage Parity Tests
# ============================================================================


class TestStorageParity:
    """Verify admin and internal routes use the same storage layer."""

    @patch("src.routers.admin_ops.get_async_redis")
    @patch("src.routers.admin_ops.SessionLocal")
    @patch("src.routers.admin_ops.settings")
    def test_admin_override_uses_same_redis_key(
        self, mock_settings, mock_session_local, mock_get_redis, client, admin_principal, mock_redis, mock_db_session
    ):
        """Admin override writes to same Redis key as internal route."""
        mock_settings.INTERNAL_UI_OVERRIDE_ALLOWED = True
        mock_settings.INTERNAL_UI_OVERRIDE_TTL_SECONDS = 600
        mock_get_redis.return_value = mock_redis
        mock_session_local.return_value = mock_db_session

        with patch("src.security.jwt.get_current_principal", return_value=admin_principal):
            client.post("/v1/admin/ops/auto-start-override", json={"enabled": True})

        # Verify it used the internal: namespace
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "internal:auto_start_override"

    @patch("src.routers.admin_db.get_async_redis")
    def test_admin_job_uses_same_redis_namespace(self, mock_get_redis, client, admin_principal, mock_redis):
        """Admin job creation uses same Redis namespace as internal route."""
        mock_get_redis.return_value = mock_redis

        with patch("src.security.jwt.get_current_principal", return_value=admin_principal):
            client.post("/v1/admin/db/jobs", json={"kind": "vacuum"})

        # Verify it used the internal:db:job: namespace
        call_args = mock_redis.setex.call_args
        assert call_args[0][0].startswith("internal:db:job:")
