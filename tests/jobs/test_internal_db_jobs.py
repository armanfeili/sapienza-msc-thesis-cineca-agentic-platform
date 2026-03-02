"""
Comprehensive tests for DB jobs feature (Phase 3)
Tests: feature flag, job creation, idempotency, cancel, auth, progress tracking
"""
import os
import time
import uuid
import requests
import pytest
from typing import Optional


BASE = os.environ.get("BASE_URL", "http://localhost:8000")

# Test tokens - should be provided via environment variables
MACHINE_TOKEN = os.environ.get("MACHINE_TOKEN", "")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
USER_TOKEN = os.environ.get("USER_TOKEN", "")


class TestDBJobsFeatureFlag:
    """Test feature flag behavior (INTERNAL_DB_UTILS_ENABLED)"""

    def test_501_when_feature_disabled(self):
        """Should return 501 when INTERNAL_DB_UTILS_ENABLED=false"""
        # Note: This test assumes feature is disabled by default
        # Skip if feature is enabled in test environment
        if os.environ.get("INTERNAL_DB_UTILS_ENABLED", "false").lower() == "true":
            pytest.skip("Feature is enabled in test environment")

        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}", "Content-Type": "application/json"}

        body = {"type": "create", "wipe": True, "users": 10}
        r = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)

        assert r.status_code == 501, f"Expected 501, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["status"] == 501
        assert data["title"] == "Not Implemented"
        assert "unavailable" in data["detail"].lower()


class TestDBJobsCreation:
    """Test job creation with 202 Accepted"""

    def test_create_job_returns_202(self):
        """Should return 202 with job_id and Location header"""
        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}", "Content-Type": "application/json"}

        body = {"type": "create", "wipe": True, "users": 50}
        r = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)

        # Skip if 501 (feature disabled)
        if r.status_code == 501:
            pytest.skip("DB utilities unavailable (INTERNAL_DB_UTILS_ENABLED=false)")

        assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"

        data = r.json()
        assert data["ok"] is True
        assert "job_id" in data

        # Verify Location header
        location = r.headers.get("Location")
        assert location, "Missing Location header"
        assert data["job_id"] in location

        # Verify correlation ID headers
        assert "X-Correlation-Id" in r.headers
        assert "X-Request-Id" in r.headers

    def test_populate_job_returns_202(self):
        """Should create populate job successfully"""
        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}", "Content-Type": "application/json"}

        body = {"type": "populate", "users": 100}
        r = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)

        if r.status_code == 501:
            pytest.skip("DB utilities unavailable")

        assert r.status_code == 202
        data = r.json()
        assert data["ok"] is True
        assert "job_id" in data

    def test_invalid_job_type_returns_422(self):
        """Should reject invalid job type"""
        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}", "Content-Type": "application/json"}

        body = {"type": "invalid", "wipe": True}
        r = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)

        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


class TestDBJobsIdempotency:
    """Test idempotency with Idempotency-Key header"""

    def test_idempotency_key_prevents_duplicate_jobs(self):
        """Should return same job_id for duplicate requests with same idempotency key"""
        headers = {
            "Authorization": f"Bearer {MACHINE_TOKEN}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"test-{uuid.uuid4()}",
        }

        body = {"type": "populate", "users": 50}

        # First request
        r1 = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)
        if r1.status_code == 501:
            pytest.skip("DB utilities unavailable")

        assert r1.status_code == 202
        job_id_1 = r1.json()["job_id"]
        assert "X-Idempotency-Replayed" not in r1.headers

        # Second request with same idempotency key
        r2 = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)
        assert r2.status_code == 202
        job_id_2 = r2.json()["job_id"]

        # Should return same job_id
        assert job_id_1 == job_id_2, "Idempotency key did not prevent duplicate job creation"

        # Should include X-Idempotency-Replayed header
        assert (
            r2.headers.get("X-Idempotency-Replayed") == "true"
        ), "Missing X-Idempotency-Replayed header on replayed request"

    def test_different_idempotency_keys_create_different_jobs(self):
        """Different idempotency keys should create different jobs"""
        body = {"type": "populate", "users": 30}

        headers1 = {
            "Authorization": f"Bearer {MACHINE_TOKEN}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"test-{uuid.uuid4()}",
        }

        headers2 = {
            "Authorization": f"Bearer {MACHINE_TOKEN}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"test-{uuid.uuid4()}",
        }

        r1 = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers1, timeout=10)
        if r1.status_code == 501:
            pytest.skip("DB utilities unavailable")

        r2 = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers2, timeout=10)

        assert r1.status_code == 202
        assert r2.status_code == 202

        job_id_1 = r1.json()["job_id"]
        job_id_2 = r2.json()["job_id"]

        assert job_id_1 != job_id_2, "Different idempotency keys created same job"


class TestDBJobsStatus:
    """Test GET /jobs/{job_id} with real-time progress"""

    def _create_job(self) -> Optional[str]:
        """Helper: create a job and return job_id"""
        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}", "Content-Type": "application/json"}
        body = {"type": "populate", "users": 20}
        r = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)

        if r.status_code == 501:
            return None

        assert r.status_code == 202
        return r.json()["job_id"]

    def test_get_status_returns_job_details(self):
        """Should return job status with progress"""
        job_id = self._create_job()
        if not job_id:
            pytest.skip("DB utilities unavailable")

        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}"}
        r = requests.get(f"{BASE}/v1/internal/db/jobs/{job_id}", headers=headers, timeout=10)

        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

        data = r.json()
        assert data["job_id"] == job_id
        assert "state" in data
        assert data["state"] in ["queued", "running", "finished", "failed", "cancelled"]
        assert "progress" in data
        assert 0.0 <= data["progress"] <= 1.0
        assert "action" in data
        assert "params" in data

    def test_get_nonexistent_job_returns_404(self):
        """Should return 404 for non-existent job"""
        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}"}
        fake_job_id = str(uuid.uuid4())
        r = requests.get(f"{BASE}/v1/internal/db/jobs/{fake_job_id}", headers=headers, timeout=10)

        assert r.status_code == 404
        data = r.json()
        assert data["status"] == 404
        assert data["title"] == "Not Found"

    def test_progress_tracking(self):
        """Should track real-time progress for running jobs"""
        job_id = self._create_job()
        if not job_id:
            pytest.skip("DB utilities unavailable")

        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}"}

        # Poll for progress updates (max 10 seconds)
        max_polls = 20
        poll_interval = 0.5
        states_seen = set()

        for _ in range(max_polls):
            r = requests.get(f"{BASE}/v1/internal/db/jobs/{job_id}", headers=headers, timeout=5)
            assert r.status_code == 200

            data = r.json()
            states_seen.add(data["state"])

            # If job finished/failed, stop polling
            if data["state"] in ["finished", "failed", "cancelled"]:
                break

            time.sleep(poll_interval)

        # Should have seen at least "queued" or "running"
        assert len(states_seen) > 0, "No job states observed"
        assert (
            "queued" in states_seen or "running" in states_seen
        ), f"Expected queued/running states, saw: {states_seen}"


class TestDBJobsCancellation:
    """Test DELETE /jobs/{job_id} idempotent cancellation"""

    def _create_job(self) -> Optional[str]:
        """Helper: create a job and return job_id"""
        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}", "Content-Type": "application/json"}
        body = {"type": "populate", "users": 100}  # Large job to ensure it's cancellable
        r = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)

        if r.status_code == 501:
            return None

        assert r.status_code == 202
        return r.json()["job_id"]

    def test_cancel_job_returns_204(self):
        """Should return 204 when cancelling job"""
        job_id = self._create_job()
        if not job_id:
            pytest.skip("DB utilities unavailable")

        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}"}
        r = requests.delete(f"{BASE}/v1/internal/db/jobs/{job_id}", headers=headers, timeout=10)

        assert r.status_code == 204, f"Expected 204, got {r.status_code}: {r.text}"
        assert r.text == "", "204 should have no body"

    def test_cancel_idempotency(self):
        """Should return 204 on repeated cancel (idempotent)"""
        job_id = self._create_job()
        if not job_id:
            pytest.skip("DB utilities unavailable")

        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}"}

        # First cancel
        r1 = requests.delete(f"{BASE}/v1/internal/db/jobs/{job_id}", headers=headers, timeout=10)
        assert r1.status_code == 204

        # Second cancel (should still be 204)
        r2 = requests.delete(f"{BASE}/v1/internal/db/jobs/{job_id}", headers=headers, timeout=10)
        assert r2.status_code == 204

        # Third cancel (should still be 204)
        r3 = requests.delete(f"{BASE}/v1/internal/db/jobs/{job_id}", headers=headers, timeout=10)
        assert r3.status_code == 204

    def test_cancel_nonexistent_job_returns_204(self):
        """Should return 204 even for non-existent job (idempotent)"""
        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}"}
        fake_job_id = str(uuid.uuid4())
        r = requests.delete(f"{BASE}/v1/internal/db/jobs/{fake_job_id}", headers=headers, timeout=10)

        assert r.status_code == 204, "Cancel should be idempotent even for non-existent jobs"


class TestDBJobsAuthentication:
    """Test authentication matrix (M2M, admin, user tokens)"""

    def test_machine_token_can_create_jobs(self):
        """M2M token (internal:all scope) should succeed"""
        if not MACHINE_TOKEN:
            pytest.skip("MACHINE_TOKEN not provided")

        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}", "Content-Type": "application/json"}
        body = {"type": "populate", "users": 10}
        r = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)

        assert r.status_code in [202, 501], f"M2M token should succeed or return 501, got {r.status_code}: {r.text}"

    def test_admin_token_returns_403(self):
        """Admin token (admin:all scope) should be rejected"""
        if not ADMIN_TOKEN:
            pytest.skip("ADMIN_TOKEN not provided")

        headers = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}
        body = {"type": "populate", "users": 10}
        r = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)

        assert r.status_code == 403, f"Admin token should be rejected, got {r.status_code}: {r.text}"

    def test_user_token_returns_403(self):
        """User token (user:me scope) should be rejected"""
        if not USER_TOKEN:
            pytest.skip("USER_TOKEN not provided")

        headers = {"Authorization": f"Bearer {USER_TOKEN}", "Content-Type": "application/json"}
        body = {"type": "populate", "users": 10}
        r = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)

        assert r.status_code == 403, f"User token should be rejected, got {r.status_code}: {r.text}"

    def test_no_token_returns_401(self):
        """No token should return 401"""
        headers = {"Content-Type": "application/json"}
        body = {"type": "populate", "users": 10}
        r = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)

        assert r.status_code == 401, f"No token should return 401, got {r.status_code}: {r.text}"


class TestDBJobsRFC7807ErrorFormat:
    """Test RFC 7807 error response format"""

    def test_404_error_format(self):
        """404 errors should follow RFC 7807 format"""
        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}"}
        fake_job_id = str(uuid.uuid4())
        r = requests.get(f"{BASE}/v1/internal/db/jobs/{fake_job_id}", headers=headers, timeout=10)

        assert r.status_code == 404
        data = r.json()

        # RFC 7807 required fields
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data
        assert "instance" in data

        # Additional fields
        assert "correlation_id" in data

        assert data["status"] == 404
        assert data["title"] == "Not Found"

    def test_501_error_format(self):
        """501 errors should follow RFC 7807 format"""
        if os.environ.get("INTERNAL_DB_UTILS_ENABLED", "false").lower() == "true":
            pytest.skip("Feature is enabled")

        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}", "Content-Type": "application/json"}
        body = {"type": "create", "wipe": True}
        r = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers, timeout=10)

        assert r.status_code == 501
        data = r.json()

        # RFC 7807 format
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data
        assert "instance" in data
        assert "correlation_id" in data

        assert data["status"] == 501
        assert data["title"] == "Not Implemented"


class TestDBJobsEndToEnd:
    """End-to-end integration tests"""

    def test_full_job_lifecycle(self):
        """Test complete job lifecycle: create → poll → complete/cancel"""
        if not MACHINE_TOKEN:
            pytest.skip("MACHINE_TOKEN not provided")

        headers = {"Authorization": f"Bearer {MACHINE_TOKEN}", "Content-Type": "application/json"}

        # 1. Create job with idempotency key
        idempotency_key = f"e2e-test-{uuid.uuid4()}"
        headers_with_idem = {**headers, "Idempotency-Key": idempotency_key}
        body = {"type": "populate", "users": 50}

        r1 = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers_with_idem, timeout=10)
        if r1.status_code == 501:
            pytest.skip("DB utilities unavailable")

        assert r1.status_code == 202
        job_id = r1.json()["job_id"]
        location = r1.headers.get("Location")

        # 2. Verify idempotency (replay request)
        r2 = requests.post(f"{BASE}/v1/internal/db/jobs", json=body, headers=headers_with_idem, timeout=10)
        assert r2.status_code == 202
        assert r2.json()["job_id"] == job_id
        assert r2.headers.get("X-Idempotency-Replayed") == "true"

        # 3. Poll status
        r3 = requests.get(f"{BASE}{location}", headers=headers, timeout=10)
        assert r3.status_code == 200
        status_data = r3.json()
        assert status_data["job_id"] == job_id
        assert status_data["state"] in ["queued", "running", "finished", "failed", "cancelled"]

        # 4. Cancel job (idempotent)
        r4 = requests.delete(f"{BASE}{location}", headers=headers, timeout=10)
        assert r4.status_code == 204

        # 5. Verify cancel idempotency
        r5 = requests.delete(f"{BASE}{location}", headers=headers, timeout=10)
        assert r5.status_code == 204

        # 6. Check final status (should show cancelled if caught in time)
        time.sleep(1)
        r6 = requests.get(f"{BASE}{location}", headers=headers, timeout=10)
        assert r6.status_code == 200
        final_status = r6.json()
        assert final_status["state"] in [
            "cancelled",
            "finished",
        ], f"Expected cancelled or finished, got {final_status['state']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
