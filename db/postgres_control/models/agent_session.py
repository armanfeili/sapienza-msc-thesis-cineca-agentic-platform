"""Agent session model for PostgreSQL storage."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.postgres_control.database import Base


class AgentSession(Base):
    """
    AgentSession represents a stateful agent interaction.

    Sessions progress through states: active → completed/cancelled/failed
    """

    __tablename__ = "agent_sessions"

    session_id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    # Session state
    status = Column(String(50), nullable=False, default="active", server_default="active", index=True)

    # Agent configuration
    manager = Column(String(255), nullable=True)
    preferred_workers = Column(JSONB, nullable=True)  # List of worker names
    llm_preferences = Column(JSONB, nullable=True)  # Dict of tool/action -> LLM name
    agent_role = Column(String(255), nullable=True)
    tools = Column(JSONB, nullable=True)  # List of allowed tool names
    temperature = Column(Float, nullable=False, default=0.2)
    max_steps = Column(Integer, nullable=False, default=8)

    # Metadata and tracking
    session_metadata = Column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Link to last step (for quick access)
    last_step_id = Column(PGUUID(as_uuid=True), ForeignKey("agent_steps.step_id", ondelete="SET NULL"), nullable=True)
    last_step_seq = Column(Integer, nullable=True)

    # ETag for HTTP caching
    etag = Column(String(64))

    # Relationships
    steps = relationship(
        "AgentStep",
        back_populates="session",
        foreign_keys="AgentStep.session_id",
        cascade="all, delete-orphan",
        order_by="AgentStep.seq",
    )
    runs = relationship("AgentRun", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed', 'cancelled', 'failed')", name="agent_sessions_status_check"),
        Index("idx_agent_sessions_user_created", "user_id", "created_at"),
        Index("idx_agent_sessions_tenant_created", "tenant_id", "created_at"),
        Index("idx_agent_sessions_status", "status"),
    )

    def compute_etag(self) -> str:
        """
        Compute ETag from session_id, status, and updated_at.

        Returns:
            Hex string of MD5 hash
        """
        # Handle case where updated_at might not be set yet
        updated_str = self.updated_at.isoformat() if self.updated_at else "pending"
        components = f"{self.session_id}:{self.status}:{updated_str}"
        return hashlib.md5(components.encode()).hexdigest()

    def update_etag(self) -> None:
        """Update the etag field with freshly computed value."""
        self.etag = self.compute_etag()

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary representation."""
        return {
            "session_id": str(self.session_id),
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "status": self.status,
            "manager": self.manager,
            "preferred_workers": self.preferred_workers,
            "llm_preferences": self.llm_preferences,
            "agent_role": self.agent_role,
            "tools": self.tools,
            "temperature": self.temperature,
            "max_steps": self.max_steps,
            "metadata": self.session_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_step_id": str(self.last_step_id) if self.last_step_id else None,
            "etag": self.etag,
        }
