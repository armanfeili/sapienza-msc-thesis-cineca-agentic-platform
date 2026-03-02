"""
Tests for src.mcp.tool_policy module.

These tests validate the tool selection, ranking, and allowlist enforcement logic.
They ensure deterministic behavior for agent tool selection based on roles and policies.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.mcp.tool_policy import (
    filter_tools,
    rank_tools,
    get_fallback_tool,
    validate_tool_access,
)


# ══════════════════════════════════════════════════════════════════════════════
# Mock Fixtures
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_policies():
    """Mock policy configuration matching src/mcp/policies.yaml structure."""
    return {
        "version": 1,
        "tool_policies": {
            "roles": {
                "analyst": {
                    "allow": [
                        "graph.query",
                        "graph.search",
                        "graph.analytics",
                        "output.*",
                    ],
                    "deny": ["graph.crud", "security.*"],
                },
                "operator": {
                    "allow": ["graph.*", "cache.*", "system.*"],
                    "deny": ["security.audit"],
                },
                "admin": {"allow": ["*"], "deny": []},
                "user": {
                    "allow": ["graph.query", "output.*"],
                    "deny": ["graph.crud", "security.*"],
                },
            },
            "rankings": {
                "query|search|find": [
                    ["graph.query", 1.0],
                    ["graph.search", 0.9],
                ],
                "create|insert|add": [["graph.crud", 1.0], ["graph.bulk", 0.8]],
                "analyze|stats": [["graph.analytics", 1.0]],
            },
            "fallbacks": {
                "graph.crud": "graph.query",
                "graph.bulk": "graph.crud",
                "security.audit": None,
            },
        },
    }


@pytest.fixture
def mock_manifest():
    """Mock MCP manifest with available tools."""
    return {
        "tools": [
            {"name": "graph.query"},
            {"name": "graph.search"},
            {"name": "graph.crud"},
            {"name": "graph.bulk"},
            {"name": "graph.analytics"},
            {"name": "security.audit"},
            {"name": "security.permissions"},
            {"name": "cache.manage"},
            {"name": "system.health"},
            {"name": "output.format"},
            {"name": "output.summarize"},
        ]
    }


@pytest.fixture
def available_tools():
    """List of all available tool names."""
    return [
        "graph.query",
        "graph.search",
        "graph.crud",
        "graph.bulk",
        "graph.analytics",
        "security.audit",
        "security.permissions",
        "cache.manage",
        "system.health",
        "output.format",
        "output.summarize",
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Tests: filter_tools()
# ══════════════════════════════════════════════════════════════════════════════


@patch("src.mcp.tool_policy._get_policies")
def test_filter_tools_analyst_role(mock_get_policies, mock_policies, available_tools):
    """Test that analyst role gets only allowed tools (read-only)."""
    mock_get_policies.return_value = mock_policies

    result = filter_tools(available_tools=available_tools, agent_role="analyst", session_tools=None)

    # Analyst should get: graph.query, graph.search, graph.analytics, output.*
    # Analyst should NOT get: graph.crud, security.*
    assert "graph.query" in result
    assert "graph.search" in result
    assert "graph.analytics" in result
    assert "output.format" in result
    assert "output.summarize" in result

    assert "graph.crud" not in result  # denied
    assert "graph.bulk" not in result  # not allowed
    assert "security.audit" not in result  # denied
    assert "security.permissions" not in result  # denied


@patch("src.mcp.tool_policy._get_policies")
def test_filter_tools_operator_role(mock_get_policies, mock_policies, available_tools):
    """Test that operator role gets graph.* and system.* tools."""
    mock_get_policies.return_value = mock_policies

    result = filter_tools(available_tools=available_tools, agent_role="operator", session_tools=None)

    # Operator should get: graph.*, cache.*, system.*
    assert "graph.query" in result
    assert "graph.crud" in result
    assert "graph.bulk" in result
    assert "cache.manage" in result
    assert "system.health" in result

    # Operator should NOT get: security.audit (explicitly denied)
    assert "security.audit" not in result


@patch("src.mcp.tool_policy._get_policies")
def test_filter_tools_admin_role(mock_get_policies, mock_policies, available_tools):
    """Test that admin role gets all tools (wildcard)."""
    mock_get_policies.return_value = mock_policies

    result = filter_tools(available_tools=available_tools, agent_role="admin", session_tools=None)

    # Admin should get everything
    assert len(result) == len(available_tools)
    assert set(result) == set(available_tools)


@patch("src.mcp.tool_policy._get_policies")
def test_filter_tools_session_allowlist_overrides_role(mock_get_policies, mock_policies, available_tools):
    """Test that explicit session allowlist overrides role policy."""
    mock_get_policies.return_value = mock_policies

    # Analyst normally can't use graph.crud, but session allowlist grants it
    result = filter_tools(
        available_tools=available_tools,
        agent_role="analyst",
        session_tools=["graph.crud", "graph.query"],
    )

    # Should only get tools from session allowlist (ignoring role policy)
    assert set(result) == {"graph.crud", "graph.query"}


def test_filter_tools_no_role_no_session_allows_all(available_tools):
    """Test that no role/session constraints allows all tools."""
    result = filter_tools(available_tools=available_tools, agent_role=None, session_tools=None)

    # Should allow all tools
    assert set(result) == set(available_tools)


@patch("src.mcp.tool_policy._get_policies")
def test_filter_tools_deny_overrides_allow(mock_get_policies, available_tools):
    """Test that deny rules override allow rules."""
    # Create policy with conflicting allow/deny
    mock_get_policies.return_value = {
        "tool_policies": {
            "roles": {
                "test_role": {
                    "allow": ["graph.*"],  # allows graph.crud
                    "deny": ["graph.crud"],  # but explicitly deny it
                }
            }
        }
    }

    result = filter_tools(available_tools=available_tools, agent_role="test_role", session_tools=None)

    # graph.crud should be denied despite graph.* allow
    assert "graph.crud" not in result
    assert "graph.query" in result  # other graph.* tools allowed


# ══════════════════════════════════════════════════════════════════════════════
# Tests: rank_tools()
# ══════════════════════════════════════════════════════════════════════════════


@patch("src.mcp.tool_policy._get_policies")
def test_rank_tools_query_task(mock_get_policies, mock_policies):
    """Test tool ranking for query/search task."""
    mock_get_policies.return_value = mock_policies

    tools = ["graph.query", "graph.search", "graph.crud"]
    result = rank_tools(tools=tools, task_description="Find all users in the graph", preferences=None)

    # Should rank query tools higher for "find" keyword
    assert result[0][0] == "graph.query"  # highest weight
    assert result[0][1] == 1.0
    assert result[1][0] == "graph.search"
    assert result[1][1] == 0.9
    assert result[2][0] == "graph.crud"
    assert result[2][1] == 0.5  # default weight


@patch("src.mcp.tool_policy._get_policies")
def test_rank_tools_create_task(mock_get_policies, mock_policies):
    """Test tool ranking for create/insert task."""
    mock_get_policies.return_value = mock_policies

    tools = ["graph.crud", "graph.bulk", "graph.query"]
    result = rank_tools(tools=tools, task_description="Create a new user node", preferences=None)

    # Should rank CRUD tools higher for "create" keyword
    assert result[0][0] == "graph.crud"
    assert result[0][1] == 1.0
    assert result[1][0] == "graph.bulk"
    assert result[1][1] == 0.8


@patch("src.mcp.tool_policy._get_policies")
def test_rank_tools_explicit_preferences_override_policy(mock_get_policies, mock_policies):
    """Test that explicit preferences override policy rankings."""
    mock_get_policies.return_value = mock_policies

    tools = ["graph.query", "graph.crud"]
    result = rank_tools(
        tools=tools,
        task_description="Query the graph",  # would normally rank graph.query higher
        preferences={"graph.crud": 1.0, "graph.query": 0.3},  # but prefer crud
    )

    # Explicit preferences should override task-based ranking
    assert result[0][0] == "graph.crud"
    assert result[0][1] == 1.0
    assert result[1][0] == "graph.query"
    assert result[1][1] == 0.3


def test_rank_tools_no_task_uses_default_weights():
    """Test that tools get default weights when no task/preferences provided."""
    tools = ["graph.query", "graph.crud", "graph.search"]
    result = rank_tools(tools=tools, task_description=None, preferences=None)

    # All should get default weight (0.5)
    assert all(weight == 0.5 for _, weight in result)
    # Order should be consistent (alphabetical since equal weights)
    assert len(result) == 3


def test_rank_tools_empty_list():
    """Test ranking empty tool list."""
    result = rank_tools(tools=[], task_description="anything", preferences=None)
    assert result == []


# ══════════════════════════════════════════════════════════════════════════════
# Tests: get_fallback_tool()
# ══════════════════════════════════════════════════════════════════════════════


@patch("src.mcp.tool_policy._get_policies")
def test_get_fallback_tool_configured_mapping(mock_get_policies, mock_policies):
    """Test explicit fallback mapping from policy."""
    mock_get_policies.return_value = mock_policies

    # graph.crud → graph.query fallback
    result = get_fallback_tool(
        blocked_tool="graph.crud",
        task_description="Create a node",
        allowed_tools=["graph.query", "graph.search"],
    )

    assert result == "graph.query"


@patch("src.mcp.tool_policy._get_policies")
def test_get_fallback_tool_no_fallback_configured(mock_get_policies, mock_policies):
    """Test tool with explicit no fallback (None value)."""
    mock_get_policies.return_value = mock_policies

    # security.audit → None (no fallback)
    result = get_fallback_tool(
        blocked_tool="security.audit",
        task_description="Audit user actions",
        allowed_tools=["graph.query"],
    )

    assert result is None


@patch("src.mcp.tool_policy._get_policies")
def test_get_fallback_tool_configured_but_not_allowed(mock_get_policies, mock_policies):
    """Test fallback configured but not in allowed_tools."""
    mock_get_policies.return_value = mock_policies

    # graph.crud → graph.query, but graph.query not in allowed_tools
    result = get_fallback_tool(
        blocked_tool="graph.crud",
        task_description="Create a node",
        allowed_tools=["cache.manage"],  # doesn't include graph.query
    )

    # Should fall back to ranking allowed tools
    assert result == "cache.manage"


@patch("src.mcp.tool_policy._get_policies")
def test_get_fallback_tool_no_config_uses_ranking(mock_get_policies, mock_policies):
    """Test fallback selection via ranking when no explicit mapping."""
    mock_get_policies.return_value = mock_policies

    # Unknown tool (no fallback mapping) → rank available tools
    result = get_fallback_tool(
        blocked_tool="unknown.tool",
        task_description="Query data",  # should rank graph.query high
        allowed_tools=["graph.query", "cache.manage"],
    )

    # Should pick highest ranked tool for the task
    assert result == "graph.query"


# ══════════════════════════════════════════════════════════════════════════════
# Tests: validate_tool_access()
# ══════════════════════════════════════════════════════════════════════════════


@patch("src.mcp.tool_policy.list_tool_names")
@patch("src.mcp.tool_policy._get_policies")
def test_validate_tool_access_allowed(mock_get_policies, mock_list_tools, mock_policies):
    """Test validation passes for allowed tool."""
    mock_get_policies.return_value = mock_policies
    mock_list_tools.return_value = [
        "graph.query",
        "graph.crud",
        "security.audit",
    ]

    allowed, reason = validate_tool_access(tool_name="graph.query", agent_role="analyst", session_tools=None)

    assert allowed is True
    assert reason is None


@patch("src.mcp.tool_policy.list_tool_names")
@patch("src.mcp.tool_policy._get_policies")
def test_validate_tool_access_denied_by_role(mock_get_policies, mock_list_tools, mock_policies):
    """Test validation fails for tool denied by role."""
    mock_get_policies.return_value = mock_policies
    mock_list_tools.return_value = ["graph.query", "graph.crud"]

    allowed, reason = validate_tool_access(
        tool_name="graph.crud",  # denied for analyst
        agent_role="analyst",
        session_tools=None,
    )

    assert allowed is False
    assert "role policy" in reason.lower()


@patch("src.mcp.tool_policy.list_tool_names")
def test_validate_tool_access_denied_by_session_allowlist(mock_list_tools):
    """Test validation fails for tool not in session allowlist."""
    mock_list_tools.return_value = ["graph.query", "graph.crud"]

    allowed, reason = validate_tool_access(
        tool_name="graph.crud",
        agent_role=None,
        session_tools=["graph.query"],  # only query allowed
    )

    assert allowed is False
    assert "session allowlist" in reason.lower()


@patch("src.mcp.tool_policy.list_tool_names")
def test_validate_tool_access_tool_not_in_manifest(mock_list_tools):
    """Test validation fails for non-existent tool."""
    mock_list_tools.return_value = ["graph.query"]

    allowed, reason = validate_tool_access(tool_name="nonexistent.tool", agent_role=None, session_tools=None)

    assert allowed is False
    assert "not found" in reason.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════════════════════


@patch("src.mcp.tool_policy.list_tool_names")
@patch("src.mcp.tool_policy._get_policies")
def test_end_to_end_analyst_workflow(mock_get_policies, mock_list_tools, mock_policies, available_tools):
    """
    Integration test: Analyst role creating a session with task-based tool selection.

    Scenario:
    1. Analyst role creates session (gets filtered tool allowlist)
    2. Task is "Find all users" (should rank query tools high)
    3. If graph.crud is blocked, fallback to graph.query
    """
    mock_get_policies.return_value = mock_policies
    mock_list_tools.return_value = available_tools

    # Step 1: Filter tools by analyst role
    allowed = filter_tools(available_tools=available_tools, agent_role="analyst", session_tools=None)

    assert "graph.query" in allowed
    assert "graph.search" in allowed
    assert "graph.crud" not in allowed  # write blocked

    # Step 2: Rank allowed tools for query task
    ranked = rank_tools(tools=allowed, task_description="Find all users in the system", preferences=None)

    # graph.query should be highest ranked for "find" keyword
    assert ranked[0][0] == "graph.query"
    assert ranked[0][1] == 1.0

    # Step 3: Try fallback for blocked tool
    fallback = get_fallback_tool(
        blocked_tool="graph.crud",  # analyst can't use this
        task_description="Find all users",
        allowed_tools=allowed,
    )

    # Should fallback to graph.query
    assert fallback == "graph.query"


@patch("src.mcp.tool_policy.list_tool_names")
@patch("src.mcp.tool_policy._get_policies")
def test_end_to_end_session_allowlist_override(mock_get_policies, mock_list_tools, mock_policies, available_tools):
    """
    Integration test: Explicit session allowlist overrides role policy.

    Scenario:
    1. Analyst role normally can't use graph.crud
    2. Session explicitly grants ["graph.crud", "graph.query"]
    3. Validation should pass for graph.crud
    """
    mock_get_policies.return_value = mock_policies
    mock_list_tools.return_value = available_tools

    # Filter with session allowlist (overrides role)
    allowed = filter_tools(
        available_tools=available_tools,
        agent_role="analyst",
        session_tools=["graph.crud", "graph.query"],
    )

    # Should only get session tools (ignoring analyst role restrictions)
    assert set(allowed) == {"graph.crud", "graph.query"}

    # Validate access (should pass)
    is_allowed, reason = validate_tool_access(
        tool_name="graph.crud",
        agent_role="analyst",
        session_tools=["graph.crud", "graph.query"],
    )

    assert is_allowed is True
    assert reason is None


# ══════════════════════════════════════════════════════════════════════════════
# Determinism Tests (P1.3 Requirement)
# ══════════════════════════════════════════════════════════════════════════════


@patch("src.mcp.tool_policy._get_policies")
def test_filter_tools_is_deterministic(mock_get_policies, mock_policies, available_tools):
    """Test that filter_tools returns consistent results (no randomness)."""
    mock_get_policies.return_value = mock_policies

    # Run multiple times, should get identical results
    results = [filter_tools(available_tools, agent_role="analyst", session_tools=None) for _ in range(5)]

    # All results should be identical (list equality)
    for i in range(1, len(results)):
        assert results[i] == results[0]


@patch("src.mcp.tool_policy._get_policies")
def test_rank_tools_is_deterministic(mock_get_policies, mock_policies):
    """Test that rank_tools returns consistent rankings (no randomness)."""
    mock_get_policies.return_value = mock_policies

    tools = ["graph.query", "graph.search", "graph.crud"]

    # Run multiple times with same inputs
    results = [rank_tools(tools, task_description="Find users", preferences=None) for _ in range(5)]

    # All results should be identical
    for i in range(1, len(results)):
        assert results[i] == results[0]


@patch("src.mcp.tool_policy._get_policies")
def test_get_fallback_tool_is_deterministic(mock_get_policies, mock_policies):
    """Test that get_fallback_tool returns consistent fallback (no randomness)."""
    mock_get_policies.return_value = mock_policies

    # Run multiple times
    results = [
        get_fallback_tool(
            blocked_tool="graph.crud",
            task_description="Create node",
            allowed_tools=["graph.query", "graph.search"],
        )
        for _ in range(5)
    ]

    # All results should be identical
    assert len(set(results)) == 1  # only one unique result
    assert results[0] == "graph.query"
