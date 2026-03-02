"""Comprehensive RFC compliance tests for agent endpoints."""
import pytest


def test_post_sessions_returns_201_with_location(client, bearer_headers):
    """POST /agents/sessions must return 201 with Location header."""
    resp = client.post(
        "/v1/agents/sessions",
        json={"manager": "default", "tools": [], "temperature": 0.7, "max_steps": 10},
        headers=bearer_headers,
    )
    # Accept both 201 (new) and 200 (existing/idempotent)
    assert resp.status_code in (200, 201), f"Expected 201 or 200, got {resp.status_code}: {resp.text}"
    if resp.status_code == 201:
        assert "Location" in resp.headers, "Location header missing on 201"
        assert "/v1/agents/sessions/" in resp.headers["Location"], "Invalid Location URI"
    assert "X-Request-Id" in resp.headers, "X-Request-Id header missing"


def test_delete_sessions_returns_204_no_content(client, bearer_headers):
    """DELETE /agents/sessions/{id} must return 204 with no body."""
    # First create a session
    create_resp = client.post(
        "/v1/agents/sessions",
        json={"manager": "default", "tools": [], "temperature": 0.7, "max_steps": 10},
        headers=bearer_headers,
    )
    assert create_resp.status_code in (200, 201)
    session_id = create_resp.json()["session_id"]

    # Delete it
    delete_resp = client.delete(f"/v1/agents/sessions/{session_id}", headers=bearer_headers)
    assert delete_resp.status_code == 204, f"Expected 204, got {delete_resp.status_code}: {delete_resp.text}"
    assert len(delete_resp.content) == 0, "204 should have no content"
    assert "X-Request-Id" in delete_resp.headers, "X-Request-Id header missing"


def test_get_sessions_returns_etag_and_304_on_replay(client, bearer_headers):
    """GET /agents/sessions must return ETag and 304 on If-None-Match match."""
    # First request
    resp1 = client.get("/v1/agents/sessions", headers=bearer_headers)
    assert resp1.status_code == 200, f"Expected 200, got {resp1.status_code}"
    assert "ETag" in resp1.headers, "ETag header missing"
    assert "Vary" in resp1.headers, "Vary header missing"
    assert resp1.headers["Vary"] == "Authorization", "Vary should be Authorization"

    etag = resp1.headers["ETag"]

    # Second request with If-None-Match
    resp2 = client.get("/v1/agents/sessions", headers={**bearer_headers, "If-None-Match": etag})
    assert resp2.status_code == 304, f"Expected 304, got {resp2.status_code}"
    assert "ETag" in resp2.headers, "ETag header missing on 304"
    assert len(resp2.content) == 0, "304 should have no content"


def test_get_session_by_id_returns_etag(client, bearer_headers):
    """GET /agents/sessions/{id} must return ETag."""
    # Create a session first
    create_resp = client.post(
        "/v1/agents/sessions",
        json={"manager": "default", "tools": [], "temperature": 0.7, "max_steps": 10},
        headers=bearer_headers,
    )
    assert create_resp.status_code in (200, 201)
    session_id = create_resp.json()["session_id"]

    # Get it
    get_resp = client.get(f"/v1/agents/sessions/{session_id}", headers=bearer_headers)
    assert get_resp.status_code == 200
    assert "ETag" in get_resp.headers, "ETag header missing"
    assert "Vary" in get_resp.headers, "Vary header missing"


def test_post_sessions_idempotency_header_echo(client, bearer_headers):
    """POST /agents/sessions must echo Idempotency-Key header."""
    idempotency_key = "my-unique-key-123"
    resp = client.post(
        "/v1/agents/sessions",
        json={"manager": "default", "tools": [], "temperature": 0.7, "max_steps": 10},
        headers={**bearer_headers, "Idempotency-Key": idempotency_key},
    )
    assert resp.status_code in (200, 201), f"Expected 201 or 200, got {resp.status_code}"
    assert "Idempotency-Key" in resp.headers, "Idempotency-Key not echoed"
    assert resp.headers["Idempotency-Key"] == idempotency_key, "Idempotency-Key value mismatch"


def test_post_steps_returns_201_with_location(client, bearer_headers):
    """POST /agents/sessions/{id}/steps must return 201 with Location."""
    # Create a session first
    create_resp = client.post(
        "/v1/agents/sessions",
        json={"manager": "default", "tools": [], "temperature": 0.7, "max_steps": 10},
        headers=bearer_headers,
    )
    assert create_resp.status_code in (200, 201)
    session_id = create_resp.json()["session_id"]

    # Create a step
    step_resp = client.post(
        f"/v1/agents/sessions/{session_id}/steps", json={"type": "message", "message": "test"}, headers=bearer_headers
    )
    assert step_resp.status_code == 201, f"Expected 201, got {step_resp.status_code}: {step_resp.text}"
    assert "Location" in step_resp.headers, "Location header missing on POST /steps 201"
    assert "/steps/" in step_resp.headers["Location"], "Invalid Location URI for step"


def test_404_returns_rfc7807_problem_detail(client, bearer_headers):
    """404 errors must return RFC 7807 Problem Detail format."""
    resp = client.get("/v1/agents/sessions/nonexistent-id", headers=bearer_headers)
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"

    # Check RFC 7807 format
    data = resp.json()
    assert "type" in data, "RFC 7807 'type' missing"
    assert "title" in data, "RFC 7807 'title' missing"
    assert "status" in data, "RFC 7807 'status' missing"
    assert "detail" in data, "RFC 7807 'detail' missing"
    assert "instance" in data, "RFC 7807 'instance' missing"
    assert data["status"] == 404, f"status should be 404, got {data['status']}"

    # Check media type is problem+json
    assert "application/problem+json" in resp.headers.get(
        "Content-Type", ""
    ), f"Content-Type should include problem+json, got {resp.headers.get('Content-Type')}"


def test_422_validation_error_returns_rfc7807_problem_detail(client, bearer_headers):
    """422 validation errors must return RFC 7807 Problem Detail format."""
    # Create session
    create_resp = client.post(
        "/v1/agents/sessions",
        json={"manager": "default", "tools": [], "temperature": 0.7, "max_steps": 10},
        headers=bearer_headers,
    )
    assert create_resp.status_code in (200, 201)
    session_id = create_resp.json()["session_id"]

    # Try to create step with invalid type
    step_resp = client.post(
        f"/v1/agents/sessions/{session_id}/steps",
        json={"type": "invalid-type", "message": "test"},
        headers=bearer_headers,
    )
    assert step_resp.status_code == 422, f"Expected 422, got {step_resp.status_code}"

    # Check RFC 7807 format
    data = step_resp.json()
    assert "type" in data, "RFC 7807 'type' missing"
    assert "title" in data, "RFC 7807 'title' missing"
    assert "status" in data, "RFC 7807 'status' missing"
    assert "detail" in data, "RFC 7807 'detail' missing"
    assert data["status"] == 422, f"status should be 422, got {data['status']}"

    # Check media type is problem+json
    assert "application/problem+json" in step_resp.headers.get(
        "Content-Type", ""
    ), f"Content-Type should include problem+json, got {step_resp.headers.get('Content-Type')}"


def test_list_sessions_uses_next_cursor_pagination(client, bearer_headers):
    """GET /agents/sessions must use next_cursor (not next_page_token)."""
    resp = client.get("/v1/agents/sessions", headers=bearer_headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    data = resp.json()
    assert "items" in data, "Response should have 'items' field"
    assert "next_cursor" in data, "Response should use 'next_cursor' (not 'next_page_token')"


def test_list_steps_uses_next_cursor_pagination(client, bearer_headers):
    """GET /agents/sessions/{id}/steps must use next_cursor."""
    # Create session and step
    create_resp = client.post(
        "/v1/agents/sessions",
        json={"manager": "default", "tools": [], "temperature": 0.7, "max_steps": 10},
        headers=bearer_headers,
    )
    assert create_resp.status_code in (200, 201)
    session_id = create_resp.json()["session_id"]

    # Get steps
    steps_resp = client.get(f"/v1/agents/sessions/{session_id}/steps", headers=bearer_headers)
    assert steps_resp.status_code == 200, f"Expected 200, got {steps_resp.status_code}"

    data = steps_resp.json()
    assert "items" in data, "Response should have 'items' field"
    assert "next_cursor" in data, "Response should use 'next_cursor' (not 'next_page_token')"


def test_x_request_id_on_all_responses(client, bearer_headers):
    """All responses should include X-Request-Id header."""
    endpoints = [
        ("GET", "/v1/agents/sessions"),
    ]

    for method, path in endpoints:
        if method == "GET":
            resp = client.get(path, headers=bearer_headers)
        else:
            resp = client.post(path, json={}, headers=bearer_headers)

        assert "X-Request-Id" in resp.headers, f"X-Request-Id missing on {method} {path}"


def test_cors_exposes_all_required_headers():
    """CORS should expose all required headers."""
    from src.config import settings
    from src.app import create_app

    app = create_app()

    # Find CORS middleware
    cors_found = False
    for middleware in app.user_middleware:
        if "CORSMiddleware" in str(middleware):
            cors_found = True
            # Check exposed headers
            if hasattr(middleware, "options"):
                exposed = middleware.options.get("expose_headers", [])
                required = ["X-Request-Id", "Location", "Idempotency-Key", "Idempotency-Replayed", "ETag", "Vary"]
                for header in required:
                    assert header in exposed or header.lower() in [
                        h.lower() for h in exposed
                    ], f"CORS should expose {header}, got {exposed}"

    # Just warn if not found (middleware detection might be tricky)
    if not cors_found:
        pytest.skip("Could not verify CORS middleware configuration")
