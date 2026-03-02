"""
Audit Log model for tracking admin actions.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class AuditLog(Base):
    """
    Audit log entry for tracking administrative actions.

    Tracks all create, update, delete operations on critical resources
    for compliance and security auditing.
    """

    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Action details
    action = Column(String, nullable=False, index=True)  # create, update, delete, etc.
    resource_type = Column(String, nullable=False, index=True)  # model, user, tenant, etc.
    resource_id = Column(String, nullable=False, index=True)

    # User context
    user_id = Column(String, nullable=False, index=True)
    tenant_id = Column(String, nullable=True, index=True)

    # Result
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)

    # Additional context
    details = Column(JSON, nullable=True)  # Additional metadata about the action

    def __repr__(self):
        return (
            f"<AuditLog(id={self.id}, action={self.action}, "
            f"resource_type={self.resource_type}, user_id={self.user_id})>"
        )
