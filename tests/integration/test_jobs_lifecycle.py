"""
Jobs Lifecycle Integration Tests

Verifies job creation, idempotency, event streaming, and cancellation.
Tests async job workflows and status tracking.

Acceptance Checklist Item: #7
"""
import pytest
import time


class TestJobsLifecycle:
    """Test job lifecycle operations."""

    def test_create_job(self, client, bearer_headers):
        """Should create a new job successfully."""
        response = client.post(
            "/v1/jobs", headers=bearer_headers, json={"job_type": "analysis", "parameters": {"target": "test_data"}}
        )
        assert response.status_code == 201

        job = response.json()
        assert job.get("job_id"), "Job should have job_id"
        assert job.get("status"), "Job should have status"
        assert job.get("created_at"), "Job should have created_at timestamp"

    def test_job_idempotency(self, client, bearer_headers):
        """Should handle duplicate job creation with idempotency key."""
        idempotency_key = f"test-job-{int(time.time())}"

        # Create job with idempotency key
        response1 = client.post(
            "/v1/jobs",
            headers={**bearer_headers, "Idempotency-Key": idempotency_key},
            json={"job_type": "test", "parameters": {}},
        )
        assert response1.status_code == 201
        job1 = response1.json()

        # Create same job again with same idempotency key
        response2 = client.post(
            "/v1/jobs",
            headers={**bearer_headers, "Idempotency-Key": idempotency_key},
            json={"job_type": "test", "parameters": {}},
        )
        assert response2.status_code in [200, 201]
        job2 = response2.json()

        # Should return same job
        assert job1["job_id"] == job2["job_id"], "Idempotent request should return same job_id"

    def test_get_job_status(self, client, bearer_headers):
        """Should retrieve job status."""
        # Create job
        create_response = client.post("/v1/jobs", headers=bearer_headers, json={"job_type": "test", "parameters": {}})
        job_id = create_response.json()["job_id"]

        # Get status
        status_response = client.get(f"/v1/jobs/{job_id}", headers=bearer_headers)
        assert status_response.status_code == 200

        job = status_response.json()
        assert job["job_id"] == job_id
        assert job.get("status") in ["pending", "running", "completed", "failed", "cancelled"]

    def test_job_events_streaming(self, client, bearer_headers):
        """Should stream job events."""
        # Create job
        create_response = client.post("/v1/jobs", headers=bearer_headers, json={"job_type": "test", "parameters": {}})
        job_id = create_response.json()["job_id"]

        # Get events (may be SSE stream or polling endpoint)
        events_response = client.get(f"/v1/jobs/{job_id}/events", headers=bearer_headers)

        # Accept both SSE (200) and regular JSON (200)
        assert events_response.status_code == 200, "Events endpoint should be accessible"

    def test_cancel_job(self, client, bearer_headers):
        """Should cancel a running job."""
        # Create job
        create_response = client.post(
            "/v1/jobs", headers=bearer_headers, json={"job_type": "long_running_test", "parameters": {}}
        )
        job_id = create_response.json()["job_id"]

        # Cancel job
        cancel_response = client.post(f"/v1/jobs/{job_id}/cancel", headers=bearer_headers)
        assert cancel_response.status_code in [200, 204]

        # Verify cancelled
        status_response = client.get(f"/v1/jobs/{job_id}", headers=bearer_headers)
        job = status_response.json()
        assert job["status"] in ["cancelled", "cancelling"], f"Job should be cancelled, got: {job['status']}"

    def test_list_user_jobs(self, client, bearer_headers):
        """Should list user's jobs."""
        response = client.get("/v1/jobs", headers=bearer_headers)
        assert response.status_code == 200

        jobs = response.json()
        assert isinstance(jobs, list), "Jobs should be a list"
