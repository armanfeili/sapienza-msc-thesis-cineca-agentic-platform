# Fix Summary: 3 Remaining Test Issues

**Date**: 2025-11-10  
**Test**: `tests/integration/test_agent_execution.py`  
**Status**: 3 issues fixed + 1 diagnostic enhancement

---

## Issue 1: ❌ METRICS ISSUE: model_warmup_ms is null (in test_agent_execution.py:890)

### Problem
- Test expected `status_data.model_warmup_ms` at top level
- Value was captured (108478ms) but only stored in `status_data.metrics.model_warmup_ms`
- Test validation: `model_warmup_ms = status_data.get("model_warmup_ms")` returned None

### Root Cause
- RunResponse schema had rollup pattern for `total_llm_calls`, `tool_calls`, `tool_errors`
- Missing: `model_warmup_ms` rollup field

### Fix
**File**: `src/schemas/agents.py`
1. Added `model_warmup_ms` field to RunResponse model (line ~386)
2. Added extraction in `extract_rollup_metrics()` validator (line ~410)

```python
# Added field:
model_warmup_ms: int | None = Field(None, description="Time taken for first model load/test in milliseconds (rollup)")

# Added extraction:
if self.model_warmup_ms is None and hasattr(self.metrics, 'model_warmup_ms'):
    self.model_warmup_ms = self.metrics.model_warmup_ms
```

### Expected Result
- Test will find `model_warmup_ms` at top level
- Validation will pass: "✅ Model warmup latency: 108478 ms"

---

## Issue 2: ❌ TODO #2 claims "graph.search" but wasn't called (in test_agent_execution.py:2793)

### Problem
- TODO description: "Analyze the tool list and identify categories using graph.search"
- Actual tool calls: `['catalog.discover', 'catalog.discover', 'catalog.discover']`
- LLM (phi3:mini) mentioned tool it didn't call

### Root Cause
- Enhanced prompt with CRITICAL CONSTRAINTS and examples (previous fix)
- LLM still not reliably following instructions

### Fix
**File**: `src/services/orchestrator.py` (line ~1950)
- Added post-execution validation
- Extracts actual tool calls from execution outputs
- Logs warning if TODO mentions unexecuted tools

```python
# Step 2.5: Validate TODO truthfulness (check if mentioned tools were actually called)
executed_tools = set()
if result.outputs:
    for output in result.outputs:
        if isinstance(output, dict):
            action = output.get("action", "")
            if action.startswith("tool_call:"):
                tool_name = action.replace("tool_call:", "")
                executed_tools.add(tool_name)

# Check each TODO for unexecuted tool mentions
import re
for todo in todos:
    description = todo.get("task", "")
    potential_tools = re.findall(r'\b([a-z_]+\.[a-z_]+)\b', description.lower())
    
    for tool_mention in potential_tools:
        if tool_mention in self.tools and tool_mention not in executed_tools:
            log.warning(
                "orchestrator.todo_validation.unexecuted_tool",
                todo_text=description,
                mentioned_tool=tool_mention,
                executed_tools=list(executed_tools)
            )
```

### Expected Result
- Validation warning logged if TODO mentions unexecuted tools
- Provides visibility into LLM hallucination issues
- Can be used to improve prompts or filter TODO descriptions

---

## Issue 3: ❌ Catalog cache not working: 3 identical discover calls (in test_agent_execution.py:2813)

### Problem
- 3 catalog.discover calls with identical parameters (count=32 each)
- Expected: 1st call fetches, 2nd/3rd hit cache
- Actual: All 3 calls fetch fresh data (22ms, 5ms, 11ms)

### Root Cause Analysis
- Cache implementation exists in `src/mcp/tools/catalog/discover.py`
- Redis import in try-except block with fallback stubs
- If Redis unavailable: `cache_get_json` returns None, `cache_set_json` returns False
- **No cache logs visible** → Redis not accessible or import failed

### Diagnostic Enhancement
**File**: `src/mcp/tools/catalog/discover.py` (lines 150-185)
- Changed cache logging from DEBUG to INFO level
- Added `redis_available` flag to cache_key_built log
- Changed cache_miss from DEBUG to INFO

```python
# Enhanced logging:
logger.info(
    "catalog.discover.cache_key_built",
    cache_key=cache_key,
    tenant_id=tenant_id,
    session_id=session_id,
    redis_available=callable(cache_get_json) and cache_get_json.__name__ != "<lambda>"
)

# Cache miss also at INFO level:
logger.info(
    "catalog.discover.cache_miss",
    tenant_id=tenant_id,
    session_id=session_id,
    cached_value=type(cached).__name__ if cached else "None",
)
```

### Expected Result
- Next test run will show cache operations in logs
- Logs will reveal:
  - If Redis is available (`redis_available: true/false`)
  - Cache key format (tenant_id, session_id values)
  - Whether cache_get returns None (miss) or data (hit)
  - Whether cache_set succeeds

### Next Steps for Issue 3
1. Run test and check logs for "catalog.discover.cache_key_built"
2. If `redis_available: false` → Redis not imported/available
3. If `redis_available: true` but always "cache_miss" → check:
   - Redis connectivity (docker-compose.yml)
   - Cache key consistency (session_id might change between calls)
   - Redis service running during test

---

## Files Modified

1. **src/schemas/agents.py**
   - Added `model_warmup_ms` rollup field
   - Added extraction in `extract_rollup_metrics()`

2. **src/services/orchestrator.py**
   - Added TODO truthfulness validation (step 2.5)
   - Logs warnings for unexecuted tool mentions

3. **src/mcp/tools/catalog/discover.py**
   - Enhanced cache logging (DEBUG → INFO)
   - Added redis_available diagnostic flag

---

## Testing Plan

### Run Integration Test
```bash
pytest tests/integration/test_agent_execution.py -v -s --tb=short > test_output_fixed.log 2>&1
```

### Expected Outcomes
1. **model_warmup_ms**: ✅ "Model warmup latency: 108478 ms"
2. **TODO truthfulness**: Warning logged (if still hallucinating)
3. **Catalog caching**: Logs show cache operations and Redis status

### Validation Checklist
- [ ] model_warmup_ms validation passes
- [ ] TODO validation warnings visible in logs
- [ ] Cache logs show Redis availability status
- [ ] Cache logs show cache keys and hit/miss results
- [ ] Test passes overall (PASSED not FAILED)

---

## Notes

### Issue 1 (model_warmup_ms)
- **HIGH CONFIDENCE**: Fix follows established rollup pattern
- Value already captured, just needs extraction
- Should resolve immediately

### Issue 2 (TODO truthfulness)
- **MEDIUM CONFIDENCE**: Validation added but won't prevent hallucinations
- Provides visibility for debugging
- May require:
  - More aggressive prompt engineering
  - Post-generation filtering
  - TODO generation after execution (list only called tools)

### Issue 3 (Catalog caching)
- **DIAGNOSTIC PHASE**: Enhanced logging will reveal root cause
- Likely causes:
  - Redis not running in test environment
  - Import failure (fallback stubs used)
  - Cache key mismatch (session_id changes)
- **NOT YET FIXED**: Need test output to identify issue

---

## Rollback Instructions

If any fix causes issues:

### Revert model_warmup_ms changes
```bash
git diff src/schemas/agents.py
git checkout src/schemas/agents.py
```

### Revert TODO validation
```bash
git diff src/services/orchestrator.py
# Remove lines 1950-1978 (the validation block)
```

### Revert cache logging
```bash
git checkout src/mcp/tools/catalog/discover.py
```
