"""Service layer for jobs business logic."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from db.postgres_control.models import Job, JobEvent
from db.postgres_control.repositories.jobs import JobsRepository
from db.redis_cache import jobs_cache


class JobsService:
    """Service layer for jobs orchestrating PostgreSQL and Redis operations."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db
        self.repo = JobsRepository(db)

    def create_job(
        self,
        owner_sub: str,
        tenant_id: str,
        job_type: str,
        payload: dict,
        idempotency_key: str | None = None,
        priority: int = 0,
    ) -> tuple[Job, bool]:
        """
        Create a new job with idempotency support.

        Args:
            owner_sub: Job owner identifier
            tenant_id: Tenant identifier
            job_type: Type of job
            payload: Job payload
            idempotency_key: Optional idempotency key
            priority: Job priority (default 0)

        Returns:
            Tuple of (Job, is_new) where is_new=True if freshly created,
            is_new=False if idempotent replay
        """
        # Check Redis idempotency cache first (fast path)
        if idempotency_key:
            cached_job_id = jobs_cache.get_idempotency_mapping(owner_sub, idempotency_key)
            if cached_job_id:
                # Idempotent replay - fetch existing job
                job = self.repo.get_job(UUID(cached_job_id))
                if job:
                    return job, False

        # Check PostgreSQL idempotency (authoritative)
        if idempotency_key:
            existing_job = self.repo.find_by_idempotency(owner_sub, idempotency_key)
            if existing_job:
                # Cache in Redis for future fast lookups
                jobs_cache.set_idempotency_mapping(
                    owner_sub,
                    idempotency_key,
                    existing_job.id,
                    ttl_hours=24,
                )
                return existing_job, False

        # Create new job in PostgreSQL
        job = self.repo.create_job(
            owner_sub=owner_sub,
            tenant_id=tenant_id,
            type=job_type,
            payload_json=payload,
            idempotency_key=idempotency_key,
            priority=priority,
        )

        # Push to Redis queue
        jobs_cache.queue_push_job(job_type, job.id, priority)

        # Cache job state in Redis
        jobs_cache.set_job_state(
            job.id,
            job.status,
            owner_sub,
            ttl_seconds=7200,  # 2 hours
        )

        # Cache idempotency mapping in Redis
        if idempotency_key:
            jobs_cache.set_idempotency_mapping(owner_sub, idempotency_key, job.id, ttl_hours=24)

        self.db.commit()
        return job, True

    def get_job(self, job_id: UUID, owner_sub: str | None = None) -> Job | None:
        """
        Get job by ID with optional owner check.

        Args:
            job_id: Job UUID
            owner_sub: Optional owner for access control

        Returns:
            Job or None if not found
        """
        if owner_sub:
            return self.repo.get_job_for_owner(job_id, owner_sub)
        return self.repo.get_job(job_id)

    def list_jobs(
        self,
        owner_sub: str | None = None,
        tenant_id: str | None = None,
        status: list[str] | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[Job], int, bool]:
        """
        List jobs with filtering and pagination.

        Args:
            owner_sub: Filter by owner (None for all)
            tenant_id: Filter by tenant
            status: Filter by status (list of statuses)
            limit: Page size
            offset: Pagination offset

        Returns:
            Tuple of (jobs, total, has_more)
        """
        jobs, total, has_more = self.repo.list_jobs(
            owner_sub=owner_sub,
            tenant_id=tenant_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return jobs, total, has_more

    def compute_list_etag(
        self,
        owner_sub: str | None = None,
        tenant_id: str | None = None,
        status: list[str] | None = None,
    ) -> str:
        """
        Compute ETag for job list.

        Args:
            owner_sub: Owner filter
            tenant_id: Tenant filter
            status: Status filter (list of statuses)

        Returns:
            ETag string
        """
        return self.repo.compute_list_etag(owner_sub=owner_sub, tenant_id=tenant_id, status=status)

    def cancel_job(self, job_id: UUID, owner_sub: str | None = None) -> tuple[Job, bool]:
        """
        Cancel a job (transition to cancelled status).

        Args:
            job_id: Job UUID
            owner_sub: Optional owner for access control

        Returns:
            Tuple of (Job, first_cancel) where first_cancel=True if
            this was the first cancellation attempt
        """
        # Get current job
        if owner_sub:
            job = self.repo.get_job_for_owner(job_id, owner_sub)
        else:
            job = self.repo.get_job(job_id)

        if not job:
            raise ValueError("Job not found")

        # Check if already terminal
        if job.is_terminal():
            return job, False

        # Use atomic Redis cancel if job is queued/running
        first_cancel = jobs_cache.atomic_cancel_if_not_terminal(job_id, ttl_seconds=3600)

        if first_cancel:
            # Transition in PostgreSQL
            updated_job = self.repo.transition_status(
                job_id=job_id,
                from_status=job.status,  # Use actual current status
                to_status="cancelled",
                completed_at=datetime.utcnow(),
                result_json={"cancelled": True},
            )

            if updated_job:
                job = updated_job
                # Update Redis state
                jobs_cache.set_job_state(
                    job_id,
                    "cancelled",
                    job.owner_sub,
                    ttl_seconds=7200,
                )

                self.db.commit()
            else:
                # Transition failed (status mismatch), return current state
                pass

        return job, first_cancel

    def get_events(self, job_id: UUID, after_seq_id: int | None = None, limit: int = 100) -> list[JobEvent]:
        """
        Get events for a job.

        Args:
            job_id: Job UUID
            after_seq_id: Only return events after this sequence ID
            limit: Maximum events to return

        Returns:
            List of JobEvent objects
        """
        # Try Redis cache first
        cached_events = jobs_cache.get_job_events(job_id, after_seq_id=after_seq_id, limit=limit)

        if cached_events:
            # Convert cached events to JobEvent objects (simplified)
            # In production, you'd hydrate from cache or fall back to PG
            pass

        # Fall back to PostgreSQL (authoritative)
        return self.repo.get_events(job_id, after_seq_id=after_seq_id, limit=limit)

    def transition_status(self, job_id: UUID, from_status: str, to_status: str) -> Job | None:
        """
        Transition job status with validation.

        Args:
            job_id: Job UUID
            from_status: Expected current status
            to_status: Target status

        Returns:
            Updated job or None if transition invalid
        """
        job = self.repo.transition_status(job_id, from_status, to_status)
        if job:
            self.db.commit()
        return job

    def append_event(self, job_id: UUID, event_type: str, event_data: dict[str, Any]) -> None:
        """
        Append an event to the job's event log.

        Args:
            job_id: Job UUID
            event_type: Event type (status, log, progress, etc.)
            event_data: Event payload
        """
        self.repo.append_event(job_id, event_type, event_data)
        self.db.commit()

    def delete_job(self, job_id: UUID) -> bool:
        """
        Delete a job and all its events.

        Args:
            job_id: Job UUID

        Returns:
            True if deleted, False if not found
        """
        # Delete from PostgreSQL (cascade to events)
        deleted = self.repo.delete_job(job_id)

        if deleted:
            # Clean up Redis keys
            jobs_cache.cleanup_job_keys(job_id)
            self.db.commit()

        return deleted
