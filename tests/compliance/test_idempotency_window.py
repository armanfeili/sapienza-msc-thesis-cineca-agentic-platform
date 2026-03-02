"""
Idempotency replay window tests.

Tests that idempotency keys expire after TTL and allow fresh job creation.
Uses environment variable override to set a short TTL for testing.
"""

import pytest
import uuid
import time
import os
from fastapi.testclient import TestClient
from src.app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def user_headers(configure_oidc, mint_token):
    """Regular user token."""
    token = mint_token(sub="user@example.com", roles=["user"])
    return {"Authorization": f"Bearer {token}"}


# ========== Idempotency replay within window ==========


def test_idempotency_replay_returns_same_job_id(client, user_headers):
    """POST with same Idempotency-Key within TTL returns same job ID with 200."""
    idem_key = f"test-idem-{uuid.uuid4()}"

    payload = {"type": "demo", "payload": {"test": "idempotency"}}

    # First request - should create new job (202)
    resp1 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": idem_key},
    )

    assert resp1.status_code == 202
    assert "Idempotency-Key" in resp1.headers
    assert resp1.headers["Idempotency-Key"] == idem_key
    assert resp1.headers.get("Idempotency-Replayed", "false") == "false"

    job_id_1 = resp1.json()["id"]

    # Second request with same key (immediate replay within TTL)
    resp2 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": idem_key},
    )

    assert resp2.status_code == 200
    assert resp2.headers["Idempotency-Replayed"] == "true"
    assert resp2.headers["Idempotency-Key"] == idem_key

    job_id_2 = resp2.json()["id"]

    # Should return the SAME job ID
    assert job_id_1 == job_id_2


def test_idempotency_replay_preserves_owner(client, user_headers):
    """Replayed idempotency request returns job with original owner."""
    idem_key = f"test-owner-{uuid.uuid4()}"

    payload = {"type": "demo", "payload": {}}

    # Create job
    resp1 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": idem_key},
    )

    assert resp1.status_code == 202
    owner_1 = resp1.json()["owner"]

    # Replay should return same owner
    resp2 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": idem_key},
    )

    assert resp2.status_code == 200
    assert resp2.headers["Idempotency-Replayed"] == "true"
    owner_2 = resp2.json()["owner"]

    assert owner_1 == owner_2 == "user@example.com"


def test_different_idempotency_keys_create_different_jobs(client, user_headers):
    """Different Idempotency-Keys create different jobs (no replay)."""
    idem_key_1 = f"key-a-{uuid.uuid4()}"
    idem_key_2 = f"key-b-{uuid.uuid4()}"

    payload = {"type": "demo", "payload": {"test": "unique"}}

    # First key
    resp1 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": idem_key_1},
    )

    assert resp1.status_code == 202
    job_id_1 = resp1.json()["id"]

    # Second key (different)
    resp2 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": idem_key_2},
    )

    assert resp2.status_code == 202  # Fresh job
    assert resp2.headers.get("Idempotency-Replayed", "false") == "false"
    job_id_2 = resp2.json()["id"]

    # Different job IDs
    assert job_id_1 != job_id_2


def test_no_idempotency_key_deduplicates_by_payload(client, user_headers):
    """
    Requests without explicit Idempotency-Key still deduplicate by payload hash.

    The API computes a fallback idempotency key from:
    - owner (token sub)
    - tenant
    - job type
    - payload hash

    This provides defensive idempotency even when clients don't send explicit keys.
    """
    payload = {"type": "demo", "payload": {"test": "no-key"}}

    # First request (no explicit key, but payload hash is used)
    resp1 = client.post("/v1/jobs", json=payload, headers=user_headers)
    assert resp1.status_code == 202
    job_id_1 = resp1.json()["id"]

    # Second request (same payload, no explicit key)
    resp2 = client.post("/v1/jobs", json=payload, headers=user_headers)

    # Payload-based deduplication returns same job ID (200 OK)
    assert resp2.status_code == 200
    assert resp2.headers.get("Idempotency-Replayed") == "true"
    job_id_2 = resp2.json()["id"]

    assert job_id_1 == job_id_2

    # Different payload creates new job
    different_payload = {"type": "demo", "payload": {"test": "different"}}
    resp3 = client.post("/v1/jobs", json=different_payload, headers=user_headers)
    assert resp3.status_code == 202  # Fresh job
    job_id_3 = resp3.json()["id"]

    assert job_id_3 != job_id_1


# ========== Idempotency key isolation ==========


def test_idempotency_key_isolated_by_user(client, configure_oidc, mint_token):
    """Same Idempotency-Key used by different users creates different jobs."""
    idem_key = f"shared-key-{uuid.uuid4()}"
    payload = {"type": "demo", "payload": {}}

    # User A
    token_a = mint_token(sub="user-a@example.com", roles=["user"])
    headers_a = {"Authorization": f"Bearer {token_a}"}

    resp_a = client.post(
        "/v1/jobs",
        json=payload,
        headers={**headers_a, "Idempotency-Key": idem_key},
    )

    assert resp_a.status_code == 202
    job_id_a = resp_a.json()["id"]

    # User B (same key, different user)
    token_b = mint_token(sub="user-b@example.com", roles=["user"])
    headers_b = {"Authorization": f"Bearer {token_b}"}

    resp_b = client.post(
        "/v1/jobs",
        json=payload,
        headers={**headers_b, "Idempotency-Key": idem_key},
    )

    assert resp_b.status_code == 202  # Fresh job (key is user-scoped)
    assert resp_b.headers.get("Idempotency-Replayed", "false") == "false"
    job_id_b = resp_b.json()["id"]

    # Different job IDs (user isolation)
    assert job_id_a != job_id_b


def test_idempotency_key_isolated_by_payload(client, user_headers):
    """Same key with different payload creates different jobs (payload is part of key hash)."""
    idem_key = f"same-key-{uuid.uuid4()}"

    # Payload A
    resp_a = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"variant": "A"}},
        headers={**user_headers, "Idempotency-Key": idem_key},
    )

    assert resp_a.status_code == 202
    job_id_a = resp_a.json()["id"]

    # Payload B (same key, different payload)
    resp_b = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"variant": "B"}},
        headers={**user_headers, "Idempotency-Key": idem_key},
    )

    assert resp_b.status_code == 202  # Fresh job (payload hash differs)
    assert resp_b.headers.get("Idempotency-Replayed", "false") == "false"
    job_id_b = resp_b.json()["id"]

    # Different job IDs
    assert job_id_a != job_id_b


# ========== Idempotency TTL expiry (requires override) ==========


@pytest.mark.skipif(
    os.getenv("IDEMPOTENCY_TTL_HOURS", "24") == "24",
    reason="Requires short TTL override (e.g., IDEMPOTENCY_TTL_HOURS=0.0001 for ~0.36s TTL). Skipping in standard runs.",
)
def test_idempotency_key_expires_after_ttl(client, user_headers):
    """
    POST with same Idempotency-Key AFTER TTL expiry creates a NEW job.

    NOTE: This test requires IDEMPOTENCY_TTL_HOURS to be set to a very short value
    (e.g., 0.0001 hours = 0.36 seconds) in the test environment.

    Run with:
        IDEMPOTENCY_TTL_HOURS=0.0001 pytest tests/test_idempotency_window.py::test_idempotency_key_expires_after_ttl -v
    """
    from src.config import settings

    # Verify TTL override is active
    ttl_seconds = settings.IDEMPOTENCY_TTL_HOURS * 3600
    assert ttl_seconds < 5, "Test requires TTL < 5 seconds (set IDEMPOTENCY_TTL_HOURS=0.001)"

    idem_key = f"expiry-test-{uuid.uuid4()}"
    payload = {"type": "demo", "payload": {"test": "expiry"}}

    # First request - creates new job (202)
    resp1 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": idem_key},
    )

    assert resp1.status_code == 202
    job_id_1 = resp1.json()["id"]

    # Wait for TTL to expire (add buffer)
    sleep_duration = ttl_seconds + 1.0
    print(f"Sleeping {sleep_duration}s for TTL expiry...")
    time.sleep(sleep_duration)

    # Second request AFTER TTL - should create NEW job (202)
    resp2 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": idem_key},
    )

    assert resp2.status_code == 202  # Fresh job (key expired)
    assert resp2.headers.get("Idempotency-Replayed", "false") == "false"
    job_id_2 = resp2.json()["id"]

    # Different job IDs (key has expired)
    assert job_id_1 != job_id_2


@pytest.mark.skipif(
    os.getenv("JOB_STORE_BACKEND", "memory") == "memory",
    reason="Memory backend doesn't enforce idempotency TTL expiry. Requires redis backend.",
)
def test_redis_backend_enforces_idempotency_ttl():
    """
    Placeholder test documenting that idempotency TTL enforcement
    is backend-dependent:

    - **Redis backend**: Uses native TTL with automatic expiry
    - **Memory backend**: No automatic expiry (TTL not enforced)

    For production deployments, use Redis backend to guarantee
    idempotency key expiry.
    """
    pass


# ========== Edge cases ==========


def test_idempotency_replay_with_completed_job(client, user_headers):
    """Replay idempotency key for a finished job still returns original job ID."""
    idem_key = f"completed-{uuid.uuid4()}"
    payload = {"type": "demo", "payload": {}}

    # Create job
    resp1 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": idem_key},
    )

    assert resp1.status_code == 202
    job_id_1 = resp1.json()["id"]

    # Let job complete (demo jobs finish quickly)
    time.sleep(0.5)

    # Replay should STILL return same job ID (even if job finished)
    resp2 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": idem_key},
    )

    assert resp2.status_code == 200
    assert resp2.headers["Idempotency-Replayed"] == "true"
    job_id_2 = resp2.json()["id"]

    assert job_id_1 == job_id_2


def test_idempotency_key_case_sensitive(client, user_headers):
    """Idempotency-Key header is case-sensitive for key value."""
    payload = {"type": "demo", "payload": {}}

    # Lowercase key
    resp1 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": "lowercase-key"},
    )

    assert resp1.status_code == 202
    job_id_1 = resp1.json()["id"]

    # Uppercase key (different)
    resp2 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**user_headers, "Idempotency-Key": "LOWERCASE-KEY"},
    )

    assert resp2.status_code == 202  # Fresh job (key is case-sensitive)
    job_id_2 = resp2.json()["id"]

    assert job_id_1 != job_id_2
