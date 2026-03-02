"""
Storage interfaces for job management.

These abstract base classes define the contract for job persistence,
enabling easy migration from Redis to Postgres or other backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.jobs.models import JobDocument, JobStatus, SSEEvent


class JobStore(ABC):
    """
    Abstract interface for job document storage.

    Implementations: RedisJobStore, PostgresJobStore (future)
    """

    @abstractmethod
    async def create(
        self,
        job: JobDocument,
        ttl_seconds: int,
    ) -> None:
        """
        Persist a new job with automatic expiry.

        Args:
            job: Job document to store
            ttl_seconds: Auto-expiry time (e.g., 10 days * 86400)

        Raises:
            StorageError: If persistence fails
        """
        pass

    @abstractmethod
    async def get(self, job_id: str) -> JobDocument | None:
        """
        Retrieve job by ID.

        Returns:
            JobDocument if found, None if expired/not found
        """
        pass

    @abstractmethod
    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: dict | None = None,
        error: str | None = None,
        ttl_seconds: int | None = None,
    ) -> bool:
        """
        Atomically update job status and optional result/error.

        Also refreshes TTL if provided.

        Returns:
            True if updated, False if job not found
        """
        pass

    @abstractmethod
    async def list_by_owner(
        self,
        owner: str,
        status: JobStatus | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[list[JobDocument], int]:
        """
        List jobs for a specific owner, newest first.

        Args:
            owner: Owner subject from JWT
            status: Optional status filter
            offset: Pagination offset
            limit: Page size

        Returns:
            (jobs, total_count)
        """
        pass

    @abstractmethod
    async def list_all(
        self,
        status: JobStatus | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[list[JobDocument], int]:
        """
        List all jobs (admin view), newest first.

        Returns:
            (jobs, total_count)
        """
        pass

    @abstractmethod
    async def delete(self, job_id: str) -> bool:
        """
        Delete job and all associated indices.

        Returns:
            True if deleted, False if not found
        """
        pass


class IdempotencyStore(ABC):
    """
    Abstract interface for idempotency key management.

    Ensures duplicate POST requests return the same job_id.
    """

    @abstractmethod
    async def get_job_id(self, key: str) -> str | None:
        """
        Check if idempotency key exists and return associated job_id.

        Returns:
            job_id if key exists and not expired, None otherwise
        """
        pass

    @abstractmethod
    async def store(self, key: str, job_id: str, ttl_seconds: int) -> None:
        """
        Store idempotency key pointing to job_id with expiry.

        Args:
            key: Idempotency key (hashed from request context)
            job_id: Associated job identifier
            ttl_seconds: How long to remember this mapping
        """
        pass


class EventStore(ABC):
    """
    Abstract interface for SSE event management.

    Stores events in a ring buffer for Last-Event-ID resume support.
    """

    @abstractmethod
    async def append(
        self,
        job_id: str,
        event: SSEEvent,
        ring_size: int,
    ) -> None:
        """
        Append event to job's ring buffer, capping at ring_size.

        Args:
            job_id: Job identifier
            event: Event to append
            ring_size: Max events to retain (e.g., 100)
        """
        pass

    @abstractmethod
    async def get_next_event_id(self, job_id: str) -> int:
        """
        Get next monotonic event ID for this job.

        Returns:
            Next sequence number (1-based)
        """
        pass

    @abstractmethod
    async def replay_from(
        self,
        job_id: str,
        last_event_id: int,
    ) -> list[SSEEvent]:
        """
        Retrieve events with event_id > last_event_id.

        If gap exists (events rotated out), returns empty list or
        partial results - caller should emit gap comment.

        Returns:
            List of events in chronological order
        """
        pass

    @abstractmethod
    async def get_all_events(self, job_id: str) -> list[SSEEvent]:
        """
        Get all buffered events for a job (for debugging/testing).

        Returns:
            All events in ring buffer, oldest to newest
        """
        pass


class StorageError(Exception):
    """Base exception for storage layer errors."""

    pass


class JobNotFoundError(StorageError):
    """Raised when job doesn't exist or has expired."""

    pass


class IdempotencyConflictError(StorageError):
    """Raised when idempotency key already exists with different job_id."""

    pass
