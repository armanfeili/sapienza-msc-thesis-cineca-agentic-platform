"""Add run metadata JSONB to agent runs

Revision ID: 025
Revises: 024
Create Date: 2025-11-21

Persist arbitrary per-run metadata (e.g., memgraph_force_llm) so request-level
flags round-trip in API responses and remain available for diagnostics.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'agent_runs',
        sa.Column(
            'metadata',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Arbitrary run-scoped metadata (mirrors request.metadata)",
        ),
    )


def downgrade():
    op.drop_column('agent_runs', 'metadata')
