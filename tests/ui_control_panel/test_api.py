"""
Tests for API client module (ui/api.py).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import os
import sys
from pathlib import Path

# Add UI directory to path
ui_path = Path(__file__).parent.parent.parent / "ui"
sys.path.insert(0, str(ui_path))


class TestAPIClient:
    """Test API client functions."""

    def test_get_api_base_from_env(self, mock_env_vars):
        """Test getting API base URL from environment."""
        from api import get_api_base

        url = get_api_base()
        assert url == "http://app:8000"  # From mock_env_vars fixture

    def test_get_api_base_default(self, monkeypatch):
        """Test default API base URL when not set."""
        from api import get_api_base

        # Unset the API_BASE_URL to test default
        monkeypatch.delenv("API_BASE_URL", raising=False)

        url = get_api_base()
        assert url == "http://localhost:8000"

    def test_handle_response_success_json(self):
        """Test handling successful JSON response."""
        from api import handle_response

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"status": "ok"}

        success, data, error = handle_response(mock_response)

        assert success is True
        assert data == {"status": "ok"}
        assert error is None

    def test_handle_response_success_text(self):
        """Test handling successful text response."""
        from api import handle_response

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = "ok"

        success, data, error = handle_response(mock_response)

        assert success is True
        assert data == {"result": "ok"}
        assert error is None

    def test_handle_response_unauthorized(self):
        """Test handling 401 Unauthorized."""
        from api import handle_response

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {}

        success, data, error = handle_response(mock_response)

        assert success is False
        assert data is None
        assert "Unauthorized" in error

    def test_handle_response_forbidden(self):
        """Test handling 403 Forbidden."""
        from api import handle_response

        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = '{"required_scopes": ["admin:all"]}'
        mock_response.json.return_value = {"required_scopes": ["admin:all"]}
        mock_response.headers = {}

        success, data, error = handle_response(mock_response)

        assert success is False
        assert data is None
        assert "admin:all" in error

    def test_handle_response_not_found(self):
        """Test handling 404 Not Found."""
        from api import handle_response

        mock_response = Mock()
        mock_response.status_code = 404

        success, data, error = handle_response(mock_response)

        assert success is False
        assert data is None
        assert "not found" in error.lower()

    def test_handle_response_rate_limit(self):
        """Test handling 429 Rate Limit."""
        from api import handle_response

        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}
        mock_response.text = "Rate limited"

        success, data, error = handle_response(mock_response)

        assert success is False
        assert data is None
        assert "60" in error


class TestAuth0Integration:
    """Test Auth0 token fetching."""

    @patch("api.requests.post")
    def test_fetch_auth0_token_password_grant(self, mock_post, mock_env_vars, sample_token):
        """Test fetching token with password grant."""
        from api import fetch_auth0_token

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_token
        mock_post.return_value = mock_response

        success, token, error = fetch_auth0_token(
            grant_type="password",
            client_id="test-client",
            client_secret="test-secret",
            username="user@test.com",
            password="password",
            scope="user:me",
        )

        assert success is True
        assert token is not None
        assert error is None
        assert token.access_token == sample_token["access_token"]

        # Verify correct Auth0 endpoint was called
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "https://test.auth0.com/oauth/token" in call_args[0][0]

        # Verify correct grant type
        payload = call_args[1]["json"]
        assert payload["grant_type"] == "http://auth0.com/oauth/grant-type/password-realm"
        assert payload["realm"] == "Username-Password-Authentication"

    @patch("api.requests.post")
    def test_fetch_auth0_token_client_credentials(self, mock_post, mock_env_vars, sample_token):
        """Test fetching token with client credentials grant."""
        from api import fetch_auth0_token

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_token
        mock_post.return_value = mock_response

        success, token, error = fetch_auth0_token(
            grant_type="client_credentials", client_id="machine-client", client_secret="machine-secret"
        )

        assert success is True
        assert token is not None
        assert error is None

        # Verify correct grant type
        payload = mock_post.call_args[1]["json"]
        assert payload["grant_type"] == "client_credentials"

    @patch("api.requests.post")
    def test_fetch_auth0_token_failure(self, mock_post, mock_env_vars):
        """Test handling Auth0 token fetch failure."""
        from api import fetch_auth0_token

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "invalid_grant", "error_description": "Wrong username or password"}
        mock_post.return_value = mock_response

        success, token, error = fetch_auth0_token(
            grant_type="password",
            client_id="test-client",
            client_secret="test-secret",
            username="wrong@test.com",
            password="wrongpassword",
        )

        assert success is False
        assert token is None
        assert "Wrong username or password" in error


class TestHealthEndpoints:
    """Test health check endpoints."""

    @patch("api.requests.request")
    def test_get_health_live(self, mock_request):
        """Test /health/live endpoint."""
        from api import get_health_live

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = "ok"
        mock_request.return_value = mock_response

        success, data, error = get_health_live()

        assert success is True
        assert data == {"result": "ok"}
        assert error is None

    @patch("api.requests.request")
    def test_get_health_ready(self, mock_request, sample_health_response):
        """Test /health/ready endpoint."""
        from api import get_health_ready

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = sample_health_response
        mock_request.return_value = mock_response

        success, data, error = get_health_ready()

        assert success is True
        assert data["status"] == "healthy"
        assert "checks" in data
        assert error is None

    @patch("api.requests.request")
    def test_get_health_components(self, mock_request, sample_health_response):
        """Test /health/components endpoint."""
        from api import get_health_components

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = sample_health_response
        mock_request.return_value = mock_response

        success, data, error = get_health_components()

        assert success is True
        assert "checks" in data
        assert error is None
        assert error is None


class TestToolsEndpoints:
    """Test tools endpoints."""

    @patch("api.requests.request")
    def test_list_tools(self, mock_request, sample_tools):
        """Test listing tools."""
        from api import list_tools

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = sample_tools
        mock_request.return_value = mock_response

        success, data, error = list_tools()

        assert success is True
        assert len(data) == 2
        assert error is None

    @patch("api.requests.request")
    def test_invoke_tool(self, mock_request):
        """Test invoking a tool."""
        from api import invoke_tool

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"result": "tool executed"}
        mock_request.return_value = mock_response

        success, data, error = invoke_tool("system.health", {})

        assert success is True
        assert data["result"] == "tool executed"
        assert error is None


class TestAgentEndpoints:
    """Test agent session endpoints."""

    @patch("api.requests.request")
    def test_list_agent_sessions(self, mock_request, sample_agent_session):
        """Test listing agent sessions."""
        from api import list_agent_sessions

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = [sample_agent_session]
        mock_request.return_value = mock_response

        success, data, error = list_agent_sessions()

        assert success is True
        assert len(data) == 1
        assert error is None

    @patch("api.requests.request")
    def test_create_agent_session(self, mock_request, sample_agent_session):
        """Test creating an agent session."""
        from api import create_agent_session

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = sample_agent_session
        mock_request.return_value = mock_response

        success, data, error = create_agent_session({"agent_type": "researcher"})

        assert success is True
        assert data["agent_type"] == "researcher"
        assert error is None


class TestJobsEndpoints:
    """Test jobs endpoints."""

    @patch("api.requests.request")
    def test_list_jobs(self, mock_request, sample_job):
        """Test listing jobs."""
        from api import list_jobs

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = [sample_job]
        mock_request.return_value = mock_response

        success, data, error = list_jobs()

        assert success is True
        assert len(data) == 1
        assert error is None

    @patch("api.requests.request")
    def test_create_job(self, mock_request, sample_job):
        """Test creating a job."""
        from api import create_job

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = sample_job
        mock_request.return_value = mock_response

        success, data, error = create_job({"type": "demo"})

        assert success is True
        assert data["type"] == "demo"
        assert error is None


class TestTenantsEndpoints:
    """Test tenants endpoints."""

    @patch("api.requests.request")
    def test_list_tenants(self, mock_request, sample_tenants):
        """Test listing tenants."""
        from api import list_tenants

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = sample_tenants
        mock_request.return_value = mock_response

        success, data, error = list_tenants()

        assert success is True
        assert len(data) == 2
        assert error is None
        assert error is None
