"""Create tools tables - tools, tool_invocations, tool_audit_events

Revision ID: 002
Revises: 001
Create Date: 2025-12-11 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tools, tool_invocations, and tool_audit_events tables with constraints and indexes."""

    # Create tools table
    op.create_table(
        "tools",
        sa.Column("id", sa.Text(), nullable=False, comment="Unique tool identifier (UUID)"),
        sa.Column("name", sa.String(length=255), nullable=False, comment="Tool name"),
        sa.Column("version", sa.String(length=50), nullable=False, comment="Tool version (semver)"),
        sa.Column("description", sa.Text(), nullable=True, comment="Tool description"),
        sa.Column(
            "input_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="JSON schema for tool inputs",
        ),
        sa.Column(
            "output_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="JSON schema for tool outputs",
        ),
        sa.Column("owner_tenant_id", sa.Text(), nullable=False, comment="Owning tenant ID"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="Last update timestamp",
        ),
        sa.Column(
            "version_number",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Version number for optimistic locking",
        ),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 255", name="ck_tools_name_length"),
        sa.CheckConstraint("char_length(version) BETWEEN 1 AND 50", name="ck_tools_version_length"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_tenant_id"], ["tenants.id"], name="fk_tools_owner_tenant"),
        comment="Tool definitions with schemas and versioning",
    )

    # Create unique constraint on (name, version)
    op.create_index("ix_tools_name_version_unique", "tools", ["name", "version"], unique=True)

    # Index on owner_tenant_id for tenant-scoped queries
    op.create_index("ix_tools_owner_tenant_id", "tools", ["owner_tenant_id"], unique=False)

    # Create tool_invocations table
    op.create_table(
        "tool_invocations",
        sa.Column("eid", sa.Text(), nullable=False, comment="Unique execution ID (UUID)"),
        sa.Column("tool_name", sa.String(length=255), nullable=False, comment="Name of the invoked tool"),
        sa.Column("tool_version", sa.String(length=50), nullable=False, comment="Version of the invoked tool"),
        sa.Column("tenant_id", sa.Text(), nullable=False, comment="Tenant executing the tool"),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            comment="Invocation status (pending/running/finished/failed/cancelled)",
        ),
        sa.Column(
            "params_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Tool input parameters as JSON",
        ),
        sa.Column(
            "result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Tool output result as JSON"
        ),
        sa.Column(
            "error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Error details if failed"
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="Invocation start timestamp",
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True, comment="Invocation completion timestamp"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True, comment="Client-provided idempotency key"),
        sa.Column(
            "requested_by",
            sa.String(length=255),
            nullable=True,
            comment="User or service that requested the invocation",
        ),
        sa.Column(
            "request_headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Relevant request headers (e.g., User-Agent, X-Request-ID)",
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True, comment="Execution latency in milliseconds"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'finished', 'failed', 'cancelled')", name="ck_tool_invocations_status"
        ),
        sa.PrimaryKeyConstraint("eid"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_tool_invocations_tenant"),
        comment="Tool invocation executions with idempotency and audit trail",
    )

    # Index on status for filtering by status
    op.create_index("ix_tool_invocations_status", "tool_invocations", ["status"], unique=False)

    # Unique index on idempotency_key (sparse - only non-NULL values)
    op.create_index(
        "ix_tool_invocations_idempotency_key_unique",
        "tool_invocations",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # Composite index on (tenant_id, started_at DESC) for pagination
    op.create_index(
        "ix_tool_invocations_tenant_started_desc",
        "tool_invocations",
        ["tenant_id", sa.text("started_at DESC")],
        unique=False,
    )

    # Index on tool_name for filtering by tool
    op.create_index("ix_tool_invocations_tool_name", "tool_invocations", ["tool_name"], unique=False)

    # Create tool_audit_events table
    op.create_table(
        "tool_audit_events",
        sa.Column("id", sa.BigInteger(), nullable=False, comment="Auto-incrementing event ID"),
        sa.Column("eid", sa.Text(), nullable=False, comment="Execution ID this event relates to"),
        sa.Column(
            "event_type",
            sa.String(length=100),
            nullable=False,
            comment="Type of audit event (e.g., invocation_started, status_changed, result_stored)",
        ),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Event-specific data as JSON",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="Event timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["eid"], ["tool_invocations.eid"], name="fk_tool_audit_events_eid", ondelete="CASCADE"),
        comment="Audit trail for tool invocations",
    )

    # Index on eid for fast lookup of events by execution
    op.create_index("ix_tool_audit_events_eid", "tool_audit_events", ["eid"], unique=False)

    # Index on (eid, created_at) for ordered event retrieval
    op.create_index("ix_tool_audit_events_eid_created_at", "tool_audit_events", ["eid", "created_at"], unique=False)

    # Create trigger for tools.updated_at (reuse existing function)
    op.execute(
        """
        CREATE TRIGGER update_tools_updated_at
        BEFORE UPDATE ON tools
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """
    )


def downgrade() -> None:
    """Drop tools tables and related objects."""

    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS update_tools_updated_at ON tools")

    # Drop tool_audit_events table (cascade will handle FK)
    op.drop_index("ix_tool_audit_events_eid_created_at", table_name="tool_audit_events")
    op.drop_index("ix_tool_audit_events_eid", table_name="tool_audit_events")
    op.drop_table("tool_audit_events")

    # Drop tool_invocations table
    op.drop_index("ix_tool_invocations_tool_name", table_name="tool_invocations")
    op.drop_index("ix_tool_invocations_tenant_started_desc", table_name="tool_invocations")
    op.drop_index("ix_tool_invocations_idempotency_key_unique", table_name="tool_invocations")
    op.drop_index("ix_tool_invocations_status", table_name="tool_invocations")
    op.drop_table("tool_invocations")

    # Drop tools table
    op.drop_index("ix_tools_owner_tenant_id", table_name="tools")
    op.drop_index("ix_tools_name_version_unique", table_name="tools")
    op.drop_table("tools")
