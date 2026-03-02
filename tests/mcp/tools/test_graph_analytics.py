"""
Unit Tests: MCP Tool graph.analytics

Test structure follows Phase 3 of GRAPH_TOOLS_IMPLEMENTATION_PLAN.md

Coverage areas:
1. Schema validation (8 tests)
2. Each action happy path (6 tests)
3. Bounds enforcement (8 tests)
4. Read-only enforcement (6 tests)
5. Security/RBAC (6 tests)

Total: 34 unit tests
"""

import pytest
from pydantic import ValidationError
from unittest.mock import Mock, patch

from src.mcp.schemas import GraphAnalyticsPayload, GraphAnalyticsAction
from src.mcp.tools.graph import analytics as graph_analytics_module
from src.mcp.runtime import ToolContext


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema Validation Tests (8 tests)
# ─────────────────────────────────────────────────────────────────────────────


class TestSchemaValidation:
    """Test GraphAnalyticsPayload schema validation."""

    def test_degree_distribution_payload(self):
        """Test degree_distribution action payload."""
        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.degree_distribution,
            labels=["User"],
            row_limit=500,
            timeout_ms=10000,
            principal="user-123",
            tenant="tenant-1",
        )
        assert payload.action == GraphAnalyticsAction.degree_distribution
        assert payload.labels == ["User"]
        assert payload.row_limit == 500

    def test_shortest_path_payload(self):
        """Test shortest_path action payload."""
        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.shortest_path,
            start_id="user-1",
            end_id="user-2",
            max_depth=5,
            principal="user-123",
            tenant="tenant-1",
        )
        assert payload.action == GraphAnalyticsAction.shortest_path
        assert payload.start_id == "user-1"
        assert payload.end_id == "user-2"
        assert payload.max_depth == 5

    def test_top_k_degree_payload(self):
        """Test top_k_degree action payload."""
        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.top_k_degree,
            labels=["Institution"],
            k=20,
            principal="admin-456",
            tenant="tenant-2",
        )
        assert payload.action == GraphAnalyticsAction.top_k_degree
        assert payload.k == 20

    def test_label_counts_payload(self):
        """Test label_counts action payload."""
        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.label_counts, principal="user-123", tenant="tenant-1"
        )
        assert payload.action == GraphAnalyticsAction.label_counts

    def test_relationship_counts_payload(self):
        """Test relationship_counts action payload."""
        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.relationship_counts, timeout_ms=15000, principal="user-789", tenant="tenant-1"
        )
        assert payload.action == GraphAnalyticsAction.relationship_counts

    def test_missing_required_fields(self):
        """Test validation fails without required fields."""
        with pytest.raises(ValidationError) as exc_info:
            GraphAnalyticsPayload(action=GraphAnalyticsAction.degree_distribution)

        errors = exc_info.value.errors()
        error_fields = {e["loc"][0] for e in errors}
        assert "principal" in error_fields
        assert "tenant" in error_fields

    def test_invalid_k_value(self):
        """Test k validation (1-100)."""
        with pytest.raises(ValidationError):
            GraphAnalyticsPayload(
                action=GraphAnalyticsAction.top_k_degree, k=0, principal="user-123", tenant="tenant-1"
            )

        with pytest.raises(ValidationError):
            GraphAnalyticsPayload(
                action=GraphAnalyticsAction.top_k_degree, k=101, principal="user-123", tenant="tenant-1"
            )

    def test_invalid_max_depth(self):
        """Test max_depth validation (1-10)."""
        with pytest.raises(ValidationError):
            GraphAnalyticsPayload(
                action=GraphAnalyticsAction.shortest_path,
                start_id="a",
                end_id="b",
                max_depth=0,
                principal="user-123",
                tenant="tenant-1",
            )

        with pytest.raises(ValidationError):
            GraphAnalyticsPayload(
                action=GraphAnalyticsAction.shortest_path,
                start_id="a",
                end_id="b",
                max_depth=11,
                principal="user-123",
                tenant="tenant-1",
            )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Action Happy Path Tests (6 tests - one per action + combined)
# ─────────────────────────────────────────────────────────────────────────────


class TestActionHappyPaths:
    """Test each action's happy path."""

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_degree_distribution_action(self, mock_adapter_class):
        """Test degree_distribution returns correct structure."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        # Mock distribution query
        mock_db.query.side_effect = [
            [{"degree": 0, "count": 10}, {"degree": 1, "count": 20}, {"degree": 2, "count": 5}],  # distribution
            [{"min": 0, "max": 2, "avg": 0.9}],  # summary
        ]

        result = graph_analytics_module._act_degree_distribution(
            mock_db, {"label": "User", "row_limit": 1000, "timeout_ms": 5000}
        )

        assert result["ok"] is True
        assert result["action"] == "degree_distribution"
        assert result["label"] == "User"
        assert "summary" in result
        assert result["summary"]["min"] == 0
        assert result["summary"]["max"] == 2
        assert "distribution" in result
        assert len(result["distribution"]) == 3

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_shortest_path_found(self, mock_adapter_class):
        """Test shortest_path when path exists."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.return_value = [
            {
                "length": 2,
                "nodes": [
                    {"orig_id": "u1", "labels": ["User"]},
                    {"orig_id": "i1", "labels": ["Institution"]},
                    {"orig_id": "u2", "labels": ["User"]},
                ],
                "edges": [{"type": "WORKS_AT"}, {"type": "EMPLOYS"}],
            }
        ]

        result = graph_analytics_module._act_shortest_path(
            mock_db, {"start_id": "u1", "end_id": "u2", "max_depth": 5, "timeout_ms": 5000}
        )

        assert result["ok"] is True
        assert result["action"] == "shortest_path"
        assert result["found"] is True
        assert result["length"] == 2
        assert len(result["path"]["nodes"]) == 3
        assert len(result["path"]["edges"]) == 2

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_shortest_path_not_found(self, mock_adapter_class):
        """Test shortest_path when no path exists."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.return_value = []

        result = graph_analytics_module._act_shortest_path(
            mock_db, {"start_id": "u1", "end_id": "isolated", "max_depth": 5, "timeout_ms": 5000}
        )

        assert result["ok"] is True
        assert result["found"] is False
        assert result["length"] is None
        assert result["path"] is None

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_top_k_degree_action(self, mock_adapter_class):
        """Test top_k_degree returns ranked nodes."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.return_value = [
            {"orig_id": "u1", "labels": ["User"], "degree": 50},
            {"orig_id": "u2", "labels": ["User"], "degree": 30},
            {"orig_id": "i1", "labels": ["Institution"], "degree": 25},
        ]

        result = graph_analytics_module._act_top_k_degree(mock_db, {"label": "User", "k": 3, "timeout_ms": 5000})

        assert result["ok"] is True
        assert result["action"] == "top_k_degree"
        assert result["k"] == 3
        assert len(result["items"]) == 3
        assert result["items"][0]["degree"] == 50  # Highest first

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_label_counts_action(self, mock_adapter_class):
        """Test label_counts returns grouped counts."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.return_value = [
            {"label": "User", "count": 150},
            {"label": "Institution", "count": 50},
            {"label": "Project", "count": 30},
        ]

        result = graph_analytics_module._act_label_counts(mock_db, {"timeout_ms": 5000})

        assert result["ok"] is True
        assert result["action"] == "label_counts"
        assert len(result["items"]) == 3
        assert result["items"][0]["label"] == "User"
        assert result["items"][0]["count"] == 150

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_relationship_counts_action(self, mock_adapter_class):
        """Test relationship_counts returns grouped counts."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db

        mock_db.query.return_value = [
            {"type": "WORKS_AT", "count": 200},
            {"type": "RUNS", "count": 100},
            {"type": "PARTICIPATES_IN", "count": 50},
        ]

        result = graph_analytics_module._act_relationship_counts(mock_db, {"timeout_ms": 5000})

        assert result["ok"] is True
        assert result["action"] == "relationship_counts"
        assert len(result["items"]) == 3
        assert result["items"][0]["type"] == "WORKS_AT"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Bounds Enforcement Tests (8 tests)
# ─────────────────────────────────────────────────────────────────────────────


class TestBoundsEnforcement:
    """Test that bounds/constraints are properly enforced."""

    def test_max_depth_within_bounds(self):
        """Test max_depth accepts valid range."""
        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.shortest_path,
            start_id="a",
            end_id="b",
            max_depth=1,  # Minimum
            principal="user-123",
            tenant="tenant-1",
        )
        assert payload.max_depth == 1

        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.shortest_path,
            start_id="a",
            end_id="b",
            max_depth=10,  # Maximum
            principal="user-123",
            tenant="tenant-1",
        )
        assert payload.max_depth == 10

    def test_k_within_bounds(self):
        """Test k accepts valid range."""
        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.top_k_degree, k=1, principal="user-123", tenant="tenant-1"  # Minimum
        )
        assert payload.k == 1

        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.top_k_degree, k=100, principal="user-123", tenant="tenant-1"  # Maximum
        )
        assert payload.k == 100

    def test_row_limit_within_bounds(self):
        """Test row_limit accepts valid range."""
        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.degree_distribution,
            row_limit=1,  # Minimum
            principal="user-123",
            tenant="tenant-1",
        )
        assert payload.row_limit == 1

        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.degree_distribution,
            row_limit=10000,  # Maximum
            principal="user-123",
            tenant="tenant-1",
        )
        assert payload.row_limit == 10000

    def test_row_limit_exceeds_max(self):
        """Test row_limit rejects values > 10000."""
        with pytest.raises(ValidationError):
            GraphAnalyticsPayload(
                action=GraphAnalyticsAction.degree_distribution,
                row_limit=10001,
                principal="user-123",
                tenant="tenant-1",
            )

    def test_timeout_within_bounds(self):
        """Test timeout_ms accepts valid range."""
        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.label_counts, timeout_ms=100, principal="user-123", tenant="tenant-1"  # Minimum
        )
        assert payload.timeout_ms == 100

        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.label_counts,
            timeout_ms=60000,  # Maximum
            principal="user-123",
            tenant="tenant-1",
        )
        assert payload.timeout_ms == 60000

    def test_timeout_exceeds_max(self):
        """Test timeout_ms rejects values > 60000."""
        with pytest.raises(ValidationError):
            GraphAnalyticsPayload(
                action=GraphAnalyticsAction.label_counts, timeout_ms=60001, principal="user-123", tenant="tenant-1"
            )

    def test_timeout_below_min(self):
        """Test timeout_ms rejects values < 100."""
        with pytest.raises(ValidationError):
            GraphAnalyticsPayload(
                action=GraphAnalyticsAction.label_counts, timeout_ms=99, principal="user-123", tenant="tenant-1"
            )

    def test_shortest_path_requires_both_ids(self):
        """Test shortest_path validation requires start_id and end_id."""
        mock_db = Mock()

        # Missing start_id
        with pytest.raises(ValueError, match="requires both start_id and end_id"):
            graph_analytics_module._act_shortest_path(mock_db, {"end_id": "b", "max_depth": 5, "timeout_ms": 5000})

        # Missing end_id
        with pytest.raises(ValueError, match="requires both start_id and end_id"):
            graph_analytics_module._act_shortest_path(mock_db, {"start_id": "a", "max_depth": 5, "timeout_ms": 5000})


# ─────────────────────────────────────────────────────────────────────────────
# 4. Read-Only Enforcement Tests (6 tests)
# ─────────────────────────────────────────────────────────────────────────────


class TestReadOnlyEnforcement:
    """Test read-only guarantees for analytics operations."""

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_degree_distribution_readonly(self, mock_adapter_class):
        """Test degree_distribution uses read-only query."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db
        mock_db.query.side_effect = [[{"degree": 1, "count": 10}], [{"min": 1, "max": 1, "avg": 1.0}]]

        graph_analytics_module._act_degree_distribution(
            mock_db, {"label": "User", "row_limit": 1000, "timeout_ms": 5000}
        )

        # Verify all queries are MATCH/RETURN only
        for call in mock_db.query.call_args_list:
            query = call[0][0].upper()
            assert "CREATE" not in query
            assert "MERGE" not in query
            assert "DELETE" not in query
            assert "SET" not in query
            assert "MATCH" in query
            assert "RETURN" in query

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_shortest_path_readonly(self, mock_adapter_class):
        """Test shortest_path uses read-only query."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db
        mock_db.query.return_value = []

        graph_analytics_module._act_shortest_path(
            mock_db, {"start_id": "a", "end_id": "b", "max_depth": 5, "timeout_ms": 5000}
        )

        query = mock_db.query.call_args[0][0].upper()
        assert "MATCH" in query
        assert "RETURN" in query
        assert "CREATE" not in query
        assert "MERGE" not in query

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_top_k_degree_readonly(self, mock_adapter_class):
        """Test top_k_degree uses read-only query."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db
        mock_db.query.return_value = []

        graph_analytics_module._act_top_k_degree(mock_db, {"label": "User", "k": 10, "timeout_ms": 5000})

        query = mock_db.query.call_args[0][0].upper()
        assert "MATCH" in query
        assert "RETURN" in query
        assert "SET" not in query

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_label_counts_readonly(self, mock_adapter_class):
        """Test label_counts uses read-only query."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db
        mock_db.query.return_value = []

        graph_analytics_module._act_label_counts(mock_db, {"timeout_ms": 5000})

        query = mock_db.query.call_args[0][0].upper()
        assert "MATCH" in query
        assert "RETURN" in query
        assert "DELETE" not in query

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_relationship_counts_readonly(self, mock_adapter_class):
        """Test relationship_counts uses read-only query."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db
        mock_db.query.return_value = []

        graph_analytics_module._act_relationship_counts(mock_db, {"timeout_ms": 5000})

        query = mock_db.query.call_args[0][0].upper()
        assert "MATCH" in query
        assert "RETURN" in query
        assert "DROP" not in query

    def test_tool_has_rbac_decorator(self):
        """Test tool has @mcp_tool decorator with required_scope."""
        # Verify the decorator is applied
        assert hasattr(graph_analytics_module.invoke, "__wrapped__")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Security/RBAC Tests (6 tests)
# ─────────────────────────────────────────────────────────────────────────────


class TestSecurity:
    """Test RBAC enforcement and security."""

    def test_requires_principal(self):
        """Test analytics actions require principal."""
        with pytest.raises(ValidationError) as exc_info:
            GraphAnalyticsPayload(action=GraphAnalyticsAction.label_counts, tenant="tenant-1")

        errors = exc_info.value.errors()
        error_fields = {e["loc"][0] for e in errors}
        assert "principal" in error_fields

    def test_requires_tenant(self):
        """Test analytics actions require tenant."""
        with pytest.raises(ValidationError) as exc_info:
            GraphAnalyticsPayload(action=GraphAnalyticsAction.label_counts, principal="user-123")

        errors = exc_info.value.errors()
        error_fields = {e["loc"][0] for e in errors}
        assert "tenant" in error_fields

    def test_empty_principal_rejected(self):
        """Test empty principal is rejected."""
        with pytest.raises(ValidationError):
            GraphAnalyticsPayload(action=GraphAnalyticsAction.label_counts, principal="", tenant="tenant-1")

    def test_empty_tenant_rejected(self):
        """Test empty tenant is rejected."""
        with pytest.raises(ValidationError):
            GraphAnalyticsPayload(action=GraphAnalyticsAction.label_counts, principal="user-123", tenant="")

    def test_defaults_applied(self):
        """Test schema applies sensible defaults."""
        payload = GraphAnalyticsPayload(
            action=GraphAnalyticsAction.degree_distribution, principal="user-123", tenant="tenant-1"
        )

        # Check defaults
        assert payload.timeout_ms == 5000  # Default timeout
        assert payload.max_depth == 5  # Default max_depth
        assert payload.k == 10  # Default k
        assert payload.row_limit == 1000  # Default row_limit

    @patch("src.mcp.tools.graph.analytics.MemgraphAdapter")
    def test_action_dispatch_security(self, mock_adapter_class):
        """Test all actions go through validated dispatch."""
        mock_db = Mock()
        mock_adapter_class.return_value = mock_db
        mock_db.query.return_value = []

        # Test wrapped function (ctx is created by @mcp_tool)
        result = graph_analytics_module.invoke.__wrapped__(
            None, {"action": "label_counts", "principal": "user-test", "tenant": "tenant-test"}
        )

        assert result["ok"] is True
        assert result["action"] == "label_counts"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
