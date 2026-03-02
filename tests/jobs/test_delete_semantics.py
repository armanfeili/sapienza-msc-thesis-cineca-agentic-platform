"""
DELETE /v1/jobs/{id} semantics regression tests.

Tests the DELETE behavior for all job states:
- queued/running: first DELETE → 202, subsequent → 200
- finished/failed/cancelled: DELETE → 200 (already terminal)
"""

import pytest
from fastapi.testclient import TestClient
from src.app import app
from src.jobs.factory import get_stores
from src.jobs.models import JobStatus, JobDocument
from datetime import datetime, timezone
import uuid


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_headers(configure_oidc, mint_token):
    """Admin token with admin:all scope."""
    token = mint_token(sub="admin@example.com", roles=["admin"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_headers(configure_oidc, mint_token):
    """Regular user token (owner)."""
    token = mint_token(sub="owner@example.com", roles=["user"])
    return {"Authorization": f"Bearer {token}"}


async def create_job_in_state(job_id: str, owner: str, status: JobStatus):
    """Helper to directly create a job in a specific state."""
    job_store, _, _ = get_stores()

    job_doc = JobDocument(
        id=job_id,
        owner=owner,
        tenant_id="test-tenant",
        type="test",
        status=status,
        payload={"test": "data"},
        result={"test": "result"} if status in (JobStatus.FINISHED, JobStatus.FAILED) else None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        error="Test error" if status == JobStatus.FAILED else None,
    )

    await job_store.create(job_doc, ttl_seconds=3600)
    return job_id


# ========== QUEUED state ==========


@pytest.mark.asyncio
async def test_delete_queued_first_returns_202(client, user_headers):
    """DELETE on queued job: first call → 202 Accepted."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "owner@example.com", JobStatus.QUEUED)

    resp = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)

    assert resp.status_code == 202
    body = resp.json()
    assert body["id"] == job_id
    assert body["status"] == "cancelled"


@pytest.mark.asyncio
async def test_delete_queued_repeat_returns_200(client, user_headers):
    """DELETE on queued job: second call → 200 OK (already cancelled)."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "owner@example.com", JobStatus.QUEUED)

    # First DELETE → 202
    resp1 = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)
    assert resp1.status_code == 202

    # Second DELETE → 200
    resp2 = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["id"] == job_id
    assert body["status"] == "cancelled"


# ========== RUNNING state ==========


@pytest.mark.asyncio
async def test_delete_running_first_returns_202(client, user_headers):
    """DELETE on running job: first call → 202 Accepted."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "owner@example.com", JobStatus.RUNNING)

    resp = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)

    assert resp.status_code == 202
    body = resp.json()
    assert body["id"] == job_id
    assert body["status"] == "cancelled"


@pytest.mark.asyncio
async def test_delete_running_repeat_returns_200(client, user_headers):
    """DELETE on running job: second call → 200 OK (already cancelled)."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "owner@example.com", JobStatus.RUNNING)

    # First DELETE → 202
    resp1 = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)
    assert resp1.status_code == 202

    # Second DELETE → 200
    resp2 = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["status"] == "cancelled"


# ========== FINISHED state ==========


@pytest.mark.asyncio
async def test_delete_finished_returns_200(client, user_headers):
    """DELETE on finished job: already terminal → 200 OK (idempotent)."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "owner@example.com", JobStatus.FINISHED)

    resp = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    assert body["status"] == "finished"  # Remains finished


@pytest.mark.asyncio
async def test_delete_finished_repeat_returns_200(client, user_headers):
    """DELETE on finished job: repeat → 200 OK (no state change)."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "owner@example.com", JobStatus.FINISHED)

    # First DELETE → 200
    resp1 = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)
    assert resp1.status_code == 200

    # Second DELETE → 200
    resp2 = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["status"] == "finished"


# ========== FAILED state ==========


@pytest.mark.asyncio
async def test_delete_failed_returns_200(client, user_headers):
    """DELETE on failed job: already terminal → 200 OK (idempotent)."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "owner@example.com", JobStatus.FAILED)

    resp = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    assert body["status"] == "failed"  # Remains failed


@pytest.mark.asyncio
async def test_delete_failed_repeat_returns_200(client, user_headers):
    """DELETE on failed job: repeat → 200 OK (no state change)."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "owner@example.com", JobStatus.FAILED)

    # First DELETE → 200
    resp1 = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)
    assert resp1.status_code == 200

    # Second DELETE → 200
    resp2 = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["status"] == "failed"


# ========== CANCELLED state ==========


@pytest.mark.asyncio
async def test_delete_cancelled_returns_200(client, user_headers):
    """DELETE on cancelled job: already cancelled → 200 OK (idempotent)."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "owner@example.com", JobStatus.CANCELLED)

    resp = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    assert body["status"] == "cancelled"


@pytest.mark.asyncio
async def test_delete_cancelled_repeat_returns_200(client, user_headers):
    """DELETE on cancelled job: repeat → 200 OK (no state change)."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "owner@example.com", JobStatus.CANCELLED)

    # First DELETE → 200
    resp1 = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)
    assert resp1.status_code == 200

    # Second DELETE → 200
    resp2 = client.delete(f"/v1/jobs/{job_id}", headers=user_headers)
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["status"] == "cancelled"


# ========== Admin can cancel any job ==========


@pytest.mark.asyncio
async def test_admin_can_delete_any_job(client, admin_headers):
    """Admin can DELETE jobs owned by others."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "someuser@example.com", JobStatus.QUEUED)

    resp = client.delete(f"/v1/jobs/{job_id}", headers=admin_headers)

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "cancelled"


# ========== Non-owner gets 404 ==========


@pytest.mark.asyncio
async def test_non_owner_delete_returns_404(client, configure_oidc, mint_token):
    """Non-owner attempting DELETE gets 404 (anti-enumeration)."""
    job_id = str(uuid.uuid4())
    await create_job_in_state(job_id, "owner@example.com", JobStatus.QUEUED)

    # Different user tries to delete
    other_token = mint_token(sub="other@example.com", roles=["user"])
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp = client.delete(f"/v1/jobs/{job_id}", headers=other_headers)

    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "Job not found"
