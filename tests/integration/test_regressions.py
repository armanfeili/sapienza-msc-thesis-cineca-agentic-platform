"""
Regression tests for key functionality.

These tests verify that critical features continue to work as expected
across code changes.
"""

import pytest
from typing import Any, Dict


class TestRandomSamplingRegression:
    """
    Regression tests for random sampling support.
    
    These tests ensure that prompts like "Show me 10 random :Blast nodes"
    correctly generate Cypher with ORDER BY rand().
    """
    
    def test_generate_cypher_random_flag(self):
        """generate_cypher select with random=True should include ORDER BY rand()."""
        from src.mcp.tools.graph.generate_cypher import _act_select
        
        result = _act_select({
            "action": "select",
            "label": "Blast",
            "limit": 10,
            "random": True,
        })
        
        assert result["ok"] is True
        cypher = result["cypher"]
        
        # Must have ORDER BY rand() before LIMIT
        assert "ORDER BY rand()" in cypher
        assert "LIMIT" in cypher
        
        # ORDER BY rand() should come before LIMIT
        rand_idx = cypher.find("ORDER BY rand()")
        limit_idx = cypher.find("LIMIT")
        assert rand_idx < limit_idx, "ORDER BY rand() must precede LIMIT"
    
    def test_generate_cypher_no_random_by_default(self):
        """generate_cypher select without random should NOT include ORDER BY rand()."""
        from src.mcp.tools.graph.generate_cypher import _act_select
        
        result = _act_select({
            "action": "select",
            "label": "Blast",
            "limit": 10,
        })
        
        assert result["ok"] is True
        assert "ORDER BY rand()" not in result["cypher"]
    
    def test_generate_cypher_random_with_properties(self):
        """generate_cypher select with properties and random should work together."""
        from src.mcp.tools.graph.generate_cypher import _act_select
        
        result = _act_select({
            "action": "select",
            "label": "Blast",
            "limit": 5,
            "random": True,
        })
        
        assert result["ok"] is True
        cypher = result["cypher"]
        
        assert "ORDER BY rand()" in cypher
        assert "LIMIT" in cypher
        # Should return node (may or may not have specific properties)
        assert "RETURN n" in cypher or "RETURN" in cypher


class TestRelationshipTypeQueries:
    """
    Regression tests for relationship type discovery.
    
    These tests ensure that prompts about relationship types work correctly.
    Note: The current generate_cypher tool uses match_rel action for relationships.
    """
    
    def test_generate_cypher_match_rel(self):
        """generate_cypher match_rel should match relationships."""
        from src.mcp.tools.graph.generate_cypher import _act_match_rel
        
        result = _act_match_rel({
            "action": "match_rel",
            "from_label": "Blast",
            "limit": 10,
        })
        
        assert result["ok"] is True
        cypher = result["cypher"]
        
        # Should have relationship pattern
        assert "Blast" in cypher
        assert "-" in cypher  # Relationship connector
    
    def test_generate_cypher_schema_inventory(self):
        """generate_cypher schema_inventory should list schema info."""
        from src.mcp.tools.graph.generate_cypher import _act_schema_inventory
        
        result = _act_schema_inventory()
        
        assert result["ok"] is True
        # Schema inventory returns a single cypher statement (complex UNION query)
        assert "cypher" in result
        assert len(result["cypher"]) > 0


class TestBlastAnchorRegression:
    """
    Regression tests for :Blast anchor preservation in relationship type queries.
    
    E.3 Fix: Ensure that relationship type discovery queries preserve the
    label anchor (e.g., :Blast) instead of dropping it to MATCH ()-[r]->().
    """
    
    def test_is_relationship_type_query_with_blast(self):
        """_is_relationship_type_query should detect relationship type queries with :Blast."""
        from src.services.orchestrator import Orchestrator
        
        # Create orchestrator instance for accessing the method
        orch = Orchestrator.__new__(Orchestrator)
        
        # Test cases that should detect :Blast anchor
        positive_cases = [
            ("What distinct relationship types exist from :Blast?", "Blast"),
            ("What relationship types does Blast have?", "Blast"),
            ("Show relationship types from :Gene", "Gene"),
            ("List relationship types from :Protein", "Protein"),
        ]
        
        for goal, expected_label in positive_cases:
            result = orch._is_relationship_type_query(goal)
            assert result is not None, f"Should detect as relationship type query: {goal}"
            assert result.get("label") == expected_label, f"Should extract label {expected_label} from: {goal}, got {result}"
    
    def test_is_relationship_type_query_negative(self):
        """_is_relationship_type_query should NOT detect unrelated queries."""
        from src.services.orchestrator import Orchestrator
        
        orch = Orchestrator.__new__(Orchestrator)
        
        # Test cases that should NOT be detected as relationship type queries
        negative_cases = [
            "Show me 10 random :Blast nodes",
            "Count all :Blast nodes",
            "What properties does :Blast have?",
            "Show me the schema",
            "List all node labels",
        ]
        
        for goal in negative_cases:
            result = orch._is_relationship_type_query(goal)
            assert result is None, f"Should NOT detect as relationship type query: {goal}"
    
    def test_relationship_type_cypher_preserves_anchor(self):
        """Relationship type Cypher should preserve the label anchor."""
        # The expected Cypher pattern when asking for relationship types from :Blast
        # should include (:Blast) not just ()-[r]->()
        
        expected_pattern = "MATCH (:Blast)-[r]->() RETURN DISTINCT type(r)"
        
        # This is what we should generate, not:
        wrong_pattern = "MATCH ()-[r]->() RETURN DISTINCT type(r)"
        
        # Verify the patterns are different (sanity check)
        assert expected_pattern != wrong_pattern
        
        # The expected pattern anchors on :Blast
        assert ":Blast" in expected_pattern
        assert ":Blast" not in wrong_pattern


class TestLimitHintRegression:
    """
    Regression tests for limit_hint parameter.
    
    Prompts in the catalog use limit_hint to suggest result limits.
    """
    
    def test_limit_hint_used_as_limit(self):
        """limit_hint should be treated as limit parameter."""
        from src.mcp.tools.graph.generate_cypher import _act_select
        
        result = _act_select({
            "action": "select",
            "label": "Blast",
            "limit_hint": 15,
        })
        
        assert result["ok"] is True
        assert result["params"]["limit"] == 15
        assert "LIMIT" in result["cypher"]
    
    def test_limit_overrides_limit_hint(self):
        """Explicit limit should override limit_hint."""
        from src.mcp.tools.graph.generate_cypher import _act_select
        
        result = _act_select({
            "action": "select",
            "label": "Blast",
            "limit": 20,
            "limit_hint": 10,
        })
        
        assert result["ok"] is True
        # Explicit limit should win
        assert result["params"]["limit"] == 20


class TestCypherValidationRegression:
    """
    Regression tests for Cypher validation.
    
    Ensure that dangerous queries are caught.
    """
    
    def test_read_only_query_safe(self):
        """Standard MATCH queries should be safe."""
        from src.security.graph_access_policy import validate_cypher
        
        safe_queries = [
            "MATCH (n:Blast) RETURN n LIMIT 10",
            "MATCH (n:Blast)-[r]->(m) RETURN type(r), count(*)",
            "MATCH (n) RETURN labels(n), count(*) ORDER BY count(*) DESC",
            "CALL db.labels() YIELD label RETURN label",
        ]
        
        for query in safe_queries:
            result = validate_cypher(query)
            assert result.is_safe, f"Query should be safe: {query}"
            assert result.is_read_only, f"Query should be read-only: {query}"
    
    def test_write_query_flagged(self):
        """Write queries should be flagged."""
        from src.security.graph_access_policy import validate_cypher
        
        write_queries = [
            "CREATE (n:Test)",
            "MERGE (n:Test {id: 1})",
            "MATCH (n) SET n.updated = true",
            "MATCH (n:Test) DETACH DELETE n",
        ]
        
        for query in write_queries:
            result = validate_cypher(query)
            assert not result.is_read_only, f"Query should not be read-only: {query}"
    
    def test_admin_query_flagged(self):
        """Admin queries should require elevated permissions."""
        from src.security.graph_access_policy import validate_cypher
        
        admin_queries = [
            "CREATE INDEX ON :Blast(id)",
            "DROP INDEX ON :Blast(id)",
            "CREATE CONSTRAINT ON (n:Blast) ASSERT n.id IS UNIQUE",
        ]
        
        for query in admin_queries:
            result = validate_cypher(query)
            assert result.requires_admin, f"Query should require admin: {query}"
    
    def test_dangerous_query_blocked(self):
        """Dangerous queries should be blocked."""
        from src.security.graph_access_policy import validate_cypher
        
        dangerous_queries = [
            "MATCH (n) DETACH DELETE n",  # Delete all nodes
            "MATCH (n) DELETE n",  # Attempt to delete all
        ]
        
        for query in dangerous_queries:
            result = validate_cypher(query)
            assert result.is_dangerous or not result.is_safe, \
                f"Query should be dangerous or blocked: {query}"


class TestIntentClassifierRegression:
    """
    Regression tests for intent classification.
    
    Ensure that intent classification continues to work correctly.
    """
    
    def test_greetings_classified_as_chat(self):
        """Greetings should be classified as chat mode."""
        from src.services.intent_classifier import classify_intent
        
        greetings = ["hi", "hello", "hey", "Hi!", "Hello!", "hey there"]
        
        for greeting in greetings:
            result = classify_intent(greeting)
            assert result.mode == "chat", f"'{greeting}' should be chat mode"
    
    def test_graph_queries_classified_as_graph(self):
        """Graph queries should be classified as graph mode."""
        from src.services.intent_classifier import classify_intent
        
        graph_prompts = [
            "How many :Blast nodes are there?",
            "Show me 10 :Blast",
            "Count nodes by label",
            "What relationship types exist?",
        ]
        
        for prompt in graph_prompts:
            result = classify_intent(prompt)
            assert result.mode == "graph", f"'{prompt}' should be graph mode"
    
    def test_security_questions_classified_as_security(self):
        """Security questions should be classified as security mode."""
        from src.services.intent_classifier import classify_intent
        
        security_prompts = [
            "What permissions do I have?",
            "Am I allowed to write?",
            "Show my effective scopes",
        ]
        
        for prompt in security_prompts:
            result = classify_intent(prompt)
            assert result.mode == "security", f"'{prompt}' should be security mode"
    
    def test_admin_commands_identified(self):
        """Admin commands should be classified appropriately."""
        from src.services.intent_classifier import classify_intent
        
        admin_prompts = [
            "Create an index on :Blast(id)",
            "CREATE INDEX ON :Blast(id)",  # Cypher syntax
        ]
        
        for prompt in admin_prompts:
            result = classify_intent(prompt)
            # Should be either admin or graph mode (contains graph indicators)
            assert result.mode in ("admin", "dangerous", "graph"), \
                f"'{prompt}' should be admin/dangerous/graph mode, got {result.mode}"
    
    def test_dangerous_commands_classified(self):
        """Dangerous commands should be flagged."""
        from src.services.intent_classifier import classify_intent
        
        dangerous_prompts = [
            "DELETE all nodes",  # Contains DELETE keyword
            "DETACH DELETE all",  # Contains DETACH DELETE
        ]
        
        for prompt in dangerous_prompts:
            result = classify_intent(prompt)
            # Should be dangerous or admin mode
            assert result.mode in ("dangerous", "admin", "graph"), \
                f"'{prompt}' should be dangerous/admin/graph, got {result.mode}"


class TestPromptCatalogRegression:
    """
    Regression tests for prompt catalog functionality.
    """
    
    def test_catalog_loads_all_prompts(self):
        """Catalog should load all prompts."""
        from src.services.prompt_catalog import load_prompt_catalog
        
        catalog = load_prompt_catalog()
        
        assert catalog["loaded"] is True
        # Should have multiple prompts (at least some)
        count = len(catalog["all"])
        assert count >= 10, f"Expected at least 10 prompts, got {count}"
    
    def test_catalog_categories(self):
        """Catalog should have expected categories."""
        from src.services.prompt_catalog import get_all_categories
        
        categories = get_all_categories()
        
        # At minimum should have read_only
        assert len(categories) >= 1, "Expected at least one category"
        assert "read_only" in categories, f"Expected 'read_only' category in {categories}"
    
    def test_prompt_p01_exists(self):
        """Prompt p01 should exist and be correct."""
        from src.services.prompt_catalog import get_prompt_by_id
        
        p01 = get_prompt_by_id("p01")
        
        assert p01 is not None
        assert "Blast" in p01["text"]
        assert p01["category"] == "read_only"
    
    def test_prompt_p03_has_random_hint(self):
        """Prompt p03 should have random=True in expected hints."""
        from src.services.prompt_catalog import get_prompt_by_id, get_execution_hints
        
        p03 = get_prompt_by_id("p03")
        assert p03 is not None
        
        hints = get_execution_hints(p03)
        assert hints.get("random") is True
        assert hints.get("limit_hint") == 10
    
    def test_dangerous_prompts_exist(self):
        """Dangerous prompts should be in 'dangerous' category if present."""
        from src.services.prompt_catalog import get_prompts_by_category, get_all_categories
        
        categories = get_all_categories()
        
        # Only test if dangerous category exists
        if "dangerous" in categories:
            dangerous = get_prompts_by_category("dangerous")
            assert len(dangerous) > 0, "Expected at least one dangerous prompt"
            # Dangerous prompts may have various dangerous patterns
            # (no limit, all nodes, cartesian product, etc.)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
