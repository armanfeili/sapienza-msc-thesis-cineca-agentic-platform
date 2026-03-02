"""Add todos, warnings, metrics to agent_runs and change output to JSONB

Revision ID: 015
Revises: 014
Create Date: 2025-11-10 12:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add missing columns to agent_runs table and change output type."""
    # Add todos column
    op.add_column(
        "agent_runs",
        sa.Column("todos", postgresql.JSONB, nullable=True, server_default="[]"),
    )
    
    # Add warnings column
    op.add_column(
        "agent_runs",
        sa.Column("warnings", postgresql.JSONB, nullable=True, server_default="[]"),
    )
    
    # Add metrics column
    op.add_column(
        "agent_runs",
        sa.Column("metrics", postgresql.JSONB, nullable=True),
    )
    
    # Change output column from Text to JSONB
    # First, we need to handle existing data
    op.execute("""
        ALTER TABLE agent_runs 
        ALTER COLUMN output TYPE jsonb 
        USING CASE 
            WHEN output IS NULL THEN NULL
            WHEN output = '' THEN NULL
            ELSE to_jsonb(output)
        END
    """)


def downgrade() -> None:
    """Revert agent_runs changes."""
    # Change output back to Text
    op.execute("""
        ALTER TABLE agent_runs 
        ALTER COLUMN output TYPE text 
        USING CASE 
            WHEN output IS NULL THEN NULL
            ELSE output::text
        END
    """)
    
    # Drop new columns
    op.drop_column("agent_runs", "metrics")
    op.drop_column("agent_runs", "warnings")
    op.drop_column("agent_runs", "todos")
