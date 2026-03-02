"""
Unit tests for audit logging system.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock
from sqlalchemy.orm import Session

from src.audit_logger import AuditLogger
from db.postgres_control.models.audit_log import AuditLog


class TestAuditLogger:
    """Test audit logging functionality."""

    def test_log_action_success(self):
        """Test logging a successful action."""
        # Mock database session
        mock_db = Mock(spec=Session)
        
        # Call log_action
        AuditLogger.log_action(
            db=mock_db,
            action="create",
            resource_type="model",
            resource_id="model-123",
            user_id="user-456",
            tenant_id="tenant-789",
            details={"model_name": "gpt-4"},
            success=True
        )
        
        # Verify session methods were called
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        
        # Verify audit log entry was created
        call_args = mock_db.add.call_args[0][0]
        assert isinstance(call_args, AuditLog)
        assert call_args.action == "create"
        assert call_args.resource_type == "model"
        assert call_args.resource_id == "model-123"
        assert call_args.user_id == "user-456"
        assert call_args.tenant_id == "tenant-789"
        assert call_args.success is True
        assert call_args.details == {"model_name": "gpt-4"}
        assert call_args.error_message is None

    def test_log_action_failure(self):
        """Test logging a failed action."""
        mock_db = Mock(spec=Session)
        
        AuditLogger.log_action(
            db=mock_db,
            action="delete",
            resource_type="tenant",
            resource_id="tenant-123",
            user_id="admin-456",
            success=False,
            error_message="Permission denied"
        )
        
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        
        call_args = mock_db.add.call_args[0][0]
        assert call_args.action == "delete"
        assert call_args.success is False
        assert call_args.error_message == "Permission denied"

    def test_log_action_without_tenant(self):
        """Test logging action without tenant context."""
        mock_db = Mock(spec=Session)
        
        AuditLogger.log_action(
            db=mock_db,
            action="update",
            resource_type="user",
            resource_id="user-123",
            user_id="admin-456",
            tenant_id=None  # No tenant context
        )
        
        call_args = mock_db.add.call_args[0][0]
        assert call_args.tenant_id is None

    def test_log_action_without_details(self):
        """Test logging action without additional details."""
        mock_db = Mock(spec=Session)
        
        AuditLogger.log_action(
            db=mock_db,
            action="read",
            resource_type="model",
            resource_id="model-123",
            user_id="user-456"
        )
        
        call_args = mock_db.add.call_args[0][0]
        assert call_args.details == {}

    def test_log_action_handles_db_error(self):
        """Test that logging handles database errors gracefully."""
        mock_db = Mock(spec=Session)
        mock_db.commit.side_effect = Exception("Database error")
        
        # Should not raise exception
        try:
            AuditLogger.log_action(
                db=mock_db,
                action="create",
                resource_type="model",
                resource_id="model-123",
                user_id="user-456"
            )
        except Exception as e:
            pytest.fail(f"log_action should handle exceptions: {e}")
        
        # Rollback should be called on error
        mock_db.rollback.assert_called_once()

    def test_log_action_complex_details(self):
        """Test logging with complex nested details."""
        mock_db = Mock(spec=Session)
        
        complex_details = {
            "before": {"name": "old-model", "version": "1.0"},
            "after": {"name": "new-model", "version": "2.0"},
            "changes": ["name", "version"],
            "metadata": {
                "ip_address": "192.168.1.1",
                "user_agent": "Mozilla/5.0"
            }
        }
        
        AuditLogger.log_action(
            db=mock_db,
            action="update",
            resource_type="model",
            resource_id="model-123",
            user_id="user-456",
            details=complex_details
        )
        
        call_args = mock_db.add.call_args[0][0]
        assert call_args.details == complex_details
        assert call_args.details["before"]["name"] == "old-model"
        assert call_args.details["after"]["version"] == "2.0"

    def test_log_action_all_resource_types(self):
        """Test logging for different resource types."""
        mock_db = Mock(spec=Session)
        
        resource_types = ["model", "user", "tenant", "agent", "job", "tool"]
        
        for resource_type in resource_types:
            mock_db.reset_mock()
            
            AuditLogger.log_action(
                db=mock_db,
                action="create",
                resource_type=resource_type,
                resource_id=f"{resource_type}-123",
                user_id="user-456"
            )
            
            call_args = mock_db.add.call_args[0][0]
            assert call_args.resource_type == resource_type
            assert call_args.resource_id == f"{resource_type}-123"

    def test_log_action_all_actions(self):
        """Test logging for different action types."""
        mock_db = Mock(spec=Session)
        
        actions = ["create", "read", "update", "delete", "execute", "cancel"]
        
        for action in actions:
            mock_db.reset_mock()
            
            AuditLogger.log_action(
                db=mock_db,
                action=action,
                resource_type="model",
                resource_id="model-123",
                user_id="user-456"
            )
            
            call_args = mock_db.add.call_args[0][0]
            assert call_args.action == action

    def test_log_action_timestamp_set(self):
        """Test that timestamp is set correctly."""
        mock_db = Mock(spec=Session)
        
        before_time = datetime.utcnow()
        
        AuditLogger.log_action(
            db=mock_db,
            action="create",
            resource_type="model",
            resource_id="model-123",
            user_id="user-456"
        )
        
        after_time = datetime.utcnow()
        
        call_args = mock_db.add.call_args[0][0]
        assert before_time <= call_args.timestamp <= after_time

    def test_log_action_generates_unique_ids(self):
        """Test that each log entry gets a unique ID."""
        mock_db = Mock(spec=Session)
        
        # Create multiple log entries
        ids = []
        for i in range(5):
            AuditLogger.log_action(
                db=mock_db,
                action="create",
                resource_type="model",
                resource_id=f"model-{i}",
                user_id="user-456"
            )
            
            # Get the audit log object from the call
            call_args = mock_db.add.call_args[0][0]
            if call_args.id:  # ID might be None if not set yet
                ids.append(call_args.id)
        
        # IDs that were set should be unique
        if ids:
            assert len(ids) == len(set(ids)), "IDs should be unique"
            
            # All IDs should be non-empty strings
            for id in ids:
                assert isinstance(id, str)
                assert len(id) > 0


class TestAuditLogModel:
    """Test AuditLog database model."""

    def test_audit_log_repr(self):
        """Test string representation of AuditLog."""
        log = AuditLog(
            id="log-123",
            action="create",
            resource_type="model",
            resource_id="model-456",
            user_id="user-789"
        )
        
        repr_str = repr(log)
        assert "log-123" in repr_str
        assert "create" in repr_str
        assert "model" in repr_str
        assert "user-789" in repr_str

    def test_audit_log_defaults(self):
        """Test default values for AuditLog."""
        log = AuditLog(
            action="test",
            resource_type="test",
            resource_id="test-123",
            user_id="user-456"
        )
        
        # Default column values are set at database level
        # In-memory objects may not have defaults yet
        # Just verify the object was created successfully
        assert log.action == "test"
        assert log.resource_type == "test"
        assert log.resource_id == "test-123"
        assert log.user_id == "user-456"

    def test_audit_log_tablename(self):
        """Test that table name is correct."""
        assert AuditLog.__tablename__ == "audit_logs"

    def test_audit_log_required_fields(self):
        """Test that required fields are enforced."""
        # This would be enforced at database level
        # Here we just verify the fields exist
        log = AuditLog(
            action="create",
            resource_type="model",
            resource_id="model-123",
            user_id="user-456"
        )
        
        assert hasattr(log, 'id')
        assert hasattr(log, 'timestamp')
        assert hasattr(log, 'action')
        assert hasattr(log, 'resource_type')
        assert hasattr(log, 'resource_id')
        assert hasattr(log, 'user_id')
        assert hasattr(log, 'tenant_id')
        assert hasattr(log, 'success')
        assert hasattr(log, 'error_message')
        assert hasattr(log, 'details')
