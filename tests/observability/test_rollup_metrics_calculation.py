"""
Test for Issue #7: Rollup Metrics Stay Null

Ensures that:
1. Rollup metrics are calculated from llm/tools lists if null
2. total_llm_calls matches length of llm list
3. tool_calls matches length of tools list  
4. tool_errors counts tools with errors
5. Rollup metrics preserved if already set
"""

import pytest
from src.schemas.agents import RunResponse, ExecutionMetrics, LLMCallMetrics, ToolCallMetrics
from datetime import datetime, timezone
from uuid import uuid4


def test_calculate_total_llm_calls_from_list():
    """Test that total_llm_calls is calculated from llm list."""
    metrics = ExecutionMetrics(
        overall_ms=1000,
        llm=[
            LLMCallMetrics(model="gpt-4", latency_ms=100, success=True, input_tokens=100, output_tokens=50, total_tokens=150),
            LLMCallMetrics(model="gpt-4", latency_ms=150, success=True, input_tokens=200, output_tokens=75, total_tokens=275),
        ],
        # total_llm_calls not set
    )
    
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "metrics": metrics,
    }
    
    response = RunResponse(**data)
    assert response.total_llm_calls == 2  # Calculated from llm list


def test_calculate_tool_calls_from_list():
    """Test that tool_calls is calculated from tools list."""
    metrics = ExecutionMetrics(
        overall_ms=500,
        tools=[
            ToolCallMetrics(name="search", latency_ms=100, success=True),
            ToolCallMetrics(name="calculator", latency_ms=50, success=True),
            ToolCallMetrics(name="database", latency_ms=200, success=True),
        ],
        # tool_calls not set
    )
    
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "metrics": metrics,
    }
    
    response = RunResponse(**data)
    assert response.tool_calls == 3  # Calculated from tools list


def test_calculate_tool_errors_from_list():
    """Test that tool_errors counts tools with errors."""
    metrics = ExecutionMetrics(
        overall_ms=800,
        tools=[
            ToolCallMetrics(name="search", latency_ms=100, success=True),  # No error
            ToolCallMetrics(name="calculator", latency_ms=50, success=False, error="Division by zero"),  # Error
            ToolCallMetrics(name="database", latency_ms=200, success=False, error="Connection failed"),  # Error
        ],
        # tool_errors not set
    )
    
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "metrics": metrics,
    }
    
    response = RunResponse(**data)
    assert response.tool_errors == 2  # Counted from tools with errors


def test_preserve_explicit_rollup_metrics():
    """Test that explicitly set rollup metrics are preserved."""
    metrics = ExecutionMetrics(
        overall_ms=1000,
        llm=[LLMCallMetrics(model="gpt-4", latency_ms=100, success=True, input_tokens=100, output_tokens=50, total_tokens=150)],
        total_llm_calls=5,  # Explicitly set (different from list length)
        tool_calls=10,
        tool_errors=2,
    )
    
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "metrics": metrics,
    }
    
    response = RunResponse(**data)
    assert response.total_llm_calls == 5  # Preserved explicit value
    assert response.tool_calls == 10
    assert response.tool_errors == 2


def test_zero_rollup_metrics_for_empty_lists():
    """Test that rollup metrics are 0 for empty llm/tools lists."""
    metrics = ExecutionMetrics(
        overall_ms=100,
        llm=[],  # Empty
        tools=[],  # Empty
    )
    
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "metrics": metrics,
    }
    
    response = RunResponse(**data)
    assert response.total_llm_calls == 0
    assert response.tool_calls == 0
    assert response.tool_errors == 0


def test_null_metrics_null_rollups():
    """Test that rollup metrics stay null if no metrics object."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "metrics": None,  # No metrics
    }
    
    response = RunResponse(**data)
    assert response.total_llm_calls is None
    assert response.tool_calls is None
    assert response.tool_errors is None


def test_mixed_successful_and_failed_tools():
    """Test tool_errors counting with mix of successes and failures."""
    metrics = ExecutionMetrics(
        overall_ms=600,
        tools=[
            ToolCallMetrics(name="tool1", latency_ms=100, success=True),  # Success
            ToolCallMetrics(name="tool2", latency_ms=50, success=False, error="Error 1"),  # Fail
            ToolCallMetrics(name="tool3", latency_ms=100, success=True),  # Success
            ToolCallMetrics(name="tool4", latency_ms=150, success=False, error="Error 2"),  # Fail
            ToolCallMetrics(name="tool5", latency_ms=200, success=True),  # Success
        ],
    )
    
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "metrics": metrics,
    }
    
    response = RunResponse(**data)
    assert response.tool_calls == 5  # Total tools
    assert response.tool_errors == 2  # Only failed tools
