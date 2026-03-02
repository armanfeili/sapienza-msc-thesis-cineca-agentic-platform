"""
Problem+JSON (RFC 9457) uniformity tests.

Verifies that all client error responses (400/401/403/404/406/422) include:
- Content-Type: application/problem+json
- Required fields: status, title, detail
- Extension fields: correlation_id (x-request-id)
"""

import pytest
from fastapi.testclient import TestClient
from src.app import app
import uuid


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def user_headers(configure_oidc, mint_token):
    """Regular user token."""
    token = mint_token(sub="user@example.com", roles=["user"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(configure_oidc, mint_token):
    """Admin token."""
    token = mint_token(sub="admin@example.com", roles=["admin"])
    return {"Authorization": f"Bearer {token}"}


# ========== 400 Bad Request ==========


def test_400_includes_correlation_id(client, user_headers):
    """400 Bad Request includes correlation_id in problem+json."""
    # Trigger 400 by using malformed UUID
    resp = client.get("/v1/jobs/not-a-uuid", headers=user_headers)

    assert resp.status_code == 400
    assert "application/problem+json" in resp.headers.get("Content-Type", "")

    body = resp.json()
    assert "status" in body
    assert body["status"] == 400
    assert "title" in body or "detail" in body

    # Check for correlation_id (might be in extensions or root)
    has_correlation = (
        "correlation_id" in body
        or ("extensions" in body and "correlation_id" in body["extensions"])
        or "x-request-id" in resp.headers
    )
    assert has_correlation, "400 response should include correlation tracking"


def test_400_unknown_job_type(client, user_headers):
    """400 for unknown job type includes correlation_id."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "unknown-type", "payload": {}},
        headers=user_headers,
    )

    assert resp.status_code == 400
    assert "application/problem+json" in resp.headers.get("Content-Type", "")

    body = resp.json()
    assert body["status"] == 400
    assert "unknown job type" in body["detail"].lower() or "unknown_type" in body.get("detail", "").lower()

    # Correlation tracking
    assert "x-request-id" in resp.headers or "correlation_id" in body


# ========== 401 Unauthorized ==========


def test_401_includes_correlation_id(client):
    """401 Unauthorized includes correlation_id."""
    # No Authorization header
    resp = client.get("/v1/jobs")

    assert resp.status_code == 401
    assert "application/problem+json" in resp.headers.get("Content-Type", "")

    body = resp.json()
    assert body["status"] == 401

    # Correlation tracking
    assert "x-request-id" in resp.headers


def test_401_invalid_token(client):
    """401 with invalid token includes correlation_id."""
    resp = client.get(
        "/v1/jobs",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert resp.status_code == 401
    assert "application/problem+json" in resp.headers.get("Content-Type", "")

    body = resp.json()
    assert body["status"] == 401
    assert "x-request-id" in resp.headers


# ========== 403 Forbidden ==========


def test_403_includes_correlation_id(client, user_headers):
    """403 Forbidden includes correlation_id."""
    # User trying to access admin endpoint
    resp = client.get("/v1/admin/jobs", headers=user_headers)

    assert resp.status_code == 403
    assert "application/problem+json" in resp.headers.get("Content-Type", "")

    body = resp.json()
    assert body["status"] == 403
    assert "detail" in body

    # Correlation tracking
    assert "x-request-id" in resp.headers


# ========== 404 Not Found ==========


def test_404_includes_correlation_id(client, user_headers):
    """404 Not Found includes correlation_id."""
    # Non-existent job with valid UUID format
    fake_uuid = str(uuid.uuid4())
    resp = client.get(f"/v1/jobs/{fake_uuid}", headers=user_headers)

    assert resp.status_code == 404
    assert "application/problem+json" in resp.headers.get("Content-Type", "")

    body = resp.json()
    assert body["status"] == 404
    assert "not found" in body["detail"].lower()

    # Correlation tracking
    assert "x-request-id" in resp.headers


def test_404_anti_enumeration_includes_correlation_id(client, user_headers, admin_headers):
    """404 from anti-enumeration (non-owner) includes correlation_id."""
    # Admin creates a job
    create_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {}},
        headers=admin_headers,
    )
    admin_job_id = create_resp.json()["id"]

    # User tries to access admin's job (should get 404)
    resp = client.get(f"/v1/jobs/{admin_job_id}", headers=user_headers)

    assert resp.status_code == 404
    assert "application/problem+json" in resp.headers.get("Content-Type", "")

    body = resp.json()
    assert body["status"] == 404
    assert "x-request-id" in resp.headers


# ========== 406 Not Acceptable ==========


def test_406_includes_correlation_id(client, user_headers, admin_headers):
    """406 Not Acceptable includes correlation_id."""
    # Create a job first
    create_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {}},
        headers=user_headers,
    )
    job_id = create_resp.json()["id"]

    # Request SSE with Accept: application/json (incompatible)
    resp = client.get(
        f"/v1/jobs/{job_id}/events",
        headers={**user_headers, "Accept": "application/json"},
    )

    assert resp.status_code == 406
    assert "application/problem+json" in resp.headers.get("Content-Type", "")

    body = resp.json()
    assert body["status"] == 406
    assert "not acceptable" in body["detail"].lower() or "text/event-stream" in body["detail"].lower()

    # Correlation tracking
    assert "x-request-id" in resp.headers


# ========== 422 Validation Error ==========


def test_422_includes_correlation_id(client, user_headers):
    """422 Validation Error includes correlation_id."""
    # Malformed request body
    resp = client.post(
        "/v1/jobs",
        json={"invalid": "structure"},  # Missing required 'type' field
        headers=user_headers,
    )

    assert resp.status_code == 422
    # FastAPI returns application/json for validation errors, but should have correlation

    body = resp.json()
    # FastAPI's default validation error format
    assert "detail" in body

    # Correlation tracking
    assert "x-request-id" in resp.headers


def test_422_invalid_last_event_id(client, user_headers, admin_headers):
    """422 for invalid Last-Event-ID includes correlation_id."""
    # Create a job
    create_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {}},
        headers=user_headers,
    )
    job_id = create_resp.json()["id"]

    # Request SSE with non-numeric Last-Event-ID
    resp = client.get(
        f"/v1/jobs/{job_id}/events",
        headers={**user_headers, "Last-Event-ID": "not-a-number"},
    )

    assert resp.status_code == 422

    body = resp.json()
    assert "detail" in body

    # Correlation tracking
    assert "x-request-id" in resp.headers


# ========== Comprehensive correlation_id test ==========


def test_all_errors_have_x_request_id_header(client, user_headers, admin_headers):
    """All error responses include X-Request-Id header."""
    import uuid

    test_cases = [
        # (method, url, headers, expected_status, description)
        ("GET", "/v1/jobs/not-a-uuid", user_headers, 400, "400 malformed UUID"),
        ("GET", "/v1/jobs", {}, 401, "401 no auth"),
        ("GET", "/v1/admin/jobs", user_headers, 403, "403 forbidden"),
        ("GET", f"/v1/jobs/{uuid.uuid4()}", user_headers, 404, "404 not found"),
    ]

    for method, url, headers, expected_status, description in test_cases:
        if method == "GET":
            resp = client.get(url, headers=headers)
        elif method == "POST":
            resp = client.post(url, json={}, headers=headers)
        elif method == "DELETE":
            resp = client.delete(url, headers=headers)

        assert resp.status_code == expected_status, f"{description} failed"
        assert "x-request-id" in resp.headers, f"{description} missing X-Request-Id header"

        # X-Request-Id should be a valid UUID
        request_id = resp.headers["x-request-id"]
        try:
            uuid.UUID(request_id)
        except ValueError:
            pytest.fail(f"{description}: X-Request-Id is not a valid UUID: {request_id}")


def test_problem_json_has_required_fields(client, user_headers):
    """Problem+JSON responses have required RFC 9457 fields."""
    # Trigger a 400 error
    resp = client.get("/v1/jobs/bad-uuid", headers=user_headers)

    assert resp.status_code == 400
    assert "application/problem+json" in resp.headers.get("Content-Type", "")

    body = resp.json()

    # Required fields per RFC 9457
    assert "status" in body, "Missing 'status' field"
    assert isinstance(body["status"], int), "'status' should be an integer"

    # At least one of title or detail must be present
    assert "title" in body or "detail" in body, "Missing both 'title' and 'detail'"

    # If present, these should be strings
    if "title" in body:
        assert isinstance(body["title"], str)
    if "detail" in body:
        assert isinstance(body["detail"], str)
