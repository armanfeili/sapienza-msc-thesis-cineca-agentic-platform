"""Quick schema validation test"""
import sys
from pathlib import Path

# Add project root to path (scripts/debug -> root)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.schemas.agents import (
    OrchestrationStepInput,
    OrchestrationStepOutput,
    TodoItem,
    ExecutionMetrics,
    RunResponse,
)

# Test OrchestrationStepInput
step_input = OrchestrationStepInput(
    step_id="step-1",
    action="test_action",
    input={"key": "value"}
)
print(f"✅ OrchestrationStepInput created: {step_input.model_dump()}")

# Test OrchestrationStepOutput
step_output = OrchestrationStepOutput(
    step_id="step-1",
    output={"result": "success"},
    error=None
)
print(f"✅ OrchestrationStepOutput created: {step_output.model_dump()}")

# Test TodoItem
todo = TodoItem(
    task="Test task",
    status="pending"
)
print(f"✅ TodoItem created: {todo.model_dump()}")

# Test ExecutionMetrics
metrics = ExecutionMetrics(
    model_warmup_ms=100,
    todo_creation_ms=50,
    total_llm_calls=3,
    tool_errors=0,
    step_count=5
)
print(f"✅ ExecutionMetrics created: {metrics.model_dump()}")

# Test RunResponse with typed fields
from datetime import datetime, timezone
from uuid import uuid4

run_response = RunResponse(
    run_id=uuid4(),
    session_id=uuid4(),
    user_id="test-user",
    tenant_id="test-tenant",
    status="succeeded",
    prompt="Test prompt",
    output="Test output",
    model="test-model",
    latency_ms=1000,
    created_at=datetime.now(timezone.utc),
    started_at=datetime.now(timezone.utc),
    finished_at=datetime.now(timezone.utc),
    steps=[step_input, step_output],
    todos=[todo],
    errors=["test error"],
    metrics=metrics
)
print(f"✅ RunResponse created with typed fields")
print(f"   Steps: {len(run_response.steps)} ({type(run_response.steps[0]).__name__}, {type(run_response.steps[1]).__name__})")
print(f"   Todos: {len(run_response.todos)} ({type(run_response.todos[0]).__name__})")
print(f"   Errors: {run_response.errors}")
print(f"   Metrics: {run_response.metrics.model_dump() if run_response.metrics else None}")

# Test serialization
serialized = run_response.model_dump(mode="json")
print(f"\n✅ Serialization successful")
print(f"   Steps in JSON: {[s.get('step_id') for s in serialized['steps']]}")
print(f"   Todos in JSON: {[t.get('task')[:20] for t in serialized['todos']]}")

print("\n🎉 All schema validations passed!")
