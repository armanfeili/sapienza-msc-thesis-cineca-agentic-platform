"""
Test ETag and caching behavior across GET endpoints.

Ensures:
- Vary: Authorization header present on all GET responses
- Weak ETags are stable for identical content
- If-None-Match returns 304 Not Modified with matching ETag
- ETags work consistently across memory and Redis backends
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


def test_get_job_has_vary_authorization(client, admin_headers):
    """GET /v1/jobs/{job_id} should include Vary: Authorization header."""
    import uuid

    # Create a job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    # GET job
    get_resp = client.get(f"/v1/jobs/{job_id}", headers=admin_headers)
    assert get_resp.status_code == 200
    assert "Vary" in get_resp.headers
    assert get_resp.headers["Vary"] == "Authorization"


def test_get_job_etag_304(client, admin_headers):
    """GET /v1/jobs/{job_id} with If-None-Match should return 304 when ETag matches."""
    import uuid

    # Create a job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    # First GET to obtain ETag
    get_resp1 = client.get(f"/v1/jobs/{job_id}", headers=admin_headers)
    assert get_resp1.status_code == 200
    assert "ETag" in get_resp1.headers
    etag = get_resp1.headers["ETag"]
    assert etag.startswith('W/"')  # Weak ETag

    # Second GET with If-None-Match
    headers_with_etag = {**admin_headers, "If-None-Match": etag}
    get_resp2 = client.get(f"/v1/jobs/{job_id}", headers=headers_with_etag)
    assert get_resp2.status_code == 304
    assert "ETag" in get_resp2.headers
    assert get_resp2.headers["ETag"] == etag  # Stable ETag
    assert "Vary" in get_resp2.headers
    assert get_resp2.headers["Vary"] == "Authorization"


def test_etag_stable_across_requests(client, admin_headers):
    """ETag should be stable for identical job state."""
    import uuid

    # Create a job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    # Get ETag twice without modifications
    get_resp1 = client.get(f"/v1/jobs/{job_id}", headers=admin_headers)
    etag1 = get_resp1.headers.get("ETag")

    get_resp2 = client.get(f"/v1/jobs/{job_id}", headers=admin_headers)
    etag2 = get_resp2.headers.get("ETag")

    assert etag1 == etag2, "ETag should be stable for identical content"


def test_admin_jobs_list_has_vary_authorization(client, admin_headers):
    """GET /v1/admin/jobs should include Vary: Authorization header."""
    resp = client.get("/v1/admin/jobs", headers=admin_headers)
    assert resp.status_code == 200
    assert "Vary" in resp.headers
    assert resp.headers["Vary"] == "Authorization"


def test_admin_jobs_list_etag_304(client, admin_headers):
    """GET /v1/admin/jobs with If-None-Match should return 304 when ETag matches."""
    import uuid

    # Create a job to ensure non-empty list
    client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )

    # First GET to obtain ETag
    resp1 = client.get("/v1/admin/jobs", headers=admin_headers)
    assert resp1.status_code == 200
    assert "ETag" in resp1.headers
    etag = resp1.headers["ETag"]

    # Second GET with If-None-Match (within short time window, list shouldn't change)
    headers_with_etag = {**admin_headers, "If-None-Match": etag}
    resp2 = client.get("/v1/admin/jobs", headers=headers_with_etag)
    assert resp2.status_code == 304
    assert "ETag" in resp2.headers
    assert "Vary" in resp2.headers
    assert resp2.headers["Vary"] == "Authorization"


def test_etag_is_weak(client, admin_headers):
    """All ETags should be weak (prefixed with W/)."""
    import uuid

    # Create a job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    # Check job detail ETag
    job_resp = client.get(f"/v1/jobs/{job_id}", headers=admin_headers)
    assert job_resp.headers["ETag"].startswith('W/"')

    # Check admin jobs list ETag
    list_resp = client.get("/v1/admin/jobs", headers=admin_headers)
    assert list_resp.headers["ETag"].startswith('W/"')


def test_cache_control_headers(client, admin_headers):
    """Verify Cache-Control headers are appropriate for each endpoint."""
    import uuid

    # Create a job
    resp = client.post(
        "/v1/jobs",
        json={"type": "demo", "payload": {"duration_ms": 100, "test_id": str(uuid.uuid4())}},
        headers=admin_headers,
    )
    job_id = resp.json()["id"]

    # GET job should have short-lived cache
    job_resp = client.get(f"/v1/jobs/{job_id}", headers=admin_headers)
    assert "Cache-Control" in job_resp.headers
    assert "private" in job_resp.headers["Cache-Control"]
    assert "max-age=15" in job_resp.headers["Cache-Control"]

    # 304 response should also have cache headers
    headers_with_etag = {**admin_headers, "If-None-Match": job_resp.headers["ETag"]}
    resp_304 = client.get(f"/v1/jobs/{job_id}", headers=headers_with_etag)
    assert resp_304.status_code == 304
    assert "Cache-Control" in resp_304.headers
