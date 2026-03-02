"""Create builtins manifests tables (PostgreSQL authoritative for model manifests)

Revision ID: 005
Revises: 004
Create Date: 2025-10-12 18:00:00.000000

Implements PostgreSQL-backed builtin model manifests with:
- builtins_manifests: Manifest content, versions, states (staged/active/archived)
- builtins_activations: Activation history with timestamps and actors
- builtins_staging_jobs: Idempotency tracking for staging operations
- builtins_manifest_audit: Append-only audit trail for all manifest operations

Redis serves as cache layer with TTLs, invalidated on stage/activate/rollback.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create builtins manifests tables with PostgreSQL as authoritative source."""

    # 1) builtins_manifests table (main manifest registry)
    op.create_table(
        "builtins_manifests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Unique manifest identifier",
        ),
        sa.Column("source_url", sa.Text, nullable=False, comment="URL from which manifest was fetched"),
        sa.Column(
            "content_json",
            postgresql.JSONB,
            nullable=False,
            comment="Full manifest content (array of model definitions)",
        ),
        sa.Column(
            "sha256",
            sa.String(64),
            nullable=False,
            unique=True,
            comment="SHA256 hash of content (content-based idempotency)",
        ),
        sa.Column("version", sa.String(255), nullable=True, comment="Optional version tag extracted from manifest"),
        sa.Column("state", sa.String(20), nullable=False, comment="Manifest state: 'staged', 'active', or 'archived'"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Creation timestamp (UTC)",
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Activation timestamp (UTC, null if never activated)",
        ),
        sa.Column(
            "created_by_sub",
            sa.String(255),
            nullable=False,
            comment="Subject ID of user who created/staged this manifest",
        ),
        sa.Column("etag", sa.String(64), nullable=False, comment="ETag for HTTP conditional requests"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Last update timestamp (UTC)",
        ),
        sa.CheckConstraint("state IN ('staged', 'active', 'archived')", name="ck_manifest_state"),
    )

    # Indexes for common queries
    op.create_index("ix_builtins_manifest_state", "builtins_manifests", ["state"])
    op.create_index("ix_builtins_manifest_created_at", "builtins_manifests", ["created_at"])
    op.create_index("ix_builtins_manifest_sha256", "builtins_manifests", ["sha256"], unique=True)

    # 2) builtins_activations table (activation history)
    op.create_table(
        "builtins_activations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True, comment="Auto-increment activation ID"),
        sa.Column("manifest_id", postgresql.UUID(as_uuid=True), nullable=False, comment="Manifest that was activated"),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Activation timestamp (UTC)",
        ),
        sa.Column("activated_by_sub", sa.String(255), nullable=False, comment="Subject ID of user who activated"),
        sa.Column("reason", sa.Text, nullable=True, comment="Optional reason for activation"),
        sa.Column(
            "previous_manifest_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Previous active manifest (null for first activation)",
        ),
        sa.Column("trace_id", sa.String(255), nullable=True, comment="Distributed trace ID for correlation"),
        sa.Column("event_id", sa.String(255), nullable=True, comment="Provenance event ID"),
        sa.ForeignKeyConstraint(
            ["manifest_id"], ["builtins_manifests.id"], name="builtins_activations_manifest_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["previous_manifest_id"],
            ["builtins_manifests.id"],
            name="builtins_activations_previous_manifest_id_fkey",
            ondelete="SET NULL",
        ),
    )

    # Indexes for history queries
    op.create_index("ix_builtins_activation_manifest_id", "builtins_activations", ["manifest_id"])
    op.create_index("ix_builtins_activation_activated_at", "builtins_activations", ["activated_at"])
    op.create_index("ix_builtins_activation_activated_by_sub", "builtins_activations", ["activated_by_sub"])

    # 3) builtins_staging_jobs table (idempotency tracking for staging)
    op.create_table(
        "builtins_staging_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Unique staging job identifier",
        ),
        sa.Column("idempotency_key", sa.Text, nullable=False, comment="Idempotency key from request header"),
        sa.Column("source_url", sa.Text, nullable=False, comment="URL from which manifest was fetched"),
        sa.Column("sha256", sa.String(64), nullable=True, comment="SHA256 hash of staged content (null on error)"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Job creation timestamp (UTC)",
        ),
        sa.Column("created_by_sub", sa.String(255), nullable=False, comment="Subject ID of user who initiated staging"),
        sa.Column("status", sa.String(20), nullable=False, comment="Job status: 'ok' or 'error'"),
        sa.Column("error_json", postgresql.JSONB, nullable=True, comment="Error details if status=error"),
        sa.CheckConstraint("status IN ('ok', 'error')", name="ck_staging_job_status"),
    )

    # Unique constraint for idempotency: one job per user per key
    op.create_unique_constraint(
        "uq_staging_job_user_key", "builtins_staging_jobs", ["created_by_sub", "idempotency_key"]
    )

    # Indexes for lookup
    op.create_index("ix_builtins_staging_job_created_at", "builtins_staging_jobs", ["created_at"])
    op.create_index("ix_builtins_staging_job_sha256", "builtins_staging_jobs", ["sha256"])

    # 4) builtins_manifest_audit table (append-only audit trail)
    op.create_table(
        "builtins_manifest_audit",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True, comment="Auto-increment audit event ID"),
        sa.Column(
            "manifest_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Manifest affected by this event (nullable for list operations)",
        ),
        sa.Column(
            "action",
            sa.String(100),
            nullable=False,
            comment="Action performed: 'stage', 'activate', 'rollback', 'delete'",
        ),
        sa.Column(
            "details_json",
            postgresql.JSONB,
            nullable=True,
            comment="Event details (state transitions, validation, errors)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Event timestamp (UTC, immutable)",
        ),
        sa.Column("actor_sub", sa.String(255), nullable=False, comment="Subject ID of user who performed action"),
        sa.Column("trace_id", sa.String(255), nullable=True, comment="Distributed trace ID for correlation"),
        sa.Column("event_id", sa.String(255), nullable=True, comment="Provenance event ID"),
        sa.ForeignKeyConstraint(
            ["manifest_id"],
            ["builtins_manifests.id"],
            name="builtins_manifest_audit_manifest_id_fkey",
            ondelete="SET NULL",
        ),
    )

    # Indexes for audit queries
    op.create_index("ix_builtins_audit_manifest_id", "builtins_manifest_audit", ["manifest_id"])
    op.create_index("ix_builtins_audit_action", "builtins_manifest_audit", ["action"])
    op.create_index("ix_builtins_audit_actor_sub", "builtins_manifest_audit", ["actor_sub"])
    op.create_index("ix_builtins_audit_created_at", "builtins_manifest_audit", ["created_at"])


def downgrade() -> None:
    """Drop builtins manifests tables (reverse migration)."""

    # Drop in reverse order (respecting foreign key constraints)
    op.drop_table("builtins_manifest_audit")
    op.drop_table("builtins_staging_jobs")
    op.drop_table("builtins_activations")
    op.drop_table("builtins_manifests")
