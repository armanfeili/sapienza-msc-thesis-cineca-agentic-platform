"""Idempotency key model for PostgreSQL storage."""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    String,
    Text,
)
from sqlalchemy.sql import func

from db.postgres_control.database import Base


class IdempotencyKey(Base):
    """
    IdempotencyKey stores request fingerprints to enable idempotent POST operations.

    Keys are associated with an owner (user_id), method, path, and request hash.
    Replay detection returns the cached response hash.
    """

    __tablename__ = "idempotency_keys"

    key = Column(String(255), primary_key=True)
    owner_user_id = Column(String(255), nullable=False, index=True)

    # Request identification
    method = Column(String(10), nullable=False)  # POST, PUT, etc.
    path = Column(String(500), nullable=False)

    # Request/response hashes
    request_hash = Column(String(64), nullable=False)
    response_hash = Column(String(64), nullable=False)

    # Response body and status (stored for replay)
    response_body = Column(Text, nullable=True)
    status_code = Column(String(3), nullable=False, default="200")  # HTTP status code (e.g., "201")

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    replayed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_idempotency_owner_created", "owner_user_id", "created_at"),)

    def to_dict(self) -> dict[str, Any]:
        """Convert idempotency key to dictionary representation."""
        return {
            "key": self.key,
            "owner_user_id": self.owner_user_id,
            "method": self.method,
            "path": self.path,
            "request_hash": self.request_hash,
            "response_hash": self.response_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "replayed_at": self.replayed_at.isoformat() if self.replayed_at else None,
        }
