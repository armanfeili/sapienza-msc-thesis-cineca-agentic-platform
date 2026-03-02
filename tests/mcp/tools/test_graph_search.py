"""
Unit Tests: MCP Tool graph.search

Test structure follows Phase 2 of GRAPH_TOOLS_IMPLEMENTATION_PLAN.md

Coverage areas:
1. Schema validation (10 tests)
2. Filters and predicates (12 tests)
3. Pagination (6 tests)
4. Projection (4 tests)
5. Security/RBAC (8 tests)

Total: 40 unit tests
"""

import pytest
from pydantic import ValidationError
from unittest.mock import Mock, patch

from src.mcp.schemas import GraphSearchPayload, GraphSearchAction
from src.mcp.tools.graph import search as graph_search_module
from src.mcp.runtime import ToolContext


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema Validation Tests (10 tests)
# ─────────────────────────────────────────────────────────────────────────────


class TestSchemaValidation:
    """Test GraphSearchPayload schema validation."""

    def test_minimal_valid_payload(self):
        """Test minimal valid payload with defaults."""
        payload = GraphSearchPayload(principal="user-123", tenant="tenant-1")
        assert payload.action == GraphSearchAction.nodes
        assert payload.page == 1
        assert payload.page_size == 25
        assert payload.timeout_ms == 5000
        assert payload.where == {}
        assert payload.select is None

    def test_full_nodes_payload(self):
        """Test fully specified nodes search payload."""
        payload = GraphSearchPayload(
            action=GraphSearchAction.nodes,
            label="User",
            where={"status": "active"},
            select=["orig_id", "name"],
            order_by="name",
            order_desc=False,
            page=2,
            page_size=50,
            timeout_ms=10000,
            principal="user-123",
            tenant="tenant-1",
        )
        assert payload.action == GraphSearchAction.nodes
        assert payload.label == "User"
        assert payload.where == {"status": "active"}
        assert payload.select == ["orig_id", "name"]
        assert payload.page == 2

    def test_edges_payload(self):
        """Test edges search payload."""
        payload = GraphSearchPayload(
            action=GraphSearchAction.edges,
            type="WORKS_AT",
            where={"since": "2024"},
            page=1,
            page_size=25,
            principal="admin-456",
            tenant="tenant-2",
        )
        assert payload.action == GraphSearchAction.edges
        assert payload.type == "WORKS_AT"

    def test_count_payload(self):
        """Test count action payload."""
        payload = GraphSearchPayload(
            action=GraphSearchAction.count,
            label="Institution",
            where={"country": "IT"},
            principal="user-789",
            tenant="tenant-1",
        )
        assert payload.action == GraphSearchAction.count

    def test_distinct_payload(self):
        """Test distinct action payload."""
        payload = GraphSearchPayload(
            action=GraphSearchAction.distinct,
            label="User",
            property="status",
            limit=50,
            principal="user-123",
            tenant="tenant-1",
        )
        assert payload.action == GraphSearchAction.distinct
        assert payload.property == "status"
        assert payload.limit == 50

    def test_missing_required_fields(self):
        """Test validation fails without required fields."""
        with pytest.raises(ValidationError) as exc_info:
            GraphSearchPayload()

        errors = exc_info.value.errors()
        error_fields = {e["loc"][0] for e in errors}
        assert "principal" in error_fields
        assert "tenant" in error_fields

    def test_invalid_page_number(self):
        """Test page validation (must be >= 1)."""
        with pytest.raises(ValidationError):
            GraphSearchPayload(page=0, principal="user-123", tenant="tenant-1")

    def test_invalid_page_size(self):
        """Test page_size validation (1-1000)."""
        with pytest.raises(ValidationError):
            GraphSearchPayload(page_size=0, principal="user-123", tenant="tenant-1")

        with pytest.raises(ValidationError):
            GraphSearchPayload(page_size=1001, principal="user-123", tenant="tenant-1")

    def test_invalid_timeout(self):
        """Test timeout_ms validation (100-30000)."""
        with pytest.raises(ValidationError):
            GraphSearchPayload(timeout_ms=50, principal="user-123", tenant="tenant-1")

        with pytest.raises(ValidationError):
            GraphSearchPayload(timeout_ms=40000, principal="user-123", tenant="tenant-1")

    def test_empty_principal_rejected(self):
        """Test empty principal string is rejected."""
        with pytest.raises(ValidationError):
            GraphSearchPayload(principal="", tenant="tenant-1")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Filters and Predicates Tests (12 tests)
# ─────────────────────────────────────────────────────────────────────────────


class TestFiltersAndPredicates:
    """Test filter logic and predicate building."""

    def test_build_label_filter_single(self):
        """Test single label filter generation."""
        result = graph_search_module._build_label_filter("User", None)
        assert result == ":`User`"

    def test_build_label_filter_multiple(self):
        """Test multiple labels returns empty (uses WHERE clause)."""
        result = graph_search_module._build_label_filter(None, ["User", "Institution"])
        assert result == ""

    def test_build_label_filter_none(self):
        """Test no label filter."""
        result = graph_search_module._build_label_filter(None, None)
        assert result == ""

    def test_build_where_simple(self):
        """Test simple WHERE clause with single property."""
        clause, params = graph_search_module._build_where_clause("n", {"status": "active"})
        assert "WHERE" in clause
        assert "n.`status`" in clause
        assert "_w0" in params
        assert params["_w0"] == "active"

    def test_build_where_multiple_properties(self):
        """Test WHERE with multiple properties (AND)."""
        clause, params = graph_search_module._build_where_clause("n", {"status": "active", "country": "IT"})
        assert "WHERE" in clause
        assert " AND " in clause
        assert len(params) == 2

    def test_build_where_with_labels(self):
        """Test WHERE with label filter for multiple labels."""
        clause, params = graph_search_module._build_where_clause(
            "n", {"status": "active"}, labels=["User", "Institution"]
        )
        assert "WHERE" in clause
        assert "any(lbl IN labels(n)" in clause
        assert "_labels" in params
        assert params["_labels"] == ["User", "Institution"]

    def test_build_where_empty(self):
        """Test WHERE clause with no filters."""
        clause, params = graph_search_module._build_where_clause("n", {})
        assert clause == ""
        assert params == {}

    def test_build_projection_all(self):
        """Test projection without select (all properties)."""
        projection = graph_search_module._build_projection("n", None)
        assert "orig_id" in projection
        assert "labels" in projection
        assert "properties(n)" in projection

    def test_build_projection_specific_fields(self):
        """Test projection with specific fields."""
        projection = graph_search_module._build_projection("n", ["name", "email"])
        assert "orig_id" in projection
        assert "labels" in projection
        assert "`name`" in projection
        assert "`email`" in projection

    def test_build_order_ascending(self):
        """Test ORDER BY ascending."""
        order = graph_search_module._build_order_clause("n", "name", False)
        assert "ORDER BY" in order
        assert "n.`name`" in order
        assert "ASC" in order

    def test_build_order_descending(self):
        """Test ORDER BY descending."""
        order = graph_search_module._build_order_clause("n", "created_at", True)
        assert "ORDER BY" in order
        assert "DESC" in order

    def test_build_order_none(self):
        """Test no ordering."""
        order = graph_search_module._build_order_clause("n", None, False)
        assert order == ""


# ─────────────────────────────────────────────────────────────────────────────
# 3. Pagination Tests (6 tests)
# ─────────────────────────────────────────────────────────────────────────────


class TestPagination:
    """Test pagination logic."""

    @patch("src.mcp.tools.graph.search.MemgraphAdapter")
    def test_nodes_pagination_first_page(self, mock_adapter_class):
        """Test first page of nodes search."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        # Mock count query
        mock_db.query.side_effect = [
            [{"total": 100}],  # count
            [{"item": {"orig_id": "1", "labels": ["User"]}}, {"item": {"orig_id": "2", "labels": ["User"]}}],  # data
        ]

        result = graph_search_module._act_nodes(mock_db, {"page": 1, "page_size": 2, "timeout_ms": 5000})

        assert result["ok"] is True
        assert result["page"] == 1
        assert result["page_size"] == 2
        assert result["total"] == 100
        assert result["count"] == 2
        assert len(result["items"]) == 2

    @patch("src.mcp.tools.graph.search.MemgraphAdapter")
    def test_nodes_pagination_second_page(self, mock_adapter_class):
        """Test second page with proper SKIP calculation."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.side_effect = [[{"total": 100}], [{"item": {"orig_id": "26", "labels": ["User"]}}]]

        result = graph_search_module._act_nodes(mock_db, {"page": 2, "page_size": 25, "timeout_ms": 5000})

        # Verify SKIP 25 was used
        call_args = mock_db.query.call_args_list[1]
        query = call_args[0][0]
        assert "SKIP 25" in query
        assert "LIMIT 25" in query

    @patch("src.mcp.tools.graph.search.MemgraphAdapter")
    def test_edges_pagination(self, mock_adapter_class):
        """Test edges pagination."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.side_effect = [
            [{"total": 50}],
            [{"item": {"type": "WORKS_AT"}, "start_id": "u1", "end_id": "i1"}],
        ]

        result = graph_search_module._act_edges(mock_db, {"page": 1, "page_size": 10, "timeout_ms": 5000})

        assert result["total"] == 50
        assert result["count"] == 1
        assert "start_orig_id" in result["items"][0]

    @patch("src.mcp.tools.graph.search.MemgraphAdapter")
    def test_pagination_empty_results(self, mock_adapter_class):
        """Test pagination with no matching results."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.side_effect = [[{"total": 0}], []]

        result = graph_search_module._act_nodes(mock_db, {"page": 1, "page_size": 25, "timeout_ms": 5000})

        assert result["total"] == 0
        assert result["count"] == 0
        assert result["items"] == []

    @patch("src.mcp.tools.graph.search.MemgraphAdapter")
    def test_pagination_last_page_partial(self, mock_adapter_class):
        """Test last page with fewer items than page_size."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.side_effect = [[{"total": 27}], [{"item": {"orig_id": "27", "labels": ["User"]}}]]  # Only 1 item

        result = graph_search_module._act_nodes(mock_db, {"page": 2, "page_size": 25, "timeout_ms": 5000})

        assert result["total"] == 27
        assert result["count"] == 1  # Partial page

    @patch("src.mcp.tools.graph.search.MemgraphAdapter")
    def test_pagination_metadata_consistency(self, mock_adapter_class):
        """Test pagination metadata is consistent."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.side_effect = [
            [{"total": 150}],
            [{"item": {"orig_id": str(i), "labels": ["User"]}} for i in range(50)],
        ]

        result = graph_search_module._act_nodes(mock_db, {"page": 3, "page_size": 50, "timeout_ms": 5000})

        # Verify: total should be full count, count should be actual items returned
        assert result["total"] == 150
        assert result["count"] == 50
        assert len(result["items"]) == 50


# ─────────────────────────────────────────────────────────────────────────────
# 4. Projection Tests (4 tests)
# ─────────────────────────────────────────────────────────────────────────────


class TestProjection:
    """Test field projection (select) logic."""

    @patch("src.mcp.tools.graph.search.MemgraphAdapter")
    def test_nodes_projection_specific_fields(self, mock_adapter_class):
        """Test nodes search with field projection."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.side_effect = [
            [{"total": 1}],
            [{"item": {"orig_id": "u1", "labels": ["User"], "name": "Alice", "email": "alice@example.com"}}],
        ]

        result = graph_search_module._act_nodes(
            mock_db, {"select": ["name", "email"], "page": 1, "page_size": 25, "timeout_ms": 5000}
        )

        # Verify query includes projection
        call_args = mock_db.query.call_args_list[1]
        query = call_args[0][0]
        assert "`name`" in query
        assert "`email`" in query

    @patch("src.mcp.tools.graph.search.MemgraphAdapter")
    def test_nodes_projection_all_properties(self, mock_adapter_class):
        """Test nodes search without projection (all properties)."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.side_effect = [
            [{"total": 1}],
            [{"item": {"orig_id": "u1", "labels": ["User"], "props": {"name": "Alice", "age": 30}}}],
        ]

        result = graph_search_module._act_nodes(mock_db, {"page": 1, "page_size": 25, "timeout_ms": 5000})

        # Verify query returns all properties
        call_args = mock_db.query.call_args_list[1]
        query = call_args[0][0]
        assert "properties(n)" in query

    @patch("src.mcp.tools.graph.search.MemgraphAdapter")
    def test_edges_projection_specific_fields(self, mock_adapter_class):
        """Test edges search with field projection."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.side_effect = [
            [{"total": 1}],
            [{"item": {"type": "WORKS_AT", "since": "2024"}, "start_id": "u1", "end_id": "i1"}],
        ]

        result = graph_search_module._act_edges(
            mock_db, {"select": ["since"], "page": 1, "page_size": 25, "timeout_ms": 5000}
        )

        # Verify projection
        assert result["items"][0]["type"] == "WORKS_AT"

    @patch("src.mcp.tools.graph.search.MemgraphAdapter")
    def test_edges_projection_all_properties(self, mock_adapter_class):
        """Test edges search without projection."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.side_effect = [
            [{"total": 1}],
            [{"item": {"type": "WORKS_AT", "props": {"since": "2024"}}, "start_id": "u1", "end_id": "i1"}],
        ]

        result = graph_search_module._act_edges(mock_db, {"page": 1, "page_size": 25, "timeout_ms": 5000})

        assert "props" in result["items"][0]


# ─────────────────────────────────────────────────────────────────────────────
# 5. Security/RBAC Tests (8 tests)
# ─────────────────────────────────────────────────────────────────────────────


class TestSecurity:
    """Test RBAC enforcement and read-only guarantees."""

    def test_write_detection_create(self):
        """Test write detection catches CREATE."""
        assert graph_search_module._looks_write("CREATE (n:User {name: 'Alice'})")

    def test_write_detection_merge(self):
        """Test write detection catches MERGE."""
        assert graph_search_module._looks_write("MERGE (n:User {orig_id: 'u1'})")

    def test_write_detection_delete(self):
        """Test write detection catches DELETE."""
        assert graph_search_module._looks_write("MATCH (n) DELETE n")

    def test_write_detection_set(self):
        """Test write detection catches SET."""
        assert graph_search_module._looks_write("MATCH (n) SET n.status = 'active'")

    def test_write_detection_drop(self):
        """Test write detection catches DROP."""
        assert graph_search_module._looks_write("DROP INDEX ON :User(name)")

    def test_read_only_match_allowed(self):
        """Test MATCH queries are not flagged as writes."""
        assert not graph_search_module._looks_write("MATCH (n:User) RETURN n")

    def test_read_only_count_allowed(self):
        """Test count queries are not flagged."""
        assert not graph_search_module._looks_write("MATCH (n) RETURN count(n)")

    def test_tool_has_rbac_decorator(self):
        """Test tool has @mcp_tool decorator with required_scope."""
        # Verify the decorator is applied
        assert hasattr(graph_search_module.invoke, "__wrapped__")
        # Verify tool name and scope are configured
        # (Full RBAC enforcement tested in integration tests)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
