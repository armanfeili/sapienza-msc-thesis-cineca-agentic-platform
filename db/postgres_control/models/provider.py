"""SQLAlchemy ORM models for LLM Providers (PostgreSQL authoritative)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.postgres_control.models.tenant import Base


class Provider(Base):
    """Provider registry table (authoritative source).

    Stores all provider metadata including type, base_url, model, tenant scope.
    Secrets (api_key) are stored separately in ProviderSecret.
    Config JSON is stored as-is, supporting arbitrary provider-specific keys.
    """

    __tablename__ = "providers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_provider_tenant_name"),
        Index("ix_provider_tenant_id", "tenant_id"),
        Index("ix_provider_type", "type"),
        Index("ix_provider_created_at", "created_at"),
    )

    # Primary key
    id: Mapped[str] = mapped_column(String(255), primary_key=True, comment="Unique provider identifier")

    # Core fields
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Human-friendly provider name")
    type: Mapped[str] = mapped_column(String(50), nullable=False, comment="Provider type (openai_compatible, custom)")
    base_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="HTTP base URL for the provider"
    )
    model: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Default model identifier")

    # Multi-tenancy
    tenant_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Tenant scope (null for global)"
    )

    # Config (arbitrary provider-specific JSON, extra='allow' semantics)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Provider-specific configuration (redacted view in API, secrets masked)"
    )

    # Boolean indicators for API responses (computed from ProviderSecret)
    has_api_key: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Whether api_key is configured"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="Creation timestamp (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
        comment="Last update timestamp (UTC)",
    )

    def __repr__(self) -> str:
        return f"<Provider(id={self.id!r}, name={self.name!r}, type={self.type!r}, tenant_id={self.tenant_id!r})>"


class ProviderSecret(Base):
    """Provider secrets table (encrypted storage, never returned in API).

    Stores sensitive credentials separately from main provider record.
    Encrypted at rest (application-level or database-level encryption).
    """

    __tablename__ = "provider_secrets"
    __table_args__ = (Index("ix_provider_secret_created_at", "created_at"),)

    # Foreign key to provider
    provider_id: Mapped[str] = mapped_column(
        String(255), primary_key=True, comment="Provider identifier (references providers.id)"
    )

    # Encrypted secret (never exposed in API)
    api_key_encrypted: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Encrypted API key (NEVER returned in API responses)"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="Creation timestamp (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
        comment="Last update timestamp (UTC)",
    )

    def __repr__(self) -> str:
        return f"<ProviderSecret(provider_id={self.provider_id!r}, has_key={bool(self.api_key_encrypted)})>"


class ProviderDefault(Base):
    """Provider defaults table (global and tenant-scoped).

    Stores default provider selections per scope (e.g., 'chat') and tenant.
    Resolution precedence: tenant-scoped > global.
    """

    __tablename__ = "provider_defaults"
    __table_args__ = (
        UniqueConstraint("scope", "tenant_id", name="uq_provider_default_scope_tenant"),
        Index("ix_provider_default_tenant_id", "tenant_id"),
        Index("ix_provider_default_provider_id", "provider_id"),
    )

    # Composite key: scope + tenant_id
    scope: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="Default scope (e.g., 'chat', 'embedding')"
    )
    tenant_id: Mapped[str] = mapped_column(
        String(255), primary_key=True, default="global", comment="Tenant scope ('global' for global default)"
    )

    # Provider reference
    provider_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Provider identifier (references providers.id)"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="Creation timestamp (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
        comment="Last update timestamp (UTC)",
    )

    def __repr__(self) -> str:
        return (
            f"<ProviderDefault(scope={self.scope!r}, tenant_id={self.tenant_id!r}, provider_id={self.provider_id!r})>"
        )


class ProviderAuditEvent(Base):
    """Provider audit events table (append-only audit trail).

    Records all changes to providers, secrets, and defaults for compliance and debugging.
    Never deleted, only inserted.
    """

    __tablename__ = "provider_audit_events"
    __table_args__ = (
        Index("ix_provider_audit_provider_id", "provider_id"),
        Index("ix_provider_audit_actor", "actor"),
        Index("ix_provider_audit_action", "action"),
        Index("ix_provider_audit_created_at", "created_at"),
        Index("ix_provider_audit_tenant_id", "tenant_id"),
    )

    # Auto-increment primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="Auto-increment event ID")

    # Event context
    provider_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Provider affected by this event (nullable for list/query operations)"
    )
    actor: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Principal who performed the action (username, service account)"
    )
    action: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Action performed (register, patch, delete, set_default, clear_default)"
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Tenant context (if applicable)"
    )

    # Event payload (before/after snapshots, diff, etc.)
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Event details (before/after, diff, validation errors, etc.)"
    )

    # Provenance correlation
    trace_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Distributed trace ID for correlation"
    )
    event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Provenance event ID")

    # Timestamp (immutable, append-only)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="Event timestamp (UTC, immutable)",
    )

    def __repr__(self) -> str:
        return f"<ProviderAuditEvent(id={self.id}, action={self.action!r}, provider_id={self.provider_id!r}, actor={self.actor!r})>"
