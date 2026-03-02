"""allow_null_tenant_id_in_model_defaults

Revision ID: 018
Revises: 017
Create Date: 2025-11-10 12:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade():
    """Allow tenant_id to be NULL in model_defaults table."""
    
    # Change tenant_id column to allow NULL values
    op.alter_column('model_defaults', 'tenant_id',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=True)


def downgrade():
    """Revert tenant_id to NOT NULL."""
    
    # Change tenant_id back to NOT NULL
    op.alter_column('model_defaults', 'tenant_id',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=False)
