"""
Tests for Jobs API error semantics and RFC 9457 problem+json responses.

Verifies:
- 400 for malformed UUIDs
- 404 for not found
- 403 for missing admin:all scope
- No 500s for client errors
- application/problem+json format
"""

import pytest
import uuid


@pytest.fixture
def user_headers(mint_token):
    """Non-admin user token."""
    tok = mint_token(sub="user123", roles=["user"])
    return {"Authorization": f"Bearer {tok}"}


def test_malformed_uuid_returns_400(client, bearer_headers):
    """Invalid UUID should return 400, not 500."""
    resp = client.get("/v1/jobs/not-a-uuid", headers=bearer_headers)
    assert resp.status_code == 400
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["status"] == 400
    assert "detail" in body or "title" in body


def test_malformed_uuid_delete_returns_400(client, bearer_headers):
    """DELETE with invalid UUID should return 400."""
    resp = client.delete("/v1/jobs/not-a-uuid", headers=bearer_headers)
    assert resp.status_code == 400
    assert resp.headers["content-type"] == "application/problem+json"


def test_malformed_uuid_sse_returns_400(client, bearer_headers):
    """SSE stream with invalid UUID should return 400."""
    resp = client.get("/v1/jobs/not-a-uuid/events", headers=bearer_headers)
    assert resp.status_code == 400
    assert resp.headers["content-type"] == "application/problem+json"


def test_not_found_returns_404(client, bearer_headers):
    """Valid UUID but non-existent job should return 404."""
    fake_uuid = str(uuid.uuid4())
    resp = client.get(f"/v1/jobs/{fake_uuid}", headers=bearer_headers)
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["status"] == 404


def test_not_found_delete_returns_404(client, bearer_headers):
    """DELETE on non-existent job should return 404."""
    fake_uuid = str(uuid.uuid4())
    resp = client.delete(f"/v1/jobs/{fake_uuid}", headers=bearer_headers)
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/problem+json"


def test_admin_endpoint_requires_admin_scope(client, user_headers):
    """Admin list should return 403 when admin:all scope missing."""
    resp = client.get("/v1/admin/jobs", headers=user_headers)
    assert resp.status_code == 403
    assert resp.headers["content-type"] == "application/problem+json"


def test_admin_delete_requires_admin_scope(client, bearer_headers, user_headers):
    """Admin DELETE should return 403 without admin:all."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50}},
        headers=bearer_headers,
    )
    job_id = resp.json()["id"]

    resp = client.delete(f"/v1/admin/jobs/{job_id}", headers=user_headers)
    assert resp.status_code == 403
    assert resp.headers["content-type"] == "application/problem+json"


def test_admin_list_requires_admin_scope(client, user_headers):
    """Admin list should return 403 without admin:all (duplicate for coverage)."""
    resp = client.get("/v1/admin/jobs", headers=user_headers)
    assert resp.status_code == 403
    assert resp.headers["content-type"] == "application/problem+json"


def test_problem_json_has_required_fields(client, bearer_headers):
    """Problem+json response should have RFC 9457 required fields."""
    resp = client.get("/v1/jobs/not-a-uuid", headers=bearer_headers)
    assert resp.status_code == 400
    body = resp.json()

    # Required fields per RFC 9457
    assert "status" in body
    assert body["status"] == 400

    # At least one of title/detail should be present
    assert "title" in body or "detail" in body


def test_problem_json_includes_correlation_id(client, bearer_headers):
    """Problem+json should include correlation_id in extensions."""
    resp = client.get("/v1/jobs/not-a-uuid", headers=bearer_headers)
    body = resp.json()

    # Should have extensions with correlation_id
    assert "extensions" in body
    assert "correlation_id" in body["extensions"]


def test_no_500_for_client_errors(client, bearer_headers):
    """Client errors should never return 500."""
    test_cases = [
        ("GET", "/v1/jobs/not-a-uuid", None),
        ("DELETE", "/v1/jobs/not-a-uuid", None),
        ("GET", f"/v1/jobs/{uuid.uuid4()}", None),  # 404
    ]

    for method, path, json_body in test_cases:
        if method == "GET":
            resp = client.get(path, headers=bearer_headers)
        elif method == "DELETE":
            resp = client.delete(path, headers=bearer_headers)

        assert resp.status_code in (400, 403, 404), f"{method} {path} returned {resp.status_code}, expected 4xx"
        assert resp.headers["content-type"] == "application/problem+json"
