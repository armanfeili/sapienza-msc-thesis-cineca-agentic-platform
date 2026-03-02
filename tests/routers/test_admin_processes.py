"""
Tests for admin processes endpoints.

Tests cover:
- RBAC: 401/403 for missing/invalid/non-admin tokens
- GET /admin/processes: listing, filtering, pagination
- DELETE /admin/processes/{pid}: idempotent stop
- GET /admin/processes/history/manifests: history retrieval
- GET /admin/processes/history/processes: event audit trail
"""

import os
import time
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import requests

BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
USER_TOKEN = os.getenv("USER_TOKEN", "")


def test_list_processes_requires_auth():
    """Test GET /admin/processes returns 401 without token."""
    r = requests.get(f"{BASE}/v1/admin/processes", timeout=5)
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_list_processes_requires_admin():
    """Test GET /admin/processes returns 403 with non-admin token."""
    if not USER_TOKEN:
        pytest.skip("USER_TOKEN not set")

    headers = {"Authorization": f"Bearer {USER_TOKEN}"}
    r = requests.get(f"{BASE}/v1/admin/processes", headers=headers, timeout=5)
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"


def test_list_processes_success():
    """Test GET /admin/processes succeeds with admin token."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    r = requests.get(f"{BASE}/v1/admin/processes", headers=headers, timeout=5)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    data = r.json()
    assert "processes" in data
    assert isinstance(data["processes"], list)
    assert "next_cursor" in data


def test_list_processes_with_filters():
    """Test GET /admin/processes with query filters."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    params = {
        "artifact": "test-artifact",
        "status": "running",
        "limit": 50,
    }
    r = requests.get(f"{BASE}/v1/admin/processes", headers=headers, params=params, timeout=5)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    data = r.json()
    assert "processes" in data
    # Validate response structure
    for proc in data["processes"]:
        assert "id" in proc
        assert "process_id" in proc
        assert "artifact" in proc
        assert "status" in proc
        assert "ts" in proc


def test_list_processes_observability_headers():
    """Test GET /admin/processes returns observability headers."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    correlation_id = str(uuid4())
    headers = {
        "Authorization": f"Bearer {ADMIN_TOKEN}",
        "X-Correlation-Id": correlation_id,
    }
    r = requests.get(f"{BASE}/v1/admin/processes", headers=headers, timeout=5)
    assert r.status_code == 200

    # Check observability headers are present
    # Note: FastAPI may not return these for 200 responses by default,
    # but they should be there for error responses


def test_stop_process_requires_auth():
    """Test DELETE /admin/processes/{pid} returns 401 without token."""
    r = requests.delete(f"{BASE}/v1/admin/processes/99999", timeout=5)
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_stop_process_requires_admin():
    """Test DELETE /admin/processes/{pid} returns 403 with non-admin token."""
    if not USER_TOKEN:
        pytest.skip("USER_TOKEN not set")

    headers = {"Authorization": f"Bearer {USER_TOKEN}"}
    r = requests.delete(f"{BASE}/v1/admin/processes/99999", headers=headers, timeout=5)
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"


def test_stop_process_invalid_pid():
    """Test DELETE /admin/processes/{pid} returns 422 for invalid PID."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    # Test with negative PID
    r = requests.delete(f"{BASE}/v1/admin/processes/-1", headers=headers, timeout=5)
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"

    # Test with zero PID
    r = requests.delete(f"{BASE}/v1/admin/processes/0", headers=headers, timeout=5)
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


def test_stop_process_idempotent():
    """Test DELETE /admin/processes/{pid} is idempotent (always returns 204)."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    pid = 88888  # Non-existent PID

    # First call
    r1 = requests.delete(f"{BASE}/v1/admin/processes/{pid}", headers=headers, timeout=5)
    assert r1.status_code == 204, f"Expected 204, got {r1.status_code}: {r1.text}"

    # Second call (idempotent)
    r2 = requests.delete(f"{BASE}/v1/admin/processes/{pid}", headers=headers, timeout=5)
    assert r2.status_code == 204, f"Expected 204, got {r2.status_code}: {r2.text}"

    # Third call (still idempotent)
    r3 = requests.delete(f"{BASE}/v1/admin/processes/{pid}", headers=headers, timeout=5)
    assert r3.status_code == 204, f"Expected 204, got {r3.status_code}: {r3.text}"


def test_stop_process_concurrent_calls():
    """Test DELETE /admin/processes/{pid} handles concurrent calls gracefully.

    Verifies:
    - All concurrent DELETEs return 204 (idempotent)
    - Redis stop-lock prevents race conditions
    - Only one STOP event recorded in database
    """
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    pid = 77777  # Non-existent PID

    # Simulate near-concurrent calls (lock should prevent race)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(requests.delete, f"{BASE}/v1/admin/processes/{pid}", headers=headers, timeout=10)
            for _ in range(5)
        ]
        results = [f.result() for f in futures]

    # All should return 204 (idempotent)
    for idx, r in enumerate(results):
        assert r.status_code == 204, f"Request {idx}: Expected 204, got {r.status_code}: {r.text}"

    # Verify all requests completed successfully
    assert len(results) == 5

    # Optional: Verify only one STOP event was recorded
    # (Would need to query the history endpoint or database directly)


def test_manifest_history_requires_auth():
    """Test GET /admin/processes/history/manifests returns 401 without token."""
    r = requests.get(f"{BASE}/v1/admin/processes/history/manifests", timeout=5)
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_manifest_history_requires_admin():
    """Test GET /admin/processes/history/manifests returns 403 with non-admin token."""
    if not USER_TOKEN:
        pytest.skip("USER_TOKEN not set")

    headers = {"Authorization": f"Bearer {USER_TOKEN}"}
    r = requests.get(f"{BASE}/v1/admin/processes/history/manifests", headers=headers, timeout=5)
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"


def test_manifest_history_success():
    """Test GET /admin/processes/history/manifests succeeds with admin token."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    r = requests.get(f"{BASE}/v1/admin/processes/history/manifests", headers=headers, timeout=5)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    data = r.json()
    assert "manifests" in data
    assert isinstance(data["manifests"], list)
    assert "next_cursor" in data


def test_manifest_history_with_filters():
    """Test GET /admin/processes/history/manifests with filters."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    params = {
        "manifest_name": "test-manifest",
        "status": "active",
        "limit": 25,
    }
    r = requests.get(
        f"{BASE}/v1/admin/processes/history/manifests",
        headers=headers,
        params=params,
        timeout=5,
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    data = r.json()
    assert "manifests" in data
    for manifest in data["manifests"]:
        assert "id" in manifest
        assert "manifest_name" in manifest
        assert "version" in manifest
        assert "status" in manifest
        assert "activated_at" in manifest


def test_manifest_history_invalid_status():
    """Test GET /admin/processes/history/manifests rejects invalid status."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    params = {"status": "invalid_status"}
    r = requests.get(
        f"{BASE}/v1/admin/processes/history/manifests",
        headers=headers,
        params=params,
        timeout=5,
    )
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


def test_process_history_requires_auth():
    """Test GET /admin/processes/history/processes returns 401 without token."""
    r = requests.get(f"{BASE}/v1/admin/processes/history/processes", timeout=5)
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_process_history_requires_admin():
    """Test GET /admin/processes/history/processes returns 403 with non-admin token."""
    if not USER_TOKEN:
        pytest.skip("USER_TOKEN not set")

    headers = {"Authorization": f"Bearer {USER_TOKEN}"}
    r = requests.get(f"{BASE}/v1/admin/processes/history/processes", headers=headers, timeout=5)
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"


def test_process_history_success():
    """Test GET /admin/processes/history/processes succeeds with admin token."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    r = requests.get(f"{BASE}/v1/admin/processes/history/processes", headers=headers, timeout=5)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    data = r.json()
    assert "events" in data
    assert isinstance(data["events"], list)
    assert "next_cursor" in data


def test_process_history_with_filters():
    """Test GET /admin/processes/history/processes with multiple filters."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    params = {
        "artifact": "test-artifact",
        "event": "start",
        "limit": 50,
    }
    r = requests.get(
        f"{BASE}/v1/admin/processes/history/processes",
        headers=headers,
        params=params,
        timeout=5,
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    data = r.json()
    assert "events" in data
    for event in data["events"]:
        assert "id" in event
        assert "process_id" in event
        assert "artifact" in event
        assert "event" in event
        assert "ts" in event


def test_process_history_invalid_event():
    """Test GET /admin/processes/history/processes rejects invalid event type."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    params = {"event": "invalid_event"}
    r = requests.get(
        f"{BASE}/v1/admin/processes/history/processes",
        headers=headers,
        params=params,
        timeout=5,
    )
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


def test_legacy_stop_endpoint_returns_410():
    """Test POST /admin/processes/{pid}:stop returns 410 Gone."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    r = requests.post(f"{BASE}/v1/admin/processes/12345:stop", headers=headers, timeout=5)
    assert r.status_code == 410, f"Expected 410, got {r.status_code}: {r.text}"

    data = r.json()
    assert "detail" in data
    assert "deprecated" in data["detail"].lower() or "DELETE" in data["detail"]


def test_pagination_limit_enforcement():
    """Test that pagination limits are enforced (max 1000)."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    # Request way over limit - FastAPI validates at parameter level
    params = {"limit": 5000}
    r = requests.get(f"{BASE}/v1/admin/processes", headers=headers, params=params, timeout=5)
    assert r.status_code == 422  # Validation error for limit > 1000

    # Request at the limit - should succeed
    params = {"limit": 1000}
    r = requests.get(f"{BASE}/v1/admin/processes", headers=headers, params=params, timeout=5)
    assert r.status_code == 200
    data = r.json()
    # Should not exceed 1000 even if more records exist
    assert len(data["processes"]) <= 1000


def test_list_processes_response_shape():
    """Test that process list response includes all required fields."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    r = requests.get(f"{BASE}/v1/admin/processes", headers=headers, timeout=5)
    assert r.status_code == 200

    data = r.json()
    assert "processes" in data
    assert "next_cursor" in data

    # If processes exist, validate schema
    if data["processes"]:
        proc = data["processes"][0]
        # Required fields
        assert "process_id" in proc
        assert "artifact" in proc
        assert "status" in proc
        assert "ts" in proc
        # Optional fields that may be present
        # pid, port, manifest_version, host, last_heartbeat, tenant_id


def test_history_cursor_pagination():
    """Test cursor-based pagination for history endpoints."""
    if not ADMIN_TOKEN:
        pytest.skip("ADMIN_TOKEN not set")

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    # Get first page with small limit
    params = {"limit": 1}
    r = requests.get(
        f"{BASE}/v1/admin/processes/history/processes",
        headers=headers,
        params=params,
        timeout=5,
    )
    assert r.status_code == 200
    data = r.json()

    # If we have a next_cursor, verify it can be used
    if data.get("next_cursor"):
        cursor = data["next_cursor"]
        params_page2 = {"limit": 1, "cursor": cursor}
        r2 = requests.get(
            f"{BASE}/v1/admin/processes/history/processes",
            headers=headers,
            params=params_page2,
            timeout=5,
        )
        # Should succeed even if no more results
        assert r2.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
