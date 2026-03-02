"""SQLAlchemy ORM models for Builtins Manifests (PostgreSQL authoritative)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.postgres_control.models.tenant import Base


class BuiltinsManifest(Base):
    """Builtins manifests table (authoritative source).

    Stores manifest content, versioning, and state tracking.
    State transitions: staged → active → archived
    Content-based idempotency via sha256 uniqueness.
    """

    __tablename__ = "builtins_manifests"
    __table_args__ = (
        CheckConstraint("state IN ('staged', 'active', 'archived')", name="ck_manifest_state"),
        Index("ix_builtins_manifest_state", "state"),
        Index("ix_builtins_manifest_created_at", "created_at"),
        Index("ix_builtins_manifest_sha256", "sha256", unique=True),
    )

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4, comment="Unique manifest identifier"
    )

    # Source and content
    source_url: Mapped[str] = mapped_column(Text, nullable=False, comment="URL from which manifest was fetched")
    content_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="Full manifest content (array of model definitions)"
    )

    # Content hash (for content-based idempotency)
    sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, comment="SHA256 hash of content (content-based idempotency)"
    )

    # Version metadata
    version: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Optional version tag extracted from manifest"
    )

    # State machine
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Manifest state: 'staged', 'active', or 'archived'"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="Creation timestamp (UTC)",
    )

    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Activation timestamp (UTC, null if never activated)"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
        comment="Last update timestamp (UTC)",
    )

    # Provenance
    created_by_sub: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Subject ID of user who created/staged this manifest"
    )

    # HTTP caching
    etag: Mapped[str] = mapped_column(String(64), nullable=False, comment="ETag for HTTP conditional requests")

    def __repr__(self) -> str:
        return f"<BuiltinsManifest(id={self.id!r}, sha256={self.sha256!r}, state={self.state!r}, version={self.version!r})>"


class BuiltinsActivation(Base):
    """Builtins activations table (activation history).

    Records every manifest activation/rollback event with timestamps and actors.
    Provides audit trail for understanding deployment history.
    """

    __tablename__ = "builtins_activations"
    __table_args__ = (
        Index("ix_builtins_activation_manifest_id", "manifest_id"),
        Index("ix_builtins_activation_activated_at", "activated_at"),
        Index("ix_builtins_activation_activated_by_sub", "activated_by_sub"),
    )

    # Primary key
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="Auto-increment activation ID"
    )

    # Manifest being activated
    manifest_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("builtins_manifests.id", ondelete="CASCADE"),
        nullable=False,
        comment="Manifest that was activated",
    )

    # Activation metadata
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="Activation timestamp (UTC)",
    )

    activated_by_sub: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Subject ID of user who activated"
    )

    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Optional reason for activation")

    # Link to previous active manifest (for rollback support)
    previous_manifest_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("builtins_manifests.id", ondelete="SET NULL"),
        nullable=True,
        comment="Previous active manifest (null for first activation)",
    )

    # Tracing
    trace_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Distributed trace ID for correlation"
    )

    event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Provenance event ID")

    def __repr__(self) -> str:
        return f"<BuiltinsActivation(id={self.id!r}, manifest_id={self.manifest_id!r}, activated_at={self.activated_at!r})>"


class BuiltinsStagingJob(Base):
    """Builtins staging jobs table (idempotency tracking).

    Records staging operations for idempotent replay.
    Unique constraint on (created_by_sub, idempotency_key) ensures exactly-once semantics.
    """

    __tablename__ = "builtins_staging_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('ok', 'error')", name="ck_staging_job_status"),
        UniqueConstraint("created_by_sub", "idempotency_key", name="uq_staging_job_user_key"),
        Index("ix_builtins_staging_job_created_at", "created_at"),
        Index("ix_builtins_staging_job_sha256", "sha256"),
    )

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4, comment="Unique staging job identifier"
    )

    # Idempotency tracking
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, comment="Idempotency key from request header")

    # Source and content hash
    source_url: Mapped[str] = mapped_column(Text, nullable=False, comment="URL from which manifest was fetched")

    sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="SHA256 hash of staged content (null on error)"
    )

    # Job metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="Job creation timestamp (UTC)",
    )

    created_by_sub: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Subject ID of user who initiated staging"
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, comment="Job status: 'ok' or 'error'")

    error_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Error details if status=error"
    )

    def __repr__(self) -> str:
        return f"<BuiltinsStagingJob(id={self.id!r}, status={self.status!r}, sha256={self.sha256!r})>"


class BuiltinsManifestAudit(Base):
    """Builtins manifest audit table (append-only audit trail).

    Records all manifest operations (stage, activate, rollback, delete) for compliance.
    Immutable audit log with distributed tracing support.
    """

    __tablename__ = "builtins_manifest_audit"
    __table_args__ = (
        Index("ix_builtins_audit_manifest_id", "manifest_id"),
        Index("ix_builtins_audit_action", "action"),
        Index("ix_builtins_audit_actor_sub", "actor_sub"),
        Index("ix_builtins_audit_created_at", "created_at"),
    )

    # Primary key
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="Auto-increment audit event ID"
    )

    # Manifest reference (nullable for list operations)
    manifest_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("builtins_manifests.id", ondelete="SET NULL"),
        nullable=True,
        comment="Manifest affected by this event (nullable for list operations)",
    )

    # Action metadata
    action: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Action performed: 'stage', 'activate', 'rollback', 'delete'"
    )

    details_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Event details (state transitions, validation, errors)"
    )

    # Timestamp (immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="Event timestamp (UTC, immutable)",
    )

    # Actor
    actor_sub: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Subject ID of user who performed action"
    )

    # Tracing
    trace_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Distributed trace ID for correlation"
    )

    event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Provenance event ID")

    def __repr__(self) -> str:
        return f"<BuiltinsManifestAudit(id={self.id!r}, action={self.action!r}, manifest_id={self.manifest_id!r}, actor={self.actor_sub!r})>"
