"""Create provider tables (PostgreSQL authoritative for providers)

Revision ID: 004
Revises: 003
Create Date: 2025-10-12 16:00:00.000000

Implements PostgreSQL-backed provider registry with:
- providers: Main provider metadata (type, base_url, model, tenant_id, config_json)
- provider_secrets: Encrypted API keys (never returned in API)
- provider_defaults: Default provider per scope/tenant (resolution precedence)
- provider_audit_events: Append-only audit trail for all provider changes

Redis serves as cache layer with short TTLs, invalidated on every write.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create provider tables with PostgreSQL as authoritative source."""

    # 1) providers table (main registry)
    op.create_table(
        "providers",
        sa.Column("id", sa.String(255), primary_key=True, comment="Unique provider identifier"),
        sa.Column("name", sa.String(255), nullable=False, comment="Human-friendly provider name"),
        sa.Column("type", sa.String(50), nullable=False, comment="Provider type (openai_compatible, custom)"),
        sa.Column("base_url", sa.String(512), nullable=True, comment="HTTP base URL for the provider"),
        sa.Column("model", sa.String(255), nullable=True, comment="Default model identifier"),
        sa.Column("tenant_id", sa.String(255), nullable=True, comment="Tenant scope (null for global)"),
        sa.Column(
            "config_json", postgresql.JSONB, nullable=True, comment="Provider-specific configuration (redacted in API)"
        ),
        sa.Column(
            "has_api_key", sa.Boolean, nullable=False, server_default="false", comment="Whether api_key is configured"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Last update timestamp (UTC)",
        ),
    )

    # Unique constraint: (tenant_id, name) - same name allowed across tenants
    op.create_unique_constraint("uq_provider_tenant_name", "providers", ["tenant_id", "name"])

    # Indexes for common queries
    op.create_index("ix_provider_tenant_id", "providers", ["tenant_id"])
    op.create_index("ix_provider_type", "providers", ["type"])
    op.create_index("ix_provider_created_at", "providers", ["created_at"])

    # 2) provider_secrets table (encrypted API keys, never exposed in API)
    op.create_table(
        "provider_secrets",
        sa.Column(
            "provider_id", sa.String(255), primary_key=True, comment="Provider identifier (references providers.id)"
        ),
        sa.Column(
            "api_key_encrypted", sa.Text, nullable=True, comment="Encrypted API key (NEVER returned in API responses)"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Last update timestamp (UTC)",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["providers.id"], name="provider_secrets_provider_id_fkey", ondelete="CASCADE"
        ),
    )

    op.create_index("ix_provider_secret_created_at", "provider_secrets", ["created_at"])

    # 3) provider_defaults table (global and tenant-scoped defaults)
    op.create_table(
        "provider_defaults",
        sa.Column("scope", sa.String(50), primary_key=True, comment="Default scope (e.g., 'chat', 'embedding')"),
        sa.Column(
            "tenant_id",
            sa.String(255),
            primary_key=True,
            server_default="global",
            comment="Tenant scope ('global' for global default)",
        ),
        sa.Column(
            "provider_id", sa.String(255), nullable=False, comment="Provider identifier (references providers.id)"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Last update timestamp (UTC)",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["providers.id"], name="provider_defaults_provider_id_fkey", ondelete="CASCADE"
        ),
    )

    # Unique constraint on (scope, tenant_id) - one default per scope per tenant
    op.create_unique_constraint("uq_provider_default_scope_tenant", "provider_defaults", ["scope", "tenant_id"])

    # Indexes for resolution queries
    op.create_index("ix_provider_default_tenant_id", "provider_defaults", ["tenant_id"])
    op.create_index("ix_provider_default_provider_id", "provider_defaults", ["provider_id"])

    # 4) provider_audit_events table (append-only audit trail)
    op.create_table(
        "provider_audit_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True, comment="Auto-increment event ID"),
        sa.Column(
            "provider_id",
            sa.String(255),
            nullable=True,
            comment="Provider affected by this event (nullable for list/query ops)",
        ),
        sa.Column(
            "actor",
            sa.String(255),
            nullable=False,
            comment="Principal who performed the action (username, service account)",
        ),
        sa.Column(
            "action",
            sa.String(100),
            nullable=False,
            comment="Action performed (register, patch, delete, set_default, clear_default)",
        ),
        sa.Column("tenant_id", sa.String(255), nullable=True, comment="Tenant context (if applicable)"),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=True,
            comment="Event details (before/after, diff, validation errors, etc.)",
        ),
        sa.Column("trace_id", sa.String(255), nullable=True, comment="Distributed trace ID for correlation"),
        sa.Column("event_id", sa.String(255), nullable=True, comment="Provenance event ID"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Event timestamp (UTC, immutable)",
        ),
    )

    # Indexes for audit queries
    op.create_index("ix_provider_audit_provider_id", "provider_audit_events", ["provider_id"])
    op.create_index("ix_provider_audit_actor", "provider_audit_events", ["actor"])
    op.create_index("ix_provider_audit_action", "provider_audit_events", ["action"])
    op.create_index("ix_provider_audit_created_at", "provider_audit_events", ["created_at"])
    op.create_index("ix_provider_audit_tenant_id", "provider_audit_events", ["tenant_id"])


def downgrade() -> None:
    """Drop provider tables (reverse migration)."""

    # Drop in reverse order (respecting foreign key constraints)
    op.drop_table("provider_audit_events")
    op.drop_table("provider_defaults")
    op.drop_table("provider_secrets")
    op.drop_table("providers")
