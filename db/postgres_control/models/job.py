"""Job model for PostgreSQL storage."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.postgres_control.database import Base


class Job(Base):
    """
    Job represents an asynchronous task in the system.

    Jobs progress through states: queued → running → finished/failed/cancelled
    """

    __tablename__ = "jobs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    type = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="queued", server_default="queued")
    owner_sub = Column(String(255), nullable=False, index=True)
    tenant_id = Column(
        String(255), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )  # Nullable for internal M2M jobs

    # Job data
    payload_json = Column(JSONB, nullable=False, default=dict, server_default="{}")
    result_json = Column(JSONB)
    error_json = Column(JSONB)

    # Idempotency and priority
    idempotency_key = Column(String(255), index=True)
    priority = Column(Integer, nullable=False, default=0, server_default="0")

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Performance metrics
    queue_latency_ms = Column(Integer)
    exec_latency_ms = Column(Integer)

    # ETag for HTTP caching
    etag = Column(String(64))

    # Relationships
    events = relationship("JobEvent", back_populates="job", cascade="all, delete-orphan", order_by="JobEvent.seq_id")

    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'finished', 'failed', 'cancelled')", name="jobs_status_check"),
        Index(
            "idx_jobs_idempotency_unique",
            "owner_sub",
            "idempotency_key",
            unique=True,
            postgresql_where="idempotency_key IS NOT NULL",
        ),
        Index("idx_jobs_owner_created", "owner_sub", "created_at"),
        Index("idx_jobs_status_created", "status", "created_at"),
        Index("idx_jobs_tenant_created", "tenant_id", "created_at"),
        Index("idx_jobs_updated", "updated_at"),
    )

    def compute_etag(self) -> str:
        """
        Compute ETag from job id, status, and updated_at.

        Returns:
            Hex string of MD5 hash
        """
        components = f"{self.id}:{self.status}:{self.updated_at.isoformat()}"
        return hashlib.md5(components.encode()).hexdigest()

    def update_etag(self) -> None:
        """Update the etag field with freshly computed value."""
        self.etag = self.compute_etag()

    def to_dict(self, include_payload: bool = False, include_result: bool = True) -> dict[str, Any]:
        """
        Convert job to dictionary representation.

        Args:
            include_payload: Whether to include full payload_json (can be large)
            include_result: Whether to include result_json/error_json

        Returns:
            Dictionary with job fields
        """
        data = {
            "id": str(self.id),
            "type": self.type,
            "status": self.status,
            "owner_sub": self.owner_sub,
            "tenant_id": self.tenant_id,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "queue_latency_ms": self.queue_latency_ms,
            "exec_latency_ms": self.exec_latency_ms,
        }

        if include_payload:
            data["payload"] = self.payload_json
        else:
            # Just include payload summary (type info or size)
            data["payload_summary"] = {
                "keys": list(self.payload_json.keys()) if isinstance(self.payload_json, dict) else None,
                "size_bytes": len(str(self.payload_json)) if self.payload_json else 0,
            }

        if include_result:
            data["result"] = self.result_json
            data["error"] = self.error_json

        return data

    def is_terminal(self) -> bool:
        """Check if job is in a terminal state (finished, failed, or cancelled)."""
        return self.status in ("finished", "failed", "cancelled")

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, type={self.type}, status={self.status}, owner={self.owner_sub})>"
