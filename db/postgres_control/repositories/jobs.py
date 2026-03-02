"""Repository for jobs data access operations."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from db.postgres_control.models.job import Job
from db.postgres_control.models.job_event import JobEvent


class JobsRepository:
    """Repository for jobs and job events CRUD operations."""

    def __init__(self, session: Session):
        self.session = session

    def create_job(
        self,
        *,
        owner_sub: str,
        tenant_id: str,
        type: str,
        payload_json: dict[str, Any],
        idempotency_key: str | None = None,
        priority: int = 0,
    ) -> Job:
        """
        Create a new job in queued status.

        Args:
            owner_sub: User/service identifier
            tenant_id: Tenant identifier
            type: Job type (e.g., 'agent.run', 'export.data')
            payload_json: Job payload/parameters
            idempotency_key: Optional key for idempotent job creation
            priority: Job priority (higher = more urgent)

        Returns:
            Newly created Job instance with etag computed

        Raises:
            IntegrityError: If idempotency_key already exists for this owner
        """
        job = Job(
            type=type,
            status="queued",
            owner_sub=owner_sub,
            tenant_id=tenant_id,
            payload_json=payload_json,
            idempotency_key=idempotency_key,
            priority=priority,
        )

        self.session.add(job)
        self.session.flush()  # Get the ID

        # Compute and set etag
        job.update_etag()

        # Create initial event
        self.append_event(
            job_id=job.id,
            event_type="status",
            event_json={
                "from": None,
                "to": "queued",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        return job

    def get_job(self, job_id: UUID) -> Job | None:
        """
        Retrieve job by ID.

        Args:
            job_id: Job UUID

        Returns:
            Job instance or None if not found
        """
        return self.session.query(Job).filter(Job.id == job_id).first()

    def get_job_for_owner(self, job_id: UUID, owner_sub: str) -> Job | None:
        """
        Retrieve job by ID, ensuring it belongs to the specified owner.

        Args:
            job_id: Job UUID
            owner_sub: Owner identifier for authorization

        Returns:
            Job instance or None if not found or not owned
        """
        return self.session.query(Job).filter(Job.id == job_id, Job.owner_sub == owner_sub).first()

    def find_by_idempotency(self, owner_sub: str, idempotency_key: str) -> Job | None:
        """
        Find job by owner and idempotency key.

        Args:
            owner_sub: Owner identifier
            idempotency_key: Idempotency key

        Returns:
            Job instance or None if not found
        """
        return (
            self.session.query(Job).filter(Job.owner_sub == owner_sub, Job.idempotency_key == idempotency_key).first()
        )

    def list_jobs(
        self,
        *,
        owner_sub: str | None = None,
        tenant_id: str | None = None,
        status: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Job], int, bool]:
        """
        List jobs with filtering and pagination.

        Args:
            owner_sub: Filter by owner (None for admin queries)
            tenant_id: Filter by tenant
            status: Filter by status list (e.g., ['queued', 'running'])
            limit: Maximum results to return
            offset: Number of records to skip

        Returns:
            Tuple of (jobs list, total count, has_more flag)
        """
        query = self.session.query(Job)

        # Apply filters
        if owner_sub:
            query = query.filter(Job.owner_sub == owner_sub)
        if tenant_id:
            query = query.filter(Job.tenant_id == tenant_id)
        if status:
            query = query.filter(Job.status.in_(status))

        # Get total count
        total = query.count()

        # Apply pagination and ordering (newest first)
        jobs = query.order_by(desc(Job.created_at)).offset(offset).limit(limit).all()

        has_more = (offset + len(jobs)) < total

        return jobs, total, has_more

    def transition_status(
        self,
        job_id: UUID,
        from_status: str | None,
        to_status: str,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        result_json: dict[str, Any] | None = None,
        error_json: dict[str, Any] | None = None,
    ) -> Job | None:
        """
        Transition job status with timestamp and latency computation.

        Args:
            job_id: Job UUID
            from_status: Expected current status (for safety, can be None to skip check)
            to_status: New status
            started_at: Timestamp when job started (for running state)
            completed_at: Timestamp when job completed (for terminal states)
            result_json: Result data (for finished state)
            error_json: Error data (for failed state)

        Returns:
            Updated Job instance or None if not found or status check failed
        """
        job = self.get_job(job_id)
        if not job:
            return None

        # Verify current status if from_status is specified
        if from_status and job.status != from_status:
            return None  # Status mismatch, refuse transition

        old_status = job.status
        job.status = to_status

        # Update timestamps
        if started_at:
            job.started_at = started_at
            # Compute queue latency (created → started)
            if job.created_at:
                delta = (started_at - job.created_at).total_seconds() * 1000
                job.queue_latency_ms = int(delta)

        if completed_at:
            job.completed_at = completed_at
            # Compute execution latency (started → completed)
            if job.started_at:
                delta = (completed_at - job.started_at).total_seconds() * 1000
                job.exec_latency_ms = int(delta)

        # Update result or error
        if result_json is not None:
            job.result_json = result_json
        if error_json is not None:
            job.error_json = error_json

        # Update etag
        job.update_etag()

        # Append status transition event
        self.append_event(
            job_id=job_id,
            event_type="status",
            event_json={
                "from": old_status,
                "to": to_status,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        return job

    def append_event(self, job_id: UUID, event_type: str, event_json: dict[str, Any]) -> JobEvent:
        """
        Append an event to the job's audit trail.

        Args:
            job_id: Job UUID
            event_type: Event type (status, log, progress, heartbeat, end)
            event_json: Event data

        Returns:
            Created JobEvent instance
        """
        event = JobEvent(
            job_id=job_id,
            event_type=event_type,
            event_json=event_json,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def get_events(self, job_id: UUID, *, after_seq_id: int | None = None, limit: int = 100) -> list[JobEvent]:
        """
        Get events for a job, optionally after a specific sequence ID.

        Args:
            job_id: Job UUID
            after_seq_id: Only return events with seq_id > this value
            limit: Maximum events to return

        Returns:
            List of JobEvent instances ordered by seq_id
        """
        query = self.session.query(JobEvent).filter(JobEvent.job_id == job_id)

        if after_seq_id is not None:
            query = query.filter(JobEvent.seq_id > after_seq_id)

        return query.order_by(JobEvent.seq_id).limit(limit).all()

    def compute_list_etag(self, owner_sub: str | None, tenant_id: str | None, status: list[str] | None) -> str:
        """
        Compute ETag for a jobs list query based on latest update and filters.

        Args:
            owner_sub: Owner filter
            tenant_id: Tenant filter
            status: Status filter

        Returns:
            MD5 hex digest as ETag
        """
        query = self.session.query(func.max(Job.updated_at))

        if owner_sub:
            query = query.filter(Job.owner_sub == owner_sub)
        if tenant_id:
            query = query.filter(Job.tenant_id == tenant_id)
        if status:
            query = query.filter(Job.status.in_(status))

        max_updated = query.scalar()

        # Combine latest timestamp with filter criteria
        filter_key = f"{owner_sub}:{tenant_id}:{','.join(sorted(status)) if status else ''}"
        timestamp_str = max_updated.isoformat() if max_updated else "empty"
        components = f"{timestamp_str}:{filter_key}"

        return hashlib.md5(components.encode()).hexdigest()

    def update_job_result(self, job_id: UUID, result_json: dict[str, Any]) -> Job | None:
        """
        Update job result data.

        Args:
            job_id: Job UUID
            result_json: Result data to store

        Returns:
            Updated Job instance or None if not found
        """
        job = self.get_job(job_id)
        if not job:
            return None

        job.result_json = result_json
        job.update_etag()
        return job

    def update_job_error(self, job_id: UUID, error: str) -> Job | None:
        """
        Update job error message.

        Args:
            job_id: Job UUID
            error: Error message

        Returns:
            Updated Job instance or None if not found
        """
        job = self.get_job(job_id)
        if not job:
            return None

        job.error_json = {"message": error}
        job.update_etag()
        return job

    def touch_job(self, job_id: UUID) -> Job | None:
        """
        Update job's updated_at timestamp (heartbeat).

        Args:
            job_id: Job UUID

        Returns:
            Updated Job instance or None if not found
        """
        job = self.get_job(job_id)
        if not job:
            return None

        # SQLAlchemy will auto-update updated_at on flush/commit
        job.update_etag()
        self.session.flush()
        return job

    def delete_job(self, job_id: UUID) -> bool:
        """
        Delete a job and its events (cascade).

        Args:
            job_id: Job UUID

        Returns:
            True if deleted, False if not found
        """
        job = self.get_job(job_id)
        if not job:
            return False

        self.session.delete(job)
        return True
