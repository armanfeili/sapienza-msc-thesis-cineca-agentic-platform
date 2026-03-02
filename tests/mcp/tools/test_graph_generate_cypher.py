"""
Integration tests for graph.generate_cypher tool with P0 runtime infrastructure.

Tests cover:
- Pydantic schema validation
- All 8 actions (select, insert_node, update_node, delete_node, upsert_rel, match_rel, count_by_label, schema_inventory)
- RBAC enforcement (requires principal/tenant)
- Parameterization and injection safety
- Read-only vs write classification
"""

import pytest
from pydantic import ValidationError

# Tool under test
from src.mcp.tools.graph import generate_cypher as generate_cypher_module

# Schema
from src.mcp.schemas import GraphGenerateCypherPayload


# ─────────────────────────────────────────────────────────────────────────────
# Schema Validation Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_schema_validation_select():
    """Test SELECT action schema validation."""
    payload = GraphGenerateCypherPayload(
        action="select",
        label="User",
        where={"email": "test@example.com"},
        **{"return": ["name", "email"]},
        limit=10,
    )
    assert payload.action == "select"
    assert payload.label == "User"
    assert payload.limit == 10


def test_schema_validation_insert_node_merge():
    """Test INSERT_NODE action with merge mode."""
    payload = GraphGenerateCypherPayload(
        action="insert_node",
        labels=["User", "Person"],
        orig_id="user-123",
        props={"name": "Alice"},
        mode="merge",
    )
    assert payload.action == "insert_node"
    assert payload.labels == ["User", "Person"]
    assert payload.mode == "merge"


def test_schema_validation_insert_node_requires_labels():
    """Test that INSERT_NODE requires non-empty labels."""
    with pytest.raises(ValidationError) as exc:
        GraphGenerateCypherPayload(
            action="insert_node",
            labels=[],  # Empty list should fail
            props={"name": "Alice"},
        )
    assert "labels" in str(exc.value).lower()


def test_schema_validation_update_node_requires_orig_id():
    """Test that UPDATE_NODE requires orig_id."""
    with pytest.raises(ValidationError) as exc:
        GraphGenerateCypherPayload(
            action="update_node",
            props={"email": "new@example.com"},
            # Missing orig_id
        )
    assert "orig_id" in str(exc.value).lower()


def test_schema_validation_delete_node_requires_orig_id():
    """Test that DELETE_NODE requires orig_id."""
    with pytest.raises(ValidationError) as exc:
        GraphGenerateCypherPayload(
            action="delete_node",
            detach=True,
            # Missing orig_id
        )
    assert "orig_id" in str(exc.value).lower()


def test_schema_validation_upsert_rel_requires_fields():
    """Test that UPSERT_REL requires start_orig_id, end_orig_id, and type."""
    with pytest.raises(ValidationError) as exc:
        GraphGenerateCypherPayload(
            action="upsert_rel",
            start_orig_id="user-1",
            end_orig_id="task-1",
            # Missing type
        )
    assert "type" in str(exc.value).lower()


def test_schema_validation_match_rel():
    """Test MATCH_REL action schema."""
    payload = GraphGenerateCypherPayload(
        action="match_rel",
        **{"type": "RUNS"},
        from_label="User",
        to_label="Task",
        limit=50,
    )
    assert payload.action == "match_rel"
    assert payload.from_label == "User"
    assert payload.to_label == "Task"


def test_schema_validation_count_by_label():
    """Test COUNT_BY_LABEL action (no additional fields required)."""
    payload = GraphGenerateCypherPayload(action="count_by_label")
    assert payload.action == "count_by_label"


def test_schema_validation_schema_inventory():
    """Test SCHEMA_INVENTORY action (no additional fields required)."""
    payload = GraphGenerateCypherPayload(action="schema_inventory")
    assert payload.action == "schema_inventory"


# ─────────────────────────────────────────────────────────────────────────────
# Functional Tests - SELECT
# ─────────────────────────────────────────────────────────────────────────────


def test_select_basic():
    """Test SELECT generates correct Cypher."""
    payload = {
        "action": "select",
        "label": "User",
        "limit": 10,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "select"
    assert result["read_only"] is True
    assert "MATCH (n:`User`)" in result["cypher"]
    assert "LIMIT $limit" in result["cypher"]
    assert result["params"]["limit"] == 10


def test_select_with_where():
    """Test SELECT with WHERE clause."""
    payload = {
        "action": "select",
        "label": "User",
        "where": {"email": "test@example.com", "status": "active"},
        "limit": 5,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert "WHERE" in result["cypher"]
    assert "n.`email` = $n_w_0" in result["cypher"]
    assert "n.`status` = $n_w_1" in result["cypher"]
    assert result["params"]["n_w_0"] == "test@example.com"
    assert result["params"]["n_w_1"] == "active"


def test_select_with_return():
    """Test SELECT with custom RETURN fields."""
    payload = {
        "action": "select",
        "label": "User",
        "return": ["name", "email"],
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert "RETURN n.`name` AS name, n.`email` AS email" in result["cypher"]


# ─────────────────────────────────────────────────────────────────────────────
# Functional Tests - INSERT_NODE
# ─────────────────────────────────────────────────────────────────────────────


def test_insert_node_merge_with_orig_id():
    """Test INSERT_NODE with MERGE mode and orig_id."""
    payload = {
        "action": "insert_node",
        "labels": ["User"],
        "orig_id": "user-123",
        "props": {"name": "Alice", "email": "alice@example.com"},
        "mode": "merge",
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "insert_node"
    assert result["read_only"] is False
    assert "MERGE (n:`User` {orig_id:$orig_id})" in result["cypher"]
    assert "SET n += $props" in result["cypher"]
    assert result["params"]["orig_id"] == "user-123"
    assert result["params"]["props"]["name"] == "Alice"


def test_insert_node_create_mode():
    """Test INSERT_NODE with CREATE mode."""
    payload = {
        "action": "insert_node",
        "labels": ["Task"],
        "orig_id": "task-456",
        "props": {"title": "Test Task"},
        "mode": "create",
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert "CREATE (n:`Task` {orig_id:$orig_id})" in result["cypher"]


def test_insert_node_without_orig_id():
    """Test INSERT_NODE without orig_id falls back to CREATE."""
    payload = {
        "action": "insert_node",
        "labels": ["User"],
        "props": {"name": "Bob"},
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert "CREATE (n:`User`)" in result["cypher"]
    assert "SET n = $props" in result["cypher"]


def test_insert_node_multiple_labels():
    """Test INSERT_NODE with multiple labels."""
    payload = {
        "action": "insert_node",
        "labels": ["User", "Admin", "Developer"],
        "orig_id": "user-789",
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert "`User`:`Admin`:`Developer`" in result["cypher"]


# ─────────────────────────────────────────────────────────────────────────────
# Functional Tests - UPDATE_NODE
# ─────────────────────────────────────────────────────────────────────────────


def test_update_node():
    """Test UPDATE_NODE generates correct Cypher."""
    payload = {
        "action": "update_node",
        "orig_id": "user-123",
        "props": {"email": "newemail@example.com", "updated_at": "2025-01-24"},
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "update_node"
    assert result["read_only"] is False
    assert "MATCH (n {orig_id:$id})" in result["cypher"]
    assert "SET n += $props" in result["cypher"]
    assert result["params"]["id"] == "user-123"
    assert result["params"]["props"]["email"] == "newemail@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# Functional Tests - DELETE_NODE
# ─────────────────────────────────────────────────────────────────────────────


def test_delete_node_with_detach():
    """Test DELETE_NODE with DETACH (default)."""
    payload = {
        "action": "delete_node",
        "orig_id": "user-123",
        "detach": True,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "delete_node"
    assert result["read_only"] is False
    assert "DETACH DELETE n" in result["cypher"]
    assert result["params"]["id"] == "user-123"


def test_delete_node_without_detach():
    """Test DELETE_NODE without DETACH."""
    payload = {
        "action": "delete_node",
        "orig_id": "user-123",
        "detach": False,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert "DELETE n" in result["cypher"]
    assert "DETACH" not in result["cypher"]


# ─────────────────────────────────────────────────────────────────────────────
# Functional Tests - UPSERT_REL
# ─────────────────────────────────────────────────────────────────────────────


def test_upsert_rel():
    """Test UPSERT_REL generates correct Cypher."""
    payload = {
        "action": "upsert_rel",
        "start_orig_id": "user-123",
        "end_orig_id": "task-456",
        "type": "ASSIGNED_TO",
        "props": {"since": "2025-01-24", "role": "owner"},
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "upsert_rel"
    assert result["read_only"] is False
    assert "MATCH (x {orig_id:$a}), (y {orig_id:$b})" in result["cypher"]
    assert "MERGE (x)-[r:`ASSIGNED_TO`]->(y)" in result["cypher"]
    assert "SET r += $props" in result["cypher"]
    assert result["params"]["a"] == "user-123"
    assert result["params"]["b"] == "task-456"
    assert result["params"]["props"]["since"] == "2025-01-24"


# ─────────────────────────────────────────────────────────────────────────────
# Functional Tests - MATCH_REL
# ─────────────────────────────────────────────────────────────────────────────


def test_match_rel_basic():
    """Test MATCH_REL with type only."""
    payload = {
        "action": "match_rel",
        "type": "RUNS",
        "limit": 100,
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "match_rel"
    assert result["read_only"] is True
    assert "MATCH (a)-[r:`RUNS`]->(b)" in result["cypher"]
    assert "LIMIT $limit" in result["cypher"]
    assert result["params"]["limit"] == 100


def test_match_rel_with_labels():
    """Test MATCH_REL with from_label and to_label."""
    payload = {
        "action": "match_rel",
        "type": "KNOWS",
        "from_label": "User",
        "to_label": "User",
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert "MATCH (a:`User`)-[r:`KNOWS`]->(b:`User`)" in result["cypher"]


def test_match_rel_with_where():
    """Test MATCH_REL with WHERE conditions on both sides."""
    payload = {
        "action": "match_rel",
        "type": "FRIENDS_WITH",
        "from_where": {"status": "active"},
        "to_where": {"verified": True},
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert "WHERE" in result["cypher"]
    assert "a.`status` = $a_w_0" in result["cypher"]
    assert "b.`verified` = $b_w_0" in result["cypher"]


# ─────────────────────────────────────────────────────────────────────────────
# Functional Tests - COUNT_BY_LABEL
# ─────────────────────────────────────────────────────────────────────────────


def test_count_by_label():
    """Test COUNT_BY_LABEL generates aggregation query."""
    payload = {
        "action": "count_by_label",
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "count_by_label"
    assert result["read_only"] is True
    assert "MATCH (n)" in result["cypher"]
    assert "UNWIND labels(n) AS lbl" in result["cypher"]
    assert "count(*) AS count" in result["cypher"]
    assert result["params"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# Functional Tests - SCHEMA_INVENTORY
# ─────────────────────────────────────────────────────────────────────────────


def test_schema_inventory():
    """Test SCHEMA_INVENTORY generates portable schema query."""
    payload = {
        "action": "schema_inventory",
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert result["action"] == "schema_inventory"
    assert result["read_only"] is True
    assert "CALL {" in result["cypher"]
    assert "UNION ALL" in result["cypher"]
    assert "elementType" in result["cypher"]
    assert result["params"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# Security Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_parameterization_prevents_injection():
    """Test that all values are parameterized, not interpolated."""
    payload = {
        "action": "select",
        "label": "User",
        "where": {"email": "'; DROP TABLE users; --"},
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    # Malicious input should be in params, not in Cypher string
    assert result["ok"] is True
    assert "DROP TABLE" not in result["cypher"]
    assert "'; DROP TABLE users; --" in str(result["params"].values())


def test_label_escaping():
    """Test that labels with backticks are escaped."""
    payload = {
        "action": "insert_node",
        "labels": ["User`Evil"],
        "orig_id": "test",
        "principal": "test_user",
        "tenant": "test_tenant",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    # Backticks should be doubled for escaping
    assert "``" in result["cypher"]


def test_read_only_classification():
    """Test that read vs write operations are correctly classified."""
    read_actions = [
        {"action": "select", "label": "User"},
        {"action": "match_rel", "type": "KNOWS"},
        {"action": "count_by_label"},
        {"action": "schema_inventory"},
    ]

    write_actions = [
        {"action": "insert_node", "labels": ["User"], "orig_id": "1"},
        {"action": "update_node", "orig_id": "1", "props": {}},
        {"action": "delete_node", "orig_id": "1"},
        {"action": "upsert_rel", "start_orig_id": "1", "end_orig_id": "2", "type": "KNOWS"},
    ]

    for payload in read_actions:
        payload.update({"principal": "test_user", "tenant": "test_tenant"})
        result = generate_cypher_module.invoke(payload)
        assert result["read_only"] is True, f"Expected {payload['action']} to be read-only"

    for payload in write_actions:
        payload.update({"principal": "test_user", "tenant": "test_tenant"})
        result = generate_cypher_module.invoke(payload)
        assert result["read_only"] is False, f"Expected {payload['action']} to be write"


# ─────────────────────────────────────────────────────────────────────────────
# RBAC Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_requires_principal():
    """Test that tool requires principal for RBAC."""
    payload = {
        "action": "select",
        "label": "User",
        # Missing principal and tenant
    }

    result = generate_cypher_module.invoke(payload)

    # Decorator should block requests without principal
    assert result["ok"] is False
    assert result["code"] == "E_PERMISSION"
    assert "principal" in result["message"].lower()


def test_with_authentication_context():
    """Test that tool works with proper authentication."""
    payload = {
        "action": "select",
        "label": "User",
        "principal": "admin_user",
        "tenant": "org_123",
    }

    result = generate_cypher_module.invoke(payload)

    assert result["ok"] is True
    assert "MATCH" in result["cypher"]
