"""
Integration tests for graph.secure_query tool with P0 runtime infrastructure.

Tests cover:
- Pydantic schema validation
- All 4 actions (ask, generate, validate, execute)
- RBAC enforcement (requires principal/tenant)
- Security validation (read-only, forbidden clauses)
- Result formatting (rows, json, csv, markdown)

Note: The 'ask' and 'generate' actions require LLM, so we'll test other actions thoroughly
and mock the LLM for 'ask'/'generate' tests.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pydantic import ValidationError

# Tool under test
from src.mcp.tools.graph import secure_query as secure_query_module

# Schema
from src.mcp.schemas import GraphSecureQueryPayload


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_memgraph():
    """Mock Memgraph adapter for testing."""
    with patch("src.mcp.tools.graph.secure_query.MemgraphAdapter") as mock:
        instance = MagicMock()
        mock.return_value = instance

        # Default query response
        instance.query.return_value = [
            {"name": "Alice", "email": "alice@example.com", "status": "active"},
            {"name": "Bob", "email": "bob@example.com", "status": "active"},
        ]

        yield instance


@pytest.fixture
def mock_llm():
    """Mock LLM adapter for NL→Cypher generation."""
    with patch("src.mcp.tools.graph.secure_query.LLMAdapter") as mock:
        instance = MagicMock()
        mock.return_value = instance

        # Default LLM response
        instance.complete.return_value = {
            "content": "MATCH (n:User) WHERE n.status = 'active' RETURN n.name AS name, n.email AS email LIMIT 100"
        }

        yield instance


# ─────────────────────────────────────────────────────────────────────────────
# Schema Validation Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_schema_validation_ask_requires_prompt():
    """Test that ASK action requires prompt."""
    with pytest.raises(ValidationError) as exc:
        GraphSecureQueryPayload(
            action="ask",
            # Missing prompt
            principal="user@example.com",
            tenant="default",
        )
    assert "prompt" in str(exc.value).lower()


def test_schema_validation_validate_requires_cypher():
    """Test that VALIDATE action requires cypher."""
    with pytest.raises(ValidationError) as exc:
        GraphSecureQueryPayload(
            action="validate",
            # Missing cypher
            principal="user@example.com",
            tenant="default",
        )
    assert "cypher" in str(exc.value).lower()


def test_schema_validation_execute_requires_cypher():
    """Test that EXECUTE action requires cypher."""
    with pytest.raises(ValidationError) as exc:
        GraphSecureQueryPayload(
            action="execute",
            # Missing cypher
            principal="user@example.com",
            tenant="default",
        )
    assert "cypher" in str(exc.value).lower()


def test_schema_validation_valid_ask():
    """Test valid ASK payload."""
    payload = GraphSecureQueryPayload(
        action="ask",
        prompt="Show me all users",
        principal="user@example.com",
        tenant="default",
    )
    assert payload.action == "ask"
    assert payload.prompt == "Show me all users"


def test_schema_validation_valid_validate():
    """Test valid VALIDATE payload."""
    payload = GraphSecureQueryPayload(
        action="validate",
        cypher="MATCH (n:User) RETURN n",
        principal="user@example.com",
        tenant="default",
    )
    assert payload.action == "validate"
    assert payload.cypher == "MATCH (n:User) RETURN n"


# ─────────────────────────────────────────────────────────────────────────────
# Security Validation Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_read_only_query(mock_memgraph):
    """Test validation of read-only query."""
    payload = {
        "action": "validate",
        "cypher": "MATCH (n:User) RETURN n LIMIT 10",
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "validate"
    assert result["validation"]["read_only"] is True
    assert result["validation"]["safe"] is True
    assert result["validation"]["allowed"] is True
    assert result["validation"]["checks"]["write_operations"] is False


def test_validate_blocks_create(mock_memgraph):
    """Test that CREATE is detected as write operation."""
    payload = {
        "action": "validate",
        "cypher": "CREATE (n:User {name: 'Charlie'})",
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["validation"]["read_only"] is False
    assert result["validation"]["safe"] is False
    assert result["validation"]["checks"]["write_operations"] is True


def test_validate_blocks_merge(mock_memgraph):
    """Test that MERGE is detected as write operation."""
    payload = {
        "action": "validate",
        "cypher": "MERGE (n:User {id: 123})",
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["validation"]["read_only"] is False
    assert result["validation"]["safe"] is False


def test_validate_blocks_delete(mock_memgraph):
    """Test that DELETE is detected as write operation."""
    payload = {
        "action": "validate",
        "cypher": "MATCH (n:User) DELETE n",
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["validation"]["read_only"] is False
    assert result["validation"]["safe"] is False


def test_validate_blocks_set(mock_memgraph):
    """Test that SET is detected as write operation."""
    payload = {
        "action": "validate",
        "cypher": "MATCH (n:User) SET n.updated = true",
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["validation"]["read_only"] is False
    assert result["validation"]["safe"] is False


def test_validate_blocks_drop(mock_memgraph):
    """Test that DROP is detected as forbidden operation."""
    payload = {
        "action": "validate",
        "cypher": "DROP DATABASE production",
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["validation"]["safe"] is False
    assert len(result["validation"]["checks"]["forbidden_clauses"]) > 0
    assert "DROP" in result["validation"]["checks"]["forbidden_clauses"][0]


# ─────────────────────────────────────────────────────────────────────────────
# Execute Action Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_execute_accepts_statement_alias(mock_memgraph):
    """Ensure statement alias is accepted and executed."""
    payload = {
        "action": "execute",
        "statement": "MATCH (n:User) RETURN n LIMIT 1",
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["cypher"].startswith("MATCH")
    mock_memgraph.query.assert_called_once()


def test_execute_read_only_query(mock_memgraph):
    """Test executing a safe read-only query."""
    payload = {
        "action": "execute",
        "cypher": "MATCH (n:User) RETURN n.name AS name, n.email AS email LIMIT 10",
        "params": {},
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "execute"
    assert "rows" in result
    assert len(result["rows"]) == 2
    assert result["rowcount"] == 2
    assert result["truncated"] is False
    assert mock_memgraph.query.called


def test_execute_with_params(mock_memgraph):
    """Test executing query with parameters."""
    payload = {
        "action": "execute",
        "cypher": "MATCH (n:User) WHERE n.name = $name RETURN n",
        "params": {"name": "Alice"},
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert mock_memgraph.query.called
    call_args = mock_memgraph.query.call_args
    assert call_args[1]["params"] == {"name": "Alice"}


def test_execute_blocks_write_query(mock_memgraph):
    """Test that write queries are blocked on execute."""
    payload = {
        "action": "execute",
        "cypher": "CREATE (n:User {name: 'Charlie'})",
        "params": {},
        "principal": "user@example.com",
        "tenant": "default",
    }

    # Should raise ValueError due to safety validation
    result = secure_query_module.invoke(payload)
    assert result["ok"] is False
    assert result["code"] == "E_INTERNAL"
    msg = result["message"].lower()
    assert any(kw in msg for kw in ["write", "modify", "read-only", "read_only", "safety"])


def test_execute_applies_max_rows(mock_memgraph):
    """Test that max_rows is enforced."""
    # Mock returning many rows
    mock_memgraph.query.return_value = [{"id": i, "name": f"User{i}"} for i in range(100)]

    payload = {
        "action": "execute",
        "cypher": "MATCH (n:User) RETURN n.id AS id, n.name AS name",
        "params": {},
        "principal": "user@example.com",
        "tenant": "default",
        "max_rows": 10,
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["rowcount"] == 10  # Limited to max_rows
    assert result["truncated"] is True


def test_execute_respects_timeout(mock_memgraph):
    """Test that timeout_ms is passed to database."""
    payload = {
        "action": "execute",
        "cypher": "MATCH (n:User) RETURN n",
        "params": {},
        "principal": "user@example.com",
        "tenant": "default",
        "timeout_ms": 3000,
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    call_args = mock_memgraph.query.call_args
    assert call_args[1]["timeout_ms"] == 3000


# ─────────────────────────────────────────────────────────────────────────────
# Result Formatting Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_execute_format_rows(mock_memgraph):
    """Test rows format (default)."""
    payload = {
        "action": "execute",
        "cypher": "MATCH (n:User) RETURN n.name AS name",
        "params": {},
        "principal": "user@example.com",
        "tenant": "default",
        "return_format": "rows",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["format"] == "rows"
    assert isinstance(result["rows"], list)
    assert result["rows"][0]["name"] == "Alice"


def test_execute_format_json(mock_memgraph):
    """Test JSON format."""
    payload = {
        "action": "execute",
        "cypher": "MATCH (n:User) RETURN n.name AS name",
        "params": {},
        "principal": "user@example.com",
        "tenant": "default",
        "return_format": "json",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["format"] == "json"
    assert "formatted_output" in result
    assert isinstance(result["formatted_output"], str)
    assert "Alice" in result["formatted_output"]


def test_execute_format_csv(mock_memgraph):
    """Test CSV format."""
    payload = {
        "action": "execute",
        "cypher": "MATCH (n:User) RETURN n.name AS name",
        "params": {},
        "principal": "user@example.com",
        "tenant": "default",
        "return_format": "csv",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["format"] == "csv"
    assert "formatted_output" in result
    assert isinstance(result["formatted_output"], str)
    assert "name" in result["formatted_output"]  # CSV header
    assert "Alice" in result["formatted_output"]


def test_execute_format_markdown(mock_memgraph):
    """Test Markdown format."""
    payload = {
        "action": "execute",
        "cypher": "MATCH (n:User) RETURN n.name AS name",
        "params": {},
        "principal": "user@example.com",
        "tenant": "default",
        "return_format": "markdown",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["format"] == "markdown"
    assert "formatted_output" in result
    assert isinstance(result["formatted_output"], str)
    assert "|" in result["formatted_output"]  # Markdown table
    assert "Alice" in result["formatted_output"]


# ─────────────────────────────────────────────────────────────────────────────
# Generate Action Tests (with mocked LLM)
# ─────────────────────────────────────────────────────────────────────────────


def test_generate_from_nl_prompt(mock_memgraph, mock_llm):
    """Test generating Cypher from NL prompt."""
    # Mock schema queries
    mock_memgraph.query.side_effect = [
        [{"labels": ["User", "Task", "Project"]}],  # show_labels
        [{"types": ["ASSIGNED_TO", "OWNS"]}],  # show_relationship_types
    ]

    payload = {
        "action": "generate",
        "prompt": "Show me all active users",
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "generate"
    assert result["prompt"] == "Show me all active users"
    assert "cypher" in result
    assert "MATCH" in result["cypher"]
    assert "User" in result["cypher"]
    assert mock_llm.complete.called


# ─────────────────────────────────────────────────────────────────────────────
# Ask Action Tests (with mocked LLM and DB)
# ─────────────────────────────────────────────────────────────────────────────


def test_ask_end_to_end(mock_memgraph, mock_llm):
    """Test end-to-end ASK: generate → validate → execute."""
    # Mock schema queries for generation
    mock_memgraph.query.side_effect = [
        [{"labels": ["User"]}],  # show_labels
        [{"types": ["KNOWS"]}],  # show_relationship_types
        # Then the actual query execution
        [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ],
    ]

    payload = {
        "action": "ask",
        "prompt": "Show me all users",
        "principal": "user@example.com",
        "tenant": "default",
        "max_rows": 100,
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "ask"
    assert result["prompt"] == "Show me all users"
    assert "cypher" in result
    assert "rows" in result
    assert result["rowcount"] == 2
    assert "validation" in result
    assert result["validation"]["safe"] is True
    assert result["validation"]["read_only"] is True


# ─────────────────────────────────────────────────────────────────────────────
# RBAC Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_requires_principal(mock_memgraph):
    """Test that tool requires principal for RBAC."""
    payload = {
        "action": "validate",
        "cypher": "MATCH (n:User) RETURN n",
        # Missing principal and tenant
    }

    result = secure_query_module.invoke(payload)

    # Decorator should block requests without principal
    assert result["ok"] is False
    assert result["code"] == "E_PERMISSION"
    assert "principal" in result["message"].lower()


def test_with_authentication_context(mock_memgraph):
    """Test that tool works with proper authentication."""
    payload = {
        "action": "validate",
        "cypher": "MATCH (n:User) RETURN n",
        "principal": "admin@example.com",
        "tenant": "org_123",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["validation"]["allowed"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


def test_execute_empty_results(mock_memgraph):
    """Test handling of empty query results."""
    mock_memgraph.query.return_value = []

    payload = {
        "action": "execute",
        "cypher": "MATCH (n:NonExistent) RETURN n",
        "params": {},
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["rowcount"] == 0
    assert result["rows"] == []
    assert result["columns"] == []


def test_validate_case_insensitive_keywords(mock_memgraph):
    """Test that validation is case-insensitive."""
    payload = {
        "action": "validate",
        "cypher": "match (n:User) where n.id = 123 delete n",  # lowercase
        "principal": "user@example.com",
        "tenant": "default",
    }

    result = secure_query_module.invoke(payload)

    assert result["ok"] is True
    assert result["validation"]["read_only"] is False  # Should detect lowercase DELETE
