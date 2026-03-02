"""Internal ops event model for audit trail of operator actions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from db.postgres_control.database import Base


class InternalOpsEvent(Base):
    """
    InternalOpsEvent records operator actions on internal endpoints.

    Tracks actions like auto-start override changes, staged manifest previews,
    and other internal operational activities.
    """

    __tablename__ = "internal_ops_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    kind = Column(String(100), nullable=False, index=True)  # e.g., 'auto_start_override', 'preview_staged'
    sub = Column(String(255), nullable=False, index=True)  # Actor subject

    # Event-specific data
    enabled = Column(Boolean)  # For auto_start_override
    note = Column(Text)  # Optional note/reason
    data_json = Column(JSONB)  # Additional structured data

    ts = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    __table_args__ = (
        Index("idx_internal_ops_events_kind_ts", "kind", "ts"),
        Index("idx_internal_ops_events_sub_ts", "sub", "ts"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for API responses."""
        return {
            "id": self.id,
            "kind": self.kind,
            "sub": self.sub,
            "enabled": self.enabled,
            "note": self.note,
            "data": self.data_json,
            "ts": self.ts.isoformat() if self.ts else None,
        }

    def __repr__(self) -> str:
        return f"<InternalOpsEvent(id={self.id}, kind={self.kind}, sub={self.sub})>"
