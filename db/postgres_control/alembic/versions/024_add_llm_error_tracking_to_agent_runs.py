"""add llm error tracking to agent runs

Revision ID: 024
Revises: 023
Create Date: 2025-01-XX

Task C.10: Expose LLM errors in agent_run outcome metadata

This migration adds columns to track LLM-related errors during agent execution,
enabling better debugging and visibility into failure reasons.

New columns:
- llm_error_type: Classification of error (timeout, context_length, rate_limit, connection, validation, unknown)
- llm_error_message: Detailed error message from the LLM provider
- llm_error_occurred_at: Timestamp when the error occurred

These fields are populated when the orchestrator encounters LLM errors during
execution and complement the existing status/error fields with provider-specific context.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade():
    # Add LLM error tracking columns to agent_runs table
    op.add_column('agent_runs', sa.Column(
        'llm_error_type',
        sa.String(100),
        nullable=True,
        comment='Type of LLM error: timeout, context_length, rate_limit, connection, validation, unknown'
    ))
    
    op.add_column('agent_runs', sa.Column(
        'llm_error_message',
        sa.Text,
        nullable=True,
        comment='Detailed error message from LLM provider'
    ))
    
    op.add_column('agent_runs', sa.Column(
        'llm_error_occurred_at',
        sa.DateTime(timezone=True),
        nullable=True,
        comment='Timestamp when LLM error occurred'
    ))
    
    # Add index on error_type for analytics and filtering
    op.create_index(
        'idx_agent_runs_llm_error_type',
        'agent_runs',
        ['llm_error_type']
    )


def downgrade():
    # Drop index first
    op.drop_index('idx_agent_runs_llm_error_type', table_name='agent_runs')
    
    # Drop columns in reverse order
    op.drop_column('agent_runs', 'llm_error_occurred_at')
    op.drop_column('agent_runs', 'llm_error_message')
    op.drop_column('agent_runs', 'llm_error_type')
