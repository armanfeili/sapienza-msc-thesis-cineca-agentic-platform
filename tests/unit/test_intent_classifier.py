"""
Unit tests for the intent classifier module.

Tests cover:
- IntentMode enum behavior
- Core classification functionality
- Simple chat detection (critical for routing)
- Dangerous operation detection
- The original 309s greeting bug regression
"""

import pytest
from unittest.mock import MagicMock, patch
import time

from src.services.intent_classifier import (
    IntentMode,
    ClassificationSource,
    IntentClassification,
    classify_intent,
    is_simple_chat,
    is_graph_query,
    requires_admin,
    is_security_question,
    is_dangerous_operation,
)


# ──────────────────────────────────────────────────────────────────────────────
# IntentMode Enum Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestIntentModeEnum:
    """Tests for IntentMode enum."""

    def test_mode_values_are_strings(self):
        """IntentMode values should be lowercase strings."""
        assert IntentMode.CHAT == "chat"
        assert IntentMode.GRAPH == "graph"
        assert IntentMode.SECURITY == "security"
        assert IntentMode.ADMIN == "admin"
        assert IntentMode.DANGEROUS == "dangerous"

    def test_mode_is_str_subclass(self):
        """IntentMode should be a str subclass for JSON serialization."""
        assert isinstance(IntentMode.CHAT, str)
        assert isinstance(IntentMode.GRAPH, str)

    def test_mode_string_comparison(self):
        """Mode should compare equal to plain strings."""
        assert IntentMode.CHAT == "chat"
        assert "chat" == IntentMode.CHAT
        assert IntentMode.GRAPH != "chat"

    def test_mode_in_dict(self):
        """Mode should work as dict key and value."""
        d = {"mode": IntentMode.CHAT}
        assert d["mode"] == "chat"
        assert d["mode"] == IntentMode.CHAT


class TestClassificationSource:
    """Tests for ClassificationSource enum."""

    def test_source_values(self):
        """ClassificationSource values should be correct."""
        assert ClassificationSource.PATTERNS == "patterns"
        assert ClassificationSource.CATALOG == "catalog"
        assert ClassificationSource.LLM == "llm"
        assert ClassificationSource.DEFAULT == "default"
        assert ClassificationSource.CONVERSATIONAL == "conversational"


# ──────────────────────────────────────────────────────────────────────────────
# Chat Mode Classification Tests - CRITICAL for routing
# ──────────────────────────────────────────────────────────────────────────────


class TestChatModeClassification:
    """Tests for chat mode classification - most important for routing."""

    @pytest.mark.parametrize(
        "prompt",
        [
            # Simple greetings - must be CHAT mode
            "Hi",
            "Hello",
            "Hey",
            "Good morning",
            "Good afternoon",
            "Good evening",
            # Compound greetings (the original 309s bug case)
            "Hi, how are you?",
            "Hello, what's your name?",
            "Hey there, how can you help me?",
            "Hi, how are you? What's your name?",
            # Thank you patterns
            "Thank you",
            "Thanks!",
            # Conversational questions
            "How are you?",
            "What's your name?",
            "Who are you?",
            "What can you do?",
        ],
    )
    def test_chat_prompts_classified_as_chat(self, prompt):
        """Chat prompts should be classified with CHAT mode."""
        result = classify_intent(prompt)
        assert result.mode == IntentMode.CHAT, f"Expected CHAT for '{prompt}', got {result.mode}"
        # Confidence should be enough for chat routing (threshold is 0.6)
        assert result.confidence >= 0.6, f"Confidence too low for chat routing: {result.confidence}"

    @pytest.mark.parametrize(
        "prompt",
        [
            "Hi",
            "Hello",
            "Hey there",
            "Good morning!",
            "Thanks",
            "Thank you!",
            "How are you?",
            "What's up?",
        ],
    )
    def test_is_simple_chat_returns_true(self, prompt):
        """is_simple_chat should return True for simple conversational prompts."""
        assert is_simple_chat(prompt) is True

    def test_non_chat_prompt_is_not_simple_chat(self):
        """Non-chat prompts should not be simple chat."""
        assert is_simple_chat("MATCH (n) RETURN n") is False
        assert is_simple_chat("Delete all nodes") is False


# ──────────────────────────────────────────────────────────────────────────────
# Dangerous Operation Detection Tests - CRITICAL for safety
# ──────────────────────────────────────────────────────────────────────────────


class TestDangerousOperationDetection:
    """Tests for dangerous operation detection - critical for safety."""

    @pytest.mark.parametrize(
        "prompt",
        [
            "Delete all nodes",
            "Remove all data",
            "DETACH DELETE n",
            "Delete all users",
            "Purge the entire graph",
        ],
    )
    def test_dangerous_prompts_detected(self, prompt):
        """Dangerous operations should be classified as DANGEROUS mode."""
        result = classify_intent(prompt)
        assert result.mode == IntentMode.DANGEROUS, f"Expected DANGEROUS for '{prompt}', got {result.mode}"

    @pytest.mark.parametrize(
        "prompt",
        [
            "Delete all nodes",
            "DETACH DELETE n",
            "DROP ALL",
        ],
    )
    def test_is_dangerous_operation(self, prompt):
        """is_dangerous_operation helper should detect dangerous prompts."""
        assert is_dangerous_operation(prompt) is True

    def test_safe_prompt_not_dangerous(self):
        """Safe prompts should not be detected as dangerous."""
        assert is_dangerous_operation("List all nodes") is False
        assert is_dangerous_operation("Hello") is False


# ──────────────────────────────────────────────────────────────────────────────
# Graph Query Detection Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestGraphQueryDetection:
    """Tests for graph query detection."""

    @pytest.mark.parametrize(
        "prompt",
        [
            "MATCH (n) RETURN n",
            "MATCH (n) RETURN n LIMIT 10",
            "match (a)-[r]->(b) return a,r,b",
            "OPTIONAL MATCH (x) RETURN x",
        ],
    )
    def test_cypher_queries_classified_as_graph(self, prompt):
        """Direct Cypher queries should be classified as GRAPH mode."""
        result = classify_intent(prompt)
        assert result.mode == IntentMode.GRAPH, f"Expected GRAPH for '{prompt}', got {result.mode}"

    def test_is_graph_query_helper(self):
        """is_graph_query helper should detect graph queries."""
        assert is_graph_query("MATCH (n) RETURN n") is True
        assert is_graph_query("Hello") is False


# ──────────────────────────────────────────────────────────────────────────────
# IntentClassification Dataclass Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestIntentClassificationDataclass:
    """Tests for IntentClassification dataclass."""

    def test_dataclass_creation(self):
        """IntentClassification should be created with all fields."""
        ic = IntentClassification(
            mode=IntentMode.CHAT,
            confidence=0.95,
            reasoning="Matched greeting pattern",
            source=ClassificationSource.PATTERNS,
        )
        assert ic.mode == IntentMode.CHAT
        assert ic.confidence == 0.95
        assert ic.reasoning == "Matched greeting pattern"
        assert ic.source == ClassificationSource.PATTERNS

    def test_dataclass_to_log_dict(self):
        """IntentClassification should have a to_log_dict method."""
        ic = IntentClassification(
            mode=IntentMode.CHAT,
            confidence=0.9,
            reasoning="Test",
        )
        log_dict = ic.to_log_dict()
        assert log_dict["mode"] == "chat"
        assert log_dict["confidence"] == 0.9
        assert log_dict["source"] == "patterns"


# ──────────────────────────────────────────────────────────────────────────────
# Catalog Integration Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCatalogIntegration:
    """Tests for prompt catalog integration."""

    def test_catalog_match_boosts_confidence(self):
        """A catalog match should boost classification confidence."""
        catalog_entry = {
            "id": "list_projects",
            "prompt": "List all projects",
            "category": "read_only",
        }
        result = classify_intent("List all projects", catalog_match=catalog_entry)
        # Catalog match should give high confidence
        assert result.confidence >= 0.9
        assert result.matched_catalog_id == "list_projects"


# ──────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ──────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases."""

    def test_very_long_prompt(self):
        """Very long prompts should be handled without errors."""
        long_prompt = "Hello " * 1000
        result = classify_intent(long_prompt)
        assert result.mode is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_unicode_prompt(self):
        """Unicode prompts should be handled correctly."""
        result = classify_intent("こんにちは")  # Japanese "Hello"
        assert result.mode is not None

    def test_mixed_case_prompt(self):
        """Classification should be case-insensitive for greetings."""
        result1 = classify_intent("HELLO")
        result2 = classify_intent("hello")
        result3 = classify_intent("HeLLo")
        assert result1.mode == result2.mode == result3.mode == IntentMode.CHAT

    def test_prompt_with_special_characters(self):
        """Prompts with special characters should be handled."""
        result = classify_intent("Hello! How are you??? :)")
        assert result.mode == IntentMode.CHAT


# ──────────────────────────────────────────────────────────────────────────────
# Performance Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPerformance:
    """Performance-related tests."""

    def test_classification_is_fast(self):
        """Classification should complete quickly (under 100ms)."""
        prompts = [
            "Hi",
            "MATCH (n) RETURN n",
            "What permissions do I have?",
            "Create a node",
            "Delete everything",
        ]

        start = time.time()
        for prompt in prompts:
            for _ in range(100):
                classify_intent(prompt)
        elapsed = time.time() - start

        # 500 classifications should complete in under 1 second
        assert elapsed < 1.0, f"Classification too slow: {elapsed:.2f}s for 500 calls"


# ──────────────────────────────────────────────────────────────────────────────
# CRITICAL Regression Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestRegressions:
    """Regression tests for previously fixed bugs."""

    def test_compound_greeting_309s_bug(self):
        """
        CRITICAL Regression test for the 309-second response time bug.
        
        The prompt "Hi, how are you? What's your name?" was not matching
        any chat pattern and defaulting to the full TODO planning pipeline,
        causing a 309-second response time for a simple greeting.
        """
        prompt = "Hi, how are you? What's your name?"
        result = classify_intent(prompt)
        
        # MUST be CHAT mode
        assert result.mode == IntentMode.CHAT, f"Compound greeting not classified as CHAT: {result}"
        
        # MUST have enough confidence for chat mode routing (threshold is 0.6)
        assert result.confidence >= 0.6, f"Confidence too low for chat mode routing: {result.confidence}"

    def test_greeting_with_question_mark(self):
        """Greetings followed by questions should still be CHAT mode."""
        prompts = [
            "Hi, how are you?",
            "Hello, what can you do?",
            "Hey! Can you help me?",
        ]
        for prompt in prompts:
            result = classify_intent(prompt)
            assert result.mode == IntentMode.CHAT, f"'{prompt}' not classified as CHAT: {result}"
            assert result.confidence >= 0.6, f"Confidence too low for '{prompt}': {result.confidence}"

    def test_simple_hi_is_chat(self):
        """Simple 'Hi' should definitely be CHAT mode with high confidence."""
        result = classify_intent("Hi")
        assert result.mode == IntentMode.CHAT
        assert result.confidence >= 0.9
