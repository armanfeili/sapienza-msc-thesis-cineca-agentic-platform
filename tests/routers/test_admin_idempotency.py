"""
Test admin POST proxy idempotency header passthrough.

Ensures:
- Admin POST passes through Idempotency-Key
- Admin POST passes through Idempotency-Replayed
- Admin POST passes through Location header
- Admin POST preserves 202/200 status codes
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


def test_admin_post_idempotency_key_passthrough(client, admin_headers):
    """Admin POST should pass through Idempotency-Key header."""
    import uuid

    idem_key = str(uuid.uuid4())

    headers = {**admin_headers, "Idempotency-Key": idem_key}
    resp = client.post(
        "/v1/admin/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}},
        headers=headers,
    )

    assert resp.status_code == 202
    assert "Idempotency-Key" in resp.headers
    assert resp.headers["Idempotency-Key"] == idem_key
    assert "Idempotency-Replayed" in resp.headers
    assert resp.headers["Idempotency-Replayed"] == "false"


def test_admin_post_idempotency_replay(client, admin_headers):
    """Admin POST should return 200 with Idempotency-Replayed: true on replay."""
    import uuid

    idem_key = str(uuid.uuid4())
    payload = {"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}}

    headers = {**admin_headers, "Idempotency-Key": idem_key}

    # First request
    resp1 = client.post("/v1/admin/jobs", json=payload, headers=headers)
    assert resp1.status_code == 202
    assert resp1.headers["Idempotency-Replayed"] == "false"
    job_id1 = resp1.json()["id"]

    # Second request with same key
    resp2 = client.post("/v1/admin/jobs", json=payload, headers=headers)
    assert resp2.status_code == 200  # Replay
    assert resp2.headers["Idempotency-Replayed"] == "true"
    assert resp2.headers["Idempotency-Key"] == idem_key
    job_id2 = resp2.json()["id"]

    assert job_id1 == job_id2  # Same job returned


def test_admin_post_location_header(client, admin_headers):
    """Admin POST should include Location header pointing to job status endpoint."""
    import uuid

    resp = client.post(
        "/v1/admin/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )

    assert resp.status_code == 202
    assert "Location" in resp.headers
    job_id = resp.json()["id"]
    assert f"/v1/jobs/{job_id}" in resp.headers["Location"]


def test_admin_post_preserves_status_codes(client, admin_headers):
    """Admin POST should preserve 202 (fresh) vs 200 (replay) status codes."""
    import uuid

    idem_key = str(uuid.uuid4())
    payload = {"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}}

    headers = {**admin_headers, "Idempotency-Key": idem_key}

    # Fresh submission
    resp1 = client.post("/v1/admin/jobs", json=payload, headers=headers)
    assert resp1.status_code == 202

    # Replay
    resp2 = client.post("/v1/admin/jobs", json=payload, headers=headers)
    assert resp2.status_code == 200


def test_admin_post_without_idempotency_key(client, admin_headers):
    """Admin POST works without Idempotency-Key (not echoed back)."""
    import uuid

    resp = client.post(
        "/v1/admin/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )

    assert resp.status_code == 202
    # No Idempotency-Key in response if not provided in request
    assert "Idempotency-Replayed" in resp.headers
    assert resp.headers["Idempotency-Replayed"] == "false"


def test_admin_post_same_as_canonical(client, admin_headers):
    """Admin POST should behave identically to canonical POST for idempotent submits."""
    import uuid

    idem_key = str(uuid.uuid4())
    payload = {"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}}

    headers = {**admin_headers, "Idempotency-Key": idem_key}

    # Submit via canonical endpoint
    resp_canonical = client.post("/v1/jobs", json=payload, headers=headers)
    assert resp_canonical.status_code == 202
    job_id_canonical = resp_canonical.json()["id"]

    # Replay via admin endpoint with same key
    resp_admin = client.post("/v1/admin/jobs", json=payload, headers=headers)
    assert resp_admin.status_code == 200  # Replay
    assert resp_admin.headers["Idempotency-Replayed"] == "true"
    job_id_admin = resp_admin.json()["id"]

    # Should return same job
    assert job_id_canonical == job_id_admin
