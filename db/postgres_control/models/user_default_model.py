"""
SQLAlchemy model for user_default_models table.

Represents per-user default model preferences with tenant scoping.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from db.postgres_control.database import Base


class UserDefaultModel(Base):
    """User-scoped default model preferences."""

    __tablename__ = "user_default_models"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # User and tenant identification
    user_id = Column(String(255), nullable=False)
    tenant_id = Column(String(255), nullable=True)

    # Reference to model instance (CASCADE delete when instance deleted)
    chat_instance_id = Column(UUID(as_uuid=True), ForeignKey("model_instances.id", ondelete="CASCADE"), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Audit and caching
    created_by = Column(String(255), nullable=False)
    etag = Column(String(64), nullable=False, default=lambda: uuid.uuid4().hex)

    # Relationship to ModelInstance
    instance = relationship("ModelInstance", foreign_keys=[chat_instance_id])

    # Indexes
    __table_args__ = (
        # Unique constraint - one default per user per tenant
        Index("idx_user_tenant_unique", "user_id", "tenant_id", unique=True),
        # Performance indexes for common queries
        Index("idx_user_id", "user_id"),
        Index("idx_tenant_id", "tenant_id"),
        Index("idx_chat_instance_id", "chat_instance_id"),
    )
