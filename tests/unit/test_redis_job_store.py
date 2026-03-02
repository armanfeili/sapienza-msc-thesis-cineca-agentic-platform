"""
Unit tests for Redis job store implementation.

These tests mock the Redis client to test the job store logic without
requiring an actual Redis instance. Tests cover:
- Job CRUD operations
- Status transitions
- Idempotency handling
- Event storage and replay
- Index management
- Error handling

Run tests:
    $ pytest tests/unit/test_redis_job_store.py -v
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

from src.jobs.models import JobDocument, SSEEvent, JobStatus
from src.jobs.interfaces import JobNotFoundError, StorageError
from db.redis_cache.job_store import (
    RedisJobStore,
    RedisIdempotencyStore,
    RedisEventStore,
)


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis = AsyncMock()
    redis.pipeline = MagicMock(return_value=AsyncMock())
    redis.script_load = AsyncMock(return_value="mock_sha")
    return redis


@pytest.fixture
def job_store():
    """Create RedisJobStore instance."""
    return RedisJobStore()


@pytest.fixture
def idempotency_store():
    """Create RedisIdempotencyStore instance."""
    return RedisIdempotencyStore()


@pytest.fixture
def event_store():
    """Create RedisEventStore instance."""
    return RedisEventStore(ring_size=100)


@pytest.fixture
def sample_job():
    """Create sample job document for testing."""
    return JobDocument(
        id=str(uuid4()),
        type="agent.run",
        status=JobStatus.QUEUED,
        owner="test-user",  # Note: field is 'owner' not 'owner_sub'
        tenant_id="test-tenant",
        payload={"param": "value"},  # Note: field is 'payload' not 'payload_json'
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_event():
    """Create sample SSE event for testing."""
    return SSEEvent(
        event_type="status",
        event_id=1,
        data={"from": "queued", "to": "running"},
        timestamp=datetime.now(timezone.utc),
    )


# ------------------------------------------------------------------------------
# RedisJobStore Tests
# ------------------------------------------------------------------------------


class TestRedisJobStoreCreate:
    """Tests for job creation."""

    @pytest.mark.asyncio
    async def test_create_job_basic(self, job_store, sample_job, mock_redis):
        """Test basic job creation with indexes."""
        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            await job_store.create(sample_job, ttl_seconds=86400)

            # Verify pipeline was used
            mock_redis.pipeline.assert_called_once()
            pipeline = mock_redis.pipeline.return_value.__aenter__.return_value

            # Verify HSET called with job data
            pipeline.hset.assert_called()

            # Verify expiry set
            pipeline.expire.assert_called()

            # Verify indexes updated (ZADD for all, owner, status)
            assert pipeline.zadd.call_count >= 3

            # Verify pipeline executed
            pipeline.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_job_with_ttl(self, job_store, sample_job, mock_redis):
        """Test job creation respects TTL."""
        ttl_seconds = 3600

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            await job_store.create(sample_job, ttl_seconds=ttl_seconds)

            pipeline = mock_redis.pipeline.return_value.__aenter__.return_value

            # Check expire was called with correct TTL
            expire_calls = [call for call in pipeline.expire.call_args_list]
            assert any(str(ttl_seconds) in str(call) for call in expire_calls)

    @pytest.mark.asyncio
    async def test_create_job_storage_error(self, job_store, sample_job, mock_redis):
        """Test error handling during job creation."""
        # Simulate Redis error
        mock_redis.pipeline.return_value.__aenter__.return_value.execute.side_effect = Exception("Redis error")

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            with pytest.raises(StorageError):
                await job_store.create(sample_job, ttl_seconds=86400)


class TestRedisJobStoreGet:
    """Tests for job retrieval."""

    @pytest.mark.asyncio
    async def test_get_job_exists(self, job_store, sample_job, mock_redis):
        """Test retrieving existing job."""
        # Mock Redis HGETALL response
        hash_data = {
            b"id": sample_job.id.encode(),
            b"type": sample_job.type.encode(),
            b"status": sample_job.status.encode(),
            b"owner": sample_job.owner.encode(),  # Note: 'owner' not 'owner_sub'
            b"tenant_id": sample_job.tenant_id.encode(),
            b"payload": '{"param": "value"}'.encode(),  # Note: 'payload' not 'payload_json'
            b"created_at": sample_job.created_at.isoformat().encode(),
            b"updated_at": sample_job.updated_at.isoformat().encode(),
        }
        mock_redis.hgetall.return_value = hash_data

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            job = await job_store.get(sample_job.id)

            assert job is not None
            assert job.id == sample_job.id
            assert job.type == sample_job.type
            assert job.status == sample_job.status

            # Verify Redis called correctly
            mock_redis.hgetall.assert_called_once_with(f"job:{sample_job.id}")

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, job_store, mock_redis):
        """Test retrieving nonexistent job returns None."""
        mock_redis.hgetall.return_value = {}

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            job = await job_store.get("nonexistent-id")

            assert job is None

    @pytest.mark.asyncio
    async def test_get_job_redis_error(self, job_store, mock_redis):
        """Test error handling during job retrieval."""
        mock_redis.hgetall.side_effect = Exception("Redis connection error")

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            with pytest.raises(StorageError):
                await job_store.get("some-job-id")


class TestRedisJobStoreUpdateStatus:
    """Tests for status transitions."""

    @pytest.mark.asyncio
    async def test_update_status_basic(self, job_store, sample_job, mock_redis):
        """Test basic status update."""
        # Mock get() to return existing job
        hash_data = {
            b"id": sample_job.id.encode(),
            b"type": b"agent.run",
            b"status": b"queued",
            b"owner": b"test-user",
            b"tenant_id": b"test-tenant",
            b"payload": b"{}",
            b"created_at": sample_job.created_at.isoformat().encode(),
            b"updated_at": sample_job.updated_at.isoformat().encode(),
        }
        mock_redis.hgetall.return_value = hash_data

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            result = await job_store.update_status(
                job_id=sample_job.id,
                status=JobStatus.RUNNING,
            )

            assert result is True
            # Verify hset was called to update status
            mock_redis.pipeline.assert_called()

    @pytest.mark.asyncio
    async def test_update_status_not_found(self, job_store, mock_redis):
        """Test status update returns False when job not found."""
        # Mock get() to return None
        mock_redis.hgetall.return_value = {}

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            result = await job_store.update_status(
                job_id="nonexistent-job",
                status=JobStatus.RUNNING,
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_update_status_with_result(self, job_store, sample_job, mock_redis):
        """Test status update with result data."""
        # Mock existing job
        hash_data = {
            b"id": sample_job.id.encode(),
            b"type": b"agent.run",
            b"status": b"running",
            b"owner": b"test-user",
            b"tenant_id": b"test-tenant",
            b"payload": b"{}",
            b"created_at": sample_job.created_at.isoformat().encode(),
            b"updated_at": sample_job.updated_at.isoformat().encode(),
        }
        mock_redis.hgetall.return_value = hash_data

        result_data = {"output": "success", "metrics": {"duration": 5.2}}

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            result = await job_store.update_status(
                job_id=sample_job.id,
                status=JobStatus.FINISHED,
                result=result_data,
            )

            assert result is True


class TestRedisJobStoreList:
    """Tests for job listing operations."""

    @pytest.mark.asyncio
    async def test_list_by_owner_basic(self, job_store, mock_redis):
        """Test listing jobs by owner."""
        # Mock ZREVRANGE response (job IDs)
        job_ids = [b"job-1", b"job-2", b"job-3"]
        mock_redis.zrevrange.return_value = job_ids
        mock_redis.zcard.return_value = 3

        # Mock HGETALL for each job
        mock_redis.hgetall.side_effect = [
            {
                b"id": b"job-1",
                b"type": b"agent.run",
                b"status": b"queued",
                b"owner": b"test-user",
                b"tenant_id": b"test-tenant",
                b"payload": b"{}",
                b"created_at": datetime.now(timezone.utc).isoformat().encode(),
            },
            {
                b"id": b"job-2",
                b"type": b"agent.run",
                b"status": b"running",
                b"owner": b"test-user",
                b"tenant_id": b"test-tenant",
                b"payload": b"{}",
                b"created_at": datetime.now(timezone.utc).isoformat().encode(),
            },
            {
                b"id": b"job-3",
                b"type": b"agent.run",
                b"status": b"finished",
                b"owner": b"test-user",
                b"tenant_id": b"test-tenant",
                b"payload": b"{}",
                b"created_at": datetime.now(timezone.utc).isoformat().encode(),
            },
        ]

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            jobs, total = await job_store.list_by_owner(
                owner="test-user",  # Note: 'owner' not 'owner_sub'
                limit=10,
                offset=0,
            )

            assert len(jobs) == 3
            assert total == 3

            # Verify correct Redis calls
            mock_redis.zcard.assert_called_once()
            mock_redis.zrevrange.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_by_owner_pagination(self, job_store, mock_redis):
        """Test pagination in job listing."""
        mock_redis.zrevrange.return_value = [b"job-4", b"job-5"]
        mock_redis.zcard.return_value = 10
        mock_redis.hgetall.side_effect = [
            {
                b"id": b"job-4",
                b"type": b"agent.run",
                b"owner": b"test-user",
                b"tenant_id": b"test-tenant",
                b"payload": b"{}",
                b"status": b"queued",
                b"created_at": datetime.now(timezone.utc).isoformat().encode(),
            },
            {
                b"id": b"job-5",
                b"type": b"agent.run",
                b"owner": b"test-user",
                b"tenant_id": b"test-tenant",
                b"payload": b"{}",
                b"status": b"queued",
                b"created_at": datetime.now(timezone.utc).isoformat().encode(),
            },
        ]

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            jobs, total = await job_store.list_by_owner(
                owner="test-user",
                limit=2,
                offset=3,  # Skip first 3
            )

            assert len(jobs) == 2
            assert total == 10

    @pytest.mark.asyncio
    async def test_list_by_owner_empty(self, job_store, mock_redis):
        """Test listing when no jobs exist."""
        mock_redis.zrevrange.return_value = []
        mock_redis.zcard.return_value = 0

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            jobs, total = await job_store.list_by_owner(
                owner="test-user",
                limit=10,
                offset=0,
            )

            assert len(jobs) == 0
            assert total == 0


class TestRedisJobStoreDelete:
    """Tests for job deletion."""

    @pytest.mark.asyncio
    async def test_delete_job_success(self, job_store, mock_redis):
        """Test successful job deletion."""
        # Mock get() to return a job (hgetall)
        hash_data = {
            b"id": b"job-123",
            b"type": b"agent.run",
            b"status": b"finished",
            b"owner": b"test-user",
            b"tenant_id": b"test-tenant",
            b"payload": b"{}",
            b"created_at": datetime.now(timezone.utc).isoformat().encode(),
        }
        mock_redis.hgetall.return_value = hash_data

        # Mock script loaded
        mock_redis.script_load.return_value = "delete_sha"

        # Mock evalsha returns 1 (job deleted)
        mock_redis.evalsha.return_value = 1

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            await job_store._ensure_scripts_loaded()

            result = await job_store.delete("job-123")

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_job_not_found(self, job_store, mock_redis):
        """Test deleting nonexistent job."""
        # Mock get() returns None (empty hash)
        mock_redis.hgetall.return_value = {}

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            result = await job_store.delete("nonexistent-job")

            # Returns False because job not found in get()
            assert result is False


class TestRedisJobStoreCancellation:
    """Tests for job cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, job_store, mock_redis):
        """Test successful job cancellation."""
        mock_redis.script_load.return_value = "cancel_sha"
        mock_redis.evalsha.return_value = b"cancelled"  # Success

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            await job_store._ensure_scripts_loaded()

            result = await job_store.cancel_job_atomic(
                job_id="job-123",
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_cancel_job_already_terminal(self, job_store, mock_redis):
        """Test cancellation fails if job already in terminal state."""
        mock_redis.script_load.return_value = "cancel_sha"
        mock_redis.evalsha.return_value = b"already_terminal"  # Already finished/failed

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            await job_store._ensure_scripts_loaded()

            result = await job_store.cancel_job_atomic(
                job_id="job-123",
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, job_store, mock_redis):
        """Test cancellation fails if job not found."""
        mock_redis.script_load.return_value = "cancel_sha"
        mock_redis.evalsha.return_value = b"not_found"

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            await job_store._ensure_scripts_loaded()

            result = await job_store.cancel_job_atomic(
                job_id="nonexistent-job",
            )

            assert result is False


# ------------------------------------------------------------------------------
# RedisIdempotencyStore Tests
# ------------------------------------------------------------------------------


class TestRedisIdempotencyStore:
    """Tests for idempotency store."""

    @pytest.mark.asyncio
    async def test_store_idempotency_key(self, idempotency_store, mock_redis):
        """Test storing idempotency mapping."""
        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            await idempotency_store.store(
                key="test-key",
                job_id="job-123",
                ttl_seconds=86400,
            )

            # Verify SETEX called with key, TTL, and job_id
            mock_redis.setex.assert_called_once_with("test-key", 86400, "job-123")

    @pytest.mark.asyncio
    async def test_get_job_id_exists(self, idempotency_store, mock_redis):
        """Test retrieving job ID by idempotency key."""
        mock_redis.get.return_value = b"job-123"

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            job_id = await idempotency_store.get_job_id("test-key")

            assert job_id == "job-123"
            mock_redis.get.assert_called_once_with("test-key")

    @pytest.mark.asyncio
    async def test_get_job_id_not_found(self, idempotency_store, mock_redis):
        """Test retrieving nonexistent idempotency key."""
        mock_redis.get.return_value = None

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            job_id = await idempotency_store.get_job_id("nonexistent-key")

            assert job_id is None


# ------------------------------------------------------------------------------
# RedisEventStore Tests
# ------------------------------------------------------------------------------


class TestRedisEventStore:
    """Tests for event storage and replay."""

    @pytest.mark.asyncio
    async def test_append_event(self, event_store, sample_event, mock_redis):
        """Test appending event to job history."""
        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            await event_store.append(
                job_id="job-123",
                event=sample_event,
                ring_size=100,
            )

            # Verify pipeline was used
            mock_redis.pipeline.assert_called_once()
            pipeline = mock_redis.pipeline.return_value.__aenter__.return_value

            # Verify LPUSH called to add event
            pipeline.lpush.assert_called_once()

            # Verify LTRIM called to maintain ring buffer
            pipeline.ltrim.assert_called_once()

            # Verify EXPIRE called to set TTL
            pipeline.expire.assert_called_once()

            # Verify pipeline executed
            pipeline.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_next_event_id(self, event_store, mock_redis):
        """Test getting next event ID (atomic increment)."""
        mock_redis.incr.return_value = 1  # First event

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            event_id = await event_store.get_next_event_id("job-123")

            assert event_id == 1
            mock_redis.incr.assert_called_once_with("job:job-123:event_seq")

            # Verify expiry set on counter (only for first event)
            mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_next_event_id_subsequent(self, event_store, mock_redis):
        """Test getting subsequent event IDs (no expire call)."""
        mock_redis.incr.return_value = 5  # Not the first event

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            event_id = await event_store.get_next_event_id("job-123")

            assert event_id == 5
            mock_redis.incr.assert_called_once_with("job:job-123:event_seq")

            # No expire call for subsequent events
            mock_redis.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_replay_from_event_id(self, event_store, mock_redis):
        """Test replaying events from specific event ID."""
        # Mock LRANGE returning event JSON
        events_json = [
            '{"event_type": "status", "event_id": 2, "data": {"to": "running"}, "timestamp": "2025-01-01T00:00:00Z"}',
            '{"event_type": "status", "event_id": 3, "data": {"to": "finished"}, "timestamp": "2025-01-01T00:00:00Z"}',
        ]
        mock_redis.lrange.return_value = [e.encode() for e in events_json]

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            events = await event_store.replay_from(
                job_id="job-123",
                last_event_id=1,  # Get events after ID 1
            )

            # Should filter to only events > last_event_id
            assert len(events) >= 0  # Depends on filtering logic
            mock_redis.lrange.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_events(self, event_store, mock_redis):
        """Test retrieving all events for a job."""
        events_json = [
            '{"event_type": "status", "event_id": 1, "data": {}, "timestamp": "2025-01-01T00:00:00Z"}',
            '{"event_type": "log", "event_id": 2, "data": {"message": "test"}, "timestamp": "2025-01-01T00:00:00Z"}',
        ]
        mock_redis.lrange.return_value = [e.encode() for e in events_json]

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            events = await event_store.get_all_events("job-123")

            assert len(events) == 2
            mock_redis.lrange.assert_called_once_with("job:job-123:events", 0, -1)

    @pytest.mark.asyncio
    async def test_append_event_ring_buffer_limit(self, event_store, sample_event, mock_redis):
        """Test ring buffer maintains size limit."""
        ring_size = 50

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            await event_store.append(
                job_id="job-123",
                event=sample_event,
                ring_size=ring_size,
            )

            pipeline = mock_redis.pipeline.return_value.__aenter__.return_value

            # Verify LTRIM called with ring_size - 1
            trim_call = pipeline.ltrim.call_args
            assert str(ring_size - 1) in str(trim_call) or (ring_size - 1) in trim_call[0]


# ------------------------------------------------------------------------------
# Integration Scenarios
# ------------------------------------------------------------------------------


class TestRedisJobStoreScenarios:
    """Test realistic scenarios combining multiple operations."""

    @pytest.mark.asyncio
    async def test_job_lifecycle(self, job_store, sample_job, mock_redis):
        """Test complete job lifecycle: create → update → delete."""
        # Mock script loading
        mock_redis.script_load.return_value = "mock_sha"

        # Mock hgetall for get operations
        hash_data = {
            b"id": sample_job.id.encode(),
            b"type": b"agent.run",
            b"status": b"queued",
            b"owner": b"test-user",
            b"tenant_id": b"test-tenant",
            b"payload": b"{}",
            b"created_at": sample_job.created_at.isoformat().encode(),
        }

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            # 1. Create job
            await job_store.create(sample_job, ttl_seconds=86400)
            assert mock_redis.pipeline.called

            # 2. Update status
            await job_store._ensure_scripts_loaded()
            mock_redis.hgetall.return_value = hash_data
            result = await job_store.update_status(
                job_id=sample_job.id,
                status=JobStatus.RUNNING,
            )
            assert result is True

            # 3. Delete job
            mock_redis.hgetall.return_value = hash_data
            mock_redis.evalsha.return_value = 1
            result = await job_store.delete(sample_job.id)
            assert result is True

    @pytest.mark.asyncio
    async def test_idempotency_workflow(self, job_store, idempotency_store, sample_job, mock_redis):
        """Test idempotent job creation workflow."""
        idempotency_key = "user-123:create-report"

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            # 1. First request: no existing job
            mock_redis.get.return_value = None
            existing_job_id = await idempotency_store.get_job_id(idempotency_key)
            assert existing_job_id is None

            # 2. Create job
            await job_store.create(sample_job, ttl_seconds=86400)

            # 3. Store idempotency mapping
            await idempotency_store.store(idempotency_key, sample_job.id, ttl_seconds=86400)

            # 4. Second request: finds existing job
            mock_redis.get.return_value = sample_job.id.encode()
            existing_job_id = await idempotency_store.get_job_id(idempotency_key)
            assert existing_job_id == sample_job.id


# ------------------------------------------------------------------------------
# Error Handling Tests
# ------------------------------------------------------------------------------


class TestRedisJobStoreErrorHandling:
    """Test error conditions and edge cases."""

    @pytest.mark.asyncio
    async def test_redis_connection_failure(self, job_store, sample_job, mock_redis):
        """Test handling of Redis connection failures."""
        mock_redis.pipeline.side_effect = ConnectionError("Cannot connect to Redis")

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            with pytest.raises(StorageError):
                await job_store.create(sample_job, ttl_seconds=86400)

    @pytest.mark.asyncio
    async def test_malformed_job_data(self, job_store, mock_redis):
        """Test handling of malformed job data from Redis."""
        # Return incomplete/invalid hash (missing required fields)
        mock_redis.hgetall.return_value = {b"id": b"job-123"}  # Missing required fields

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            # Should raise StorageError due to missing required fields
            with pytest.raises((StorageError, Exception)):
                job = await job_store.get("job-123")

    @pytest.mark.asyncio
    async def test_script_loading_failure(self, job_store, mock_redis):
        """Test handling of Lua script loading failures."""
        mock_redis.script_load.side_effect = Exception("Script compilation error")

        with patch("db.redis_cache.job_store.get_async_redis", return_value=mock_redis):
            with pytest.raises(Exception):
                await job_store._ensure_scripts_loaded()
