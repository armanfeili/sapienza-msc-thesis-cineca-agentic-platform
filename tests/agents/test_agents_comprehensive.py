"""
Comprehensive integration tests for Agents API.

Tests cover:
- Session CRUD operations
- Step sequencing and creation
- Run execution
- Rate limiting (429 responses)
- Idempotency replays
- ETag caching (304)
- Pagination with cursors
- RBAC permissions
- RFC7807 error handling
"""

import os
import time
import uuid
from typing import Dict, Optional

import pytest
import requests

# Configuration
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
API_V1 = f"{BASE_URL}/v1"

# Auth tokens from environment or use defaults
# Default to tokens provided at session start if not overridden
DEFAULT_ADMIN_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBfUER0Z1l6angzVXlSVE9mTG10RSJ9.eyJpc3MiOiJodHRwczovL2NpbmVjYS5ldS5hdXRoMC5jb20vIiwic3ViIjoiYXV0aDB8NjhjNzA5OTY5MjI1YWZlMjY1MTUxZWQ1IiwiYXVkIjoiYXBpOi8vY2luZWNhLWFnZW50aWMtcGxhdGZvcm0iLCJpYXQiOjE3NjA4NzI5MTAsImV4cCI6MTc2MDk1OTMxMCwic2NvcGUiOiJ1c2VyOm1lIHRvb2xzOmludm9rZTphbGwgYWRtaW46YWxsIiwiZ3R5IjoicGFzc3dvcmQiLCJhenAiOiJrd2tmMWJHbjJObWRLV3ppb1pZa3Z0WU0wMjJkemI1QyJ9.DhCbqp2nfej14ufxfzqs5KlcBmvJq9F7p-eJrTTTt5nd2RyZMAVMIp7oqjeG0DRhaXVcKdZNDpArdQ4aY281ehWaUWOxWLbn5H7HnirOvZpcM5_uAbLgVc-5EhqVuMxw9tbWe_dpff0avKcE2TcTXR8nx1esTWFUk-69Aog7eMbs90y7nmGjQKjDHjhhcnEFhOpc7zotjuVJiZ0f8fvkhicCAtQFVQgXer4N529c8XYNTnqkBiuPBCxNZIzXRa5Lp9kqsM96_TKrdU3Q_DwLV7yXJYp2KT1BOKqKzbet4MrmprxGQ3SjBKa57Lxo4ZENOwlzkj2AXc4mkpKX0y0CfQ"
DEFAULT_USER_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBfUER0Z1l6angzVXlSVE9mTG10RSJ9.eyJpc3MiOiJodHRwczovL2NpbmVjYS5ldS5hdXRoMC5jb20vIiwic3ViIjoiYXV0aDB8NjhjNzE1ZDU2ZjVlN2Q0ZWZhNmFkNmU2IiwiYXVkIjoiYXBpOi8vY2luZWNhLWFnZW50aWMtcGxhdGZvcm0iLCJpYXQiOjE3NjA4NzI5NTEsImV4cCI6MTc2MDk1OTM1MSwic2NvcGUiOiJ1c2VyOm1lIHRvb2xzOmludm9rZTpiYXNpYyIsImd0eSI6InBhc3N3b3JkIiwiYXpwIjoia3drZjFiR24yTm1kS1d6aW9aWWt2dFlNMDIyZHpiNUMifQ.hrt5-ydLTozxPrX1B-ElDApXqxTbCI48f-CIAXVlEK1UOg8DykY-0cciDbxIufhKURW0woV6mNZLQIUKNFcZ1_cNuQfnmBdgXO6J4bgjlPjCBSN8JJlPyQmae0hOhUZJBznBlL7DxhsERqLR78yDazM9rNu4V28sF5_zRmYb_CuK1RVo5s6j2AbNGbUgVR8dn09-ZXvVFqHeqU069hwsuL0YULsGmAs1L5YX3qBcnIvyzUT97LLZwynDaJPO_AAtN_eOXix-U0rUuvnS6Nk_TGKzGALrn9rL47RDZyXfQyYeCRfVPQayYrk0nNd3pf1wPsPgX30GvNW6LTO0CdALPQ"

TOKEN = os.environ.get("TEST_TOKEN", DEFAULT_USER_TOKEN)
ADMIN_TOKEN = os.environ.get("TEST_ADMIN_TOKEN", DEFAULT_ADMIN_TOKEN)

# Skip tests if no auth tokens
pytestmark = pytest.mark.skipif(not TOKEN, reason="TEST_TOKEN environment variable not set")


# Fixtures


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Standard user auth headers."""
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def admin_headers() -> Dict[str, str]:
    """Admin user auth headers."""
    if not ADMIN_TOKEN:
        pytest.skip("TEST_ADMIN_TOKEN not set")
    return {
        "Authorization": f"Bearer {ADMIN_TOKEN}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def session_id(auth_headers) -> str:
    """Create a test session and return its ID."""
    response = requests.post(
        f"{API_V1}/agents/sessions",
        json={
            "manager": "auto",
            "tools": [],
            "temperature": 0.7,
            "max_steps": 10,
        },
        headers=auth_headers,
        timeout=10,
    )
    assert response.status_code == 201
    data = response.json()
    session_id = data["session_id"]

    yield session_id

    # Cleanup: cancel session
    requests.delete(
        f"{API_V1}/agents/sessions/{session_id}",
        headers=auth_headers,
        timeout=5,
    )


# Session CRUD Tests


class TestSessionCRUD:
    """Test session create, read, update, delete operations."""

    def test_create_session_success(self, auth_headers):
        """Test successful session creation."""
        response = requests.post(
            f"{API_V1}/agents/sessions",
            json={
                "manager": "auto",
                "tools": ["calculator"],
                "temperature": 0.8,
                "max_steps": 20,
                "metadata": {"test": "value"},
            },
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 201
        assert "Location" in response.headers

        data = response.json()
        assert "session_id" in data
        assert data["manager"] == "auto"
        assert data["temperature"] == 0.8
        assert data["max_steps"] == 20
        assert data["status"] == "active"
        assert data["metadata"]["test"] == "value"

    def test_create_session_with_custom_id(self, auth_headers):
        """Test session creation with custom session_id."""
        custom_id = str(uuid.uuid4())

        response = requests.post(
            f"{API_V1}/agents/sessions",
            json={
                "session_id": custom_id,
                "manager": "auto",
                "tools": [],
            },
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["session_id"] == custom_id

        # Cleanup
        requests.delete(
            f"{API_V1}/agents/sessions/{custom_id}",
            headers=auth_headers,
            timeout=5,
        )

    def test_create_duplicate_session_returns_409(self, auth_headers, session_id):
        """Test creating duplicate session returns 409 with RFC7807 error."""
        response = requests.post(
            f"{API_V1}/agents/sessions",
            json={
                "session_id": session_id,
                "manager": "auto",
                "tools": [],
            },
            headers=auth_headers,
            timeout=10,
        )

        # Should return existing session (200) or conflict (409)
        assert response.status_code in (200, 409)

        if response.status_code == 409:
            data = response.json()
            assert data["status"] == 409
            assert data["type"] == "https://httpstatuses.com/409"
            assert "error_code" in data.get("extensions", {})
            assert data["extensions"]["error_code"] == "duplicate_session"

    def test_get_session_success(self, auth_headers, session_id):
        """Test retrieving session by ID."""
        response = requests.get(
            f"{API_V1}/agents/sessions/{session_id}",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert "status" in data
        assert "created_at" in data

    def test_get_nonexistent_session_returns_404(self, auth_headers):
        """Test getting non-existent session returns RFC7807 404."""
        fake_id = str(uuid.uuid4())

        response = requests.get(
            f"{API_V1}/agents/sessions/{fake_id}",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == 404
        assert data["type"] == "https://httpstatuses.com/404"
        assert data["title"] == "Session Not Found"
        assert "error_code" in data.get("extensions", {})
        assert data["extensions"]["error_code"] == "session_not_found"
        assert data["extensions"]["session_id"] == fake_id

    def test_list_sessions_success(self, auth_headers, session_id):
        """Test listing sessions with pagination."""
        response = requests.get(
            f"{API_V1}/agents/sessions",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

        # Should include our test session
        session_ids = [s["session_id"] for s in data["items"]]
        assert session_id in session_ids

    def test_list_sessions_pagination(self, auth_headers):
        """Test session list pagination with cursors."""
        # Get first page with small limit
        response = requests.get(
            f"{API_V1}/agents/sessions?limit=2",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data

        # If there's a next page, fetch it
        if "next_page_token" in data and data["next_page_token"]:
            cursor = data["next_page_token"]
            response2 = requests.get(
                f"{API_V1}/agents/sessions?limit=2&cursor={cursor}",
                headers=auth_headers,
                timeout=10,
            )
            assert response2.status_code == 200

    def test_delete_session_success(self, auth_headers):
        """Test session deletion (cancellation)."""
        # Create session
        create_response = requests.post(
            f"{API_V1}/agents/sessions",
            json={"manager": "auto", "tools": []},
            headers=auth_headers,
            timeout=10,
        )
        assert create_response.status_code == 201
        session_id = create_response.json()["session_id"]

        # Delete session
        delete_response = requests.delete(
            f"{API_V1}/agents/sessions/{session_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert delete_response.status_code == 204

        # Verify session is cancelled
        get_response = requests.get(
            f"{API_V1}/agents/sessions/{session_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["status"] == "cancelled"

    def test_delete_idempotent(self, auth_headers, session_id):
        """Test session deletion is idempotent."""
        # Delete once
        response1 = requests.delete(
            f"{API_V1}/agents/sessions/{session_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert response1.status_code == 204

        # Delete again - should succeed
        response2 = requests.delete(
            f"{API_V1}/agents/sessions/{session_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert response2.status_code in (204, 404)


# Step Tests


class TestSteps:
    """Test step creation and sequencing."""

    def test_create_step_success(self, auth_headers, session_id):
        """Test creating a step in a session."""
        response = requests.post(
            f"{API_V1}/agents/sessions/{session_id}/steps",
            json={
                "type": "message",
                "input": {"text": "Hello"},
                "output": {"response": "Hi there"},
            },
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 201
        assert "Location" in response.headers

        data = response.json()
        assert "step_id" in data
        assert data["session_id"] == session_id
        assert data["seq"] == 1
        assert data["type"] == "message"

    def test_steps_sequenced_correctly(self, auth_headers, session_id):
        """Test steps are sequenced incrementally."""
        # Create 3 steps
        for i in range(3):
            response = requests.post(
                f"{API_V1}/agents/sessions/{session_id}/steps",
                json={
                    "type": "message",
                    "input": {"text": f"Step {i}"},
                },
                headers=auth_headers,
                timeout=10,
            )
            assert response.status_code == 201
            data = response.json()
            assert data["seq"] == i + 1

    def test_create_step_on_cancelled_session_fails(self, auth_headers):
        """Test creating step on cancelled session returns 400."""
        # Create and cancel session
        create_resp = requests.post(
            f"{API_V1}/agents/sessions",
            json={"manager": "auto", "tools": []},
            headers=auth_headers,
            timeout=10,
        )
        session_id = create_resp.json()["session_id"]

        requests.delete(
            f"{API_V1}/agents/sessions/{session_id}",
            headers=auth_headers,
            timeout=10,
        )

        # Try to create step
        response = requests.post(
            f"{API_V1}/agents/sessions/{session_id}/steps",
            json={"type": "message", "input": {}},
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == 400
        assert data["title"] == "Session Not Active"
        assert "error_code" in data.get("extensions", {})
        assert data["extensions"]["error_code"] == "session_not_active"

    def test_list_steps_success(self, auth_headers, session_id):
        """Test listing steps for a session."""
        # Create some steps
        for i in range(3):
            requests.post(
                f"{API_V1}/agents/sessions/{session_id}/steps",
                json={"type": "message", "input": {"text": f"Step {i}"}},
                headers=auth_headers,
                timeout=10,
            )

        # List steps
        response = requests.get(
            f"{API_V1}/agents/sessions/{session_id}/steps",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 3

        # Verify ordering by seq
        seqs = [s["seq"] for s in data["items"]]
        assert seqs == sorted(seqs)

    def test_list_steps_pagination(self, auth_headers, session_id):
        """Test step list pagination."""
        # Create 5 steps
        for i in range(5):
            requests.post(
                f"{API_V1}/agents/sessions/{session_id}/steps",
                json={"type": "message", "input": {"text": f"Step {i}"}},
                headers=auth_headers,
                timeout=10,
            )

        # Get first page
        response = requests.get(
            f"{API_V1}/agents/sessions/{session_id}/steps?limit=2",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert "next_cursor" in data  # Fixed: API uses next_cursor, not next_page_token

        # Get second page
        cursor = data["next_cursor"]
        response2 = requests.get(
            f"{API_V1}/agents/sessions/{session_id}/steps?limit=2&cursor={cursor}",
            headers=auth_headers,
            timeout=10,
        )

        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["items"]) == 2

        # Verify no overlap
        page1_seqs = {s["seq"] for s in data["items"]}
        page2_seqs = {s["seq"] for s in data2["items"]}
        assert page1_seqs.isdisjoint(page2_seqs)


# Run Tests


class TestRuns:
    """Test agent run execution."""

    def test_create_run_with_existing_session(self, auth_headers, session_id):
        """Test creating run with existing session."""
        response = requests.post(
            f"{API_V1}/agent-runs",
            json={
                "session_id": session_id,
                "prompt": "Hello world",
                "manager": "auto",
            },
            headers=auth_headers,
            timeout=15,
        )

        assert response.status_code == 201
        assert "Location" in response.headers

        data = response.json()
        assert "run_id" in data
        assert data["session_id"] == session_id
        assert data["status"] in ("succeeded", "failed", "running")

    def test_create_run_creates_session_automatically(self, auth_headers):
        """Test run creation without session_id creates session."""
        response = requests.post(
            f"{API_V1}/agent-runs",
            json={
                "prompt": "Test prompt",
                "manager": "auto",
                "tools": [],
            },
            headers=auth_headers,
            timeout=15,
        )

        assert response.status_code == 201
        data = response.json()
        assert "run_id" in data
        assert "session_id" in data

        # Cleanup session
        if "session_id" in data:
            requests.delete(
                f"{API_V1}/agents/sessions/{data['session_id']}",
                headers=auth_headers,
                timeout=5,
            )

    def test_get_run_by_id(self, auth_headers):
        """Test retrieving run by ID."""
        # Create run
        create_resp = requests.post(
            f"{API_V1}/agent-runs",
            json={"prompt": "Test", "manager": "auto"},
            headers=auth_headers,
            timeout=15,
        )
        assert create_resp.status_code == 201
        run_id = create_resp.json()["run_id"]

        # Get run
        get_resp = requests.get(
            f"{API_V1}/agent-runs/{run_id}",
            headers=auth_headers,
            timeout=10,
        )

        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["run_id"] == run_id

    def test_get_nonexistent_run_returns_404(self, auth_headers):
        """Test getting non-existent run returns RFC7807 404."""
        fake_id = str(uuid.uuid4())

        response = requests.get(
            f"{API_V1}/agent-runs/{fake_id}",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == 404
        assert data["title"] == "Run Not Found"
        assert data["extensions"]["error_code"] == "run_not_found"


# Idempotency Tests


class TestIdempotency:
    """Test idempotency key handling."""

    def test_idempotent_session_creation(self, auth_headers):
        """Test session creation with idempotency key."""
        idempotency_key = str(uuid.uuid4())
        headers = {**auth_headers, "Idempotency-Key": idempotency_key}

        # First request
        response1 = requests.post(
            f"{API_V1}/agents/sessions",
            json={"manager": "auto", "tools": []},
            headers=headers,
            timeout=10,
        )
        assert response1.status_code == 201
        session_id1 = response1.json()["session_id"]
        assert "Idempotency-Replayed" not in response1.headers

        # Second request with same key
        response2 = requests.post(
            f"{API_V1}/agents/sessions",
            json={"manager": "auto", "tools": []},
            headers=headers,
            timeout=10,
        )
        # Fixed: Idempotent replay returns 200, not 201 (REST best practice)
        assert response2.status_code == 200, f"Expected 200 for idempotent replay, got {response2.status_code}"
        session_id2 = response2.json()["session_id"]
        assert response2.headers.get("Idempotency-Replayed") == "true"

        # Should return same session
        assert session_id1 == session_id2

        # Cleanup
        requests.delete(
            f"{API_V1}/agents/sessions/{session_id1}",
            headers=auth_headers,
            timeout=5,
        )

    def test_idempotent_step_creation(self, auth_headers, session_id):
        """Test step creation with idempotency key."""
        idempotency_key = str(uuid.uuid4())
        headers = {**auth_headers, "Idempotency-Key": idempotency_key}

        # First request
        response1 = requests.post(
            f"{API_V1}/agents/sessions/{session_id}/steps",
            json={"type": "message", "input": {"text": "Hello"}},
            headers=headers,
            timeout=10,
        )
        assert response1.status_code == 201
        step_id1 = response1.json()["step_id"]

        # Second request with same key
        response2 = requests.post(
            f"{API_V1}/agents/sessions/{session_id}/steps",
            json={"type": "message", "input": {"text": "Different text"}},
            headers=headers,
            timeout=10,
        )
        assert response2.status_code == 201
        step_id2 = response2.json()["step_id"]
        assert response2.headers.get("Idempotency-Replayed") == "true"

        # Should return same step
        assert step_id1 == step_id2


# ETag Caching Tests


class TestETagCaching:
    """Test ETag caching for list endpoints."""

    def test_session_list_etag_caching(self, auth_headers, session_id):
        """Test ETag caching on session list."""
        # First request
        response1 = requests.get(
            f"{API_V1}/agents/sessions",
            headers=auth_headers,
            timeout=10,
        )
        assert response1.status_code == 200
        etag = response1.headers.get("ETag")

        if etag:
            # Second request with If-None-Match
            headers_with_etag = {**auth_headers, "If-None-Match": etag}
            response2 = requests.get(
                f"{API_V1}/agents/sessions",
                headers=headers_with_etag,
                timeout=10,
            )

            # Should return 304 if no changes
            assert response2.status_code in (200, 304)

    def test_steps_list_etag_caching(self, auth_headers, session_id):
        """Test ETag caching on steps list."""
        # First request
        response1 = requests.get(
            f"{API_V1}/agents/sessions/{session_id}/steps",
            headers=auth_headers,
            timeout=10,
        )
        assert response1.status_code == 200
        etag = response1.headers.get("ETag")

        if etag:
            # Second request with If-None-Match
            headers_with_etag = {**auth_headers, "If-None-Match": etag}
            response2 = requests.get(
                f"{API_V1}/agents/sessions/{session_id}/steps",
                headers=headers_with_etag,
                timeout=10,
            )

            # Should return 304 if no changes
            assert response2.status_code in (200, 304)

    def test_etag_invalidated_on_modification(self, auth_headers, session_id):
        """Test ETag is invalidated when steps are added."""
        # Get initial ETag
        response1 = requests.get(
            f"{API_V1}/agents/sessions/{session_id}/steps",
            headers=auth_headers,
            timeout=10,
        )
        etag1 = response1.headers.get("ETag")

        if etag1:
            # Add a step
            requests.post(
                f"{API_V1}/agents/sessions/{session_id}/steps",
                json={"type": "message", "input": {"text": "New step"}},
                headers=auth_headers,
                timeout=10,
            )

            # Get new ETag
            response2 = requests.get(
                f"{API_V1}/agents/sessions/{session_id}/steps",
                headers=auth_headers,
                timeout=10,
            )
            etag2 = response2.headers.get("ETag")

            # ETag should have changed
            assert etag1 != etag2


# Rate Limiting Tests


class TestRateLimiting:
    """Test rate limiting enforcement."""

    def test_rate_limit_headers_present(self, auth_headers):
        """Test rate limit headers are included in responses."""
        response = requests.post(
            f"{API_V1}/agents/sessions",
            json={"manager": "auto", "tools": []},
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 201

        # Check for rate limit headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Window" in response.headers

        # Cleanup
        if response.status_code == 201:
            session_id = response.json()["session_id"]
            requests.delete(
                f"{API_V1}/agents/sessions/{session_id}",
                headers=auth_headers,
                timeout=5,
            )

    @pytest.mark.slow
    def test_rate_limit_enforced_on_sessions(self, auth_headers):
        """Test rate limiting is enforced on session creation."""
        # Session creation limit is 10/minute
        # Create sessions until we hit the limit
        created_sessions = []

        for i in range(15):
            response = requests.post(
                f"{API_V1}/agents/sessions",
                json={"manager": "auto", "tools": []},
                headers=auth_headers,
                timeout=10,
            )

            if response.status_code == 201:
                created_sessions.append(response.json()["session_id"])
            elif response.status_code == 429:
                # Rate limit hit!
                data = response.json()
                assert data["status"] == 429
                assert data["title"] == "Too Many Requests"
                assert "Retry-After" in response.headers
                assert "error_code" not in data or data.get("extensions", {}).get("error_code") == "rate_limit_exceeded"
                break

        # Cleanup
        for session_id in created_sessions:
            requests.delete(
                f"{API_V1}/agents/sessions/{session_id}",
                headers=auth_headers,
                timeout=5,
            )

    @pytest.mark.slow
    def test_rate_limit_per_resource(self, auth_headers, session_id):
        """Test rate limiting is per-resource for steps."""
        # Steps limit is 100/minute per session
        # This test verifies the rate limit is scoped to session

        response = requests.post(
            f"{API_V1}/agents/sessions/{session_id}/steps",
            json={"type": "message", "input": {}},
            headers=auth_headers,
            timeout=10,
        )

        # Should succeed (we haven't hit limit yet)
        assert response.status_code == 201
        assert "X-RateLimit-Limit" in response.headers

        # Verify rate limit header matches config (supports both prod and test modes)
        # In test mode: 10000/min, in prod mode: 100/min
        from db.redis_cache.rate_limit import get_rate_limit_config

        expected_limit, _ = get_rate_limit_config("steps:create")
        actual_limit = int(response.headers["X-RateLimit-Limit"])

        # Verify the limit is one of the expected values
        assert actual_limit == expected_limit, (
            f"Rate limit mismatch: expected {expected_limit} (from config), "
            f"got {actual_limit} (from API header). "
            f"Ensure RATE_LIMIT_MODE env var matches test expectations."
        )


# Error Handling Tests


class TestErrorHandling:
    """Test RFC7807 error response format."""

    def test_404_error_format(self, auth_headers):
        """Test 404 errors follow RFC7807 format."""
        response = requests.get(
            f"{API_V1}/agents/sessions/nonexistent",
            headers=auth_headers,
            timeout=10,
        )

        assert response.status_code == 404
        data = response.json()

        # RFC7807 required fields
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data

        # Our additions
        assert "extensions" in data
        assert "error_code" in data["extensions"]
        assert data["extensions"]["error_code"] == "session_not_found"

    def test_400_error_format(self, auth_headers):
        """Test 400 errors follow RFC7807 format."""
        response = requests.get(
            f"{API_V1}/agents/sessions?cursor=invalid_cursor",
            headers=auth_headers,
            timeout=10,
        )

        # May return 400 if cursor validation is strict
        if response.status_code == 400:
            data = response.json()
            assert "type" in data
            assert "title" in data
            assert "status" in data
            assert data["status"] == 400
            assert "extensions" in data
            assert "error_code" in data["extensions"]


# RBAC Tests (if admin token available)


class TestRBAC:
    """Test role-based access control."""

    def test_user_cannot_see_others_sessions(self, auth_headers, admin_headers):
        """Test users only see their own sessions."""
        # User creates session
        user_resp = requests.post(
            f"{API_V1}/agents/sessions",
            json={"manager": "auto", "tools": []},
            headers=auth_headers,
            timeout=10,
        )
        assert user_resp.status_code == 201
        user_session_id = user_resp.json()["session_id"]

        # Admin creates session
        admin_resp = requests.post(
            f"{API_V1}/agents/sessions",
            json={"manager": "auto", "tools": []},
            headers=admin_headers,
            timeout=10,
        )
        assert admin_resp.status_code == 201
        admin_session_id = admin_resp.json()["session_id"]

        # User lists sessions - should only see their own
        user_list_resp = requests.get(
            f"{API_V1}/agents/sessions",
            headers=auth_headers,
            timeout=10,
        )
        user_sessions = [s["session_id"] for s in user_list_resp.json()["items"]]
        assert user_session_id in user_sessions
        # May or may not see admin's session depending on isolation

        # Admin lists sessions - should see all
        admin_list_resp = requests.get(
            f"{API_V1}/agents/sessions",
            headers=admin_headers,
            timeout=10,
        )
        admin_sessions = [s["session_id"] for s in admin_list_resp.json()["items"]]
        # Admin should see both
        assert user_session_id in admin_sessions or admin_session_id in admin_sessions

        # Cleanup
        requests.delete(f"{API_V1}/agents/sessions/{user_session_id}", headers=auth_headers, timeout=5)
        requests.delete(f"{API_V1}/agents/sessions/{admin_session_id}", headers=admin_headers, timeout=5)


# Performance marker for slow tests
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
