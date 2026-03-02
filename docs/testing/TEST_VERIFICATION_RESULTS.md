# Test Verification Results - November 18, 2025

## Executive Summary

**Status: ⚠️ PARTIAL SUCCESS - Implementation Complete, Runtime Issues Detected**

- ✅ **Unit Tests:** All 20 tests PASSED (OrchestrationResult)
- ❌ **Integration Test:** FAILED with 500 error after 9+ minutes
- ⚠️ **Simple Mode:** Did NOT activate (should have been < 90s)
- ❌ **RBAC:** Principal missing in MCP runtime
- ❌ **API Response:** Pydantic validation error on output field

---

## Test Execution Results

### ✅ Step 1: Unit Tests (PASSED)

**Command:**
```bash
docker compose exec -T app pytest tests/unit/test_orchestration_result.py -v --tb=short
```

**Result: SUCCESS**
- ✅ 20/20 tests passed in 2.35s
- ✅ All OrchestrationResult fields validated
- ✅ Error normalization working
- ✅ LLM metrics tracking working
- ✅ Timeout stage handling working
- ✅ to_dict() serialization working

**Tests Passed:**
1. test_minimal_construction_with_goal_only
2. test_construction_with_all_fields
3. test_planning_timeout_result
4. test_step_execution_timeout_result
5. test_multiple_errors_accumulation
6. test_fatal_error_result
7. test_llm_error_result
8. test_tool_error_result
9. test_to_dict_minimal
10. test_to_dict_with_outputs
11. test_to_dict_with_errors
12. test_to_dict_with_metrics
13. test_to_dict_with_timeout_stage
14. test_successful_execution_result
15. test_successful_multi_step_result
16. test_errors_field_exists_on_new_instance
17. test_errors_field_accessible_after_timeout
18. test_errors_field_in_to_dict
19. test_errors_and_error_fields_coexist
20. test_errors_field_survives_dataclass_conversion

---

### ❌ Step 2: Integration Test (FAILED)

**Command:**
```bash
docker compose exec \
  -e LLM_MEMGRAPH_NL_TEST_MODE=true \
  -e MEMGRAPH_NL_SIMPLE_MODE=true \
  app bash -c \
  'pytest tests/integration/test_agent_memgraph_nl_prompts_v2.py::TestAgentMemgraphNLPrompts::test_nl_prompts_memgraph_rbac_matrix \
     --nl-prompts=1 --nl-prompts-role=admin -v -s --tb=short 2>&1 \
   | tee tests/integration/output/test_prompt_1.log'
```

**Result: FAILED**
- ❌ Test ran for 9+ minutes (expected < 90s with simple mode)
- ❌ Final status: 500 Internal Server Error
- ❌ Simple mode DID NOT activate (3 TODOs created, not 1)
- ❌ Test timeouts still using 600s (not 90s/180s from test mode)
- ✅ Auth0 tokens validated successfully
- ✅ Services (Redis, Postgres, Memgraph, Ollama) all healthy
- ⚠️ LLM smoke test took 117.8s (very slow, indicating CPU-only inference)

**Execution Timeline:**
- 0:00 - Test started, run_id created
- 0:00-9:00 - Status: running (polling every 30s)
- 9:30 - Test failed with 500 error
- Total: 716.52s (11m 56s)

---

## Root Cause Analysis

### Issue 1: Simple Mode Not Activated ⚠️

**Symptom:**
- Orchestrator created 3 TODOs (not 1 synthetic TODO)
- No "orchestrator.simple_mode.enabled" logs found
- Test took 9+ minutes instead of < 90s

**Log Evidence:**
```json
{"event": "orchestrator.run.complete", "goal": "How many :Blast nodes are there?", "llm_call_count": 2, "outputs": 8, "todos": 3}
```

**Root Cause:**
The `MEMGRAPH_NL_SIMPLE_MODE` environment variable was passed to pytest, but NOT to the FastAPI app container where the orchestrator runs. The test passes env vars to the pytest command, but the actual agent run executes inside the already-running app container which doesn't have this variable.

**Fix Required:**
Add `MEMGRAPH_NL_SIMPLE_MODE=true` to docker-compose.yml or pass it when starting the app container:

```yaml
# docker-compose.yml or docker-compose.override.yml
services:
  app:
    environment:
      - MEMGRAPH_NL_SIMPLE_MODE=true  # Add this
```

Or restart with env var:
```bash
docker compose stop app
docker compose run -d --name app --service-ports \
  -e LLM_MEMGRAPH_NL_TEST_MODE=true \
  -e MEMGRAPH_NL_SIMPLE_MODE=true \
  app
```

---

### Issue 2: RBAC Principal Missing ❌

**Symptom:**
Tools failing with permission errors:
- `data.archive`: "Permission check failed: no principal"
- `graph.search`: "Permission check failed: no principal"

**Log Evidence:**
```json
{"event": "Permission check failed: no principal", "extra": {"action": "default", "principal": null, "required_scope": "tools:write", "resource": "mcp.tools.data.archive", "tenant": null, "tool": "data.archive"}}

{"event": "Permission check failed: no principal", "extra": {"action": "default", "principal": null, "required_scope": "tools:basic", "resource": "mcp.tools.graph.search", "tenant": null, "tool": "graph.search"}}
```

**Root Cause:**
The test creates an agent run via REST API with Auth0 JWT token (admin role), but when the principal dict is constructed in `agent_runs.py`, it's not being properly propagated to the orchestrator's tool context.

**Possible Causes:**
1. Test is not passing `todo_mode` and `category` in request body
2. Orchestrator is not reading params correctly
3. ToolContext construction doesn't include principal from params

**Fix Required:**
Need to verify the test passes the prompt metadata properly. Check `test_agent_memgraph_nl_prompts_v2.py` around line 1100-1200 where it constructs the POST request body.

---

### Issue 3: Test Mode Timeouts Not Applied ❌

**Symptom:**
- Test says "Per-call timeout: 600s | Run timeout: 600s"
- Should be "Per-call timeout: 90s | Run timeout: 180s" with `LLM_MEMGRAPH_NL_TEST_MODE=true`

**Root Cause:**
Same as Issue 1 - environment variable passed to pytest, not to the app container. The compute config is loaded at app startup, so it doesn't see the test mode flag.

**Fix Required:**
Same as Issue 1 - add to docker-compose.yml or restart container with env vars.

---

### Issue 4: Pydantic Validation Error ❌

**Symptom:**
Final 500 error with:
```
ValidationError: 2 validation errors for RunResponse
output.dict[any,any]
  Input should be a valid dictionary [type=dict_type, input_value='After analyzing various ...-induced blast disease.', input_type=str]
output.list[any]
  Input should be a valid list [type=list_type, input_value='After analyzing various ...-induced blast disease.', input_type=str]
```

**Root Cause:**
The `RunResponse.output` field expects `dict | list`, but the orchestrator is returning a string. This is likely because:
1. The orchestration completed successfully (3 TODOs, 8 outputs)
2. The final "output" field is being set to the LLM's text response instead of structured data
3. Error normalization applied to `outputs[]` entries, but not to the top-level `output` field

**Fix Required:**
In `agent_runs.py` around line 550-600 where the final `RunResponse` is constructed, ensure `output` field is properly structured:

```python
# WRONG (current):
output = result.outputs[-1] if result.outputs else None

# RIGHT:
output = result.outputs[-1] if result.outputs else {}
# OR
output = {"text": result.outputs[-1]} if result.outputs else {}
```

---

## Detailed Findings by Verification Step

### Step 3: RBAC Principal Logging (R4) - ❌ FAILED

**Expected:**
```
[principal: OK] principal_sub=auth0|... principal_scopes=['tools:basic'] principal_tenant_id=tenant-123
```

**Actual:**
```
Permission check failed: no principal
```

**Status:** ❌ Principal not propagated to MCP runtime

---

### Step 4: Cypher Extraction (R5) - ⚠️ UNKNOWN

**Expected:**
```
🔍 Extracted Cypher from step[1].output.cypher
📊 Cypher extraction summary:
   - graph.generate_cypher calls: 1
   - Cypher queries extracted: 1
```

**Actual:**
Test failed before Cypher extraction validation could run. Log file shows only polling output, no extraction details.

**Status:** ⚠️ Cannot validate until test completes successfully

---

### Step 5: Simple Mode Activation (R6) - ❌ FAILED

**Expected:**
```
orchestrator.simple_mode.enabled todo_mode=none category=read_only
```

**Actual:**
No simple mode logs found. Orchestrator created 3 TODOs (normal planning mode).

**Status:** ❌ Simple mode NOT activated

---

### Step 6: LLM Metrics (D) - ⚠️ PARTIAL

**Expected:**
```
llm_attempted_calls: 2
llm_successful_calls: 2
```

**Actual:**
From orchestrator logs:
```json
{"event": "orchestrator.run.complete", "llm_call_count": 2, "outputs": 8, "todos": 3}
```

**Status:** ⚠️ Metrics tracked in orchestrator, but response failed before reaching client

---

## Required Fixes

### Priority 1: Environment Variable Propagation (CRITICAL)

**Problem:** Test-specific env vars not reaching the app container

**Solution:**

```bash
# Stop current container
docker compose stop app

# Restart with test environment variables
docker compose up -d --force-recreate app \
  -e LLM_MEMGRAPH_NL_TEST_MODE=true \
  -e MEMGRAPH_NL_SIMPLE_MODE=true
```

Or add to `docker-compose.override.yml`:

```yaml
services:
  app:
    environment:
      - LLM_MEMGRAPH_NL_TEST_MODE=true
      - MEMGRAPH_NL_SIMPLE_MODE=true
```

Then rebuild:
```bash
docker compose up -d --build app
```

---

### Priority 2: Pydantic Validation Fix (CRITICAL)

**File:** `src/routers/agent_runs.py`

**Problem:** `RunResponse.output` expects dict/list, got string

**Solution:**

Find the code around line 500-600 where RunResponse is constructed from OrchestrationResult, and ensure output field is structured:

```python
# Construct final response with proper output type
output_value = {}
if result.outputs:
    last_output = result.outputs[-1]
    if isinstance(last_output, dict):
        output_value = last_output
    elif isinstance(last_output, str):
        output_value = {"text": last_output}
    else:
        output_value = {"data": last_output}

return RunResponse(
    run_id=run_id,
    status=final_status,
    output=output_value,  # Now always dict/list, never string
    ...
)
```

---

### Priority 3: Principal Propagation Fix (HIGH)

**Files:**
- `tests/integration/test_agent_memgraph_nl_prompts_v2.py` (test body construction)
- `src/routers/agent_runs.py` (principal extraction)
- `src/services/orchestrator.py` (context creation)

**Problem:** Principal dict created in agent_runs.py but not reaching MCP runtime

**Investigation Needed:**

1. Check test request body includes prompt metadata:
```python
# In test file ~line 1100-1200
data = {
    "prompt": prompt_entry["text"],
    "params": {
        "category": prompt_entry["category"],  # Must be present
        "todo_mode": prompt_entry["todo_mode"],  # Must be present
        # ... other fields
    }
}
```

2. Check orchestrator.run() receives and uses params:
```python
# In orchestrator.py
async def run(self, goal: str, params: dict = None, ...):
    principal = params.get("principal") if params else None
    tenant_id = params.get("tenant_id") if params else None
    
    ctx = OrchestrationContext(
        principal=principal,  # Must pass through
        tenant=tenant_id,
        ...
    )
```

3. Check ToolContext inherits principal:
```python
# In orchestrator tool execution
tool_ctx = ToolContext(
    principal=ctx.principal,  # From orchestration context
    tenant=ctx.tenant,
    ...
)
```

---

## Next Steps

### Immediate Actions Required:

1. **Fix Environment Variables:**
   ```bash
   # Edit docker-compose.override.yml to add:
   services:
     app:
       environment:
         - LLM_MEMGRAPH_NL_TEST_MODE=true
         - MEMGRAPH_NL_SIMPLE_MODE=true
   
   # Rebuild and restart
   docker compose up -d --build app
   ```

2. **Fix Pydantic Validation:**
   - Edit `src/routers/agent_runs.py`
   - Find RunResponse construction (~line 500-600)
   - Ensure `output` field is always dict/list, never string
   - Apply error normalization to output field

3. **Fix Principal Propagation:**
   - Verify test passes `category` and `todo_mode` in request
   - Add debug logging in orchestrator.run() to print params
   - Verify ToolContext receives principal from context

4. **Rerun Test:**
   ```bash
   docker compose exec \
     app bash -c \
     'pytest tests/integration/test_agent_memgraph_nl_prompts_v2.py::TestAgentMemgraphNLPrompts::test_nl_prompts_memgraph_rbac_matrix \
        --nl-prompts=1 --nl-prompts-role=admin -v -s --tb=short 2>&1 \
      | tee tests/integration/output/test_prompt_1_fixed.log'
   ```

---

## Success Criteria (Updated)

**Must Pass Before Verification Complete:**

- [ ] Simple mode activates (1 TODO created, not 3)
- [ ] Test completes in < 90 seconds (not 9+ minutes)
- [ ] Test mode timeouts applied (90s/180s, not 600s)
- [ ] No "Permission check failed: no principal" errors
- [ ] RBAC logs show `[principal: OK]` with admin scopes
- [ ] No Pydantic validation errors
- [ ] Final status: `succeeded` (not 500 error)
- [ ] At least 1 Cypher query extracted
- [ ] LLM metrics tracked and returned

---

## Summary

**Implementation: ✅ COMPLETE**
- All code changes are in place
- Unit tests validate OrchestrationResult enhancements
- Error normalization, LLM metrics, timeout handling all implemented

**Runtime Configuration: ❌ NEEDS FIXES**
- Environment variables not propagating to app container
- Pydantic schema mismatch in API response
- Principal dict not reaching MCP runtime

**Estimated Time to Fix:** ~30-60 minutes
1. Docker environment: 5 minutes
2. Pydantic validation: 15 minutes
3. Principal debugging: 30 minutes
4. Retest: 2 minutes

**Once fixed, expect:**
- Test runtime: < 90 seconds
- All RBAC checks pass
- Cypher extraction visible
- Simple mode activated
- Clean success response
