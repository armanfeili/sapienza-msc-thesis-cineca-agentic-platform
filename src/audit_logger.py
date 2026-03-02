"""
Audit logging system for tracking admin actions.

This module provides functionality to log all admin-level actions
such as creating/updating/deleting models, users, tenants, etc.
"""

from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.orm import Session

from db.postgres_control.models import AuditLog

logger = structlog.get_logger()


class AuditLogger:
    """
    Audit logger for tracking admin actions.

    Logs are stored in PostgreSQL for compliance and security auditing.
    """

    @staticmethod
    def log_action(
        db: Session,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: str,
        tenant_id: str | None = None,
        details: dict[str, Any] | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """
        Log an admin action to the database.

        Args:
            db: Database session
            action: Action performed (create, update, delete, etc.)
            resource_type: Type of resource (model, user, tenant, etc.)
            resource_id: ID of the resource affected
            user_id: ID of user performing the action
            tenant_id: Optional tenant context
            details: Optional additional details (will be stored as JSON)
            success: Whether the action succeeded
            error_message: Error message if action failed
        """
        try:
            audit_entry = AuditLog(
                timestamp=datetime.utcnow(),
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                user_id=user_id,
                tenant_id=tenant_id,
                details=details or {},
                success=success,
                error_message=error_message,
            )

            db.add(audit_entry)
            db.commit()

            # Also log to structured logger
            logger.info(
                "audit_log",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                user_id=user_id,
                tenant_id=tenant_id,
                success=success,
            )

        except Exception as e:
            logger.error(f"Failed to write audit log: {e!s}")
            # Don't fail the main operation if audit logging fails
            db.rollback()

    @staticmethod
    def log_create(
        db: Session,
        resource_type: str,
        resource_id: str,
        user_id: str,
        tenant_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log a resource creation action."""
        AuditLogger.log_action(
            db=db,
            action="create",
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            tenant_id=tenant_id,
            details=details,
            success=True,
        )

    @staticmethod
    def log_update(
        db: Session,
        resource_type: str,
        resource_id: str,
        user_id: str,
        tenant_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log a resource update action."""
        AuditLogger.log_action(
            db=db,
            action="update",
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            tenant_id=tenant_id,
            details=details,
            success=True,
        )

    @staticmethod
    def log_delete(
        db: Session,
        resource_type: str,
        resource_id: str,
        user_id: str,
        tenant_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log a resource deletion action."""
        AuditLogger.log_action(
            db=db,
            action="delete",
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            tenant_id=tenant_id,
            details=details,
            success=True,
        )

    @staticmethod
    def log_failed_action(
        db: Session,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: str,
        error_message: str,
        tenant_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log a failed action attempt."""
        AuditLogger.log_action(
            db=db,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            tenant_id=tenant_id,
            details=details,
            success=False,
            error_message=error_message,
        )
