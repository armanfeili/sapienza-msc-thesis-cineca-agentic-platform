"""Create builtin process tracking tables.

Revision ID: 011
Revises: 010
Create Date: 2025-10-21 00:00:00.000000
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create manifest_status enum (idempotent)
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE manifeststatus AS ENUM ('staged', 'active', 'rolled_back', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    # Create process_event enum (idempotent)
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE processevent AS ENUM ('start', 'heartbeat', 'stop', 'exit', 'signal');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    # Create builtin_manifest_activation_history table (if not exists)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS builtin_manifest_activation_history (
            id UUID PRIMARY KEY,
            manifest_name VARCHAR(255) NOT NULL,
            version VARCHAR(100) NOT NULL,
            activated_at TIMESTAMPTZ NOT NULL,
            activated_by TEXT,
            status manifeststatus NOT NULL,
            notes TEXT
        )
        """
    )

    # Create indexes for builtin_manifest_activation_history
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_builtin_manifest_activation_history_manifest_name ON builtin_manifest_activation_history (manifest_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_builtin_manifest_activation_history_activated_at ON builtin_manifest_activation_history (activated_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_builtin_manifest_activation_history_status ON builtin_manifest_activation_history (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_builtin_manifest_name_activated_at ON builtin_manifest_activation_history (manifest_name, activated_at)"
    )

    # Create builtin_process_events table (if not exists)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS builtin_process_events (
            id UUID PRIMARY KEY,
            process_id VARCHAR(255) NOT NULL,
            artifact VARCHAR(255) NOT NULL,
            pid INTEGER,
            port INTEGER,
            event processevent NOT NULL,
            reason TEXT,
            exit_code INTEGER,
            ts TIMESTAMPTZ NOT NULL,
            tenant_id VARCHAR(255),
            manifest_version VARCHAR(100),
            host VARCHAR(255)
        )
        """
    )

    # Create indexes for builtin_process_events
    op.execute("CREATE INDEX IF NOT EXISTS ix_builtin_process_events_process_id ON builtin_process_events (process_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_builtin_process_events_artifact ON builtin_process_events (artifact)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_builtin_process_events_pid ON builtin_process_events (pid)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_builtin_process_events_event ON builtin_process_events (event)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_builtin_process_events_ts ON builtin_process_events (ts)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_builtin_process_events_tenant_id ON builtin_process_events (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_builtin_process_artifact_ts ON builtin_process_events (artifact, ts)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_builtin_process_pid_ts ON builtin_process_events (pid, ts)")


def downgrade() -> None:
    # Drop tables
    op.drop_table("builtin_process_events")
    op.drop_table("builtin_manifest_activation_history")

    # Drop enums
    op.execute("DROP TYPE processevent")
    op.execute("DROP TYPE manifeststatus")
