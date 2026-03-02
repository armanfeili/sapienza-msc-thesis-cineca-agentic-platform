"""
Test for Issue #1: Token Counts Intermittently Null

Ensures that:
1. total_tokens calculated from input + output if missing
2. Token fields default to 0 instead of null for aggregation
3. Partial token data handled gracefully
4. Explicit token values preserved
"""

import pytest
from src.schemas.agents import LLMCallMetrics


def test_calculate_total_from_input_output():
    """Test that total_tokens is calculated if input/output present."""
    metrics = LLMCallMetrics(
        model="gpt-4",
        latency_ms=100,
        success=True,
        input_tokens=150,
        output_tokens=75,
        # total_tokens missing
    )
    
    assert metrics.total_tokens == 225  # 150 + 75


def test_preserve_explicit_total_tokens():
    """Test that explicitly set total_tokens is preserved."""
    metrics = LLMCallMetrics(
        model="gpt-4",
        latency_ms=100,
        success=True,
        input_tokens=150,
        output_tokens=75,
        total_tokens=300,  # Explicitly set (overrides calculation)
    )
    
    assert metrics.total_tokens == 300  # Preserved


def test_only_input_tokens_available():
    """Test that total_tokens uses input_tokens if output missing."""
    metrics = LLMCallMetrics(
        model="gpt-4",
        latency_ms=100,
        success=True,
        input_tokens=150,
        # output_tokens missing
    )
    
    assert metrics.total_tokens == 150
    assert metrics.output_tokens == 0  # Defaulted


def test_only_output_tokens_available():
    """Test that total_tokens uses output_tokens if input missing."""
    metrics = LLMCallMetrics(
        model="gpt-4",
        latency_ms=100,
        success=True,
        output_tokens=75,
        # input_tokens missing
    )
    
    assert metrics.total_tokens == 75
    assert metrics.input_tokens == 0  # Defaulted


def test_all_tokens_null_defaults_to_zero():
    """Test that all null token fields default to 0."""
    metrics = LLMCallMetrics(
        model="gpt-4",
        latency_ms=100,
        success=True,
        # All token fields missing
    )
    
    assert metrics.input_tokens == 0
    assert metrics.output_tokens == 0
    assert metrics.total_tokens == 0


def test_zero_tokens_preserved():
    """Test that explicit zero tokens are preserved."""
    metrics = LLMCallMetrics(
        model="gpt-4",
        latency_ms=100,
        success=True,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
    )
    
    assert metrics.input_tokens == 0
    assert metrics.output_tokens == 0
    assert metrics.total_tokens == 0


def test_failed_call_with_tokens():
    """Test that failed calls can still have token metrics."""
    metrics = LLMCallMetrics(
        model="gpt-4",
        latency_ms=50,
        success=False,
        error="API timeout",
        input_tokens=100,
        # Partial input before failure
    )
    
    assert metrics.input_tokens == 100
    assert metrics.output_tokens == 0  # Defaulted
    assert metrics.total_tokens == 100


def test_aggregation_friendly():
    """Test that defaulting to 0 makes aggregation easier."""
    calls = [
        LLMCallMetrics(model="gpt-4", latency_ms=100, success=True, input_tokens=50, output_tokens=25),
        LLMCallMetrics(model="gpt-4", latency_ms=150, success=True),  # No tokens
        LLMCallMetrics(model="gpt-4", latency_ms=200, success=True, input_tokens=100, output_tokens=50),
    ]
    
    # All have total_tokens (no nulls)
    total = sum(call.total_tokens for call in calls)
    assert total == 225  # 75 + 0 + 150
    
    # No None values to handle
    assert all(call.total_tokens is not None for call in calls)
