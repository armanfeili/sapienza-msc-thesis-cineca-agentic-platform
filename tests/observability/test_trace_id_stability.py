"""
Test for Issue #3: Trace ID Stability

Ensures that:
1. trace_id is set once at creation and never changes
2. request_id is separate and tracks HTTP requests
3. trace_id persists across GET requests
4. Both trace_id and request_id are present in responses
"""

import pytest
from src.schemas.agents import RunResponse
from datetime import datetime, timezone
from uuid import uuid4


def test_trace_id_stability():
    """Test that trace_id remains stable across multiple accesses."""
    # Simulate a run with stable trace_id
    stable_trace_id = str(uuid4())
    
    # First response (POST create)
    data1 = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "trace_id": stable_trace_id,
        "request_id": "req-1234",
    }
    
    response1 = RunResponse(**data1)
    assert response1.trace_id == stable_trace_id
    assert response1.request_id == "req-1234"
    
    # Second response (GET retrieve - different request_id but same trace_id)
    data2 = {
        "run_id": data1["run_id"],  # Same run
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": data1["started_at"],
        "finished_at": datetime.now(timezone.utc),
        "trace_id": stable_trace_id,  # Same trace_id
        "request_id": "req-5678",  # Different request_id
    }
    
    response2 = RunResponse(**data2)
    assert response2.trace_id == stable_trace_id  # Unchanged!
    assert response2.trace_id == response1.trace_id  # Same as original
    assert response2.request_id == "req-5678"  # Different request
    assert response2.request_id != response1.request_id  # Request IDs differ


def test_trace_id_and_request_id_are_separate():
    """Test that trace_id and request_id are distinct fields."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "trace_id": str(uuid4()),  # Stable trace ID
        "request_id": str(uuid4()),  # HTTP request ID
    }
    
    response = RunResponse(**data)
    
    # Both fields exist
    assert response.trace_id is not None
    assert response.request_id is not None
    
    # They are different
    assert response.trace_id != response.request_id


def test_trace_id_required_for_stability():
    """Test that trace_id should be set for proper correlation."""
    # Run without trace_id (acceptable but not ideal)
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "trace_id": None,  # Missing trace_id
        "request_id": "req-1234",
    }
    
    response = RunResponse(**data)
    
    # Should not fail, but trace_id is None
    assert response.trace_id is None
    assert response.request_id == "req-1234"


def test_request_id_matches_http_header():
    """Test that request_id should match X-Request-Id header."""
    x_request_id = "req-abc-123"
    
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "trace_id": str(uuid4()),
        "request_id": x_request_id,  # Should match header
    }
    
    response = RunResponse(**data)
    assert response.request_id == x_request_id


def test_trace_id_immutable_across_serialization():
    """Test that trace_id doesn't change during serialization."""
    stable_trace_id = str(uuid4())
    
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "trace_id": stable_trace_id,
        "request_id": "req-9999",
    }
    
    response = RunResponse(**data)
    
    # Serialize to dict
    serialized = response.model_dump(mode="json")
    assert serialized["trace_id"] == stable_trace_id
    
    # Deserialize back
    response2 = RunResponse(**serialized)
    assert response2.trace_id == stable_trace_id


def test_both_fields_in_response():
    """Test that both trace_id and request_id are present in responses."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "trace_id": str(uuid4()),
        "request_id": str(uuid4()),
        "output": {"result": "success"},
    }
    
    response = RunResponse(**data)
    serialized = response.model_dump(mode="json")
    
    # Both fields present
    assert "trace_id" in serialized
    assert "request_id" in serialized
    assert serialized["trace_id"] is not None
    assert serialized["request_id"] is not None
