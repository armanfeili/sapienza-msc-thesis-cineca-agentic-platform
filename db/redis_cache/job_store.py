"""
Redis implementations of job storage interfaces.

Uses Redis data structures for scalable, TTL-based job management:
- job:{id} HASH: Job document with auto-expiry
- jobs:all ZSET: Global index (score=created_at epoch ms)
- jobs:owner:{owner} ZSET: Per-user index
- jobs:status:{status} ZSET: Status-based index
- job:{id}:events LIST: SSE ring buffer (capped at SSE_RING_SIZE)
- job:{id}:event_seq COUNTER: Monotonic event IDs
- idem:{owner}:{tenant}:{type}:{hash}:{key} STRING: Idempotency (24h TTL)

Used when JOB_STORE_BACKEND=redis (production).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime

from db.redis_cache.async_client import get_async_redis
from db.redis_cache.lua_scripts import (
    CANCEL_JOB_SCRIPT,
    CLEANUP_ORPHANS_SCRIPT,
    DELETE_JOB_SCRIPT,
    UPDATE_STATUS_SCRIPT,
)
from src.config import settings
from src.jobs.interfaces import (
    EventStore,
    IdempotencyStore,
    JobStore,
    StorageError,
)
from src.jobs.models import JobDocument, JobStatus, SSEEvent

logger = logging.getLogger(__name__)


class RedisJobStore(JobStore):
    """
    Redis-backed job storage with TTL-based auto-expiry.

    Key Schema:
    - job:{id} → HASH with job fields
    - jobs:all → ZSET (score=created_at_ms, member=job_id)
    - jobs:owner:{owner} → ZSET (score=created_at_ms, member=job_id)
    - jobs:status:{status} → ZSET (score=created_at_ms, member=job_id)

    All keys expire after JOB_TTL_DAYS to prevent unbounded growth.
    """

    def __init__(self):
        self._ttl_days = settings.JOB_TTL_DAYS
        # Pre-register Lua scripts for atomic operations
        self._cancel_job_sha = None
        self._update_status_sha = None
        self._cleanup_orphans_sha = None
        self._delete_job_sha = None

    async def _ensure_scripts_loaded(self):
        """Load Lua scripts into Redis on first use (lazy initialization)."""
        if self._cancel_job_sha is None:
            redis = await get_async_redis()
            self._cancel_job_sha = await redis.script_load(CANCEL_JOB_SCRIPT)
            self._update_status_sha = await redis.script_load(UPDATE_STATUS_SCRIPT)
            self._cleanup_orphans_sha = await redis.script_load(CLEANUP_ORPHANS_SCRIPT)
            self._delete_job_sha = await redis.script_load(DELETE_JOB_SCRIPT)
            logger.info(
                "redis.lua_scripts.loaded",
                extra={
                    "cancel_sha": self._cancel_job_sha[:8],
                    "update_sha": self._update_status_sha[:8],
                    "cleanup_sha": self._cleanup_orphans_sha[:8],
                    "delete_sha": self._delete_job_sha[:8],
                },
            )

    async def create(self, job: JobDocument, ttl_seconds: int) -> None:
        """
        Store job in Redis with TTL.

        Creates HASH for job document and adds to all indexes atomically.
        """
        redis = await get_async_redis()
        job_key = f"job:{job.id}"

        # Convert JobDocument to Redis HASH
        hash_dict = job.to_hash_dict()

        # Score for ZSET indexes (created_at as epoch ms for sorting)
        score = int(job.created_at.timestamp() * 1000)

        try:
            # Atomic pipeline: create job + add to indexes
            async with redis.pipeline(transaction=True) as pipe:
                # Store job HASH with TTL
                pipe.hset(job_key, mapping=hash_dict)
                pipe.expire(job_key, ttl_seconds)

                # Add to global index
                pipe.zadd("jobs:all", {job.id: score})
                pipe.expire("jobs:all", ttl_seconds)

                # Add to owner index
                owner_key = f"jobs:owner:{job.owner}"
                pipe.zadd(owner_key, {job.id: score})
                pipe.expire(owner_key, ttl_seconds)

                # Add to status index
                status_key = f"jobs:status:{job.status.value}"
                pipe.zadd(status_key, {job.id: score})
                pipe.expire(status_key, ttl_seconds)

                await pipe.execute()

            logger.debug(
                "redis.job.created",
                extra={
                    "job_id": job.id,
                    "owner": job.owner,
                    "status": job.status.value,
                    "ttl_seconds": ttl_seconds,
                },
            )
        except Exception as e:
            logger.error(f"redis.job.create.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to create job {job.id}: {e}")

    async def get(self, job_id: str) -> JobDocument | None:
        """Retrieve job from Redis."""
        redis = await get_async_redis()
        job_key = f"job:{job_id}"

        try:
            hash_data = await redis.hgetall(job_key)

            if not hash_data:
                return None

            # Convert bytes keys/values to strings
            hash_dict = {
                k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8") if isinstance(v, bytes) else v
                for k, v in hash_data.items()
            }

            return JobDocument.from_hash_dict(hash_dict)

        except Exception as e:
            logger.error(f"redis.job.get.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to get job {job_id}: {e}")

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: dict | None = None,
        error: str | None = None,
        ttl_seconds: int | None = None,
    ) -> bool:
        """
        Atomically update job status.

        Transitions:
        1. Read current status from HASH
        2. Update HASH fields (status, updated_at, result, error)
        3. Move ZSET membership from old status to new status
        4. If terminal, optionally extend TTL

        Returns:
            True if update succeeded, False if job not found
        """
        redis = await get_async_redis()
        job_key = f"job:{job_id}"

        try:
            # Get current job to determine old status
            current_job = await self.get(job_id)
            if not current_job:
                logger.warning(f"redis.job.update_status.not_found: {job_id}")
                return False

            old_status = current_job.status
            updated_at = datetime.utcnow().isoformat()

            # Build update dict
            updates = {
                "status": status.value,
                "updated_at": updated_at,
            }

            if result is not None:
                updates["result"] = json.dumps(result)

            if error is not None:
                updates["error"] = error

            # Atomic pipeline: update HASH + move ZSET membership
            async with redis.pipeline(transaction=True) as pipe:
                # Update HASH fields
                pipe.hset(job_key, mapping=updates)

                # Move from old status index to new status index
                if old_status != status:
                    old_status_key = f"jobs:status:{old_status.value}"
                    new_status_key = f"jobs:status:{status.value}"

                    # Get score from old index
                    pipe.zscore(old_status_key, job_id)

                    # Remove from old index
                    pipe.zrem(old_status_key, job_id)

                    # Will add to new index after getting score

                results = await pipe.execute()

            # If status changed, add to new index with same score
            if old_status != status:
                score = results[-2]  # zscore result
                if score is not None:
                    new_status_key = f"jobs:status:{status.value}"
                    await redis.zadd(new_status_key, {job_id: score})

                    # Refresh TTL on new index
                    if ttl_seconds:
                        await redis.expire(new_status_key, ttl_seconds)

            # Extend TTL if terminal status and ttl_seconds provided
            if status.is_terminal and ttl_seconds:
                await redis.expire(job_key, ttl_seconds)

            logger.debug(
                "redis.job.status_updated",
                extra={
                    "job_id": job_id,
                    "old_status": old_status.value,
                    "new_status": status.value,
                    "terminal": status.is_terminal,
                },
            )

            return True

        except Exception as e:
            logger.error(f"redis.job.update_status.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to update job {job_id} status: {e}")

    async def cancel_job_atomic(
        self,
        job_id: str,
    ) -> bool:
        """
        Atomically cancel a job using Lua CAS (Compare-And-Set).

        Safer than update_status() for concurrent cancellation scenarios.
        Uses Lua script to check status and update in a single atomic operation.

        Returns:
            True if job was cancelled (transitioned from queued/running)
            False if job was already terminal or not found

        Raises:
            StorageError: Redis operation failed
        """
        await self._ensure_scripts_loaded()
        redis = await get_async_redis()
        job_key = f"job:{job_id}"

        try:
            # Execute atomic cancellation Lua script
            result = await redis.evalsha(
                self._cancel_job_sha,
                1,  # numkeys
                job_key,  # KEYS[1]
                datetime.utcnow().isoformat(),  # ARGV[1] = timestamp
                json.dumps({"cancelled": True}),  # ARGV[2] = result
            )

            # Decode result
            result_str = result.decode("utf-8") if isinstance(result, bytes) else result

            if result_str == "cancelled":
                logger.info("redis.job.cancel_atomic.success", extra={"job_id": job_id, "result": "transitioned"})
                return True
            elif result_str == "already_terminal":
                logger.info("redis.job.cancel_atomic.already_terminal", extra={"job_id": job_id})
                return False
            elif result_str == "not_found":
                logger.warning("redis.job.cancel_atomic.not_found", extra={"job_id": job_id})
                return False
            else:
                logger.error(
                    "redis.job.cancel_atomic.unexpected_result", extra={"job_id": job_id, "result": result_str}
                )
                return False

        except Exception as e:
            logger.error(f"redis.job.cancel_atomic.failed: {e}", exc_info=True)
            raise StorageError(f"Atomic cancel failed for job {job_id}: {e}")

    async def list_by_owner(
        self,
        owner: str,
        status: JobStatus | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[list[JobDocument], int]:
        """
        List jobs by owner, newest first.

        Uses jobs:owner:{owner} ZSET if no status filter,
        otherwise intersects with jobs:status:{status}.
        """
        redis = await get_async_redis()

        try:
            owner_key = f"jobs:owner:{owner}"

            if status:
                # Intersect owner + status indexes
                status_key = f"jobs:status:{status.value}"
                temp_key = f"jobs:temp:{owner}:{status.value}:{int(time.time() * 1000)}"

                # ZINTERSTORE with temp key
                await redis.zinterstore(temp_key, [owner_key, status_key])
                await redis.expire(temp_key, 60)  # Clean up after 1 minute

                source_key = temp_key
            else:
                source_key = owner_key

            # Get total count
            total = await redis.zcard(source_key)

            # Get page (ZREVRANGE for newest first, descending by score)
            job_ids = await redis.zrevrange(source_key, offset, offset + limit - 1)

            # Fetch job documents in parallel
            jobs = []
            for job_id_bytes in job_ids:
                job_id = job_id_bytes.decode("utf-8") if isinstance(job_id_bytes, bytes) else job_id_bytes
                job = await self.get(job_id)
                if job:  # Job might have expired between ZRANGE and GET
                    jobs.append(job)

            # Clean up temp key if used
            if status:
                await redis.delete(temp_key)

            return jobs, total

        except Exception as e:
            logger.error(f"redis.job.list_by_owner.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to list jobs for owner {owner}: {e}")

    async def list_all(
        self,
        status: JobStatus | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[list[JobDocument], int]:
        """
        List all jobs (admin view), newest first.

        Uses jobs:all ZSET if no status filter,
        otherwise uses jobs:status:{status}.
        """
        redis = await get_async_redis()

        try:
            source_key = f"jobs:status:{status.value}" if status else "jobs:all"

            # Get total count
            total = await redis.zcard(source_key)

            # Get page (ZREVRANGE for newest first)
            job_ids = await redis.zrevrange(source_key, offset, offset + limit - 1)

            # Fetch job documents in parallel
            jobs = []
            for job_id_bytes in job_ids:
                job_id = job_id_bytes.decode("utf-8") if isinstance(job_id_bytes, bytes) else job_id_bytes
                job = await self.get(job_id)
                if job:  # Job might have expired
                    jobs.append(job)

            return jobs, total

        except Exception as e:
            logger.error(f"redis.job.list_all.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to list all jobs: {e}")

    async def delete(self, job_id: str) -> bool:
        """
        Delete job and all its indexes.

        Removes:
        - job:{id} HASH
        - Entries from jobs:all, jobs:owner:{owner}, jobs:status:{status}
        - job:{id}:events LIST
        - job:{id}:event_seq COUNTER
        """
        redis = await get_async_redis()
        job_key = f"job:{job_id}"

        try:
            # Get job to know owner/status for index cleanup
            job = await self.get(job_id)
            if not job:
                return False

            # Atomic deletion
            async with redis.pipeline(transaction=True) as pipe:
                # Delete job HASH
                pipe.delete(job_key)

                # Remove from indexes
                pipe.zrem("jobs:all", job_id)
                pipe.zrem(f"jobs:owner:{job.owner}", job_id)
                pipe.zrem(f"jobs:status:{job.status.value}", job_id)

                # Delete events and counter
                pipe.delete(f"job:{job_id}:events")
                pipe.delete(f"job:{job_id}:event_seq")

                await pipe.execute()

            logger.debug("redis.job.deleted", extra={"job_id": job_id})
            return True

        except Exception as e:
            logger.error(f"redis.job.delete.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to delete job {job_id}: {e}")

    async def cleanup_orphaned_index_members(
        self,
        index_key: str,
        batch_size: int = 100,
    ) -> int:
        """
        Clean orphaned members from ZSET indexes using Lua script.

        Orphaned members are job IDs in the index whose job HASH no longer exists.
        This can happen due to TTL expiry or manual deletion.

        Args:
            index_key: Redis key for ZSET index (e.g., "jobs:all", "jobs:owner:alice")
            batch_size: Number of members to check per call (default 100)

        Returns:
            Number of orphaned members removed

        Example usage:
            # Clean global index
            removed = await store.cleanup_orphaned_index_members("jobs:all", batch_size=500)

            # Clean per-owner index
            removed = await store.cleanup_orphaned_index_members("jobs:owner:alice")
        """
        await self._ensure_scripts_loaded()
        redis = await get_async_redis()

        try:
            # Execute cleanup Lua script
            removed_count = await redis.evalsha(
                self._cleanup_orphans_sha,
                1,  # numkeys
                index_key,  # KEYS[1]
                batch_size,  # ARGV[1]
            )

            removed = int(removed_count)

            if removed > 0:
                logger.info(
                    "redis.index.cleanup_orphans",
                    extra={
                        "index_key": index_key,
                        "removed_count": removed,
                        "batch_size": batch_size,
                    },
                )

            return removed

        except Exception as e:
            logger.error(f"redis.index.cleanup_orphans.failed: {e}", exc_info=True, extra={"index_key": index_key})
            raise StorageError(f"Failed to cleanup orphans in {index_key}: {e}")


class RedisIdempotencyStore(IdempotencyStore):
    """
    Redis-backed idempotency key storage.

    Key Format: idem:{owner}:{tenant}:{type}:{payload_hash}:{key}
    Value: job_id
    TTL: IDEMPOTENCY_TTL_HOURS (default 24 hours)
    """

    def __init__(self):
        self._ttl_hours = settings.IDEMPOTENCY_TTL_HOURS
        self._ttl_seconds = self._ttl_hours * 3600

    @staticmethod
    def _create_key(
        owner: str,
        tenant: str,
        job_type: str,
        payload: dict,
        idempotency_key: str | None = None,
    ) -> str:
        """
        Generate idempotency key.

        Format: idem:{owner}:{tenant}:{type}:{sha256(payload)[:16]}:{key}
        """
        # Hash payload for deterministic key generation
        payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()[:16]

        # Use provided key or hash
        key_suffix = idempotency_key or payload_hash

        return f"idem:{owner}:{tenant}:{job_type}:{payload_hash}:{key_suffix}"

    async def get_job_id(self, key: str) -> str | None:
        """Check if idempotency key exists and return job_id."""
        redis = await get_async_redis()

        try:
            job_id_bytes = await redis.get(key)
            if job_id_bytes:
                return job_id_bytes.decode("utf-8") if isinstance(job_id_bytes, bytes) else job_id_bytes
            return None
        except Exception as e:
            logger.error(f"redis.idempotency.get.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to check idempotency key: {e}")

    async def store(self, key: str, job_id: str, ttl_seconds: int) -> None:
        """Store idempotency key with TTL."""
        redis = await get_async_redis()

        try:
            await redis.setex(key, ttl_seconds, job_id)
            logger.debug(
                "redis.idempotency.stored",
                extra={
                    "key": key,
                    "job_id": job_id,
                    "ttl_seconds": ttl_seconds,
                },
            )
        except Exception as e:
            logger.error(f"redis.idempotency.store.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to store idempotency key: {e}")


class RedisEventStore(EventStore):
    """
    Redis-backed SSE event storage with ring buffer.

    Key Schema:
    - job:{id}:events → LIST of SSE events (JSON)
    - job:{id}:event_seq → COUNTER for monotonic event IDs

    Ring buffer: LIST is trimmed to SSE_RING_SIZE after each append.
    """

    def __init__(self, ring_size: int = 100):
        self._ring_size = ring_size
        self._ttl_days = settings.JOB_TTL_DAYS
        self._ttl_seconds = self._ttl_days * 86400

    async def append(self, job_id: str, event: SSEEvent, ring_size: int) -> None:
        """
        Append event to ring buffer.

        Uses LPUSH + LTRIM to maintain FIFO ring buffer.
        Newest events at head (index 0).
        """
        redis = await get_async_redis()
        events_key = f"job:{job_id}:events"

        try:
            # Serialize event to JSON
            event_json = event.to_storage_json()

            async with redis.pipeline(transaction=True) as pipe:
                # Prepend event (newest first)
                pipe.lpush(events_key, event_json)

                # Trim to ring_size
                pipe.ltrim(events_key, 0, ring_size - 1)

                # Refresh TTL
                pipe.expire(events_key, self._ttl_seconds)

                await pipe.execute()

            logger.debug(
                "redis.event.appended",
                extra={
                    "job_id": job_id,
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "ring_size": ring_size,
                },
            )
        except Exception as e:
            logger.error(f"redis.event.append.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to append event to job {job_id}: {e}")

    async def get_next_event_id(self, job_id: str) -> int:
        """
        Get next event ID (atomic increment).

        Uses INCR on job:{id}:event_seq counter.
        """
        redis = await get_async_redis()
        seq_key = f"job:{job_id}:event_seq"

        try:
            # INCR is atomic
            event_id = await redis.incr(seq_key)

            # Set TTL if this is the first event
            if event_id == 1:
                await redis.expire(seq_key, self._ttl_seconds)

            return event_id
        except Exception as e:
            logger.error(f"redis.event.seq.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to get next event ID for job {job_id}: {e}")

    async def replay_from(self, job_id: str, last_event_id: int) -> list[SSEEvent]:
        """
        Replay events after last_event_id.

        Returns events with event_id > last_event_id in chronological order.

        Note: Ring buffer may have dropped old events, so gaps are possible.
        Caller should handle "no backlog" comment when gap detected.
        """
        redis = await get_async_redis()
        events_key = f"job:{job_id}:events"

        try:
            # Get all events from LIST (LRANGE 0 -1)
            event_jsons = await redis.lrange(events_key, 0, -1)

            # Parse and filter
            events = []
            for event_json_bytes in reversed(event_jsons):  # Reverse to get chronological order
                event_json = (
                    event_json_bytes.decode("utf-8") if isinstance(event_json_bytes, bytes) else event_json_bytes
                )
                event_dict = json.loads(event_json)

                # Parse SSEEvent
                event = SSEEvent(
                    event_id=event_dict["event_id"],
                    event_type=event_dict["event_type"],
                    data=event_dict["data"],
                )

                # Filter by last_event_id
                if event.event_id > last_event_id:
                    events.append(event)

            # Sort by event_id (should already be sorted, but ensure)
            events.sort(key=lambda e: e.event_id)

            return events

        except Exception as e:
            logger.error(f"redis.event.replay.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to replay events for job {job_id}: {e}")

    async def get_all_events(self, job_id: str) -> list[SSEEvent]:
        """Get all events for a job (for debugging/admin)."""
        redis = await get_async_redis()
        events_key = f"job:{job_id}:events"

        try:
            event_jsons = await redis.lrange(events_key, 0, -1)

            events = []
            for event_json_bytes in reversed(event_jsons):  # Chronological order
                event_json = (
                    event_json_bytes.decode("utf-8") if isinstance(event_json_bytes, bytes) else event_json_bytes
                )
                event_dict = json.loads(event_json)

                events.append(
                    SSEEvent(
                        event_id=event_dict["event_id"],
                        event_type=event_dict["event_type"],
                        data=event_dict["data"],
                    )
                )

            return events

        except Exception as e:
            logger.error(f"redis.event.get_all.failed: {e}", exc_info=True)
            raise StorageError(f"Failed to get all events for job {job_id}: {e}")


def create_idempotency_key(
    owner: str,
    tenant: str,
    job_type: str,
    payload: dict,
    idempotency_key: str | None = None,
) -> str:
    """
    Public helper to generate idempotency keys.

    Format: idem:{owner}:{tenant}:{type}:{sha256(payload)[:16]}:{key}
    """
    return RedisIdempotencyStore._create_key(owner, tenant, job_type, payload, idempotency_key)


__all__ = [
    "RedisEventStore",
    "RedisIdempotencyStore",
    "RedisJobStore",
    "create_idempotency_key",
]
