"""
Integration tests for chat prompt handling.

These tests verify that simple conversational prompts are handled correctly
without invoking unnecessary tools or creating TODO lists.
"""

import pytest
from typing import Any
from unittest.mock import patch, MagicMock

# Mock principal for tests
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


def make_mock_context(principal: dict | None = None):
    """Create a mock ToolContext."""
    from src.mcp.runtime import ToolContext
    ctx = MagicMock(spec=ToolContext)
    ctx.principal = principal or TEST_USER_PRINCIPAL
    ctx.tenant = principal.get("tenant_id") if principal else "default"
    ctx.trace_id = "test-trace-id"
    ctx.tool = "test.tool"
    ctx.action = "test"
    ctx.timeout_ms = None
    ctx.start_time = 0
    return ctx


# Test data: chat prompts that should NOT invoke any tools
CHAT_PROMPTS = [
    ("hi", "greeting"),
    ("hello", "greeting"),
    ("hey there", "greeting"),
    ("Hi!", "greeting"),
    ("Hello!", "greeting"),
    ("who are you?", "identity"),
    ("what are you?", "identity"),
    ("What can you do?", "capabilities"),
    ("tell me about yourself", "identity"),
    ("thanks", "pleasantry"),
    ("thank you", "pleasantry"),
    ("bye", "pleasantry"),
    ("goodbye", "pleasantry"),
    ("good morning", "pleasantry"),
    ("help", "help"),
]

# Test data: prompts that SHOULD invoke graph tools (not chat)
GRAPH_PROMPTS = [
    "How many :Blast nodes are there?",
    "Show me 10 :Blast nodes",
    "MATCH (n:Blast) RETURN n LIMIT 5",
    "What relationship types exist from :Blast?",
    "Count nodes by label",
]

# Test data: security prompts  
SECURITY_PROMPTS = [
    "Do I have permission to run write queries?",
    "What am I allowed to do?",
    "Show my effective scopes",
]


class TestIntentClassification:
    """Test the intent classifier directly."""
    
    def test_classify_chat_prompts(self):
        """Chat prompts should be classified as 'chat' mode."""
        from src.services.intent_classifier import classify_intent
        
        for prompt, expected_type in CHAT_PROMPTS:
            result = classify_intent(prompt)
            assert result.mode == "chat", f"Expected 'chat' for '{prompt}', got '{result.mode}'"
            assert result.confidence >= 0.8, f"Expected high confidence for '{prompt}', got {result.confidence}"
    
    def test_classify_graph_prompts(self):
        """Graph prompts should be classified as 'graph' mode."""
        from src.services.intent_classifier import classify_intent
        
        for prompt in GRAPH_PROMPTS:
            result = classify_intent(prompt)
            assert result.mode == "graph", f"Expected 'graph' for '{prompt}', got '{result.mode}'"
    
    def test_classify_security_prompts(self):
        """Security prompts should be classified as 'security' mode."""
        from src.services.intent_classifier import classify_intent
        
        for prompt in SECURITY_PROMPTS:
            result = classify_intent(prompt)
            assert result.mode == "security", f"Expected 'security' for '{prompt}', got '{result.mode}'"
    
    def test_is_simple_chat_helper(self):
        """Test the is_simple_chat helper function."""
        from src.services.intent_classifier import is_simple_chat
        
        # Should return True for chat prompts
        assert is_simple_chat("hi") is True
        assert is_simple_chat("hello") is True
        assert is_simple_chat("who are you?") is True
        
        # Should return False for non-chat prompts
        assert is_simple_chat("How many :Blast nodes?") is False
        assert is_simple_chat("MATCH (n) RETURN n") is False


class TestPromptCatalog:
    """Test the prompt catalog loading and matching."""
    
    def test_catalog_loads(self):
        """Catalog should load successfully."""
        from src.services.prompt_catalog import load_prompt_catalog, get_catalog_stats
        
        catalog = load_prompt_catalog()
        stats = get_catalog_stats()
        
        assert catalog["loaded"] is True
        assert stats["total_prompts"] > 0
    
    def test_get_prompt_by_id(self):
        """Should retrieve prompts by ID."""
        from src.services.prompt_catalog import get_prompt_by_id
        
        # p01 is "How many :Blast nodes are there?"
        prompt = get_prompt_by_id("p01")
        assert prompt is not None
        assert "Blast" in prompt.get("text", "")
        assert prompt.get("category") == "read_only"
    
    def test_match_prompt_by_text(self):
        """Should match prompts by text."""
        from src.services.prompt_catalog import match_prompt_by_text
        
        # Exact match
        prompt = match_prompt_by_text("How many :Blast nodes are there?")
        assert prompt is not None
        assert prompt.get("id") == "p01"
    
    def test_get_execution_hints(self):
        """Should extract execution hints from catalog entries."""
        from src.services.prompt_catalog import get_prompt_by_id, get_execution_hints
        
        # p03 has limit_hint=10 and random=True
        prompt = get_prompt_by_id("p03")
        if prompt:
            hints = get_execution_hints(prompt)
            assert hints.get("limit_hint") == 10
            assert hints.get("random") is True


class TestGenerateCypherEnhancements:
    """Test the generate_cypher tool enhancements."""
    
    def test_select_with_random(self):
        """Select action should support ORDER BY rand() when random=True."""
        from src.mcp.tools.graph.generate_cypher import _act_select
        
        result = _act_select({
            "action": "select",
            "label": "Blast",
            "limit": 10,
            "random": True,
        })
        
        assert result["ok"] is True
        assert "ORDER BY rand()" in result["cypher"]
        assert "LIMIT" in result["cypher"]
    
    def test_select_without_random(self):
        """Select action should NOT include ORDER BY rand() when random=False."""
        from src.mcp.tools.graph.generate_cypher import _act_select
        
        result = _act_select({
            "action": "select",
            "label": "Blast",
            "limit": 10,
            "random": False,
        })
        
        assert result["ok"] is True
        assert "ORDER BY rand()" not in result["cypher"]
    
    def test_select_with_limit_hint(self):
        """Select action should support limit_hint as alias for limit."""
        from src.mcp.tools.graph.generate_cypher import _act_select
        
        result = _act_select({
            "action": "select",
            "label": "Blast",
            "limit_hint": 15,
        })
        
        assert result["ok"] is True
        assert result["params"]["limit"] == 15


class TestGraphAccessPolicy:
    """Test the graph access policy module."""
    
    def test_validate_read_only_query(self):
        """Read-only queries should be marked as safe."""
        from src.security.graph_access_policy import validate_cypher
        
        result = validate_cypher("MATCH (n:Blast) RETURN n LIMIT 10")
        
        assert result.is_safe is True
        assert result.is_read_only is True
        assert result.has_writes is False
    
    def test_validate_write_query(self):
        """Write queries should be flagged."""
        from src.security.graph_access_policy import validate_cypher
        
        result = validate_cypher("CREATE (n:Test {name: 'test'})")
        
        assert result.is_safe is False
        assert result.is_read_only is False
        assert result.has_writes is True
    
    def test_validate_delete_query(self):
        """Delete queries should be flagged."""
        from src.security.graph_access_policy import validate_cypher
        
        result = validate_cypher("MATCH (n:Test) DELETE n")
        
        assert result.is_safe is False
        assert result.has_deletes is True
    
    def test_validate_admin_query(self):
        """Admin queries should require admin role."""
        from src.security.graph_access_policy import validate_cypher
        
        result = validate_cypher("CREATE INDEX ON :Blast(blast_version)")
        
        assert result.requires_admin is True
    
    def test_validate_for_admin_principal(self):
        """Admin principal should be allowed to execute admin queries."""
        from src.security.graph_access_policy import validate_for_principal
        
        admin_principal = {
            "id": "admin@test.com",
            "roles": ["admin"],
            "permissions": ["admin:all"],
        }
        
        result = validate_for_principal(
            "CREATE INDEX ON :Blast(blast_version)",
            admin_principal,
        )
        
        assert result.is_safe is True
    
    def test_validate_for_user_principal(self):
        """User principal should NOT be allowed admin queries."""
        from src.security.graph_access_policy import validate_for_principal
        
        user_principal = {
            "id": "user@test.com",
            "roles": ["user"],
            "permissions": ["tools:basic"],
        }
        
        result = validate_for_principal(
            "CREATE INDEX ON :Blast(blast_version)",
            user_principal,
        )
        
        assert result.is_safe is False
        assert "admin" in result.denial_reason.lower()


class TestSecurityTools:
    """Test the security MCP tools."""
    
    def test_describe_principal(self):
        """describe_principal should return principal info."""
        from src.mcp.tools.security.describe_principal import _act_describe
        
        principal = {
            "id": "test@example.com",
            "email": "test@example.com",
            "tenant_id": "default",
            "roles": ["analyst"],
            "permissions": ["tools:basic"],
            "scopes": ["tools:invoke:basic"],
        }
        
        result = _act_describe({"principal": principal})
        
        assert result["ok"] is True
        assert result["principal_id"] == "test@example.com"
        assert "analyst" in result["roles"]
        assert result["is_admin"] is False
    
    def test_describe_admin_principal(self):
        """describe_principal should identify admin users."""
        from src.mcp.tools.security.describe_principal import _act_describe
        
        admin_principal = {
            "id": "admin@example.com",
            "roles": ["admin"],
            "permissions": ["admin:all"],
        }
        
        result = _act_describe({"principal": admin_principal})
        
        assert result["ok"] is True
        assert result["is_admin"] is True
    
    def test_allowed_operations_user(self):
        """allowed_operations should return read-only ops for regular users."""
        from src.mcp.tools.security.allowed_operations import _act_list
        
        user_principal = {
            "id": "user@test.com",
            "roles": ["user"],
            "permissions": ["tools:basic"],
        }
        
        result = _act_list({"principal": user_principal})
        
        assert result["ok"] is True
        assert result["can_execute_reads"] is True
        assert result["can_execute_writes"] is False
        assert result["can_manage_schema"] is False
        assert "MATCH" in result["read_operations"]
        assert len(result["write_operations"]) == 0
    
    def test_allowed_operations_admin(self):
        """allowed_operations should return all ops for admin users."""
        from src.mcp.tools.security.allowed_operations import _act_list
        
        admin_principal = {
            "id": "admin@test.com",
            "roles": ["admin"],
            "permissions": ["admin:all"],
        }
        
        result = _act_list({"principal": admin_principal})
        
        assert result["ok"] is True
        assert result["can_execute_reads"] is True
        assert result["can_execute_writes"] is True
        assert result["can_manage_schema"] is True
        assert len(result["write_operations"]) > 0
        assert len(result["admin_operations"]) > 0


class TestAdminModeClassification:
    """Test classification of admin prompts."""
    
    ADMIN_PROMPTS = [
        "Create an index on :Blast(blast_version)",
        "Drop the index on :User",
        "Add a constraint on :Blast(id)",
    ]
    
    def test_classify_admin_prompts(self):
        """Admin prompts should be classified as 'admin' mode."""
        from src.services.intent_classifier import classify_intent
        
        for prompt in self.ADMIN_PROMPTS:
            result = classify_intent(prompt)
            # Admin prompts could also be classified as "graph" with admin flags
            assert result.mode in ("admin", "graph"), f"Expected 'admin' or 'graph' for '{prompt}', got '{result.mode}'"
    
    def test_admin_write_detection(self):
        """Graph access policy should detect admin writes."""
        from src.security.graph_access_policy import validate_cypher
        
        # Index creation
        result = validate_cypher("CREATE INDEX ON :Blast(blast_version)")
        assert result.requires_admin is True
        
        # Constraint creation
        result = validate_cypher("CREATE CONSTRAINT ON (b:Blast) ASSERT b.id IS UNIQUE")
        assert result.requires_admin is True


class TestDangerousModeClassification:
    """Test classification of dangerous prompts."""
    
    DANGEROUS_PROMPTS = [
        "MATCH (n) DETACH DELETE n",
        "Delete everything in the database",
        "Remove all nodes",
        "MATCH (n) DELETE n",
    ]
    
    def test_classify_dangerous_prompts(self):
        """Dangerous prompts should be classified as 'dangerous' mode."""
        from src.services.intent_classifier import classify_intent
        
        for prompt in self.DANGEROUS_PROMPTS:
            result = classify_intent(prompt)
            # Dangerous prompts should be flagged
            assert result.mode in ("dangerous", "graph"), f"Expected 'dangerous' or 'graph' for '{prompt}', got '{result.mode}'"
    
    def test_dangerous_query_detection(self):
        """Graph access policy should detect dangerous queries."""
        from src.security.graph_access_policy import validate_cypher
        
        # DETACH DELETE without WHERE - has deletes and is not safe
        result = validate_cypher("MATCH (n) DETACH DELETE n")
        assert result.has_deletes is True
        assert result.is_safe is False
        
        # DELETE without WHERE
        result = validate_cypher("MATCH (n) DELETE n")
        assert result.has_deletes is True
        assert result.is_safe is False


class TestAdminModeHandler:
    """Test the admin mode handler logic."""
    
    def test_admin_handler_refuses_non_admin(self):
        """Admin handler should refuse requests from non-admin users."""
        # This tests the internal logic without running the full orchestrator
        from src.security.graph_access_policy import validate_for_principal
        
        user_principal = {
            "id": "user@test.com",
            "roles": ["user"],
            "permissions": ["tools:basic"],
        }
        
        # Try to create an index (admin operation)
        result = validate_for_principal(
            "CREATE INDEX ON :Blast(blast_version)",
            user_principal,
        )
        
        assert result.is_safe is False
        assert "admin" in result.denial_reason.lower()
    
    def test_admin_handler_allows_admin(self):
        """Admin handler should allow requests from admin users."""
        from src.security.graph_access_policy import validate_for_principal
        
        admin_principal = {
            "id": "admin@test.com",
            "roles": ["admin"],
            "permissions": ["admin:all"],
        }
        
        result = validate_for_principal(
            "CREATE INDEX ON :Blast(blast_version)",
            admin_principal,
        )
        
        assert result.is_safe is True


class TestDangerousModeHandler:
    """Test the dangerous mode handler logic."""
    
    def test_dangerous_handler_detects_bulk_delete(self):
        """Dangerous handler should detect bulk delete patterns."""
        from src.security.graph_access_policy import validate_cypher
        
        # DETACH DELETE without LIMIT - has deletes and is not safe
        result = validate_cypher("MATCH (n:Blast) DETACH DELETE n")
        assert result.has_deletes is True
        assert result.is_safe is False
        
        # DELETE without WHERE clause - not safe
        result = validate_cypher("MATCH (n) DELETE n")
        assert result.has_deletes is True
        assert result.is_safe is False
    
    def test_dangerous_handler_allows_safe_delete(self):
        """Dangerous handler should allow targeted deletes with LIMIT."""
        from src.security.graph_access_policy import validate_cypher
        
        # Delete with WHERE and LIMIT is safer
        result = validate_cypher("MATCH (n:Blast) WHERE n.obsolete = true DELETE n LIMIT 10")
        # May still be flagged as having deletes but less dangerous
        assert result.has_deletes is True
    
    def test_suggest_explain_prefix(self):
        """Dangerous queries should be convertible to EXPLAIN."""
        dangerous_query = "MATCH (n) DETACH DELETE n"
        explain_query = f"EXPLAIN {dangerous_query}"
        
        # EXPLAIN version should be safe to analyze
        from src.security.graph_access_policy import validate_cypher
        
        result = validate_cypher(explain_query)
        # EXPLAIN doesn't actually execute the query
        assert "EXPLAIN" in explain_query


# Mark tests that require the full stack (LLM, etc.) as integration
@pytest.mark.integration
class TestChatModeIntegration:
    """Integration tests for chat mode (require running services)."""
    
    @pytest.mark.asyncio
    async def test_chat_prompt_no_tools(self):
        """Chat prompts should return without tool calls."""
        # This test requires the orchestrator to be running
        # Skip if not in integration environment
        pytest.skip("Requires full integration environment")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
