"""add queued status to agent_runs

Revision ID: 021
Revises: 020
Create Date: 2025-11-13

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade():
    """Add 'queued' status to agent_runs status check constraint."""
    # Drop the old constraint
    op.drop_constraint("agent_runs_status_check", "agent_runs", type_="check")
    
    # Create new constraint with 'queued' status
    op.create_check_constraint(
        "agent_runs_status_check",
        "agent_runs",
        "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')"
    )
    
    # Update default value for status column
    op.alter_column(
        "agent_runs",
        "status",
        server_default="queued"
    )


def downgrade():
    """Remove 'queued' status from agent_runs status check constraint."""
    # Drop the new constraint
    op.drop_constraint("agent_runs_status_check", "agent_runs", type_="check")
    
    # Recreate old constraint without 'queued'
    op.create_check_constraint(
        "agent_runs_status_check",
        "agent_runs",
        "status IN ('running', 'succeeded', 'failed', 'cancelled')"
    )
    
    # Restore old default value
    op.alter_column(
        "agent_runs",
        "status",
        server_default="running"
    )
