# Rough Edges Fix Plan
**Date**: November 10, 2025  
**Status**: Implementation Ready  
**Scope**: 12 polish issues identified in production logs

---

## Executive Summary

This document provides actionable fixes for 12 remaining rough edges in the agent execution telemetry system. Each issue includes:
- Root cause analysis
- Specific file locations
- Implementation approach (no code, per request)
- Validation strategy

---

## Issue 1: Misleading Token-Fetch Log in Docker

### Problem
```
⚠ fetch_auth0_tokens.sh failed: [stderr]
✓ Using tokens from environment variables (Docker)
```
The "failed" message appears even though this is **expected behavior** in Docker.

### Root Cause
`tests/conftest.py` line 115: Always prints "failed" when script exits non-zero, without checking if we're in Docker.

### Fix Approach
**File**: `tests/conftest.py` (lines ~108-116)

**Before logging the warning**:
1. Check if `RUNNING_IN_DOCKER` env var is set or `/.dockerenv` exists
2. If in Docker: Log "⏩ Skipping Auth0 token fetch (using Docker env vars)" at INFO level
3. If not in Docker: Keep current warning behavior

**Validation**:
- Run integration test in Docker → Should see "Skipping" message, not "failed"
- Run test locally → Should still see warning if script fails

---

## Issue 2: Model Name Format Inconsistency

### Problem
```json
{
  "model": "phi3-mini",           // Top-level
  "metrics": {
    "llm_calls": [
      {"model": "phi3:mini"}       // LLM metric (different format)
    ]
  }
}
```
This breaks grouping/filtering in dashboards.

### Root Cause
`src/config.py` line 440: Maps `"phi3-mini-q4"` → `"phi3:mini"` in model resolution, but top-level field uses input name while metrics use resolved name.

### Fix Approach
**Files**:
- `src/routers/agent_runs.py` (line ~401: `model=used_model`)
- `src/services/orchestrator.py` (model name propagation)

**Strategy**:
1. Create `normalize_model_name(name: str) -> str` utility function
   - Apply consistent transformation: `phi3-mini` → `phi3:mini`
   - Handle all variants: `phi3-mini-q4`, `phi3-mini-instruct` → `phi3:mini`
   
2. Apply normalization at ingestion:
   - In orchestrator before storing LLM metrics
   - In agent_runs router before setting `run.model`
   
3. Add validation in `RunResponse` model validator:
   - Assert: `self.model == self.metrics.llm_calls[0].model` (if LLM calls exist)

**Validation**:
- Create agent run → Both top-level and metrics show `phi3:mini`
- Add test: `test_model_name_consistency()`

---

## Issue 3: Trace ID Flips Between Responses

### Problem
```json
// POST response:
{"trace_id": "f492...", "x-request-id": "4845..."}

// GET response (same run):
{"trace_id": "4845..."}  // Now matches x-request-id!
```

### Root Cause
`src/routers/agent_runs.py` lines 401 & 424:
- Line 401: Sets `trace_id=request_id` when saving run
- Line 424: Overwrites with `result.trace_id = ev.trace_id` from provenance event

### Fix Approach
**File**: `src/routers/agent_runs.py` (lines 400-430)

**Strategy**:
1. **Keep stable trace_id**: Set once at run creation, never overwrite
   - Line 401: Use a **stable** trace ID (e.g., generate UUID at run creation)
   - Do NOT use `request_id` as trace_id
   
2. **Add separate request_id field**:
   - Add `request_id: str | None` to `RunResponse` schema
   - Line 424: Set `result.request_id = request_id` (from context)
   - Keep `result.trace_id = ev.trace_id` (from provenance, stable)

3. **Update X-Request-Id header**:
   - Header reflects HTTP request ID
   - Response body `request_id` matches header
   - Response body `trace_id` is stable across requests

**Validation**:
- POST /agent-runs → Save `trace_id` from response
- GET /agent-runs/{id} → Assert `trace_id` unchanged
- Both responses include separate `request_id` matching `X-Request-Id` header

---

## Issue 4: Event ID Disappears

### Problem
```json
// POST response:
{"event_id": "abc123"}

// GET response:
{"event_id": null}
```

### Root Cause
`src/routers/agent_runs.py` line 425: Only sets `event_id` in POST response, but field is not persisted to database.

### Fix Approach
**Files**:
- `db/postgres_control/tables.py` - Add `event_id` column to `agent_runs` table
- `src/routers/agent_runs.py` - Persist event_id

**Strategy**:
1. **Add DB column**: 
   - Migration: `ALTER TABLE agent_runs ADD COLUMN event_id TEXT NULL`
   
2. **Persist at creation**:
   - Line 401: Add `event_id=ev.event_id` when creating run record
   
3. **Consistent serialization**:
   - Line 425: Remove override (now comes from DB)
   - GET endpoint: Will naturally include persisted event_id

4. **Add test**:
   - Assert `create_response.event_id == get_response.event_id`
   - Assert `event_id` is non-null and stable

**Validation**:
- Create run → GET run → `event_id` matches and is non-null
- Test: `test_event_id_persistence()`

---

## Issue 5: Output Type Drift (Empty String vs Object)

### Problem
```json
// POST response (immediate):
{"output": ""}

// GET response (after completion):
{"output": {"result": "...", "summary": "..."}}
```

### Root Cause
`src/routers/agent_runs.py`:
- Line 216: Initializes `output_text: str = ""`
- Line 397: Stores `output=final_output_obj` (object)
- Line 427: Overrides with `result.output = output_text` (string)

### Fix Approach
**File**: `src/routers/agent_runs.py` (lines 216, 397, 427)

**Strategy**:
1. **Never use empty string**:
   - Line 216: Initialize `output_text: str | None = None`
   - Line 427: Only set if output is actually ready: 
     ```python
     result.output = final_output_obj if final_output_obj else None
     ```

2. **Schema validation**:
   - Update `RunResponse.output` type: `dict | list | None` (remove `str`)
   - Add validator: Reject empty strings (`""`)

3. **Consistent population**:
   - If status is `succeeded`, output MUST be dict/list
   - If status is `running/pending`, output MUST be None
   - If status is `failed`, output MAY be None or error dict

**Validation**:
- POST response: `output` is `null` (not `""`)
- GET completed run: `output` is object
- Add schema test: `assert response.output != ""`

---

## Issue 6: Step Timing Incomplete/Inconsistent

### Problem
```json
{
  "steps": [
    {"name": "create-todos", "started_at": null, "finished_at": null},
    {"name": "tool-output", "latency_ms": null},
    {"name": "final-output", "started_at": "T1", "finished_at": "T1"}  // Same timestamp
  ]
}
```

### Root Cause
`src/services/orchestrator.py`: Step timing not consistently captured for all step types.

### Fix Approach
**File**: `src/services/orchestrator.py` (step creation logic)

**Strategy**:
1. **Always stamp timestamps**:
   - Every step creation: Set `started_at = datetime.now(timezone.utc)`
   - Every step completion: Set `finished_at = datetime.now(timezone.utc)`
   - Compute `latency_ms = (finished - started).total_seconds() * 1000`

2. **Handle zero-duration steps**:
   - If `finished_at == started_at`: Set `latency_ms = 0` (not `null`)
   - This represents "effectively instant" operations

3. **Add validation**:
   - In `OrchestrationStepOutput` model validator:
     ```python
     if self.finished_at and self.started_at:
         assert self.finished_at >= self.started_at
         if self.latency_ms is None:
             self.latency_ms = 0
     ```

**Validation**:
- All steps have non-null `started_at`, `finished_at`
- All steps have `latency_ms >= 0` (never null)
- Add test: `test_step_timing_completeness()`

---

## Issue 7: Rollup Metrics Stay Null

### Problem
```json
{
  "metrics": {
    "model_warmup_ms": null,
    "todo_creation_ms": null,
    "todo_execution_ms": null
  }
}
```

### Root Cause
`src/schemas/agents.py` lines 203-205: Fields defined but never populated in orchestrator.

### Fix Approach
**Files**:
- `src/services/orchestrator.py` - Compute rollups from events
- `src/routers/agent_runs.py` - Persist to database

**Strategy**:
1. **Track phase timings in orchestrator**:
   - Start warmup: `warmup_start = time.time()`
   - End warmup: `warmup_end = time.time()` → `model_warmup_ms = (end - start) * 1000`
   - Same for TODO creation/execution phases

2. **Add to metrics object**:
   - In `final_metrics` dict (line ~391):
     ```python
     final_metrics = {
         "model_warmup_ms": compute_warmup_duration(steps),
         "todo_creation_ms": compute_todo_creation_duration(steps),
         "todo_execution_ms": compute_todo_execution_duration(steps),
         ...
     }
     ```

3. **Helper functions**:
   - `compute_warmup_duration(steps)`: Sum latency of warmup-related steps
   - `compute_todo_creation_duration(steps)`: Find "create-todos" step latency
   - `compute_todo_execution_duration(steps)`: Sum latency of all execution steps

**Validation**:
- All rollup fields are non-null positive integers
- Test: Rollups match sum of granular timings (within 10ms tolerance)
- Add test: `test_rollup_metrics_populated()`

---

## Issue 8: TODOs Marked Completed Without Evidence

### Problem
```json
{
  "todos": [
    {"title": "Initiate llm:planner", "status": "completed"}  // But no planner calls in steps!
  ]
}
```

### Root Cause
TODO status set optimistically without verifying corresponding step execution.

### Fix Approach
**File**: `src/services/orchestrator.py` (TODO tracking logic)

**Strategy**:
1. **Strict completion criteria**:
   - Mark `completed` ONLY if matching step exists in `steps` array
   - Match by: TODO description contains tool name AND step tool matches

2. **Add status variants**:
   - `completed`: Step recorded in execution log
   - `skipped`: Not executed (with reason: "not_required", "optional", etc.)
   - `not_applicable`: Planned but not relevant after analysis

3. **Post-execution reconciliation**:
   - After all steps complete, iterate TODOs:
     ```python
     for todo in todos:
         if todo.status == "completed":
             has_matching_step = any(
                 step.tool == extract_tool_name(todo.title) 
                 for step in steps
             )
             if not has_matching_step:
                 todo.status = "not_applicable"
                 todo.reason = "No matching step found"
     ```

**Validation**:
- Every "completed" TODO has at least one matching step
- Add test: `test_todo_completion_evidence()`
- Log warning if TODO marked completed without evidence

---

## Issue 9: Final-Tools-Output Zero-Time Step

### Problem
```json
{
  "name": "final-tools-output",
  "started_at": "2024-11-10T15:47:43.123Z",
  "finished_at": "2024-11-10T15:47:43.123Z",  // Same timestamp
  "latency_ms": null
}
```

### Root Cause
Step created with same start/end time, but `latency_ms` not set to 0.

### Fix Approach
**File**: `src/services/orchestrator.py` (step finalization)

**Strategy**:
1. **Set latency_ms for zero-duration steps**:
   ```python
   if step.started_at and step.finished_at:
       duration_ms = (step.finished_at - step.started_at).total_seconds() * 1000
       step.latency_ms = max(0, int(duration_ms))  // Ensure non-negative
   ```

2. **Add model validator** in `OrchestrationStepOutput`:
   ```python
   @model_validator(mode='after')
   def ensure_latency_populated(self):
       if self.started_at and self.finished_at and self.latency_ms is None:
           duration = (self.finished_at - self.started_at).total_seconds() * 1000
           self.latency_ms = max(0, int(duration))
       return self
   ```

**Validation**:
- No steps have `latency_ms: null` when timestamps exist
- Zero-duration steps show `latency_ms: 0`
- Test: `test_zero_duration_step_latency()`

---

## Issue 10: Top-Level Metric Duplication

### Problem
```json
{
  "total_llm_calls": 3,  // Top-level
  "metrics": {
    "total_llm_calls": 3  // Duplicate!
  }
}
```

### Root Cause
`src/schemas/agents.py` lines 252-254: Rollup fields exist at both levels.

### Fix Approach
**File**: `src/schemas/agents.py` (RunResponse schema)

**Strategy** (Two options - recommend Option 2):

**Option 1: Keep only in metrics**
- Remove top-level fields: `total_llm_calls`, `tool_calls`, `tool_errors`
- All consumers read from `metrics.*`
- Simpler, single source of truth

**Option 2: Keep both but compute at serialization** (RECOMMENDED)
- Keep both locations for backwards compatibility
- Add validator that auto-populates top-level from metrics:
  ```python
  @model_validator(mode='after')
  def sync_rollup_metrics(self):
      if self.metrics:
          self.total_llm_calls = len(self.metrics.llm_calls or [])
          self.tool_calls = len(self.metrics.tool_calls or [])
          self.tool_errors = sum(1 for tc in (self.metrics.tool_calls or []) if tc.error)
      return self
  ```

**Validation**:
- Add contract test: `assert response.total_llm_calls == len(response.metrics.llm_calls)`
- Test all three rollup fields match
- Test: `test_rollup_metrics_consistency()`

---

## Issue 11: Health/Warmup Log Polish

### Problem
```
🔄 Checking component health...
   Overall status: degraded
   ✅ All providers healthy (Ollama ready)
```
Shows "degraded" then immediately "healthy" - confusing sequence.

### Root Cause
`tests/integration/test_agent_execution.py` lines 326-360: Prints "degraded" during warmup wait loop.

### Fix Approach
**File**: `tests/integration/test_agent_execution.py` (provider health check section)

**Strategy**:
1. **Change warmup status wording**:
   - Instead of printing raw status ("degraded"), print semantic message
   - If status is not "ok": Print "⏳ Providers warming up... (attempt {n}/30)"
   - Only print "⚠️ Providers degraded" if we exhaust retries AND have explicit `ALLOW_DEGRADED_PROVIDERS` flag

2. **Update health component status**:
   - `src/health/components.py`: Return `"warming_up"` status during initial load
   - Only return `"degraded"` if warmup fails after timeout
   - Return `"ok"` once warmup succeeds

3. **Test output flow**:
   ```
   🔄 Waiting for provider warmup to complete...
      ⏳ Providers warming up... (checking every 2s)
      ✅ All providers healthy (Ollama ready)
   ```

**Validation**:
- Run integration test → Should see "warming up" not "degraded"
- Only see "degraded" if we give up after 30s
- Clean, progressive status messages

---

## Issue 12: Create Response Already "Succeeded" with Empty Output

### Problem
```json
// POST /agent-runs response (immediate):
{
  "status": "succeeded",
  "finished_at": "2024-11-10T15:47:43Z",
  "output": ""  // Empty! Work still finishing in background?
}
```

### Root Cause
**Race condition**: Response serialized before orchestrator completes output population.

### Fix Approach
**File**: `src/routers/agent_runs.py` (create endpoint, lines 390-435)

**Strategy** (Two options - recommend Option 2):

**Option 1: Return initial snapshot**
- Return `status: "running"` immediately after orchestration starts
- Set `finished_at: null`, `output: null`
- Client polls GET endpoint for completion

**Option 2: Refresh before response** (RECOMMENDED)
- After orchestration completes (line 403: `db.commit()`)
- Add: `db.refresh(run)` to ensure latest state
- Add transactional read with lock if needed:
  ```python
  db.commit()  # Commit orchestrator results
  db.expire_all()  # Clear session cache
  db.refresh(run)  # Re-read from DB
  ```
- Ensure `final_output_obj` is fully populated before setting `run.output`

**Validation**:
- POST response: If `status == "succeeded"`, then `output` MUST be non-null object
- Add test: `test_create_response_consistency()`
- Add assertion before response:
  ```python
  if run.status == "succeeded":
      assert run.output is not None and run.output != ""
  ```

---

## Implementation Priority

### Phase 1: Critical Data Integrity (High Priority)
1. **Issue 5**: Output type drift - Prevents schema violations
2. **Issue 3**: Trace ID stability - Breaks tracing/correlation
3. **Issue 6**: Step timing completeness - Required for SLA monitoring
4. **Issue 12**: Create response race - Data consistency issue

### Phase 2: Observability & Polish (Medium Priority)
5. **Issue 2**: Model name consistency - Breaks dashboards
6. **Issue 4**: Event ID persistence - Audit trail gaps
7. **Issue 7**: Rollup metrics - Performance monitoring
8. **Issue 8**: TODO completion evidence - Correctness validation

### Phase 3: User Experience (Lower Priority)
9. **Issue 1**: Docker log message - Cosmetic but confusing
10. **Issue 11**: Health log polish - UX improvement
11. **Issue 9**: Zero-time step - Edge case handling
12. **Issue 10**: Metric duplication - Technical debt

---

## Testing Strategy

### Unit Tests (Per Issue)
Each fix should include focused unit test:
```python
# Example for Issue 2
def test_model_name_consistency():
    response = create_agent_run(model="phi3-mini-q4")
    assert response.model == "phi3:mini"
    assert response.metrics.llm_calls[0].model == "phi3:mini"
```

### Integration Test Additions
Add to `tests/integration/test_agent_execution.py`:
- Section: "Rough Edges Validation"
- Validate all 12 fixes in one comprehensive test run
- Use real orchestration to catch serialization issues

### Contract Tests
Add to new file `tests/test_response_contracts.py`:
- Schema validation (output never `""`)
- Field consistency (model names match)
- Metric math (rollups match granular)
- Stability (trace_id/event_id don't change)

---

## Rollback Plan

Each fix is isolated, so rollback is per-issue:

1. **Database changes** (Issue 4):
   - Migration file includes DOWN migration
   - Can roll back column addition safely

2. **Schema changes** (Issues 2, 3, 5, 10):
   - Use Pydantic `Field(deprecated=True)` for backwards compat
   - Keep old fields populated during transition

3. **Logic changes** (Issues 6, 7, 8, 9, 11, 12):
   - Feature flag: `ENABLE_POLISHED_TELEMETRY=true`
   - Default: false (old behavior)
   - Enable gradually per environment

---

## Success Metrics

**Before Fixes**:
- 12 known inconsistencies in prod logs
- Dashboard queries require complex normalization
- Support tickets about "disappeared" trace IDs

**After Fixes**:
- Zero schema violations in response validation tests
- 100% of completed TODOs have matching steps
- All timestamps non-null, all latencies >= 0
- Single stable trace_id per run across all requests
- Clean, progressive health check logs

**Validation Command**:
```bash
# Run comprehensive validation
pytest tests/integration/test_agent_execution.py::TestAgentExecution::test_rough_edges_validation -v

# Expected: All assertions pass, clean logs
```

---

## Dependencies & Risks

### External Dependencies
- None - all fixes are internal refactoring

### Risks
1. **Schema breaking changes**: Mitigated by backwards-compatible field additions
2. **Performance impact**: Minimal (only adds validators, no new queries)
3. **Test brittleness**: Mitigated by using real orchestration in tests

### Assumptions
- Orchestrator completes before POST response (Issue 12 assumes synchronous execution)
- Model name normalization rules are complete (Issue 2 may need updates for new models)
- TODO-to-step matching logic is accurate (Issue 8 requires clear naming conventions)

---

## Next Steps

1. **Review this plan** with team
2. **Create tracking tickets** (one per issue or one epic with 12 sub-tasks)
3. **Implement Phase 1** (critical fixes)
4. **Run integration tests** after each phase
5. **Deploy to staging** with feature flag
6. **Monitor metrics** for 48 hours
7. **Enable in production** gradually

**Estimated Effort**: 
- Phase 1: 2 days
- Phase 2: 2 days  
- Phase 3: 1 day
- Testing & validation: 1 day
- **Total**: 6 days (1 sprint)

---

## Appendix: File Modification Summary

| File | Issues Fixed | Change Type |
|------|-------------|-------------|
| `tests/conftest.py` | #1 | Logic (log message) |
| `tests/integration/test_agent_execution.py` | #11 | Logic (status wording) |
| `src/config.py` | #2 | Add utility function |
| `src/routers/agent_runs.py` | #3, #4, #5, #12 | Logic + Schema |
| `src/schemas/agents.py` | #2, #5, #9, #10 | Schema + Validators |
| `src/services/orchestrator.py` | #2, #6, #7, #8, #9 | Logic (timing, metrics) |
| `src/health/components.py` | #11 | Logic (status values) |
| `db/postgres_control/tables.py` | #4 | Migration (add column) |

**Total Files Modified**: 8  
**Lines Changed**: ~200 (estimated)  
**New Tests**: 12 unit tests + 1 integration test suite
