"""JobEvent model for audit trail of job state changes."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.postgres_control.database import Base


class JobEvent(Base):
    """
    JobEvent records state changes and significant events in a job's lifecycle.

    Event types:
    - status: Status transition (queued→running, running→finished, etc.)
    - log: Worker log message
    - progress: Progress update (percentage, step, etc.)
    - heartbeat: Worker keepalive signal
    - end: Final event marking job completion
    """

    __tablename__ = "job_events"

    seq_id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_id = Column(PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    event_json = Column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationship
    job = relationship("Job", back_populates="events")

    __table_args__ = (
        Index("idx_job_events_job_seq", "job_id", "seq_id"),
        Index("idx_job_events_created", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for API responses."""
        return {
            "seq_id": self.seq_id,
            "job_id": str(self.job_id),
            "event_type": self.event_type,
            "event_data": self.event_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_sse_event(self) -> str:
        """
        Format event as Server-Sent Event (SSE) message.

        Returns:
            SSE-formatted string with id, event type, and data
        """
        lines = [
            f"id: {self.seq_id}",
            f"event: {self.event_type}",
            f"data: {self.event_json}",
            "",  # Empty line terminates the event
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<JobEvent(seq_id={self.seq_id}, job_id={self.job_id}, type={self.event_type})>"
