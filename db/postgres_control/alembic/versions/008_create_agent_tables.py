"""Create agent tables

Revision ID: 008
Revises: 007
Create Date: 2025-10-17 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create agent_sessions table
    op.create_table(
        "agent_sessions",
        sa.Column(
            "session_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("manager", sa.String(255)),
        sa.Column("preferred_workers", postgresql.JSONB),
        sa.Column("llm_preferences", postgresql.JSONB),
        sa.Column("agent_role", sa.String(255)),
        sa.Column("tools", postgresql.JSONB),
        sa.Column("temperature", sa.Float, nullable=False, server_default="0.2"),
        sa.Column("max_steps", sa.Integer, nullable=False, server_default="8"),
        sa.Column("session_metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("last_step_id", postgresql.UUID(as_uuid=True)),
        sa.Column("etag", sa.String(64)),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled', 'failed')", name="agent_sessions_status_check"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="agent_sessions_tenant_id_fkey", ondelete="CASCADE"
        ),
    )

    # Create agent_steps table
    op.create_table(
        "agent_steps",
        sa.Column(
            "step_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("message", sa.Text),
        sa.Column("tool", sa.String(255)),
        sa.Column("input", postgresql.JSONB),
        sa.Column("output", postgresql.JSONB),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("error", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')", name="agent_steps_status_check"
        ),
        sa.CheckConstraint("type IN ('user', 'assistant', 'tool', 'system', 'error')", name="agent_steps_type_check"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["agent_sessions.session_id"], name="agent_steps_session_id_fkey", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("session_id", "seq", name="uq_agent_steps_session_seq"),
    )

    # Create agent_runs table
    op.create_table(
        "agent_runs",
        sa.Column(
            "run_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True)),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("model", sa.String(255)),
        sa.Column("manager", sa.String(255)),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("trace_id", sa.String(255)),
        sa.Column("event_id", sa.String(255)),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="agent_runs_status_check"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["agent_sessions.session_id"], name="agent_runs_session_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="agent_runs_tenant_id_fkey", ondelete="CASCADE"),
    )

    # Create idempotency_keys table
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("owner_user_id", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_hash", sa.String(64), nullable=False),
        sa.Column("response_body", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("replayed_at", sa.DateTime(timezone=True)),
    )

    # Add foreign key for last_step_id (after agent_steps is created)
    op.create_foreign_key(
        "agent_sessions_last_step_id_fkey",
        "agent_sessions",
        "agent_steps",
        ["last_step_id"],
        ["step_id"],
        ondelete="SET NULL",
    )

    # Create indexes for agent_sessions
    op.create_index("idx_agent_sessions_user_created", "agent_sessions", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_agent_sessions_tenant_created", "agent_sessions", ["tenant_id", sa.text("created_at DESC")])
    op.create_index("idx_agent_sessions_status", "agent_sessions", ["status"])

    # Create indexes for agent_steps
    op.create_index("idx_agent_steps_session_seq", "agent_steps", ["session_id", "seq"])
    op.create_index("idx_agent_steps_session_created", "agent_steps", ["session_id", sa.text("created_at ASC")])

    # Create indexes for agent_runs
    op.create_index("idx_agent_runs_user_started", "agent_runs", ["user_id", sa.text("started_at DESC")])
    op.create_index("idx_agent_runs_session_started", "agent_runs", ["session_id", sa.text("started_at DESC")])
    op.create_index("idx_agent_runs_trace_id", "agent_runs", ["trace_id"])
    op.create_index("idx_agent_runs_event_id", "agent_runs", ["event_id"])

    # Create indexes for idempotency_keys
    op.create_index("idx_idempotency_owner_created", "idempotency_keys", ["owner_user_id", sa.text("created_at DESC")])

    # Create trigger to auto-update updated_at for agent_sessions
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_agent_sessions_updated_at()
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
        CREATE TRIGGER agent_sessions_updated_at_trigger
        BEFORE UPDATE ON agent_sessions
        FOR EACH ROW
        EXECUTE FUNCTION update_agent_sessions_updated_at();
    """
    )


def downgrade() -> None:
    # Drop triggers and functions
    op.execute("DROP TRIGGER IF EXISTS agent_sessions_updated_at_trigger ON agent_sessions")
    op.execute("DROP FUNCTION IF EXISTS update_agent_sessions_updated_at()")

    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table("idempotency_keys")
    op.drop_table("agent_runs")
    op.drop_table("agent_steps")
    op.drop_table("agent_sessions")
