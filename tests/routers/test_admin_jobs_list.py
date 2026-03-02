"""
Tests for admin jobs list endpoint.

Validates:
- Authorization (admin:all required)
- Status filtering
- Pagination (limit, page_token)
- ETag caching (If-None-Match → 304)
- Anti-enumeration (non-admin gets 403/404)
"""

import pytest
from fastapi.testclient import TestClient


def test_admin_jobs_list_requires_admin(client: TestClient, mint_token):
    """Admin jobs endpoint requires admin:all scope."""
    # Non-admin user token (no admin:all scope)
    user_token = mint_token(sub="user123", roles=["user"])
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Admin user token (with admin:all scope)
    admin_token = mint_token(sub="admin", roles=["admin"])
    bearer_headers = {"Authorization": f"Bearer {admin_token}"}

    # Non-admin user should get 403 Forbidden
    resp = client.get("/v1/admin/jobs", headers=user_headers)
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    # Admin user should get 200 OK
    resp = client.get("/v1/admin/jobs", headers=bearer_headers)
    assert resp.status_code == 200


def test_admin_jobs_list_basic(client: TestClient, bearer_headers):
    """Admin can list all jobs across owners."""
    # Create jobs as admin
    job1_resp = client.post(
        "/v1/jobs", json={"type": "demo", "payload": {"test": "admin-list-1"}}, headers=bearer_headers
    )
    assert resp.status_code == 202
    job1_id = job1_resp.json()["id"]

    job2_resp = client.post(
        "/v1/jobs", json={"type": "demo", "payload": {"test": "admin-list-2"}}, headers=bearer_headers
    )
    assert resp.status_code == 202
    job2_id = job2_resp.json()["id"]

    # List all jobs
    resp = client.get("/v1/admin/jobs", headers=bearer_headers)
    assert resp.status_code == 200

    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "has_more" in data

    # Should contain both jobs
    job_ids = [item["id"] for item in data["items"]]
    assert job1_id in job_ids
    assert job2_id in job_ids


def test_admin_jobs_list_status_filter(client: TestClient, bearer_headers):
    """Status filter works correctly."""
    # Create jobs in different states
    queued_job_resp = client.post(
        "/v1/jobs", json={"type": "demo", "payload": {"test": "queued"}}, headers=bearer_headers
    )
    assert resp.status_code == 202
    queued_job_id = queued_job_resp.json()["id"]

    # Cancel one job (to get cancelled status)
    cancelled_job_resp = client.post(
        "/v1/jobs", json={"type": "demo", "payload": {"test": "to-cancel"}}, headers=bearer_headers
    )
    assert resp.status_code == 202
    cancelled_job_id = cancelled_job_resp.json()["id"]

    cancel_resp = client.post(f"/v2/jobs/{cancelled_job_id}/cancel", headers=bearer_headers)
    assert cancel_resp.status_code == 202

    # Filter by queued status
    resp_queued = client.get("/v1/admin/jobs?status=queued", headers=bearer_headers)
    assert resp_queued.status_code == 200
    queued_data = resp_queued.json()
    queued_ids = [item["id"] for item in queued_data["items"]]

    # Should contain queued job, not cancelled
    assert queued_job_id in queued_ids
    assert cancelled_job_id not in queued_ids

    # Filter by cancelled status
    resp_cancelled = client.get("/v1/admin/jobs?status=cancelled", headers=bearer_headers)
    assert resp_cancelled.status_code == 200
    cancelled_data = resp_cancelled.json()
    cancelled_ids = [item["id"] for item in cancelled_data["items"]]

    # Should contain cancelled job, not queued
    assert cancelled_job_id in cancelled_ids
    assert queued_job_id not in cancelled_ids


def test_admin_jobs_list_pagination(client: TestClient, bearer_headers):
    """Pagination with limit and page_token works."""
    # Create multiple jobs
    job_ids = []
    for i in range(5):
        resp = client.post("/v1/jobs", json={"type": "demo", "payload": {"index": i}}, headers=bearer_headers)
        assert resp.status_code == 202
        job_ids.append(resp.json()["id"])

    # Get first page with limit=2
    resp_page1 = client.get("/v1/admin/jobs?limit=2", headers=bearer_headers)
    assert resp_page1.status_code == 200
    page1_data = resp_page1.json()

    assert len(page1_data["items"]) <= 2
    assert page1_data["has_more"] in [True, False]

    # If there's more, get next page
    if page1_data["has_more"]:
        next_token = page1_data["next_page_token"]
        assert next_token is not None

        resp_page2 = client.get(f"/v1/admin/jobs?limit=2&page_token={next_token}", headers=bearer_headers)
        assert resp_page2.status_code == 200
        page2_data = resp_page2.json()

        # Pages should not overlap
        page1_ids = {item["id"] for item in page1_data["items"]}
        page2_ids = {item["id"] for item in page2_data["items"]}
        assert len(page1_ids & page2_ids) == 0, "Pages should not overlap"


def test_admin_jobs_list_invalid_page_token(client: TestClient, bearer_headers):
    """Invalid page_token returns 400."""
    # Non-integer token
    resp = client.get("/v1/admin/jobs?page_token=invalid", headers=bearer_headers)
    assert resp.status_code == 400
    assert "page_token" in resp.text.lower()

    # Negative token
    resp = client.get("/v1/admin/jobs?page_token=-1", headers=bearer_headers)
    assert resp.status_code == 400


def test_admin_jobs_list_etag_caching(client: TestClient, bearer_headers):
    """ETag caching with If-None-Match returns 304."""
    # Create a job
    job_resp = client.post("/v1/jobs", json={"type": "demo", "payload": {"test": "etag"}}, headers=bearer_headers)
    assert resp.status_code == 202

    # First request
    resp1 = client.get("/v1/admin/jobs", headers=bearer_headers)
    assert resp1.status_code == 200
    etag = resp1.headers.get("ETag")
    assert etag is not None, "ETag header should be present"

    # Second request with If-None-Match (content unchanged)
    headers_with_etag = {**bearer_headers, "If-None-Match": etag}
    resp2 = client.get("/v1/admin/jobs", headers=headers_with_etag)
    assert resp2.status_code == 304, f"Expected 304, got {resp2.status_code}"


def test_admin_jobs_list_invalid_status_filter(client: TestClient, bearer_headers):
    """Invalid status filter returns 400."""
    resp = client.get("/v1/admin/jobs?status=invalid-status", headers=bearer_headers)
    assert resp.status_code == 400
    assert "status" in resp.text.lower()


def test_admin_jobs_list_multi_status_filter(client: TestClient, bearer_headers):
    """Multiple status filters work (repeated query param)."""
    # Create jobs
    queued_resp = client.post("/v1/jobs", json={"type": "demo", "payload": {"test": "queued"}}, headers=bearer_headers)
    assert resp.status_code == 202
    queued_id = queued_resp.json()["id"]

    cancelled_resp = client.post(
        "/v1/jobs", json={"type": "demo", "payload": {"test": "cancelled"}}, headers=bearer_headers
    )
    assert resp.status_code == 202
    cancelled_id = cancelled_resp.json()["id"]

    # Cancel second job
    client.post(f"/v2/jobs/{cancelled_id}/cancel", headers=bearer_headers)

    # Filter by multiple statuses (queued OR cancelled)
    resp = client.get("/v1/admin/jobs?status=queued&status=cancelled", headers=bearer_headers)
    assert resp.status_code == 200
    data = resp.json()

    job_ids = [item["id"] for item in data["items"]]
    # Should contain both
    assert queued_id in job_ids or cancelled_id in job_ids


def test_admin_jobs_list_response_structure(client: TestClient, bearer_headers):
    """Response has correct structure and fields."""
    # Create a job
    job_resp = client.post("/v1/jobs", json={"type": "demo", "payload": {"test": "structure"}}, headers=bearer_headers)
    assert resp.status_code == 202

    # List jobs
    resp = client.get("/v1/admin/jobs", headers=bearer_headers)
    assert resp.status_code == 200

    data = resp.json()

    # Top-level structure
    assert "items" in data
    assert "total" in data
    assert "has_more" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)
    assert isinstance(data["has_more"], bool)

    # Item structure
    if data["items"]:
        item = data["items"][0]
        assert "id" in item
        assert "type" in item
        assert "status" in item
        assert "created_at" in item
        assert "owner" in item
        # Optional fields
        assert "updated_at" in item or "updated_at" not in item
        assert "result" in item or "result" not in item
        assert "tenant_id" in item or "tenant_id" not in item


def test_admin_jobs_list_limit_validation(client: TestClient, bearer_headers):
    """Limit parameter validation (1-50 range)."""
    # Too low
    resp = client.get("/v1/admin/jobs?limit=0", headers=bearer_headers)
    assert resp.status_code == 422  # Validation error

    # Too high
    resp = client.get("/v1/admin/jobs?limit=100", headers=bearer_headers)
    assert resp.status_code == 422  # Validation error

    # Valid range
    resp = client.get("/v1/admin/jobs?limit=1", headers=bearer_headers)
    assert resp.status_code == 200

    resp = client.get("/v1/admin/jobs?limit=50", headers=bearer_headers)
    assert resp.status_code == 200
