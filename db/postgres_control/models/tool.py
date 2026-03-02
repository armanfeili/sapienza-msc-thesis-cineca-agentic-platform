"""
SQLAlchemy ORM model for Tool entity.

Defines the tools table schema with constraints, indexes, and relationships.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.postgres_control.database import Base


class Tool(Base):
    """
    Tool ORM model.

    Represents a versioned tool definition with JSON schemas for inputs/outputs.
    """

    __tablename__ = "tools"

    # Primary key
    id: Mapped[str] = mapped_column(Text, primary_key=True, comment="Unique tool identifier (UUID)")

    # Required fields
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Tool name")

    version: Mapped[str] = mapped_column(String(50), nullable=False, comment="Tool version (semver)")

    # Optional description
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Tool description")

    # JSON schemas for validation
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, comment="JSON schema for tool inputs")

    output_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="JSON schema for tool outputs"
    )

    # Ownership
    owner_tenant_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tenants.id", name="fk_tools_owner_tenant"), nullable=False, comment="Owning tenant ID"
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
    version_number: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0"), comment="Version number for optimistic locking"
    )

    # Relationships (optional, for ORM queries)
    # owner_tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="tools")

    # Table constraints
    __table_args__ = (
        # Unique constraint on (name, version)
        Index(
            "ix_tools_name_version_unique",
            name,
            version,
            unique=True,
        ),
        # Index on owner_tenant_id for tenant-scoped queries
        Index(
            "ix_tools_owner_tenant_id",
            owner_tenant_id,
        ),
        # Check constraints
        CheckConstraint("char_length(name) BETWEEN 1 AND 255", name="ck_tools_name_length"),
        CheckConstraint("char_length(version) BETWEEN 1 AND 50", name="ck_tools_version_length"),
        {"comment": "Tool definitions with schemas and versioning"},
    )

    def __repr__(self) -> str:
        return f"<Tool(id={self.id!r}, name={self.name!r}, version={self.version!r})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "owner_tenant_id": self.owner_tenant_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
