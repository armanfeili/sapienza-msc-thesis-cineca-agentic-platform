# Agent Execution Test Improvements - Implementation Plan

**Date**: 2025-11-12  
**Status**: Ready for Implementation  
**Test File**: `tests/integration/test_agent_execution.py`

---

## Overview

The agent execution test currently passes (✅ 1 passed in 116.93s) but needs hardening to prevent regressions and catch edge cases. This document outlines 14 improvements with clear acceptance criteria.

## Current Issues

From the test output analysis:

1. ⚠️ **3 catalog.discover calls** - 1 real (79ms) + 2 "reused" (null latency)
2. ⚠️ **`request_id` is null** in final status (was set in create response)
3. ⚠️ **Null metrics**: `todo_creation_ms`, `todo_execution_ms` are null
4. ⚠️ **Duplicate warmup**: `model_warmup_ms` appears at root and in `metrics`
5. ℹ️ **Reused steps**: have `null` timing fields instead of zero values

---

## Implementation TODOs

### 1. Cache & Reuse Tool Catalog ✅

**Goal**: Cache catalog.discover results to avoid redundant calls.

**Current State**:
- 3 catalog.discover steps (1 real @ 79ms, 2 reused @ null latency)
- No explicit cache validation

**Implementation**:
```python
# In test_agent_run_executes_successfully:

# Step 5a: Assert only ONE real catalog.discover call
real_discover_calls = [
    step for step in steps 
    if step.get("action") == "catalog.discover" 
    and step.get("latency_ms") is not None
    and step.get("latency_ms") > 0
]

assert len(real_discover_calls) == 1, (
    f"Expected exactly 1 real catalog.discover call, found {len(real_discover_calls)}. "
    f"Catalog should be cached and reused within a run."
)

# Verify reused calls have zero latency
reused_discover_calls = [
    step for step in steps
    if step.get("action") == "catalog.discover"
    and step.get("input", {}).get("reused") == True
]

for reused_call in reused_discover_calls:
    latency = reused_call.get("latency_ms")
    assert latency == 0, (
        f"Reused catalog.discover call should have latency_ms=0, got {latency}"
    )

print(f"   ✅ Catalog caching verified: 1 real call, {len(reused_discover_calls)} reused")
```

**Acceptance**: Only 1 real catalog.discover with latency > 0; reused calls have latency_ms == 0.

---

### 2. Propagate `request_id` in Final Status ✅

**Goal**: Maintain request_id from creation through completion.

**Current State**:
- Create response has `x-request-id: 7c83dc72-cf76-476a-ac68-b537e491781f`
- Final status has `request_id: null`

**Implementation**:
```python
# After create_response
create_data = create_response.json()
creation_request_id = create_response.headers.get("x-request-id")

# After final status
final_status_data = requests.get(...).json()
final_request_id = final_status_data.get("request_id")

assert final_request_id is not None, "request_id should not be null in final status"
assert final_request_id == creation_request_id, (
    f"request_id mismatch: creation={creation_request_id}, final={final_request_id}"
)

print(f"   ✅ request_id propagated: {final_request_id}")
```

**Code Fix Required**:
```python
# In src/routers/agent_runs.py or orchestrator
# Store request_id from request context and persist to run record
```

**Acceptance**: Final status JSON has non-null request_id matching x-request-id header.

---

### 3. Fill Timing Metrics for Reused Steps ✅

**Goal**: Eliminate null timing fields in step records.

**Current State**:
```json
{
  "step_id": "todo-1-discover-reused",
  "started_at": null,
  "finished_at": null,
  "latency_ms": null
}
```

**Implementation**:
```python
# Validation in test
for step in steps:
    step_id = step.get("step_id")
    
    # Check if step is marked as reused
    is_reused = step.get("input", {}).get("reused", False)
    
    if is_reused:
        # Reused steps should have zero-duration timing
        assert step.get("latency_ms") == 0, (
            f"Reused step {step_id} should have latency_ms=0, got {step.get('latency_ms')}"
        )
        # started_at and finished_at should be present and equal (zero duration)
        started = step.get("started_at")
        finished = step.get("finished_at")
        assert started is not None, f"Reused step {step_id} missing started_at"
        assert finished is not None, f"Reused step {step_id} missing finished_at"
        assert started == finished, f"Reused step {step_id} should have started_at == finished_at"
    else:
        # Real steps must have valid timing
        assert step.get("latency_ms") is not None, f"Step {step_id} missing latency_ms"
        assert step.get("started_at") is not None, f"Step {step_id} missing started_at"
        assert step.get("finished_at") is not None, f"Step {step_id} missing finished_at"

print("   ✅ All steps have valid timing fields (no null values)")
```

**Code Fix Required**:
```python
# In orchestrator when recording reused steps
reused_step = {
    "type": "step",
    "step_id": f"{todo_id}-discover-reused",
    "action": "catalog.discover",
    "input": {"reused": True, "from_context": True},
    "started_at": current_time,  # Same timestamp
    "finished_at": current_time,  # Same timestamp
    "latency_ms": 0
}
```

**Acceptance**: No timing fields are null; reused steps have zeroed timing with started_at == finished_at.

---

### 4. Non-null Metrics: `todo_creation_ms` / `todo_execution_ms` ✅

**Goal**: Populate or remove unused metric fields.

**Current State**:
```json
{
  "metrics": {
    "todo_creation_ms": null,
    "todo_execution_ms": null
  }
}
```

**Implementation**:
```python
# In test
metrics = status_data.get("metrics", {})

# Option A: If these should be populated
todo_creation_ms = metrics.get("todo_creation_ms")
todo_execution_ms = metrics.get("todo_execution_ms")

assert todo_creation_ms is not None, "todo_creation_ms should be populated"
assert isinstance(todo_creation_ms, (int, float)), "todo_creation_ms should be numeric"
assert todo_creation_ms >= 0, "todo_creation_ms should be non-negative"

# Option B: If these are unused, they should not appear in response
assert "todo_creation_ms" not in metrics, "Unused field todo_creation_ms should be omitted"
```

**Code Fix Required**:
```python
# In orchestrator metrics collection
metrics = {
    "overall_ms": overall_latency,
    "llm": llm_metrics,
    "tools": tool_metrics,
    "model_warmup_ms": warmup_time,
    "todo_creation_ms": todo_creation_latency,  # Actually measure this
    "todo_execution_ms": todo_execution_latency,  # Actually measure this
    # ... OR remove these fields entirely
}
```

**Acceptance**: Both fields are meaningful numbers OR completely omitted (never null).

---

### 5. Warn if `model_warmup_ms` is Duplicated ✅

**Goal**: Single source of truth for warmup metric.

**Current State**:
```json
{
  "model_warmup_ms": 109903,
  "metrics": {
    "model_warmup_ms": 109903
  }
}
```

**Implementation**:
```python
# In test
root_warmup = status_data.get("model_warmup_ms")
metrics_warmup = metrics.get("model_warmup_ms")

# Assert: Only one location should have the value
if root_warmup is not None and metrics_warmup is not None:
    # If both exist, they must match
    assert root_warmup == metrics_warmup, (
        f"model_warmup_ms mismatch: root={root_warmup}, metrics={metrics_warmup}"
    )
    pytest.warn(
        "model_warmup_ms appears in both root and metrics. "
        "Consider using a single location to avoid confusion."
    )
elif root_warmup is None and metrics_warmup is None:
    pytest.fail("model_warmup_ms is missing from both root and metrics")

print(f"   ✅ model_warmup_ms: {root_warmup or metrics_warmup}ms (single source)")
```

**Code Fix Required**:
```python
# Choose one location - recommend metrics.model_warmup_ms
# Remove from root level or vice versa
```

**Acceptance**: Exactly one location contains the value; contract test enforces it.

---

### 6. Latency Budget Test ✅

**Goal**: Hard assertion for LLM cold-start budget.

**Current State**:
- Soft check: "109903ms (within 120000ms cold budget)" ✅
- No failure on budget violation

**Implementation**:
```python
# Define budgets
COLD_START_BUDGET_MS = 120_000  # 2 minutes
WARM_BUDGET_MS = 30_000  # 30 seconds
WARNING_THRESHOLD_MS = 90_000  # 1.5 minutes

first_llm = llm_metrics[0]
first_llm_latency = first_llm.get("latency_ms", 0)

# Hard assertion: Must be under budget
assert first_llm_latency <= COLD_START_BUDGET_MS, (
    f"First LLM call exceeded cold-start budget: {first_llm_latency}ms > {COLD_START_BUDGET_MS}ms. "
    f"Model warmup is taking too long."
)

# Warning threshold
if first_llm_latency > WARNING_THRESHOLD_MS:
    print(f"   ⚠️  Warning: First LLM call took {first_llm_latency}ms (>{WARNING_THRESHOLD_MS}ms)")
    print(f"      Consider model caching or using a pre-warmed model")
else:
    print(f"   ✅ First LLM call: {first_llm_latency}ms (within {COLD_START_BUDGET_MS}ms cold budget)")
```

**Acceptance**: Test fails when first LLM > 120s; warns when > 90s.

---

### 7. Security Path Smoke Tests ✅

**Goal**: Exercise graph.secure_query with positive and negative test cases.

**Implementation**:
```python
def test_graph_secure_query_validation(self, base_url, admin_headers, user_headers):
    """Test graph.secure_query security validation."""
    
    # Test 1: Benign read (should pass)
    benign_response = requests.post(
        f"{base_url}/v1/tools/graph.secure_query",
        headers=admin_headers,
        json={"prompt": "Show me all users"},
        timeout=30
    )
    assert benign_response.status_code == 200, "Benign read should succeed"
    print("   ✅ Benign read passed")
    
    # Test 2: Write attempt (should be blocked)
    write_response = requests.post(
        f"{base_url}/v1/tools/graph.secure_query",
        headers=admin_headers,
        json={"prompt": "DELETE all nodes"},
        timeout=30
    )
    assert write_response.status_code in [400, 403], (
        f"Write attempt should be blocked, got {write_response.status_code}"
    )
    print("   ✅ Write attempt blocked")
    
    # Test 3: Dangerous CALL statement (should be blocked)
    dangerous_response = requests.post(
        f"{base_url}/v1/tools/graph.secure_query",
        headers=admin_headers,
        json={"prompt": "CALL dbms.stop()"},
        timeout=30
    )
    assert dangerous_response.status_code in [400, 403], "Dangerous CALL should be blocked"
    print("   ✅ Dangerous CALL blocked")
    
    # Test 4: DETACH DELETE (should be blocked)
    detach_response = requests.post(
        f"{base_url}/v1/tools/graph.secure_query",
        headers=admin_headers,
        json={"prompt": "DETACH DELETE all nodes"},
        timeout=30
    )
    assert detach_response.status_code in [400, 403], "DETACH DELETE should be blocked"
    print("   ✅ DETACH DELETE blocked")
    
    # Test 5: Role-gated read (user vs admin)
    user_response = requests.post(
        f"{base_url}/v1/tools/graph.secure_query",
        headers=user_headers,
        json={"prompt": "Show admin-only data"},
        timeout=30
    )
    # User should either get limited results or 403
    assert user_response.status_code in [200, 403], "User query should be validated"
    
    admin_response = requests.post(
        f"{base_url}/v1/tools/graph.secure_query",
        headers=admin_headers,
        json={"prompt": "Show admin-only data"},
        timeout=30
    )
    # Admin should succeed (assuming data exists)
    if admin_response.status_code == 200:
        print("   ✅ Admin query succeeded")
    
    # Verify audit logging
    audit_response = requests.get(
        f"{base_url}/v1/security/audit",
        headers=admin_headers,
        timeout=10
    )
    assert audit_response.status_code == 200, "Should be able to retrieve audit logs"
    audit_data = audit_response.json()
    
    # Check that secure_query calls are logged
    secure_query_events = [
        event for event in audit_data.get("events", [])
        if "secure_query" in str(event).lower()
    ]
    assert len(secure_query_events) > 0, "secure_query calls should be audited"
    print(f"   ✅ {len(secure_query_events)} secure_query events audited")
```

**Acceptance**: All negative cases blocked with 400/403; positive read passes; all logged in audit.

---

### 8. Provider Health Expectations ✅

**Goal**: Validate provider enumeration matches configuration.

**Implementation**:
```python
# In Step 0b: Provider health check
providers_data = health_response.json().get("providers", [])

# Assert: Provider set is non-empty
assert len(providers_data) > 0, "Provider list should not be empty"

# Assert: Each provider lists at least one model
for provider in providers_data:
    provider_id = provider.get("provider_id")
    models = provider.get("models", [])
    assert len(models) > 0, (
        f"Provider {provider_id} should list at least one model, found {len(models)}"
    )
    print(f"   Provider {provider_id}: {len(models)} model(s)")

# If environment specifies expected provider count, validate
expected_provider_count = os.getenv("EXPECTED_PROVIDER_COUNT")
if expected_provider_count:
    expected_count = int(expected_provider_count)
    assert len(providers_data) == expected_count, (
        f"Expected {expected_count} providers, found {len(providers_data)}"
    )

print(f"   ✅ {len(providers_data)} provider(s) validated with models")
```

**Acceptance**: Test fails only on empty provider set or missing model list.

---

### 9. Tool List Contract ✅

**Goal**: Validate required tools exist with proper metadata.

**Implementation**:
```python
REQUIRED_TOOLS = [
    "agent.context",
    "catalog.discover",
    "graph.query",
    "system.metrics",
    "system.health",
    "model.manage",
    "cache.manage"
]

EXPECTED_CATEGORIES = {
    "agent.context": "agent",
    "catalog.discover": "catalog",
    "graph.query": "graph",
    "system.metrics": "system",
    "system.health": "system",
    "model.manage": "model",
    "cache.manage": "cache"
}

# Get tool details from discovery output
discovered_items = tools_output.get("items", [])
tool_details = {item["name"]: item for item in discovered_items}

for tool_name in REQUIRED_TOOLS:
    assert tool_name in tool_details, f"Required tool missing: {tool_name}"
    
    tool = tool_details[tool_name]
    
    # Validate description is non-empty
    description = tool.get("description", "")
    assert len(description) > 0, f"Tool {tool_name} has empty description"
    assert len(description) > 10, f"Tool {tool_name} description too short: '{description}'"
    
    # Validate category matches expected
    expected_category = EXPECTED_CATEGORIES[tool_name]
    actual_category = tool.get("category", "")
    assert actual_category == expected_category, (
        f"Tool {tool_name} has wrong category: expected '{expected_category}', got '{actual_category}'"
    )
    
    print(f"   ✅ {tool_name}: category={actual_category}, desc={len(description)} chars")

print(f"   ✅ All {len(REQUIRED_TOOLS)} required tools validated")
```

**Acceptance**: All required tools exist with non-empty description and correct category.

---

### 10. Structured Output Only ✅

**Goal**: Enforce pure JSON outputs (no prose).

**Implementation**: Already implemented in Step 5e, but enhance:

```python
def validate_no_prose(output_data, context=""):
    """Validate output contains no prose markers."""
    prose_indicators = [
        "i will", "let me", "here is", "here are", 
        "sure", "certainly", "i can", "of course", 
        "to accomplish", "first", "then", "finally",
        "step 1", "step 2"
    ]
    
    output_str = json.dumps(output_data).lower()
    
    found_indicators = []
    for indicator in prose_indicators:
        if indicator in output_str:
            found_indicators.append(indicator)
    
    assert len(found_indicators) == 0, (
        f"Prose indicators found in {context}: {found_indicators}. "
        f"Expected pure JSON structure only. "
        f"Content preview: {str(output_data)[:200]}"
    )

# Apply to all outputs
for output in outputs:
    output_data = output.get("output")
    step_id = output.get("step_id")
    validate_no_prose(output_data, context=f"output[{step_id}]")

print("   ✅ All outputs are pure structured JSON (no prose)")
```

**Acceptance**: Validator passes for all outputs; fails on prose.

---

### 11. Traceability ✅

**Goal**: Assert trace_id and event_id are present and valid.

**Implementation**:
```python
# Validate trace_id
trace_id = status_data.get("trace_id")
assert trace_id is not None, "trace_id should not be null"
assert len(trace_id) > 0, "trace_id should not be empty"
assert "-" in trace_id, "trace_id should be UUID format (contains hyphens)"

# Validate event_id
event_id = status_data.get("event_id")
assert event_id is not None, "event_id should not be null"
assert len(event_id) > 0, "event_id should not be empty"

# Verify trace_id is stable across requests for same run
second_status = requests.get(f"{base_url}/v1/agent-runs/{run_id}", headers=admin_headers).json()
second_trace_id = second_status.get("trace_id")
assert second_trace_id == trace_id, (
    f"trace_id should be stable across requests: {trace_id} vs {second_trace_id}"
)

print(f"   ✅ Traceability validated: trace_id={trace_id[:8]}..., event_id={event_id[:8]}...")
```

**Acceptance**: Both fields exist, are non-empty, and trace_id is stable.

---

### 12. Metrics Roll-up Consistency ✅

**Goal**: Make timing drift check a hard assertion.

**Implementation**: Already implemented in Step 2c, enhance:

```python
# STRICT: Convert to hard assertion
tolerance_percent = 5  # ±5% tolerance
tolerance_multiplier = tolerance_percent / 100.0

started_str = status_data.get('started_at')
finished_str = status_data.get('finished_at')
overall_ms = metrics.get("overall_ms")

if started_str and finished_str:
    started = datetime.fromisoformat(started_str.replace('Z', '+00:00'))
    finished = datetime.fromisoformat(finished_str.replace('Z', '+00:00'))
    actual_duration_ms = int((finished - started).total_seconds() * 1000)
    
    lower_bound = actual_duration_ms * (1 - tolerance_multiplier)
    upper_bound = actual_duration_ms * (1 + tolerance_multiplier)
    
    # HARD ASSERTION (no longer just print)
    assert lower_bound <= overall_ms <= upper_bound, (
        f"overall_ms ({overall_ms}ms) doesn't match actual duration ({actual_duration_ms}ms) within ±{tolerance_percent}%. "
        f"Expected range: {int(lower_bound)}-{int(upper_bound)}ms. "
        f"This indicates a metrics collection bug."
    )
    
    drift_percent = abs(overall_ms - actual_duration_ms) / actual_duration_ms * 100
    print(f"   ✅ overall_ms: {overall_ms}ms (drift: {drift_percent:.2f}%)")
```

**Acceptance**: Test fails when drift exceeds ±5%.

---

### 13. Catalog Count Guardrail ✅

**Goal**: Range check + specific membership validation.

**Implementation**: Already partially implemented, enhance:

```python
# Range validation
MIN_TOOLS = 25
MAX_TOOLS = 60

assert MIN_TOOLS <= tools_count <= MAX_TOOLS, (
    f"Tools count {tools_count} outside expected range [{MIN_TOOLS}, {MAX_TOOLS}]. "
    f"Tool discovery may be incomplete or excessive."
)

# Specific membership validation (from TODO #9)
for tool_name in REQUIRED_TOOLS:
    assert tool_name in discovered_tool_names, (
        f"Required tool '{tool_name}' not found in discovered tools. "
        f"Found: {discovered_tool_names}"
    )

print(f"   ✅ Tool count validated: {tools_count} tools (range: {MIN_TOOLS}-{MAX_TOOLS})")
print(f"   ✅ All {len(REQUIRED_TOOLS)} required tools present")
```

**Acceptance**: Both range and membership tests pass.

---

### 14. Status Summary Parity ✅

**Goal**: Ensure tools_count matches tools array length.

**Implementation**:
```python
# Validate at creation
create_output = create_data.get("output", {})
if "tools_count" in create_output and "tools" in create_output:
    create_count = create_output["tools_count"]
    create_tools = create_output["tools"]
    assert create_count == len(create_tools), (
        f"Create output tools_count mismatch: count={create_count}, len(tools)={len(create_tools)}"
    )

# Validate in final status
final_output = status_data.get("output", {})
if "tools_count" in final_output and "tools" in final_output:
    final_count = final_output["tools_count"]
    final_tools = final_output["tools"]
    assert final_count == len(final_tools), (
        f"Final output tools_count mismatch: count={final_count}, len(tools)={len(final_tools)}"
    )

# Validate in tool discovery output
if tools_output:
    disco_count = tools_output.get("tools_count")
    disco_tools = tools_output.get("tools", [])
    assert disco_count == len(disco_tools), (
        f"Tool discovery tools_count mismatch: count={disco_count}, len(tools)={len(disco_tools)}"
    )

print("   ✅ tools_count matches tools array length in all outputs")
```

**Acceptance**: Test checks parity in all locations and fails on mismatch.

---

## Implementation Priority

### Phase 1: Critical (Immediate)
1. ✅ TODO #1: Cache catalog.discover
2. ✅ TODO #2: Propagate request_id
3. ✅ TODO #3: Fill timing for reused steps
4. ✅ TODO #4: Non-null metrics
5. ✅ TODO #6: Latency budget hard assertion
6. ✅ TODO #12: Metrics roll-up hard assertion

### Phase 2: Important (Next Sprint)
7. ✅ TODO #5: Deduplicate model_warmup_ms
8. ✅ TODO #9: Tool list contract
9. ✅ TODO #10: Structured output validation
10. ✅ TODO #11: Traceability
11. ✅ TODO #13: Catalog count guardrail
12. ✅ TODO #14: Status summary parity

### Phase 3: Security (Separate PR)
13. ✅ TODO #7: Security path smoke tests
14. ✅ TODO #8: Provider health expectations

---

## Code Changes Required

### Backend Changes (src/):

1. **Orchestrator** (`src/orchestrator/`):
   - Cache catalog.discover results per run/session
   - Propagate request_id through execution
   - Fill timing for reused steps (zero duration)
   - Populate todo_creation_ms and todo_execution_ms
   - Deduplicate model_warmup_ms location

2. **API Routers** (`src/routers/agent_runs.py`):
   - Capture and persist request_id from headers
   - Ensure all metrics fields are populated or omitted (never null)

### Test Changes:

1. **test_agent_execution.py**:
   - Add all 14 validation checks with hard assertions
   - Create separate test for security validation (#7)
   - Add provider health validation (#8)
   - Enhance existing checks to be strict

---

## Success Criteria

✅ **All 14 TODOs implemented with passing tests**  
✅ **Zero null fields in metrics/timing**  
✅ **Only 1 real catalog.discover call per run**  
✅ **request_id propagated correctly**  
✅ **Latency budget enforced**  
✅ **Security paths validated**  
✅ **Test coverage > 95%**  

---

## Next Steps

1. Review this plan with team
2. Create GitHub issues for each TODO
3. Implement Phase 1 (Critical) in current sprint
4. Create separate PR for security tests (Phase 3)
5. Update documentation with new test coverage

---

**Ready for Implementation** 🚀
