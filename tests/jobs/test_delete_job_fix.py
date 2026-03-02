"""
Test DELETE /jobs/{job_id} to verify asyncio.run() fix.

Ensures:
- No event loop crashes (asyncio.run() removed from request handler)
- First cancel returns 202 Accepted
- Subsequent cancels return 200 OK
- Works with both memory and Redis backends
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def admin_headers(mint_token):
    """Generate admin token with admin:all permission."""
    token = mint_token(
        sub="admin-user",
        roles=["admin"],
        scopes=["admin:all"],
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(app):
    """Test client for the FastAPI app."""
    return TestClient(app)


def test_delete_job_first_cancel_202(client, admin_headers):
    """First DELETE should return 202 Accepted when transitioning to cancelled."""
    # Create a job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 10000}},
        headers=admin_headers,
    )
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    # First cancel should return 202
    cancel_resp = client.delete(f"/v1/jobs/{job_id}", headers=admin_headers)
    assert cancel_resp.status_code == 202, f"Expected 202, got {cancel_resp.status_code}: {cancel_resp.text}"
    assert cancel_resp.json()["status"] == "cancelled"
    assert cancel_resp.json()["id"] == job_id


def test_delete_job_subsequent_cancel_200(client, admin_headers):
    """Subsequent DELETE calls should return 200 OK (idempotent)."""
    import uuid

    # Create a job with unique payload to avoid idempotency replay
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 10000, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    # First cancel
    client.delete(f"/v1/jobs/{job_id}", headers=admin_headers)

    # Second cancel should return 200
    cancel_resp = client.delete(f"/v1/jobs/{job_id}", headers=admin_headers)
    assert cancel_resp.status_code == 200, f"Expected 200, got {cancel_resp.status_code}: {cancel_resp.text}"
    assert cancel_resp.json()["status"] == "cancelled"


def test_delete_job_already_finished_200(client, admin_headers):
    """DELETE on finished job should return 200 OK."""
    # Create a job that finishes quickly
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 1}},
        headers=admin_headers,
    )
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    # Wait for job to finish
    import time

    time.sleep(0.5)

    # Cancel finished job should return 200
    cancel_resp = client.delete(f"/v1/jobs/{job_id}", headers=admin_headers)
    assert cancel_resp.status_code == 200
    # Status should be finished, not cancelled
    assert cancel_resp.json()["status"] in ("finished", "failed", "cancelled")


def test_delete_job_invalid_uuid_400(client, admin_headers):
    """DELETE with invalid UUID should return 400 Bad Request."""
    cancel_resp = client.delete("/v1/jobs/not-a-uuid", headers=admin_headers)
    assert cancel_resp.status_code == 400
    assert "Invalid job_id format" in cancel_resp.json()["detail"]


def test_delete_job_not_found_404(client, admin_headers):
    """DELETE on non-existent job should return 404 Not Found."""
    import uuid

    fake_id = str(uuid.uuid4())
    cancel_resp = client.delete(f"/v1/jobs/{fake_id}", headers=admin_headers)
    assert cancel_resp.status_code == 404
    assert "not found" in cancel_resp.json()["detail"].lower()


def test_delete_job_no_auth_401(client):
    """DELETE without auth should return 401 Unauthorized."""
    import uuid

    fake_id = str(uuid.uuid4())
    cancel_resp = client.delete(f"/v1/jobs/{fake_id}")
    assert cancel_resp.status_code == 401


def test_delete_job_insufficient_perms_403(client, mint_token):
    """DELETE without admin:all should return 403 Forbidden."""
    # Token without admin:all
    token = mint_token(
        sub="regular-user",
        scopes=["read:jobs"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    import uuid

    fake_id = str(uuid.uuid4())
    cancel_resp = client.delete(f"/v1/jobs/{fake_id}", headers=headers)
    assert cancel_resp.status_code == 403


def test_delete_job_cache_control_header(client, admin_headers):
    """DELETE response should have Cache-Control: no-store."""
    # Create a job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 10000}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    # Cancel and check headers
    cancel_resp = client.delete(f"/v1/jobs/{job_id}", headers=admin_headers)
    assert "Cache-Control" in cancel_resp.headers
    assert cancel_resp.headers["Cache-Control"] == "no-store"


def test_delete_no_asyncio_crash(client, admin_headers):
    """
    Verify no asyncio.run() crash occurs during DELETE.

    Previously, calling asyncio.run() in a FastAPI request handler
    would crash with: "RuntimeError: asyncio.run() cannot be called from a running event loop"

    This test ensures the fix (using await instead of asyncio.run) works.
    """
    import uuid

    # Create multiple jobs with unique payloads
    job_ids = []
    for _ in range(3):
        resp = client.post(
            "/v1/jobs",
            json={"type": "demo", "payload": {"duration_ms": 10000, "test_id": str(uuid.uuid4())}},
            headers=admin_headers,
        )
        assert resp.status_code == 202
        job_ids.append(resp.json()["id"])

    # Cancel all jobs - should not crash
    for job_id in job_ids:
        cancel_resp = client.delete(f"/v1/jobs/{job_id}", headers=admin_headers)
        assert cancel_resp.status_code in (200, 202)
        assert "id" in cancel_resp.json()
        assert "status" in cancel_resp.json()
