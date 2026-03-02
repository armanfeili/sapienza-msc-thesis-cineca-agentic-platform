"""Initial migration - create tenants table

Revision ID: 001
Revises:
Create Date: 2025-10-11 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tenants table with all constraints and indexes."""

    # Create tenants table
    op.create_table(
        "tenants",
        sa.Column("id", sa.Text(), nullable=False, comment="Unique tenant identifier (e.g., tenant-abc123)"),
        sa.Column("name", sa.String(length=255), nullable=False, comment="Tenant display name"),
        sa.Column("admin_email", sa.String(length=320), nullable=False, comment="Primary admin contact email"),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="Arbitrary tenant metadata (region, tier, etc.)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="Last update timestamp",
        ),
        sa.Column(
            "version",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Version number for optimistic locking",
        ),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 255", name="ck_tenants_name_length"),
        sa.PrimaryKeyConstraint("id"),
        comment="Tenant organizations with isolation and metadata",
    )

    # Create indexes
    # Unique constraint on lowercase name (for idempotency/conflict detection)
    op.create_index("ix_tenants_name_lower_unique", "tenants", [sa.text("LOWER(name)")], unique=True)

    # Index on lowercase email for fast lookups
    op.create_index("ix_tenants_admin_email_lower", "tenants", [sa.text("LOWER(admin_email)")], unique=False)

    # Index on created_at DESC for pagination
    op.create_index("ix_tenants_created_at_desc", "tenants", [sa.text("created_at DESC")], unique=False)

    # Create trigger function for updated_at
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            NEW.version = OLD.version + 1;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """
    )

    # Create trigger on tenants table
    op.execute(
        """
        CREATE TRIGGER update_tenants_updated_at
        BEFORE UPDATE ON tenants
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """
    )


def downgrade() -> None:
    """Drop tenants table and related objects."""

    # Drop trigger first
    op.execute("DROP TRIGGER IF EXISTS update_tenants_updated_at ON tenants")

    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # Drop indexes (will be dropped automatically with table, but explicit for clarity)
    op.drop_index("ix_tenants_created_at_desc", table_name="tenants")
    op.drop_index("ix_tenants_admin_email_lower", table_name="tenants")
    op.drop_index("ix_tenants_name_lower_unique", table_name="tenants")

    # Drop table
    op.drop_table("tenants")
