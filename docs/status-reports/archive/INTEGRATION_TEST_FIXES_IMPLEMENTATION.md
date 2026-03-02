# Integration Test Fixes - Implementation Plan

**Date**: November 10, 2025  
**Status**: 🔧 IN PROGRESS

---

## Issues to Fix

Based on the test output, here are the issues that need to be fixed:

### 1. ✅ Provider Enumeration (FIXED)
**Issue**: Provider details only show aggregated counts  
**Status**: ✅ **FIXED** - Individual provider details now included in health response  
**Location**: `src/health/components.py:239-291`  
**Test Output**: 
```
✅ Provider enumeration includes individual provider details:
   Provider 1: ollama-local (ollama)
      Status: healthy, Model: None
```

---

### 2. ❌ Model Warmup Time (TODO)
**Issue**: `model_warmup_ms = null` (not captured)  
**Status**: ❌ **TODO**  
**Location**: `src/services/orchestrator.py` - capture first LLM call latency  
**Implementation**:
```python
# In Orchestrator.run() method, before first LLM call:
if not hasattr(self, '_warmup_captured'):
    warmup_start = time.time()
    # First LLM call happens here (_create_agent_todo_list)
    todos = await self._create_agent_todo_list(goal, ctx, result)
    warmup_ms = int((time.time() - warmup_start) * 1000)
    result.model_warmup_ms = warmup_ms
    self._warmup_captured = True
```

---

### 3. ❌ TODO Truthfulness (TODO)
**Issue**: TODO #3 claims `graph.search` + `user.profile` but no calls recorded  
**Status**: ❌ **TODO**  
**Current Output**:
```
❌ CORRECTNESS ISSUE: TODO claims tools executed but no calls recorded
   Missing: graph.search, user.profile
   TODO: Employ graph.search and user.profile tools together, if necessary...
   Actual calls: ['catalog.discover', 'catalog.discover', 'catalog.discover']
```

**Fix Options**:
- **Option A**: Update planner to only mention tools that will be called
- **Option B**: Ensure agent actually calls all tools mentioned in TODOs
- **Recommended**: Option A (modify LLM prompt to be more conservative)

**Location**: `src/services/orchestrator.py:1202` - `_create_agent_todo_list()`

---

### 4. ❌ Catalog Caching (TODO)
**Issue**: 3 identical `catalog.discover` calls (29ms, 4ms, 4ms) returning count=32  
**Status**: ❌ **TODO**  
**Current Output**:
```
❌ PERFORMANCE ISSUE: All 3 calls returned identical count (32)
→ REQUIRED FIX: Implement Redis caching for catalog.discover
→ Cache key format: 'catalog:{tenant_id}:{session_id}'
→ TTL: 3600s (1 hour)
```

**Implementation**:
```python
# In catalog.discover tool implementation
cache_key = f"catalog:{tenant_id}:{session_id}"
cached = await redis.get(cache_key)
if cached:
    return json.loads(cached)

# Fetch from source
result = await fetch_catalog()

# Cache for 1 hour
await redis.setex(cache_key, 3600, json.dumps(result))
return result
```

---

### 5. ❌ Request ID Preservation (TODO)
**Issue**: `request_id` present in create response headers but `null` in final status  
**Status**: ❌ **TODO**  
**Current Output**:
```
Create Response: x-request-id: ae44675c-ba63-4cdf-a716-bfa9f41101f9
Final Status: "request_id": null
```

**Location**: `src/routers/agent_runs.py` - thread request_id through run record

**Implementation**:
```python
# In create_agent_run endpoint:
request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

# Store in agent_run record
agent_run = {
    "run_id": run_id,
    "request_id": request_id,  # Add this field
    # ... other fields
}
```

---

### 6. ❌ Step Timing Consistency (TODO)
**Issue**: `create-todos` step shows `started_at/finished_at = null` while output has timestamps  
**Status**: ❌ **TODO**  
**Current Output**:
```python
{
  "type": "step",
  "step_id": "create-todos",
  "action": "Create TODO list",
  "started_at": null,  # ← Missing
  "finished_at": null,  # ← Missing
  "latency_ms": null   # ← Missing
}

# But the corresponding output has:
{
  "type": "output",
  "step_id": "create-todos",
  "started_at": "2025-11-10T17:56:59.185919Z",  # ← Present
  "finished_at": "2025-11-10T17:58:18.469293Z",  # ← Present
  "latency_ms": 79283
}
```

**Location**: `src/services/orchestrator.py` - populate timing on step record  
**Implementation**:
```python
# In run() method when creating todo_creation_step:
todo_creation_step = Step(
    id="create-todos",
    action="Create TODO list",
    input={"goal": goal},
    meta={"type": "planning"},
    started_at=todo_creation_start,  # ← Add this
    finished_at=utc_now().isoformat(),  # ← Add this
    latency_ms=int((time.time() - todo_start_time) * 1000)  # ← Add this
)
```

---

### 7. ❌ Provider Model Display (TODO)
**Issue**: Provider shows `Model: None` for `ollama-local`  
**Status**: ❌ **TODO**  
**Current Output**:
```
Provider 1: ollama-local (ollama)
   Status: healthy, Model: None  # ← Should show actual model or "no default model"
```

**Location**: `src/health/components.py:239` - `probe_providers()`  
**Implementation**:
```python
# When building provider_detail:
model_name = provider.get("model")
if not model_name:
    # Try to get from provider configuration or registry
    model_name = "no default model loaded"

provider_detail = {
    "name": provider.get("name", "unknown"),
    "type": ptype,
    "status": "healthy" if provider_healthy else "unhealthy",
    "model": model_name,  # ← Now shows meaningful value
}
```

---

## Implementation Priority

### HIGH (Production Blockers)
1. ✅ **Provider Enumeration** - DONE
2. ❌ **Catalog Caching** - Performance issue, affects scalability
3. ❌ **TODO Truthfulness** - Correctness issue, affects agent reliability

### MEDIUM (Observability)
4. ❌ **Model Warmup Time** - Metrics issue, affects performance analysis
5. ❌ **Request ID Preservation** - Tracing issue, affects debugging
6. ❌ **Step Timing Consistency** - Metrics issue, affects observability

### LOW (Polish)
7. ❌ **Provider Model Display** - UI/UX issue, minor

---

## Test Validation

After each fix, run the integration test to verify:

```bash
docker compose exec -T app bash -c "export AUTH0_ADMIN_TOKEN='...' && \
  export AUTH0_USER_TOKEN='...' && \
  export AUTH0_MACHINE_TOKEN='...' && \
  pytest tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully -v -s --tb=short"
```

### Expected Output Changes

#### After Fix #2 (Model Warmup):
```
✅ model_warmup_ms captured: 79280ms
```

#### After Fix #3 (TODO Truthfulness):
```
✅ 3/3 TODOs completed (100.0%)
✅ All TODOs accurately reflect actual execution
```

#### After Fix #4 (Catalog Caching):
```
✅ catalog.discover caching detected (3 calls → 1 fetch)
```

#### After Fix #5 (Request ID):
```
✅ request_id preserved: ae44675c-ba63-4cdf-a716-bfa9f41101f9
```

#### After Fix #6 (Step Timing):
```
✅ All steps have consistent timing fields
```

#### After Fix #7 (Provider Model):
```
Provider 1: ollama-local (ollama)
   Status: healthy, Model: phi3:mini
```

---

## Files to Modify

1. ✅ `src/health/components.py` - Provider enumeration (DONE)
2. ❌ `src/services/orchestrator.py` - Model warmup, TODO truthfulness, step timing
3. ❌ `src/mcp/tools/catalog.py` - Catalog caching (or wherever catalog.discover is implemented)
4. ❌ `src/routers/agent_runs.py` - Request ID preservation
5. ❌ `db/postgres_control/repositories/provider_repo.py` - Provider model retrieval

---

**Next Actions**:
1. Implement model warmup time capture
2. Fix TODO truthfulness in planner
3. Implement catalog caching
4. Preserve request_id through run lifecycle
5. Fix step timing consistency
6. Polish provider model display
