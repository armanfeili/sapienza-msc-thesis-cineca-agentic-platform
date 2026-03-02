"""Add steps and output columns to agent_runs

Revision ID: 013
Revises: 012
Create Date: 2025-11-07 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add steps and output columns to agent_runs table."""
    # Add steps column to store execution steps as JSONB
    op.add_column(
        "agent_runs",
        sa.Column("steps", postgresql.JSONB, nullable=True, server_default="[]"),
    )
    
    # Add output column to store final output text
    op.add_column(
        "agent_runs",
        sa.Column("output", sa.Text, nullable=True),
    )


def downgrade() -> None:
    """Remove steps and output columns from agent_runs table."""
    op.drop_column("agent_runs", "output")
    op.drop_column("agent_runs", "steps")
