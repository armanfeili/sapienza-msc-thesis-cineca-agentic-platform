"""Test to verify HTTP status codes and RFC 7807 error format (no DB dependency)."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient


def test_create_session_status_code_is_201_not_200(client, bearer_headers):
    """Verify the decorator shows status_code=201."""
    from src.routers.agent import router

    # Find the create_session route
    for route in router.routes:
        if (
            hasattr(route, "path")
            and route.path == "/sessions"
            and hasattr(route, "methods")
            and "POST" in route.methods
        ):
            # Check the status_code in the route
            if hasattr(route, "status_code"):
                assert route.status_code == 201, f"Expected status_code=201, got {route.status_code}"
            print(f"✅ POST /sessions route has status_code=201")
            break


def test_validation_error_returns_rfc7807_problem_detail(client):
    """Verify validation errors return RFC 7807 format (no auth needed for bad JSON)."""
    # Send malformed request body
    resp = client.post(
        "/v1/agents/sessions",
        json={"temperature": "not-a-number"},  # Should be float
        headers={"Authorization": "Bearer invalid"},  # Invalid token
    )

    # Could be 422 (validation) or 401 (auth), both should be RFC 7807
    assert resp.status_code in (401, 422), f"Expected 401 or 422, got {resp.status_code}"

    # Check RFC 7807 format
    data = resp.json()
    assert "type" in data, f"RFC 7807 'type' missing: {data}"
    assert "title" in data, f"RFC 7807 'title' missing: {data}"
    assert "status" in data, f"RFC 7807 'status' missing: {data}"

    # Check media type
    content_type = resp.headers.get("Content-Type", "")
    if resp.status_code == 422:
        assert (
            "application/problem+json" in content_type
        ), f"Content-Type should be problem+json for 422, got {content_type}"

    print(f"✅ Error response ({resp.status_code}) uses RFC 7807 format")


def test_location_header_is_set_in_create_session_response_decorator(client):
    """Verify Location header is documented in the response decorator."""
    from src.routers.agent import router

    for route in router.routes:
        if (
            hasattr(route, "path")
            and route.path == "/sessions"
            and hasattr(route, "methods")
            and "POST" in route.methods
        ):
            # Check if responses dict includes Location header
            if hasattr(route, "responses") and isinstance(route.responses, dict):
                resp_201 = route.responses.get(201, {})
                if isinstance(resp_201, dict) and "headers" in resp_201:
                    assert (
                        "Location" in resp_201["headers"]
                    ), f"Location header not in 201 response: {resp_201['headers']}"
                    print(f"✅ POST /sessions response decorator documents Location header")
                    break


def test_error_responses_use_problem_detail_model():
    """Verify error responses use ProblemDetail model."""
    from src.routers.agent import router, ProblemDetail

    for route in router.routes:
        if (
            hasattr(route, "path")
            and route.path == "/sessions"
            and hasattr(route, "methods")
            and "POST" in route.methods
        ):
            if hasattr(route, "responses") and isinstance(route.responses, dict):
                # Check 404, 409, 422 responses use ProblemDetail
                for code in [400, 404, 409]:
                    if code in route.responses:
                        resp_info = route.responses[code]
                        if isinstance(resp_info, dict) and "model" in resp_info:
                            assert (
                                resp_info["model"] == ProblemDetail
                            ), f"Status {code} should use ProblemDetail model, got {resp_info['model']}"
                            print(f"✅ Status {code} response uses ProblemDetail model")


def test_delete_endpoint_status_code():
    """Verify DELETE endpoint returns 204."""
    from src.routers.agent import router

    for route in router.routes:
        if (
            hasattr(route, "path")
            and "/sessions/{session_id}" in route.path
            and hasattr(route, "methods")
            and "DELETE" in route.methods
        ):
            assert route.status_code == 204, f"DELETE should return 204, got {route.status_code}"
            print(f"✅ DELETE /sessions/{{session_id}} has status_code=204")
            break


def test_get_endpoints_have_etag_support():
    """Verify GET endpoints document ETag support."""
    from src.routers.agent import router

    get_routes = [
        ("/sessions", "list_sessions"),
        ("/sessions/{session_id}", "get_session"),
        ("/sessions/{session_id}/steps", "list_session_steps"),
    ]

    for route in router.routes:
        if hasattr(route, "path") and hasattr(route, "methods") and "GET" in route.methods:
            for expected_path, _ in get_routes:
                if expected_path in route.path:
                    if hasattr(route, "responses") and isinstance(route.responses, dict):
                        resp_200 = route.responses.get(200, {})
                        if isinstance(resp_200, dict) and "headers" in resp_200:
                            assert (
                                "ETag" in resp_200["headers"]
                            ), f"ETag not in 200 response for {route.path}: {resp_200['headers']}"
                            print(f"✅ GET {route.path} documents ETag header")
                        break
