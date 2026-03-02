"""
SQLAlchemy ORM model for ToolAuditEvent entity.

Defines the tool_audit_events table schema for tracking invocation state changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.postgres_control.database import Base


class ToolAuditEvent(Base):
    """
    ToolAuditEvent ORM model.

    Represents an audit event for a tool invocation (e.g., status change, result stored).
    """

    __tablename__ = "tool_audit_events"

    # Primary key (auto-incrementing)
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="Auto-incrementing event ID"
    )

    # Foreign key to tool_invocations
    eid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("tool_invocations.eid", name="fk_tool_audit_events_eid", ondelete="CASCADE"),
        nullable=False,
        comment="Execution ID this event relates to",
    )

    # Event metadata
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of audit event (e.g., invocation_started, status_changed, result_stored)",
    )

    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, comment="Event-specific data as JSON")

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="Event timestamp"
    )

    # Relationships
    # invocation: Mapped["ToolInvocation"] = relationship(
    #     "ToolInvocation",
    #     back_populates="audit_events"
    # )

    # Table constraints
    __table_args__ = (
        # Index on eid for fast lookup of events by execution
        Index(
            "ix_tool_audit_events_eid",
            eid,
        ),
        # Composite index for ordered event retrieval
        Index(
            "ix_tool_audit_events_eid_created_at",
            eid,
            created_at,
        ),
        {"comment": "Audit trail for tool invocations"},
    )

    def __repr__(self) -> str:
        return f"<ToolAuditEvent(id={self.id!r}, eid={self.eid!r}, event_type={self.event_type!r})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "eid": self.eid,
            "event_type": self.event_type,
            "payload": self.payload_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
