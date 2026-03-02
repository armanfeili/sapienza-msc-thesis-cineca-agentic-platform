"""
Domain models for Job management.

These models are storage-agnostic and represent the core business entities.
They can be persisted to Redis, Postgres, or any other backend.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer


class JobStatus(str, Enum):
    """Job lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Check if this status is a terminal state."""
        return self in (JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELLED)


class JobDocument(BaseModel):
    """
    Core job entity - storage-agnostic domain model.

    This model represents the immutable aspects of a job and can be
    serialized to/from any backend (Redis HASH, Postgres row, etc.).

    All timestamps are in UTC ISO8601 format for consistency.
    """

    id: str = Field(..., description="Unique job identifier (UUID)")
    owner: str = Field(..., description="Owner subject (from JWT sub claim)")
    tenant_id: str = Field(..., description="Tenant identifier for multi-tenancy")
    type: str = Field(..., description="Job type (e.g., 'demo', 'training')")
    status: JobStatus = Field(default=JobStatus.QUEUED, description="Current job status")
    payload: dict[str, Any] = Field(default_factory=dict, description="Job input parameters")
    result: dict[str, Any] | None = Field(default=None, description="Job output (set on completion)")
    created_at: Annotated[
        datetime, 
        PlainSerializer(lambda v: v.isoformat() if v else None, return_type=str, when_used='json')
    ] = Field(..., description="Job creation timestamp (UTC)")
    updated_at: Annotated[
        datetime | None, 
        PlainSerializer(lambda v: v.isoformat() if v else None, return_type=str, when_used='json')
    ] = Field(default=None, description="Last status change timestamp (UTC)")
    error: str | None = Field(default=None, description="Error message if status=failed")

    model_config = ConfigDict()

    def to_hash_dict(self) -> dict[str, str]:
        """
        Convert to flat string dict for Redis HASH storage.

        All complex types (dict, datetime) are JSON-encoded.
        This ensures clean separation between domain and storage.
        """
        import json

        return {
            "id": self.id,
            "owner": self.owner,
            "tenant_id": self.tenant_id,
            "type": self.type,
            "status": self.status.value,
            "payload": json.dumps(self.payload),
            "result": json.dumps(self.result) if self.result else "",
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
            "error": self.error or "",
        }

    @classmethod
    def from_hash_dict(cls, data: dict[str, str | bytes]) -> JobDocument:
        """
        Reconstruct from Redis HASH.

        Handles both str and bytes (Redis returns bytes in some clients).
        """
        import json

        def decode(v: str | bytes) -> str:
            return v.decode("utf-8") if isinstance(v, bytes) else v

        def parse_json(v: str) -> Any:
            return json.loads(v) if v else None

        def parse_datetime(v: str) -> datetime | None:
            return datetime.fromisoformat(v) if v else None

        return cls(
            id=decode(data["id"]),
            owner=decode(data["owner"]),
            tenant_id=decode(data["tenant_id"]),
            type=decode(data["type"]),
            status=JobStatus(decode(data["status"])),
            payload=parse_json(decode(data["payload"])),
            result=parse_json(decode(data.get("result", ""))) if data.get("result") else None,
            created_at=parse_datetime(decode(data["created_at"])),  # type: ignore
            updated_at=parse_datetime(decode(data.get("updated_at", ""))),
            error=decode(data.get("error", "")) or None,
        )


class SSEEvent(BaseModel):
    """
    Server-Sent Event for job status updates.

    Stored in job:{id}:events ring buffer for Last-Event-ID resume.
    """

    event_id: int = Field(..., description="Monotonic event sequence number")
    event_type: str = Field(..., description="Event type: 'status', 'end', 'error'")
    data: dict[str, Any] = Field(..., description="Event payload (job_id, status, etc.)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event emission time (UTC)")

    def to_sse_format(self) -> str:
        """
        Format as SSE wire protocol.

        Example:
            id: 42
            event: status
            data: {"job_id": "123", "status": "running"}
        """
        import json

        lines = [
            f"id: {self.event_id}",
            f"event: {self.event_type}",
            f"data: {json.dumps(self.data)}",
            "",  # SSE requires blank line
        ]
        return "\n".join(lines)

    def to_storage_json(self) -> str:
        """Serialize for Redis LIST storage."""
        import json

        return json.dumps(
            {
                "event_id": self.event_id,
                "event_type": self.event_type,
                "data": self.data,
                "timestamp": self.timestamp.isoformat(),
            }
        )

    @classmethod
    def from_storage_json(cls, s: str | bytes) -> SSEEvent:
        """Deserialize from Redis LIST."""
        import json

        data = json.loads(s if isinstance(s, str) else s.decode("utf-8"))
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            data=data["data"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


class JobCreateRequest(BaseModel):
    """Request to create a new job (from POST /jobs)."""

    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    owner: str  # From JWT
    tenant_id: str  # From request context


class JobUpdateRequest(BaseModel):
    """Request to update job status (from workers)."""

    status: JobStatus
    result: dict[str, Any] | None = None
    error: str | None = None
