"""
Tests for atomic job operations using Lua scripts.

Verifies:
- Atomic cancellation with CAS semantics
- Concurrent cancellation safety
- Index cleanup orphan detection
"""

import pytest
import asyncio
from datetime import datetime

from db.redis_cache.job_store import RedisJobStore
from src.jobs.models import JobDocument, JobStatus
from db.redis_cache.async_client import get_async_redis


pytestmark = pytest.mark.skipif(
    True,  # Skip by default; run with `pytest -k atomic`
    reason="Redis atomic tests require Redis backend (set JOB_STORE_BACKEND=redis)",
)


@pytest.mark.asyncio
async def test_cancel_job_atomic_success():
    """Test atomic cancellation transitions job from queued to cancelled."""
    store = RedisJobStore()
    job = JobDocument(
        id="atomic-cancel-1",
        owner="alice",
        tenant="test-tenant",
        type="test-job",
        status=JobStatus.QUEUED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Create job
    await store.create(job, ttl_seconds=3600)

    # Cancel atomically
    result = await store.cancel_job_atomic("atomic-cancel-1")

    assert result is True  # Successfully transitioned

    # Verify status changed
    updated_job = await store.get("atomic-cancel-1")
    assert updated_job is not None
    assert updated_job.status == JobStatus.CANCELLED
    assert updated_job.result == {"cancelled": True}


@pytest.mark.asyncio
async def test_cancel_job_atomic_already_terminal():
    """Test atomic cancellation fails if job already finished."""
    store = RedisJobStore()
    job = JobDocument(
        id="atomic-cancel-2",
        owner="alice",
        tenant="test-tenant",
        type="test-job",
        status=JobStatus.FINISHED,  # Already terminal
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        result={"data": "completed"},
    )

    await store.create(job, ttl_seconds=3600)

    # Attempt to cancel (should return False)
    result = await store.cancel_job_atomic("atomic-cancel-2")

    assert result is False  # No transition (already terminal)

    # Verify status unchanged
    updated_job = await store.get("atomic-cancel-2")
    assert updated_job is not None
    assert updated_job.status == JobStatus.FINISHED
    assert updated_job.result == {"data": "completed"}


@pytest.mark.asyncio
async def test_cancel_job_atomic_not_found():
    """Test atomic cancellation returns False for missing job."""
    store = RedisJobStore()

    # Cancel non-existent job
    result = await store.cancel_job_atomic("nonexistent-job")

    assert result is False


@pytest.mark.asyncio
async def test_cancel_job_atomic_concurrent_safety():
    """Test atomic cancellation handles concurrent cancel attempts safely."""
    store = RedisJobStore()
    job = JobDocument(
        id="atomic-cancel-concurrent",
        owner="alice",
        tenant="test-tenant",
        type="test-job",
        status=JobStatus.RUNNING,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    await store.create(job, ttl_seconds=3600)

    # Simulate 10 concurrent cancellation attempts
    results = await asyncio.gather(*[store.cancel_job_atomic("atomic-cancel-concurrent") for _ in range(10)])

    # Exactly one should succeed (first one), rest should return False
    success_count = sum(1 for r in results if r is True)
    failure_count = sum(1 for r in results if r is False)

    # Due to atomicity, only the first cancel succeeds
    # The rest see it's already terminal and return False
    assert success_count == 1, f"Expected 1 success, got {success_count}"
    assert failure_count == 9, f"Expected 9 failures, got {failure_count}"

    # Verify final state is cancelled
    updated_job = await store.get("atomic-cancel-concurrent")
    assert updated_job is not None
    assert updated_job.status == JobStatus.CANCELLED


@pytest.mark.asyncio
async def test_cleanup_orphaned_index_members_basic():
    """Test cleanup removes orphaned ZSET members."""
    store = RedisJobStore()
    redis = await get_async_redis()

    # Create a job then manually delete the HASH (simulating TTL expiry)
    job = JobDocument(
        id="orphan-test-1",
        owner="alice",
        tenant="test-tenant",
        type="test-job",
        status=JobStatus.QUEUED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    await store.create(job, ttl_seconds=3600)

    # Verify job exists in index
    members = await redis.zrange("jobs:all", 0, -1)
    job_ids = [m.decode("utf-8") if isinstance(m, bytes) else m for m in members]
    assert "orphan-test-1" in job_ids

    # Manually delete the job HASH (simulate TTL expiry)
    await redis.delete("job:orphan-test-1")

    # Run cleanup
    removed = await store.cleanup_orphaned_index_members("jobs:all", batch_size=100)

    # Should have removed the orphaned member
    assert removed >= 1

    # Verify orphan no longer in index
    members_after = await redis.zrange("jobs:all", 0, -1)
    job_ids_after = [m.decode("utf-8") if isinstance(m, bytes) else m for m in members_after]
    assert "orphan-test-1" not in job_ids_after


@pytest.mark.asyncio
async def test_cleanup_orphaned_index_members_batch():
    """Test cleanup handles batch size correctly."""
    store = RedisJobStore()
    redis = await get_async_redis()

    # Create 5 jobs, delete 3 HASHes (create orphans)
    for i in range(5):
        job = JobDocument(
            id=f"orphan-batch-{i}",
            owner="alice",
            tenant="test-tenant",
            type="test-job",
            status=JobStatus.QUEUED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        await store.create(job, ttl_seconds=3600)

    # Delete 3 job HASHes (create orphans)
    for i in [0, 2, 4]:
        await redis.delete(f"job:orphan-batch-{i}")

    # Run cleanup with batch size = 10 (should process all)
    removed = await store.cleanup_orphaned_index_members("jobs:all", batch_size=10)

    # Should have removed 3 orphans
    assert removed >= 3


@pytest.mark.asyncio
async def test_cleanup_orphaned_index_members_no_orphans():
    """Test cleanup returns 0 when no orphans exist."""
    store = RedisJobStore()

    # Create a valid job (no orphans)
    job = JobDocument(
        id="no-orphan-test",
        owner="alice",
        tenant="test-tenant",
        type="test-job",
        status=JobStatus.QUEUED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    await store.create(job, ttl_seconds=3600)

    # Run cleanup
    removed = await store.cleanup_orphaned_index_members("jobs:all", batch_size=100)

    # Should remove 0 orphans (all members are valid)
    assert removed == 0
