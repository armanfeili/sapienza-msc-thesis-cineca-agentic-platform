"""
Pytest configuration and fixtures for UI tests.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import sys
from pathlib import Path
import os

# Add UI directory to path FIRST
ui_path = Path(__file__).parent.parent.parent / "ui"
sys.path.insert(0, str(ui_path))


# Create a mock session_state that supports both dict and attribute access
class MockSessionState(dict):
    """Mock streamlit session_state that supports attribute-style access."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value

    def __setitem__(self, key, value):
        super().__setitem__(key, value)


# Mock streamlit module before any UI imports
mock_st = MagicMock()
mock_st.session_state = MockSessionState()
mock_st.secrets = MagicMock()


# Mock st.secrets.get to support default parameter
def mock_secrets_get(key, default=None):
    """Mock secrets.get that supports default parameter."""
    return default


mock_st.secrets.get = mock_secrets_get


# Mock st.columns to return list of mock columns
def mock_columns(spec):
    """Mock st.columns that returns a list of mocks."""
    if isinstance(spec, int):
        return [MagicMock() for _ in range(spec)]
    elif isinstance(spec, list):
        return [MagicMock() for _ in range(len(spec))]
    return [MagicMock()]


mock_st.columns = mock_columns

# Mock other streamlit functions
mock_st.container = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
mock_st.expander = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))
mock_st.spinner = MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))

sys.modules["streamlit"] = mock_st


@pytest.fixture(autouse=True)
def setup_ui_state():
    """Automatically set up UI state for all tests."""
    from state import UIState

    state = UIState()
    mock_st.session_state.ui_state = state
    yield state
    # Clean up after test
    if hasattr(mock_st.session_state, "ui_state"):
        del mock_st.session_state["ui_state"]


@pytest.fixture
def mock_streamlit():
    """Mock Streamlit components."""
    return mock_st


@pytest.fixture
def mock_requests():
    """Mock requests library for API tests."""
    with patch("requests.request") as mock_request:
        # Create mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}
        mock_response.text = "ok"
        mock_response.headers = {"content-type": "application/json"}

        mock_request.return_value = mock_response

        yield {"request": mock_request, "response": mock_response}


@pytest.fixture
def sample_token():
    """Sample JWT token for testing."""
    return {
        "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJzY29wZSI6InVzZXI6bWUgdG9vbHM6aW52b2tlOmFsbCIsImV4cCI6OTk5OTk5OTk5OX0.test",
        "expires_in": 3600,
        "token_type": "Bearer",
    }


@pytest.fixture
def sample_health_response():
    """Sample health check response."""
    return {
        "service": "cineca-agentic-platform",
        "version": "0.1.0",
        "status": "healthy",
        "time": "2025-10-28T12:00:00Z",
        "checks": {
            "app": {"ok": True, "status": "ok", "latency_ms": 0},
            "postgres": {"ok": True, "status": "ok", "latency_ms": 5},
            "redis": {"ok": True, "status": "ok", "latency_ms": 3},
            "memgraph": {"ok": True, "status": "ok", "latency_ms": 10},
        },
    }


@pytest.fixture
def sample_tools():
    """Sample tools list."""
    return [
        {
            "id": "system.health",
            "name": "System Health",
            "description": "Check system health",
            "category": "system",
            "safe": True,
        },
        {
            "id": "graph.search",
            "name": "Graph Search",
            "description": "Search knowledge graph",
            "category": "graph",
            "safe": True,
        },
    ]


@pytest.fixture
def sample_agent_session():
    """Sample agent session."""
    return {
        "session_id": "test-session-123",
        "agent_type": "researcher",
        "status": "active",
        "created_at": "2025-10-28T12:00:00Z",
        "messages": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there!"}],
    }


@pytest.fixture
def sample_job():
    """Sample job data."""
    return {
        "id": "job-123",
        "type": "demo",
        "status": "completed",
        "created_at": "2025-10-28T12:00:00Z",
        "updated_at": "2025-10-28T12:01:00Z",
        "result": {"output": "success"},
    }


@pytest.fixture
def sample_tenants():
    """Sample tenants list."""
    return [
        {
            "id": "tenant-1",
            "name": "Default Tenant",
            "description": "Default tenant for testing",
            "created_at": "2025-10-28T12:00:00Z",
        },
        {"id": "tenant-2", "name": "Test Tenant", "description": "Test tenant", "created_at": "2025-10-28T12:00:00Z"},
    ]


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing - applied to ALL tests automatically."""
    env_vars = {
        "API_BASE_URL": "http://app:8000",
        "AUTH0_DOMAIN": "test.auth0.com",
        "AUTH0_CLIENT_ID": "test-client-id",
        "AUTH0_CLIENT_SECRET": "test-client-secret",
        "AUTH0_AUDIENCE": "test-audience",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    return env_vars
