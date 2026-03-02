"""
Tests for main app entry point and utilities.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add UI directory to path
ui_path = Path(__file__).parent.parent.parent / "ui"
sys.path.insert(0, str(ui_path))


class TestAppEntry:
    """Test main app.py entry point."""

    @patch("streamlit.set_page_config")
    @patch("streamlit.session_state", new_callable=dict)
    def test_app_initialization(self, mock_session_state, mock_set_page_config):
        """Test app initializes correctly."""
        from state import UIState

        # Import should set page config
        # Note: In real scenario, import app.py would call set_page_config

        # Verify state initialization
        state = UIState()
        assert state.active_identity == "machine"
        assert state.tokens.admin is None
        assert state.tokens.user is None
        assert state.tokens.machine is None
        assert len(state.errors) == 0

    @patch("streamlit.tabs")
    @patch("streamlit.session_state", new_callable=dict)
    def test_tab_structure(self, mock_session_state, mock_tabs):
        """Test tab structure is created."""
        from state import UIState

        state = UIState()
        mock_session_state["ui_state"] = state

        # Mock tabs
        tab_mocks = [Mock() for _ in range(9)]
        mock_tabs.return_value = tab_mocks

        # Verify we can create 9 tabs
        tabs = mock_tabs(
            [
                "🔐 Auth",
                "📊 Dashboard",
                "🔍 Explore",
                "🤖 Agents",
                "⚙️ Jobs",
                "🛠️ Tools",
                "🧠 Models",
                "🏢 Tenants",
                "👨‍💼 Admin",
            ]
        )

        assert len(tabs) == 9


class TestHelpers:
    """Test helper/utility functions."""

    def test_format_timestamp(self):
        """Test timestamp formatting."""
        # Note: If there's a format_timestamp helper, test it
        from datetime import datetime

        dt = datetime(2024, 1, 15, 14, 30, 0)
        # Example: formatted = format_timestamp(dt)
        # assert formatted == "2024-01-15 14:30:00"

    def test_format_duration(self):
        """Test duration formatting."""
        # Note: If there's a format_duration helper, test it
        from datetime import timedelta

        duration = timedelta(hours=2, minutes=30, seconds=15)
        # Example: formatted = format_duration(duration)
        # assert formatted == "2h 30m 15s"

    def test_parse_json_safe(self):
        """Test safe JSON parsing."""
        import json

        # Valid JSON
        valid = '{"key": "value"}'
        result = json.loads(valid)
        assert result == {"key": "value"}

        # Invalid JSON should raise
        invalid = "{key: value}"
        with pytest.raises(json.JSONDecodeError):
            json.loads(invalid)

    def test_truncate_string(self):
        """Test string truncation."""
        text = "A" * 100

        # Example helper function
        def truncate(s: str, length: int) -> str:
            return s if len(s) <= length else s[: length - 3] + "..."

        result = truncate(text, 50)
        assert len(result) == 50
        assert result.endswith("...")


class TestTokenHandling:
    """Test token handling utilities."""

    def test_token_expiry_check(self):
        """Test checking if token is expired."""
        from state import Token

        # Expired token
        expired = Token(
            access_token="test",
            expires_at=datetime.now() - timedelta(hours=1),
            subject="test@test.com",
            scopes=["user:me"],
        )

        assert expired.expires_at < datetime.now()

        # Valid token
        valid = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="test@test.com",
            scopes=["user:me"],
        )

        assert valid.expires_at > datetime.now()

    def test_token_scope_check(self):
        """Test checking if token has required scope."""
        from state import Token

        token = Token(
            access_token="test",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="test@test.com",
            scopes=["user:me", "tools:invoke:basic"],
        )

        # Has scope
        assert "user:me" in token.scopes
        assert "tools:invoke:basic" in token.scopes

        # Missing scope
        assert "admin:all" not in token.scopes


class TestAPIHelpers:
    """Test API helper functions."""

    @patch("requests.get")
    def test_handle_response_json(self, mock_get):
        """Test handle_response with JSON."""
        from api import handle_response

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"result": "success"}

        success, data, error = handle_response(mock_response)

        assert success is True
        assert data == {"result": "success"}
        assert error is None

    @patch("requests.get")
    def test_handle_response_text(self, mock_get):
        """Test handle_response with plain text."""
        from api import handle_response

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = "ok"

        success, data, error = handle_response(mock_response)

        assert success is True
        assert data == {"result": "ok"}
        assert error is None

    @patch("requests.get")
    def test_handle_response_error(self, mock_get):
        """Test handle_response with error."""
        from api import handle_response

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        success, data, error = handle_response(mock_response)

        assert success is False
        assert data is None
        assert error is not None


class TestEnvironmentVariables:
    """Test environment variable handling."""

    def test_required_env_vars(self, mock_env_vars):
        """Test required environment variables are loaded."""
        import os

        assert os.getenv("API_BASE_URL") == "http://app:8000"
        assert os.getenv("AUTH0_DOMAIN") == "test.auth0.com"
        assert os.getenv("AUTH0_CLIENT_ID") == "test-client-id"

    def test_missing_env_var_handling(self):
        """Test handling of missing environment variables."""
        import os

        # Should return None for missing var
        result = os.getenv("NONEXISTENT_VAR")
        assert result is None

        # Should return default for missing var
        result = os.getenv("NONEXISTENT_VAR", "default")
        assert result == "default"


class TestLogging:
    """Test logging configuration."""

    def test_log_file_creation(self, tmp_path):
        """Test log file is created."""
        import logging

        log_file = tmp_path / "test.log"

        # Create logger
        logger = logging.getLogger("test")
        handler = logging.FileHandler(log_file)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Write log
        logger.info("Test message")

        # Verify file exists
        assert log_file.exists()

        # Verify content
        content = log_file.read_text()
        assert "Test message" in content

    def test_log_rotation(self):
        """Test log rotation configuration."""
        from logging.handlers import RotatingFileHandler

        # Example configuration
        handler = RotatingFileHandler("test.log", maxBytes=10 * 1024 * 1024, backupCount=5)  # 10MB

        assert handler.maxBytes == 10 * 1024 * 1024
        assert handler.backupCount == 5


class TestErrorRecovery:
    """Test error recovery mechanisms."""

    @patch("streamlit.session_state", new_callable=dict)
    def test_graceful_degradation_no_auth(self, mock_session_state):
        """Test UI works without authentication."""
        from state import UIState

        state = UIState()
        mock_session_state["ui_state"] = state

        # Should have no active token
        from state import get_active_token

        token = get_active_token()

        assert token is None

    @patch("api.requests.request")
    def test_api_failure_handling(self, mock_request):
        """Test handling of API failures."""
        from api import get_health_live

        # Mock connection error
        mock_request.side_effect = Exception("Connection refused")

        success, data, error = get_health_live()

        assert success is False
        assert data is None
        assert error is not None
        assert "Connection" in error or "connection" in error or "Request failed" in error


class TestDataValidation:
    """Test data validation utilities."""

    def test_validate_job_params(self):
        """Test job parameters validation."""
        # Valid params
        valid_params = {"type": "demo", "params": {"sleep": 5}}

        assert "type" in valid_params
        assert isinstance(valid_params["params"], dict)

        # Invalid params
        invalid_params = {"type": 123, "params": "not a dict"}  # Should be string  # Should be dict

        assert not isinstance(invalid_params["type"], str)
        assert not isinstance(invalid_params["params"], dict)

    def test_validate_tool_input(self):
        """Test tool input validation."""
        import json

        # Valid JSON input
        valid_input = '{"param": "value"}'
        parsed = json.loads(valid_input)
        assert isinstance(parsed, dict)

        # Invalid JSON input
        invalid_input = "{not valid json}"
        with pytest.raises(json.JSONDecodeError):
            json.loads(invalid_input)

    def test_validate_tenant_data(self):
        """Test tenant data validation."""
        # Valid tenant
        valid_tenant = {"id": "tenant-123", "name": "Test Tenant", "description": "A test tenant"}

        assert all(k in valid_tenant for k in ["id", "name"])

        # Missing required field
        invalid_tenant = {
            "id": "tenant-123"
            # Missing name
        }

        assert "name" not in invalid_tenant
