"""add_sequence_to_model_defaults_id

Revision ID: 017
Revises: 016
Create Date: 2025-11-10 12:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade():
    """Add sequence and default to model_defaults.id column."""
    
    # Create sequence for id column
    op.execute("CREATE SEQUENCE model_defaults_id_seq")
    
    # Set the sequence as default for id column
    op.execute("ALTER TABLE model_defaults ALTER COLUMN id SET DEFAULT nextval('model_defaults_id_seq')")
    
    # Set the sequence owner to the id column (so it's dropped if column is dropped)
    op.execute("ALTER SEQUENCE model_defaults_id_seq OWNED BY model_defaults.id")
    
    # If there are existing rows, set the sequence to the max id + 1
    op.execute("""
        SELECT setval('model_defaults_id_seq', COALESCE((SELECT MAX(id) FROM model_defaults), 0) + 1, false)
    """)


def downgrade():
    """Remove sequence and default from model_defaults.id column."""
    
    # Remove default
    op.execute("ALTER TABLE model_defaults ALTER COLUMN id DROP DEFAULT")
    
    # Drop sequence
    op.execute("DROP SEQUENCE IF EXISTS model_defaults_id_seq")
