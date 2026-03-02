# Agent Run Schema Documentation

## Overview

This document defines the canonical schema for `AgentRun` objects across success and failure paths.

## Top-Level AgentRun Fields

```json
{
  "id": "uuid",
  "session_id": "uuid",
  "user_id": "string",
  "tenant_id": "string",
  "prompt": "string",
  "status": "queued|running|succeeded|failed",
  "model": "string|null",
  "latency_ms": "integer|null",
  "created_at": "datetime",
  "started_at": "datetime|null",
  "finished_at": "datetime|null",
  "output": "object|null",
  "steps": "array|null",
  "todos": "array|null",
  "warnings": "array|null",
  "metrics": "object|null",
  "event_id": "uuid|null"
}
```

## Output Structure

### Success Path

When a run completes successfully:

```json
{
  "output": {
    "summary": "High-level summary of results",
    "data": {
      "result": "Actual result data",
      "tools": [...],
      "count": 42
    },
    "todos_completed": 3,
    "todos_failed": 0
  }
}
```

Or for tool discovery:

```json
{
  "output": {
    "tools": [
      {
        "name": "catalog.discover",
        "category": "query",
        "description": "..."
      }
    ],
    "tools_count": 15,
    "source_groups": ["memgraph", "postgres"]
  }
}
```

### Failure Path

When a run fails (timeout, error, etc.):

```json
{
  "output": {
    "error": "Human-readable error message",
    "failure_type": "run_timeout|todo_plan_timeout|todo_step_timeout|orchestrator_error|llm_error|tool_error",
    "partial_results": true,
    "todos_completed": 1,
    "todos_failed": 1,
    "context": {
      "timeout_seconds": 300,
      "failed_todo_index": 2,
      "step_id": "..."
    }
  }
}
```

#### Failure Types

- **`run_timeout`**: Entire orchestration exceeded `AGENT_RUN_TIMEOUT_SECONDS` (default: 300s)
- **`todo_plan_timeout`**: Planning phase for a TODO exceeded `LLM_STEP_TIMEOUT_SECONDS` (default: 120s)
- **`todo_step_timeout`**: Step execution within a TODO exceeded timeout
- **`orchestrator_error`**: General orchestrator execution error
- **`llm_error`**: LLM call failed or returned error
- **`tool_error`**: Tool execution failed
- **`validation_error`**: Input/output validation failed

## Steps Structure

Array of `OrchestrationStepOutput` objects:

```json
{
  "steps": [
    {
      "type": "output",
      "step_id": "1",
      "output": {
        "result": "data"
      },
      "error": null,
      "started_at": "2025-11-15T12:00:00Z",
      "finished_at": "2025-11-15T12:00:01Z",
      "latency_ms": 1000
    }
  ]
}
```

### Required Fields
- `step_id` (string): Unique identifier for the step
- `type` (literal): Always `"output"`

### Optional Fields
- `output` (dict|null): Output data from step execution (MUST be dict if present)
- `error` (string|null): Error message if step failed
- `started_at` (datetime|null): ISO timestamp when step started
- `finished_at` (datetime|null): ISO timestamp when step finished
- `latency_ms` (integer|null): Execution time in milliseconds

### Validation Rules
1. **`output` MUST be dict, not string**
   - ✅ `{"result": "success"}`
   - ✅ `{"error": "Something failed"}`
   - ❌ `"plain string"` (will raise Pydantic ValidationError)

2. **Timing consistency**
   - If `started_at` and `finished_at` present, `latency_ms` calculated automatically
   - `finished_at` >= `started_at`

3. **Error steps**
   - If `error` is set, `output` should still be a dict (e.g., `{"error": "..."}`)
   - Both `error` and `output` can coexist

## TODOs Structure

Array of `TodoItem` objects:

```json
{
  "todos": [
    {
      "task": "Discover available tools",
      "status": "completed"
    },
    {
      "task": "Query database",
      "status": "failed_due_to_timeout"
    }
  ]
}
```

### Status Values
- `"queued"`: TODO not yet started
- `"running"`: Currently executing
- `"completed"`: Successfully completed
- `"failed"`: Failed due to error
- `"failed_due_to_timeout"`: Failed because run timed out
- `null`: Status not yet determined

## Partial Results on Failure

When a run fails (e.g., timeout), partial results SHOULD be preserved:

```json
{
  "status": "failed",
  "output": {
    "error": "Orchestration timeout after 300s",
    "failure_type": "run_timeout",
    "partial_results": true,
    "todos_completed": 1,
    "todos_failed": 1
  },
  "steps": [
    {
      "step_id": "1",
      "output": {"tools": [...]},
      "latency_ms": 5000
    }
  ],
  "todos": [
    {
      "task": "Discover tools",
      "status": "completed"
    },
    {
      "task": "Query database",
      "status": "failed_due_to_timeout"
    }
  ]
}
```

**Key Points:**
- Completed TODOs remain in `todos` array with `status="completed"`
- Incomplete TODOs marked with `status="failed_due_to_timeout"`
- Steps from completed TODOs preserved in `steps` array
- `output.partial_results=true` indicates partial success

## Metrics Structure

```json
{
  "metrics": {
    "overall_ms": 15000,
    "total_llm_calls": 3,
    "tool_calls": 2,
    "tool_errors": 0,
    "model_warmup_ms": 108712,
    "llm": [
      {
        "model": "phi3:mini",
        "latency_ms": 5000,
        "success": true
      }
    ],
    "tools": [
      {
        "tool": "catalog.discover",
        "latency_ms": 500,
        "success": true
      }
    ]
  }
}
```

## Validation Examples

### ✅ Valid Error Output

```python
OrchestrationStepOutput(
    step_id="test",
    output={"error": "Timeout occurred"},
    error="Timeout occurred"
)
```

### ❌ Invalid String Output

```python
OrchestrationStepOutput(
    step_id="test",
    output="Timeout occurred"  # INVALID - raises ValidationError
)
```

### ✅ Valid Timeout Output

```python
{
    "output": {
        "error": "Orchestration timeout after 300s",
        "failure_type": "run_timeout",
        "timeout_seconds": 300,
        "partial_results": true
    }
}
```

## Migration Notes

### From Old to New Schema

If you have code that creates string outputs, update to dict:

```python
# OLD (will fail validation)
output = "Error message"

# NEW (correct)
output = {"error": "Error message"}
```

### Testing Your Code

Use the validation test suite:
```bash
pytest tests/unit/test_orchestration_output_validation.py -v
```

## References

- **Pydantic Models**: `src/schemas/agents.py`
  - `OrchestrationStepInput`
  - `OrchestrationStepOutput`
  - `TodoItem`
  - `ExecutionMetrics`

- **Failure Types**: `src/models/failure_types.py`
  - `FailureType` enum
  - `get_failure_message()` helper

- **Orchestrator**: `src/services/orchestrator.py`
  - Timeout configuration
  - Error handling
  - Result construction

- **Agent Runs Router**: `src/routers/agent_runs.py`
  - Background execution
  - Result serialization
  - Status updates
