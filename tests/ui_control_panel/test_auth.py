"""
Comprehensive tests for authentication functionality.
Tests both successful auth and error cases when credentials are missing.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import os


class TestAuthenticationCredentialChecks:
    """Test authentication credential validation."""

    @patch.dict(os.environ, {}, clear=True)
    @patch("streamlit.error")
    def test_admin_login_missing_all_credentials(self, mock_error):
        """Test admin login fails when all credentials are missing."""
        from views.auth import _login_admin

        # Call login with no env vars set
        _login_admin()

        # Should show error about missing credentials
        mock_error.assert_called_once()
        error_msg = mock_error.call_args[0][0]
        assert "AUTH0_USER_CLIENT_ID" in error_msg
        assert "AUTH0_USER_CLIENT_SECRET" in error_msg
        assert "AUTH0_ADMIN_USERNAME" in error_msg
        assert "AUTH0_ADMIN_PASSWORD" in error_msg

    @patch.dict(os.environ, {"AUTH0_USER_CLIENT_ID": "test-id"}, clear=True)
    @patch("streamlit.error")
    def test_admin_login_missing_partial_credentials(self, mock_error):
        """Test admin login fails when some credentials are missing."""
        from views.auth import _login_admin

        # Call login with only client_id set
        _login_admin()

        # Should show error about missing credentials
        mock_error.assert_called_once()
        error_msg = mock_error.call_args[0][0]
        assert "not configured" in error_msg

    @patch.dict(os.environ, {}, clear=True)
    @patch("streamlit.error")
    def test_user_login_missing_all_credentials(self, mock_error):
        """Test user login fails when all credentials are missing."""
        from views.auth import _login_user

        # Call login with no env vars set
        _login_user()

        # Should show error about missing credentials
        mock_error.assert_called_once()
        error_msg = mock_error.call_args[0][0]
        assert "AUTH0_USER_CLIENT_ID" in error_msg
        assert "AUTH0_USER_CLIENT_SECRET" in error_msg
        assert "AUTH0_USER_USERNAME" in error_msg
        assert "AUTH0_USER_PASSWORD" in error_msg

    @patch.dict(os.environ, {}, clear=True)
    @patch("streamlit.error")
    def test_machine_token_missing_credentials(self, mock_error):
        """Test machine token fetch fails when credentials are missing."""
        from views.auth import _fetch_machine_token

        # Call fetch with no env vars set
        _fetch_machine_token()

        # Should show error about missing credentials
        mock_error.assert_called_once()
        error_msg = mock_error.call_args[0][0]
        assert "AUTH0_MACHINE_CLIENT_ID" in error_msg
        assert "AUTH0_MACHINE_CLIENT_SECRET" in error_msg


class TestAdminAuthentication:
    """Test admin authentication flow."""

    @patch.dict(
        os.environ,
        {
            "AUTH0_USER_CLIENT_ID": "test-client",
            "AUTH0_USER_CLIENT_SECRET": "test-secret",
            "AUTH0_ADMIN_USERNAME": "admin@test.com",
            "AUTH0_ADMIN_PASSWORD": "admin-password",
        },
    )
    @patch("views.auth.fetch_auth0_token")
    @patch("views.auth.set_token")
    @patch("streamlit.success")
    @patch("streamlit.rerun")
    @patch("streamlit.spinner")
    def test_admin_login_success(self, mock_spinner, mock_rerun, mock_success, mock_set_token, mock_fetch):
        """Test successful admin login."""
        from views.auth import _login_admin

        # Mock successful token fetch
        mock_spinner.return_value.__enter__ = Mock()
        mock_spinner.return_value.__exit__ = Mock()
        mock_fetch.return_value = (True, "admin-token-123", None)

        # Call login
        _login_admin()

        # Verify fetch was called with correct parameters
        mock_fetch.assert_called_once_with(
            grant_type="password",
            client_id="test-client",
            client_secret="test-secret",
            username="admin@test.com",
            password="admin-password",
            scope="user:me tools:invoke:all admin:all",
        )

        # Verify token was stored
        mock_set_token.assert_called_once_with("admin", "admin-token-123")

        # Verify success message and rerun
        mock_success.assert_called()
        mock_rerun.assert_called_once()

    @patch.dict(
        os.environ,
        {
            "AUTH0_USER_CLIENT_ID": "test-client",
            "AUTH0_USER_CLIENT_SECRET": "test-secret",
            "AUTH0_ADMIN_USERNAME": "admin@test.com",
            "AUTH0_ADMIN_PASSWORD": "wrong-password",
        },
    )
    @patch("views.auth.fetch_auth0_token")
    @patch("streamlit.error")
    @patch("streamlit.spinner")
    def test_admin_login_failure(self, mock_spinner, mock_error, mock_fetch):
        """Test failed admin login."""
        from views.auth import _login_admin

        # Mock failed token fetch
        mock_spinner.return_value.__enter__ = Mock()
        mock_spinner.return_value.__exit__ = Mock()
        mock_fetch.return_value = (False, None, "Invalid credentials")

        # Call login
        _login_admin()

        # Verify error was shown
        mock_error.assert_called_once()
        error_msg = mock_error.call_args[0][0]
        assert "Login failed" in error_msg
        assert "Invalid credentials" in error_msg


class TestUserAuthentication:
    """Test user authentication flow."""

    @patch.dict(
        os.environ,
        {
            "AUTH0_USER_CLIENT_ID": "test-client",
            "AUTH0_USER_CLIENT_SECRET": "test-secret",
            "AUTH0_USER_USERNAME": "user@test.com",
            "AUTH0_USER_PASSWORD": "user-password",
        },
    )
    @patch("views.auth.fetch_auth0_token")
    @patch("views.auth.set_token")
    @patch("streamlit.success")
    @patch("streamlit.rerun")
    @patch("streamlit.spinner")
    def test_user_login_success(self, mock_spinner, mock_rerun, mock_success, mock_set_token, mock_fetch):
        """Test successful user login."""
        from views.auth import _login_user

        # Mock successful token fetch
        mock_spinner.return_value.__enter__ = Mock()
        mock_spinner.return_value.__exit__ = Mock()
        mock_fetch.return_value = (True, "user-token-456", None)

        # Call login
        _login_user()

        # Verify fetch was called with correct parameters
        mock_fetch.assert_called_once_with(
            grant_type="password",
            client_id="test-client",
            client_secret="test-secret",
            username="user@test.com",
            password="user-password",
            scope="user:me tools:invoke:basic",
        )

        # Verify token was stored
        mock_set_token.assert_called_once_with("user", "user-token-456")

        # Verify success message and rerun
        mock_success.assert_called()
        mock_rerun.assert_called_once()

    @patch.dict(
        os.environ,
        {
            "AUTH0_USER_CLIENT_ID": "test-client",
            "AUTH0_USER_CLIENT_SECRET": "test-secret",
            "AUTH0_USER_USERNAME": "user@test.com",
            "AUTH0_USER_PASSWORD": "wrong-password",
        },
    )
    @patch("views.auth.fetch_auth0_token")
    @patch("streamlit.error")
    @patch("streamlit.spinner")
    def test_user_login_failure(self, mock_spinner, mock_error, mock_fetch):
        """Test failed user login."""
        from views.auth import _login_user

        # Mock failed token fetch
        mock_spinner.return_value.__enter__ = Mock()
        mock_spinner.return_value.__exit__ = Mock()
        mock_fetch.return_value = (False, None, "Wrong username or password")

        # Call login
        _login_user()

        # Verify error was shown
        mock_error.assert_called_once()
        error_msg = mock_error.call_args[0][0]
        assert "Login failed" in error_msg
        assert "Wrong username or password" in error_msg


class TestMachineAuthentication:
    """Test machine token authentication flow."""

    @patch.dict(
        os.environ, {"AUTH0_MACHINE_CLIENT_ID": "machine-client", "AUTH0_MACHINE_CLIENT_SECRET": "machine-secret"}
    )
    @patch("views.auth.fetch_auth0_token")
    @patch("views.auth.set_token")
    @patch("streamlit.success")
    @patch("streamlit.rerun")
    @patch("streamlit.spinner")
    def test_machine_token_fetch_success(self, mock_spinner, mock_rerun, mock_success, mock_set_token, mock_fetch):
        """Test successful machine token fetch."""
        from views.auth import _fetch_machine_token

        # Mock successful token fetch
        mock_spinner.return_value.__enter__ = Mock()
        mock_spinner.return_value.__exit__ = Mock()
        mock_fetch.return_value = (True, "machine-token-789", None)

        # Call fetch
        _fetch_machine_token()

        # Verify fetch was called with correct parameters
        mock_fetch.assert_called_once_with(
            grant_type="client_credentials", client_id="machine-client", client_secret="machine-secret"
        )

        # Verify token was stored
        mock_set_token.assert_called_once_with("machine", "machine-token-789")

        # Verify success message and rerun
        mock_success.assert_called()
        mock_rerun.assert_called_once()

    @patch.dict(
        os.environ, {"AUTH0_MACHINE_CLIENT_ID": "machine-client", "AUTH0_MACHINE_CLIENT_SECRET": "wrong-secret"}
    )
    @patch("views.auth.fetch_auth0_token")
    @patch("streamlit.error")
    @patch("streamlit.spinner")
    def test_machine_token_fetch_failure(self, mock_spinner, mock_error, mock_fetch):
        """Test failed machine token fetch."""
        from views.auth import _fetch_machine_token

        # Mock failed token fetch
        mock_spinner.return_value.__enter__ = Mock()
        mock_spinner.return_value.__exit__ = Mock()
        mock_fetch.return_value = (False, None, "Invalid client credentials")

        # Call fetch
        _fetch_machine_token()

        # Verify error was shown
        mock_error.assert_called_once()
        error_msg = mock_error.call_args[0][0]
        assert "Token fetch failed" in error_msg
        assert "Invalid client credentials" in error_msg


class TestAuthenticationTokenManagement:
    """Test token management (logout, renewal)."""

    @patch("views.auth.clear_token")
    @patch("streamlit.success")
    @patch("streamlit.rerun")
    def test_admin_logout(self, mock_rerun, mock_success, mock_clear):
        """Test admin logout."""
        from views.auth import _login_admin

        # Simulate logout by clearing token
        mock_clear("admin")

        mock_clear.assert_called_once_with("admin")

    @patch("views.auth.clear_token")
    def test_user_logout(self, mock_clear):
        """Test user logout."""
        from views.auth import _login_user

        # Simulate logout by clearing token
        mock_clear("user")

        mock_clear.assert_called_once_with("user")


class TestAuthenticationWithSecretsFallback:
    """Test authentication with secrets.toml fallback."""

    @patch.dict(os.environ, {}, clear=True)
    @patch("views.auth.fetch_auth0_token")
    @patch("views.auth.set_token")
    @patch("streamlit.success")
    @patch("streamlit.rerun")
    @patch("streamlit.spinner")
    def test_admin_login_with_secrets(self, mock_spinner, mock_rerun, mock_success, mock_set_token, mock_fetch):
        """Test admin login using secrets.toml when env vars not set."""
        from views.auth import _login_admin

        # Mock streamlit secrets
        import streamlit as st

        st.secrets.get = MagicMock(
            side_effect=lambda key: {
                "AUTH0_USER_CLIENT_ID": "secret-client",
                "AUTH0_USER_CLIENT_SECRET": "secret-secret",
                "AUTH0_ADMIN_USERNAME": "admin@secret.com",
                "AUTH0_ADMIN_PASSWORD": "secret-password",
            }.get(key)
        )

        # Mock successful token fetch
        mock_spinner.return_value.__enter__ = Mock()
        mock_spinner.return_value.__exit__ = Mock()
        mock_fetch.return_value = (True, "admin-token-secret", None)

        # Call login
        _login_admin()

        # Verify fetch was called with credentials from secrets
        mock_fetch.assert_called_once()
        call_args = mock_fetch.call_args[1]
        assert call_args["client_id"] == "secret-client"
        assert call_args["username"] == "admin@secret.com"

    @patch.dict(os.environ, {}, clear=True)
    @patch("views.auth.fetch_auth0_token")
    @patch("views.auth.set_token")
    @patch("streamlit.success")
    @patch("streamlit.rerun")
    @patch("streamlit.spinner")
    def test_machine_token_with_secrets(self, mock_spinner, mock_rerun, mock_success, mock_set_token, mock_fetch):
        """Test machine token using secrets.toml when env vars not set."""
        from views.auth import _fetch_machine_token

        # Mock streamlit secrets
        import streamlit as st

        st.secrets.get = MagicMock(
            side_effect=lambda key: {
                "AUTH0_MACHINE_CLIENT_ID": "secret-machine-client",
                "AUTH0_MACHINE_CLIENT_SECRET": "secret-machine-secret",
            }.get(key)
        )

        # Mock successful token fetch
        mock_spinner.return_value.__enter__ = Mock()
        mock_spinner.return_value.__exit__ = Mock()
        mock_fetch.return_value = (True, "machine-token-secret", None)

        # Call fetch
        _fetch_machine_token()

        # Verify fetch was called with credentials from secrets
        mock_fetch.assert_called_once()
        call_args = mock_fetch.call_args[1]
        assert call_args["client_id"] == "secret-machine-client"


class TestAuthenticationErrorMessages:
    """Test authentication error messages match UI."""

    @patch.dict(os.environ, {}, clear=True)
    @patch("streamlit.error")
    def test_admin_error_message_exact_match(self, mock_error):
        """Test admin error message matches UI exactly."""
        from views.auth import _login_admin

        _login_admin()

        error_msg = mock_error.call_args[0][0]
        expected = "Auth0 admin credentials not configured. Please set AUTH0_USER_CLIENT_ID, AUTH0_USER_CLIENT_SECRET, AUTH0_ADMIN_USERNAME, and AUTH0_ADMIN_PASSWORD environment variables."
        assert error_msg == expected

    @patch.dict(os.environ, {}, clear=True)
    @patch("streamlit.error")
    def test_user_error_message_exact_match(self, mock_error):
        """Test user error message matches UI exactly."""
        from views.auth import _login_user

        _login_user()

        error_msg = mock_error.call_args[0][0]
        expected = "Auth0 user credentials not configured. Please set AUTH0_USER_CLIENT_ID, AUTH0_USER_CLIENT_SECRET, AUTH0_USER_USERNAME, and AUTH0_USER_PASSWORD environment variables."
        assert error_msg == expected

    @patch.dict(os.environ, {}, clear=True)
    @patch("streamlit.error")
    def test_machine_error_message_exact_match(self, mock_error):
        """Test machine error message matches UI exactly."""
        from views.auth import _fetch_machine_token

        # Mock streamlit secrets to return None
        import streamlit as st

        st.secrets.get = MagicMock(return_value=None)

        _fetch_machine_token()

        error_msg = mock_error.call_args[0][0]
        expected = "Auth0 machine credentials not configured. Please set AUTH0_MACHINE_CLIENT_ID and AUTH0_MACHINE_CLIENT_SECRET environment variables."
        assert error_msg == expected
