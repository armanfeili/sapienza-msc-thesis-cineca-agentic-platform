"""Create jobs tables

Revision ID: 003
Revises: 002
Create Date: 2025-10-12 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create jobs table
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("owner_sub", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("payload_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("result_json", postgresql.JSONB),
        sa.Column("error_json", postgresql.JSONB),
        sa.Column("idempotency_key", sa.String(255)),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("queue_latency_ms", sa.Integer),
        sa.Column("exec_latency_ms", sa.Integer),
        sa.Column("etag", sa.String(64)),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'finished', 'failed', 'cancelled')", name="jobs_status_check"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="jobs_tenant_id_fkey", ondelete="CASCADE"),
    )

    # Create unique constraint for idempotency (only when idempotency_key is not null)
    op.create_index(
        "idx_jobs_idempotency_unique",
        "jobs",
        ["owner_sub", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # Create indexes for performance
    op.create_index("idx_jobs_owner_created", "jobs", ["owner_sub", sa.text("created_at DESC")])
    op.create_index("idx_jobs_status_created", "jobs", ["status", sa.text("created_at DESC")])
    op.create_index("idx_jobs_tenant_created", "jobs", ["tenant_id", sa.text("created_at DESC")])
    op.create_index("idx_jobs_updated", "jobs", [sa.text("updated_at DESC")])
    op.create_index("idx_jobs_idempotency_key", "jobs", ["idempotency_key"])

    # Create trigger to auto-update updated_at
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_jobs_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """
    )

    op.execute(
        """
        CREATE TRIGGER jobs_updated_at_trigger
        BEFORE UPDATE ON jobs
        FOR EACH ROW
        EXECUTE FUNCTION update_jobs_updated_at();
    """
    )

    # Create job_events table
    op.create_table(
        "job_events",
        sa.Column("seq_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name="job_events_job_id_fkey", ondelete="CASCADE"),
    )

    # Create indexes for job_events
    op.create_index("idx_job_events_job_seq", "job_events", ["job_id", "seq_id"])
    op.create_index("idx_job_events_created", "job_events", [sa.text("created_at DESC")])


def downgrade() -> None:
    # Drop job_events table and indexes
    op.drop_index("idx_job_events_created", table_name="job_events")
    op.drop_index("idx_job_events_job_seq", table_name="job_events")
    op.drop_table("job_events")

    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS jobs_updated_at_trigger ON jobs;")
    op.execute("DROP FUNCTION IF EXISTS update_jobs_updated_at();")

    # Drop jobs indexes
    op.drop_index("idx_jobs_idempotency_key", table_name="jobs")
    op.drop_index("idx_jobs_updated", table_name="jobs")
    op.drop_index("idx_jobs_tenant_created", table_name="jobs")
    op.drop_index("idx_jobs_status_created", table_name="jobs")
    op.drop_index("idx_jobs_owner_created", table_name="jobs")
    op.drop_index("idx_jobs_idempotency_unique", table_name="jobs")

    # Drop jobs table
    op.drop_table("jobs")
