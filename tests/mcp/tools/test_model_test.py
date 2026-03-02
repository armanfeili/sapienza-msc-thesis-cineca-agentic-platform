"""
Tests for model.test tool (P3 pattern).

Tests internal _act_* functions directly following P3 testing pattern.
"""

from __future__ import annotations

import pytest
from typing import Any, Dict
from unittest.mock import MagicMock, patch

# Import the tool module
from src.mcp.tools.model import test as model_test_module


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_ctx():
    """Mock ToolContext."""
    ctx = MagicMock()
    ctx.principal = "test-user"
    ctx.tenant = "test-tenant"
    ctx.trace_id = "test-trace-123"
    return ctx


@pytest.fixture(autouse=True)
def reset_overrides():
    """Reset _OVERRIDES between tests."""
    model_test_module._OVERRIDES.clear()
    yield
    model_test_module._OVERRIDES.clear()


@pytest.fixture
def mock_adapter():
    """Mock LLMAdapter with typical methods."""
    adapter = MagicMock()
    adapter.provider = "openai"
    adapter.model = "gpt-4"
    adapter.info.return_value = {
        "provider": "openai",
        "model": "gpt-4",
    }
    # Mock chat/complete method
    adapter.chat.return_value = "test response from adapter"
    adapter.embeddings.return_value = [0.1] * 384
    return adapter


# ─────────────────────────────────────────────────────────────────────────────
# Test Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


def test_approx_token_count():
    """Token approximation should use ~4 chars per token heuristic."""
    assert model_test_module._approx_token_count("test") == 1  # 4 chars -> 1 token
    assert model_test_module._approx_token_count("hello world") == 2  # 11 chars -> 2 tokens
    assert model_test_module._approx_token_count("a" * 100) == 25  # 100 chars -> 25 tokens
    assert model_test_module._approx_token_count("") == 1  # Empty -> minimum 1


def test_percentiles():
    """Percentile calculation should be accurate."""
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    result = model_test_module._percentiles(values, percentiles=(50, 90, 99))

    assert "p50" in result
    assert "p90" in result
    assert "p99" in result
    assert 40.0 <= result["p50"] <= 60.0  # Median around 50
    assert 80.0 <= result["p90"] <= 100.0  # 90th percentile high
    assert 90.0 <= result["p99"] <= 100.0  # 99th percentile very high


def test_percentiles_empty():
    """Empty value list should return zeros."""
    result = model_test_module._percentiles([], percentiles=(50, 90))
    assert result == {"p50": 0.0, "p90": 0.0}


def test_deterministic_text_from_seed():
    """Deterministic text generation should be reproducible."""
    text1 = model_test_module._deterministic_text_from_seed("test-seed")
    text2 = model_test_module._deterministic_text_from_seed("test-seed")
    assert text1 == text2  # Same seed -> same output
    assert len(text1) > 0


def test_deterministic_text_different_seeds():
    """Different seeds should produce different text."""
    text1 = model_test_module._deterministic_text_from_seed("seed-1")
    text2 = model_test_module._deterministic_text_from_seed("seed-2")
    # Highly unlikely to be the same
    assert text1 != text2


def test_deterministic_embedding_from_seed():
    """Deterministic embedding generation should be reproducible."""
    vec1 = model_test_module._deterministic_embedding_from_seed("test-seed", dimensions=128)
    vec2 = model_test_module._deterministic_embedding_from_seed("test-seed", dimensions=128)

    assert len(vec1) == 128
    assert vec1 == vec2  # Same seed -> same vector

    # Check normalization (unit vector)
    magnitude = sum(x * x for x in vec1) ** 0.5
    assert abs(magnitude - 1.0) < 0.001  # Should be normalized


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_ping
# ─────────────────────────────────────────────────────────────────────────────


@patch.object(model_test_module, "_adapter")
def test_act_ping_success(mock_adapter_factory, mock_adapter, mock_ctx):
    """ping should return provider and model info."""
    mock_adapter_factory.return_value = mock_adapter

    result = model_test_module._act_ping(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "ping"
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4"


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_canary
# ─────────────────────────────────────────────────────────────────────────────


def test_act_canary_simulate_default(mock_ctx):
    """canary should default to simulate mode."""
    result = model_test_module._act_canary(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "canary"
    assert result["mode"] == "simulate"
    assert "response" in result
    assert len(result["response"]) > 0


def test_act_canary_simulate_deterministic(mock_ctx):
    """canary simulate mode should be deterministic."""
    result1 = model_test_module._act_canary(mock_ctx, {"prompt": "test"})
    result2 = model_test_module._act_canary(mock_ctx, {"prompt": "test"})

    assert result1["response"] == result2["response"]  # Deterministic


def test_act_canary_simulate_different_prompts(mock_ctx):
    """Different prompts should produce different responses in simulate mode."""
    result1 = model_test_module._act_canary(mock_ctx, {"prompt": "hello"})
    result2 = model_test_module._act_canary(mock_ctx, {"prompt": "world"})

    # Different prompts should produce different outputs
    assert result1["response"] != result2["response"]


@patch.object(model_test_module, "_adapter")
def test_act_canary_live_mode(mock_adapter_factory, mock_adapter, mock_ctx):
    """canary with simulate=false should call adapter."""
    mock_adapter_factory.return_value = mock_adapter

    result = model_test_module._act_canary(mock_ctx, {"simulate": False})

    assert result["ok"] is True
    assert result["action"] == "canary"
    assert result["mode"] == "live"
    assert result["response"] == "test response from adapter"


@patch.object(model_test_module, "_adapter")
def test_act_canary_live_error(mock_adapter_factory, mock_adapter, mock_ctx):
    """canary live mode should handle errors gracefully."""
    mock_adapter.chat.side_effect = Exception("Connection failed")
    mock_adapter_factory.return_value = mock_adapter

    result = model_test_module._act_canary(mock_ctx, {"simulate": False})

    assert result["ok"] is False
    assert result["mode"] == "live"
    assert "error" in result


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_tokens
# ─────────────────────────────────────────────────────────────────────────────


def test_act_tokens_approximate_default(mock_ctx):
    """tokens should default to approximate mode."""
    result = model_test_module._act_tokens(mock_ctx, {"text": "hello world test"})

    assert result["ok"] is True
    assert result["action"] == "tokens"
    assert result["mode"] == "approximate"
    assert result["count"] > 0


def test_act_tokens_approximate_calculation(mock_ctx):
    """Approximate token count should use heuristic."""
    text = "a" * 100  # 100 chars -> ~25 tokens
    result = model_test_module._act_tokens(mock_ctx, {"text": text})

    assert result["count"] == 25


@patch.object(model_test_module, "_adapter")
def test_act_tokens_exact_mode(mock_adapter_factory, mock_adapter, mock_ctx):
    """tokens with exact=true should use adapter tokenizer."""
    mock_adapter.count_tokens.return_value = 42
    mock_adapter_factory.return_value = mock_adapter

    result = model_test_module._act_tokens(mock_ctx, {"text": "test", "exact": True})

    assert result["ok"] is True
    assert result["mode"] == "exact"
    assert result["count"] == 42


@patch.object(model_test_module, "_adapter")
def test_act_tokens_exact_fallback(mock_adapter_factory, mock_adapter, mock_ctx):
    """tokens exact mode should fallback to approximate if adapter lacks tokenizer."""
    # No tokenizer method
    del mock_adapter.count_tokens
    del mock_adapter.tokenize
    del mock_adapter.encode
    mock_adapter_factory.return_value = mock_adapter

    result = model_test_module._act_tokens(mock_ctx, {"text": "test" * 10, "exact": True})

    assert result["ok"] is True
    assert result["mode"] == "approximate"
    assert "note" in result


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_embeddings
# ─────────────────────────────────────────────────────────────────────────────


def test_act_embeddings_simulate_default(mock_ctx):
    """embeddings should default to simulate mode."""
    result = model_test_module._act_embeddings(mock_ctx, {"text": "test"})

    assert result["ok"] is True
    assert result["action"] == "embeddings"
    assert result["mode"] == "simulate"
    assert result["dimensions"] > 0
    assert len(result["embedding"]) == result["dimensions"]


def test_act_embeddings_simulate_deterministic(mock_ctx):
    """embeddings simulate mode should be deterministic."""
    result1 = model_test_module._act_embeddings(mock_ctx, {"text": "hello"})
    result2 = model_test_module._act_embeddings(mock_ctx, {"text": "hello"})

    assert result1["embedding"] == result2["embedding"]  # Deterministic


def test_act_embeddings_simulate_normalized(mock_ctx):
    """Simulated embeddings should be normalized unit vectors."""
    result = model_test_module._act_embeddings(mock_ctx, {"text": "test"})

    vec = result["embedding"]
    magnitude = sum(x * x for x in vec) ** 0.5
    assert abs(magnitude - 1.0) < 0.001  # Should be normalized


@patch.object(model_test_module, "_adapter")
def test_act_embeddings_live_mode(mock_adapter_factory, mock_adapter, mock_ctx):
    """embeddings with simulate=false should call adapter."""
    mock_adapter_factory.return_value = mock_adapter

    result = model_test_module._act_embeddings(mock_ctx, {"text": "test", "simulate": False})

    assert result["ok"] is True
    assert result["mode"] == "live"
    assert result["dimensions"] == 384
    assert len(result["embedding"]) == 384


@patch.object(model_test_module, "_adapter")
def test_act_embeddings_adapter_not_supported(mock_adapter_factory, mock_adapter, mock_ctx):
    """embeddings should fail gracefully if adapter doesn't support it."""
    del mock_adapter.embeddings
    mock_adapter_factory.return_value = mock_adapter

    result = model_test_module._act_embeddings(mock_ctx, {"text": "test", "simulate": False})

    assert result["ok"] is False
    assert "not support" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Test _act_latency
# ─────────────────────────────────────────────────────────────────────────────


def test_act_latency_simulate_default(mock_ctx):
    """latency should default to simulate mode."""
    result = model_test_module._act_latency(mock_ctx, {})

    assert result["ok"] is True
    assert result["action"] == "latency"
    assert result["mode"] == "simulate"
    assert result["trials"] == 5  # Default
    assert "avg_ms" in result
    assert "min_ms" in result
    assert "max_ms" in result
    assert "p50" in result
    assert "p90" in result
    assert "p99" in result


def test_act_latency_simulate_deterministic(mock_ctx):
    """latency simulate mode should be deterministic with same prompt."""
    result1 = model_test_module._act_latency(mock_ctx, {"prompt": "test", "trials": 3})
    result2 = model_test_module._act_latency(mock_ctx, {"prompt": "test", "trials": 3})

    assert result1["avg_ms"] == result2["avg_ms"]  # Deterministic
    assert result1["min_ms"] == result2["min_ms"]


def test_act_latency_simulate_custom_trials(mock_ctx):
    """latency should respect custom trial count."""
    result = model_test_module._act_latency(mock_ctx, {"trials": 10})

    assert result["trials"] == 10


def test_act_latency_simulate_realistic_values(mock_ctx):
    """Simulated latency should be within realistic range (50-150ms)."""
    result = model_test_module._act_latency(mock_ctx, {"trials": 20})

    assert 50 <= result["min_ms"] <= 150
    assert 50 <= result["max_ms"] <= 150
    assert 50 <= result["avg_ms"] <= 150


@patch.object(model_test_module, "_call_chat")
@patch.object(model_test_module, "_adapter")
def test_act_latency_live_mode(mock_adapter_factory, mock_call_chat, mock_adapter, mock_ctx):
    """latency with simulate=false should time actual calls."""
    mock_adapter_factory.return_value = mock_adapter
    mock_call_chat.return_value = "response"

    result = model_test_module._act_latency(mock_ctx, {"simulate": False, "trials": 3})

    assert result["ok"] is True
    assert result["mode"] == "live"
    assert result["trials"] == 3
    assert mock_call_chat.call_count == 3


# ─────────────────────────────────────────────────────────────────────────────
# Test Entry Point Validation
# ─────────────────────────────────────────────────────────────────────────────


def test_entry_point_exists():
    """Entry point function should exist."""
    assert hasattr(model_test_module, "model_test")
    assert callable(model_test_module.model_test)


def test_backward_compatibility_aliases():
    """Backward compatibility aliases should exist."""
    assert hasattr(model_test_module, "invoke")
    assert hasattr(model_test_module, "run")
    assert hasattr(model_test_module, "handle")
    assert model_test_module.invoke == model_test_module.model_test
    assert model_test_module.run == model_test_module.model_test
    assert model_test_module.handle == model_test_module.model_test
