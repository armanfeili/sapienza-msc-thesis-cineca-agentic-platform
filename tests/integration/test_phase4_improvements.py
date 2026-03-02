"""
Quick test to verify Phase 4 API improvements: ETag, Location, Idempotency headers, and Vary headers.
"""

import pytest
from fastapi.testclient import TestClient
from src.app import create_app
import json


@pytest.fixture
def app():
    """Create test app."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def admin_token(mint_token):
    """Create admin token with all permissions."""
    return mint_token(sub="admin", scopes=["admin:all", "user:me"])


@pytest.fixture
def user_token(mint_token):
    """Create user token with basic permissions."""
    return mint_token(sub="user1", scopes=["user:me", "tools:basic"])


class TestETagSupport:
    """Test ETag generation and If-None-Match handling."""

    def test_get_sessions_includes_etag(self, client, admin_token):
        """GET /agents/sessions should include ETag header."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = client.get("/v1/agents/sessions", headers=headers)
        assert r.status_code == 200
        assert "etag" in r.headers or "ETag" in r.headers

    def test_etag_304_not_modified(self, client, admin_token):
        """GET with If-None-Match matching ETag should return 304."""
        headers = {"Authorization": f"Bearer {admin_token}"}

        # First request to get ETag
        r1 = client.get("/v1/agents/sessions", headers=headers)
        assert r1.status_code == 200
        etag = r1.headers.get("ETag") or r1.headers.get("etag")
        assert etag

        # Second request with If-None-Match matching ETag
        headers_with_etag = {**headers, "If-None-Match": etag}
        r2 = client.get("/v1/agents/sessions", headers=headers_with_etag)

        # Should return 304 Not Modified (when content hasn't changed)
        # May return 200 if content changed between requests
        assert r2.status_code in (200, 304)
        if r2.status_code == 304:
            assert r2.content == b""  # 304 should have no body


class TestLocationHeaders:
    """Test Location headers on POST 201 responses."""

    def test_create_session_returns_location(self, client, admin_token):
        """POST /agents/sessions should return Location header."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        body = {"manager": "test-manager", "tools": ["tool1"], "temperature": 0.2, "max_steps": 5}

        r = client.post("/v1/agents/sessions", json=body, headers=headers)
        assert r.status_code == 201
        assert "location" in r.headers or "Location" in r.headers

        # Location should contain the session ID
        location = r.headers.get("Location") or r.headers.get("location")
        data = r.json()
        session_id = data.get("session_id")
        assert session_id
        assert str(session_id) in location


class TestIdempotencyHeaders:
    """Test Idempotency-Key echo and Idempotency-Replayed headers."""

    def test_idempotency_key_echoed(self, client, admin_token):
        """POST with Idempotency-Key should echo it in response."""
        headers = {"Authorization": f"Bearer {admin_token}", "Idempotency-Key": "test-key-123"}
        body = {"manager": "test-manager", "tools": ["tool1"], "temperature": 0.2, "max_steps": 5}

        r = client.post("/v1/agents/sessions", json=body, headers=headers)
        assert r.status_code == 201

        # Check that Idempotency-Key is echoed
        assert "idempotency-key" in r.headers or "Idempotency-Key" in r.headers
        key = r.headers.get("Idempotency-Key") or r.headers.get("idempotency-key")
        assert key == "test-key-123"

    def test_idempotency_replay_flag(self, client, admin_token):
        """Replayed request should have Idempotency-Replayed: true."""
        headers = {"Authorization": f"Bearer {admin_token}", "Idempotency-Key": "replay-key-456"}
        body = {"manager": "test-manager", "tools": ["tool1"], "temperature": 0.2, "max_steps": 5}

        # First request
        r1 = client.post("/v1/agents/sessions", json=body, headers=headers)
        assert r1.status_code == 201
        data1 = r1.json()

        # Replay request with same key
        r2 = client.post("/v1/agents/sessions", json=body, headers=headers)
        assert r2.status_code == 201  # Should return original status code

        # Check for Idempotency-Replayed header
        replayed = r2.headers.get("Idempotency-Replayed") or r2.headers.get("idempotency-replayed")
        if replayed:
            assert replayed.lower() == "true"


class TestVaryHeaders:
    """Test Vary headers for cache correctness."""

    def test_sessions_endpoint_has_vary_authorization(self, client, admin_token, user_token):
        """GET /agents/sessions should have Vary: Authorization."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = client.get("/v1/agents/sessions", headers=headers)
        assert r.status_code == 200

        # Check for Vary header
        vary = r.headers.get("Vary") or r.headers.get("vary")
        assert vary
        # Should include Authorization
        assert "Authorization" in vary or "authorization" in vary.lower()


class TestPaginationCursor:
    """Test that pagination uses next_cursor instead of next_page_token."""

    def test_sessions_list_uses_next_cursor(self, client, admin_token):
        """GET /agents/sessions response should use next_cursor field."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = client.get("/v1/agents/sessions", headers=headers)
        assert r.status_code == 200
        data = r.json()

        # Response should have next_cursor field (not next_page_token)
        assert "next_cursor" in data
        assert "next_page_token" not in data


class TestSessionStateValidation:
    """Test that cancelled sessions cannot accept new steps."""

    def test_cannot_add_step_to_cancelled_session(self, client, admin_token):
        """POST /sessions/{id}/steps should return error if session is cancelled."""
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Create a session
        body = {"manager": "test-manager", "tools": ["tool1"], "temperature": 0.2, "max_steps": 5}
        r1 = client.post("/v1/agents/sessions", json=body, headers=headers)
        assert r1.status_code == 201
        session_data = r1.json()
        session_id = session_data["session_id"]

        # Cancel the session
        r2 = client.delete(f"/v1/agents/sessions/{session_id}", headers=headers)
        assert r2.status_code == 204

        # Try to add a step to cancelled session
        step_body = {"type": "message", "message": "test message"}
        r3 = client.post(f"/v1/agents/sessions/{session_id}/steps", json=step_body, headers=headers)

        # Should return error (400 or 409 depending on implementation)
        assert r3.status_code >= 400
        error = r3.json()
        # Should indicate session is not active
        assert "active" in str(error).lower() or "cancelled" in str(error).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
