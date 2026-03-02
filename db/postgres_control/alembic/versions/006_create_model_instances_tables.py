"""Create model instances tables (PostgreSQL authoritative for model instances)

Revision ID: 006
Revises: 005
Create Date: 2025-10-13 00:00:00.000000

Implements PostgreSQL-backed model instance management with:
- model_instances: Registry of loaded model instances per tenant
- model_instance_events: Event log for instance lifecycle (load/unload/test)
- model_defaults: Global and per-tenant default model selections

Redis serves as cache layer with TTLs, invalidated on instance mutations.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create model instances tables with PostgreSQL as authoritative source."""

    # 1) model_instances table (main instance registry)
    op.create_table(
        "model_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.String(255), nullable=True, comment="Tenant scope (null for global)"),
        sa.Column("instance_name", sa.String(255), nullable=False, comment="Human-readable instance name"),
        sa.Column("provider_id", sa.String(255), nullable=False, comment="FK to providers table"),
        sa.Column("model_id", sa.String(255), nullable=False, comment="Model identifier (e.g., gpt-4, claude-3)"),
        sa.Column("model_uri", sa.Text, nullable=True, comment="Optional model URI/path"),
        sa.Column(
            "enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
            comment="Instance administratively enabled",
        ),
        sa.Column(
            "loaded", sa.Boolean, nullable=False, server_default=sa.text("false"), comment="Instance loaded in runtime"
        ),
        sa.Column(
            "is_default",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Marked as default (deprecated, use model_defaults)",
        ),
        sa.Column("context_window", sa.Integer, nullable=True, comment="Maximum context window size"),
        sa.Column(
            "modalities",
            postgresql.JSONB,
            nullable=True,
            comment="Supported modalities (chat, completion, embedding, etc.)",
        ),
        sa.Column("description", sa.Text, nullable=True, comment="Instance description"),
        sa.Column(
            "parameters", postgresql.JSONB, nullable=True, comment="Model parameters (temperature, max_tokens, etc.)"
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("etag", sa.String(64), nullable=False, comment="ETag for HTTP caching"),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["providers.id"], ondelete="CASCADE", name="fk_model_instances_provider"
        ),
        sa.UniqueConstraint("tenant_id", "instance_name", name="uq_model_instances_tenant_name"),
        comment="Model instance registry (PostgreSQL authoritative)",
    )

    # Indexes for efficient queries
    op.create_index("ix_model_instances_tenant_created", "model_instances", ["tenant_id", sa.text("created_at DESC")])
    op.create_index(
        "ix_model_instances_provider_loaded",
        "model_instances",
        ["provider_id", sa.text("loaded DESC"), sa.text("created_at DESC")],
    )
    op.create_index("ix_model_instances_enabled", "model_instances", ["enabled"])

    # 2) model_instance_events table (audit/event log)
    op.create_table(
        "model_instance_events",
        sa.Column("seq_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("instance_id", postgresql.UUID(as_uuid=True), nullable=False, comment="FK to model_instances"),
        sa.Column(
            "event_type", sa.String(100), nullable=False, comment="Event type (load, unload, test, update, delete)"
        ),
        sa.Column("event_json", postgresql.JSONB, nullable=True, comment="Event payload/context"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actor_sub", sa.String(255), nullable=True, comment="User subject who triggered event"),
        sa.Column("trace_id", sa.String(255), nullable=True, comment="Correlation/trace ID"),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["model_instances.id"], ondelete="CASCADE", name="fk_model_instance_events_instance"
        ),
        comment="Model instance event log (append-only)",
    )

    # Indexes for event queries
    op.create_index(
        "ix_model_instance_events_instance", "model_instance_events", ["instance_id", sa.text("created_at DESC")]
    )
    op.create_index(
        "ix_model_instance_events_type", "model_instance_events", ["event_type", sa.text("created_at DESC")]
    )
    op.create_index(
        "ix_model_instance_events_actor", "model_instance_events", ["actor_sub", sa.text("created_at DESC")]
    )

    # 3) model_defaults table (default model selection)
    op.create_table(
        "model_defaults",
        sa.Column("scope", sa.String(20), nullable=False, comment="Scope: 'global' or 'tenant'"),
        sa.Column("tenant_id", sa.String(255), nullable=True, comment="Tenant ID (null for global scope)"),
        sa.Column("instance_id", postgresql.UUID(as_uuid=True), nullable=False, comment="FK to model_instances"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("etag", sa.String(64), nullable=False, comment="ETag for HTTP caching"),
        sa.ForeignKeyConstraint(
            ["instance_id"], ["model_instances.id"], ondelete="CASCADE", name="fk_model_defaults_instance"
        ),
        sa.PrimaryKeyConstraint("scope", "tenant_id", name="pk_model_defaults"),
        sa.CheckConstraint("scope IN ('global', 'tenant')", name="ck_model_defaults_scope"),
        sa.CheckConstraint(
            "(scope = 'global' AND tenant_id IS NULL) OR (scope = 'tenant' AND tenant_id IS NOT NULL)",
            name="ck_model_defaults_scope_tenant",
        ),
        comment="Default model instance per scope (global or tenant)",
    )

    # Index for efficient default lookups
    op.create_index("ix_model_defaults_instance", "model_defaults", ["instance_id"])


def downgrade() -> None:
    """Drop model instances tables."""
    op.drop_table("model_defaults")
    op.drop_table("model_instance_events")
    op.drop_table("model_instances")
