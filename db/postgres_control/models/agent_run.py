"""Agent run model for PostgreSQL storage."""

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
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.postgres_control.database import Base


class AgentRun(Base):
    """
    AgentRun represents a single execution/invocation of an agent.

    Runs can be one-shot or bound to a session, and track the model used,
    performance metrics, and execution status.
    """

    __tablename__ = "agent_runs"

    run_id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    session_id = Column(
        PGUUID(as_uuid=True), ForeignKey("agent_sessions.session_id", ondelete="CASCADE"), nullable=True, index=True
    )

    user_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    # Model and manager used (legacy fields - kept for backward compatibility)
    model = Column(String(255), nullable=True)
    manager = Column(String(255), nullable=True)
    
    # Model configuration (populated from DB default at run creation)
    model_instance_name = Column(String(255), nullable=True, comment="Human-readable instance name (e.g., phi3-mini)")
    model_id = Column(String(255), nullable=True, comment="Provider-specific model ID (e.g., phi3:mini)")
    provider_name = Column(String(255), nullable=True, comment="Provider name (e.g., ollama-local)")
    provider_id = Column(String(255), ForeignKey("providers.id", ondelete="SET NULL"), nullable=True, index=True)
    config_source = Column(String(50), nullable=True, comment="Source of model config (db_default, env_fallback, etc.)")

    # Performance metrics
    latency_ms = Column(Integer, nullable=True)

    # Tracing identifiers
    trace_id = Column(String(255), nullable=True, index=True)
    request_id = Column(String(255), nullable=True, index=True)  # HTTP request ID correlation
    event_id = Column(String(255), nullable=True, index=True)

    # Run status
    status = Column(String(50), nullable=False, default="queued", server_default="queued")
    
    # LLM error tracking (Task C.10)
    llm_error_type = Column(String(100), nullable=True, comment="Type: timeout, context_length, rate_limit, connection, validation, unknown")
    llm_error_message = Column(Text, nullable=True, comment="Detailed error message from LLM provider")
    llm_error_occurred_at = Column(DateTime(timezone=True), nullable=True, comment="Timestamp when LLM error occurred")

    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)

    # Execution data (JSONB columns)
    todos = Column(JSONB, nullable=True, server_default="[]")
    steps = Column(JSONB, nullable=True, server_default="[]")
    output = Column(JSONB, nullable=True)  # Changed from Text to JSONB for structured data
    warnings = Column(JSONB, nullable=True, server_default="[]")  # Non-fatal warnings during execution
    metrics = Column(JSONB, nullable=True)  # Execution metrics: overall_ms, llm calls, tool calls
    # Arbitrary metadata (mirrors request metadata; named run_metadata to avoid clashing with SQLAlchemy Base.metadata)
    run_metadata = Column("metadata", JSONB, nullable=False, server_default="{}")

    # Relationships
    session = relationship("AgentSession", back_populates="runs")

    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="agent_runs_status_check"),
        Index("idx_agent_runs_user_started", "user_id", "started_at"),
        Index("idx_agent_runs_session_started", "session_id", "started_at"),
        Index("idx_agent_runs_tenant_user_started", "tenant_id", "user_id", "started_at"),
        Index("idx_agent_runs_tenant_session_started", "tenant_id", "session_id", "started_at"),
        Index("idx_agent_runs_status_started", "status", "started_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert run to dictionary representation."""
        # Compute degraded/used_fallback from metrics
        metrics = self.metrics or {}
        llm_attempted = metrics.get("llm_attempted_calls", 0)
        llm_successful = metrics.get("llm_successful_calls", 0)
        # Degraded if LLM was attempted but some failed
        degraded = bool(llm_attempted > 0 and llm_successful < llm_attempted)
        # Used fallback if LLM was attempted and all failed
        used_fallback = bool(llm_attempted > 0 and llm_successful == 0)
        
        return {
            "run_id": str(self.run_id),
            "session_id": str(self.session_id) if self.session_id else None,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "model": self.model,
            "manager": self.manager,
            # New model config fields
            "model_instance_name": self.model_instance_name,
            "model_id": self.model_id,
            "provider_name": self.provider_name,
            "provider_id": self.provider_id,
            "config_source": self.config_source,
            # Performance and tracing
            "latency_ms": self.latency_ms,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "event_id": self.event_id,
            "status": self.status,
            # LLM error tracking
            "llm_error_type": self.llm_error_type,
            "llm_error_message": self.llm_error_message,
            "llm_error_occurred_at": self.llm_error_occurred_at.isoformat() if self.llm_error_occurred_at else None,
            # Timestamps
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "todos": self.todos if self.todos else [],
            "steps": self.steps if self.steps else [],
            "output": self.output,
            "warnings": self.warnings if self.warnings else [],
            "metrics": self.metrics,
            "metadata": self.run_metadata or {},
            # Degraded/fallback flags (computed from metrics)
            "degraded": degraded if degraded else None,
            "used_fallback": used_fallback if used_fallback else None,
        }
