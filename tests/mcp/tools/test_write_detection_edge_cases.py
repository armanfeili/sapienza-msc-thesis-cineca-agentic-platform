"""
Edge case tests for read-only enforcement in graph.query and graph.secure_query.

Tests tricky Cypher patterns that can imply writes:
- CALL { ... } subqueries with writes
- CALL db.createLabel/procedure writes
- FOREACH with SET/CREATE
- LOAD CSV variants with writes
- MERGE in subqueries
- DETACH DELETE
- SET after MATCH
"""

import pytest
from unittest.mock import MagicMock

from src.mcp.tools.graph import query as query_module
from src.mcp.tools.graph import secure_query as secure_query_module


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_memgraph(monkeypatch):
    """Mock MemgraphAdapter."""
    mock_adapter = MagicMock()
    mock_adapter.query.return_value = []

    def mock_adapter_factory():
        return mock_adapter

    # Patch for both modules
    monkeypatch.setattr("src.mcp.tools.graph.query.MemgraphAdapter", mock_adapter_factory)
    monkeypatch.setattr("src.mcp.tools.graph.secure_query.MemgraphAdapter", mock_adapter_factory)
    return mock_adapter


# ─────────────────────────────────────────────────────────────────────────────
# CALL { } Subquery Write Detection
# ─────────────────────────────────────────────────────────────────────────────


def test_graph_query_blocks_call_subquery_with_create(mock_memgraph):
    """CALL { CREATE ... } in subquery is blocked in read-only mode."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "CALL { CREATE (n:User {name: 'Alice'}) RETURN n } RETURN n",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    msg = result.get("message", "").lower()
    assert any(kw in msg for kw in ["write", "create", "modify", "read-only", "read_only"])


def test_graph_query_blocks_call_subquery_with_merge(mock_memgraph):
    """CALL { MERGE ... } in subquery is blocked in read-only mode."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "CALL { MERGE (n:User {id: 1}) RETURN n } RETURN n",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    msg = result.get("message", "").lower()
    assert any(kw in msg for kw in ["write", "merge", "modify", "read-only", "read_only"])


def test_secure_query_validates_call_subquery_write(mock_memgraph):
    """graph.secure_query.validate detects writes in CALL subqueries."""
    result = secure_query_module.invoke(
        {
            "action": "validate",
            "cypher": "CALL { CREATE (n:Temp) RETURN n } RETURN count(n)",
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    # Should detect write operation
    assert result["ok"] is True  # Validation succeeds
    assert result["is_safe"] is False  # But query is unsafe
    assert result["is_write"] is True  # Detected as write


# ─────────────────────────────────────────────────────────────────────────────
# CALL db.* Procedure Writes
# ─────────────────────────────────────────────────────────────────────────────


def test_graph_query_blocks_call_db_create_label(mock_memgraph):
    """CALL db.createLabel is blocked in read-only mode."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "CALL db.createLabel('NewLabel')",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    msg = result.get("message", "").lower()
    assert any(kw in msg for kw in ["write", "modify", "read-only", "read_only"])


def test_graph_query_blocks_call_db_create_property(mock_memgraph):
    """CALL db.createProperty is blocked in read-only mode."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "CALL db.createProperty('newProp')",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    msg = result.get("message", "").lower()
    assert any(kw in msg for kw in ["write", "modify", "read-only", "read_only"])


def test_secure_query_validates_call_procedures(mock_memgraph):
    """graph.secure_query.validate detects CALL procedure writes."""
    result = secure_query_module.invoke(
        {
            "action": "validate",
            "cypher": "CALL db.createLabel('Evil')",
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is True  # Validation succeeds
    assert result["is_safe"] is False  # But query is unsafe
    assert result["is_write"] is True  # Detected as write


# ─────────────────────────────────────────────────────────────────────────────
# FOREACH Write Detection
# ─────────────────────────────────────────────────────────────────────────────


def test_graph_query_blocks_foreach_with_create(mock_memgraph):
    """FOREACH with CREATE is blocked in read-only mode."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "MATCH (u:User) FOREACH (i IN [1,2,3] | CREATE (n:Task {id: i}))",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    msg = result.get("message", "").lower()
    assert any(kw in msg for kw in ["write", "create", "modify", "read-only", "read_only"])


def test_graph_query_blocks_foreach_with_set(mock_memgraph):
    """FOREACH with SET is blocked in read-only mode."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "MATCH (u:User) FOREACH (i IN [1,2,3] | SET u.count = i)",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    msg = result.get("message", "").lower()
    assert any(kw in msg for kw in ["write", "set", "modify", "read-only", "read_only"])


def test_secure_query_validates_foreach_writes(mock_memgraph):
    """graph.secure_query.validate detects FOREACH writes."""
    result = secure_query_module.invoke(
        {
            "action": "validate",
            "cypher": "MATCH (u) FOREACH (x IN [1] | SET u.flag = true)",
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["is_write"] is True


# ─────────────────────────────────────────────────────────────────────────────
# LOAD CSV Write Detection
# ─────────────────────────────────────────────────────────────────────────────


def test_graph_query_blocks_load_csv_with_create(mock_memgraph):
    """LOAD CSV with CREATE is blocked in read-only mode."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "LOAD CSV FROM 'file:///data.csv' AS row CREATE (n:User {name: row[0]})",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    msg = result.get("message", "").lower()
    assert any(kw in msg for kw in ["write", "create", "modify", "read-only", "read_only"])


def test_graph_query_blocks_load_csv_with_merge(mock_memgraph):
    """LOAD CSV with MERGE is blocked in read-only mode."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "LOAD CSV FROM 'file:///data.csv' AS row MERGE (n:User {id: row[0]})",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False


def test_secure_query_validates_load_csv_writes(mock_memgraph):
    """graph.secure_query.validate detects LOAD CSV writes."""
    result = secure_query_module.invoke(
        {
            "action": "validate",
            "cypher": "LOAD CSV FROM 'file:///evil.csv' AS row CREATE (n {data: row})",
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["is_write"] is True


# ─────────────────────────────────────────────────────────────────────────────
# DETACH DELETE Detection
# ─────────────────────────────────────────────────────────────────────────────


def test_graph_query_blocks_detach_delete(mock_memgraph):
    """DETACH DELETE is blocked in read-only mode."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "MATCH (n:User {id: 123}) DETACH DELETE n",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    msg = result.get("message", "").lower()
    assert any(kw in msg for kw in ["write", "delete", "modify", "read-only", "read_only"])


def test_secure_query_validates_detach_delete(mock_memgraph):
    """graph.secure_query.validate detects DETACH DELETE."""
    result = secure_query_module.invoke(
        {"action": "validate", "cypher": "MATCH (n) DETACH DELETE n", "principal": "test-user", "tenant": "test-tenant"}
    )

    assert result["is_write"] is True


# ─────────────────────────────────────────────────────────────────────────────
# SET After MATCH Detection
# ─────────────────────────────────────────────────────────────────────────────


def test_graph_query_blocks_set_after_match(mock_memgraph):
    """SET after MATCH is blocked in read-only mode."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "MATCH (u:User {id: 123}) SET u.hacked = true RETURN u",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False
    msg = result.get("message", "").lower()
    assert any(kw in msg for kw in ["write", "set", "modify", "read-only", "read_only"])


def test_secure_query_validates_set_operations(mock_memgraph):
    """graph.secure_query.validate detects SET operations."""
    result = secure_query_module.invoke(
        {
            "action": "validate",
            "cypher": "MATCH (n) SET n.modified = timestamp()",
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["is_write"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Case Insensitivity Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_graph_query_blocks_lowercase_create(mock_memgraph):
    """Lowercase 'create' is also blocked."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "create (n:User {name: 'test'})",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False


def test_graph_query_blocks_mixed_case_merge(mock_memgraph):
    """MiXeD cAsE 'MeRgE' is also blocked."""
    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "MaTcH (n) MeRgE (m:User {id: 1})",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Safe Read-Only Queries (Should Pass)
# ─────────────────────────────────────────────────────────────────────────────


def test_graph_query_allows_safe_match(mock_memgraph):
    """Safe MATCH queries are allowed in read-only mode."""
    mock_memgraph.query.return_value = [{"name": "Alice"}]

    result = query_module.invoke(
        {
            "action": "run",
            "cypher": "MATCH (u:User) RETURN u.name LIMIT 10",
            "read_only": True,
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is True
    assert result["action"] == "run"


def test_secure_query_validates_safe_query(mock_memgraph):
    """Safe queries pass validation."""
    result = secure_query_module.invoke(
        {
            "action": "validate",
            "cypher": "MATCH (u:User)-[:WORKS_AT]->(c:Company) RETURN u.name, c.name",
            "principal": "test-user",
            "tenant": "test-tenant",
        }
    )

    assert result["ok"] is True
    assert result["is_safe"] is True
    assert result["is_write"] is False
