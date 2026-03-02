"""
PostgreSQL models for built-in process lifecycle tracking and manifest activation history.

Tables:
- builtin_manifest_activation_history: Timeline of manifest stage/activate/rollback operations
- builtin_process_events: Audit trail of process lifecycle events (start/stop/heartbeat/exit/signal)
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from db.postgres_control.database import Base


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(UTC)


# ---------------- Enums ----------------
class ManifestStatus(str, enum.Enum):
    """Status of a manifest activation operation."""

    STAGED = "staged"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class ProcessEvent(str, enum.Enum):
    """Type of process lifecycle event."""

    START = "start"
    HEARTBEAT = "heartbeat"
    STOP = "stop"
    EXIT = "exit"
    SIGNAL = "signal"


# ---------------- Models ----------------
class BuiltinManifestActivationHistory(Base):
    """
    Persistent timeline of built-in manifest activation operations.

    Each row represents a stage/activate/rollback/failure event for a specific
    manifest version. Used by GET /admin/processes/history/manifests.
    """

    __tablename__ = "builtin_manifest_activation_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False)
    manifest_name = Column(String(255), nullable=False, index=True)
    version = Column(String(100), nullable=False)
    activated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    activated_by = Column(Text, nullable=True)  # user sub or system identifier
    status = Column(
        Enum(ManifestStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
        default=ManifestStatus.STAGED,
    )
    notes = Column(Text, nullable=True)  # optional context/reason

    __table_args__ = (
        Index("ix_builtin_manifest_name_activated_at", "manifest_name", "activated_at"),
        Index("ix_builtin_manifest_status", "status"),
    )

    def __repr__(self):
        return f"<ManifestActivation {self.manifest_name}@{self.version} {self.status} at {self.activated_at}>"


class BuiltinProcessEvent(Base):
    """
    Audit trail of built-in process lifecycle events.

    Each row captures a single event (start/heartbeat/stop/exit/signal) for a process.
    Enables reconstruction of "what ran when" and powers GET /admin/processes/history/processes.

    Heartbeats may be compressed (e.g., bucketed by minute) to avoid excessive rows.
    """

    __tablename__ = "builtin_process_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False)
    process_id = Column(String(255), nullable=False, index=True)  # stable identifier across restarts
    artifact = Column(String(255), nullable=False, index=True)  # e.g., "llama3-8b", "whisper-large"
    pid = Column(Integer, nullable=True, index=True)  # OS process ID
    port = Column(Integer, nullable=True)  # listening port if applicable
    event = Column(Enum(ProcessEvent, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    reason = Column(Text, nullable=True)  # e.g., "admin_stop", "oom_killed", "graceful_shutdown"
    exit_code = Column(Integer, nullable=True)  # only for EXIT events
    ts = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    tenant_id = Column(String(255), nullable=True, index=True)  # multi-tenancy support
    manifest_version = Column(String(100), nullable=True)  # manifest version that started this process
    host = Column(String(255), nullable=True)  # hostname/pod for distributed deployments

    __table_args__ = (
        Index("ix_builtin_process_ts", "ts"),
        Index("ix_builtin_process_artifact_ts", "artifact", "ts"),
        Index("ix_builtin_process_pid_ts", "pid", "ts"),
        Index("ix_builtin_process_process_id", "process_id"),
        Index("ix_builtin_process_tenant_id", "tenant_id"),
    )

    def __repr__(self):
        return f"<ProcessEvent {self.artifact} pid={self.pid} {self.event} at {self.ts}>"


__all__ = [
    "BuiltinManifestActivationHistory",
    "BuiltinProcessEvent",
    "ManifestStatus",
    "ProcessEvent",
]
