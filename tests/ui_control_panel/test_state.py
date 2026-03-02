"""
Tests for state management module (ui_control_panel/state.py).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add UI directory to path
ui_path = Path(__file__).parent.parent.parent / "ui"
sys.path.insert(0, str(ui_path))


class TestToken:
    """Test Token dataclass."""

    def test_token_creation(self):
        """Test creating a token."""
        from state import Token

        expires_at = datetime.now() + timedelta(hours=1)
        token = Token(
            access_token="test-token",
            expires_at=expires_at,
            subject="test-user",
            scopes=["user:me", "tools:invoke:basic"],
        )

        assert token.access_token == "test-token"
        assert token.subject == "test-user"
        assert len(token.scopes) == 2

    def test_token_is_expired_false(self):
        """Test token is not expired."""
        from state import Token

        expires_at = datetime.now() + timedelta(hours=1)
        token = Token(access_token="test-token", expires_at=expires_at, subject="test-user", scopes=[])

        assert token.is_expired is False

    def test_token_is_expired_true(self):
        """Test token is expired."""
        from state import Token

        expires_at = datetime.now() - timedelta(hours=1)
        token = Token(access_token="test-token", expires_at=expires_at, subject="test-user", scopes=[])

        assert token.is_expired is True

    def test_token_has_scope_true(self):
        """Test token has specific scope."""
        from state import Token

        token = Token(
            access_token="test-token",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="test-user",
            scopes=["user:me", "admin:all"],
        )

        assert token.has_scope("user:me") is True

    def test_token_has_scope_false(self):
        """Test token does not have specific scope."""
        from state import Token

        token = Token(
            access_token="test-token",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="test-user",
            scopes=["user:me"],
        )

        assert token.has_scope("admin:all") is False


class TestTokenSet:
    """Test TokenSet dataclass."""

    def test_token_set_creation(self):
        """Test creating a token set."""
        from state import TokenSet

        token_set = TokenSet()

        assert token_set.admin is None
        assert token_set.user is None
        assert token_set.machine is None

    def test_token_set_with_tokens(self):
        """Test token set with tokens."""
        from state import TokenSet, Token

        admin_token = Token(
            access_token="admin-token",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="admin@test.com",
            scopes=["admin:all"],
        )

        token_set = TokenSet(admin=admin_token)

        assert token_set.admin is not None
        assert token_set.admin.subject == "admin@test.com"


class TestUIState:
    """Test UIState dataclass."""

    def test_ui_state_defaults(self):
        """Test UI state default values."""
        from state import UIState

        state = UIState()

        assert state.active_identity == "machine"
        assert state.developer_mode is False
        # Note: selected_tenant attribute not implemented in UIState
        assert len(state.errors) == 0

    def test_ui_state_selected_tenant(self):
        """Test UIState tracks selected tenant."""
        from state import UIState, TenantInfo

        tenant = TenantInfo(tenant_id="T001", name="Test Tenant", admin_name="Admin User", admin_email="admin@test.com")

        state = UIState()
        state.selected_tenant = tenant

        assert state.selected_tenant == tenant
        assert state.selected_tenant.tenant_id == "T001"


class TestStateFunctions:
    """Test state management functions."""

    @patch("streamlit.session_state", new_callable=dict)
    def test_init_state(self, mock_session_state):
        """Test initializing state."""
        from state import init_state, UIState

        state = init_state()

        assert isinstance(state, UIState)
        assert "ui_state" in mock_session_state

    @patch("streamlit.session_state", new_callable=dict)
    def test_get_state_existing(self, mock_session_state):
        """Test getting existing state."""
        from state import UIState, get_state

        existing_state = UIState(developer_mode=True)
        mock_session_state["ui_state"] = existing_state

        state = get_state()

        assert state.developer_mode is True

    @patch("streamlit.session_state", new_callable=dict)
    def test_set_token(self, mock_session_state):
        """Test setting a token."""
        from state import UIState, Token, set_token

        mock_session_state["ui_state"] = UIState()

        token = Token(
            access_token="test-token", expires_at=datetime.now() + timedelta(hours=1), subject="test-user", scopes=[]
        )

        set_token("admin", token)

        state = mock_session_state["ui_state"]
        assert state.tokens.admin is not None
        assert state.tokens.admin.access_token == "test-token"

    @patch("streamlit.session_state", new_callable=dict)
    def test_clear_token(self, mock_session_state):
        """Test clearing a token."""
        from state import UIState, Token, clear_token

        token = Token(
            access_token="test-token", expires_at=datetime.now() + timedelta(hours=1), subject="test-user", scopes=[]
        )

        state = UIState()
        state.tokens.admin = token
        mock_session_state["ui_state"] = state

        clear_token("admin")

        assert mock_session_state["ui_state"].tokens.admin is None

    @patch("streamlit.session_state", new_callable=dict)
    def test_get_active_token_admin(self, mock_session_state):
        """Test getting active admin token."""
        from state import UIState, Token, get_active_token

        admin_token = Token(
            access_token="admin-token",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="admin@test.com",
            scopes=["admin:all"],
        )

        state = UIState(active_identity="admin")
        state.tokens.admin = admin_token
        mock_session_state["ui_state"] = state

        token = get_active_token()

        assert token is not None
        assert token.subject == "admin@test.com"

    @patch("streamlit.session_state", new_callable=dict)
    def test_get_active_token_expired(self, mock_session_state):
        """Test get_active_token returns None for expired token."""
        from state import UIState, Token, TokenSet, get_active_token

        expired_token = Token(
            access_token="expired-token", expires_at=datetime.now() - timedelta(hours=1), subject="test-user"  # Expired
        )

        token_set = TokenSet(user=expired_token)
        state = UIState(active_identity="user")
        state.tokens = token_set
        mock_session_state["ui_state"] = state

        result = get_active_token()
        assert result is None  # Should return None for expired token

    @patch("streamlit.session_state", new_callable=dict)
    def test_add_error(self, mock_session_state):
        """Test adding an error."""
        from state import UIState, add_error

        mock_session_state["ui_state"] = UIState()

        add_error("Test error", "Error details", "trace-123")

        state = mock_session_state["ui_state"]
        assert len(state.errors) == 1
        assert state.errors[0]["message"] == "Test error"
        assert state.errors[0]["trace_id"] == "trace-123"

    @patch("streamlit.session_state", new_callable=dict)
    def test_clear_errors(self, mock_session_state):
        """Test clearing errors."""
        from state import UIState, add_error, clear_errors

        mock_session_state["ui_state"] = UIState()

        add_error("Error 1")
        add_error("Error 2")

        clear_errors()

        state = mock_session_state["ui_state"]
        assert len(state.errors) == 0


class TestTenantInfo:
    """Test TenantInfo dataclass."""

    @patch("streamlit.session_state", new_callable=dict)
    def test_tenant_info_creation(self, mock_session_state):
        """Test TenantInfo can be created with id and description."""
        from state import TenantInfo

        tenant = TenantInfo(id="tenant-123", name="Test Tenant", description="A test tenant")

        assert tenant.id == "tenant-123"
        assert tenant.tenant_id == "tenant-123"  # Should sync
        assert tenant.name == "Test Tenant"
        assert tenant.description == "A test tenant"
