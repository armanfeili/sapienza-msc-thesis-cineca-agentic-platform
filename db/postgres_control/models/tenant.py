"""
SQLAlchemy ORM model for Tenant entity.

Defines the tenants table schema with constraints, indexes, and triggers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.postgres_control.database import Base


class Tenant(Base):
    """
    Tenant ORM model.

    Represents an organization/customer tenant with isolation and metadata.
    """

    __tablename__ = "tenants"

    # Primary key
    id: Mapped[str] = mapped_column(Text, primary_key=True, comment="Unique tenant identifier (e.g., tenant-abc123)")

    # Required fields
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Tenant display name")

    admin_email: Mapped[str] = mapped_column(
        String(320), nullable=False, comment="Primary admin contact email"  # RFC 5321 max email length
    )

    # Optional metadata (JSONB for flexible schema)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",  # Column name in DB
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="Arbitrary tenant metadata (region, tier, etc.)",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment="Creation timestamp"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="Last update timestamp",
    )

    # Optimistic locking version
    version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0"), comment="Version number for optimistic locking"
    )

    # Table constraints
    __table_args__ = (
        # Unique constraint on lowercase name (idempotency/conflict detection)
        Index(
            "ix_tenants_name_lower_unique",
            text("LOWER(name)"),
            unique=True,
        ),
        # Index on lowercase email for fast lookups
        Index(
            "ix_tenants_admin_email_lower",
            text("LOWER(admin_email)"),
        ),
        # Index on created_at for pagination/sorting
        Index(
            "ix_tenants_created_at_desc",
            created_at.desc(),
        ),
        # Check constraint for name length
        CheckConstraint("char_length(name) BETWEEN 1 AND 255", name="ck_tenants_name_length"),
        {"comment": "Tenant organizations with isolation and metadata"},
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id!r}, name={self.name!r})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "admin_email": self.admin_email,
            "metadata": self.metadata_,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
