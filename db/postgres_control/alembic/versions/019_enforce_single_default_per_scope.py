"""enforce_single_default_per_scope

Revision ID: 019
Revises: 018
Create Date: 2025-01-11 14:00:00.000000

Enforces single default model per (scope, tenant_id) combination by:
1. Adding 'user' to allowed scope values
2. Sanitizing any existing multi-default data
3. Adding unique index to enforce constraint at database level
4. Adding id column with sequence for better tracking

This migration supports the Default Model Resolver (DMR) system which requires
PostgreSQL as the single source of truth for default model configuration.

Design rationale:
- (scope, tenant_id) must be unique even when tenant_id is NULL
- 'user' scope represents per-user defaults (handled separately in user_default_models table)
- Unique index prevents race conditions and ensures data integrity
- Sanitization keeps most recent default when duplicates exist
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade():
    """
    Enforce single default per (scope, tenant_id) combination.
    
    Steps:
    1. Drop old CHECK constraint for scope
    2. Add 'user' to allowed scope values
    3. Sanitize multi-default data (keep most recent)
    4. Create unique index to enforce single default
    5. Update comments
    """
    
    # ──────────────────────────────────────────────────────────────────
    # Step 1: Update scope constraint to allow 'user'
    # ──────────────────────────────────────────────────────────────────
    
    # Drop old scope constraint (scope IN ('global', 'tenant'))
    op.drop_constraint('ck_model_defaults_scope', 'model_defaults', type_='check')
    
    # Add new scope constraint (scope IN ('global', 'tenant', 'user'))
    op.create_check_constraint(
        'ck_model_defaults_scope',
        'model_defaults',
        "scope IN ('global', 'tenant', 'user')"
    )
    
    # ──────────────────────────────────────────────────────────────────
    # Step 2: Update scope-tenant relationship constraint
    # ──────────────────────────────────────────────────────────────────
    
    # Drop old scope-tenant constraint
    op.drop_constraint('ck_model_defaults_scope_tenant', 'model_defaults', type_='check')
    
    # Add new scope-tenant constraint with 'user' support
    # Rules:
    # - global scope: tenant_id MUST be NULL
    # - tenant scope: tenant_id MUST NOT be NULL
    # - user scope: handled separately in user_default_models table (allow NULL for backward compat)
    op.create_check_constraint(
        'ck_model_defaults_scope_tenant',
        'model_defaults',
        """(
            (scope = 'global' AND tenant_id IS NULL) OR
            (scope = 'tenant' AND tenant_id IS NOT NULL) OR
            (scope = 'user')
        )"""
    )
    
    # ──────────────────────────────────────────────────────────────────
    # Step 3: Sanitize multi-default data
    # ──────────────────────────────────────────────────────────────────
    
    # CRITICAL: Remove duplicate defaults, keeping the most recent one
    # This prevents unique constraint violation in next step
    
    connection = op.get_bind()
    
    # Find all (scope, tenant_id) combinations with multiple rows
    # Keep only the row with latest updated_at, delete others
    # Handle NULL tenant_id correctly with COALESCE and IS DISTINCT FROM
    
    sanitize_sql = sa.text("""
        WITH ranked_defaults AS (
            SELECT 
                scope,
                tenant_id,
                instance_id,
                updated_at,
                ROW_NUMBER() OVER (
                    PARTITION BY scope, COALESCE(tenant_id, '__NULL__')
                    ORDER BY updated_at DESC, created_at DESC
                ) as rn
            FROM model_defaults
        ),
        duplicates AS (
            SELECT scope, tenant_id
            FROM ranked_defaults
            WHERE rn > 1
        )
        DELETE FROM model_defaults
        WHERE (scope, COALESCE(tenant_id, '__NULL__')) IN (
            SELECT scope, COALESCE(tenant_id, '__NULL__')
            FROM duplicates
        )
        AND (scope, tenant_id, instance_id, updated_at) NOT IN (
            SELECT scope, tenant_id, instance_id, updated_at
            FROM ranked_defaults
            WHERE rn = 1
        )
    """)
    
    result = connection.execute(sanitize_sql)
    rows_deleted = result.rowcount
    
    # Log sanitization result (will appear in migration output)
    if rows_deleted > 0:
        print(f"[019_enforce_single_default] Sanitized {rows_deleted} duplicate default(s)")
    
    # ──────────────────────────────────────────────────────────────────
    # Step 4: Create unique index to enforce single default constraint
    # ──────────────────────────────────────────────────────────────────
    
    # Create unique index that handles NULL tenant_id correctly
    # PostgreSQL UNIQUE constraint treats NULL as distinct, but we want
    # only ONE global default (scope='global', tenant_id=NULL)
    
    # Use partial unique index: UNIQUE (scope, tenant_id) WHERE tenant_id IS NOT NULL
    # Plus separate constraint for global scope
    
    # Drop existing primary key constraint (scope, tenant_id)
    # This is necessary because PK doesn't properly handle NULL tenant_id uniqueness
    op.drop_constraint('pk_model_defaults', 'model_defaults', type_='primary')
    
    # Create unique index for tenant-scoped defaults (tenant_id NOT NULL)
    op.create_index(
        'uq_model_defaults_scope_tenant_not_null',
        'model_defaults',
        ['scope', 'tenant_id'],
        unique=True,
        postgresql_where=sa.text('tenant_id IS NOT NULL')
    )
    
    # Create unique index for global defaults (tenant_id IS NULL)
    # This ensures only ONE (scope='global', tenant_id=NULL) row exists
    op.create_index(
        'uq_model_defaults_scope_null_tenant',
        'model_defaults',
        ['scope'],
        unique=True,
        postgresql_where=sa.text('tenant_id IS NULL')
    )
    
    # ──────────────────────────────────────────────────────────────────
    # Step 5: Add surrogate primary key (id column)
    # ──────────────────────────────────────────────────────────────────
    
    # Add id column as new primary key (already done in migration 016-017)
    # Just ensure it's marked as primary key if not already
    
    # Check if id column exists from migration 016/017
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('model_defaults')]
    
    if 'id' in columns:
        # Column exists (from migration 016), just set it as primary key
        op.create_primary_key('pk_model_defaults', 'model_defaults', ['id'])
    else:
        # Should not happen (migration 016 should have added it)
        # Add id column with sequence if missing
        op.add_column(
            'model_defaults',
            sa.Column(
                'id',
                sa.BigInteger(),
                autoincrement=True,
                nullable=False,
                server_default=sa.text("nextval('model_defaults_id_seq')")
            )
        )
        op.create_primary_key('pk_model_defaults', 'model_defaults', ['id'])


def downgrade():
    """
    Revert to previous state (multi-defaults allowed, no 'user' scope).
    
    WARNING: This may cause data loss if user-scoped defaults exist.
    """
    
    # ──────────────────────────────────────────────────────────────────
    # Step 1: Drop unique indexes
    # ──────────────────────────────────────────────────────────────────
    
    op.drop_index('uq_model_defaults_scope_null_tenant', table_name='model_defaults')
    op.drop_index('uq_model_defaults_scope_tenant_not_null', table_name='model_defaults')
    
    # ──────────────────────────────────────────────────────────────────
    # Step 2: Restore (scope, tenant_id) as primary key
    # ──────────────────────────────────────────────────────────────────
    
    # Drop id-based primary key
    op.drop_constraint('pk_model_defaults', 'model_defaults', type_='primary')
    
    # Restore original compound primary key
    op.create_primary_key('pk_model_defaults', 'model_defaults', ['scope', 'tenant_id'])
    
    # ──────────────────────────────────────────────────────────────────
    # Step 3: Remove 'user' scope support
    # ──────────────────────────────────────────────────────────────────
    
    # WARNING: Delete any user-scoped defaults before reverting constraint
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM model_defaults WHERE scope = 'user'"))
    
    # Drop new scope-tenant constraint
    op.drop_constraint('ck_model_defaults_scope_tenant', 'model_defaults', type_='check')
    
    # Restore original scope-tenant constraint (no 'user' scope)
    op.create_check_constraint(
        'ck_model_defaults_scope_tenant',
        'model_defaults',
        """(
            (scope = 'global' AND tenant_id IS NULL) OR
            (scope = 'tenant' AND tenant_id IS NOT NULL)
        )"""
    )
    
    # ──────────────────────────────────────────────────────────────────
    # Step 4: Restore original scope constraint
    # ──────────────────────────────────────────────────────────────────
    
    # Drop new scope constraint
    op.drop_constraint('ck_model_defaults_scope', 'model_defaults', type_='check')
    
    # Restore original scope constraint (no 'user' scope)
    op.create_check_constraint(
        'ck_model_defaults_scope',
        'model_defaults',
        "scope IN ('global', 'tenant')"
    )
