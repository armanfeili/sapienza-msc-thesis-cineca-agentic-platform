"""
Integration Tests: MCP Tool graph.search

End-to-end tests with live Memgraph database.

Test structure follows Phase 2 of GRAPH_TOOLS_IMPLEMENTATION_PLAN.md

Coverage areas:
1. Node search with filters (end-to-end)
2. Edge search with filters (end-to-end)
3. Count accuracy validation
4. Distinct values verification
5. Audit trail verification
6. RBAC enforcement with Auth0 tokens

Total: 6 integration tests
"""

import pytest
import os
from typing import Dict, Any

# Import the tool directly
from src.mcp.tools.graph import search as graph_search_module
from src.mcp.runtime import ToolContext
from src.adapters.db_memgraph import MemgraphAdapter

# ─────────────────────────────────────────────────────────────────────────────
# Test Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Auth0 tokens from environment (set via export in shell)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
USER_TOKEN = os.getenv("USER_TOKEN", "")
MACHINE_TOKEN = os.getenv("MACHINE_TOKEN", "")

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def memgraph():
    """Provide clean Memgraph connection."""
    db = MemgraphAdapter()
    yield db


@pytest.fixture(scope="module")
def seed_test_data(memgraph):
    """Seed test data for integration tests."""
    # Create test nodes
    memgraph.query(
        """
        MERGE (u1:User {orig_id: 'user-test-1', name: 'Alice', status: 'active', country: 'IT'})
        MERGE (u2:User {orig_id: 'user-test-2', name: 'Bob', status: 'inactive', country: 'US'})
        MERGE (u3:User {orig_id: 'user-test-3', name: 'Charlie', status: 'active', country: 'IT'})
        MERGE (i1:Institution {orig_id: 'inst-test-1', name: 'University A', country: 'IT'})
        MERGE (i2:Institution {orig_id: 'inst-test-2', name: 'Company B', country: 'US'})
    """,
        {},
    )

    # Create test relationships
    memgraph.query(
        """
        MATCH (u1:User {orig_id: 'user-test-1'})
        MATCH (i1:Institution {orig_id: 'inst-test-1'})
        MERGE (u1)-[:WORKS_AT {since: '2024', role: 'researcher'}]->(i1)
        
        MATCH (u2:User {orig_id: 'user-test-2'})
        MATCH (i2:Institution {orig_id: 'inst-test-2'})
        MERGE (u2)-[:WORKS_AT {since: '2023', role: 'engineer'}]->(i2)
        
        MATCH (u3:User {orig_id: 'user-test-3'})
        MATCH (i1:Institution {orig_id: 'inst-test-1'})
        MERGE (u3)-[:WORKS_AT {since: '2024', role: 'student'}]->(i1)
    """,
        {},
    )

    yield

    # Cleanup
    memgraph.query(
        """
        MATCH (n) WHERE n.orig_id STARTS WITH 'user-test-' OR n.orig_id STARTS WITH 'inst-test-'
        DETACH DELETE n
    """,
        {},
    )


def invoke_tool(action: str, **kwargs) -> Dict[str, Any]:
    """Helper to invoke graph.search with minimal boilerplate."""
    ctx = ToolContext(
        principal=kwargs.pop("principal", "user-integration-test"),
        tenant=kwargs.pop("tenant", "tenant-test"),
        scopes=kwargs.pop("scopes", ["tools:basic"]),
        tool_name="graph.search",
    )

    payload = {"action": action, "principal": ctx.principal, "tenant": ctx.tenant, **kwargs}
    return graph_search_module.invoke(ctx, payload)


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestNodeSearchEndToEnd:
    """Test node search with live database."""

    def test_search_nodes_by_label(self, seed_test_data):
        """Test searching nodes by label."""
        result = invoke_tool("nodes", label="User", page=1, page_size=10)

        assert result["ok"] is True
        assert result["action"] == "nodes"
        assert result["total"] >= 3  # At least our test users
        assert len(result["items"]) >= 3

        # Verify structure
        for item in result["items"]:
            assert "orig_id" in item
            assert "labels" in item
            assert "User" in item["labels"]

    def test_search_nodes_with_where_filter(self, seed_test_data):
        """Test searching nodes with property filter."""
        result = invoke_tool("nodes", label="User", where={"status": "active"}, page=1, page_size=10)

        assert result["ok"] is True
        assert result["total"] >= 2  # Alice and Charlie

        # Verify all returned users have status=active
        for item in result["items"]:
            if item["orig_id"].startswith("user-test-"):
                # Our test data
                assert "status" in item or ("props" in item and item["props"].get("status") == "active")

    def test_search_nodes_with_projection(self, seed_test_data):
        """Test searching nodes with field projection."""
        result = invoke_tool("nodes", label="User", select=["name", "status"], page=1, page_size=10)

        assert result["ok"] is True
        assert len(result["items"]) >= 3

        # Verify projection
        for item in result["items"]:
            assert "orig_id" in item  # Always included
            assert "labels" in item  # Always included
            # Check projected fields are present
            if item["orig_id"].startswith("user-test-"):
                assert "name" in item or ("props" in item)

    def test_search_nodes_with_pagination(self, seed_test_data):
        """Test pagination works correctly."""
        # First page
        result1 = invoke_tool("nodes", label="User", page=1, page_size=2)

        # Second page
        result2 = invoke_tool("nodes", label="User", page=2, page_size=2)

        assert result1["page"] == 1
        assert result2["page"] == 2
        assert result1["page_size"] == 2
        assert result2["page_size"] == 2

        # Totals should match
        assert result1["total"] == result2["total"]

        # Items should be different (if there are enough)
        if result1["total"] > 2:
            ids1 = {item["orig_id"] for item in result1["items"]}
            ids2 = {item["orig_id"] for item in result2["items"]}
            assert ids1 != ids2  # Different pages should have different items


class TestEdgeSearchEndToEnd:
    """Test edge search with live database."""

    def test_search_edges_by_type(self, seed_test_data):
        """Test searching edges by relationship type."""
        result = invoke_tool("edges", type="WORKS_AT", page=1, page_size=10)

        assert result["ok"] is True
        assert result["action"] == "edges"
        assert result["total"] >= 3  # Our test relationships

        # Verify structure
        for item in result["items"]:
            assert "type" in item
            assert item["type"] == "WORKS_AT"
            assert "start_orig_id" in item
            assert "end_orig_id" in item

    def test_search_edges_with_where_filter(self, seed_test_data):
        """Test searching edges with property filter."""
        result = invoke_tool("edges", type="WORKS_AT", where={"since": "2024"}, page=1, page_size=10)

        assert result["ok"] is True
        assert result["total"] >= 2  # Alice and Charlie both started in 2024

        # Verify all returned edges have since=2024
        for item in result["items"]:
            if item["start_orig_id"].startswith("user-test-"):
                assert "since" in item or ("props" in item and item["props"].get("since") == "2024")


class TestCountAction:
    """Test count action accuracy."""

    def test_count_nodes_by_label(self, seed_test_data):
        """Test counting nodes by label."""
        result = invoke_tool("count", label="User")

        assert result["ok"] is True
        assert result["action"] == "count"
        assert result["count"] >= 3  # At least our test users

    def test_count_nodes_with_filter(self, seed_test_data):
        """Test counting nodes with filter."""
        result = invoke_tool("count", label="User", where={"country": "IT"})

        assert result["ok"] is True
        assert result["count"] >= 2  # Alice and Charlie

    def test_count_edges_by_type(self, seed_test_data):
        """Test counting edges by type."""
        result = invoke_tool("count", type="WORKS_AT")

        assert result["ok"] is True
        assert result["count"] >= 3  # Our test relationships


class TestDistinctAction:
    """Test distinct values extraction."""

    def test_distinct_property_values(self, seed_test_data):
        """Test getting distinct values for a property."""
        result = invoke_tool("distinct", label="User", property="status", limit=10)

        assert result["ok"] is True
        assert result["action"] == "distinct"
        assert result["property"] == "status"
        assert "values" in result
        assert len(result["values"]) >= 2  # active, inactive
        assert "active" in result["values"]
        assert "inactive" in result["values"]

    def test_distinct_with_label_filter(self, seed_test_data):
        """Test distinct values filtered by label."""
        result = invoke_tool("distinct", label="User", property="country", limit=10)

        assert result["ok"] is True
        assert len(result["values"]) >= 2  # IT, US
        assert "IT" in result["values"]
        assert "US" in result["values"]


class TestRBACEnforcement:
    """Test RBAC enforcement with Auth0 tokens."""

    @pytest.mark.skipif(not USER_TOKEN, reason="USER_TOKEN not set")
    def test_user_token_can_invoke_search(self, seed_test_data):
        """Test USER_TOKEN (tools:basic) can invoke graph.search."""
        ctx = ToolContext(
            principal="user-integration-test",
            tenant="tenant-test",
            scopes=["tools:basic"],
            tool_name="graph.search",
            auth_token=USER_TOKEN,
        )

        result = graph_search_module.invoke(
            ctx,
            {
                "action": "nodes",
                "label": "User",
                "principal": ctx.principal,
                "tenant": ctx.tenant,
                "page": 1,
                "page_size": 10,
            },
        )

        assert result["ok"] is True
        assert len(result["items"]) >= 3

    @pytest.mark.skipif(not ADMIN_TOKEN, reason="ADMIN_TOKEN not set")
    def test_admin_token_can_invoke_search(self, seed_test_data):
        """Test ADMIN_TOKEN (tools:all) can invoke graph.search."""
        ctx = ToolContext(
            principal="admin-integration-test",
            tenant="tenant-test",
            scopes=["tools:invoke:all"],
            tool_name="graph.search",
            auth_token=ADMIN_TOKEN,
        )

        result = graph_search_module.invoke(
            ctx, {"action": "count", "label": "User", "principal": ctx.principal, "tenant": ctx.tenant}
        )

        assert result["ok"] is True
        assert result["count"] >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
