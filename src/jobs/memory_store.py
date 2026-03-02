"""
In-memory implementations of job storage interfaces.

These implementations wrap the existing in-memory _JOBS dictionary
and provide a clean migration path to Redis.

Used when JOB_STORE_BACKEND=memory (default for testing/development).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from src.jobs.interfaces import (
    EventStore,
    IdempotencyStore,
    JobStore,
)
from src.jobs.models import JobDocument, JobStatus, SSEEvent

# Import the existing global _JOBS dictionary
# We'll refactor this to use the store interface
_JOBS: dict[str, dict[str, Any]] = {}
_IDEMPOTENCY_KEYS: dict[str, str] = {}  # key -> job_id
_EVENTS: dict[str, list[SSEEvent]] = {}  # job_id -> events
_EVENT_SEQ: dict[str, int] = {}  # job_id -> next_event_id


class MemoryJobStore(JobStore):
    """
    In-memory job storage using Python dict.

    This wraps the existing _JOBS dictionary to maintain backward compatibility
    while providing a clean interface for the Redis migration.
    """

    def __init__(self):
        self._jobs = _JOBS

    async def create(self, job: JobDocument, ttl_seconds: int) -> None:
        """Store job in memory (TTL ignored - in-memory has no expiry)."""
        self._jobs[job.id] = {
            "id": job.id,
            "owner_sub": job.owner,
            "metadata": {"tenant": job.tenant_id},
            "type": job.type,
            "status": job.status.value,
            "payload": job.payload,
            "result": job.result,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "error": job.error,
        }

    async def get(self, job_id: str) -> JobDocument | None:
        """Retrieve job from memory."""
        job_dict = self._jobs.get(job_id)
        if not job_dict:
            return None

        return JobDocument(
            id=job_dict["id"],
            owner=job_dict.get("owner_sub", ""),
            tenant_id=job_dict.get("metadata", {}).get("tenant", "global"),
            type=job_dict.get("type", ""),
            status=JobStatus(job_dict.get("status", "queued")),
            payload=job_dict.get("payload", {}),
            result=job_dict.get("result"),
            created_at=datetime.fromisoformat(job_dict["created_at"]),
            updated_at=datetime.fromisoformat(job_dict["updated_at"]) if job_dict.get("updated_at") else None,
            error=job_dict.get("error"),
        )

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: dict | None = None,
        error: str | None = None,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Update job status in memory."""
        job_dict = self._jobs.get(job_id)
        if not job_dict:
            return False

        job_dict["status"] = status.value
        job_dict["updated_at"] = datetime.utcnow().isoformat()

        if result is not None:
            job_dict["result"] = result

        if error is not None:
            job_dict["error"] = error

        return True

    async def list_by_owner(
        self,
        owner: str,
        status: JobStatus | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[list[JobDocument], int]:
        """List jobs by owner, newest first."""
        # Filter jobs by owner
        filtered = []
        for job_dict in self._jobs.values():
            if job_dict.get("owner_sub") != owner:
                continue
            if status and job_dict.get("status") != status.value:
                continue
            filtered.append(job_dict)

        # Sort by created_at descending
        filtered.sort(key=lambda j: (j.get("created_at", ""), j["id"]), reverse=True)

        total = len(filtered)
        page = filtered[offset : offset + limit]

        # Convert to JobDocument
        jobs = []
        for job_dict in page:
            jobs.append(
                JobDocument(
                    id=job_dict["id"],
                    owner=job_dict.get("owner_sub", ""),
                    tenant_id=job_dict.get("metadata", {}).get("tenant", "global"),
                    type=job_dict.get("type", ""),
                    status=JobStatus(job_dict.get("status", "queued")),
                    payload=job_dict.get("payload", {}),
                    result=job_dict.get("result"),
                    created_at=datetime.fromisoformat(job_dict["created_at"]),
                    updated_at=datetime.fromisoformat(job_dict["updated_at"]) if job_dict.get("updated_at") else None,
                    error=job_dict.get("error"),
                )
            )

        return jobs, total

    async def list_all(
        self,
        status: JobStatus | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[list[JobDocument], int]:
        """List all jobs (admin view), newest first."""
        # Filter jobs by status if provided
        filtered = []
        for job_dict in self._jobs.values():
            if status and job_dict.get("status") != status.value:
                continue
            filtered.append(job_dict)

        # Sort by created_at descending
        filtered.sort(key=lambda j: (j.get("created_at", ""), j["id"]), reverse=True)

        total = len(filtered)
        page = filtered[offset : offset + limit]

        # Convert to JobDocument
        jobs = []
        for job_dict in page:
            jobs.append(
                JobDocument(
                    id=job_dict["id"],
                    owner=job_dict.get("owner_sub", ""),
                    tenant_id=job_dict.get("metadata", {}).get("tenant", "global"),
                    type=job_dict.get("type", ""),
                    status=JobStatus(job_dict.get("status", "queued")),
                    payload=job_dict.get("payload", {}),
                    result=job_dict.get("result"),
                    created_at=datetime.fromisoformat(job_dict["created_at"]),
                    updated_at=datetime.fromisoformat(job_dict["updated_at"]) if job_dict.get("updated_at") else None,
                    error=job_dict.get("error"),
                )
            )

        return jobs, total

    async def delete(self, job_id: str) -> bool:
        """Delete job from memory."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            # Clean up events and sequences
            _EVENTS.pop(job_id, None)
            _EVENT_SEQ.pop(job_id, None)
            return True
        return False


class MemoryIdempotencyStore(IdempotencyStore):
    """In-memory idempotency key storage."""

    def __init__(self):
        self._keys = _IDEMPOTENCY_KEYS

    async def get_job_id(self, key: str) -> str | None:
        """Check if idempotency key exists."""
        return self._keys.get(key)

    async def store(self, key: str, job_id: str, ttl_seconds: int) -> None:
        """Store idempotency key (TTL ignored in memory)."""
        self._keys[key] = job_id


class MemoryEventStore(EventStore):
    """In-memory SSE event storage."""

    def __init__(self, ring_size: int = 100):
        self._events = _EVENTS
        self._seq = _EVENT_SEQ
        self._ring_size = ring_size

    async def append(self, job_id: str, event: SSEEvent, ring_size: int) -> None:
        """Append event to ring buffer."""
        if job_id not in self._events:
            self._events[job_id] = []

        self._events[job_id].append(event)

        # Trim to ring_size
        if len(self._events[job_id]) > ring_size:
            self._events[job_id] = self._events[job_id][-ring_size:]

    async def get_next_event_id(self, job_id: str) -> int:
        """Get next event ID."""
        if job_id not in self._seq:
            self._seq[job_id] = 1
        else:
            self._seq[job_id] += 1
        return self._seq[job_id]

    async def replay_from(self, job_id: str, last_event_id: int) -> list[SSEEvent]:
        """Replay events after last_event_id."""
        events = self._events.get(job_id, [])
        return [e for e in events if e.event_id > last_event_id]

    async def get_all_events(self, job_id: str) -> list[SSEEvent]:
        """Get all events for a job."""
        return self._events.get(job_id, [])


def create_idempotency_key(
    owner: str,
    tenant: str,
    job_type: str,
    payload: dict,
    idempotency_key: str | None = None,
) -> str:
    """
    Generate idempotency key from request context.

    Format: idem:{owner}:{tenant}:{type}:{sha256(payload)}:{key}

    Args:
        owner: Job owner (JWT sub)
        tenant: Tenant ID
        job_type: Job type
        payload: Job payload (for hashing)
        idempotency_key: Optional user-provided key

    Returns:
        Idempotency key for storage
    """
    import json

    # Hash payload for deterministic key generation
    payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()[:16]

    # Use provided key or hash
    key_suffix = idempotency_key or payload_hash

    return f"idem:{owner}:{tenant}:{job_type}:{payload_hash}:{key_suffix}"


__all__ = [
    "MemoryEventStore",
    "MemoryIdempotencyStore",
    "MemoryJobStore",
    "create_idempotency_key",
]
