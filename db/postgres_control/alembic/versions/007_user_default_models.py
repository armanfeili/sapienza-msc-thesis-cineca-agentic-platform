"""Add user_default_models table

Revision ID: 007
Revises: 006
Create Date: 2025-10-17 10:00:00.000000

This migration adds support for per-user default model preferences with the following features:
- User-scoped defaults (user_id + tenant_id)
- Foreign key relationship to model_instances with CASCADE delete
- Unique constraint to prevent duplicate user/tenant combinations
- Indices for efficient lookups by user_id, tenant_id, and instance_id
- ETag support for cache validation
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create user_default_models table for per-user default preferences."""

    # Create user_default_models table
    op.create_table(
        "user_default_models",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            comment="Primary key UUID",
        ),
        sa.Column(
            "user_id", sa.String(length=255), nullable=False, comment="User subject from JWT token (Auth0 sub claim)"
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=255),
            nullable=True,
            comment="Tenant ID for scoped defaults (NULL = global user default)",
        ),
        sa.Column(
            "chat_instance_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="FK to model_instances.id (the default model for this user/tenant)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
            comment="Timestamp when default was first set",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
            comment="Timestamp when default was last updated",
        ),
        sa.Column("created_by", sa.String(length=255), nullable=True, comment="User subject who created this default"),
        sa.Column("etag", sa.String(length=64), nullable=True, comment="ETag for HTTP cache validation"),
        sa.PrimaryKeyConstraint("id", name="pk_user_default_models"),
        sa.ForeignKeyConstraint(
            ["chat_instance_id"],
            ["model_instances.id"],
            name="fk_user_default_models_instance",
            ondelete="CASCADE",  # When instance deleted, clear user defaults pointing to it
        ),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant_default"),
        comment="Per-user default model preferences with tenant scoping",
    )

    # Create indices for efficient lookups
    op.create_index("idx_user_default_models_user_id", "user_default_models", ["user_id"], unique=False)

    op.create_index("idx_user_default_models_tenant_id", "user_default_models", ["tenant_id"], unique=False)

    op.create_index("idx_user_default_models_instance_id", "user_default_models", ["chat_instance_id"], unique=False)

    # Create composite index for the common query pattern (user_id + tenant_id)
    op.create_index(
        "idx_user_default_models_user_tenant",
        "user_default_models",
        ["user_id", "tenant_id"],
        unique=True,  # Enforces uniqueness, redundant with constraint but improves query performance
    )


def downgrade() -> None:
    """Drop user_default_models table and all associated indices."""

    # Drop indices first
    op.drop_index("idx_user_default_models_user_tenant", table_name="user_default_models")
    op.drop_index("idx_user_default_models_instance_id", table_name="user_default_models")
    op.drop_index("idx_user_default_models_tenant_id", table_name="user_default_models")
    op.drop_index("idx_user_default_models_user_id", table_name="user_default_models")

    # Drop table (FK constraint dropped automatically)
    op.drop_table("user_default_models")
