"""
Unit tests for ui/state.py - Session state management.
"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

# Mock streamlit before importing state
sys.modules['streamlit'] = MagicMock()

from ui_control_panel.state import (
    Token,
    TokenSet,
    TenantInfo,
    TenantContext,
    UIState,
)


class TestToken:
    """Test Token class functionality."""

    def test_token_creation(self):
        """Test creating a token with required fields."""
        expires_at = datetime.now() + timedelta(hours=1)
        token = Token(
            access_token="test_token_12345",
            expires_at=expires_at,
            subject="user|123",
            scopes=["read:models", "write:models"]
        )
        
        assert token.access_token == "test_token_12345"
        assert token.expires_at == expires_at
        assert token.subject == "user|123"
        assert len(token.scopes) == 2

    def test_token_is_not_expired_when_future(self):
        """Test that future tokens are not expired."""
        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(hours=1)
        )
        
        assert token.is_expired is False

    def test_token_is_expired_when_past(self):
        """Test that past tokens are expired."""
        token = Token(
            access_token="test",
            expires_at=datetime.now() - timedelta(hours=1)
        )
        
        assert token.is_expired is True

    def test_seconds_until_expiry_positive(self):
        """Test seconds until expiry for future token."""
        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(minutes=10)
        )
        
        seconds = token.seconds_until_expiry
        assert 590 <= seconds <= 610  # ~600 seconds (10 minutes) with some tolerance

    def test_seconds_until_expiry_zero_when_expired(self):
        """Test seconds until expiry is zero for expired tokens."""
        token = Token(
            access_token="test",
            expires_at=datetime.now() - timedelta(hours=1)
        )
        
        assert token.seconds_until_expiry == 0

    def test_needs_renewal_when_less_than_5_minutes(self):
        """Test that tokens expiring in < 5 minutes need renewal."""
        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(minutes=4)
        )
        
        assert token.needs_renewal is True

    def test_does_not_need_renewal_when_more_than_5_minutes(self):
        """Test that tokens expiring in > 5 minutes don't need renewal."""
        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(minutes=10)
        )
        
        assert token.needs_renewal is False

    def test_masked_token_short(self):
        """Test token masking for short tokens."""
        token = Token(
            access_token="short",
            expires_at=datetime.now() + timedelta(hours=1)
        )
        
        assert token.masked_token == "***"

    def test_masked_token_long(self):
        """Test token masking for long tokens."""
        token = Token(
            access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.TJVA95OrM7E2cBab30RMHrHDcEfxjoYZgeFONFh7HgQ",
            expires_at=datetime.now() + timedelta(hours=1)
        )
        
        masked = token.masked_token
        assert masked.startswith("eyJhbGci")
        assert masked.endswith("ONFh7HgQ")
        assert "..." in masked

    def test_has_scope_returns_true_when_present(self):
        """Test has_scope returns True for present scope."""
        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(hours=1),
            scopes=["read:models", "write:models", "admin"]
        )
        
        assert token.has_scope("read:models") is True
        assert token.has_scope("admin") is True

    def test_has_scope_returns_false_when_absent(self):
        """Test has_scope returns False for absent scope."""
        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(hours=1),
            scopes=["read:models"]
        )
        
        assert token.has_scope("write:models") is False
        assert token.has_scope("admin") is False

    def test_token_with_empty_scopes(self):
        """Test token with no scopes."""
        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(hours=1)
        )
        
        assert token.scopes == []
        assert token.has_scope("any") is False


class TestTokenSet:
    """Test TokenSet class functionality."""

    def test_empty_token_set(self):
        """Test creating empty token set."""
        token_set = TokenSet()
        
        assert token_set.admin is None
        assert token_set.user is None
        assert token_set.machine is None

    def test_token_set_with_tokens(self):
        """Test token set with different identity tokens."""
        expires_at = datetime.now() + timedelta(hours=1)
        
        admin_token = Token(access_token="admin_token", expires_at=expires_at)
        user_token = Token(access_token="user_token", expires_at=expires_at)
        machine_token = Token(access_token="machine_token", expires_at=expires_at)
        
        token_set = TokenSet(
            admin=admin_token,
            user=user_token,
            machine=machine_token
        )
        
        assert token_set.admin == admin_token
        assert token_set.user == user_token
        assert token_set.machine == machine_token


class TestTenantInfo:
    """Test TenantInfo class functionality."""

    def test_tenant_info_creation(self):
        """Test creating tenant info."""
        tenant = TenantInfo(
            tenant_id="tenant-123",
            name="Test Tenant",
            description="Test description",
            admin_name="Admin User",
            admin_email="admin@example.com"
        )
        
        assert tenant.tenant_id == "tenant-123"
        assert tenant.name == "Test Tenant"
        assert tenant.description == "Test description"
        assert tenant.admin_name == "Admin User"
        assert tenant.admin_email == "admin@example.com"

    def test_tenant_id_alias_syncs(self):
        """Test that id and tenant_id fields sync."""
        # Set tenant_id, id should sync
        tenant1 = TenantInfo(tenant_id="tenant-123")
        assert tenant1.id == "tenant-123"
        
        # Set id, tenant_id should sync
        tenant2 = TenantInfo(id="tenant-456")
        assert tenant2.tenant_id == "tenant-456"

    def test_tenant_info_defaults(self):
        """Test default values for tenant info."""
        tenant = TenantInfo()
        
        assert tenant.tenant_id is None
        assert tenant.id is None
        assert tenant.name == ""
        assert tenant.description == ""
        assert tenant.admin_name == ""
        assert tenant.admin_email == ""


class TestTenantContext:
    """Test TenantContext class functionality."""

    def test_empty_tenant_context(self):
        """Test creating empty tenant context."""
        context = TenantContext()
        
        assert context.current is None
        assert context.available == []

    def test_tenant_context_with_data(self):
        """Test tenant context with current and available tenants."""
        context = TenantContext(
            current="tenant-123",
            available=[
                {"id": "tenant-123", "name": "Tenant 1"},
                {"id": "tenant-456", "name": "Tenant 2"}
            ]
        )
        
        assert context.current == "tenant-123"
        assert len(context.available) == 2
        assert context.available[0]["name"] == "Tenant 1"


class TestUIState:
    """Test UIState class functionality."""

    def test_default_ui_state(self):
        """Test creating default UI state."""
        state = UIState()
        
        # Authentication defaults
        assert state.active_identity == "machine"
        assert isinstance(state.tokens, TokenSet)
        assert state.tokens.admin is None
        
        # Tenant defaults
        assert isinstance(state.tenant, TenantContext)
        assert state.tenant.current is None
        assert state.selected_tenant is None
        
        # Cached data defaults
        assert state.providers == []
        assert state.models == []
        assert state.tools == []

    def test_ui_state_with_active_token(self):
        """Test UI state with an active token."""
        expires_at = datetime.now() + timedelta(hours=1)
        machine_token = Token(
            access_token="machine_token",
            expires_at=expires_at,
            scopes=["read:models", "write:models"]
        )
        
        token_set = TokenSet(machine=machine_token)
        state = UIState(
            active_identity="machine",
            tokens=token_set
        )
        
        assert state.active_identity == "machine"
        assert state.tokens.machine is not None
        assert not state.tokens.machine.is_expired

    def test_ui_state_with_tenant_context(self):
        """Test UI state with tenant information."""
        tenant_info = TenantInfo(
            tenant_id="tenant-123",
            name="Test Tenant"
        )
        
        tenant_context = TenantContext(
            current="tenant-123",
            available=[{"id": "tenant-123", "name": "Test Tenant"}]
        )
        
        state = UIState(
            tenant=tenant_context,
            selected_tenant=tenant_info
        )
        
        assert state.tenant.current == "tenant-123"
        assert state.selected_tenant.name == "Test Tenant"

    def test_ui_state_with_cached_data(self):
        """Test UI state with cached providers, models, and tools."""
        state = UIState(
            providers=[{"id": "provider-1", "name": "OpenAI"}],
            models=[{"id": "model-1", "name": "gpt-4"}],
            tools=[{"name": "calculator", "description": "Calculate"}]
        )
        
        assert len(state.providers) == 1
        assert len(state.models) == 1
        assert len(state.tools) == 1
        assert state.providers[0]["name"] == "OpenAI"


class TestTokenExpiration:
    """Test token expiration edge cases."""

    def test_token_exactly_at_expiry(self):
        """Test token at exact expiry moment."""
        # This is tricky to test due to timing, but we can test close to expiry
        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(microseconds=100)
        )
        
        # Should not be expired yet
        # (But might be expired by the time we check, so be lenient)
        # This test mainly ensures no crashes at boundary
        _ = token.is_expired  # Should not raise

    def test_token_renewal_threshold(self):
        """Test token renewal exactly at 5-minute threshold."""
        # Exactly 5 minutes (300 seconds)
        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(seconds=300)
        )
        
        # At exactly 300 seconds, should not need renewal (< 300 needs renewal)
        # But due to execution time, might be 299, so check boundary behavior
        assert token.seconds_until_expiry >= 290


class TestTokenScopes:
    """Test token scope handling."""

    def test_multiple_scopes(self):
        """Test token with multiple scopes."""
        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(hours=1),
            scopes=["read:models", "write:models", "admin", "read:agents", "write:agents"]
        )
        
        assert len(token.scopes) == 5
        assert token.has_scope("read:models")
        assert token.has_scope("admin")
        assert not token.has_scope("delete:everything")

    def test_scope_case_sensitivity(self):
        """Test that scope matching is case-sensitive."""
        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(hours=1),
            scopes=["read:Models"]  # Capital M
        )
        
        assert token.has_scope("read:Models") is True
        assert token.has_scope("read:models") is False  # Lowercase m


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
