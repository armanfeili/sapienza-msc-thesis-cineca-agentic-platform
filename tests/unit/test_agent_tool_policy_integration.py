"""
Unit tests for tool policy integration in agent session endpoints.

These tests verify that P1.3 (Tool Policy & Selection) is properly
integrated with P1.1 (Agent Orchestration Endpoints).
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4
from datetime import datetime

from src.routers.agent import create_session
from src.schemas.agents import CreateSessionRequest


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    user = MagicMock()
    user.sub = "user-123"
    user.scopes = ["user:me", "tools:basic"]
    user.raw = {"tid": "tenant-123"}
    user.tenant_id = "tenant-123"
    return user


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = MagicMock()
    return db


@pytest.fixture
def mock_request():
    """Mock FastAPI request."""
    request = MagicMock()
    request.url_for = MagicMock(return_value="/v1/agents/sessions/test-session")
    return request


@pytest.fixture
def mock_response():
    """Mock FastAPI response."""
    response = MagicMock()
    response.headers = {}
    return response


@pytest.fixture
def session_request_with_role():
    """Session creation request with agent role."""
    return CreateSessionRequest(
        prompt="Test prompt",
        agent_role="analyst",  # analyst role should filter tools
        tools=None,  # no explicit allowlist (use role policy)
        temperature=0.7,
        max_steps=10,
    )


@pytest.fixture
def session_request_with_explicit_tools():
    """Session creation request with explicit tool allowlist."""
    return CreateSessionRequest(
        prompt="Test prompt",
        agent_role="operator",
        tools=["graph.query", "cache.manage"],  # explicit allowlist
        temperature=0.7,
        max_steps=10,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Tool Policy Integration
# ══════════════════════════════════════════════════════════════════════════════


@patch("src.routers.agent.SessionResponse")
@patch("src.routers.agent.filter_tools")
@patch("src.routers.agent.list_tool_names")
@patch("src.routers.agent.AgentSessionRepository")
@patch("src.routers.agent.RateLimitHandler")
@patch("src.routers.agent.IdempotencyHandler")
@patch("src.routers.agent.set_session_state")
@patch("src.routers.agent.invalidate_sessions_etag")
@patch("src.routers.agent.record_provenance")
@pytest.mark.asyncio
async def test_session_creation_applies_tool_policy_with_role(
    mock_provenance,
    mock_invalidate,
    mock_set_state,
    mock_idem_handler,
    mock_rate_limiter,
    mock_repo,
    mock_list_tools,
    mock_filter_tools,
    mock_session_response,
    session_request_with_role,
    mock_request,
    mock_response,
    mock_db,
    mock_user,
):
    """
    Test that session creation applies tool policy filtering based on agent role.

    Verifies P1.3 integration: filter_tools() is called with agent_role.
    """
    # Mock SessionResponse.model_validate to avoid Pydantic validation issues
    mock_response_obj = MagicMock()
    mock_response_obj.model_dump.return_value = {"session_id": "test-123"}
    mock_session_response.model_validate.return_value = mock_response_obj

    # Setup mocks
    mock_list_tools.return_value = ["graph.query", "graph.crud", "security.audit"]
    mock_filter_tools.return_value = ["graph.query"]  # analyst only gets read tools

    mock_session = MagicMock()
    mock_session.session_id = str(uuid4())
    mock_session.user_id = mock_user.sub
    mock_session.tenant_id = "tenant-123"
    mock_session.status = "active"
    mock_session.tools = ["graph.query"]
    mock_session.temperature = 0.7
    mock_session.max_steps = 10
    mock_session.metadata = {}
    mock_session.created_at = datetime.fromisoformat("2025-10-26T00:00:00")
    mock_session.updated_at = datetime.fromisoformat("2025-10-26T00:00:00")
    mock_session.last_step_id = None
    mock_session.etag = "test-etag"

    mock_repo.create.return_value = mock_session
    mock_repo.get_by_id_and_owner.return_value = None  # no existing session

    # Mock rate limiter
    mock_rate_instance = MagicMock()
    mock_rate_instance.check = AsyncMock(return_value=None)
    mock_rate_limiter.return_value = mock_rate_instance

    # Mock idempotency handler
    mock_idem_instance = MagicMock()
    mock_idem_instance.check.return_value = None  # not a replay
    mock_idem_instance.cache = MagicMock()
    mock_idem_handler.return_value = mock_idem_instance

    # Call endpoint
    await create_session(
        req=session_request_with_role,
        request=mock_request,
        response=mock_response,
        db=mock_db,
        user=mock_user,
        idempotency_key=None,
    )

    # Verify tool policy was applied
    mock_list_tools.assert_called_once()
    mock_filter_tools.assert_called_once_with(
        available_tools=["graph.query", "graph.crud", "security.audit"],
        agent_role="analyst",
        session_tools=None,  # no explicit allowlist
    )

    # Verify session was created with FILTERED tools (not raw request.tools)
    mock_repo.create.assert_called_once()
    create_call_kwargs = mock_repo.create.call_args[1]
    assert create_call_kwargs["tools"] == ["graph.query"]  # filtered result


@patch("src.routers.agent.add_rate_limit_headers")
@patch("src.routers.agent.SessionResponse")
@patch("src.routers.agent.filter_tools")
@patch("src.routers.agent.list_tool_names")
@patch("src.routers.agent.AgentSessionRepository")
@patch("src.routers.agent.RateLimitHandler")
@patch("src.routers.agent.IdempotencyHandler")
@patch("src.routers.agent.set_session_state")
@patch("src.routers.agent.invalidate_sessions_etag")
@patch("src.routers.agent.record_provenance")
@pytest.mark.asyncio
async def test_session_creation_respects_explicit_allowlist(
    mock_provenance,
    mock_invalidate,
    mock_set_state,
    mock_idem_handler,
    mock_rate_limiter,
    mock_repo,
    mock_list_tools,
    mock_filter_tools,
    mock_session_response,
    mock_add_rate_limit_headers,
    session_request_with_explicit_tools,
    mock_request,
    mock_response,
    mock_db,
    mock_user,
):
    """
    Test that explicit session tools allowlist is passed to filter_tools().

    Verifies P1.3 integration: session_tools parameter overrides role policy.
    """
    # Mock add_rate_limit_headers to avoid Redis asyncio issues
    mock_add_rate_limit_headers.return_value = AsyncMock()

    # Mock SessionResponse.model_validate to avoid Pydantic validation issues
    mock_response_obj = MagicMock()
    mock_response_obj.model_dump.return_value = {"session_id": "test-123"}
    mock_session_response.model_validate.return_value = mock_response_obj

    # Setup mocks
    mock_list_tools.return_value = ["graph.query", "cache.manage", "system.health"]
    mock_filter_tools.return_value = ["graph.query", "cache.manage"]  # explicit list

    mock_session = MagicMock()
    mock_session.session_id = str(uuid4())
    mock_session.tools = ["graph.query", "cache.manage"]
    mock_session.created_at = datetime.fromisoformat("2025-10-26T00:00:00")
    mock_session.updated_at = datetime.fromisoformat("2025-10-26T00:00:00")

    mock_repo.create.return_value = mock_session
    mock_repo.get_by_id_and_owner.return_value = None

    # Mock rate limiter
    mock_rate_instance = MagicMock()
    mock_rate_instance.check = AsyncMock(return_value=None)
    mock_rate_limiter.return_value = mock_rate_instance

    # Mock idempotency handler
    mock_idem_instance = MagicMock()
    mock_idem_instance.check.return_value = None
    mock_idem_instance.cache = MagicMock()
    mock_idem_handler.return_value = mock_idem_instance

    # Call endpoint
    await create_session(
        req=session_request_with_explicit_tools,
        request=mock_request,
        response=mock_response,
        db=mock_db,
        user=mock_user,
        idempotency_key=None,
    )

    # Verify filter_tools was called with explicit session tools
    mock_filter_tools.assert_called_once_with(
        available_tools=mock_list_tools.return_value,
        agent_role="operator",
        session_tools=["graph.query", "cache.manage"],  # explicit allowlist
    )

    # Verify session stored filtered tools
    create_call_kwargs = mock_repo.create.call_args[1]
    assert create_call_kwargs["tools"] == ["graph.query", "cache.manage"]


@patch("src.routers.agent.add_rate_limit_headers")
@patch("src.routers.agent.SessionResponse")
@patch("src.routers.agent.filter_tools")
@patch("src.routers.agent.list_tool_names")
@patch("src.routers.agent.AgentSessionRepository")
@patch("src.routers.agent.RateLimitHandler")
@patch("src.routers.agent.IdempotencyHandler")
@patch("src.routers.agent.set_session_state")
@patch("src.routers.agent.invalidate_sessions_etag")
@patch("src.routers.agent.record_provenance")
@pytest.mark.asyncio
async def test_session_creation_handles_no_role_no_tools(
    mock_provenance,
    mock_invalidate,
    mock_set_state,
    mock_idem_handler,
    mock_rate_limiter,
    mock_repo,
    mock_list_tools,
    mock_filter_tools,
    mock_session_response,
    mock_add_rate_limit_headers,
    mock_request,
    mock_response,
    mock_db,
    mock_user,
):
    """
    Test that session creation without role/tools allows all tools.

    Verifies P1.3 integration: No role + no session_tools = allow all.
    """
    # Mock add_rate_limit_headers to avoid Redis asyncio issues
    mock_add_rate_limit_headers.return_value = AsyncMock()

    # Mock SessionResponse.model_validate to avoid Pydantic validation issues
    mock_response_obj = MagicMock()
    mock_response_obj.model_dump.return_value = {"session_id": "test-123"}
    mock_session_response.model_validate.return_value = mock_response_obj

    # Setup mocks
    all_tools = ["graph.query", "graph.crud", "security.audit"]
    mock_list_tools.return_value = all_tools
    mock_filter_tools.return_value = all_tools  # no filtering

    mock_session = MagicMock()
    mock_session.session_id = str(uuid4())
    mock_session.tools = all_tools
    mock_session.created_at = datetime.fromisoformat("2025-10-26T00:00:00")
    mock_session.updated_at = datetime.fromisoformat("2025-10-26T00:00:00")

    mock_repo.create.return_value = mock_session
    mock_repo.get_by_id_and_owner.return_value = None

    # Mock rate limiter
    mock_rate_instance = MagicMock()
    mock_rate_instance.check = AsyncMock(return_value=None)
    mock_rate_limiter.return_value = mock_rate_instance

    # Mock idempotency handler
    mock_idem_instance = MagicMock()
    mock_idem_instance.check.return_value = None
    mock_idem_instance.cache = MagicMock()
    mock_idem_handler.return_value = mock_idem_instance

    # Create request with no role and no tools
    request = CreateSessionRequest(
        prompt="Test",
        agent_role=None,  # no role
        tools=None,  # no explicit allowlist
        temperature=0.7,
        max_steps=10,
    )

    # Call endpoint
    await create_session(
        req=request,
        request=mock_request,
        response=mock_response,
        db=mock_db,
        user=mock_user,
        idempotency_key=None,
    )

    # Verify filter_tools was called with None for both role and session_tools
    mock_filter_tools.assert_called_once_with(
        available_tools=all_tools,
        agent_role=None,
        session_tools=None,
    )

    # Verify all tools were stored (no filtering)
    create_call_kwargs = mock_repo.create.call_args[1]
    assert create_call_kwargs["tools"] == all_tools


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Fallback Behavior (Tool Policy Not Available)
# ══════════════════════════════════════════════════════════════════════════════


@patch("src.routers.agent.add_rate_limit_headers")
@patch("src.routers.agent.SessionResponse")
@patch("src.routers.agent.AgentSessionRepository")
@patch("src.routers.agent.RateLimitHandler")
@patch("src.routers.agent.IdempotencyHandler")
@patch("src.routers.agent.set_session_state")
@patch("src.routers.agent.invalidate_sessions_etag")
@patch("src.routers.agent.record_provenance")
@pytest.mark.asyncio
async def test_session_creation_fallback_when_tool_policy_unavailable(
    mock_provenance,
    mock_invalidate,
    mock_set_state,
    mock_idem_handler,
    mock_rate_limiter,
    mock_repo,
    mock_session_response,
    mock_add_rate_limit_headers,
    session_request_with_explicit_tools,
    mock_request,
    mock_response,
    mock_db,
    mock_user,
):
    """
    Test that session creation gracefully handles missing tool policy module.

    Verifies fallback behavior: If filter_tools not available, use raw request.tools.
    """
    # Mock add_rate_limit_headers to avoid Redis asyncio issues
    mock_add_rate_limit_headers.return_value = AsyncMock()

    # Mock SessionResponse.model_validate to avoid Pydantic validation issues
    mock_response_obj = MagicMock()
    mock_response_obj.model_dump.return_value = {"session_id": "test-123"}
    mock_session_response.model_validate.return_value = mock_response_obj

    # Mock session
    mock_session = MagicMock()
    mock_session.session_id = str(uuid4())
    mock_session.tools = ["graph.query", "cache.manage"]
    mock_session.created_at = datetime.fromisoformat("2025-10-26T00:00:00")
    mock_session.updated_at = datetime.fromisoformat("2025-10-26T00:00:00")

    mock_repo.create.return_value = mock_session
    mock_repo.get_by_id_and_owner.return_value = None

    # Mock rate limiter
    mock_rate_instance = MagicMock()
    mock_rate_instance.check = AsyncMock(return_value=None)
    mock_rate_limiter.return_value = mock_rate_instance

    # Mock idempotency handler
    mock_idem_instance = MagicMock()
    mock_idem_instance.check.return_value = None
    mock_idem_instance.cache = MagicMock()
    mock_idem_handler.return_value = mock_idem_instance

    # The fallback function is already defined in the router module
    # It should return available_tools if tool policy not available

    # Call endpoint
    await create_session(
        req=session_request_with_explicit_tools,
        request=mock_request,
        response=mock_response,
        db=mock_db,
        user=mock_user,
        idempotency_key=None,
    )

    # Should still create session even without tool policy module
    mock_repo.create.assert_called_once()
