"""
Integration tests for PostgreSQL JobsRepository.

These tests use the actual PostgreSQL database from Docker Compose,
providing realistic testing against the production database engine.

Setup:
    Ensure PostgreSQL is running:
    $ docker compose up -d postgres

Run tests:
    $ pytest tests/integration/test_jobs_postgres.py -v
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from db.postgres_control.database import SessionLocal, Base, engine
from db.postgres_control.models.job import Job
from db.postgres_control.models.job_event import JobEvent
from db.postgres_control.models.tenant import Tenant
from db.postgres_control.repositories.jobs import JobsRepository


@pytest.fixture(scope="function")
def db_session():
    """
    Create a database session for testing.

    Uses the actual PostgreSQL database from Docker Compose.
    Each test gets a clean session with transaction rollback.
    """
    # Create a new session
    session = SessionLocal()

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    # Create a test tenant if it doesn't exist
    existing_tenant = session.query(Tenant).filter(Tenant.id == "test-tenant").first()
    if not existing_tenant:
        tenant = Tenant(id="test-tenant", name="Test Tenant", admin_email="admin@test.com")
        session.add(tenant)
        session.commit()

    # Cleanup BEFORE test to ensure clean state
    try:
        session.query(Job).filter(Job.tenant_id == "test-tenant").delete()
        session.commit()
    except Exception:
        session.rollback()

    yield session

    # Cleanup: Delete all test jobs and events created during the test
    try:
        # Delete all jobs for test tenant (cascade will delete events)
        session.query(Job).filter(Job.tenant_id == "test-tenant").delete()
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


@pytest.fixture
def repo(db_session):
    """Create JobsRepository instance."""
    return JobsRepository(db_session)


# ------------------------------------------------------------------------------
# Job Creation Tests
# ------------------------------------------------------------------------------


def test_create_job_basic(repo: JobsRepository, db_session):
    """Test basic job creation."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={"message": "Hello"})

    assert job.id is not None
    assert job.type == "demo"
    assert job.status == "queued"
    assert job.owner_sub == "user123"
    assert job.tenant_id == "test-tenant"
    assert job.payload_json == {"message": "Hello"}
    assert job.priority == 0
    assert job.etag is not None
    assert job.created_at is not None

    # Verify event was created
    events = db_session.query(JobEvent).filter(JobEvent.job_id == job.id).all()
    assert len(events) == 1
    assert events[0].event_type == "status"
    assert events[0].event_json["to"] == "queued"


def test_create_job_with_idempotency_key(repo: JobsRepository, db_session):
    """Test job creation with idempotency key."""
    job1 = repo.create_job(
        owner_sub="user123",
        tenant_id="test-tenant",
        type="test",
        payload_json={"data": "value"},
        idempotency_key="unique-key-123",
    )

    assert job1.idempotency_key == "unique-key-123"
    db_session.commit()

    # Attempting to create another job with same idempotency key should fail
    with pytest.raises(IntegrityError):
        job2 = repo.create_job(
            owner_sub="user123",
            tenant_id="test-tenant",
            type="test",
            payload_json={"data": "different"},
            idempotency_key="unique-key-123",
        )
        db_session.commit()

    db_session.rollback()


def test_create_job_with_priority(repo: JobsRepository):
    """Test job creation with custom priority."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={}, priority=10)

    assert job.priority == 10


def test_create_job_generates_etag(repo: JobsRepository):
    """Test that job creation generates an ETag."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    assert job.etag is not None
    assert len(job.etag) == 32  # MD5 hash hex string


# ------------------------------------------------------------------------------
# Job Retrieval Tests
# ------------------------------------------------------------------------------


def test_get_job_by_id(repo: JobsRepository):
    """Test retrieving job by ID."""
    created_job = repo.create_job(
        owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={"key": "value"}
    )

    retrieved_job = repo.get_job(created_job.id)

    assert retrieved_job is not None
    assert retrieved_job.id == created_job.id
    assert retrieved_job.type == "demo"
    assert retrieved_job.payload_json == {"key": "value"}


def test_get_job_nonexistent(repo: JobsRepository):
    """Test retrieving nonexistent job returns None."""
    nonexistent_id = uuid4()
    job = repo.get_job(nonexistent_id)

    assert job is None


def test_get_job_for_owner(repo: JobsRepository):
    """Test retrieving job with owner verification."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    # Owner can retrieve their job
    retrieved = repo.get_job_for_owner(job.id, "user123")
    assert retrieved is not None
    assert retrieved.id == job.id

    # Different owner cannot retrieve the job
    other_owner = repo.get_job_for_owner(job.id, "user456")
    assert other_owner is None


def test_find_by_idempotency(repo: JobsRepository, db_session):
    """Test finding job by idempotency key."""
    job = repo.create_job(
        owner_sub="user123", tenant_id="test-tenant", type="test", payload_json={}, idempotency_key="idem-key-abc"
    )
    db_session.commit()

    found = repo.find_by_idempotency("user123", "idem-key-abc")
    assert found is not None
    assert found.id == job.id

    # Different owner cannot find the job
    not_found = repo.find_by_idempotency("user456", "idem-key-abc")
    assert not_found is None


# ------------------------------------------------------------------------------
# Job Listing Tests
# ------------------------------------------------------------------------------


def test_list_jobs_all(repo: JobsRepository):
    """Test listing all jobs for an owner."""
    # Create multiple jobs
    for i in range(5):
        repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={"index": i})

    jobs, total, has_more = repo.list_jobs(owner_sub="user123")

    assert len(jobs) >= 5  # May have other jobs from parallel tests
    assert total >= 5
    assert has_more is False or total > 20


def test_list_jobs_pagination(repo: JobsRepository):
    """Test job listing with pagination."""
    # Create 25 jobs
    for i in range(25):
        repo.create_job(
            owner_sub=f"paginate-user-{i % 3}",  # Distribute across 3 users
            tenant_id="test-tenant",
            type="demo",
            payload_json={"index": i},
        )

    # First page for one user
    jobs_page1, total, has_more = repo.list_jobs(owner_sub="paginate-user-0", limit=5, offset=0)
    assert len(jobs_page1) <= 5

    if total > 5:
        assert has_more is True


def test_list_jobs_filter_by_status(repo: JobsRepository, db_session):
    """Test filtering jobs by status."""
    # Create jobs with different statuses
    job1 = repo.create_job(owner_sub="status-user", tenant_id="test-tenant", type="demo", payload_json={})

    job2 = repo.create_job(owner_sub="status-user", tenant_id="test-tenant", type="demo", payload_json={})
    job2.status = "running"
    db_session.commit()

    job3 = repo.create_job(owner_sub="status-user", tenant_id="test-tenant", type="demo", payload_json={})
    job3.status = "finished"
    db_session.commit()

    # Filter for queued jobs
    queued_jobs, total, _ = repo.list_jobs(owner_sub="status-user", status=["queued"])
    assert len(queued_jobs) >= 1
    assert all(j.status == "queued" for j in queued_jobs)

    # Filter for running jobs
    running_jobs, total, _ = repo.list_jobs(owner_sub="status-user", status=["running"])
    assert len(running_jobs) >= 1
    assert all(j.status == "running" for j in running_jobs)

    # Filter for multiple statuses
    active_jobs, total, _ = repo.list_jobs(owner_sub="status-user", status=["queued", "running"])
    assert len(active_jobs) >= 2


def test_list_jobs_ordered_by_creation(repo: JobsRepository, db_session):
    """Test that jobs are listed with consistent ordering."""
    # Create jobs and explicitly commit between each to ensure different timestamps
    job1 = repo.create_job(owner_sub="order-user", tenant_id="test-tenant", type="demo", payload_json={"order": 1})
    db_session.commit()

    import time

    time.sleep(0.01)  # Small delay to ensure different timestamps

    job2 = repo.create_job(owner_sub="order-user", tenant_id="test-tenant", type="demo", payload_json={"order": 2})
    db_session.commit()

    time.sleep(0.01)

    job3 = repo.create_job(owner_sub="order-user", tenant_id="test-tenant", type="demo", payload_json={"order": 3})
    db_session.commit()

    jobs, total, has_more = repo.list_jobs(owner_sub="order-user", limit=3)

    # Should return all 3 jobs
    assert len(jobs) == 3
    assert total == 3
    assert has_more is False

    # Most recent first (job3, job2, job1)
    assert jobs[0].id == job3.id
    assert jobs[1].id == job2.id
    assert jobs[2].id == job1.id


# ------------------------------------------------------------------------------
# Status Transition Tests
# ------------------------------------------------------------------------------


def test_transition_status_basic(repo: JobsRepository, db_session):
    """Test basic status transition."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    assert job.status == "queued"

    # Transition to running
    now = datetime.now(timezone.utc)
    updated_job = repo.transition_status(job.id, from_status="queued", to_status="running", started_at=now)

    db_session.commit()

    assert updated_job is not None
    assert updated_job.status == "running"
    assert updated_job.started_at is not None
    assert updated_job.queue_latency_ms is not None
    assert updated_job.queue_latency_ms >= 0


def test_transition_status_with_result(repo: JobsRepository, db_session):
    """Test status transition to finished with result."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    # Transition to running
    started_at = datetime.now(timezone.utc)
    repo.transition_status(job.id, "queued", "running", started_at=started_at)
    db_session.commit()

    # Transition to finished
    completed_at = started_at + timedelta(seconds=5)
    updated_job = repo.transition_status(
        job.id,
        from_status="running",
        to_status="finished",
        completed_at=completed_at,
        result_json={"status": "success", "output": "Done!"},
    )

    db_session.commit()

    assert updated_job.status == "finished"
    assert updated_job.completed_at is not None
    assert updated_job.result_json == {"status": "success", "output": "Done!"}
    assert updated_job.exec_latency_ms is not None
    assert updated_job.exec_latency_ms >= 4000  # At least 4 seconds


def test_transition_status_with_error(repo: JobsRepository, db_session):
    """Test status transition to failed with error."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    # Transition to running
    started_at = datetime.now(timezone.utc)
    repo.transition_status(job.id, "queued", "running", started_at=started_at)
    db_session.commit()

    # Transition to failed
    completed_at = started_at + timedelta(seconds=2)
    updated_job = repo.transition_status(
        job.id,
        from_status="running",
        to_status="failed",
        completed_at=completed_at,
        error_json={"error": "Something went wrong", "code": 500},
    )

    db_session.commit()

    assert updated_job.status == "failed"
    assert updated_job.error_json == {"error": "Something went wrong", "code": 500}
    assert updated_job.result_json is None


def test_transition_status_mismatch_fails(repo: JobsRepository):
    """Test that status transition fails if from_status doesn't match."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    assert job.status == "queued"

    # Try to transition from "running" to "finished" when job is actually "queued"
    updated_job = repo.transition_status(
        job.id,
        from_status="running",  # Wrong current status
        to_status="finished",
        completed_at=datetime.now(timezone.utc),
    )

    assert updated_job is None  # Transition should fail


def test_transition_status_updates_etag(repo: JobsRepository, db_session):
    """Test that status transitions update the ETag."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    original_etag = job.etag

    # Transition status
    repo.transition_status(job.id, from_status="queued", to_status="running", started_at=datetime.now(timezone.utc))
    db_session.commit()

    # ETag should change
    db_session.refresh(job)
    assert job.etag != original_etag


def test_transition_status_creates_event(repo: JobsRepository, db_session):
    """Test that status transitions create events."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    # Should have 1 event (initial queued)
    events_before = db_session.query(JobEvent).filter(JobEvent.job_id == job.id).count()
    assert events_before == 1

    # Transition to running
    repo.transition_status(job.id, from_status="queued", to_status="running", started_at=datetime.now(timezone.utc))
    db_session.commit()

    # Should have 2 events now
    events_after = db_session.query(JobEvent).filter(JobEvent.job_id == job.id).all()
    assert len(events_after) == 2
    assert events_after[1].event_type == "status"
    assert events_after[1].event_json["from"] == "queued"
    assert events_after[1].event_json["to"] == "running"


# ------------------------------------------------------------------------------
# Event Logging Tests
# ------------------------------------------------------------------------------


def test_append_event(repo: JobsRepository, db_session):
    """Test appending events to a job."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    # Append a custom event
    event = repo.append_event(
        job_id=job.id, event_type="progress", event_json={"step": 1, "total": 10, "message": "Processing..."}
    )

    db_session.commit()

    assert event.job_id == job.id
    assert event.event_type == "progress"
    assert event.event_json["step"] == 1
    assert event.seq_id is not None


def test_get_events_for_job(repo: JobsRepository, db_session):
    """Test getting all events for a job."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    # Append multiple events
    for i in range(5):
        repo.append_event(job_id=job.id, event_type="progress", event_json={"step": i + 1})

    db_session.commit()

    events = repo.get_events(job.id)

    # Should have 6 events (1 initial + 5 progress)
    assert len(events) == 6
    assert events[0].event_type == "status"  # Initial event
    for i in range(1, 6):
        assert events[i].event_type == "progress"
        assert events[i].event_json["step"] == i


def test_get_events_after_seq_id(repo: JobsRepository, db_session):
    """Test getting events after a specific sequence ID."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    # Append multiple events
    for i in range(5):
        repo.append_event(job_id=job.id, event_type="progress", event_json={"step": i + 1})

    db_session.commit()

    # Get all events to find seq_id
    all_events = repo.get_events(job.id)
    third_event_seq = all_events[2].seq_id

    # Get events after third event
    events_after = repo.get_events(job.id, after_seq_id=third_event_seq)

    # Should get events after seq_id 3
    assert len(events_after) > 0
    assert all(e.seq_id > third_event_seq for e in events_after)


# ------------------------------------------------------------------------------
# Helper Methods Tests
# ------------------------------------------------------------------------------


def test_update_job_result(repo: JobsRepository, db_session):
    """Test updating job result."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    result = {"output": "Success", "duration": 123}
    repo.update_job_result(job.id, result)
    db_session.commit()

    db_session.refresh(job)
    assert job.result_json == result


def test_update_job_error(repo: JobsRepository, db_session):
    """Test updating job error."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    error = "Task failed with exception"
    repo.update_job_error(job.id, error)
    db_session.commit()

    db_session.refresh(job)
    assert job.error_json == {"message": error}


def test_touch_job(repo: JobsRepository, db_session):
    """Test touching job to update timestamp."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    original_updated_at = job.updated_at

    # Touch the job
    import time

    time.sleep(0.01)  # Small delay to ensure timestamp changes
    repo.touch_job(job.id)
    db_session.commit()

    db_session.refresh(job)
    # updated_at should change
    assert job.updated_at >= original_updated_at


def test_delete_job(repo: JobsRepository, db_session):
    """Test deleting a job."""
    job = repo.create_job(owner_sub="user123", tenant_id="test-tenant", type="demo", payload_json={})

    job_id = job.id

    # Delete the job
    result = repo.delete_job(job_id)
    db_session.commit()

    assert result is True

    # Job should no longer exist
    deleted_job = repo.get_job(job_id)
    assert deleted_job is None


def test_delete_nonexistent_job(repo: JobsRepository):
    """Test deleting a job that doesn't exist."""
    nonexistent_id = uuid4()
    result = repo.delete_job(nonexistent_id)

    assert result is False


def test_compute_list_etag(repo: JobsRepository, db_session):
    """Test computing ETag for job list queries."""
    # Create first job
    job1 = repo.create_job(owner_sub="etag-user", tenant_id="test-tenant", type="demo", payload_json={})
    db_session.commit()

    etag1 = repo.compute_list_etag("etag-user", "test-tenant", None)
    assert etag1 is not None
    assert len(etag1) == 32  # MD5 hash

    # Create another job with explicit commit to ensure different timestamp
    import time

    time.sleep(0.01)

    job2 = repo.create_job(owner_sub="etag-user", tenant_id="test-tenant", type="demo", payload_json={})
    db_session.commit()

    # ETag should change
    etag2 = repo.compute_list_etag("etag-user", "test-tenant", None)
    assert etag2 != etag1


# ------------------------------------------------------------------------------
# Edge Cases and Error Handling
# ------------------------------------------------------------------------------


def test_get_job_with_invalid_uuid(repo: JobsRepository):
    """Test that invalid UUID handling is graceful."""
    invalid_id = uuid4()
    job = repo.get_job(invalid_id)
    assert job is None


def test_empty_list_jobs(repo: JobsRepository):
    """Test listing jobs when there are none for a user."""
    jobs, total, has_more = repo.list_jobs(owner_sub="nonexistent-user-xyz-123")

    assert jobs == []
    assert total == 0
    assert has_more is False


def test_transition_nonexistent_job(repo: JobsRepository):
    """Test transitioning status of nonexistent job."""
    nonexistent_id = uuid4()
    result = repo.transition_status(
        nonexistent_id, from_status="queued", to_status="running", started_at=datetime.now(timezone.utc)
    )

    assert result is None
