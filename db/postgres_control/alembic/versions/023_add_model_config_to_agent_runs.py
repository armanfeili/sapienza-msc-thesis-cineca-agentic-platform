"""Add model config fields to agent_runs

Revision ID: 023
Revises: 022
Create Date: 2025-11-17 11:10:00.000000

Task B.7: Persist model config in agent_run metadata

Adds columns to agent_runs table to persist the complete model configuration
used for each run. This allows tracking which model instance was used and
makes debugging/auditing easier.

New columns:
- model_instance_name: Human-readable instance name (e.g., "phi3-mini")
- model_id: Provider-specific model ID (e.g., "phi3:mini" for Ollama)
- provider_name: Provider name (e.g., "ollama-local")
- provider_id: Foreign key to providers table
- config_source: Source of the configuration ("db_default", "env_fallback", etc.)

These fields are populated from the DB default at run creation time and
remain immutable for the duration of the run.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add model configuration fields to agent_runs."""
    # Add model_instance_name column (human-readable name)
    op.add_column(
        'agent_runs',
        sa.Column('model_instance_name', sa.String(255), nullable=True),
    )
    
    # Add model_id column (provider-specific model ID, already exists as "model")
    # Rename "model" to "model_id" for clarity
    # Note: "model" column already exists, so we'll keep it and add model_id as alias
    # Actually, let's just add model_id as a new column
    op.add_column(
        'agent_runs',
        sa.Column('model_id', sa.String(255), nullable=True),
    )
    
    # Add provider_name column
    op.add_column(
        'agent_runs',
        sa.Column('provider_name', sa.String(255), nullable=True),
    )
    
    # Add provider_id as foreign key to providers table
    op.add_column(
        'agent_runs',
        sa.Column('provider_id', sa.String(255), nullable=True),
    )
    
    # Add config_source column to track where config came from
    op.add_column(
        'agent_runs',
        sa.Column('config_source', sa.String(50), nullable=True),
    )
    
    # Add foreign key constraint for provider_id
    op.create_foreign_key(
        'fk_agent_runs_provider_id',
        'agent_runs',
        'providers',
        ['provider_id'],
        ['id'],
        ondelete='SET NULL'  # If provider is deleted, set to NULL
    )
    
    # Add index on provider_id for faster queries
    op.create_index(
        'idx_agent_runs_provider_id',
        'agent_runs',
        ['provider_id']
    )
    
    # Add index on config_source for analytics
    op.create_index(
        'idx_agent_runs_config_source',
        'agent_runs',
        ['config_source']
    )
    
    # Add comment to model_id column
    op.execute("""
        COMMENT ON COLUMN agent_runs.model_id IS 
        'Provider-specific model ID (e.g., phi3:mini for Ollama, gpt-4 for OpenAI)'
    """)
    
    op.execute("""
        COMMENT ON COLUMN agent_runs.model_instance_name IS 
        'Human-readable model instance name from model_instances table'
    """)
    
    op.execute("""
        COMMENT ON COLUMN agent_runs.provider_name IS 
        'Provider name from providers table'
    """)
    
    op.execute("""
        COMMENT ON COLUMN agent_runs.config_source IS 
        'Source of model configuration: db_default, env_fallback, api_override, etc.'
    """)


def downgrade() -> None:
    """Remove model configuration fields from agent_runs."""
    # Drop indexes
    op.drop_index('idx_agent_runs_config_source', table_name='agent_runs')
    op.drop_index('idx_agent_runs_provider_id', table_name='agent_runs')
    
    # Drop foreign key constraint
    op.drop_constraint('fk_agent_runs_provider_id', 'agent_runs', type_='foreignkey')
    
    # Drop columns
    op.drop_column('agent_runs', 'config_source')
    op.drop_column('agent_runs', 'provider_id')
    op.drop_column('agent_runs', 'provider_name')
    op.drop_column('agent_runs', 'model_id')
    op.drop_column('agent_runs', 'model_instance_name')
