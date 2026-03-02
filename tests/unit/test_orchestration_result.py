"""
Unit tests for OrchestrationResult data structure.

Tests construction, attribute defaults, serialization, and error handling
for OrchestrationResult across success, timeout, and exception scenarios.

Related TODO: A1.5 - Add unit tests for OrchestrationResult
"""

import pytest
from datetime import datetime, timezone
from dataclasses import asdict

from src.services.orchestrator import OrchestrationResult, Step


class TestOrchestrationResultConstruction:
    """Test suite for OrchestrationResult construction and defaults."""
    
    def test_minimal_construction_with_goal_only(self):
        """Test OrchestrationResult can be constructed with only goal parameter."""
        result = OrchestrationResult(goal="Test goal")
        
        assert result.goal == "Test goal"
        assert result.manager is None
        assert result.steps == []
        assert result.outputs == []
        assert result.todos == []
        assert result.errors == []  # A1: Critical - errors field must exist
        assert result.warnings == []
        assert result.error is None
        assert result.llm_metrics == []
        assert result.tool_metrics == []
        assert result.total_llm_calls == 0
        assert result.llm_call_count == 0
        assert result.llm_attempted_calls == 0
        assert result.llm_successful_calls == 0
        assert result.tool_calls == 0
        assert result.tool_errors == 0
        assert result.model_warmup_ms is None
        assert result.current_stage is None
        assert result.timeout_stage is None
        assert result.metrics == {}
        assert isinstance(result.started_at, str)
        assert result.finished_at is None
    
    def test_construction_with_all_fields(self):
        """Test OrchestrationResult construction with all fields populated."""
        started_at = datetime.now(timezone.utc).isoformat()
        finished_at = datetime.now(timezone.utc).isoformat()
        
        steps = [
            Step(id="1", action="llm:manager", input={"prompt": "Test prompt"})
        ]
        
        outputs = [
            {
                "step_id": 1,
                "action": "llm:manager",
                "output": {"text": "Test output"},
                "error": None
            }
        ]
        
        todos = [
            {"step_id": "1", "description": "Test task", "status": "completed"}
        ]
        
        result = OrchestrationResult(
            goal="Complex goal",
            manager="phi3:mini",
            steps=steps,
            outputs=outputs,
            todos=todos,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"],
            started_at=started_at,
            finished_at=finished_at,
            error="Primary error message",
            llm_metrics=[{"call": 1, "duration_ms": 100}],
            tool_metrics=[{"tool": "test", "duration_ms": 50}],
            total_llm_calls=2,
            llm_call_count=2,
            llm_attempted_calls=2,
            llm_successful_calls=1,
            tool_calls=3,
            tool_errors=1,
            model_warmup_ms=1500,
            current_stage="completed",
            timeout_stage=None,
            metrics={"custom": "value"}
        )
        
        assert result.goal == "Complex goal"
        assert result.manager == "phi3:mini"
        assert len(result.steps) == 1
        assert len(result.outputs) == 1
        assert len(result.todos) == 1
        assert len(result.errors) == 2
        assert result.errors[0] == "Error 1"
        assert len(result.warnings) == 1
        assert result.error == "Primary error message"
        assert len(result.llm_metrics) == 1
        assert len(result.tool_metrics) == 1
        assert result.total_llm_calls == 2
        assert result.llm_attempted_calls == 2
        assert result.llm_successful_calls == 1
        assert result.tool_calls == 3
        assert result.tool_errors == 1
        assert result.model_warmup_ms == 1500
        assert result.metrics["custom"] == "value"


class TestOrchestrationResultTimeoutScenario:
    """Test OrchestrationResult construction in timeout scenarios."""
    
    def test_planning_timeout_result(self):
        """Test OrchestrationResult construction when planning times out."""
        result = OrchestrationResult(goal="Test planning timeout")
        
        # Simulate timeout during planning (A2 scenario)
        result.errors.append("Planning timed out after 540 seconds")
        result.timeout_stage = "planning_todo_list"
        result.llm_attempted_calls = 1
        result.llm_successful_calls = 0
        result.finished_at = datetime.now(timezone.utc).isoformat()
        
        # Verify timeout state
        assert len(result.errors) == 1
        assert "Planning timed out" in result.errors[0]
        assert result.timeout_stage == "planning_todo_list"
        assert result.llm_attempted_calls == 1
        assert result.llm_successful_calls == 0
        assert result.finished_at is not None
        
        # Verify errors field is always accessible (no AttributeError)
        assert hasattr(result, 'errors')
        assert isinstance(result.errors, list)
    
    def test_step_execution_timeout_result(self):
        """Test OrchestrationResult construction when step execution times out."""
        result = OrchestrationResult(goal="Test step timeout")
        
        # Add partial progress before timeout
        result.todos = [
            {"step_id": "1", "description": "Task 1", "status": "completed"},
            {"step_id": "2", "description": "Task 2", "status": "in_progress"}
        ]
        result.steps = [
            Step(id="1", action="llm:worker", input={"prompt": "Step 1"})
        ]
        result.outputs = [
            {"step_id": 1, "output": {"text": "Step 1 output"}, "error": None}
        ]
        
        # Simulate timeout during step 2
        result.errors.append("Step execution timed out after 540 seconds")
        result.timeout_stage = "executing_step_2"
        result.llm_attempted_calls = 2
        result.llm_successful_calls = 1
        result.finished_at = datetime.now(timezone.utc).isoformat()
        
        # Verify partial progress preserved
        assert len(result.todos) == 2
        assert len(result.steps) == 1
        assert len(result.outputs) == 1
        assert len(result.errors) == 1
        assert result.timeout_stage == "executing_step_2"
        assert result.llm_attempted_calls == 2
        assert result.llm_successful_calls == 1
    
    def test_multiple_errors_accumulation(self):
        """Test that multiple errors can be accumulated in errors list."""
        result = OrchestrationResult(goal="Test multiple errors")
        
        # Simulate multiple error conditions
        result.errors.append("Error 1: Planning failed")
        result.errors.append("Error 2: Step execution failed")
        result.errors.append("Error 3: Timeout occurred")
        
        assert len(result.errors) == 3
        assert result.errors[0] == "Error 1: Planning failed"
        assert result.errors[1] == "Error 2: Step execution failed"
        assert result.errors[2] == "Error 3: Timeout occurred"


class TestOrchestrationResultExceptionScenario:
    """Test OrchestrationResult construction in exception scenarios."""
    
    def test_fatal_error_result(self):
        """Test OrchestrationResult construction after fatal error."""
        result = OrchestrationResult(goal="Test fatal error")
        
        # Simulate fatal error (e.g., Pydantic validation error)
        result.errors.append("Fatal error: 1 validation error for OrchestrationStepOutput")
        result.error = "Fatal error: 1 validation error for OrchestrationStepOutput"
        result.finished_at = datetime.now(timezone.utc).isoformat()
        result.llm_attempted_calls = 0
        result.llm_successful_calls = 0
        result.tool_calls = 0
        result.tool_errors = 0
        
        # Verify error state
        assert len(result.errors) == 1
        assert "validation error" in result.errors[0]
        assert result.error is not None
        assert result.finished_at is not None
        assert result.llm_attempted_calls == 0
    
    def test_llm_error_result(self):
        """Test OrchestrationResult construction after LLM failure."""
        result = OrchestrationResult(goal="Test LLM error")
        
        # Simulate LLM error
        result.errors.append("LLM error: Model inference failed")
        result.llm_attempted_calls = 1
        result.llm_successful_calls = 0
        result.llm_metrics = [
            {
                "call_number": 1,
                "status": "error",
                "error": "Model inference failed",
                "duration_ms": 150
            }
        ]
        
        assert len(result.errors) == 1
        assert "LLM error" in result.errors[0]
        assert result.llm_attempted_calls == 1
        assert result.llm_successful_calls == 0
        assert len(result.llm_metrics) == 1
        assert result.llm_metrics[0]["status"] == "error"
    
    def test_tool_error_result(self):
        """Test OrchestrationResult construction after tool failure."""
        result = OrchestrationResult(goal="Test tool error")
        
        # Simulate tool error
        result.errors.append("Tool error: Permission check failed: no principal")
        result.tool_calls = 1
        result.tool_errors = 1
        result.tool_metrics = [
            {
                "tool_name": "graph.generate_cypher",
                "status": "error",
                "error": "Permission check failed: no principal",
                "duration_ms": 50
            }
        ]
        
        assert len(result.errors) == 1
        assert "Permission check failed" in result.errors[0]
        assert result.tool_calls == 1
        assert result.tool_errors == 1
        assert len(result.tool_metrics) == 1


class TestOrchestrationResultSerialization:
    """Test OrchestrationResult serialization via to_dict method."""
    
    def test_to_dict_minimal(self):
        """Test to_dict with minimal OrchestrationResult."""
        result = OrchestrationResult(goal="Minimal test")
        result_dict = result.to_dict()
        
        # Verify required fields present
        assert "goal" in result_dict
        assert result_dict["goal"] == "Minimal test"
        assert "errors" in result_dict  # A1: Critical - errors must be in dict
        assert result_dict["errors"] == []
        assert "warnings" in result_dict
        assert result_dict["warnings"] == []
        assert "output" in result_dict  # Aggregated output field
    
    def test_to_dict_with_outputs(self):
        """Test to_dict with outputs aggregation."""
        result = OrchestrationResult(goal="Test outputs")
        result.outputs = [
            {
                "step_id": 1,
                "output": {"text": "Output 1"}
            },
            {
                "step_id": 2,
                "output": {"result": "Output 2"}
            },
            {
                "step_id": 3,
                "output": {"response": "Output 3"}
            }
        ]
        
        result_dict = result.to_dict()
        
        # Verify aggregated output
        assert "output" in result_dict
        aggregated_output = result_dict["output"]
        assert "Output 1" in aggregated_output
        assert "Output 2" in aggregated_output
        assert "Output 3" in aggregated_output
    
    def test_to_dict_with_errors(self):
        """Test to_dict includes errors list."""
        result = OrchestrationResult(goal="Test errors serialization")
        result.errors = ["Error 1", "Error 2", "Error 3"]
        result.warnings = ["Warning 1"]
        
        result_dict = result.to_dict()
        
        assert "errors" in result_dict
        assert len(result_dict["errors"]) == 3
        assert result_dict["errors"][0] == "Error 1"
        assert "warnings" in result_dict
        assert len(result_dict["warnings"]) == 1
    
    def test_to_dict_with_metrics(self):
        """Test to_dict includes metrics."""
        result = OrchestrationResult(goal="Test metrics")
        result.llm_attempted_calls = 5
        result.llm_successful_calls = 4
        result.tool_calls = 3
        result.tool_errors = 1
        result.metrics = {"custom_metric": "value"}
        
        result_dict = result.to_dict()
        
        # Verify metrics included (nested in metrics dict)
        assert "metrics" in result_dict
        assert "llm_attempted_calls" in result_dict["metrics"]
        assert result_dict["metrics"]["llm_attempted_calls"] == 5
        assert "llm_successful_calls" in result_dict["metrics"]
        assert result_dict["metrics"]["llm_successful_calls"] == 4
        assert "tool_calls" in result_dict["metrics"]
        assert result_dict["metrics"]["tool_calls"] == 3
        assert "tool_errors" in result_dict["metrics"]
        assert result_dict["metrics"]["tool_errors"] == 1
        assert "custom_metric" in result_dict["metrics"]
        assert result_dict["metrics"]["custom_metric"] == "value"

    def test_to_dict_preserves_zero_successful_llm_calls(self):
        """Zero successful LLM calls should not be replaced by total count."""
        result = OrchestrationResult(goal="LLM timeout run")
        result.llm_metrics = [
            {"success": False, "latency_ms": 1000, "purpose": "test"},
        ]
        result.llm_attempted_calls = 1
        result.llm_successful_calls = 0

        result_dict = result.to_dict()
        metrics = result_dict["metrics"]
        assert metrics["llm_attempted_calls"] == 1
        assert metrics["llm_successful_calls"] == 0
    
    def test_to_dict_with_timeout_stage(self):
        """Test to_dict includes timeout_stage when set."""
        result = OrchestrationResult(goal="Test timeout stage")
        result.timeout_stage = "planning_todo_list"
        result.errors.append("Planning timed out")
        
        result_dict = result.to_dict()
        
        # timeout_stage is nested in metrics dict
        assert "metrics" in result_dict
        assert "timeout_stage" in result_dict["metrics"]
        assert result_dict["metrics"]["timeout_stage"] == "planning_todo_list"
        assert len(result_dict["errors"]) == 1


class TestOrchestrationResultSuccessScenario:
    """Test OrchestrationResult construction in successful execution."""
    
    def test_successful_execution_result(self):
        """Test OrchestrationResult for successful orchestration."""
        result = OrchestrationResult(goal="Successful test")
        
        # Add successful execution data
        result.manager = "phi3:mini"
        result.todos = [
            {"step_id": "1", "description": "Generate Cypher query", "status": "completed"}
        ]
        result.steps = [
            Step(id="1", action="graph.generate_cypher", input={"prompt": "Generate query"})
        ]
        result.outputs = [
            {
                "step_id": 1,
                "output": {
                    "text": "MATCH (b:Blast) RETURN count(b) as blast_count",
                    "cypher_query": "MATCH (b:Blast) RETURN count(b)"
                },
                "error": None
            }
        ]
        result.llm_attempted_calls = 1
        result.llm_successful_calls = 1
        result.tool_calls = 1
        result.tool_errors = 0
        result.finished_at = datetime.now(timezone.utc).isoformat()
        
        # Verify successful state
        assert len(result.errors) == 0  # No errors in success case
        assert len(result.warnings) == 0
        assert result.error is None
        assert len(result.todos) == 1
        assert result.todos[0]["status"] == "completed"
        assert len(result.outputs) == 1
        assert result.outputs[0]["error"] is None
        assert result.llm_attempted_calls == 1
        assert result.llm_successful_calls == 1
        assert result.tool_calls == 1
        assert result.tool_errors == 0
        assert result.timeout_stage is None
    
    def test_successful_multi_step_result(self):
        """Test OrchestrationResult for successful multi-step orchestration."""
        result = OrchestrationResult(goal="Multi-step test")
        
        result.manager = "phi3:mini"
        result.todos = [
            {"step_id": "1", "description": "Step 1", "status": "completed"},
            {"step_id": "2", "description": "Step 2", "status": "completed"},
            {"step_id": "3", "description": "Step 3", "status": "completed"}
        ]
        result.steps = [
            Step(id="1", action="llm:worker1", input={"prompt": "Prompt 1"}),
            Step(id="2", action="tool:query", input={"prompt": "Prompt 2"}),
            Step(id="3", action="llm:worker2", input={"prompt": "Prompt 3"})
        ]
        result.outputs = [
            {"step_id": 1, "output": {"text": "Output 1"}, "error": None},
            {"step_id": 2, "output": {"result": "Output 2"}, "error": None},
            {"step_id": 3, "output": {"response": "Output 3"}, "error": None}
        ]
        result.llm_attempted_calls = 3
        result.llm_successful_calls = 3
        result.tool_calls = 1
        result.tool_errors = 0
        
        assert len(result.todos) == 3
        assert all(todo["status"] == "completed" for todo in result.todos)
        assert len(result.steps) == 3
        assert len(result.outputs) == 3
        assert result.llm_attempted_calls == 3
        assert result.llm_successful_calls == 3


class TestOrchestrationResultErrorsFieldCritical:
    """Critical tests ensuring errors field always exists (A1 requirement)."""
    
    def test_errors_field_exists_on_new_instance(self):
        """Test that errors field exists on newly created instance."""
        result = OrchestrationResult(goal="Test")
        
        # This must not raise AttributeError (A1 critical fix)
        assert hasattr(result, 'errors')
        assert isinstance(result.errors, list)
        assert len(result.errors) == 0
    
    def test_errors_field_accessible_after_timeout(self):
        """Test that errors field is accessible after timeout simulation."""
        result = OrchestrationResult(goal="Test")
        
        # Simulate timeout appending to errors
        try:
            result.errors.append("Timeout occurred")
        except AttributeError as e:
            pytest.fail(f"errors field missing after timeout: {e}")
        
        assert len(result.errors) == 1
    
    def test_errors_field_in_to_dict(self):
        """Test that errors field is included in to_dict output."""
        result = OrchestrationResult(goal="Test")
        result.errors.append("Test error")
        
        result_dict = result.to_dict()
        
        assert "errors" in result_dict
        assert isinstance(result_dict["errors"], list)
        assert len(result_dict["errors"]) == 1
        assert result_dict["errors"][0] == "Test error"
    
    def test_errors_and_error_fields_coexist(self):
        """Test that both errors (list) and error (string) fields work together."""
        result = OrchestrationResult(goal="Test")
        
        result.errors.append("Error 1")
        result.errors.append("Error 2")
        result.error = "Primary error message"
        
        # Both fields should be accessible
        assert len(result.errors) == 2
        assert result.error == "Primary error message"
        
        result_dict = result.to_dict()
        assert "errors" in result_dict
        assert "error" in result_dict
    
    def test_errors_field_survives_dataclass_conversion(self):
        """Test that errors field survives asdict() conversion."""
        result = OrchestrationResult(goal="Test")
        result.errors.append("Test error")
        
        # Convert to dict using dataclasses.asdict
        result_as_dict = asdict(result)
        
        assert "errors" in result_as_dict
        assert isinstance(result_as_dict["errors"], list)
        assert len(result_as_dict["errors"]) == 1


class TestTimeoutMetricInjection:
    """Ensure configured timeout values are propagated into metrics."""

    def test_apply_timeout_config_metrics_sets_defaults(self):
        from src.services.orchestrator import (  # Local import avoids circulars during module import
            RUN_TIMEOUT_SECONDS,
            STEP_TIMEOUT_SECONDS,
            _apply_timeout_config_metrics,
        )

        metrics: dict[str, int] = {}
        _apply_timeout_config_metrics(metrics)

        assert metrics["configured_run_timeout_seconds"] == RUN_TIMEOUT_SECONDS
        assert metrics["configured_step_timeout_seconds"] == STEP_TIMEOUT_SECONDS
        assert metrics["run_timeout_budget_ms"] == RUN_TIMEOUT_SECONDS * 1000
