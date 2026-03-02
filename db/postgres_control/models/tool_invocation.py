"""
SQLAlchemy ORM model for ToolInvocation entity.

Defines the tool_invocations table schema with idempotency and audit trail.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.postgres_control.database import Base


class ToolInvocation(Base):
    """
    ToolInvocation ORM model.

    Represents a tool execution with idempotency, status tracking, and audit trail.
    """

    __tablename__ = "tool_invocations"

    # Primary key (execution ID)
    eid: Mapped[str] = mapped_column(Text, primary_key=True, comment="Unique execution ID (UUID)")

    # Tool identification
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Name of the invoked tool")

    tool_version: Mapped[str] = mapped_column(String(50), nullable=False, comment="Version of the invoked tool")

    # Tenant association
    tenant_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("tenants.id", name="fk_tool_invocations_tenant"),
        nullable=False,
        comment="Tenant executing the tool",
    )

    # Execution status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Invocation status (pending/running/finished/failed/cancelled)"
    )

    # Input/output data (JSONB)
    params_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, comment="Tool input parameters as JSON")

    result_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="Tool output result as JSON"
    )

    error_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="Error details if failed"
    )

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Invocation start timestamp",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Invocation completion timestamp"
    )

    # Idempotency and audit fields
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Client-provided idempotency key"
    )

    requested_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="User or service that requested the invocation"
    )

    request_headers: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="Relevant request headers (e.g., User-Agent, X-Request-ID)"
    )

    latency_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Execution latency in milliseconds"
    )

    # Relationships
    # audit_events: Mapped[list["ToolAuditEvent"]] = relationship(
    #     "ToolAuditEvent",
    #     back_populates="invocation",
    #     cascade="all, delete-orphan"
    # )

    # Table constraints
    __table_args__ = (
        # Index on status for filtering
        Index(
            "ix_tool_invocations_status",
            status,
        ),
        # Unique sparse index on idempotency_key (only non-NULL values)
        Index(
            "ix_tool_invocations_idempotency_key_unique",
            idempotency_key,
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        # Composite index for pagination (tenant_id, started_at DESC)
        Index(
            "ix_tool_invocations_tenant_started_desc",
            tenant_id,
            text("started_at DESC"),
        ),
        # Index on tool_name for filtering by tool
        Index(
            "ix_tool_invocations_tool_name",
            tool_name,
        ),
        # Check constraint for valid status values
        CheckConstraint(
            "status IN ('pending', 'running', 'finished', 'failed', 'cancelled')", name="ck_tool_invocations_status"
        ),
        {"comment": "Tool invocation executions with idempotency and audit trail"},
    )

    def __repr__(self) -> str:
        return f"<ToolInvocation(eid={self.eid!r}, tool={self.tool_name!r}, status={self.status!r})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "eid": self.eid,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "tenant_id": self.tenant_id,
            "status": self.status,
            "params": self.params_json,
            "result": self.result_json,
            "error": self.error_json,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "idempotency_key": self.idempotency_key,
            "requested_by": self.requested_by,
            "request_headers": self.request_headers,
            "latency_ms": self.latency_ms,
        }
