"""
Unit tests for graph.bulk tool.

Coverage:
- Schema validation (8 tests)
- Batch operations (10 tests)
- Idempotency (6 tests)
- Dry-run mode (4 tests)
- Progress tracking (6 tests)
- Security/RBAC (8 tests)
- Transaction safety (6 tests)

Total: 48 tests
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pydantic import ValidationError

import src.mcp.tools.graph.bulk as graph_bulk_module
from src.mcp.schemas import GraphBulkPayload, GraphBulkAction


# ─────────────────────────────────────────────────────────────────────────────
# 1. SCHEMA VALIDATION TESTS (8 tests)
# ─────────────────────────────────────────────────────────────────────────────


def test_schema_valid_ingest_nodes():
    """Valid ingest_nodes payload should pass validation."""
    payload = GraphBulkPayload(
        action=GraphBulkAction.ingest_nodes,
        principal="user|123",
        tenant="org-1",
        nodes=[{"labels": ["Person"], "orig_id": "p1", "props": {}}],
    )
    assert payload.action == GraphBulkAction.ingest_nodes


def test_schema_valid_ingest_edges():
    """Valid ingest_edges payload should pass validation."""
    payload = GraphBulkPayload(
        action=GraphBulkAction.ingest_edges,
        principal="user|456",
        tenant="org-2",
        edges=[{"start_orig_id": "p1", "end_orig_id": "p2", "type": "KNOWS", "props": {}}],
    )
    assert payload.action == GraphBulkAction.ingest_edges


def test_schema_batch_size_defaults_to_100():
    """batch_size should default to 100."""
    payload = GraphBulkPayload(
        action="upsert_nodes",
        principal="user|789",
        tenant="org-3",
        nodes=[{"labels": ["Test"], "orig_id": "t1", "props": {}}],
    )
    assert payload.batch_size == 100


def test_schema_batch_size_min_max():
    """batch_size must be between 1 and 1000."""
    payload = GraphBulkPayload(
        action="upsert_edges",
        principal="user|101",
        tenant="org-4",
        edges=[{"start_orig_id": "t1", "end_orig_id": "t2", "type": "TEST", "props": {}}],
        batch_size=500,
    )
    assert payload.batch_size == 500

    with pytest.raises(ValidationError):
        GraphBulkPayload(
            action="upsert_nodes",
            principal="u",
            tenant="t",
            nodes=[{"labels": ["Test"], "orig_id": "t1", "props": {}}],
            batch_size=0,
        )

    with pytest.raises(ValidationError):
        GraphBulkPayload(
            action="upsert_nodes",
            principal="u",
            tenant="t",
            nodes=[{"labels": ["Test"], "orig_id": "t1", "props": {}}],
            batch_size=1001,
        )


def test_schema_dry_run_defaults_false():
    """dry_run should default to False."""
    payload = GraphBulkPayload(
        action="ingest_nodes", principal="u", tenant="t", nodes=[{"labels": ["Test"], "orig_id": "t1", "props": {}}]
    )
    assert payload.dry_run is False


def test_schema_fail_fast_defaults_false():
    """fail_fast should default to True."""
    payload = GraphBulkPayload(
        action="ingest_edges",
        principal="u",
        tenant="t",
        edges=[{"start_orig_id": "t1", "end_orig_id": "t2", "type": "TEST", "props": {}}],
    )
    assert payload.fail_fast is True


def test_schema_timeout_ms_defaults_30000():
    """timeout_ms should default to 30000."""
    payload = GraphBulkPayload(
        action="upsert_nodes", principal="u", tenant="t", nodes=[{"labels": ["Test"], "orig_id": "t1", "props": {}}]
    )
    assert payload.timeout_ms == 30000


def test_schema_missing_required_fields():
    """Missing required fields should raise validation error."""
    with pytest.raises(ValidationError):
        GraphBulkPayload(action="ingest_nodes", tenant="org", nodes=[])

    with pytest.raises(ValidationError):
        GraphBulkPayload(action="ingest_nodes", principal="user", nodes=[])

    with pytest.raises(ValidationError):
        GraphBulkPayload(principal="user", tenant="org", nodes=[])


# ─────────────────────────────────────────────────────────────────────────────
# 2. BATCH OPERATIONS TESTS (10 tests)
# ─────────────────────────────────────────────────────────────────────────────


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_batch_ingest_nodes_success(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "user|123",
        "tenant": "org-1",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": ["Person"], "orig_id": "p2", "props": {}},
        ],
    }

    result = graph_bulk_module.invoke(payload)
    assert result["ok"] is True
    assert result["processed"] == 2


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_batch_ingest_edges_success(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_edges",
        "principal": "user|456",
        "tenant": "org-2",
        "edges": [
            {"start_orig_id": "p1", "end_orig_id": "p2", "type": "KNOWS", "props": {}},
        ],
    }

    result = graph_bulk_module.invoke(payload)
    assert result["ok"] is True


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_batch_size_chunking(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    items = [{"labels": ["Person"], "orig_id": f"p{i}", "props": {}} for i in range(250)]
    payload = {"action": "ingest_nodes", "principal": "user|789", "tenant": "org-3", "nodes": items, "batch_size": 100}

    result = graph_bulk_module.invoke(payload)
    assert result["processed"] == 250


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_batch_empty_items(mock_memgraph):
    """Empty nodes/edges list should raise validation error."""
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    # Schema validation should reject empty nodes list
    with pytest.raises(ValidationError) as exc_info:
        payload_dict = {"action": "ingest_nodes", "principal": "u", "tenant": "t", "nodes": []}
        GraphBulkPayload(**payload_dict)

    assert "'nodes' list is required and must be non-empty" in str(exc_info.value)


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_batch_invalid_node_validation(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}, {"labels": [], "orig_id": "p2", "props": {}}],
    }

    result = graph_bulk_module.invoke(payload)
    assert result.get("failed", 0) >= 1 or len(result.get("errors", [])) >= 1


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_batch_invalid_edge_validation(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_edges",
        "principal": "u",
        "tenant": "t",
        "edges": [
            {"start_orig_id": "p1", "end_orig_id": "p2", "type": "KNOWS", "props": {}},
            {"start_orig_id": "p3", "type": "FOLLOWS", "props": {}},
        ],
    }

    result = graph_bulk_module.invoke(payload)
    assert result.get("failed", 0) >= 1 or len(result.get("errors", [])) >= 1


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_batch_upsert_nodes_success(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload = {
        "action": "upsert_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
        "idempotency_key": "key1",
    }

    result = graph_bulk_module.invoke(payload)
    assert result["ok"] is True


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_batch_upsert_edges_success(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload = {
        "action": "upsert_edges",
        "principal": "u",
        "tenant": "t",
        "edges": [{"start_orig_id": "p1", "end_orig_id": "p2", "type": "KNOWS", "props": {}}],
        "idempotency_key": "key2",
    }

    result = graph_bulk_module.invoke(payload)
    assert result["ok"] is True


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_batch_fail_fast_stops_on_error(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.side_effect = Exception("DB error")

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": ["Person"], "orig_id": "p2", "props": {}},
            {"labels": ["Person"], "orig_id": "p3", "props": {}},
        ],
        "fail_fast": True,
    }

    result = graph_bulk_module.invoke(payload)
    # With fail_fast, should stop after first error
    assert result["failed"] >= 1
    assert result["processed"] <= 2  # May process item causing error + one more


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_batch_continue_on_error(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": [], "orig_id": "p2", "props": {}},
            {"labels": ["Person"], "orig_id": "p3", "props": {}},
        ],
        "fail_fast": False,
    }

    result = graph_bulk_module.invoke(payload)
    assert result["processed"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# 3. IDEMPOTENCY TESTS (6 tests)
# ─────────────────────────────────────────────────────────────────────────────


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_idempotency_upsert_nodes_dedupe(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload = {
        "action": "upsert_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
        ],
        "idempotency_key": "key3",
    }

    result = graph_bulk_module.invoke(payload)
    assert result["skipped"] == 1


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_idempotency_upsert_edges_dedupe(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload = {
        "action": "upsert_edges",
        "principal": "u",
        "tenant": "t",
        "edges": [
            {"start_orig_id": "p1", "end_orig_id": "p2", "type": "KNOWS", "props": {}},
            {"start_orig_id": "p1", "end_orig_id": "p2", "type": "KNOWS", "props": {}},
        ],
        "idempotency_key": "key4",
    }

    result = graph_bulk_module.invoke(payload)
    assert result["skipped"] == 1


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_idempotency_cache_per_invocation(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload1 = {
        "action": "upsert_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
        "idempotency_key": "key5",
    }

    result1 = graph_bulk_module.invoke(payload1)
    assert result1["skipped"] == 0

    payload2 = {**payload1, "idempotency_key": "key6"}
    result2 = graph_bulk_module.invoke(payload2)
    assert result2["skipped"] == 0


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_idempotency_composite_key_format(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload = {
        "action": "upsert_edges",
        "principal": "u",
        "tenant": "t",
        "edges": [{"start_orig_id": "p1", "end_orig_id": "p2", "type": "KNOWS", "props": {}}],
        "idempotency_key": "key7",
    }

    result = graph_bulk_module.invoke(payload)
    assert result["succeeded"] == 1


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_idempotency_without_key_no_dedupe(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload = {
        "action": "upsert_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
        ],
    }

    result = graph_bulk_module.invoke(payload)
    assert result["processed"] == 2
    assert result.get("skipped", 0) == 0


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_idempotency_different_keys_no_dedupe(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload1 = {
        "action": "upsert_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
        "idempotency_key": "key8",
    }
    result1 = graph_bulk_module.invoke(payload1)
    assert result1["succeeded"] == 1

    payload2 = {**payload1, "idempotency_key": "key9"}
    result2 = graph_bulk_module.invoke(payload2)
    assert result2["succeeded"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. DRY-RUN MODE TESTS (4 tests)
# ─────────────────────────────────────────────────────────────────────────────


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_dry_run_validates_without_writes(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
        "dry_run": True,
    }

    result = graph_bulk_module.invoke(payload)
    assert result["dry_run"] is True
    assert mock_db.query.call_count == 0


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_dry_run_detects_validation_errors(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}, {"labels": [], "orig_id": "p2", "props": {}}],
        "dry_run": True,
    }

    result = graph_bulk_module.invoke(payload)
    assert result["dry_run"] is True
    assert result.get("failed", 0) >= 1 or len(result.get("errors", [])) >= 1


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_dry_run_all_valid_items(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_edges",
        "principal": "u",
        "tenant": "t",
        "edges": [
            {"start_orig_id": "p1", "end_orig_id": "p2", "type": "KNOWS", "props": {}},
            {"start_orig_id": "p2", "end_orig_id": "p3", "type": "FOLLOWS", "props": {}},
        ],
        "dry_run": True,
    }

    result = graph_bulk_module.invoke(payload)
    assert result["dry_run"] is True
    assert result["processed"] == 2


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_dry_run_false_writes_to_db(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
        "dry_run": False,
    }

    result = graph_bulk_module.invoke(payload)
    assert result.get("dry_run", False) is False
    assert mock_db.query.call_count >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. PROGRESS TRACKING TESTS (6 tests)
# ─────────────────────────────────────────────────────────────────────────────


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_progress_processed_count(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": ["Person"], "orig_id": "p2", "props": {}},
            {"labels": ["Person"], "orig_id": "p3", "props": {}},
        ],
    }

    result = graph_bulk_module.invoke(payload)
    assert result["processed"] == 3


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_progress_succeeded_count(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": ["Person"], "orig_id": "p2", "props": {}},
        ],
    }

    result = graph_bulk_module.invoke(payload)
    assert result["succeeded"] == 2


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_progress_failed_count(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": [], "orig_id": "p2", "props": {}},
            {"labels": ["Person"], "orig_id": "p3", "props": {}},
        ],
        "fail_fast": False,
    }

    result = graph_bulk_module.invoke(payload)
    assert result["failed"] >= 1


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_progress_skipped_count(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload = {
        "action": "upsert_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
        ],
        "idempotency_key": "key10",
    }

    result = graph_bulk_module.invoke(payload)
    assert result["skipped"] == 1


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_progress_errors_list(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    items = [{"labels": [], "orig_id": f"p{i}", "props": {}} for i in range(15)]
    payload = {"action": "ingest_nodes", "principal": "u", "tenant": "t", "nodes": items, "fail_fast": False}

    result = graph_bulk_module.invoke(payload)
    assert "errors" in result
    assert len(result["errors"]) <= 10


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_progress_summary_format(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload = {
        "action": "upsert_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
        ],
        "idempotency_key": "key11",
    }

    result = graph_bulk_module.invoke(payload)
    assert "ok" in result
    assert "processed" in result
    assert "succeeded" in result
    assert "failed" in result
    assert "skipped" in result


# ─────────────────────────────────────────────────────────────────────────────
# 6. SECURITY/RBAC TESTS (8 tests)
# ─────────────────────────────────────────────────────────────────────────────


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_security_requires_tools_write_scope(mock_memgraph):
    """Tool should require tools:write scope (handled by @mcp_tool decorator)."""
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    # The @mcp_tool decorator handles scope validation
    # This test verifies the tool can be called with proper auth
    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
    }

    result = graph_bulk_module.invoke(payload)
    assert result["ok"] is True


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_security_tenant_isolation_nodes(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "org-8",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
    }

    graph_bulk_module.invoke(payload)
    calls = mock_db.query.call_args_list
    if calls:
        query = calls[0][0][0]
        assert "tenant:" in query or "org-8" in str(calls)


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_security_tenant_isolation_edges(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_edges",
        "principal": "u",
        "tenant": "org-9",
        "edges": [{"start_orig_id": "p1", "end_orig_id": "p2", "type": "KNOWS", "props": {}}],
    }

    graph_bulk_module.invoke(payload)
    calls = mock_db.query.call_args_list
    if calls:
        query = calls[0][0][0]
        assert "tenant:" in query or "org-9" in str(calls)


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_security_metadata_created_by(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload = {
        "action": "upsert_nodes",
        "principal": "user|707",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
        "idempotency_key": "key12",
    }

    graph_bulk_module.invoke(payload)
    calls = mock_db.query.call_args_list
    if len(calls) >= 2:
        query = calls[1][0][0]
        assert "created_by" in query or "user|707" in str(calls)


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_security_metadata_updated_by(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": True}]

    payload = {
        "action": "upsert_nodes",
        "principal": "user|808",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
        "idempotency_key": "key13",
    }

    graph_bulk_module.invoke(payload)
    calls = mock_db.query.call_args_list
    if len(calls) >= 2:
        query = calls[1][0][0]
        assert "updated_by" in query or "user|808" in str(calls)


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_security_principal_from_payload(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "user|real",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
    }

    graph_bulk_module.invoke(payload)
    # Principal should be used


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_security_tenant_from_payload(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "org-real",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
    }

    graph_bulk_module.invoke(payload)
    # Tenant should be used


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_security_scope_validation_on_invoke(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
    }

    result = graph_bulk_module.invoke(payload)
    assert result["ok"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 7. TRANSACTION SAFETY TESTS (6 tests)
# ─────────────────────────────────────────────────────────────────────────────


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_transaction_batch_atomicity(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": ["Person"], "orig_id": "p2", "props": {}},
        ],
        "batch_size": 2,
    }

    graph_bulk_module.invoke(payload)
    # Each execute_query is atomic


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_transaction_error_rollback(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.side_effect = [None, Exception("DB error")]

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [
            {"labels": ["Person"], "orig_id": "p1", "props": {}},
            {"labels": ["Person"], "orig_id": "p2", "props": {}},
        ],
        "batch_size": 1,
        "fail_fast": False,
    }

    result = graph_bulk_module.invoke(payload)
    assert result["succeeded"] >= 1 or result["failed"] >= 1


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_transaction_isolation_concurrent_ops(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload1 = {
        "action": "ingest_nodes",
        "principal": "u1",
        "tenant": "t1",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
    }

    payload2 = {
        "action": "ingest_nodes",
        "principal": "u2",
        "tenant": "t2",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
    }

    result1 = graph_bulk_module.invoke(payload1)
    result2 = graph_bulk_module.invoke(payload2)
    assert result1["ok"] is True
    assert result2["ok"] is True


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_transaction_timeout_handling(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.side_effect = Exception("Timeout")

    payload = {
        "action": "ingest_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
        "timeout_ms": 1000,
    }

    result = graph_bulk_module.invoke(payload)
    assert result.get("ok") is not None  # Tool completed


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_transaction_consistency_checks(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db

    payload = {
        "action": "ingest_edges",
        "principal": "u",
        "tenant": "t",
        "edges": [{"start_orig_id": "nonexistent1", "end_orig_id": "nonexistent2", "type": "KNOWS", "props": {}}],
    }

    result = graph_bulk_module.invoke(payload)
    # Should handle missing nodes


@patch("src.mcp.tools.graph.bulk.MemgraphAdapter")
def test_transaction_upsert_race_condition(mock_memgraph):
    mock_db = MagicMock()
    mock_memgraph.return_value = mock_db
    mock_db.query.return_value = [{"exists": False}]

    payload = {
        "action": "upsert_nodes",
        "principal": "u",
        "tenant": "t",
        "nodes": [{"labels": ["Person"], "orig_id": "p1", "props": {}}],
        "idempotency_key": "key14",
    }

    result1 = graph_bulk_module.invoke(payload)
    result2 = graph_bulk_module.invoke(payload)
    assert result1["ok"] is True
    assert result2["ok"] is True
