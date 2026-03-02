"""Rename session_metadata column to metadata in agent_sessions table

Revision ID: 014
Revises: 013
Create Date: 2025-11-10 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename session_metadata column to metadata to match SQLAlchemy model."""
    op.alter_column("agent_sessions", "session_metadata", new_column_name="metadata")


def downgrade() -> None:
    """Revert metadata column name back to session_metadata."""
    op.alter_column("agent_sessions", "metadata", new_column_name="session_metadata")
