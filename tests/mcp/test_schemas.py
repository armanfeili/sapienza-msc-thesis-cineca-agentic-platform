"""
Tests for MCP tool payload schemas.

Verifies that all Pydantic schemas:
- Accept valid payloads
- Reject invalid payloads with clear errors
- Apply defaults correctly
- Enforce cross-field validation
"""

import pytest
from pydantic import ValidationError

from src.mcp.schemas import (
    GraphQueryPayload,
    GraphSecureQueryPayload,
    GraphCrudPayload,
    SystemHealthPayload,
    DataArchivePayload,
    SecurityAuditPayload,
    ModelManagePayload,
    GraphQueryAction,
    GraphSecureQueryAction,
    get_schema,
)


# ─────────────────────────────────────────────────────────────────────────────
# graph.query tests
# ─────────────────────────────────────────────────────────────────────────────


def test_graph_query_minimal():
    """Minimal valid payload for graph.query."""
    payload = GraphQueryPayload(cypher="MATCH (n) RETURN n LIMIT 10")
    assert payload.action == GraphQueryAction.run
    assert payload.cypher == "MATCH (n) RETURN n LIMIT 10"
    assert payload.params == {}
    assert payload.read_only is True
    assert payload.timeout_ms == 5000


def test_graph_query_full():
    """Full payload with all fields."""
    payload = GraphQueryPayload(
        action="explain",
        cypher="MATCH (u:User {id: $uid}) RETURN u",
        params={"uid": "u123"},
        read_only=False,
        timeout_ms=10000,
        limit=500,
        principal="p123",
        tenant="t456",
        trace_id="trace789",
    )
    assert payload.action == GraphQueryAction.explain
    assert payload.params == {"uid": "u123"}
    assert payload.read_only is False
    assert payload.limit == 500


def test_graph_query_alias_and_principal_dict():
    """graph.query accepts legacy 'query' key and dict principal payloads."""
    payload = GraphQueryPayload(
        query="MATCH (b:Blast) RETURN b",
        principal={"id": "auth0|123", "tenant_id": "tenant"},
        tenant="tenant",
    )
    assert payload.cypher == "MATCH (b:Blast) RETURN b"
    assert isinstance(payload.principal, dict)


def test_graph_query_empty_cypher_rejected():
    """Empty cypher should fail validation."""
    with pytest.raises(ValidationError) as exc:
        GraphQueryPayload(cypher="")
    assert "string_too_short" in str(exc.value) or "at least 1" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────────────
# graph.secure_query tests
# ─────────────────────────────────────────────────────────────────────────────


def test_secure_query_ask_action():
    """Test ask action with natural language prompt."""
    payload = GraphSecureQueryPayload(
        action="ask",
        prompt="Who are the active users?",
        principal="p123",
        tenant="t456",
    )
    assert payload.action == GraphSecureQueryAction.ask
    assert payload.prompt == "Who are the active users?"
    assert payload.max_rows == 1000
    assert payload.timeout_ms == 5000
    assert payload.return_format == "rows"


def test_secure_query_execute_action():
    """Test execute action with Cypher query."""
    payload = GraphSecureQueryPayload(
        action="execute",
        cypher="MATCH (u:User) RETURN u.name",
        params={},
        principal="p123",
        tenant="t456",
        max_rows=500,
        return_format="json",
    )
    assert payload.action == GraphSecureQueryAction.execute
    assert payload.cypher == "MATCH (u:User) RETURN u.name"
    assert payload.max_rows == 500
    assert payload.return_format == "json"


def test_secure_query_missing_prompt_for_ask():
    """Ask action requires prompt."""
    # Validators run correctly and reject None prompt for ask action
    with pytest.raises(ValidationError) as exc:
        GraphSecureQueryPayload(
            action="ask",
            prompt=None,  # Explicitly None to trigger validator
            principal="p123",
            tenant="t456",
        )
    assert "prompt" in str(exc.value).lower() and "required" in str(exc.value).lower()


def test_secure_query_missing_cypher_for_execute():
    """Execute action requires cypher."""
    # Validators run correctly and reject None cypher for execute action
    with pytest.raises(ValidationError) as exc:
        GraphSecureQueryPayload(
            action="execute",
            cypher=None,  # Explicitly None
            principal="p123",
            tenant="t456",
        )
    assert "cypher" in str(exc.value).lower() and "required" in str(exc.value).lower()


def test_secure_query_missing_principal():
    """Principal is required for all actions."""
    with pytest.raises(ValidationError) as exc:
        GraphSecureQueryPayload(
            action="ask",
            prompt="test",
            tenant="t456",
        )
    assert "principal" in str(exc.value).lower()


def test_secure_query_missing_tenant():
    """Tenant is required for all actions."""
    with pytest.raises(ValidationError) as exc:
        GraphSecureQueryPayload(
            action="ask",
            prompt="test",
            principal="p123",
        )
    assert "tenant" in str(exc.value).lower()


def test_secure_query_invalid_return_format():
    """Return format must be one of: rows, markdown, csv, json."""
    with pytest.raises(ValidationError) as exc:
        GraphSecureQueryPayload(
            action="ask",
            prompt="test",
            principal="p123",
            tenant="t456",
            return_format="xml",
        )
    assert "return_format" in str(exc.value).lower()


def test_secure_query_max_rows_bounds():
    """Max rows must be between 1 and 10000."""
    # Too small
    with pytest.raises(ValidationError):
        GraphSecureQueryPayload(
            action="ask",
            prompt="test",
            principal="p123",
            tenant="t456",
            max_rows=0,
        )

    # Too large
    with pytest.raises(ValidationError):
        GraphSecureQueryPayload(
            action="ask",
            prompt="test",
            principal="p123",
            tenant="t456",
            max_rows=20000,
        )

    # Valid extremes
    GraphSecureQueryPayload(
        action="ask",
        prompt="test",
        principal="p123",
        tenant="t456",
        max_rows=1,
    )

    GraphSecureQueryPayload(
        action="ask",
        prompt="test",
        principal="p123",
        tenant="t456",
        max_rows=10000,
    )


# ─────────────────────────────────────────────────────────────────────────────
# graph.crud tests
# ─────────────────────────────────────────────────────────────────────────────


def test_graph_crud_create_node():
    """Test create_node operation."""
    payload = GraphCrudPayload(
        operation="create_node",
        label="User",
        properties={"id": "u123", "name": "Alice"},
        principal="p123",
        tenant="t456",
    )
    assert payload.operation == "create_node"  # use_enum_values=True converts to string
    assert payload.label == "User"
    assert payload.properties["name"] == "Alice"


def test_graph_crud_from_field_alias():
    """Test 'from' field with alias."""
    payload = GraphCrudPayload(
        operation="create_relationship",
        **{"from": {"id": "u123"}, "to": {"id": "i456"}, "rel_type": "AFFILIATED_WITH"},
        principal="p123",
        tenant="t456",
    )
    assert payload.from_ == {"id": "u123"}
    assert payload.to == {"id": "i456"}
    assert payload.rel_type == "AFFILIATED_WITH"


# ─────────────────────────────────────────────────────────────────────────────
# system.health tests
# ─────────────────────────────────────────────────────────────────────────────


def test_system_health_defaults():
    """Test default values."""
    payload = SystemHealthPayload()
    assert payload.action == "liveness"  # use_enum_values=True converts to string
    assert payload.verbose is False


def test_system_health_readiness():
    """Test readiness action."""
    payload = SystemHealthPayload(action="readiness", verbose=True)
    assert payload.action == "readiness"  # use_enum_values=True converts to string
    assert payload.verbose is True


# ─────────────────────────────────────────────────────────────────────────────
# data.archive tests
# ─────────────────────────────────────────────────────────────────────────────


def test_data_archive_mark():
    """Test mark action."""
    payload = DataArchivePayload(
        action="mark",
        node_ids=["n1", "n2", "n3"],
        principal="p123",
        tenant="t456",
    )
    assert payload.action == "mark"  # use_enum_values=True converts to string
    assert len(payload.node_ids) == 3


def test_data_archive_purge_requires_confirm():
    """Purge action requires confirm=true."""
    # Field validators run during validation but don't block instantiation
    # if confirm is not explicitly set
    with pytest.raises(ValidationError) as exc:
        DataArchivePayload(
            action="purge",
            node_ids=["n1"],
            confirm=False,  # Explicitly set to False
            principal="p123",
            tenant="t456",
        )
    assert "confirm" in str(exc.value).lower()

    # Should succeed with confirm=true
    payload = DataArchivePayload(
        action="purge",
        node_ids=["n1"],
        confirm=True,
        principal="p123",
        tenant="t456",
    )
    assert payload.confirm is True


# ─────────────────────────────────────────────────────────────────────────────
# security.audit tests
# ─────────────────────────────────────────────────────────────────────────────


def test_security_audit_access():
    """Test access event logging."""
    payload = SecurityAuditPayload(
        action="access",
        category="authentication",
        event_action="login",
        outcome="success",
        resource="user:u123",
        principal="p123",
        tenant="t456",
    )
    assert payload.action == "access"  # use_enum_values=True converts to string
    assert payload.category == "authentication"


def test_security_audit_clear_requires_confirm():
    """Clear action requires confirm=true."""
    # Field validators run during validation
    with pytest.raises(ValidationError) as exc:
        SecurityAuditPayload(
            action="clear",
            confirm=False,  # Explicitly set to False
            principal="p123",
            tenant="t456",
        )
    assert "confirm" in str(exc.value).lower()


def test_security_audit_list_defaults():
    """List action has default limit."""
    payload = SecurityAuditPayload(
        action="list",
        principal="p123",
        tenant="t456",
    )
    assert payload.limit == 100


# ─────────────────────────────────────────────────────────────────────────────
# model.manage tests
# ─────────────────────────────────────────────────────────────────────────────


def test_model_manage_info():
    """Test info action."""
    payload = ModelManagePayload(action="info")
    assert payload.action == "info"  # use_enum_values=True converts to string


def test_model_manage_set_config():
    """Test config update with validation."""
    payload = ModelManagePayload(
        action="set_config",
        model="gpt-4",
        temperature=0.7,
        max_tokens=4096,
    )
    assert payload.model == "gpt-4"
    assert payload.temperature == 0.7
    assert payload.max_tokens == 4096


def test_model_manage_temperature_bounds():
    """Temperature must be 0.0-2.0."""
    with pytest.raises(ValidationError):
        ModelManagePayload(action="set_config", temperature=-0.1)

    with pytest.raises(ValidationError):
        ModelManagePayload(action="set_config", temperature=2.5)

    # Valid extremes
    ModelManagePayload(action="set_config", temperature=0.0)
    ModelManagePayload(action="set_config", temperature=2.0)


# ─────────────────────────────────────────────────────────────────────────────
# Schema registry tests
# ─────────────────────────────────────────────────────────────────────────────


def test_get_schema_registry():
    """Test schema lookup by tool name."""
    assert get_schema("graph.query") == GraphQueryPayload
    assert get_schema("graph.secure_query") == GraphSecureQueryPayload
    assert get_schema("graph.crud") == GraphCrudPayload
    assert get_schema("system.health") == SystemHealthPayload
    assert get_schema("data.archive") == DataArchivePayload
    assert get_schema("security.audit") == SecurityAuditPayload
    assert get_schema("model.manage") == ModelManagePayload
    assert get_schema("nonexistent.tool") is None


def test_schema_round_trip():
    """Test serialize → parse round-trip."""
    original = GraphSecureQueryPayload(
        action="ask",
        prompt="List all users",
        principal="p123",
        tenant="t456",
        max_rows=500,
        return_format="markdown",
    )

    # Serialize to dict (use model_dump in Pydantic v2)
    data = original.model_dump()

    # Reconstruct from dict
    reconstructed = GraphSecureQueryPayload(**data)

    assert reconstructed.action == original.action
    assert reconstructed.prompt == original.prompt
    assert reconstructed.max_rows == original.max_rows
    assert reconstructed.return_format == original.return_format
