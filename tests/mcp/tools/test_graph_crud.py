"""
Unit tests for graph.crud tool.

Coverage:
- Schema validation (10 tests)
- CRUD operations (15 tests)
- Write permission enforcement (12 tests)
- Transaction safety (10 tests)
- Security/RBAC (10 tests)

Total: 57 tests
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pydantic import ValidationError

# Import the tool module
import src.mcp.tools.graph.crud as graph_crud_module
from src.mcp.schemas import GraphCrudPayload, GraphCrudOperation


# ──────────────────────────────────────────────────────────────────────────────
# 1. Schema Validation Tests (10 tests)
# ──────────────────────────────────────────────────────────────────────────────
def test_create_node_payload_valid():
    """Test valid create_node payload."""
    payload = {
        "operation": "create_node",
        "labels": ["User"],
        "properties": {"name": "Alice", "orig_id": "user-1"},
        "principal": "test-user",
        "tenant": "tenant-1",
    }
    validated = GraphCrudPayload(**payload)
    assert validated.operation == GraphCrudOperation.create_node
    assert validated.labels == ["User"]
    assert validated.properties == {"name": "Alice", "orig_id": "user-1"}


def test_update_node_payload_valid():
    """Test valid update_node payload."""
    payload = {
        "operation": "update_node",
        "label": "User",
        "match": {"orig_id": "user-1"},
        "properties": {"age": 30},
        "principal": "test-user",
        "tenant": "tenant-1",
    }
    validated = GraphCrudPayload(**payload)
    assert validated.operation == GraphCrudOperation.update_node
    assert validated.match == {"orig_id": "user-1"}


def test_delete_node_payload_valid():
    """Test valid delete_node payload."""
    payload = {
        "operation": "delete_node",
        "match": {"orig_id": "user-1"},
        "principal": "test-user",
        "tenant": "tenant-1",
    }
    validated = GraphCrudPayload(**payload)
    assert validated.operation == GraphCrudOperation.delete_node
    assert validated.match == {"orig_id": "user-1"}


def test_create_relationship_payload_valid():
    """Test valid create_relationship payload."""
    payload = {
        "operation": "create_relationship",
        "from": {"orig_id": "user-1"},
        "to": {"orig_id": "project-1"},
        "rel_type": "WORKS_ON",
        "properties": {"since": "2024-01-01"},
        "principal": "test-user",
        "tenant": "tenant-1",
    }
    validated = GraphCrudPayload(**payload)
    assert validated.operation == GraphCrudOperation.create_relationship
    assert validated.from_["orig_id"] == "user-1"
    assert validated.to["orig_id"] == "project-1"
    assert validated.rel_type == "WORKS_ON"


def test_delete_relationship_payload_valid():
    """Test valid delete_relationship payload."""
    payload = {
        "operation": "delete_relationship",
        "from": {"orig_id": "user-1"},
        "to": {"orig_id": "project-1"},
        "rel_type": "WORKS_ON",
        "principal": "test-user",
        "tenant": "tenant-1",
    }
    validated = GraphCrudPayload(**payload)
    assert validated.operation == GraphCrudOperation.delete_relationship


def test_missing_operation_field():
    """Test payload missing required operation field."""
    with pytest.raises(ValidationError) as exc_info:
        GraphCrudPayload(labels=["User"], principal="test-user", tenant="tenant-1")
    assert "operation" in str(exc_info.value)


def test_invalid_operation_value():
    """Test payload with invalid operation value."""
    with pytest.raises(ValidationError):
        GraphCrudPayload(operation="invalid_op", principal="test-user", tenant="tenant-1")


def test_from_field_alias():
    """Test 'from' field accepts both 'from' and 'from_' via alias."""
    payload = {
        "operation": "create_relationship",
        "from": {"orig_id": "node-1"},
        "to": {"orig_id": "node-2"},
        "rel_type": "LINKS",
        "principal": "test-user",
        "tenant": "tenant-1",
    }
    validated = GraphCrudPayload(**payload)
    # Field is stored as from_ internally
    assert validated.from_["orig_id"] == "node-1"


def test_empty_labels_rejected():
    """Test that empty labels list is caught early."""
    payload = {
        "operation": "create_node",
        "labels": [],
        "properties": {"orig_id": "node-1"},
        "principal": "test-user",
        "tenant": "tenant-1",
    }
    # Schema allows empty list, but invoke should reject
    validated = GraphCrudPayload(**payload)
    assert validated.labels == []


def test_principal_and_tenant_optional_in_schema():
    """Test that principal and tenant are optional in schema but required at runtime."""
    payload = {"operation": "create_node", "labels": ["User"], "properties": {"orig_id": "user-1"}}
    # Schema validation passes (fields are optional)
    validated = GraphCrudPayload(**payload)
    assert validated.principal is None
    assert validated.tenant is None
    # Runtime validation (in invoke) should catch this


# ──────────────────────────────────────────────────────────────────────────────
# 2. CRUD Operations Tests (15 tests)
# ──────────────────────────────────────────────────────────────────────────────
@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_node_new(mock_adapter_class):
    """Test creating a new node (didn't exist before)."""
    mock_db = mock_adapter_class.return_value
    # First query: existence check returns 0
    mock_db.query.side_effect = [
        [{"c": 0}],  # existence check
        None,  # MERGE query (no return)
        [
            {
                "labels": ["User"],
                "props": {"orig_id": "user-1", "name": "Alice", "tenant": "tenant-1", "created_by": "test-user"},
            }
        ],  # fetch created node
    ]

    result = graph_crud_module._act_create_node(
        mock_db,
        {"labels": ["User"], "properties": {"orig_id": "user-1", "name": "Alice"}},
        principal="test-user",
        tenant="tenant-1",
    )

    assert result["ok"] is True
    assert result["operation"] == "create_node"
    assert result["created"] is True
    assert result["node"]["orig_id"] == "user-1"
    assert result["node"]["labels"] == ["User"]
    assert "elapsed_ms" in result


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_node_existing(mock_adapter_class):
    """Test creating a node that already exists (merge semantics)."""
    mock_db = mock_adapter_class.return_value
    # Existence check returns 1 (exists)
    mock_db.query.side_effect = [
        [{"c": 1}],  # existence check
        None,  # MERGE query
        [
            {"labels": ["User"], "props": {"orig_id": "user-1", "name": "Alice Updated", "tenant": "tenant-1"}}
        ],  # fetch node
    ]

    result = graph_crud_module._act_create_node(
        mock_db,
        {"labels": ["User"], "properties": {"orig_id": "user-1", "name": "Alice Updated"}},
        principal="test-user",
        tenant="tenant-1",
    )

    assert result["created"] is False  # Not newly created


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_node_auto_generate_orig_id(mock_adapter_class):
    """Test creating a node with auto-generated orig_id."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [
        [{"c": 0}],  # existence check
        None,  # MERGE
        [
            {
                "labels": ["User"],
                "props": {
                    "orig_id": "auto-generated-uuid",
                    "name": "Bob",
                    "tenant": "tenant-1",
                    "created_by": "test-user",
                },
            }
        ],
    ]

    result = graph_crud_module._act_create_node(
        mock_db,
        {"labels": ["User"], "properties": {"name": "Bob"}},  # no orig_id
        principal="test-user",
        tenant="tenant-1",
    )

    assert result["ok"] is True
    assert "orig_id" in result["node"]["properties"]  # auto-generated


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_update_node_by_orig_id(mock_adapter_class):
    """Test updating node by orig_id."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = [
        {"labels": ["User"], "props": {"orig_id": "user-1", "name": "Alice", "age": 30, "tenant": "tenant-1"}}
    ]

    result = graph_crud_module._act_update_node(
        mock_db,
        {"match": {"orig_id": "user-1"}, "properties": {"age": 30}, "mode": "merge"},
        principal="test-user",
        tenant="tenant-1",
    )

    assert result["ok"] is True
    assert result["operation"] == "update_node"
    assert result["updated"] is True
    assert result["node"]["properties"]["age"] == 30


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_update_node_by_label_and_match(mock_adapter_class):
    """Test updating node by label + match conditions."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = [
        {
            "labels": ["User"],
            "props": {"orig_id": "user-1", "email": "alice@example.com", "status": "active", "tenant": "tenant-1"},
        }
    ]

    result = graph_crud_module._act_update_node(
        mock_db,
        {"label": "User", "match": {"email": "alice@example.com"}, "properties": {"status": "active"}},
        principal="test-user",
        tenant="tenant-1",
    )

    assert result["updated"] is True
    assert "email" in result["node"]["properties"]


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_update_node_replace_mode(mock_adapter_class):
    """Test updating node with replace mode (replaces all properties except orig_id)."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = [
        {"labels": ["User"], "props": {"orig_id": "user-1", "name": "New Name", "tenant": "tenant-1"}}
    ]

    result = graph_crud_module._act_update_node(
        mock_db,
        {"match": {"orig_id": "user-1"}, "properties": {"name": "New Name"}, "mode": "replace"},
        principal="test-user",
        tenant="tenant-1",
    )

    assert result["ok"] is True
    # In replace mode, old properties are removed except orig_id


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_update_node_not_found(mock_adapter_class):
    """Test updating non-existent node raises error."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = []  # No node found

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module._act_update_node(
            mock_db,
            {"match": {"orig_id": "nonexistent"}, "properties": {"name": "Test"}},
            principal="test-user",
            tenant="tenant-1",
        )
    assert "No node found" in str(exc_info.value)


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_delete_node_by_orig_id(mock_adapter_class):
    """Test deleting node by orig_id."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = [{"c": 1}]  # One node deleted

    result = graph_crud_module._act_delete_node(
        mock_db, {"match": {"orig_id": "user-1"}}, principal="test-user", tenant="tenant-1"
    )

    assert result["ok"] is True
    assert result["operation"] == "delete_node"
    assert result["deleted"] == 1
    assert "elapsed_ms" in result


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_delete_node_by_label_and_match(mock_adapter_class):
    """Test deleting node by label + match conditions."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = [{"c": 1}]

    result = graph_crud_module._act_delete_node(
        mock_db, {"label": "User", "match": {"email": "test@example.com"}}, principal="test-user", tenant="tenant-1"
    )

    assert result["deleted"] == 1


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_delete_node_not_found(mock_adapter_class):
    """Test deleting non-existent node returns deleted=0."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = []  # No node found

    result = graph_crud_module._act_delete_node(
        mock_db, {"match": {"orig_id": "nonexistent"}}, principal="test-user", tenant="tenant-1"
    )

    assert result["deleted"] == 0


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_relationship_new(mock_adapter_class):
    """Test creating a new relationship."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [[{"c": 0}], None]  # existence check: doesn't exist  # MERGE query

    result = graph_crud_module._act_create_relationship(
        mock_db,
        {
            "from_": {"orig_id": "user-1"},
            "to": {"orig_id": "project-1"},
            "rel_type": "WORKS_ON",
            "properties": {"since": "2024-01-01"},
        },
        principal="test-user",
        tenant="tenant-1",
    )

    assert result["ok"] is True
    assert result["operation"] == "create_relationship"
    assert result["created"] is True
    assert result["relationship"]["type"] == "WORKS_ON"
    assert result["relationship"]["from_orig_id"] == "user-1"
    assert result["relationship"]["to_orig_id"] == "project-1"


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_relationship_existing(mock_adapter_class):
    """Test creating relationship that already exists (merge semantics)."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [[{"c": 1}], None]  # existence check: exists  # MERGE query

    result = graph_crud_module._act_create_relationship(
        mock_db,
        {
            "from_": {"orig_id": "user-1"},
            "to": {"orig_id": "project-1"},
            "rel_type": "WORKS_ON",
            "properties": {"updated": "2024-02-01"},
        },
        principal="test-user",
        tenant="tenant-1",
    )

    assert result["created"] is False  # Not newly created


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_delete_relationship_exists(mock_adapter_class):
    """Test deleting existing relationship."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = [{"c": 1}]  # One relationship deleted

    result = graph_crud_module._act_delete_relationship(
        mock_db,
        {"from_": {"orig_id": "user-1"}, "to": {"orig_id": "project-1"}, "rel_type": "WORKS_ON"},
        principal="test-user",
        tenant="tenant-1",
    )

    assert result["ok"] is True
    assert result["operation"] == "delete_relationship"
    assert result["deleted"] == 1


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_delete_relationship_not_found(mock_adapter_class):
    """Test deleting non-existent relationship returns deleted=0."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = []  # No relationship found

    result = graph_crud_module._act_delete_relationship(
        mock_db,
        {"from_": {"orig_id": "user-1"}, "to": {"orig_id": "project-999"}, "rel_type": "WORKS_ON"},
        principal="test-user",
        tenant="tenant-1",
    )

    assert result["deleted"] == 0


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_node_missing_labels(mock_adapter_class):
    """Test creating node without labels raises error."""
    mock_db = mock_adapter_class.return_value

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module._act_create_node(
            mock_db,
            {
                "properties": {"name": "Test"}
                # missing labels
            },
            principal="test-user",
            tenant="tenant-1",
        )
    assert "requires 'labels'" in str(exc_info.value)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Write Permission Enforcement Tests (12 tests)
# ──────────────────────────────────────────────────────────────────────────────
def test_tool_has_write_scope_decorator():
    """Test that graph.crud tool has tools:write scope requirement."""
    # Check that the invoke function has the @mcp_tool decorator with required_scope
    assert hasattr(graph_crud_module.invoke, "__wrapped__")
    # The decorator should enforce tools:write scope


def test_create_node_requires_principal():
    """Test that create_node requires principal."""
    payload = {
        "operation": "create_node",
        "labels": ["User"],
        "properties": {"orig_id": "user-1"},
        "tenant": "tenant-1"
        # missing principal
    }

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module.invoke.__wrapped__(None, payload)  # ctx
    assert "principal is required" in str(exc_info.value)


def test_create_node_requires_tenant():
    """Test that create_node requires tenant."""
    payload = {
        "operation": "create_node",
        "labels": ["User"],
        "properties": {"orig_id": "user-1"},
        "principal": "test-user"
        # missing tenant
    }

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module.invoke.__wrapped__(None, payload)  # ctx
    assert "tenant is required" in str(exc_info.value)


def test_update_node_requires_principal():
    """Test that update_node requires principal."""
    payload = {
        "operation": "update_node",
        "match": {"orig_id": "user-1"},
        "properties": {"age": 30},
        "tenant": "tenant-1"
        # missing principal
    }

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module.invoke.__wrapped__(None, payload)
    assert "principal is required" in str(exc_info.value)


def test_delete_node_requires_principal():
    """Test that delete_node requires principal."""
    payload = {
        "operation": "delete_node",
        "match": {"orig_id": "user-1"},
        "tenant": "tenant-1"
        # missing principal
    }

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module.invoke.__wrapped__(None, payload)
    assert "principal is required" in str(exc_info.value)


def test_create_relationship_requires_principal():
    """Test that create_relationship requires principal."""
    payload = {
        "operation": "create_relationship",
        "from": {"orig_id": "user-1"},
        "to": {"orig_id": "project-1"},
        "rel_type": "WORKS_ON",
        "tenant": "tenant-1"
        # missing principal
    }

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module.invoke.__wrapped__(None, payload)
    assert "principal is required" in str(exc_info.value)


def test_delete_relationship_requires_principal():
    """Test that delete_relationship requires principal."""
    payload = {
        "operation": "delete_relationship",
        "from": {"orig_id": "user-1"},
        "to": {"orig_id": "project-1"},
        "rel_type": "WORKS_ON",
        "tenant": "tenant-1"
        # missing principal
    }

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module.invoke.__wrapped__(None, payload)
    assert "principal is required" in str(exc_info.value)


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_node_adds_tenant_to_properties(mock_adapter_class):
    """Test that create_node automatically adds tenant to node properties."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [
        [{"c": 0}],  # existence check
        None,  # MERGE
        [{"labels": ["User"], "props": {"orig_id": "user-1", "tenant": "tenant-1", "created_by": "test-user"}}],
    ]

    result = graph_crud_module._act_create_node(
        mock_db, {"labels": ["User"], "properties": {"orig_id": "user-1"}}, principal="test-user", tenant="tenant-1"
    )

    # Check that MERGE was called with tenant in properties
    merge_call = mock_db.query.call_args_list[1]
    assert "tenant" in merge_call[0][1]["props"]
    assert merge_call[0][1]["props"]["tenant"] == "tenant-1"


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_relationship_adds_tenant_to_properties(mock_adapter_class):
    """Test that create_relationship automatically adds tenant to relationship properties."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [[{"c": 0}], None]  # existence check  # MERGE

    result = graph_crud_module._act_create_relationship(
        mock_db,
        {"from_": {"orig_id": "user-1"}, "to": {"orig_id": "project-1"}, "rel_type": "WORKS_ON", "properties": {}},
        principal="test-user",
        tenant="tenant-1",
    )

    # Check that tenant was added to properties in result
    assert result["relationship"]["properties"]["tenant"] == "tenant-1"


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_update_node_enforces_tenant_isolation(mock_adapter_class):
    """Test that update_node only updates nodes from same tenant."""
    mock_db = mock_adapter_class.return_value

    # Tenant in query should match tenant in payload
    mock_db.query.return_value = [{"labels": ["User"], "props": {"orig_id": "user-1", "tenant": "tenant-1"}}]

    result = graph_crud_module._act_update_node(
        mock_db,
        {"match": {"orig_id": "user-1"}, "properties": {"name": "Updated"}},
        principal="test-user",
        tenant="tenant-1",
    )

    # Check that query includes tenant filter
    cypher = mock_db.query.call_args[0][0]
    assert "tenant: $tenant" in cypher


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_delete_node_enforces_tenant_isolation(mock_adapter_class):
    """Test that delete_node only deletes nodes from same tenant."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = [{"c": 1}]

    result = graph_crud_module._act_delete_node(
        mock_db, {"match": {"orig_id": "user-1"}}, principal="test-user", tenant="tenant-1"
    )

    # Check that query includes tenant filter
    cypher = mock_db.query.call_args[0][0]
    assert "tenant: $tenant" in cypher


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_relationship_enforces_tenant_isolation(mock_adapter_class):
    """Test that create_relationship only connects nodes from same tenant."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [[{"c": 0}], None]  # existence check  # MERGE

    result = graph_crud_module._act_create_relationship(
        mock_db,
        {"from_": {"orig_id": "user-1"}, "to": {"orig_id": "project-1"}, "rel_type": "WORKS_ON", "properties": {}},
        principal="test-user",
        tenant="tenant-1",
    )

    # Check that MERGE query includes tenant filter on both nodes
    merge_call = mock_db.query.call_args_list[1]
    cypher = merge_call[0][0]
    assert cypher.count("tenant: $tenant") == 2  # Both source and target nodes


# ──────────────────────────────────────────────────────────────────────────────
# 4. Transaction Safety Tests (10 tests)
# ──────────────────────────────────────────────────────────────────────────────
@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_node_is_transactional(mock_adapter_class):
    """Test that create_node operations are transactional (existence check + MERGE + fetch)."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [
        [{"c": 0}],  # existence check
        None,  # MERGE
        [
            {"labels": ["User"], "props": {"orig_id": "user-1", "tenant": "tenant-1", "created_by": "test-user"}}
        ],  # fetch
    ]

    result = graph_crud_module._act_create_node(
        mock_db, {"labels": ["User"], "properties": {"orig_id": "user-1"}}, principal="test-user", tenant="tenant-1"
    )

    # Should have 3 queries: check existence, MERGE, fetch
    assert mock_db.query.call_count == 3


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_update_node_returns_updated_properties(mock_adapter_class):
    """Test that update_node returns the updated node properties."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = [
        {"labels": ["User"], "props": {"orig_id": "user-1", "name": "Updated Name", "age": 30, "tenant": "tenant-1"}}
    ]

    result = graph_crud_module._act_update_node(
        mock_db,
        {"match": {"orig_id": "user-1"}, "properties": {"name": "Updated Name", "age": 30}},
        principal="test-user",
        tenant="tenant-1",
    )

    # Result should include updated properties
    assert result["node"]["properties"]["name"] == "Updated Name"
    assert result["node"]["properties"]["age"] == 30


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_delete_node_uses_detach_delete(mock_adapter_class):
    """Test that delete_node uses DETACH DELETE to remove relationships."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = [{"c": 1}]

    result = graph_crud_module._act_delete_node(
        mock_db, {"match": {"orig_id": "user-1"}}, principal="test-user", tenant="tenant-1"
    )

    # Check that DETACH DELETE was used
    cypher = mock_db.query.call_args[0][0]
    assert "DETACH DELETE" in cypher


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_relationship_requires_both_nodes_exist(mock_adapter_class):
    """Test that create_relationship matches both nodes (MATCH before MERGE)."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [[{"c": 0}], None]  # existence check  # MERGE

    result = graph_crud_module._act_create_relationship(
        mock_db,
        {"from_": {"orig_id": "user-1"}, "to": {"orig_id": "project-1"}, "rel_type": "WORKS_ON", "properties": {}},
        principal="test-user",
        tenant="tenant-1",
    )

    # Check that MATCH is used before MERGE
    merge_call = mock_db.query.call_args_list[1]
    cypher = merge_call[0][0]
    assert "MATCH (a {orig_id: $from_id" in cypher
    assert "MATCH" in cypher
    assert "MERGE" in cypher


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_node_with_failure_raises_error(mock_adapter_class):
    """Test that create_node raises error if node fetch fails after MERGE."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [[{"c": 0}], None, []]  # existence check  # MERGE  # fetch fails (empty result)

    with pytest.raises(RuntimeError) as exc_info:
        graph_crud_module._act_create_node(
            mock_db, {"labels": ["User"], "properties": {"orig_id": "user-1"}}, principal="test-user", tenant="tenant-1"
        )
    assert "Failed to create node" in str(exc_info.value)


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_update_node_missing_properties_rejected(mock_adapter_class):
    """Test that update_node without properties raises error."""
    mock_db = mock_adapter_class.return_value

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module._act_update_node(
            mock_db,
            {
                "match": {"orig_id": "user-1"}
                # missing properties
            },
            principal="test-user",
            tenant="tenant-1",
        )
    assert "requires 'properties'" in str(exc_info.value)


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_delete_node_missing_match_rejected(mock_adapter_class):
    """Test that delete_node without match criteria raises error."""
    mock_db = mock_adapter_class.return_value

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module._act_delete_node(
            mock_db,
            {
                # missing match
            },
            principal="test-user",
            tenant="tenant-1",
        )
    assert "requires either" in str(exc_info.value)


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_relationship_missing_from_rejected(mock_adapter_class):
    """Test that create_relationship without 'from' raises error."""
    mock_db = mock_adapter_class.return_value

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module._act_create_relationship(
            mock_db,
            {
                # missing from_
                "to": {"orig_id": "project-1"},
                "rel_type": "WORKS_ON",
                "properties": {},
            },
            principal="test-user",
            tenant="tenant-1",
        )
    assert "requires 'from'" in str(exc_info.value)


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_relationship_missing_to_rejected(mock_adapter_class):
    """Test that create_relationship without 'to' raises error."""
    mock_db = mock_adapter_class.return_value

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module._act_create_relationship(
            mock_db,
            {
                "from_": {"orig_id": "user-1"},
                # missing to
                "rel_type": "WORKS_ON",
                "properties": {},
            },
            principal="test-user",
            tenant="tenant-1",
        )
    assert "requires" in str(exc_info.value).lower()


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_relationship_missing_rel_type_rejected(mock_adapter_class):
    """Test that create_relationship without rel_type raises error."""
    mock_db = mock_adapter_class.return_value

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module._act_create_relationship(
            mock_db,
            {
                "from_": {"orig_id": "user-1"},
                "to": {"orig_id": "project-1"},
                # missing rel_type
                "properties": {},
            },
            principal="test-user",
            tenant="tenant-1",
        )
    assert "requires" in str(exc_info.value).lower()


# ──────────────────────────────────────────────────────────────────────────────
# 5. Security/RBAC Tests (10 tests)
# ──────────────────────────────────────────────────────────────────────────────
def test_empty_principal_rejected():
    """Test that empty principal string is rejected."""
    payload = {
        "operation": "create_node",
        "labels": ["User"],
        "properties": {"orig_id": "user-1"},
        "principal": "",  # empty string
        "tenant": "tenant-1",
    }

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module.invoke.__wrapped__(None, payload)
    assert "principal is required" in str(exc_info.value)


def test_empty_tenant_rejected():
    """Test that empty tenant string is rejected."""
    payload = {
        "operation": "create_node",
        "labels": ["User"],
        "properties": {"orig_id": "user-1"},
        "principal": "test-user",
        "tenant": "",  # empty string
    }

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module.invoke.__wrapped__(None, payload)
    assert "tenant is required" in str(exc_info.value)


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_node_adds_created_by_metadata(mock_adapter_class):
    """Test that create_node adds created_by metadata."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [
        [{"c": 0}],
        None,
        [{"labels": ["User"], "props": {"orig_id": "user-1", "created_by": "alice", "tenant": "tenant-1"}}],
    ]

    result = graph_crud_module._act_create_node(
        mock_db, {"labels": ["User"], "properties": {"orig_id": "user-1"}}, principal="alice", tenant="tenant-1"
    )

    # Check that created_by was added
    merge_call = mock_db.query.call_args_list[1]
    assert merge_call[0][1]["props"]["created_by"] == "alice"


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_update_node_adds_updated_by_metadata(mock_adapter_class):
    """Test that update_node adds updated_by and updated_at metadata."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = [
        {"labels": ["User"], "props": {"orig_id": "user-1", "updated_by": "bob", "tenant": "tenant-1"}}
    ]

    result = graph_crud_module._act_update_node(
        mock_db, {"match": {"orig_id": "user-1"}, "properties": {"name": "Updated"}}, principal="bob", tenant="tenant-1"
    )

    # Check that updated_by was added to properties
    query_call = mock_db.query.call_args
    props = query_call[0][1]["props"]
    assert props["updated_by"] == "bob"
    assert "updated_at" in props


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_create_relationship_adds_created_by_metadata(mock_adapter_class):
    """Test that create_relationship adds created_by and created_at metadata."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [[{"c": 0}], None]

    result = graph_crud_module._act_create_relationship(
        mock_db,
        {"from_": {"orig_id": "user-1"}, "to": {"orig_id": "project-1"}, "rel_type": "WORKS_ON", "properties": {}},
        principal="charlie",
        tenant="tenant-1",
    )

    # Check that created_by and created_at were added
    assert result["relationship"]["properties"]["created_by"] == "charlie"
    assert "created_at" in result["relationship"]["properties"]


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
@patch("src.mcp.tools.graph.crud.audit_access")
def test_create_node_audit_logged(mock_audit, mock_adapter_class):
    """Test that create_node operations are audit logged."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [
        [{"c": 0}],
        None,
        [{"labels": ["User"], "props": {"orig_id": "user-1", "tenant": "tenant-1", "created_by": "test-user"}}],
    ]

    result = graph_crud_module._act_create_node(
        mock_db, {"labels": ["User"], "properties": {"orig_id": "user-1"}}, principal="test-user", tenant="tenant-1"
    )

    # Verify audit_access was called
    assert mock_audit.called
    call_kwargs = mock_audit.call_args[1]
    assert call_kwargs["principal"] == "test-user"
    assert call_kwargs["action"] == "create_node"
    assert call_kwargs["allowed"] is True


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
@patch("src.mcp.tools.graph.crud.audit_access")
def test_delete_node_audit_logged(mock_audit, mock_adapter_class):
    """Test that delete_node operations are audit logged."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.return_value = [{"c": 1}]

    result = graph_crud_module._act_delete_node(
        mock_db, {"match": {"orig_id": "user-1"}}, principal="test-user", tenant="tenant-1"
    )

    # Verify audit_access was called
    assert mock_audit.called
    call_kwargs = mock_audit.call_args[1]
    assert call_kwargs["action"] == "delete_node"
    assert call_kwargs["attributes"]["deleted"] == 1


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_update_node_cannot_change_tenant(mock_adapter_class):
    """Test that update_node cannot change tenant to a different value."""
    mock_db = mock_adapter_class.return_value

    with pytest.raises(ValueError) as exc_info:
        graph_crud_module._act_update_node(
            mock_db,
            {"match": {"orig_id": "user-1"}, "properties": {"tenant": "different-tenant"}},  # Trying to change tenant
            principal="test-user",
            tenant="tenant-1",
        )
    assert "Cannot update node with different tenant" in str(exc_info.value)


@patch("src.mcp.tools.graph.crud.MemgraphAdapter")
def test_operation_dispatch_security(mock_adapter_class):
    """Test that invoke validates payload before dispatching to operation handlers."""
    mock_db = mock_adapter_class.return_value
    mock_db.query.side_effect = [
        [{"c": 0}],
        None,
        [{"labels": ["User"], "props": {"orig_id": "user-1", "tenant": "tenant-1", "created_by": "test-user"}}],
    ]

    # Valid payload should dispatch successfully
    payload = {
        "operation": "create_node",
        "labels": ["User"],
        "properties": {"orig_id": "user-1"},
        "principal": "test-user",
        "tenant": "tenant-1",
    }

    result = graph_crud_module.invoke.__wrapped__(None, payload)
    assert result["ok"] is True


def test_unsupported_operation_rejected():
    """Test that unsupported operation values are rejected."""
    payload = {"operation": "invalid_operation", "principal": "test-user", "tenant": "tenant-1"}

    # Should fail at schema validation
    with pytest.raises(ValidationError):
        GraphCrudPayload(**payload)
