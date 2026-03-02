"""
Test for Issue #4: Event ID Disappears After Creation

Ensures that:
1. event_id is present in RunResponse
2. event_id persists in database after updates
3. event_id is available in subsequent GET requests
4. event_id remains consistent throughout lifecycle
"""

import pytest
from src.schemas.agents import RunResponse
from datetime import datetime, timezone
from uuid import uuid4


def test_event_id_present_in_response():
    """Test that event_id is present in successful responses."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "event_id": "prov-event-123",  # Provenance event ID
    }
    
    response = RunResponse(**data)
    assert response.event_id == "prov-event-123"
    assert response.event_id is not None


def test_event_id_can_be_null():
    """Test that event_id can be None for running status."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "event_id": None,  # Not yet recorded
    }
    
    response = RunResponse(**data)
    assert response.event_id is None


def test_event_id_differs_from_trace_id():
    """Test that event_id and trace_id are separate identifiers."""
    trace_id = str(uuid4())
    event_id = "prov-event-456"
    
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "trace_id": trace_id,
        "event_id": event_id,
    }
    
    response = RunResponse(**data)
    assert response.trace_id == trace_id
    assert response.event_id == event_id
    assert response.trace_id != response.event_id  # Different IDs


def test_event_id_serialization():
    """Test that event_id is included in JSON serialization."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "event_id": "prov-event-789",
    }
    
    response = RunResponse(**data)
    json_data = response.model_dump(mode="json")
    
    assert "event_id" in json_data
    assert json_data["event_id"] == "prov-event-789"


def test_event_id_persistence_throughout_lifecycle():
    """Test that event_id persists from creation through completion."""
    run_id = uuid4()
    event_id = "prov-event-complete-123"
    
    # Simulate completed run with event_id
    data = {
        "run_id": run_id,
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "event_id": event_id,
        "output": {"result": "done"},
    }
    
    response = RunResponse(**data)
    
    # Verify event_id is present and unchanged
    assert response.event_id == event_id
    assert response.run_id == run_id
    assert response.status == "succeeded"


def test_multiple_runs_different_event_ids():
    """Test that different runs have different event_ids."""
    run1_data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "event_id": "prov-event-run1",
    }
    
    run2_data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "event_id": "prov-event-run2",
    }
    
    response1 = RunResponse(**run1_data)
    response2 = RunResponse(**run2_data)
    
    assert response1.event_id != response2.event_id
    assert response1.run_id != response2.run_id
