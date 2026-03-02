"""
SQLAlchemy ORM models for model instances.

Provides type-safe access to model_instances, model_instance_events, and model_defaults tables.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.postgres_control.models.tenant import Base


class ModelInstance(Base):
    """Model instance registry (PostgreSQL authoritative)."""

    __tablename__ = "model_instances"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    tenant_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Tenant scope (null for global)"
    )
    instance_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Human-readable instance name")
    provider_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, comment="FK to providers table"
    )
    model_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Model identifier (e.g., gpt-4, claude-3)"
    )
    model_uri: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Optional model URI/path")
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", comment="Instance administratively enabled"
    )
    loaded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", comment="Instance loaded in runtime"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", comment="Marked as default (deprecated, use model_defaults)"
    )
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Maximum context window size")
    modalities: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Supported modalities (chat, completion, embedding, etc.)"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Instance description")
    parameters: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Model parameters (temperature, max_tokens, etc.)"
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()", onupdate="now()"
    )
    etag: Mapped[str] = mapped_column(String(64), nullable=False, comment="ETag for HTTP caching")

    # Relationships
    events: Mapped[list[ModelInstanceEvent]] = relationship(
        "ModelInstanceEvent", back_populates="instance", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "instance_name", name="uq_model_instances_tenant_name"),
        Index("ix_model_instances_tenant_created", "tenant_id", "created_at"),
        Index("ix_model_instances_provider_loaded", "provider_id", "loaded", "created_at"),
        Index("ix_model_instances_enabled", "enabled"),
    )


class ModelInstanceEvent(Base):
    """Model instance event log (append-only)."""

    __tablename__ = "model_instance_events"

    seq_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instance_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("model_instances.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK to model_instances",
    )
    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Event type (load, unload, test, update, delete)"
    )
    event_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Event payload/context")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default="now()")
    actor_sub: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="User subject who triggered event"
    )
    trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Correlation/trace ID")

    # Relationships
    instance: Mapped[ModelInstance] = relationship("ModelInstance", back_populates="events")

    __table_args__ = (
        Index("ix_model_instance_events_instance", "instance_id", "created_at"),
        Index("ix_model_instance_events_type", "event_type", "created_at"),
        Index("ix_model_instance_events_actor", "actor_sub", "created_at"),
    )


class ModelDefault(Base):
    """Default model instance per scope (global or tenant)."""

    __tablename__ = "model_defaults"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="Primary key")
    scope: Mapped[str] = mapped_column(String(20), nullable=False, comment="Scope: 'global' or 'tenant'")
    tenant_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Tenant ID (null for global scope)"
    )
    instance_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("model_instances.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK to model_instances",
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()", onupdate="now()"
    )
    etag: Mapped[str] = mapped_column(String(64), nullable=False, comment="ETag for HTTP caching")

    __table_args__ = (
        CheckConstraint("scope IN ('global', 'tenant')", name="ck_model_defaults_scope"),
        CheckConstraint(
            "(scope = 'global' AND tenant_id IS NULL) OR (scope = 'tenant' AND tenant_id IS NOT NULL)",
            name="ck_model_defaults_scope_tenant",
        ),
        Index("ix_model_defaults_instance", "instance_id"),
    )
