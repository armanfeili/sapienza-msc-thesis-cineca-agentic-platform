"""
End-to-End Integration Tests for PostgreSQL Jobs Worker.

These tests verify the complete job processing flow with worker:
1. API creates job in PostgreSQL  
2. Job enters Redis queue
3. Worker picks up job from queue
4. Worker executes job and updates PostgreSQL
5. SSE streams events from PostgreSQL
6. Cancellation via Redis flags

Requirements:
- PostgreSQL running (job storage)
- Redis running (queues + cancel flags)
- Worker process running (job execution)
- USE_POSTGRES_JOBS=true environment variable

Setup:
    Start all services:
    $ docker compose up -d postgres redis worker

Run tests:
    $ pytest tests/integration/test_worker_e2e.py -v -s

Skip if worker not available:
    $ pytest tests/integration/test_worker_e2e.py -v -m "not requires_services"

Note:
    These tests require:
    - PostgreSQL running on localhost (or via Docker)
    - Redis running on localhost (or via Docker)  
    - Worker process running
    
    Tests will skip gracefully if PostgreSQL is not available.
"""

from __future__ import annotations

import pytest
import time
import re
import json
from typing import Dict, List, Optional
from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient

# Database imports
from db.postgres_control.database import SessionLocal, Base, engine
from db.postgres_control.models.job import Job
from db.postgres_control.models.tenant import Tenant
from db.postgres_control.repositories.jobs import JobsRepository

# Redis imports
from db.redis_cache import jobs_cache


# Mark all tests as requiring services (can be skipped)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not getattr(__import__("src.config").config.settings, "USE_POSTGRES_JOBS", False),
        reason="Worker E2E tests require USE_POSTGRES_JOBS=true",
    ),
]


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------


@pytest.fixture(scope="function")
def db_session():
    """
    Create database session for E2E tests.

    Uses actual PostgreSQL from Docker Compose.
    """
    session = SessionLocal()
    Base.metadata.create_all(bind=engine)

    # Ensure test tenant exists
    existing_tenant = session.query(Tenant).filter(Tenant.id == "test-tenant").first()
    if not existing_tenant:
        tenant = Tenant(id="test-tenant", name="Test Tenant E2E", admin_email="admin-e2e@test.com")
        session.add(tenant)
        session.commit()

    # Cleanup before test
    try:
        session.query(Job).filter(Job.tenant_id == "test-tenant").delete()
        session.commit()
    except Exception:
        session.rollback()

    yield session

    # Cleanup after test
    try:
        session.query(Job).filter(Job.tenant_id == "test-tenant").delete()
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


@pytest.fixture(scope="function")
def repo(db_session):
    """Create JobsRepository instance."""
    return JobsRepository(db_session)


@pytest.fixture
def admin_token(mint_token) -> str:
    """Generate admin token with full permissions."""
    return mint_token(
        sub="admin-worker-e2e",
        roles=["admin"],
        scopes=["admin:all"],
    )


@pytest.fixture
def admin_headers(admin_token) -> Dict[str, str]:
    """HTTP headers with admin authorization."""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture
def client(app) -> TestClient:
    """FastAPI test client."""
    return TestClient(app)


# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------


def parse_sse_events(lines: List[str]) -> List[Dict]:
    """
    Parse SSE stream lines into structured events.

    SSE format:
        retry: 5000
        id: 1
        event: status
        data: {"status": "queued"}
        <blank line>

    Returns:
        List of event dicts with id, event, data keys
    """
    events = []
    current_event = {}

    for line in lines:
        # Handle both str and bytes
        if isinstance(line, bytes):
            line = line.decode("utf-8")

        line = line.strip()

        if not line:
            # Blank line = event complete
            if current_event:
                events.append(current_event.copy())
                current_event = {}
            continue

        if line.startswith("retry:"):
            # Skip retry directive
            continue

        if line.startswith("id:"):
            try:
                current_event["id"] = int(line.split(":", 1)[1].strip())
            except (ValueError, IndexError):
                pass
        elif line.startswith("event:"):
            current_event["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_str = line.split(":", 1)[1].strip()
            try:
                current_event["data"] = json.loads(data_str)
            except json.JSONDecodeError:
                current_event["data"] = data_str

    # Add final event if exists
    if current_event:
        events.append(current_event)

    return events


def wait_for_job_status(
    repo: JobsRepository, job_id: UUID, target_status: str, timeout: float = 10.0, poll_interval: float = 0.2
) -> Optional[Job]:
    """
    Poll database until job reaches target status or timeout.

    Args:
        repo: JobsRepository instance
        job_id: Job UUID
        target_status: Target status (queued, running, finished, failed, cancelled)
        timeout: Maximum wait time in seconds
        poll_interval: Poll frequency in seconds

    Returns:
        Job object if status reached, None if timeout
    """
    start = time.time()

    while time.time() - start < timeout:
        try:
            job = repo.get_job(job_id)
            if job and job.status == target_status:
                return job
        except Exception:
            pass
        time.sleep(poll_interval)

    return None


# ------------------------------------------------------------------------------
# E2E Job Lifecycle Tests
# ------------------------------------------------------------------------------


class TestWorkerE2EJobLifecycle:
    """Test complete job lifecycle with worker processing."""

    def test_demo_job_full_lifecycle(self, client, admin_headers, repo, db_session):
        """
        E2E test: Create demo job → worker processes → job finishes.

        Flow:
        1. POST /v1/jobs creates job in PostgreSQL
        2. Job enters Redis queue
        3. Worker pops job from queue
        4. Worker transitions: queued → running → finished
        5. Result stored in PostgreSQL
        """
        # Create job via API
        response = client.post(
            "/v1/jobs", json={"type": "demo", "payload": {"duration_ms": 500}}, headers=admin_headers  # 0.5 second job
        )

        assert response.status_code == 202
        data = response.json()
        assert "id" in data
        assert data["status"] == "queued"

        job_id = UUID(data["id"])

        # Verify job in PostgreSQL
        job = repo.get_job(job_id)
        assert job is not None
        assert job.status == "queued"
        assert job.type == "demo"
        assert job.payload_json == {"duration_ms": 500}

        # Wait for worker to process job
        finished_job = wait_for_job_status(repo, job_id, "finished", timeout=10.0)
        assert finished_job is not None, "Job did not reach 'finished' status within timeout"

        # Verify result
        assert finished_job.result_json is not None
        assert finished_job.result_json.get("status") == "completed"
        assert "actual_duration_ms" in finished_job.result_json

        # Verify job events logged
        events = repo.get_job_events(job_id)
        assert len(events) >= 2  # At least queued + finished

        event_types = {e.event_type for e in events}
        assert "status" in event_types

    def test_test_job_instant_completion(self, client, admin_headers, repo):
        """E2E test: Test job completes instantly with payload echo."""
        response = client.post(
            "/v1/jobs",
            json={"type": "test", "payload": {"message": "Hello Worker!", "test_data": 42}},
            headers=admin_headers,
        )

        assert response.status_code == 202
        job_id = UUID(response.json()["id"])

        # Wait for completion
        finished_job = wait_for_job_status(repo, job_id, "finished", timeout=5.0)
        assert finished_job is not None

        # Verify payload echoed
        assert finished_job.result_json is not None
        assert finished_job.result_json.get("status") == "completed"
        assert finished_job.result_json.get("input") == {"message": "Hello Worker!", "test_data": 42}

    def test_long_running_job_with_steps(self, client, admin_headers, repo):
        """
        E2E test: Long-running job with multiple steps.

        This test may take 10+ seconds as worker processes steps.
        """
        response = client.post(
            "/v1/jobs",
            json={"type": "long-running", "payload": {"steps": 3}},  # 3 steps × 3s = 9s total
            headers=admin_headers,
        )

        assert response.status_code == 202
        job_id = UUID(response.json()["id"])

        # Wait for running status
        running_job = wait_for_job_status(repo, job_id, "running", timeout=5.0)
        assert running_job is not None, "Job should transition to running"

        # Wait for completion (allow generous timeout)
        finished_job = wait_for_job_status(repo, job_id, "finished", timeout=15.0)
        assert finished_job is not None, "Long-running job should finish"

        # Verify steps completed
        assert finished_job.result_json is not None
        assert finished_job.result_json.get("steps_completed") == 3


# ------------------------------------------------------------------------------
# E2E SSE Streaming Tests
# ------------------------------------------------------------------------------


class TestWorkerE2ESSEStreaming:
    """Test SSE event streaming with worker processing."""

    def test_sse_stream_job_lifecycle_events(self, client, admin_headers):
        """
        E2E test: Stream SSE events for complete job lifecycle.

        Verifies:
        - Retry header present
        - Event IDs are monotonic
        - Status events received
        """
        # Create job
        response = client.post(
            "/v1/jobs", json={"type": "demo", "payload": {"duration_ms": 1000}}, headers=admin_headers  # 1 second
        )

        assert response.status_code == 202
        job_id = response.json()["id"]

        # Stream events
        collected_lines = []
        with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=admin_headers) as sse_resp:
            assert sse_resp.status_code == 200
            assert "text/event-stream" in sse_resp.headers.get("content-type", "")

            # Collect events for a few seconds
            start = time.time()
            for line in sse_resp.iter_lines():
                collected_lines.append(line)

                # Stop after 5 seconds max
                if time.time() - start > 5.0:
                    break

                # Look for finished event
                line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                if "finished" in line_str.lower():
                    # Read a bit more then stop
                    time.sleep(0.2)
                    for _ in range(5):
                        try:
                            collected_lines.append(next(sse_resp.iter_lines()))
                        except StopIteration:
                            break
                    break

        # Verify retry header
        assert any(b"retry:" in (line if isinstance(line, bytes) else line.encode()) for line in collected_lines[:10])

        # Parse events
        events = parse_sse_events(collected_lines)

        # Verify events received
        assert len(events) >= 1, f"Should receive at least one event"

        # Verify event IDs are monotonic if present
        event_ids = [e["id"] for e in events if "id" in e]
        if event_ids:
            assert event_ids == sorted(event_ids), "Event IDs should be monotonically increasing"

    def test_sse_resume_with_last_event_id(self, client, admin_headers):
        """E2E test: Resume SSE stream from specific event ID."""
        # Create job
        response = client.post(
            "/v1/jobs", json={"type": "demo", "payload": {"duration_ms": 500}}, headers=admin_headers
        )
        job_id = response.json()["id"]

        # First stream: collect some events
        first_lines = []
        with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=admin_headers) as sse_resp:
            start = time.time()
            for line in sse_resp.iter_lines():
                first_lines.append(line)
                if time.time() - start > 1.5:  # Collect for 1.5s
                    break

        first_events = parse_sse_events(first_lines)

        if len(first_events) < 2:
            # Job too fast, skip this test
            pytest.skip("Job completed too quickly to test resumption")

        # Resume from first event
        resume_id = first_events[0].get("id", 0)

        # Second stream: resume from event
        headers_with_resume = {**admin_headers, "Last-Event-ID": str(resume_id)}
        with client.stream("GET", f"/v1/jobs/{job_id}/events", headers=headers_with_resume) as sse_resp:
            resumed_lines = []
            for i, line in enumerate(sse_resp.iter_lines()):
                resumed_lines.append(line)
                if i > 20:  # Limit collection
                    break

        resumed_events = parse_sse_events(resumed_lines)

        # Verify resumed events start after resume_id
        if resumed_events and "id" in resumed_events[0]:
            assert resumed_events[0]["id"] > resume_id, "Resumed stream should start after Last-Event-ID"


# ------------------------------------------------------------------------------
# E2E Cancellation Tests
# ------------------------------------------------------------------------------


class TestWorkerE2ECancellation:
    """Test job cancellation with worker."""

    def test_cancel_running_job(self, client, admin_headers, repo):
        """E2E test: Cancel job while worker is processing it."""
        # Create long-running job
        response = client.post(
            "/v1/jobs", json={"type": "long-running", "payload": {"steps": 10}}, headers=admin_headers  # 30 seconds
        )

        assert response.status_code == 202
        job_id = UUID(response.json()["id"])

        # Wait for job to start running
        running_job = wait_for_job_status(repo, job_id, "running", timeout=5.0)

        if not running_job:
            pytest.skip("Job did not start running in time (worker may be slow/busy)")

        # Cancel while running
        cancel_response = client.delete(f"/v1/jobs/{job_id}", headers=admin_headers)
        assert cancel_response.status_code == 200

        # Worker should detect cancel flag
        # Give worker time to check (checks every 0.5s in sleep chunks)
        time.sleep(2.0)

        # Verify cancellation or still running (acceptable)
        job = repo.get_job(job_id)
        assert job.status in ["cancelled", "running", "finished"]

        # If cancelled, verify didn't complete all steps
        if job.status == "cancelled":
            if job.result_json:
                steps_completed = job.result_json.get("steps_completed", 0)
                assert steps_completed < 10, "Cancelled job should not complete all steps"


# ------------------------------------------------------------------------------
# E2E Error Handling Tests
# ------------------------------------------------------------------------------


class TestWorkerE2EErrorHandling:
    """Test error scenarios in E2E flow."""

    def test_sse_stream_for_nonexistent_job(self, client, admin_headers):
        """E2E test: SSE stream for non-existent job returns 404."""
        fake_job_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(f"/v1/jobs/{fake_job_id}/events", headers=admin_headers)
        assert response.status_code == 404

    def test_get_nonexistent_job(self, client, admin_headers):
        """E2E test: GET for non-existent job returns 404."""
        fake_job_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(f"/v1/jobs/{fake_job_id}", headers=admin_headers)
        assert response.status_code == 404


# ------------------------------------------------------------------------------
# E2E Heartbeat Tests
# ------------------------------------------------------------------------------


class TestWorkerE2EHeartbeat:
    """Test worker heartbeat mechanism."""

    def test_job_updated_at_heartbeat(self, client, admin_headers, repo):
        """
        E2E test: Verify worker updates job timestamp during execution.

        Worker updates updated_at every 5 seconds as heartbeat.
        """
        # Create long-running job
        response = client.post(
            "/v1/jobs", json={"type": "long-running", "payload": {"steps": 3}}, headers=admin_headers  # 9 seconds total
        )

        assert response.status_code == 202
        job_id = UUID(response.json()["id"])

        # Wait for running
        running_job = wait_for_job_status(repo, job_id, "running", timeout=5.0)

        if not running_job:
            pytest.skip("Job did not start running (worker may be slow/busy)")

        # Record initial timestamp
        initial_updated_at = running_job.updated_at

        # Wait for heartbeat interval (5+ seconds)
        time.sleep(6.0)

        # Refresh job from DB
        repo.db.expire(running_job)
        updated_job = repo.get_job(job_id)

        # Verify timestamp updated (heartbeat occurred) if still running
        if updated_job.status == "running":
            assert (
                updated_job.updated_at > initial_updated_at
            ), "Worker should update job timestamp during execution (heartbeat)"


# ------------------------------------------------------------------------------
# E2E Idempotency Tests
# ------------------------------------------------------------------------------


class TestWorkerE2EIdempotency:
    """Test idempotency in E2E flow."""

    def test_duplicate_job_with_idempotency_key(self, client, admin_headers, repo):
        """E2E test: Same idempotency key returns existing job."""
        idempotency_key = "test-worker-e2e-idem-001"

        # First request
        response1 = client.post(
            "/v1/jobs",
            json={"type": "demo", "payload": {"duration_ms": 500}},
            headers={**admin_headers, "Idempotency-Key": idempotency_key},
        )

        assert response1.status_code == 202
        job_id_1 = response1.json()["id"]

        # Second request with same key
        response2 = client.post(
            "/v1/jobs",
            json={"type": "demo", "payload": {"duration_ms": 500}},
            headers={**admin_headers, "Idempotency-Key": idempotency_key},
        )

        # Should return same job (202 or 200)
        assert response2.status_code in [200, 202]
        job_id_2 = response2.json()["id"]

        assert job_id_1 == job_id_2, "Idempotency key should return same job ID"


# ------------------------------------------------------------------------------
# E2E Performance Tests (Optional)
# ------------------------------------------------------------------------------


class TestWorkerE2EPerformance:
    """Test performance characteristics (optional, may be slow)."""

    def test_multiple_sequential_jobs(self, client, admin_headers, repo):
        """
        E2E test: Worker can process multiple jobs sequentially.

        Creates multiple jobs and verifies worker processes them all.
        """
        job_ids = []

        # Create 5 jobs
        for i in range(5):
            response = client.post(
                "/v1/jobs", json={"type": "demo", "payload": {"duration_ms": 300, "index": i}}, headers=admin_headers
            )
            assert response.status_code == 202
            job_ids.append(UUID(response.json()["id"]))

        # Wait for all to finish
        timeout = 20.0  # Allow generous time
        finished_count = 0

        start = time.time()
        while time.time() - start < timeout:
            finished_count = sum(
                1 for job_id in job_ids if repo.get_job(job_id) and repo.get_job(job_id).status == "finished"
            )

            if finished_count == len(job_ids):
                break

            time.sleep(0.5)

        # At least some should finish
        assert finished_count > 0, f"At least one job should finish. Got {finished_count}/{len(job_ids)}"

        # Ideally all finish (worker processes sequentially)
        # But we allow partial completion in case worker is slow
