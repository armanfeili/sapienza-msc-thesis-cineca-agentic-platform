"""add status_code to idempotency_keys table

Revision ID: 022
Revises: 021
Create Date: 2025-11-16

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade():
    """Add status_code column to idempotency_keys table."""
    op.add_column(
        "idempotency_keys",
        sa.Column("status_code", sa.String(3), nullable=False, server_default="200")
    )


def downgrade():
    """Remove status_code column from idempotency_keys table."""
    op.drop_column("idempotency_keys", "status_code")
