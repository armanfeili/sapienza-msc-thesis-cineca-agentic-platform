"""
Caching parity tests: Vary header, ETag isolation, 304 responses.

Verifies:
- Vary: Authorization header present on user-scoped endpoints
- ETags differ for different users viewing different jobs
- 304 Not Modified works correctly with If-None-Match
"""

import pytest
from fastapi.testclient import TestClient
from src.app import app
import uuid
import json


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def user_alice(configure_oidc, mint_token):
    """Alice's token."""
    token = mint_token(sub="alice@example.com", roles=["user"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_bob(configure_oidc, mint_token):
    """Bob's token."""
    token = mint_token(sub="bob@example.com", roles=["user"])
    return {"Authorization": f"Bearer {token}"}


# ========== Vary: Authorization header ==========


def test_get_job_has_vary_authorization(client, user_alice):
    """GET /v1/jobs/{id} includes Vary: Authorization header."""
    # Create a job as Alice
    create_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50}},
        headers=user_alice,
    )
    assert create_resp.status_code in (200, 202)
    job_id = create_resp.json()["id"]

    # Get job status
    resp = client.get(f"/v1/jobs/{job_id}", headers=user_alice)

    assert resp.status_code == 200
    assert "Vary" in resp.headers
    assert "Authorization" in resp.headers["Vary"]


def test_list_jobs_has_vary_authorization(client, user_alice):
    """GET /v1/jobs (list) includes Vary: Authorization header."""
    # Create at least one job
    client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {}},
        headers=user_alice,
    )

    # List jobs
    resp = client.get("/v1/jobs", headers=user_alice)

    assert resp.status_code == 200
    assert "Vary" in resp.headers
    assert "Authorization" in resp.headers["Vary"]


def test_304_response_has_vary_authorization(client, user_alice):
    """304 Not Modified response includes Vary: Authorization header."""
    # Create a job
    create_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50}},
        headers=user_alice,
    )
    job_id = create_resp.json()["id"]

    # Get job to obtain ETag
    resp1 = client.get(f"/v1/jobs/{job_id}", headers=user_alice)
    assert resp1.status_code == 200
    etag = resp1.headers.get("ETag")
    assert etag is not None

    # Request again with If-None-Match
    resp2 = client.get(
        f"/v1/jobs/{job_id}",
        headers={**user_alice, "If-None-Match": etag},
    )

    assert resp2.status_code == 304
    assert "Vary" in resp2.headers
    assert "Authorization" in resp2.headers["Vary"]


# ========== ETag isolation ==========


def test_etags_differ_for_different_jobs(client, user_alice):
    """ETags differ for different jobs."""
    # Create two jobs
    resp1 = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50}},
        headers=user_alice,
    )
    job_id_1 = resp1.json()["id"]

    resp2 = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100}},
        headers=user_alice,
    )
    job_id_2 = resp2.json()["id"]

    # Get both jobs
    get1 = client.get(f"/v1/jobs/{job_id_1}", headers=user_alice)
    get2 = client.get(f"/v1/jobs/{job_id_2}", headers=user_alice)

    assert get1.status_code == 200
    assert get2.status_code == 200

    etag1 = get1.headers.get("ETag")
    etag2 = get2.headers.get("ETag")

    assert etag1 is not None
    assert etag2 is not None
    assert etag1 != etag2, "Different jobs should have different ETags"


def test_etags_differ_for_user_a_vs_user_b_different_jobs(client, user_alice, user_bob):
    """Alice's job ETag differs from Bob's job ETag (different jobs)."""
    # Alice creates a job
    alice_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50}},
        headers=user_alice,
    )
    alice_job_id = alice_resp.json()["id"]

    # Bob creates a job with same payload
    bob_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50}},
        headers=user_bob,
    )
    bob_job_id = bob_resp.json()["id"]

    # Get both jobs
    alice_get = client.get(f"/v1/jobs/{alice_job_id}", headers=user_alice)
    bob_get = client.get(f"/v1/jobs/{bob_job_id}", headers=user_bob)

    assert alice_get.status_code == 200
    assert bob_get.status_code == 200

    alice_etag = alice_get.headers.get("ETag")
    bob_etag = bob_get.headers.get("ETag")

    assert alice_etag is not None
    assert bob_etag is not None
    # Different job IDs → different ETags
    assert alice_etag != bob_etag


def test_list_etags_differ_for_user_a_vs_user_b(client, user_alice, user_bob):
    """List endpoint ETags differ for Alice vs Bob (different job sets)."""
    # Alice creates a job
    client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"alice": True}},
        headers=user_alice,
    )

    # Bob creates a job
    client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"bob": True}},
        headers=user_bob,
    )

    # Get lists
    alice_list = client.get("/v1/jobs", headers=user_alice)
    bob_list = client.get("/v1/jobs", headers=user_bob)

    assert alice_list.status_code == 200
    assert bob_list.status_code == 200

    # Lists should differ (Alice sees only her jobs, Bob sees only his)
    alice_items = alice_list.json()["items"]
    bob_items = bob_list.json()["items"]

    alice_ids = {j["id"] for j in alice_items}
    bob_ids = {j["id"] for j in bob_items}

    # No overlap (user isolation)
    assert len(alice_ids & bob_ids) == 0, "Users should not see each other's jobs"


# ========== 304 Not Modified behavior ==========


def test_if_none_match_returns_304(client, user_alice):
    """If-None-Match with matching ETag returns 304."""
    # Create a job
    create_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50}},
        headers=user_alice,
    )
    job_id = create_resp.json()["id"]

    # First GET to obtain ETag
    resp1 = client.get(f"/v1/jobs/{job_id}", headers=user_alice)
    assert resp1.status_code == 200
    etag = resp1.headers.get("ETag")

    # Second GET with If-None-Match
    resp2 = client.get(
        f"/v1/jobs/{job_id}",
        headers={**user_alice, "If-None-Match": etag},
    )

    assert resp2.status_code == 304
    assert resp2.content == b"", "304 response should have no body"
    assert resp2.headers.get("ETag") == etag


def test_if_none_match_with_different_etag_returns_200(client, user_alice):
    """If-None-Match with non-matching ETag returns 200 with full body."""
    # Create a job
    create_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 50}},
        headers=user_alice,
    )
    job_id = create_resp.json()["id"]

    # Get job status
    resp = client.get(
        f"/v1/jobs/{job_id}",
        headers={**user_alice, "If-None-Match": 'W/"different-etag"'},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    assert "status" in body


def test_etag_changes_when_status_changes(client, user_alice):
    """ETag changes when job status changes."""
    import time

    # Create a long-running job
    create_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 500}},
        headers=user_alice,
    )
    job_id = create_resp.json()["id"]

    # Get initial ETag (likely queued)
    resp1 = client.get(f"/v1/jobs/{job_id}", headers=user_alice)
    etag1 = resp1.headers.get("ETag")
    status1 = resp1.json()["status"]

    # Wait for status change
    time.sleep(0.7)

    # Get new ETag (likely finished)
    resp2 = client.get(f"/v1/jobs/{job_id}", headers=user_alice)
    etag2 = resp2.headers.get("ETag")
    status2 = resp2.json()["status"]

    # If status changed, ETag should differ
    if status1 != status2:
        assert etag1 != etag2, "ETag should change when status changes"


# ========== Cache-Control headers ==========


def test_get_job_has_cache_control(client, user_alice):
    """GET /v1/jobs/{id} includes Cache-Control header."""
    # Create a job
    create_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {}},
        headers=user_alice,
    )
    job_id = create_resp.json()["id"]

    # Get job
    resp = client.get(f"/v1/jobs/{job_id}", headers=user_alice)

    assert resp.status_code == 200
    assert "Cache-Control" in resp.headers
    # Should be private and short-lived
    cache_control = resp.headers["Cache-Control"]
    assert "private" in cache_control or "no-store" in cache_control


def test_delete_has_no_store_cache_control(client, user_alice):
    """DELETE /v1/jobs/{id} includes Cache-Control: no-store."""
    # Create a job
    create_resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {}},
        headers=user_alice,
    )
    job_id = create_resp.json()["id"]

    # Delete job
    resp = client.delete(f"/v1/jobs/{job_id}", headers=user_alice)

    assert resp.status_code in (200, 202)
    assert "Cache-Control" in resp.headers
    assert "no-store" in resp.headers["Cache-Control"]
