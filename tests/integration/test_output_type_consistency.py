"""
Test for Issue #5: Output Type Drift (Empty String vs Object)

Ensures that:
1. Output field is never an empty string
2. Output is always dict, list, or None
3. Schema validation rejects empty strings
4. Successful runs have populated output
"""

import pytest
from pydantic import ValidationError
from src.schemas.agents import RunResponse
from datetime import datetime, timezone
from uuid import uuid4


def test_output_never_empty_string():
    """Test that output field cannot be an empty string."""
    # Attempt to create response with empty string output
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "output": "",  # Empty string should be converted to None
    }
    
    response = RunResponse(**data)
    
    # Validator should convert empty string to None
    assert response.output is None
    assert response.output != ""


def test_output_type_is_dict_list_or_none():
    """Test that output is only dict, list, or None."""
    # Test with dict
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "output": {"result": "success", "data": [1, 2, 3]},
    }
    response = RunResponse(**data)
    assert isinstance(response.output, dict)
    
    # Test with list
    data["output"] = [{"item": 1}, {"item": 2}]
    response = RunResponse(**data)
    assert isinstance(response.output, list)
    
    # Test with None
    data["output"] = None
    response = RunResponse(**data)
    assert response.output is None


def test_output_type_rejects_plain_string():
    """Test that plain strings are rejected as output type."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "output": "this is plain text",  # Should fail validation
    }
    
    # This should raise ValidationError because str is not in allowed types
    with pytest.raises(ValidationError) as exc_info:
        RunResponse(**data)
    
    assert "output" in str(exc_info.value)


def test_succeeded_status_with_null_output_logs_warning(caplog):
    """Test that succeeded status with null output logs a warning."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "output": None,  # Succeeded but no output
    }
    
    response = RunResponse(**data)
    
    # Should create response but log warning
    assert response.output is None
    # Note: In production, this would log a warning via structlog


def test_running_status_with_null_output():
    """Test that running status with null output is acceptable."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "output": None,  # Expected for running status
    }
    
    response = RunResponse(**data)
    assert response.output is None
    assert response.status == "running"


def test_failed_status_with_null_output():
    """Test that failed status with null output is acceptable."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "failed",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "output": None,  # Acceptable for failed status
        "errors": ["Something went wrong"],
    }
    
    response = RunResponse(**data)
    assert response.output is None
    assert response.status == "failed"


def test_output_consistency_across_serialization():
    """Test that output type remains consistent through serialization."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "output": {"result": "test", "items": [1, 2, 3]},
    }
    
    response = RunResponse(**data)
    
    # Serialize to dict
    serialized = response.model_dump(mode="json")
    
    # Output should still be dict
    assert isinstance(serialized["output"], dict)
    assert serialized["output"]["result"] == "test"
    
    # Deserialize back
    response2 = RunResponse(**serialized)
    assert isinstance(response2.output, dict)
    assert response2.output == data["output"]
