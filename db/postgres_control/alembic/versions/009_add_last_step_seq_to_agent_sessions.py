"""Add last_step_seq column to agent_sessions

Revision ID: 009
Revises: 008
Create Date: 2025-10-18 23:45:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_sessions", sa.Column("last_step_seq", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("agent_sessions", "last_step_seq")
