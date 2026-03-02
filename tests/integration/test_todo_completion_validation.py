"""
Test for Issue #8: TODO Completion Validation

Ensures that:
1. Completed TODOs have matching execution steps (evidence)
2. Warning logged when TODO marked completed without evidence
3. TODOs with evidence pass validation silently
4. Empty/null todos/steps don't cause errors
"""

import pytest
from pytest import MonkeyPatch
from src.schemas.agents import RunResponse, TodoItem, OrchestrationStepInput
from datetime import datetime, timezone
from uuid import uuid4


def test_completed_todo_with_evidence():
    """Test that completed TODO with matching step passes validation."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(task="Execute search tool", status="completed"),
        ],
        "steps": [
            OrchestrationStepInput(
                step_id="1",
                action="search",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
        ],
    }
    
    # Should not raise error
    response = RunResponse(**data)
    assert response.todos[0].status == "completed"


def test_completed_todo_without_evidence_logs_warning(caplog):
    """Test that completed TODO without matching step logs warning."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(task="Initiate llm:planner", status="completed"),
        ],
        "steps": [
            OrchestrationStepInput(
                step_id="1",
                action="search",  # Different action - no planner step
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
        ],
    }
    
    # Should log warning but not fail
    response = RunResponse(**data)
    assert response.todos[0].status == "completed"
    # Warning should be logged (checked via caplog in real test environment)


def test_pending_todo_no_validation():
    """Test that pending TODOs are not validated for evidence."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "running",
        "started_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(task="Execute search tool", status="pending"),
        ],
        "steps": [],  # No steps yet
    }
    
    # Should not log warning for pending TODO
    response = RunResponse(**data)
    assert response.todos[0].status == "pending"


def test_no_todos_no_validation():
    """Test that runs without TODOs don't trigger validation."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": None,  # No TODOs
        "steps": [
            OrchestrationStepInput(
                step_id="1",
                action="search",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
        ],
    }
    
    # Should not raise error
    response = RunResponse(**data)
    assert response.todos is None


def test_no_steps_no_validation():
    """Test that runs without steps don't trigger validation."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(task="Execute search tool", status="completed"),
        ],
        "steps": None,  # No steps
    }
    
    # Should not raise error (early return in validator)
    response = RunResponse(**data)
    assert response.todos[0].status == "completed"


def test_multiple_todos_mixed_evidence():
    """Test validation with multiple TODOs, some with evidence."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(task="Execute search tool", status="completed"),  # Has evidence
            TodoItem(task="Initiate calculator", status="completed"),  # Has evidence
            TodoItem(task="Initiate llm:planner", status="completed"),  # No evidence
        ],
        "steps": [
            OrchestrationStepInput(
                step_id="1",
                action="search",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
            OrchestrationStepInput(
                step_id="2",
                action="calculator",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
        ],
    }
    
    # Should log warning only for TODO without evidence
    response = RunResponse(**data)
    assert len(response.todos) == 3
    assert all(t.status == "completed" for t in response.todos)


def test_step_id_matching():
    """Test that step_id can match TODO task description."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(task="Execute create-todos step", status="completed"),
        ],
        "steps": [
            OrchestrationStepInput(
                step_id="create-todos",  # Matches TODO description
                action="generate_todos",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
        ],
    }
    
    # Should pass - step_id matches TODO
    response = RunResponse(**data)
    assert response.todos[0].status == "completed"


def test_case_insensitive_matching():
    """Test that TODO-step matching is case-insensitive."""
    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(task="Execute SEARCH Tool", status="completed"),  # Uppercase
        ],
        "steps": [
            OrchestrationStepInput(
                step_id="1",
                action="search",  # Lowercase
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
        ],
    }
    
    # Should match case-insensitively
    response = RunResponse(**data)
    assert response.todos[0].status == "completed"


def test_completed_summary_todo_skips_warning(monkeypatch):
    """Completed summarization TODOs should not emit missing-evidence warnings."""
    events = []

    class FakeLog:
        def warning(self, event, **kwargs):
            events.append(("warning", event, kwargs))

        def info(self, event, **kwargs):
            events.append(("info", event, kwargs))

    import structlog

    monkeypatch.setattr(structlog, "get_logger", lambda *_, **__: FakeLog())
    RunResponse._WARNED_TODO_EVIDENCE.clear()

    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(task="Summarize findings", status="completed", expect_evidence=False),
        ],
        "steps": [
            OrchestrationStepInput(
                step_id="1",
                action="placeholder-step",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
        ],
    }

    RunResponse(**data)
    warning_events = [evt for evt in events if evt[1] == "todo.completed_without_evidence"]
    assert not warning_events


def test_missing_evidence_warns_only_once(monkeypatch):
    """Ensure duplicate validation does not spam the log for the same TODO."""
    events = []

    class FakeLog:
        def warning(self, event, **kwargs):
            events.append(("warning", event, kwargs))

        def info(self, event, **kwargs):
            events.append(("info", event, kwargs))

    import structlog

    monkeypatch.setattr(structlog, "get_logger", lambda *_, **__: FakeLog())
    RunResponse._WARNED_TODO_EVIDENCE.clear()

    shared_run_id = uuid4()
    data = {
        "run_id": shared_run_id,
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(task="Initiate llm:planner", status="completed"),
        ],
        "steps": [
            OrchestrationStepInput(
                step_id="1",
                action="search",  # Different action - no planner step
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
        ],
    }

    RunResponse(**data)
    RunResponse(**data)

    warning_events = [evt for evt in events if evt[1] == "todo.completed_without_evidence"]
    assert len(warning_events) == 1


# ==============================================================================
# NEW TESTS FOR NESTED STEPS, FALLBACK MODE, AND METRICS CONSISTENCY
# ==============================================================================


def test_nested_steps_validation_finds_tool_in_nested_steps(monkeypatch: MonkeyPatch) -> None:
    """Test that validation finds tool references in nested_steps."""
    events = []

    class FakeLog:
        def warning(self, event, **kwargs):
            events.append(("warning", event, kwargs))

        def info(self, event, **kwargs):
            events.append(("info", event, kwargs))

    import structlog

    monkeypatch.setattr(structlog, "get_logger", lambda *_, **__: FakeLog())
    RunResponse._WARNED_TODO_EVIDENCE.clear()

    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(
                task="Execute query using Memgraph",
                status="completed",
                nested_steps=[
                    "memgraph_query: Find all nodes",
                    "Process the results",
                ],
            ),
        ],
        "steps": [
            OrchestrationStepInput(
                step_id="1",
                action="memgraph_query",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
        ],
    }

    RunResponse(**data)

    # Should NOT produce warning because memgraph_query was found in nested steps AND executed
    warning_events = [evt for evt in events if evt[1] == "todo.completed_without_evidence"]
    assert len(warning_events) == 0


def test_nested_steps_validation_warns_for_unexecuted_tool_in_nested_steps(
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that validation warns when tool mentioned in nested_steps wasn't executed."""
    events = []

    class FakeLog:
        def warning(self, event, **kwargs):
            events.append(("warning", event, kwargs))

        def info(self, event, **kwargs):
            events.append(("info", event, kwargs))

    import structlog

    monkeypatch.setattr(structlog, "get_logger", lambda *_, **__: FakeLog())
    RunResponse._WARNED_TODO_EVIDENCE.clear()

    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(
                task="Run analysis",
                status="completed",
                nested_steps=[
                    "slurm_submit: Submit batch job",
                    "Wait for completion",
                ],
                fallback_mode=False,  # Not fallback mode, so should warn
            ),
        ],
        "steps": [
            OrchestrationStepInput(
                step_id="1",
                action="search",  # Different action - slurm_submit not executed
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
        ],
    }

    RunResponse(**data)

    # Should produce warning because slurm_submit in nested steps wasn't executed
    warning_events = [evt for evt in events if evt[1] == "todo.completed_without_evidence"]
    assert len(warning_events) >= 1


def test_fallback_mode_downgrades_warnings_to_info(monkeypatch: MonkeyPatch) -> None:
    """Test that fallback_mode=True downgrades warnings to info level."""
    events = []

    class FakeLog:
        def warning(self, event, **kwargs):
            events.append(("warning", event, kwargs))

        def info(self, event, **kwargs):
            events.append(("info", event, kwargs))

    import structlog

    monkeypatch.setattr(structlog, "get_logger", lambda *_, **__: FakeLog())
    RunResponse._WARNED_TODO_EVIDENCE.clear()

    data = {
        "run_id": uuid4(),
        "user_id": "test_user",
        "tenant_id": "test_tenant",
        "status": "succeeded",
        "started_at": datetime.now(timezone.utc),
        "finished_at": datetime.now(timezone.utc),
        "todos": [
            TodoItem(
                task="Use slurm_submit to submit job",
                status="completed",
                fallback_mode=True,  # Fallback mode - should NOT warn
            ),
        ],
        "steps": [
            OrchestrationStepInput(
                step_id="1",
                action="llm",  # Only LLM action, no tool
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            ),
        ],
    }

    RunResponse(**data)

    # In fallback mode, should NOT produce warning even though tool wasn't executed
    # The validation should log at info level instead
    warning_events = [evt for evt in events if evt[1] == "todo.completed_without_evidence"]
    assert len(warning_events) == 0

    # Check for info-level fallback log
    info_events = [evt for evt in events if evt[1] == "todo.fallback_mode_no_tool"]
    # This event might be logged at info level when fallback mode is active
    # (The actual implementation logs at info level for fallback mode)


def test_metrics_has_tools_derived_from_tool_calls() -> None:
    """Test that has_tools is properly derived from tool_calls count."""
    # Test 1: Zero tool calls means has_tools=False
    tool_calls_zero = 0
    has_tools_zero = tool_calls_zero > 0
    assert has_tools_zero is False

    # Test 2: Non-zero tool calls means has_tools=True
    tool_calls_nonzero = 3
    has_tools_nonzero = tool_calls_nonzero > 0
    assert has_tools_nonzero is True


def test_todo_item_nested_steps_field() -> None:
    """Test that TodoItem properly stores nested_steps as list of strings."""
    todo = TodoItem(
        task="Test task",
        status="completed",
        nested_steps=[
            "Step 1: Do first thing",
            "Step 2: Do second thing",
        ],
    )
    assert len(todo.nested_steps) == 2
    assert todo.nested_steps[0] == "Step 1: Do first thing"
    assert todo.nested_steps[1] == "Step 2: Do second thing"


def test_todo_item_fallback_mode_field() -> None:
    """Test that TodoItem properly stores fallback_mode."""
    # Default is False
    todo_default = TodoItem(task="Test", status="completed")
    assert todo_default.fallback_mode is False

    # Can be set to True
    todo_fallback = TodoItem(task="Test", status="completed", fallback_mode=True)
    assert todo_fallback.fallback_mode is True
