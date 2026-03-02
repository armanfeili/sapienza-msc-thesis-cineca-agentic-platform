"""
Unit tests for OrchestrationStepOutput validation.

Ensures that output field must be dict, not string, to prevent Pydantic validation errors.
"""

import pytest
from pydantic import ValidationError
from datetime import datetime, timezone

from src.schemas.agents import OrchestrationStepOutput


class TestOrchestrationStepOutputValidation:
    """Test suite for OrchestrationStepOutput validation rules."""
    
    def test_output_must_be_dict_not_string(self):
        """Test that output field rejects plain strings."""
        with pytest.raises(ValidationError) as exc_info:
            OrchestrationStepOutput(
                step_id="test-step",
                output="plain string should fail"  # Should raise ValidationError
            )
        
        # Verify the error is about the output field type
        errors = exc_info.value.errors()
        assert any("output" in str(err) for err in errors), \
            f"Expected validation error for 'output' field, got: {errors}"
    
    def test_output_accepts_dict(self):
        """Test that output field accepts dict values."""
        step = OrchestrationStepOutput(
            step_id="test-step",
            output={"result": "success", "data": {"count": 42}}
        )
        assert step.output == {"result": "success", "data": {"count": 42}}
    
    def test_output_accepts_none(self):
        """Test that output field accepts None."""
        step = OrchestrationStepOutput(
            step_id="test-step",
            output=None
        )
        assert step.output is None
    
    def test_error_output_must_be_dict(self):
        """Test that error cases also use dict for output."""
        step = OrchestrationStepOutput(
            step_id="test-step",
            output={"error": "Something went wrong"},
            error="Something went wrong"
        )
        assert isinstance(step.output, dict)
        assert step.output["error"] == "Something went wrong"
        assert step.error == "Something went wrong"
    
    def test_timeout_error_output_structure(self):
        """Test canonical error structure for timeout scenarios."""
        step = OrchestrationStepOutput(
            step_id="test-step",
            output={
                "error": "Orchestration timeout after 300s",
                "failure_type": "run_timeout",
                "timeout_seconds": 300
            },
            error="Orchestration timeout after 300s"
        )
        
        assert isinstance(step.output, dict)
        assert "error" in step.output
        assert "failure_type" in step.output
        assert step.output["failure_type"] == "run_timeout"
    
    def test_empty_dict_output(self):
        """Test that empty dict is valid output."""
        step = OrchestrationStepOutput(
            step_id="test-step",
            output={}
        )
        assert step.output == {}
    
    def test_nested_dict_output(self):
        """Test that nested dicts are valid."""
        step = OrchestrationStepOutput(
            step_id="test-step",
            output={
                "tools": [
                    {"name": "tool1", "category": "query"},
                    {"name": "tool2", "category": "write"}
                ],
                "metadata": {
                    "count": 2,
                    "source": "discovery"
                }
            }
        )
        assert len(step.output["tools"]) == 2
        assert step.output["metadata"]["count"] == 2
    
    def test_output_with_timing_fields(self):
        """Test that output works alongside timing fields."""
        now = datetime.now(timezone.utc)
        
        step = OrchestrationStepOutput(
            step_id="test-step",
            output={"result": "completed"},
            started_at=now,
            finished_at=now,
            latency_ms=0
        )
        
        assert isinstance(step.output, dict)
        assert step.started_at is not None
        assert step.finished_at is not None
        assert step.latency_ms == 0
    
    def test_fallback_error_structure(self):
        """Test the fallback error output structure used in agent_runs.py."""
        error_msg = "Orchestrator error: Connection timeout"
        
        step = OrchestrationStepOutput(
            step_id="fallback",
            output={"error": error_msg},
            error=error_msg
        )
        
        assert isinstance(step.output, dict)
        assert "error" in step.output
        assert step.output["error"] == error_msg
        assert step.error == error_msg
