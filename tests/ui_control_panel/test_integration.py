"""
Integration tests for UI with mocked API.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add UI directory to path
ui_path = Path(__file__).parent.parent.parent / "ui"
sys.path.insert(0, str(ui_path))


class TestUIIntegration:
    """Integration tests for UI components working together."""

    @patch("requests.post")
    @patch("streamlit.session_state", new_callable=dict)
    @patch("streamlit.success")
    @patch("streamlit.error")
    def test_full_auth_flow(self, mock_error, mock_success, mock_session_state, mock_post, mock_env_vars):
        """Test complete authentication flow."""
        from api import fetch_auth0_token
        from state import UIState, set_token, get_active_token

        # Setup
        mock_session_state["ui_state"] = UIState()

        # Mock Auth0 response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbkB0ZXN0LmNvbSIsInNjb3BlIjoidXNlcjptZSBhZG1pbjphbGwiLCJleHAiOjk5OTk5OTk5OTl9.test",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        # Fetch token
        success, token, error = fetch_auth0_token(
            grant_type="password",
            client_id="test-client",
            client_secret="test-secret",
            username="admin@test.com",
            password="password",
            scope="user:me admin:all",
        )

        assert success is True
        assert token is not None

        # Store token
        set_token("admin", token)

        # Verify token is accessible
        active_token = get_active_token()
        assert active_token is None  # Because active_identity is "machine" by default

        # Change active identity
        mock_session_state["ui_state"].active_identity = "admin"

        active_token = get_active_token()
        assert active_token is not None
        assert active_token.subject == "admin@test.com"

    @patch("api.requests.request")
    @patch("streamlit.session_state", new_callable=dict)
    def test_dashboard_health_check_flow(self, mock_session_state, mock_request):
        """Test dashboard health check integration."""
        from api import get_health_live, get_health_ready, get_health_components
        from state import UIState, Token

        # Setup authenticated state
        token = Token(
            access_token="test-token",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="machine@client",
            scopes=["internal:all"],
        )

        state = UIState(active_identity="machine")
        state.tokens.machine = token
        mock_session_state["ui_state"] = state

        # Mock health responses
        def mock_get_response(url, **kwargs):
            response = Mock()
            response.status_code = 200

            if "/health/live" in url:
                response.headers = {"content-type": "text/plain"}
                response.text = "ok"
            else:
                response.headers = {"content-type": "application/json"}
                response.json.return_value = {
                    "status": "healthy",
                    "checks": {"app": {"ok": True, "status": "ok"}, "postgres": {"ok": True, "status": "ok"}},
                }

            return response

        mock_request.side_effect = mock_get_response

        # Test health endpoints
        success, data, error = get_health_live()
        assert success is True
        assert data["result"] == "ok"

        success, data, error = get_health_ready()
        assert success is True
        assert data["status"] == "healthy"

        success, data, error = get_health_components()
        assert success is True
        assert "checks" in data

    @patch("api.requests.request")
    @patch("streamlit.session_state", new_callable=dict)
    def test_tool_invocation_flow(self, mock_session_state, mock_request):
        """Test tool listing and invocation flow."""
        from api import list_tools, invoke_tool
        from state import UIState, Token

        # Setup authenticated state
        token = Token(
            access_token="test-token",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="user@test.com",
            scopes=["user:me", "tools:invoke:basic"],
        )

        state = UIState(active_identity="user")
        state.tokens.user = token
        mock_session_state["ui_state"] = state

        # Mock tools list
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.headers = {"content-type": "application/json"}
        mock_get_response.json.return_value = [{"id": "system.health", "name": "System Health", "safe": True}]

        # Mock POST response for tool invocation
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.headers = {"content-type": "application/json"}
        mock_post_response.json.return_value = {"result": "healthy"}

        # Set side_effect to return different responses based on method
        def mock_request_response(method, url, **kwargs):
            if method.upper() == "GET":
                return mock_get_response
            else:  # POST
                return mock_post_response

        mock_request.side_effect = mock_request_response

        # List tools
        success, tools, error = list_tools()
        assert success is True
        assert len(tools) == 1

        # Invoke tool
        success, result, error = invoke_tool("system.health", {})
        assert success is True
        assert result["result"] == "healthy"

    @patch("api.requests.request")
    @patch("streamlit.session_state", new_callable=dict)
    def test_agent_session_flow(self, mock_session_state, mock_request):
        """Test agent session creation and interaction."""
        from api import list_agent_sessions, create_agent_session, send_agent_message
        from state import UIState, Token

        # Setup authenticated state
        token = Token(
            access_token="admin-token",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="admin@test.com",
            scopes=["admin:all"],
        )

        state = UIState(active_identity="admin")
        state.tokens.admin = token
        mock_session_state["ui_state"] = state

        def mock_request_response(method, url, **kwargs):
            response = Mock()
            response.headers = {"content-type": "application/json"}

            if method == "GET" and "/sessions" in url:
                # List sessions
                response.status_code = 200
                response.json.return_value = []
            elif method == "POST" and "/sessions" in url and "/messages" not in url:
                # Create session
                response.status_code = 201
                response.json.return_value = {
                    "session_id": "new-session-123",
                    "agent_type": "researcher",
                    "status": "active",
                }
            elif method == "POST" and "/messages" in url:
                # Send message
                response.status_code = 200
                response.json.return_value = {"message_id": "msg-456", "response": "Hello! I'm a researcher agent."}
            else:
                response.status_code = 404
                response.json.return_value = {"error": "Not found"}

            return response

        mock_request.side_effect = mock_request_response

        # List sessions
        success, sessions, error = list_agent_sessions()
        assert success is True
        assert len(sessions) == 0

        # Create session
        success, session, error = create_agent_session({"agent_type": "researcher"})
        assert success is True
        assert session["session_id"] == "new-session-123"

        # Send message
        success, response, error = send_agent_message("new-session-123", "Hello!")
        assert success is True
        assert "response" in response

    @patch("api.requests.request")
    @patch("streamlit.session_state", new_callable=dict)
    def test_job_lifecycle_flow(self, mock_session_state, mock_request):
        """Test job creation, monitoring, and cancellation."""
        from api import list_jobs, create_job, get_job, cancel_job
        from state import UIState, Token

        # Setup authenticated state
        token = Token(
            access_token="user-token",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="user@test.com",
            scopes=["user:me"],
        )

        state = UIState(active_identity="user")
        state.tokens.user = token
        mock_session_state["ui_state"] = state

        # Mock job creation
        mock_post_response = Mock()
        mock_post_response.status_code = 201
        mock_post_response.headers = {"content-type": "application/json"}
        mock_post_response.json.return_value = {"id": "job-123", "type": "demo", "status": "queued"}

        # Mock GET response for job retrieval
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.headers = {"content-type": "application/json"}
        mock_get_response.json.return_value = {"id": "job-123", "type": "demo", "status": "running"}

        # Mock DELETE response for job cancellation
        mock_delete_response = Mock()
        mock_delete_response.status_code = 204
        mock_delete_response.headers = {}

        # Set side_effect to return different responses based on method
        def mock_request_response(method, url, **kwargs):
            if method.upper() == "POST":
                return mock_post_response
            elif method.upper() == "GET":
                return mock_get_response
            else:  # DELETE
                return mock_delete_response

        mock_request.side_effect = mock_request_response

        success, job, error = create_job({"type": "demo", "params": {"sleep": 1}})
        assert success is True
        assert job["id"] == "job-123"

        success, job, error = get_job("job-123")
        assert success is True
        assert job["status"] == "running"

        success, data, error = cancel_job("job-123")
        assert success is True


class TestErrorHandling:
    """Test error handling across UI."""

    @patch("streamlit.session_state", new_callable=dict)
    def test_error_tracking(self, mock_session_state):
        """Test error tracking in state."""
        from state import UIState, add_error, clear_errors

        state = UIState()
        mock_session_state = {"ui_state": state}

        with patch("streamlit.session_state", mock_session_state):
            # Add errors
            add_error("Error 1", "Details 1", "trace-1")
            add_error("Error 2", "Details 2", "trace-2")

            assert len(state.errors) == 2

            # Clear errors
            clear_errors()

            assert len(state.errors) == 0

    @patch("api.requests.request")
    def test_api_error_handling(self, mock_request):
        """Test API error responses are handled correctly."""
        from api import get_health_live

        # Mock 500 error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}
        mock_request.return_value = mock_response

        success, data, error = get_health_live()

        assert success is False
        assert data is None
        assert error is not None
        assert "connection error" in error.lower() or "unavailable" in error.lower()


class TestMultiTenancy:
    """Test multi-tenancy features."""

    @patch("api.requests.request")
    @patch("streamlit.session_state", new_callable=dict)
    def test_tenant_selection(self, mock_session_state, mock_request):
        """Test tenant selection and switching."""
        from api import list_tenants
        from state import UIState, TenantInfo, Token

        # Setup
        token = Token(
            access_token="admin-token",
            expires_at=datetime.now() + timedelta(hours=1),
            subject="admin@test.com",
            scopes=["admin:all"],
        )

        state = UIState(active_identity="admin")
        state.tokens.admin = token
        mock_session_state["ui_state"] = state

        # Mock tenants list
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = [
            {"id": "tenant-1", "name": "Tenant 1"},
            {"id": "tenant-2", "name": "Tenant 2"},
        ]
        mock_request.return_value = mock_response

        success, tenants, error = list_tenants()
        assert success is True
        assert len(tenants) == 2

        # Select tenant - TenantInfo stores current selection and available list
        state.tenant.current = "tenant-1"
        state.tenant.available = [{"id": "tenant-1", "name": "Tenant 1"}, {"id": "tenant-2", "name": "Tenant 2"}]

        assert state.tenant.current == "tenant-1"
        assert len(state.tenant.available) == 2
