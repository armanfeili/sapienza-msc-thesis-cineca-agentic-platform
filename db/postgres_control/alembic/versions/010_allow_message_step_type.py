"""Allow 'message' as a step type.

Revision ID: 010
Revises: 009
Create Date: 2025-10-19 00:00:00.000000
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old check constraint
    op.execute("ALTER TABLE agent_steps DROP CONSTRAINT agent_steps_type_check")

    # Add new check constraint that includes 'message'
    op.execute(
        "ALTER TABLE agent_steps ADD CONSTRAINT agent_steps_type_check "
        "CHECK (type IN ('message', 'user', 'assistant', 'tool', 'system', 'error'))"
    )


def downgrade() -> None:
    # Revert to old check constraint
    op.execute("ALTER TABLE agent_steps DROP CONSTRAINT agent_steps_type_check")

    op.execute(
        "ALTER TABLE agent_steps ADD CONSTRAINT agent_steps_type_check "
        "CHECK (type IN ('user', 'assistant', 'tool', 'system', 'error'))"
    )
