"""Agent step model for PostgreSQL storage."""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.postgres_control.database import Base


class AgentStep(Base):
    """
    AgentStep represents a single step in an agent session.

    Steps are sequentially numbered within a session and track the progression
    of user messages, agent responses, tool calls, and system events.
    """

    __tablename__ = "agent_steps"

    step_id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    session_id = Column(
        PGUUID(as_uuid=True), ForeignKey("agent_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Monotonic sequence number per session (allocated via Redis INCR)
    seq = Column(Integer, nullable=False)

    # Step type and content
    type = Column(String(50), nullable=False)  # message, user, assistant, tool, system, error
    message = Column(Text, nullable=True)
    tool = Column(String(255), nullable=True)

    # Structured input/output
    input = Column(JSONB, nullable=True)
    output = Column(JSONB, nullable=True)

    # Step status
    status = Column(String(50), nullable=False, default="queued", server_default="queued")

    # Error information (if failed)
    error = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    session = relationship("AgentSession", back_populates="steps", foreign_keys=[session_id])

    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_agent_steps_session_seq"),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')", name="agent_steps_status_check"
        ),
        CheckConstraint(
            "type IN ('message', 'user', 'assistant', 'tool', 'system', 'error')", name="agent_steps_type_check"
        ),
        Index("idx_agent_steps_session_seq", "session_id", "seq"),
        Index("idx_agent_steps_session_created", "session_id", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert step to dictionary representation."""
        return {
            "step_id": str(self.step_id),
            "session_id": str(self.session_id),
            "seq": self.seq,
            "type": self.type,
            "message": self.message,
            "tool": self.tool,
            "input": self.input,
            "output": self.output,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
