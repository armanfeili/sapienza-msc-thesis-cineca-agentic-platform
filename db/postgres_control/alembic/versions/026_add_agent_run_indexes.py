"""Add composite indexes for agent_runs listing queries

Revision ID: 026
Revises: 025
Create Date: 2025-11-30
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        'idx_agent_runs_tenant_user_started',
        'agent_runs',
        ['tenant_id', 'user_id', 'started_at'],
    )
    op.create_index(
        'idx_agent_runs_tenant_session_started',
        'agent_runs',
        ['tenant_id', 'session_id', 'started_at'],
    )
    op.create_index(
        'idx_agent_runs_status_started',
        'agent_runs',
        ['status', 'started_at'],
    )


def downgrade():
    op.drop_index('idx_agent_runs_status_started', table_name='agent_runs')
    op.drop_index('idx_agent_runs_tenant_session_started', table_name='agent_runs')
    op.drop_index('idx_agent_runs_tenant_user_started', table_name='agent_runs')
