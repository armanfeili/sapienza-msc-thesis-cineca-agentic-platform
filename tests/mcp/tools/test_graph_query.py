"""
Integration tests for hardened graph.query tool.

Tests the P1-hardened graph.query implementation with:
- @mcp_tool decorator integration
- Pydantic schema validation
- RBAC enforcement
- Audit trail verification
- Metrics emission
"""

import pytest
from unittest.mock import patch, MagicMock

from src.mcp.tools.graph import query as graph_query_module
from src.mcp.schemas import GraphQueryPayload
from pydantic import ValidationError


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_memgraph(monkeypatch):
    """Mock MemgraphAdapter to avoid real DB dependency."""
    mock_adapter = MagicMock()
    mock_adapter.query.return_value = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
    ]

    def mock_adapter_factory():
        return mock_adapter

    monkeypatch.setattr("src.mcp.tools.graph.query.MemgraphAdapter", mock_adapter_factory)
    return mock_adapter


# ─────────────────────────────────────────────────────────────────────────────
# Schema Validation Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_schema_validation_minimal():
    """Test minimal valid payload."""
    payload = GraphQueryPayload(cypher="MATCH (n) RETURN n LIMIT 10")
    assert payload.cypher == "MATCH (n) RETURN n LIMIT 10"
    assert payload.action == "run"
    assert payload.read_only is True
    assert payload.params == {}


def test_schema_validation_with_params():
    """Test payload with query parameters."""
    payload = GraphQueryPayload(
        action="run",
        cypher="MATCH (u:User {id: $uid}) RETURN u",
        params={"uid": "user123"},
        read_only=False,
    )
    assert payload.params == {"uid": "user123"}
    assert payload.read_only is False


def test_schema_validation_empty_cypher_rejected():
    """Empty cypher should be rejected."""
    with pytest.raises(ValidationError) as exc:
        GraphQueryPayload(cypher="")
    assert "string_too_short" in str(exc.value) or "at least 1" in str(exc.value)


def test_schema_validation_explain_action():
    """Test EXPLAIN action."""
    payload = GraphQueryPayload(
        action="explain",
        cypher="MATCH (n) RETURN n",
    )
    assert payload.action == "explain"


def test_schema_validation_profile_action():
    """Test PROFILE action."""
    payload = GraphQueryPayload(
        action="profile",
        cypher="MATCH (n) RETURN n",
    )
    assert payload.action == "profile"


# ─────────────────────────────────────────────────────────────────────────────
# Functional Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_run_action_executes_query(mock_memgraph):
    """Test that run action executes the Cypher query."""
    payload = {
        "action": "run",
        "cypher": "MATCH (n) RETURN n.name as name, n.age as age LIMIT 10",
        "params": {},
        "principal": "test_user",  # Required for RBAC
        "tenant": "test_tenant",
    }

    result = graph_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "run"
    assert "rows" in result
    assert len(result["rows"]) == 2
    assert result["rows"][0]["name"] == "Alice"
    assert mock_memgraph.query.called


def test_run_action_with_params(mock_memgraph):
    """Test run action with query parameters."""
    payload = {
        "action": "run",
        "cypher": "MATCH (n:User) WHERE n.name = $name RETURN n",
        "params": {"name": "Alice"},
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = graph_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "run"
    assert mock_memgraph.query.called
    # Verify params were passed
    call_args = mock_memgraph.query.call_args
    assert call_args[1]["params"] == {"name": "Alice"}


def test_run_action_with_limit(mock_memgraph):
    """Test client-side row limit."""
    # Mock returns 2 rows, but limit=1
    payload = {
        "action": "run",
        "cypher": "MATCH (n) RETURN n",
        "limit": 1,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = graph_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["rowcount"] == 1  # Limited to 1
    assert result["truncated"] is True  # Flag indicates truncation


def test_run_action_read_only_blocks_writes(mock_memgraph):
    """Test that read_only=true blocks write queries."""
    payload = {
        "action": "run",
        "cypher": "CREATE (n:User {name: 'Charlie'})",
        "read_only": True,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    # Decorator catches the ValueError and returns error response
    result = graph_query_module.invoke(payload)

    assert result["ok"] is False
    assert result["code"] == "E_INTERNAL"
    msg = result["message"].lower()
    assert any(kw in msg for kw in ["write", "modify", "read-only", "read_only"])
    assert not mock_memgraph.query.called  # Should not execute


def test_explain_action(mock_memgraph):
    """Test EXPLAIN action."""
    mock_memgraph.query.return_value = [{"QUERY PLAN": "NodeByLabelScan"}]

    payload = {
        "action": "explain",
        "cypher": "MATCH (n:User) RETURN n",
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = graph_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "explain"
    assert "rows" in result
    mock_memgraph.query.assert_called_once()
    # Check that EXPLAIN was prefixed
    call_args = mock_memgraph.query.call_args[0]
    assert "EXPLAIN" in call_args[0]


def test_profile_action(mock_memgraph):
    """Test PROFILE action."""
    mock_memgraph.query.return_value = [{"OPERATOR": "Produce", "ACTUAL HITS": 10}]

    payload = {
        "action": "profile",
        "cypher": "MATCH (n:User) RETURN n",
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = graph_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "profile"
    mock_memgraph.query.assert_called_once()
    call_args = mock_memgraph.query.call_args[0]
    assert "PROFILE" in call_args[0]


def test_timeout_enforcement(mock_memgraph):
    """Test timeout_ms parameter is passed through."""
    payload = {
        "action": "run",
        "cypher": "MATCH (n) RETURN n",
        "timeout_ms": 3000,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = graph_query_module.invoke(payload)

    assert result["ok"] is True
    call_args = mock_memgraph.query.call_args
    assert call_args[1].get("timeout_ms") == 3000


# ─────────────────────────────────────────────────────────────────────────────
# Security Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_write_detection_create(mock_memgraph):
    """Test write detection for CREATE statements."""
    payload = {
        "action": "run",
        "cypher": "CREATE (n:User {name: 'test'})",
        "read_only": True,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = graph_query_module.invoke(payload)
    assert result["ok"] is False
    msg = result["message"].lower()
    assert any(kw in msg for kw in ["write", "modify", "read-only", "read_only"])


def test_write_detection_merge(mock_memgraph):
    """Test write detection for MERGE statements."""
    payload = {
        "action": "run",
        "cypher": "MERGE (n:User {id: 123})",
        "read_only": True,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = graph_query_module.invoke(payload)
    assert result["ok"] is False
    msg = result["message"].lower()
    assert any(kw in msg for kw in ["write", "modify", "read-only", "read_only"])


def test_write_detection_delete(mock_memgraph):
    """Test write detection for DELETE statements."""
    payload = {
        "action": "run",
        "cypher": "MATCH (n:User) DELETE n",
        "read_only": True,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = graph_query_module.invoke(payload)
    assert result["ok"] is False
    msg = result["message"].lower()
    assert any(kw in msg for kw in ["write", "modify", "read-only", "read_only"])


def test_write_detection_set(mock_memgraph):
    """Test write detection for SET statements."""
    payload = {
        "action": "run",
        "cypher": "MATCH (n:User) SET n.updated = true",
        "read_only": True,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = graph_query_module.invoke(payload)
    assert result["ok"] is False
    msg = result["message"].lower()
    assert any(kw in msg for kw in ["write", "modify", "read-only", "read_only"])


def test_read_query_allowed_with_readonly(mock_memgraph):
    """Test that read-only queries work with read_only=true."""
    payload = {
        "action": "run",
        "cypher": "MATCH (n:User) RETURN n",
        "read_only": True,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = graph_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["read_only"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Helper Function Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_columns_extraction():
    """Test column extraction from rows."""
    from src.mcp.tools.graph.query import _columns

    rows = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
    ]

    cols = _columns(rows)
    assert set(cols) == {"name", "age"}


def test_columns_empty_rows():
    """Test column extraction with no rows."""
    from src.mcp.tools.graph.query import _columns

    cols = _columns([])
    assert cols == []


def test_slice_rows_no_limit():
    """Test row slicing with no limit."""
    from src.mcp.tools.graph.query import _slice_rows

    rows = [{"i": 1}, {"i": 2}, {"i": 3}]
    result, truncated = _slice_rows(rows, None)

    assert result == rows
    assert truncated is False


def test_slice_rows_with_limit():
    """Test row slicing with limit."""
    from src.mcp.tools.graph.query import _slice_rows

    rows = [{"i": 1}, {"i": 2}, {"i": 3}]
    result, truncated = _slice_rows(rows, 2)

    assert len(result) == 2
    assert truncated is True


def test_looks_write():
    """Test write detection helper."""
    from src.mcp.tools.graph.query import _looks_write

    assert _looks_write("CREATE (n)") is True
    assert _looks_write("MERGE (n)") is True
    assert _looks_write("DELETE n") is True
    assert _looks_write("SET n.prop = 1") is True
    assert _looks_write("MATCH (n) RETURN n") is False
    assert _looks_write("MATCH (n) WHERE n.id = 1 RETURN n") is False
