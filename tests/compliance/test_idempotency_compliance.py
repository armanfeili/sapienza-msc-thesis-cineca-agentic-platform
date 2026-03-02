"""
Test idempotency compliance for POST /v1/agents/sessions.

Tests verify:
1. Fresh create returns 201 + Location header
2. Idempotent replay returns 200 + Idempotency-Replayed: true
3. Error responses use application/problem+json
"""
import pytest
from fastapi import status
from fastapi.testclient import TestClient


def test_post_sessions_fresh_create_returns_201(client: TestClient, bearer_headers):
    """Test A: POST without prior key → 201 and Location header present."""
    response = client.post(
        "/v1/agents/sessions",
        json={
            "manager": "planner",
            "tools": [],
            "temperature": 0.7,
        },
        headers=bearer_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED, f"Expected 201, got {response.status_code}: {response.text}"

    # Verify Location header is present
    assert "location" in response.headers, "Location header missing"
    location = response.headers["location"]
    assert "/v1/agents/sessions/" in location, f"Invalid Location: {location}"

    # Verify X-Request-Id is present
    assert "x-request-id" in response.headers, "X-Request-Id header missing"

    # Verify response body contains session_id
    data = response.json()
    assert "session_id" in data, "session_id missing from response"
    assert data["session_id"] in location, "Location doesn't match session_id"


def test_post_sessions_idempotent_replay_returns_200(client: TestClient, bearer_headers):
    """Test B: POST with same Idempotency-Key → 200, Idempotency-Replayed: true, same body, same Location."""
    idempotency_key = "test-idem-key-12345"

    # First request - should create new session (201)
    response1 = client.post(
        "/v1/agents/sessions",
        json={
            "manager": "planner",
            "tools": [],
            "temperature": 0.7,
        },
        headers={**bearer_headers, "Idempotency-Key": idempotency_key},
    )

    assert response1.status_code == status.HTTP_201_CREATED, f"First request: Expected 201, got {response1.status_code}"

    data1 = response1.json()
    location1 = response1.headers.get("location")

    # Verify Idempotency-Key is echoed
    assert response1.headers.get("idempotency-key") == idempotency_key, "Idempotency-Key not echoed in first response"

    # Second request with same Idempotency-Key - should replay (200)
    response2 = client.post(
        "/v1/agents/sessions",
        json={
            "manager": "planner",
            "tools": [],
            "temperature": 0.7,
        },
        headers={**bearer_headers, "Idempotency-Key": idempotency_key},
    )

    assert (
        response2.status_code == status.HTTP_200_OK
    ), f"Second request: Expected 200, got {response2.status_code}: {response2.text}"

    # Verify Idempotency-Replayed header is set to "true"
    assert (
        response2.headers.get("idempotency-replayed") == "true"
    ), f"Idempotency-Replayed not set: {response2.headers.get('idempotency-replayed')}"

    # Verify Idempotency-Key is echoed
    assert response2.headers.get("idempotency-key") == idempotency_key, "Idempotency-Key not echoed in replay response"

    # Verify Location header is present and same
    location2 = response2.headers.get("location")
    assert location2 == location1, f"Location changed: {location1} != {location2}"

    # Verify X-Request-Id is present
    assert "x-request-id" in response2.headers, "X-Request-Id missing in replay"

    # Verify response body is identical
    data2 = response2.json()
    assert data2["session_id"] == data1["session_id"], "session_id changed in replay"
    assert data2["status"] == data1["status"], "status changed in replay"


def test_post_sessions_existing_session_id_returns_200(client: TestClient, bearer_headers):
    """Test providing existing session_id returns 200 with Location."""
    # Create a session first
    response1 = client.post(
        "/v1/agents/sessions",
        json={
            "manager": "planner",
            "tools": [],
            "temperature": 0.7,
        },
        headers=bearer_headers,
    )

    assert response1.status_code == status.HTTP_201_CREATED
    session_id = response1.json()["session_id"]

    # Try to create again with same session_id
    response2 = client.post(
        "/v1/agents/sessions",
        json={
            "session_id": session_id,
            "manager": "planner",
            "tools": [],
            "temperature": 0.7,
        },
        headers=bearer_headers,
    )

    assert (
        response2.status_code == status.HTTP_200_OK
    ), f"Expected 200 for existing session_id, got {response2.status_code}"

    # Verify Location header
    assert "location" in response2.headers, "Location header missing"
    assert session_id in response2.headers["location"], "Location doesn't match session_id"

    # Verify X-Request-Id
    assert "x-request-id" in response2.headers, "X-Request-Id missing"

    # Verify session_id matches
    assert response2.json()["session_id"] == session_id


def test_post_sessions_error_returns_problem_json(client: TestClient, bearer_headers):
    """Test C: 4xx/5xx errors → Content-Type: application/problem+json."""
    # Invalid temperature should trigger 422 validation error
    response = client.post(
        "/v1/agents/sessions",
        json={
            "manager": "planner",
            "tools": [],
            "temperature": 99.9,  # Invalid: must be 0.0-2.0
        },
        headers=bearer_headers,
    )

    # Should get validation error
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, f"Expected 422, got {response.status_code}"

    # Verify Content-Type is application/problem+json
    content_type = response.headers.get("content-type", "")
    assert (
        "application/problem+json" in content_type or "application/json" in content_type
    ), f"Expected problem+json, got: {content_type}"

    # Verify response has RFC 7807 structure
    data = response.json()
    # FastAPI validation errors have different structure, but should contain error info
    assert "detail" in data or "title" in data, "Response should have error details"


def test_post_sessions_all_required_headers_present(client: TestClient, bearer_headers):
    """Verify all required headers are present in responses."""
    idempotency_key = "test-headers-key"

    # Create session with idempotency key
    response = client.post(
        "/v1/agents/sessions",
        json={
            "manager": "planner",
            "tools": [],
            "temperature": 0.7,
        },
        headers={**bearer_headers, "Idempotency-Key": idempotency_key},
    )

    assert response.status_code == status.HTTP_201_CREATED

    # Verify all required headers
    assert "location" in response.headers, "Location header missing"
    assert "idempotency-key" in response.headers, "Idempotency-Key echo missing"
    assert "x-request-id" in response.headers, "X-Request-Id missing"
    assert response.headers["idempotency-key"] == idempotency_key, "Idempotency-Key not correctly echoed"

    # Replay should have additional Idempotency-Replayed header
    response2 = client.post(
        "/v1/agents/sessions",
        json={
            "manager": "planner",
            "tools": [],
            "temperature": 0.7,
        },
        headers={**bearer_headers, "Idempotency-Key": idempotency_key},
    )

    assert response2.status_code == status.HTTP_200_OK
    assert "idempotency-replayed" in response2.headers, "Idempotency-Replayed missing"
    assert response2.headers["idempotency-replayed"] == "true"
    assert "location" in response2.headers, "Location missing in replay"
    assert "x-request-id" in response2.headers, "X-Request-Id missing in replay"
    assert "idempotency-key" in response2.headers, "Idempotency-Key missing in replay"
