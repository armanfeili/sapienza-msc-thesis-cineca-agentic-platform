"""
Tests for user-owned job permissions and flows.

Verifies:
- Users can create their own jobs (no admin:all required)
- Users can cancel/stream ONLY their own jobs (owner OR admin:all)
- Anti-enumeration: non-owners get 404, not 403
- Admin can access any job
"""

import pytest
import uuid
import json
import time


@pytest.fixture
def user_alice(mint_token):
    """Non-admin user Alice."""
    tok = mint_token(sub="alice@example.com", roles=["user"])
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def user_bob(mint_token):
    """Non-admin user Bob."""
    tok = mint_token(sub="bob@example.com", roles=["user"])
    return {"Authorization": f"Bearer {tok}"}


def test_user_can_create_job(client, user_alice):
    """Any authenticated user can create jobs."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers=user_alice,
    )
    assert resp.status_code == 202
    assert "Location" in resp.headers
    body = resp.json()
    assert "id" in body
    assert body["owner"] == "alice@example.com"


def test_user_job_appears_in_own_list(client, user_alice):
    """Created job appears in GET /v1/jobs for the owner."""
    # Create job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers=user_alice,
    )
    job_id = resp.json()["id"]

    # List jobs
    resp = client.get("/v1/jobs", headers=user_alice)
    assert resp.status_code == 200
    jobs = resp.json()["items"]
    job_ids = [j["id"] for j in jobs]
    assert job_id in job_ids


def test_user_job_not_visible_to_other_users(client, user_alice, user_bob):
    """Jobs created by Alice should not appear in Bob's list."""
    # Alice creates job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers=user_alice,
    )
    alice_job_id = resp.json()["id"]

    # Bob lists jobs
    resp = client.get("/v1/jobs", headers=user_bob)
    assert resp.status_code == 200
    jobs = resp.json()["items"]
    job_ids = [j["id"] for j in jobs]
    assert alice_job_id not in job_ids


def test_owner_can_get_job_status(client, user_alice):
    """Owner can GET their own job."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers=user_alice,
    )
    job_id = resp.json()["id"]

    resp = client.get(f"/v1/jobs/{job_id}", headers=user_alice)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    assert body["owner"] == "alice@example.com"


def test_non_owner_cannot_get_job_status(client, user_alice, user_bob):
    """Non-owner gets 404 (anti-enumeration)."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers=user_alice,
    )
    job_id = resp.json()["id"]

    # Bob tries to GET Alice's job
    resp = client.get(f"/v1/jobs/{job_id}", headers=user_bob)
    assert resp.status_code == 404


def test_admin_can_get_any_job(client, user_alice, bearer_headers):
    """Admin can access any job regardless of owner."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers=user_alice,
    )
    job_id = resp.json()["id"]

    # Admin gets Alice's job
    resp = client.get(f"/v1/jobs/{job_id}", headers=bearer_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["owner"] == "alice@example.com"


def test_owner_can_cancel_own_job(client, user_alice):
    """Owner can DELETE (cancel) their own job."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 5000}},  # Long-running
        headers=user_alice,
    )
    job_id = resp.json()["id"]

    # Cancel
    resp = client.delete(f"/v1/jobs/{job_id}", headers=user_alice)
    assert resp.status_code in (200, 202)  # 202 if first cancel, 200 if already terminal


def test_non_owner_cannot_cancel_job(client, user_alice, user_bob):
    """Non-owner gets 404 when trying to cancel (anti-enumeration)."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 5000}},
        headers=user_alice,
    )
    job_id = resp.json()["id"]

    # Bob tries to cancel Alice's job
    resp = client.delete(f"/v1/jobs/{job_id}", headers=user_bob)
    assert resp.status_code == 404


def test_admin_can_cancel_any_job(client, user_alice, bearer_headers):
    """Admin can cancel any job."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 5000}},
        headers=user_alice,
    )
    job_id = resp.json()["id"]

    # Admin cancels
    resp = client.delete(f"/v1/jobs/{job_id}", headers=bearer_headers)
    assert resp.status_code in (200, 202)


def test_owner_can_stream_sse(client, user_alice):
    """Owner can open SSE stream for their job."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers=user_alice,
    )
    job_id = resp.json()["id"]

    # Open SSE stream
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=user_alice) as sse_resp:
        assert sse_resp.status_code == 200
        assert sse_resp.headers["content-type"] == "text/event-stream; charset=utf-8"


def test_non_owner_cannot_stream_sse(client, user_alice, user_bob):
    """Non-owner gets 404 when trying to open SSE stream."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers=user_alice,
    )
    job_id = resp.json()["id"]

    # Bob tries to stream Alice's job
    resp = client.get(f"/v1/jobs/{job_id}/events", headers=user_bob)
    assert resp.status_code == 404


def test_admin_can_stream_any_sse(client, user_alice, bearer_headers):
    """Admin can stream any job."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers=user_alice,
    )
    job_id = resp.json()["id"]

    # Admin streams
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=bearer_headers) as sse_resp:
        assert sse_resp.status_code == 200


def test_idempotency_for_user_jobs(client, user_alice):
    """Idempotency works for user-created jobs."""
    idem_key = str(uuid.uuid4())

    # First request
    resp1 = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers={**user_alice, "Idempotency-Key": idem_key},
    )
    assert resp1.status_code == 202
    job_id1 = resp1.json()["id"]

    # Replay with same key
    resp2 = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers={**user_alice, "Idempotency-Key": idem_key},
    )
    assert resp2.status_code == 200
    assert resp2.headers.get("Idempotency-Replayed") == "true"
    job_id2 = resp2.json()["id"]
    assert job_id1 == job_id2


def test_cancel_idempotency_for_owner(client, user_alice):
    """Owner can cancel repeatedly (first 202, then 200)."""
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 5000}},
        headers=user_alice,
    )
    job_id = resp.json()["id"]

    # First cancel
    resp1 = client.delete(f"/v1/jobs/{job_id}", headers=user_alice)
    status1 = resp1.status_code

    # Second cancel (idempotent)
    resp2 = client.delete(f"/v1/jobs/{job_id}", headers=user_alice)
    status2 = resp2.status_code

    # One should be 202 (if transition happened), next should be 200
    assert {status1, status2} <= {200, 202}


def test_user_job_full_lifecycle(client, user_alice):
    """Test complete user flow: create → status → SSE → cancel."""
    # 1. Create
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 200}},
        headers=user_alice,
    )
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    # 2. Check status
    resp = client.get(f"/v1/jobs/{job_id}", headers=user_alice)
    assert resp.status_code == 200
    assert resp.json()["owner"] == "alice@example.com"

    # 3. Stream SSE (read a few events)
    with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=user_alice) as sse_resp:
        assert sse_resp.status_code == 200
        lines = []
        for line in sse_resp.iter_lines():
            lines.append(line)
            if len(lines) >= 5:  # Read just a few events
                break
        assert any("retry:" in line for line in lines)

    # 4. Cancel
    resp = client.delete(f"/v1/jobs/{job_id}", headers=user_alice)
    assert resp.status_code in (200, 202)
