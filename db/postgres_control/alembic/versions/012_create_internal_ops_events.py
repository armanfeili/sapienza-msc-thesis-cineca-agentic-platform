"""Create internal_ops_events table

Revision ID: 012
Revises: 011
Create Date: 2025-10-21

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create internal_ops_events table for audit trail of internal operations."""
    op.create_table(
        "internal_ops_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(length=100), nullable=False, index=True),
        sa.Column("sub", sa.String(length=255), nullable=False, index=True),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("data_json", JSONB(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )

    # Create composite indexes for common queries
    op.create_index("idx_internal_ops_events_kind_ts", "internal_ops_events", ["kind", "ts"])
    op.create_index("idx_internal_ops_events_sub_ts", "internal_ops_events", ["sub", "ts"])


def downgrade() -> None:
    """Drop internal_ops_events table."""
    op.drop_index("idx_internal_ops_events_sub_ts", table_name="internal_ops_events")
    op.drop_index("idx_internal_ops_events_kind_ts", table_name="internal_ops_events")
    op.drop_table("internal_ops_events")
