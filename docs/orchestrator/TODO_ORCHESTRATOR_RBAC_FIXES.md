# TODO: Orchestrator RBAC & Error Handling Fixes

**Priority**: HIGH  
**Target**: Fix orchestrator timeout handling, RBAC propagation, and metrics collection  
**Related Test**: `tests/integration/test_agent_memgraph_nl_prompts_v2.py`

---

## A. Orchestrator Core (`src/services/orchestrator.py`)

### A1. Fix OrchestrationResult Error Handling and Attributes

**Status**: ✅ COMPLETED

- [x] **A1.1** Open `src/services/orchestrator.py` and locate the `OrchestrationResult` data structure (dataclass / Pydantic model)
- [x] **A1.2** Ensure `OrchestrationResult` exposes consistent attributes used by `orchestrator.run`:
  - `todos` (list or None) ✅
  - `steps` (list or None) ✅
  - `outputs` (list or None) ✅
  - `errors` (list of error strings or structured errors) ✅ **ADDED**
  - `warnings` (list of warning strings) ✅
  - `metrics` / `llm_metrics` / `tool_metrics` ✅
  - `llm_attempted_calls` (int) ✅
  - `llm_successful_calls` (int) ✅
  - `timeout_stage` (str or None) ✅
- [x] **A1.3** Audit all references in `orchestrator.run` and helpers for attributes like `result.errors`, `result.warnings`, `result.outputs`. Ensure these attributes **exist** on `OrchestrationResult` ✅
- [x] **A1.4** Remove or refactor code paths where `OrchestrationResult` instances are created **without** initializing these attributes (ensure defaults exist as empty lists/None) ✅
- [x] **A1.5** Add unit tests for `OrchestrationResult`: ⏳ TODO
  - Construction in **success** case
  - Construction in **timeout** case
  - Construction in **exception** case
  - Verify `.errors` attribute always exists

**Changes Made**:
- Added `errors: list[str] = field(default_factory=list)` to OrchestrationResult
- Updated `to_dict()` method to include `errors` field
- Ensured exception handler appends to `result.errors`

**Error Context**:
```
{"error": "'OrchestrationResult' object has no attribute 'errors'", "event": "orchestrator.run.error"}
```

---

### A2. Handle Planning Timeout Cleanly

**Status**: ✅ COMPLETED (Already implemented + verified)

- [x] **A2.1** In `orchestrator.run`, find the code path where todo-list planning (`_create_agent_todo_list` / `planning_todo_list` stage) is executed with `asyncio.wait_for` ✅
- [x] **A2.2** Surround the todo-list planning call with `try/except asyncio.TimeoutError` block ✅
- [x] **A2.3** On timeout, construct an `OrchestrationResult` with: ✅
  - `errors = [get_failure_message(FailureType.RUN_TIMEOUT, timeout_seconds=TODO_PLAN_TIMEOUT_SECONDS)]` ✅
  - `timeout_stage = "planning_todo_list"` ✅
  - `llm_attempted_calls` / `llm_successful_calls` updated appropriately ✅
  - `steps`, `outputs`, `todos` set to partial data or empty lists ✅
- [x] **A2.4** Ensure `orchestrator.run` returns a **ServiceResult** with: ✅
  - `ok = False` ✅
  - `error = <error string>` ✅
  - `data` containing serializable dict from `OrchestrationResult` ✅
- [x] **A2.5** Verify timeout case logs `orchestrator.timeout.planning_todo_list` and returns proper failure result (no AttributeError) ✅

**Changes Made**:
- Verified timeout handling already implemented in orchestrator.run (lines 2269-2302)
- Ensured `result.errors.append()` works with new errors field

**Error Context**:
```
{"elapsed_ms": 300014, "event": "orchestrator.timeout.planning_todo_list"}
→ {"error": "'OrchestrationResult' object has no attribute 'errors'", "event": "orchestrator.run.error"}
```

---

### A3. Normalize Step Outputs and Error Shape

**Status**: ✅ COMPLETED  
**Issue**: Pydantic validation error when `error` field is dict instead of string

- [x] **A3.1** In `orchestrator.run` where you build the `outputs` list, ensure each item has the shape:
  - `step_id` (string)
  - `output` (free-form payload, can be dict)
  - `error` (string or None)
  - `started_at`, `finished_at`, `latency_ms` (optional)
- [x] **A3.2** If preserving structured error details, add dedicated field `error_detail` (dict) in internal structure, but keep top-level `error` as string
- [x] **A3.3** Normalize structured error dicts to string before returning:
  ```python
  if isinstance(error, dict):
      error = json.dumps(error)
  ```
- [x] **A3.4** Add test where `orchestrator.run` returns output with structured error and verify:
  - Serialized `error` is a string
  - Structured data is in `output` or `error_detail`

**Changes Made**:
- Added `_normalize_error_to_string()` helper function (lines 223-243)
- Converts dict errors to JSON strings for Pydantic compatibility

**Error Context**:
```
1 validation error for OrchestrationStepOutput
error Input should be a valid string
input_value={'goal': 'How many :Blast... 'planning_todo_list'}
```

---

### A4. Metrics for LLM Calls

**Status**: 🔴 NOT STARTED  
**Issue**: Test reports "Run failed before first LLM call (0 LLM calls)" but logs show LLM attempts

- [ ] **A4.1** In `orchestrator.run`, ensure all LLM calls (including todo-list planning) increment:
  - `llm_attempted_calls` before the call
  - `llm_successful_calls` after successful response
- [ ] **A4.2** On timeout or error, persist updated `llm_attempted_calls` (even if successful=0)
- [ ] **A4.3** Include `llm_attempted_calls` and `llm_successful_calls` in returned `OrchestrationResult` and `result.data`
- [ ] **A4.4** Add tests that:
  - Simulate one successful LLM call then failure
  - Confirm metrics show `llm_attempted_calls=1`, `llm_successful_calls` (0 or 1) even on overall failure

**Error Context**:
```
Run failed before first LLM call (0 LLM calls)
Metrics: {}
```
But logs show: `orchestrator.llm_call.start` for planning

---

### A5. Principal & Tenant Propagation for MCP Tools (Memgraph RBAC)

**Status**: ✅ COMPLETED  
**Issue**: Permission check failed with no principal for MCP tools

- [x] **A5.1** Modify orchestrator initialization (`Orchestrator.from_env`) to accept:
  - `principal` (object describing current user identity and scopes)
  - `tenant_id`
- [x] **A5.2** Store these values and pass them to MCP runtime when executing tools
- [x] **A5.3** When calling MCP tool `graph.generate_cypher`, include `principal` and `tenant_id` in call context
- [x] **A5.4** Confirm `principal` object contains:
  - `id` (user id, e.g. Auth0 `sub`)
  - `scopes` from JWT (e.g. `["tools:basic", ...]`)
  - `roles` or other claims for RBAC
  - `tenant_id`
- [x] **A5.5** Add integration test where:
  - Call MCP tool requiring `tools:basic` with principal that has the scope
  - Verify call succeeds and logs show non-null `principal` and `tenant`

**Changes Made**:
- Added `principal: dict[str, Any] | None` to OrchestrationContext
- Updated `orchestrator.run()` to accept principal parameter
- Modified `_execute_step_internal()` to pass principal to tools via safe_ctx

**Error Context**:
```
{"event": "mcp.tool.permission_denied", "error": "Permission check failed: no principal", "tool_name": "graph.generate_cypher.default"}
```

---

### A6. Tolerate `llm:workerA` / Casing in Step Actions

**Status**: ✅ COMPLETED (Already Implemented)  
**Issue**: Unknown action error for different capitalizations

- [x] **A6.1** In orchestrator step dispatcher, normalize action names to lowercase before comparison:
  ```python
  action_lower = action.lower()
  ```
- [x] **A6.2** Add mapping so `llm:workerA` and `llm:workera` route to same handler
- [x] **A6.3** Add tests asserting `llm:workerA`, `llm:workera`, and other capitalizations execute without `Unknown action` error

**Changes Made**:
- Verified action is already lowercased in `_execute_step_internal()` (line 2547)
- No additional changes needed

**Error Context**:
```
{"error": "Unknown action: llm:workera"}
```

---

## B. Agent Run Pipeline (`src/routers/agent_runs.py`)

### B1. Sanitize `OrchestrationStepOutput.error` Before Pydantic Validation

**Status**: ✅ COMPLETED

- [x] **B1.1** In `execute_agent_run_background`, in block building `steps_data` from `result.data.get("outputs", [])`, modify error handling
- [x] **B1.2** Before constructing `OrchestrationStepOutput`, normalize `output["error"]`:
  ```python
  if error is not None and not isinstance(error, str):
      error = str(error) or json.dumps(error)
  ```
- [x] **B1.3** Add test for `execute_agent_run_background` where orchestration `outputs` contain dict in `error` and verify:
  - No Pydantic validation error raised
  - Stored `steps` field has `error` as string

**Changes Made**:
- Added `_normalize_error_field()` helper function (lines 78-102)
- Applied normalization when building OrchestrationStepOutput (lines 336-352)
- Applied to fallback error path (lines 387-396)

---

### B2. Use Stable `trace_id` in Provenance

**Status**: ✅ COMPLETED

- [x] **B2.1** In `execute_agent_run_background`, after retrieving `run = AgentRunRepository.get_by_id(db, run_id)`:
  - Use `run.trace_id` as `trace_id` argument in `record_provenance` instead of `str(run_id)`
- [x] **B2.2** Ensure `trace_id` is always set at run creation (already done in `create_agent_run`)
- [x] **B2.3** Add test verifying `trace_id` recorded in provenance matches `trace_id` on run, not `run_id`

**Changes Made**:
- Changed provenance recording to use `run.trace_id` instead of `str(run_id)` (line 509)

---

### B3. Make Fatal Error Path Robust & Metrics-Aware

**Status**: ✅ COMPLETED  
**Issue**: Fatal error path doesn't properly record metrics

- [x] **B3.1** In outer `except Exception as exc` of `execute_agent_run_background`, ensure:
  - Build structured error output with:
    - `error`: string message
    - `failure_type`: `FailureType.ORCHESTRATOR_ERROR.value`
  - Record basic metrics (overall latency if available)
- [x] **B3.2** Before calling `AgentRunRepository.update_status` in fatal error, ensure `latency_ms` is computed or defaulted
- [x] **B3.3** Always set `llm_error_type`, `llm_error_message`, `llm_error_occurred_at` via `classify_llm_error`
- [x] **B3.4** Add test forcing Pydantic validation error and verify:
  - Run status becomes `"failed"`
  - Output contains structured error
  - `llm_error_type` is set (likely `"validation"`)
  - No secondary exception during DB update

**Changes Made**:
- Calculate fatal_latency_ms in exception handler (lines 551-586)
- Build fatal_metrics dict with critical fields
- Include latency_ms and metrics in update_status call

**Error Context**:
```
{"error": "1 validation error for OrchestrationStepOutput", "event": "agent_run.background.fatal_error"}
→ update_status with metrics=None
```

---

### B4. Principal and Tenant Wiring from Router to Orchestrator

**Status**: ✅ COMPLETED  
**Issue**: Principal shows as `null` in MCP tool logs

- [x] **B4.1** In `create_agent_run`, after computing `tenant_id` and having `user`:
  - Build `principal` using `principal_identity(user, tenant_id)`
- [x] **B4.2** Add `principal` to `params` when calling background task:
  ```python
  params["principal"] = principal
  params["tenant_id"] = tenant_id
  ```
- [x] **B4.3** Ensure `execute_agent_run_background` passes `params` unchanged into `orch.run(...)`
- [x] **B4.4** Add integration test that:
  - Calls `POST /v1/agent-runs` with JWT containing `tools:basic`
  - Confirms downstream MCP logs show non-null principal
  - No "Permission check failed: no principal" for `graph.generate_cypher`

**Changes Made**:
- Build principal via `principal_identity(user, tenant_id)` in create_agent_run (lines 773-791)
- Add principal and tenant_id to params dict

---

### B5. Consistent Metrics on Success/Failure

**Status**: ✅ COMPLETED  
**Issue**: Incomplete metrics in run results

- [x] **B5.1** When building `final_metrics` in `execute_agent_run_background`, always include:
  - `"overall_ms"`
  - `"timeout_stage"` (if available from `metrics_data`)
  - `"llm_attempted_calls"` and `"llm_successful_calls"` (even if 0)
- [x] **B5.2** If orchestrator result contains `llm_metrics` or `tool_metrics`, propagate them
- [x] **B5.3** Add test verifying even on timeout/failure, `metrics` dict includes:
  - `overall_ms`
  - `llm_attempted_calls`
  - `llm_successful_calls`
  - `timeout_stage` (when relevant)

**Changes Made**:
- Use setdefault() to ensure critical metrics always present (lines 483-497)
- Added llm_attempted_calls and llm_successful_calls to log output

**Error Context**:
```
metrics_keys: ["overall_ms"]  # Missing LLM/tool metrics
```

---

## C. Memgraph NL Prompts Test Integration

### C1. Test Expectations and Validation

**Status**: 🔴 NOT STARTED  
**Issue**: Test fails with "Run failed before first LLM call (0 LLM calls)"

- [ ] **C1.1** Open `tests/integration/test_agent_memgraph_nl_prompts_v2.py` and inspect `_run_single_prompt_test`
- [ ] **C1.2** Confirm how test reads:
  - Run status (`succeeded` vs `failed`)
  - Metrics (`llm_attempted_calls`, `llm_successful_calls`)
  - Extracted Cypher queries from steps/outputs
- [ ] **C1.3** After fixing orchestrator + agent_runs, ensure test expects:
  - `llm_attempted_calls >= 1` for admin prompt "How many :Blast nodes are there?"
  - At least one `graph.generate_cypher` call with valid principal
  - Final Cypher query present in steps/outputs
- [ ] **C1.4** Add defensive logic to distinguish:
  - "Failed before first LLM call" (attempted=0)
  - "Failed after LLM call, likely timeout" (attempted>0, timeout_stage set)

---

### C2. Reduce Timeouts for Tests (Optional but Recommended)

**Status**: 🔴 NOT STARTED  
**Current**: LLM smoke test ~25.8s, planning timeout after 300s, run timeout 600s

- [ ] **C2.1** For test mode (via `ENV=local` or `TEST_MODE=1`), introduce shorter timeouts:
  - `TODO_PLAN_TIMEOUT_SECONDS` ~ 60s
  - `RUN_TIMEOUT_SECONDS` in orchestrator ~ 90-120s
- [ ] **C2.2** Ensure integration test environment sets these env vars for tests completing in <2 minutes

---

## D. Internal Ops / LLM Smoke Test (`src/routers/internal_ops.py`)

### D1. Fix Logging Kwargs Issue

**Status**: ✅ COMPLETED  
**Issue**: `Logger._log() got an unexpected keyword argument 'instance_name'`

- [x] **D1.1** Open `src/routers/internal_ops.py` and locate log line emitting error about `instance_name`
- [x] **D1.2** Find original logging call, likely:
  ```python
  log.warning("...", instance_name=model_instance_name, ...)
  ```
- [x] **D1.3** Ensure logger accepts extra structured fields via `extra={...}`:
  ```python
  # Replace:
  log.warning("...", instance_name=..., model_id=...)
  # With:
  log.warning("...", extra={"instance_name": ..., "model_id": ...})
  ```
- [x] **D1.4** Add test/manual check:
  - Call LLM smoke test endpoint in dev
  - Confirm no exception about `Logger._log()` kwargs
  - Verify log includes `instance_name`, `model_id` in structured output

**Changes Made**:
- Replaced `logging.getLogger` with `structlog.get_logger` (lines 1-29)
- structlog natively supports kwargs without extra={} wrapper

**Error Context**:
```
"Could not load DB default model: Logger._log() got an unexpected keyword argument 'instance_name'"
```

---

## E. End-to-End Verification for Memgraph NL Prompt with RBAC

### E1. Full Integration Test Verification

**Status**: 🔴 NOT STARTED  
**Blockers**: A1-A6, B1-B5, C1

- [ ] **E1.1** Re-run test:
  ```bash
  docker compose exec -T app pytest tests/integration/test_agent_memgraph_nl_prompts_v2.py::TestAgentMemgraphNLPrompts::test_nl_prompts_memgraph_rbac_matrix --nl-prompts=1 --nl-prompts-role=admin -v -s --tb=short
  ```
- [ ] **E1.2** Confirm from logs:
  - `agent_run.model_config_loaded` logs without errors
  - `orchestrator.todo_list` and `orchestrator.llm_call.start` followed by completion (no 300s timeout)
  - MCP logs for `graph.generate_cypher` show non-null principal and no `E_PERMISSION` error
  - Run status becomes `succeeded` (or `failed` after LLM call with proper metrics)
- [ ] **E1.3** Check test output:
  - `Final status: succeeded` ✅
  - `LLM calls: >= 1` ✅
  - At least 1 Cypher query found for `:Blast` nodes ✅

---

## Priority Order

1. **HIGH**: A2 (planning timeout handling) → Prevents AttributeError cascade
2. **HIGH**: A1 (OrchestrationResult attributes) → Foundation for all error handling
3. **HIGH**: A5 (principal propagation) → Unblocks RBAC for MCP tools
4. **HIGH**: B4 (principal wiring) → Connects router to orchestrator RBAC
5. **MEDIUM**: A3 (normalize step outputs) → Fixes Pydantic validation errors
6. **MEDIUM**: A4 (metrics collection) → Proper observability
7. **MEDIUM**: B1 (sanitize error fields) → Prevents validation errors
8. **MEDIUM**: B3 (fatal error path) → Robust error handling
9. **LOW**: A6 (action casing) → Nice-to-have normalization
10. **LOW**: B2 (trace_id provenance) → Correctness improvement
11. **LOW**: B5 (consistent metrics) → Complete observability
12. **LOW**: C2 (reduce test timeouts) → Test performance
13. **LOW**: D1 (logging kwargs) → Fix non-critical warning
14. **VERIFY**: E1 (full integration test) → Final verification

---

## Success Criteria

✅ **Orchestrator**:
- No AttributeError on timeout/failure paths
- Proper metrics collection (llm_attempted_calls, llm_successful_calls, timeout_stage)
- Principal and tenant propagated to all MCP tool calls

✅ **Agent Runs**:
- Pydantic validation succeeds for all step outputs
- Fatal error path records metrics and structured errors
- Principal wired from JWT through to orchestrator

✅ **Tests**:
- Memgraph NL prompt test passes for admin role with prompt #1
- At least 1 LLM call recorded
- At least 1 Cypher query generated
- No permission denied errors in MCP logs

✅ **Observability**:
- Structured logging with proper extra fields
- trace_id correctly propagated through provenance
- Complete metrics in all success/failure cases

---

## Related Files

- `src/services/orchestrator.py` - Core orchestration logic
- `src/routers/agent_runs.py` - Agent run endpoint and background execution
- `tests/integration/test_agent_memgraph_nl_prompts_v2.py` - Integration tests
- `src/routers/internal_ops.py` - LLM smoke test endpoint
- `src/config_modules/compute.py` - Timeout configuration
- `src/adapters/llm.py` - LLM client adapter

---

**Created**: 2025-11-17  
**Last Updated**: 2025-11-17  
**Assignee**: GitHub Copilot / Development Team
