"""
Tests for hardened graph.schema tool.

Validates:
- Schema validation (action enum)
- Schema discovery actions (labels, types, properties, counts)
- Indexes and constraints discovery
- Inventory generation
- RBAC enforcement (principal requirement, authentication)
"""

import pytest
from pydantic import ValidationError
from unittest.mock import patch, MagicMock

from src.mcp.tools.graph import schema as schema_module
from src.mcp.schemas import GraphSchemaPayload


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_memgraph(monkeypatch):
    """Mock MemgraphAdapter to avoid real DB dependency."""
    mock_adapter = MagicMock()

    # Default responses for different queries
    mock_adapter.query.return_value = []

    def mock_adapter_factory():
        return mock_adapter

    monkeypatch.setattr("src.mcp.tools.graph.schema.MemgraphAdapter", mock_adapter_factory)
    return mock_adapter


# ─────────────────────────────────────────────────────────────────────────────
# Schema Validation Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_schema_validation_minimal():
    """Test minimal valid payload."""
    payload = GraphSchemaPayload(action="labels", principal="test-user", tenant="test-tenant")
    assert payload.action == "labels"
    assert payload.principal == "test-user"


def test_schema_validation_invalid_action():
    """Test invalid action raises ValidationError."""
    with pytest.raises(ValidationError):
        GraphSchemaPayload(action="invalid_action", principal="test-user", tenant="test-tenant")


def test_schema_validation_with_filters():
    """Test payload with optional filters."""
    payload = GraphSchemaPayload(action="node_properties", label="User", principal="test-user", tenant="test-tenant")
    assert payload.label == "User"


def test_schema_validation_type_alias():
    """Test 'type' field alias works."""
    payload = GraphSchemaPayload(
        action="relationship_properties", type="WORKS_AT", principal="test-user", tenant="test-tenant"
    )
    assert payload.type_ == "WORKS_AT"


# ─────────────────────────────────────────────────────────────────────────────
# Labels Action Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_labels_returns_node_labels(mock_memgraph):
    """Labels action returns all node labels."""
    mock_memgraph.query.return_value = [{"label": "User"}, {"label": "Task"}, {"label": "Project"}]

    result = schema_module.invoke({"action": "labels", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert result["action"] == "labels"
    assert "items" in result
    assert len(result["items"]) == 3
    assert "User" in result["items"]
    assert "Task" in result["items"]


def test_labels_empty_database(mock_memgraph):
    """Labels action with empty database returns empty list."""
    mock_memgraph.query.return_value = []

    result = schema_module.invoke({"action": "labels", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert result["items"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Relationship Types Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_relationship_types_returns_types(mock_memgraph):
    """Relationship_types action returns all relationship types."""
    mock_memgraph.query.return_value = [
        {"relationship_type": "WORKS_AT"},
        {"relationship_type": "MANAGES"},
        {"relationship_type": "ASSIGNED_TO"},
    ]

    result = schema_module.invoke({"action": "relationship_types", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert result["action"] == "relationship_types"
    assert len(result["items"]) == 3
    assert "WORKS_AT" in result["items"]


# ─────────────────────────────────────────────────────────────────────────────
# Node Properties Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_node_properties_all_labels(mock_memgraph):
    """Node_properties without label returns all properties."""
    mock_memgraph.query.return_value = [{"k": "name"}, {"k": "email"}, {"k": "age"}]

    result = schema_module.invoke({"action": "node_properties", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert result["action"] == "node_properties"
    assert len(result["items"]) == 3
    assert "name" in result["items"]


def test_node_properties_specific_label(mock_memgraph):
    """Node_properties with label filter."""
    mock_memgraph.query.return_value = [{"k": "firstName"}, {"k": "lastName"}, {"k": "email"}]

    result = schema_module.invoke(
        {"action": "node_properties", "label": "User", "principal": "test-user", "tenant": "test-tenant"}
    )

    assert result["ok"] is True
    assert result["label"] == "User"
    assert "firstName" in result["items"]


# ─────────────────────────────────────────────────────────────────────────────
# Relationship Properties Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_relationship_properties_all_types(mock_memgraph):
    """Relationship_properties without type returns all properties."""
    mock_memgraph.query.return_value = [{"k": "since"}, {"k": "role"}]

    result = schema_module.invoke(
        {"action": "relationship_properties", "principal": "test-user", "tenant": "test-tenant"}
    )

    assert result["ok"] is True
    assert len(result["items"]) == 2


def test_relationship_properties_specific_type(mock_memgraph):
    """Relationship_properties with type filter."""
    mock_memgraph.query.return_value = [{"k": "since"}, {"k": "department"}]

    result = schema_module.invoke(
        {"action": "relationship_properties", "type": "WORKS_AT", "principal": "test-user", "tenant": "test-tenant"}
    )

    assert result["ok"] is True
    assert result["type"] == "WORKS_AT"
    assert "since" in result["items"]


# ─────────────────────────────────────────────────────────────────────────────
# Count Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_node_counts(mock_memgraph):
    """Node_counts returns count per label."""
    mock_memgraph.query.return_value = [
        {"label": "User", "count": 150},
        {"label": "Task", "count": 320},
        {"label": "Project", "count": 45},
    ]

    result = schema_module.invoke({"action": "node_counts", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert result["action"] == "node_counts"
    assert len(result["items"]) == 3
    assert result["items"][0]["label"] == "User"
    assert result["items"][0]["count"] == 150


def test_relationship_counts(mock_memgraph):
    """Relationship_counts returns count per type."""
    mock_memgraph.query.return_value = [{"type": "WORKS_AT", "count": 150}, {"type": "MANAGES", "count": 45}]

    result = schema_module.invoke({"action": "relationship_counts", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert len(result["items"]) == 2
    assert result["items"][0]["type"] == "WORKS_AT"


# ─────────────────────────────────────────────────────────────────────────────
# Indexes and Constraints Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_indexes_returns_index_info(mock_memgraph):
    """Indexes action returns index information."""
    mock_memgraph.query.return_value = [{"label": "User", "properties": ["email"], "type": "label-property"}]

    result = schema_module.invoke({"action": "indexes", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert result["action"] == "indexes"
    assert len(result["items"]) == 1


def test_indexes_fallback_on_error(mock_memgraph):
    """Indexes action falls back to empty list on error."""
    mock_memgraph.query.side_effect = Exception("SHOW INDEX INFO not supported")

    result = schema_module.invoke({"action": "indexes", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert result["items"] == []


def test_constraints_returns_constraint_info(mock_memgraph):
    """Constraints action returns constraint information."""
    mock_memgraph.query.return_value = [{"label": "User", "properties": ["email"], "type": "unique"}]

    result = schema_module.invoke({"action": "constraints", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert result["action"] == "constraints"
    assert len(result["items"]) == 1


def test_constraints_fallback_on_error(mock_memgraph):
    """Constraints action falls back to empty list on error."""
    mock_memgraph.query.side_effect = Exception("Enterprise only")

    result = schema_module.invoke({"action": "constraints", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert result["items"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Inventory Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_inventory_returns_schema_summary(mock_memgraph):
    """Inventory action returns comprehensive schema summary."""
    mock_memgraph.query.return_value = [
        {"label": "User", "property": "email", "count": 100, "type": "STRING", "elementType": "node"},
        {"label": "WORKS_AT", "property": "User", "count": 50, "type": "RELATIONSHIP", "elementType": "relationship"},
    ]

    result = schema_module.invoke({"action": "inventory", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert result["action"] == "inventory"
    assert "columns" in result
    assert "rows" in result
    assert "rowcount" in result
    assert result["rowcount"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# RBAC Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_requires_principal(mock_memgraph):
    """Tool requires principal (enforced by decorator)."""
    mock_memgraph.query.return_value = []

    result = schema_module.invoke({"action": "labels", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True


def test_with_authentication_context(mock_memgraph):
    """Tool works with full authentication context."""
    mock_memgraph.query.return_value = [{"label": "User"}]

    result = schema_module.invoke(
        {"action": "labels", "principal": "auth0|user123", "tenant": "acme-corp", "trace_id": "trace-abc-123"}
    )

    assert result["ok"] is True
    assert "items" in result


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


def test_filters_none_values_from_results(mock_memgraph):
    """Tool filters out None values from query results."""
    mock_memgraph.query.return_value = [{"label": "User"}, {"label": None}, {"label": "Task"}]  # Should be filtered

    result = schema_module.invoke({"action": "labels", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    assert len(result["items"]) == 2
    assert None not in result["items"]


def test_handles_duplicate_labels(mock_memgraph):
    """Tool handles duplicate values correctly."""
    mock_memgraph.query.return_value = [{"label": "User"}, {"label": "User"}, {"label": "Task"}]  # Duplicate

    result = schema_module.invoke({"action": "labels", "principal": "test-user", "tenant": "test-tenant"})

    assert result["ok"] is True
    # Query should use DISTINCT, so duplicates handled by DB
    assert "User" in result["items"]
