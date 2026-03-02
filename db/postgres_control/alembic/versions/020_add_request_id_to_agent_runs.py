"""add request_id to agent_runs

Revision ID: 020
Revises: 019
Create Date: 2025-11-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020'
down_revision: Union[str, None] = '019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add request_id column to agent_runs table for HTTP request correlation."""
    op.add_column('agent_runs', 
                  sa.Column('request_id', sa.String(255), nullable=True))
    op.create_index('idx_agent_runs_request_id', 'agent_runs', ['request_id'])


def downgrade() -> None:
    """Remove request_id column from agent_runs table."""
    op.drop_index('idx_agent_runs_request_id', table_name='agent_runs')
    op.drop_column('agent_runs', 'request_id')
