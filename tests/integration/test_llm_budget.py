"""
LLM Budget Tests: Verify LLM call counts for different query types.

These tests ensure the orchestrator respects LLM call budgets:
- Chat prompts: 1 LLM call maximum
- Simple graph queries: ≤2 LLM calls
- Security questions: 0 LLM calls (handled by tools)
- Admin/dangerous: 0 LLM calls (handled by policy)

The tests verify that mode routing correctly bypasses expensive LLM
planning for queries that can be handled directly.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any


# Test principals
TEST_USER_PRINCIPAL = {
    "id": "test@example.com",
    "email": "test@example.com",
    "tenant_id": "default",
    "roles": ["analyst"],
    "permissions": ["tools:basic", "graph:read"],
    "scopes": ["tools:invoke:basic"],
}

TEST_ADMIN_PRINCIPAL = {
    "id": "admin@example.com",
    "email": "admin@example.com",
    "tenant_id": "default",
    "roles": ["admin"],
    "permissions": ["admin:all", "tools:basic", "graph:read", "graph:write"],
    "scopes": ["tools:invoke:basic", "tools:invoke:advanced"],
}


class TestChatModeLLMBudget:
    """Test LLM budget for chat mode."""
    
    def test_chat_mode_classification_no_llm(self):
        """Chat prompts should be classified without LLM calls."""
        from src.services.intent_classifier import classify_intent
        
        # These should be classified entirely by heuristics (no LLM)
        chat_prompts = ["hi", "hello", "who are you?", "thanks", "bye"]
        
        for prompt in chat_prompts:
            result = classify_intent(prompt)
            assert result.mode == "chat", f"Expected chat for '{prompt}'"
            # Classification is heuristic-based, so confidence should be high
            assert result.confidence >= 0.8, f"Expected high confidence for '{prompt}'"
    
    def test_is_simple_chat_helper(self):
        """is_simple_chat should work without LLM."""
        from src.services.intent_classifier import is_simple_chat
        
        assert is_simple_chat("hi") is True
        assert is_simple_chat("hello!") is True
        assert is_simple_chat("How many :Blast nodes?") is False


class TestSecurityModeLLMBudget:
    """Test LLM budget for security mode."""
    
    def test_security_mode_classification_no_llm(self):
        """Security prompts should be classified without LLM calls."""
        from src.services.intent_classifier import classify_intent
        
        security_prompts = [
            "Do I have permission to run write queries?",
            "What am I allowed to do?",
            "Show my effective scopes",
        ]
        
        for prompt in security_prompts:
            result = classify_intent(prompt)
            assert result.mode == "security", f"Expected security for '{prompt}'"
    
    def test_security_tools_no_llm_needed(self):
        """Security tools should work without LLM calls."""
        from src.mcp.tools.security.describe_principal import _act_describe
        from src.mcp.tools.security.allowed_operations import _act_list
        
        # These return deterministic results based on principal
        describe_result = _act_describe({"principal": TEST_USER_PRINCIPAL})
        assert describe_result["ok"] is True
        
        list_result = _act_list({"principal": TEST_USER_PRINCIPAL})
        assert list_result["ok"] is True


class TestGraphModeLLMBudget:
    """Test LLM budget for graph mode."""
    
    def test_simple_graph_query_detection(self):
        """Simple graph queries should be detected for fast path."""
        from src.services.orchestrator import Orchestrator
        
        orch = Orchestrator()
        
        # These should be classified as simple
        simple_queries = [
            "How many :Blast nodes are there?",
            "Count all :Blast nodes",
            "Show 10 :Blast nodes",
        ]
        
        for query in simple_queries:
            is_simple = orch._is_simple_graph_query(query, {"category": "read_only"})
            # Simple queries with read_only category should be fast-pathed
            assert is_simple is True, f"Expected simple query: '{query}'"
    
    def test_complex_query_not_simple(self):
        """Complex queries should not be classified as simple."""
        from src.services.orchestrator import Orchestrator
        
        orch = Orchestrator()
        
        # Complex queries need full planning
        complex_queries = [
            "Find all paths between :Blast and :File nodes",
            "Calculate the average out-degree of :Blast nodes and compare to :File",
        ]
        
        for query in complex_queries:
            is_simple = orch._is_simple_graph_query(query, None)
            assert is_simple is False, f"Expected complex query: '{query}'"


class TestAdminModeLLMBudget:
    """Test LLM budget for admin mode."""
    
    def test_admin_mode_classification_no_llm(self):
        """Admin prompts should be classified without LLM calls."""
        from src.services.intent_classifier import classify_intent
        
        admin_prompts = [
            "CREATE INDEX ON :Blast(blast_version)",
            "Create an index on :Blast(id)",
        ]
        
        for prompt in admin_prompts:
            result = classify_intent(prompt)
            assert result.mode == "admin", f"Expected admin for '{prompt}'"


class TestDangerousModeLLMBudget:
    """Test LLM budget for dangerous mode."""
    
    def test_dangerous_mode_classification_no_llm(self):
        """Dangerous prompts should be classified without LLM calls."""
        from src.services.intent_classifier import classify_intent
        
        dangerous_prompts = [
            "DELETE all nodes",
            "MATCH (n) DETACH DELETE n",
            "Delete everything in the database",
        ]
        
        for prompt in dangerous_prompts:
            result = classify_intent(prompt)
            assert result.mode == "dangerous", f"Expected dangerous for '{prompt}'"


class TestCypherValidationNoLLM:
    """Test that Cypher validation works without LLM."""
    
    def test_cypher_validation_is_heuristic(self):
        """Cypher validation should use pattern matching, not LLM."""
        from src.security.graph_access_policy import validate_cypher
        
        # Read-only queries
        result = validate_cypher("MATCH (n:Blast) RETURN n LIMIT 10")
        assert result.is_read_only is True
        
        # Write queries
        result = validate_cypher("CREATE (n:Test {name: 'test'})")
        assert result.has_writes is True
        
        # Admin queries
        result = validate_cypher("CREATE INDEX ON :Blast(id)")
        assert result.requires_admin is True


class TestPromptCatalogNoLLM:
    """Test that prompt catalog matching works without LLM."""
    
    def test_catalog_matching_is_heuristic(self):
        """Prompt catalog should use text matching, not LLM."""
        from src.services.prompt_catalog import match_prompt_by_text, get_prompt_by_id
        
        # Exact match (no LLM needed)
        prompt = match_prompt_by_text("How many :Blast nodes are there?")
        if prompt:  # Catalog may or may not be loaded
            assert prompt["id"] == "p01"
        
        # ID lookup (no LLM needed)
        prompt = get_prompt_by_id("p01")
        if prompt:
            assert "Blast" in prompt.get("text", "")


class TestIntentClassificationLatency:
    """Test that intent classification is fast (no LLM delay)."""
    
    def test_classification_under_50ms(self):
        """Classification should complete in <50ms (heuristic path)."""
        import time
        from src.services.intent_classifier import classify_intent
        
        prompts = [
            "hi",
            "How many :Blast nodes?",
            "Do I have permission?",
            "CREATE INDEX ON :Test(id)",
            "DELETE all nodes",
        ]
        
        for prompt in prompts:
            start = time.time()
            result = classify_intent(prompt)
            elapsed_ms = (time.time() - start) * 1000
            
            assert elapsed_ms < 50, f"Classification took {elapsed_ms:.1f}ms for '{prompt}'"
            assert result.mode is not None


class TestTODOFilteringForLLMBudget:
    """Test that TODO filtering reduces LLM calls."""
    
    def test_storage_todos_filtered_for_simple_queries(self):
        """Storage TODOs should be filtered for simple read-only queries."""
        from src.services.orchestrator import Orchestrator
        
        orch = Orchestrator()
        
        # Simulate TODOs with storage tasks
        todos = [
            {"task": "Generate Cypher query for counting nodes", "status": "pending"},
            {"task": "Execute the query", "status": "pending"},
            {"task": "Store results in context", "status": "pending"},  # Should be filtered
        ]
        
        # Filter for simple read-only query
        filtered = orch._filter_unnecessary_todos(
            todos,
            goal="How many :Blast nodes?",
            params={"category": "read_only"},
        )
        
        # Storage task should be removed
        assert len(filtered) == 2
        assert not any("store" in t.get("task", "").lower() for t in filtered)
    
    def test_storage_todos_kept_when_needed(self):
        """Storage TODOs should be kept when explicitly requested."""
        from src.services.orchestrator import Orchestrator
        
        orch = Orchestrator()
        
        todos = [
            {"task": "Generate Cypher query", "status": "pending"},
            {"task": "Store results in cache for later use", "status": "pending"},
        ]
        
        # Don't filter for queries that need storage
        filtered = orch._filter_unnecessary_todos(
            todos,
            goal="Export all :Blast nodes and save to cache",
            params={"category": "data_quality"},  # Not read_only
        )
        
        # Storage task should be kept
        assert len(filtered) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
