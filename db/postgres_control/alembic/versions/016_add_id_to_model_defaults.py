"""add_id_to_model_defaults

Revision ID: 016
Revises: 015
Create Date: 2025-11-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade():
    """Add id column to model_defaults table and update primary key."""
    
    # Drop the old composite primary key constraint
    op.drop_constraint('pk_model_defaults', 'model_defaults', type_='primary')
    
    # Add id column as primary key with autoincrement
    op.add_column('model_defaults',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False)
    )
    
    # Create new primary key on id column
    op.create_primary_key('pk_model_defaults', 'model_defaults', ['id'])
    
    # Create unique constraint on (scope, tenant_id) to preserve uniqueness
    op.create_unique_constraint('uq_model_defaults_scope_tenant', 'model_defaults', ['scope', 'tenant_id'])


def downgrade():
    """Revert to composite primary key on (scope, tenant_id)."""
    
    # Drop the unique constraint
    op.drop_constraint('uq_model_defaults_scope_tenant', 'model_defaults', type_='unique')
    
    # Drop the id column primary key
    op.drop_constraint('pk_model_defaults', 'model_defaults', type_='primary')
    
    # Drop id column
    op.drop_column('model_defaults', 'id')
    
    # Recreate original composite primary key
    op.create_primary_key('pk_model_defaults', 'model_defaults', ['scope', 'tenant_id'])
