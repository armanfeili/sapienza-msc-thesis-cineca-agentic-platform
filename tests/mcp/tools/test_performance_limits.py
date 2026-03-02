"""
Performance limit tests for P1 tools.

Tests timeout enforcement and row cap limits to ensure queries
don't consume excessive resources.
"""
import pytest
from unittest.mock import Mock, patch
from src.mcp.tools.graph import query as query_module
from src.mcp.tools.graph import secure_query as secure_query_module


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_memgraph():
    """Mock Memgraph adapter."""
    with patch.object(query_module, "MemgraphAdapter") as mock:
        db_instance = Mock()
        mock.return_value = db_instance
        yield db_instance


@pytest.fixture
def mock_memgraph_secure():
    """Mock Memgraph adapter for secure_query."""
    with patch.object(secure_query_module, "MemgraphAdapter") as mock:
        db_instance = Mock()
        mock.return_value = db_instance
        yield db_instance


# ============================================================================
# Row Cap Tests
# ============================================================================


def test_graph_query_respects_max_rows_default(mock_memgraph):
    """
    Test that graph.query returns all rows when no limit is specified.

    When limit is not specified, all rows from the database are returned.
    """
    # Mock query returning 5000 rows
    large_result = [{"x": i} for i in range(5000)]
    mock_memgraph.query.return_value = large_result

    payload = {
        "action": "run",
        "cypher": "UNWIND range(1, 5000) AS x RETURN x",
        "principal": "test-user",
        "tenant": "test-tenant",
        "read_only": True,
        # No limit specified - returns all rows
    }

    result = query_module.invoke(payload)

    assert result["ok"] is True
    assert len(result["rows"]) == 5000  # All rows returned
    assert result["truncated"] is False  # Not truncated


def test_graph_query_respects_custom_max_rows(mock_memgraph):
    """
    Test that graph.query respects custom max_rows limit.
    """
    # Mock query returning 5000 rows
    large_result = [{"x": i} for i in range(5000)]
    mock_memgraph.query.return_value = large_result

    payload = {
        "action": "run",
        "cypher": "UNWIND range(1, 5000) AS x RETURN x",
        "principal": "test-user",
        "tenant": "test-tenant",
        "read_only": True,
        "limit": 100,  # Custom limit
    }

    result = query_module.invoke(payload)

    assert result["ok"] is True
    assert len(result["rows"]) == 100  # Capped at custom limit
    assert result["truncated"] is True


def test_graph_query_no_truncation_when_under_limit(mock_memgraph):
    """
    Test that graph.query doesn't truncate when result is under limit.
    """
    # Mock query returning 50 rows
    small_result = [{"x": i} for i in range(50)]
    mock_memgraph.query.return_value = small_result

    payload = {
        "action": "run",
        "cypher": "UNWIND range(1, 50) AS x RETURN x",
        "principal": "test-user",
        "tenant": "test-tenant",
        "read_only": True,
        "limit": 1000,
    }

    result = query_module.invoke(payload)

    assert result["ok"] is True
    assert len(result["rows"]) == 50  # All rows returned
    assert result["truncated"] is False


def test_secure_query_execute_respects_max_rows(mock_memgraph_secure):
    """
    Test that graph.secure_query.execute respects max_rows limit.
    """
    # Mock permission check
    with patch.object(secure_query_module, "_check_permissions", return_value=True):
        # Mock query returning 2000 rows
        large_result = [{"x": i} for i in range(2000)]
        mock_memgraph_secure.query.return_value = large_result

        payload = {
            "action": "execute",
            "cypher": "MATCH (n) RETURN n",
            "principal": "test-user",
            "tenant": "test-tenant",
            "max_rows": 500,  # Custom limit
        }

        result = secure_query_module.invoke(payload)

        assert result["ok"] is True
        assert len(result["rows"]) == 500  # Capped at custom limit
        assert result["truncated"] is True


# ============================================================================
# Timeout Tests
# ============================================================================


def test_graph_query_passes_timeout_to_adapter(mock_memgraph):
    """
    Test that graph.query passes timeout_ms to MemgraphAdapter.
    """
    mock_memgraph.query.return_value = [{"n": {"name": "test"}}]

    payload = {
        "action": "run",
        "cypher": "MATCH (n) RETURN n LIMIT 1",
        "principal": "test-user",
        "tenant": "test-tenant",
        "read_only": True,
        "timeout_ms": 3000,  # Custom timeout
    }

    result = query_module.invoke(payload)

    assert result["ok"] is True

    # Verify timeout was passed to query method
    mock_memgraph.query.assert_called_once()
    call_kwargs = mock_memgraph.query.call_args.kwargs
    assert call_kwargs["timeout_ms"] == 3000


def test_graph_query_uses_default_timeout_when_not_specified(mock_memgraph):
    """
    Test that graph.query uses default timeout when not specified.
    The schema sets default=5000, so timeout is passed to adapter.
    """
    mock_memgraph.query.return_value = [{"n": {"name": "test"}}]

    payload = {
        "action": "run",
        "cypher": "MATCH (n) RETURN n LIMIT 1",
        "principal": "test-user",
        "tenant": "test-tenant",
        "read_only": True,
        # No timeout_ms specified - schema default of 5000 applies
    }

    result = query_module.invoke(payload)

    assert result["ok"] is True

    # Verify default timeout (5000ms) was passed
    mock_memgraph.query.assert_called_once()
    call_kwargs = mock_memgraph.query.call_args.kwargs
    # Schema default is 5000ms, so it should be passed
    assert call_kwargs.get("timeout_ms") == 5000


def test_secure_query_execute_passes_timeout(mock_memgraph_secure):
    """
    Test that graph.secure_query.execute passes timeout_ms to adapter.
    """
    with patch.object(secure_query_module, "_check_permissions", return_value=True):
        mock_memgraph_secure.query.return_value = [{"n": {"name": "test"}}]

        payload = {
            "action": "execute",
            "cypher": "MATCH (n) RETURN n LIMIT 1",
            "principal": "test-user",
            "tenant": "test-tenant",
            "timeout_ms": 2000,  # Custom timeout
        }

        result = secure_query_module.invoke(payload)

        assert result["ok"] is True

        # Verify timeout was passed
        mock_memgraph_secure.query.assert_called_once()
        call_kwargs = mock_memgraph_secure.query.call_args.kwargs
        assert call_kwargs["timeout_ms"] == 2000


# ============================================================================
# Edge Case Tests
# ============================================================================


def test_graph_query_handles_zero_limit(mock_memgraph):
    """
    Test that graph.query rejects limit=0 (schema requires ge=1).
    """
    mock_memgraph.query.return_value = [{"x": 1}, {"x": 2}]

    payload = {
        "action": "run",
        "cypher": "MATCH (n) RETURN n LIMIT 2",
        "principal": "test-user",
        "tenant": "test-tenant",
        "read_only": True,
        "limit": 0,  # Zero limit - invalid per schema
    }

    result = query_module.invoke(payload)

    # Should fail validation
    assert result["ok"] is False
    assert "validation error" in result.get("message", "").lower()
    assert "limit" in result.get("message", "").lower()


def test_graph_query_handles_negative_limit(mock_memgraph):
    """
    Test that graph.query rejects negative limit (schema requires ge=1).
    """
    mock_memgraph.query.return_value = [{"x": 1}, {"x": 2}]

    payload = {
        "action": "run",
        "cypher": "MATCH (n) RETURN n LIMIT 2",
        "principal": "test-user",
        "tenant": "test-tenant",
        "read_only": True,
        "limit": -1,  # Negative limit - invalid per schema
    }

    result = query_module.invoke(payload)

    # Should fail validation
    assert result["ok"] is False
    assert "validation error" in result.get("message", "").lower()
    assert "limit" in result.get("message", "").lower()


def test_graph_query_handles_very_large_limit(mock_memgraph):
    """
    Test that graph.query handles very large limit values.
    """
    mock_memgraph.query.return_value = [{"x": i} for i in range(10)]

    payload = {
        "action": "run",
        "cypher": "MATCH (n) RETURN n LIMIT 10",
        "principal": "test-user",
        "tenant": "test-tenant",
        "read_only": True,
        "limit": 999999,  # Very large limit
    }

    result = query_module.invoke(payload)

    assert result["ok"] is True
    assert len(result["rows"]) == 10  # Only 10 rows available
    assert result["truncated"] is False


def test_timeout_zero_means_no_timeout(mock_memgraph):
    """
    Test that timeout_ms=0 is rejected (schema requires ge=100).
    """
    mock_memgraph.query.return_value = [{"n": {"name": "test"}}]

    payload = {
        "action": "run",
        "cypher": "MATCH (n) RETURN n LIMIT 1",
        "principal": "test-user",
        "tenant": "test-tenant",
        "read_only": True,
        "timeout_ms": 0,  # Zero timeout - invalid per schema
    }

    result = query_module.invoke(payload)

    # Should fail validation
    assert result["ok"] is False
    assert "validation error" in result.get("message", "").lower()
    assert "timeout" in result.get("message", "").lower()
