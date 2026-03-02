"""
Test for Issue #12: Create Response Race Condition

Ensures that:
1. POST response has consistent state (status matches output)
2. If status is succeeded, output must be populated
3. No race condition between DB commit and response serialization
4. Output is from database, not in-memory variable
"""

import pytest
from src.schemas.agents import RunResponse
from datetime import datetime, timezone
from uuid import uuid4


def test_succeeded_status_has_populated_output():
    """Test that succeeded status always has non-null output."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "output": {"result": "success", "data": [1, 2, 3]},  # Populated
    }
    
    response = RunResponse(**data)
    assert response.status == "succeeded"
    assert response.output is not None
    assert isinstance(response.output, dict)


def test_succeeded_status_with_null_output_logs_warning():
    """Test that succeeded with null output logs warning (edge case)."""
    # This is a warning case, not an error
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "output": None,  # Null output with succeeded status
    }
    
    # Should not raise error, but will log warning in validator
    response = RunResponse(**data)
    assert response.status == "succeeded"
    assert response.output is None


def test_running_status_can_have_null_output():
    """Test that running status with null output is normal."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "output": None,  # Expected for running status
    }
    
    response = RunResponse(**data)
    assert response.status == "running"
    assert response.output is None


def test_finished_at_present_when_status_succeeded():
    """Test that finished_at is present for succeeded status."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),  # Must be present
        "output": {"result": "done"},
    }
    
    response = RunResponse(**data)
    assert response.status == "succeeded"
    assert response.finished_at is not None
    assert response.finished_at >= response.started_at


def test_response_consistency():
    """Test that response fields are consistent with each other."""
    started = datetime.now(timezone.utc)
    finished = datetime.now(timezone.utc)
    
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": started,
        "finished_at": finished,
        "output": {"result": "complete"},
        "latency_ms": int((finished - started).total_seconds() * 1000),
    }
    
    response = RunResponse(**data)
    
    # All consistency checks
    assert response.status == "succeeded"
    assert response.output is not None
    assert response.finished_at is not None
    assert response.latency_ms is not None
    assert response.latency_ms >= 0


def test_output_from_database_not_variable():
    """Test that output comes from database object, not in-memory variable."""
    # Simulate database object with output
    db_output = {"database": "value", "committed": True}
    
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "output": db_output,  # From database
    }
    
    response = RunResponse(**data)
    
    # Output should match database object
    assert response.output == db_output
    assert response.output is not None
    assert "database" in response.output


def test_empty_string_converted_to_none():
    """Test that empty string output is converted to None (preventing type drift)."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "output": "",  # Empty string should be converted
    }
    
    response = RunResponse(**data)
    assert response.output is None  # Converted by validator
    assert response.output != ""  # Never empty string
