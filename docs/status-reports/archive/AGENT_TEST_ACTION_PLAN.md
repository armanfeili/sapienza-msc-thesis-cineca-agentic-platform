# 🎯 Agent Execution Test - Quick Action Plan

**Status**: ✅ Test passes but needs hardening  
**Priority**: Critical for production readiness  
**ETA**: 2-3 days

---

## 📋 Summary

Your test discovered **all the right issues**! Here's what we need to fix:

### 🔴 Critical Issues (Fix Now)

1. **Multiple catalog.discover calls** - Should cache and reuse (1 real, others from cache)
2. **`request_id` lost** - null in final status but present at creation
3. **Null timing fields** - Reused steps have `null` instead of `0`
4. **Null metrics** - `todo_creation_ms`/`todo_execution_ms` are `null`
5. **Duplicate warmup** - `model_warmup_ms` in both root and metrics
6. **No hard budget** - Latency check is soft, should fail if exceeded

### 🟡 Important (Next Sprint)

7. Tool contract validation (required tools + descriptions)
8. Structured output enforcement (no prose)
9. Traceability (trace_id + event_id validation)
10. Count parity (tools_count == len(tools))

### 🟢 Security (Separate PR)

11. `graph.secure_query` security validation
12. Provider health expectations

---

## 🛠️ What Needs Changing

### Backend (`src/`)

```python
# 1. Orchestrator: Cache catalog.discover
@lru_cache(maxsize=128)
def get_catalog_for_run(run_id: str) -> dict:
    """Cache catalog per run."""
    return catalog.discover()

# 2. API: Propagate request_id
run_record = AgentRun(
    run_id=run_id,
    request_id=request.headers.get("x-request-id"),  # ← Add this
    ...
)

# 3. Orchestrator: Zero-duration for reused steps
reused_step = {
    "started_at": now,
    "finished_at": now,  # ← Same timestamp
    "latency_ms": 0       # ← Not null
}

# 4. Metrics: Populate or remove
metrics = {
    "todo_creation_ms": measure_todo_creation(),  # ← Actually measure
    "todo_execution_ms": measure_todo_execution(), # ← Or remove entirely
    # ...
}

# 5. Deduplicate warmup
# Keep only in metrics.model_warmup_ms, remove from root
```

### Tests (`tests/integration/test_agent_execution.py`)

```python
# Add hard assertions for all 14 TODOs
# See AGENT_EXECUTION_TEST_IMPROVEMENTS.md for full implementation
```

---

## ✅ Acceptance Criteria

Run this command - all should pass:

```bash
docker compose exec -T app bash -c "pytest tests/integration/test_agent_execution.py -v"
```

Expected output:
```
✅ Only 1 real catalog.discover (others cached)
✅ request_id present in final status
✅ No null timing fields
✅ No null metrics  
✅ model_warmup_ms in one location only
✅ Latency < 120s budget (fails if exceeded)
✅ All required tools present
✅ No prose in outputs
✅ trace_id + event_id validated
✅ tools_count == len(tools) everywhere
```

---

## 📝 Implementation Checklist

### Phase 1: Critical (This Sprint)
- [ ] Implement catalog caching (TODO #1)
- [ ] Propagate request_id (TODO #2)
- [ ] Fix reused step timing (TODO #3)
- [ ] Populate/remove null metrics (TODO #4)
- [ ] Deduplicate warmup metric (TODO #5)
- [ ] Add latency budget assertion (TODO #6)
- [ ] Add metrics roll-up assertion (TODO #12)

### Phase 2: Important (Next Sprint)
- [ ] Tool contract validation (TODO #9)
- [ ] Structured output validation (TODO #10)
- [ ] Traceability validation (TODO #11)
- [ ] Catalog count guardrail (TODO #13)
- [ ] Status parity check (TODO #14)

### Phase 3: Security (Separate PR)
- [ ] Security path tests (TODO #7)
- [ ] Provider health tests (TODO #8)

---

## 🚀 Quick Start

1. **Read the full plan**: `AGENT_EXECUTION_TEST_IMPROVEMENTS.md`
2. **Pick a TODO**: Start with #1 (catalog caching)
3. **Make the change**: Update orchestrator code
4. **Run the test**: Verify it passes
5. **Repeat**: Move to next TODO

---

## 📚 Files to Check

- **Implementation Plan**: `AGENT_EXECUTION_TEST_IMPROVEMENTS.md` (detailed)
- **Test File**: `tests/integration/test_agent_execution.py` (needs updates)
- **Orchestrator**: `src/orchestrator/*.py` (needs fixes)
- **API Router**: `src/routers/agent_runs.py` (needs request_id)
- **Test Output**: `test_full_output.log` (shows current state)

---

## 💡 Key Insights

Your test is **excellent** - it found all the real issues:

1. ✅ **Real LLM execution** - Not mocked
2. ✅ **Real Auth0** - Not bypassed  
3. ✅ **Real database** - Persisted correctly
4. ✅ **Real Redis** - Cache working
5. ✅ **Performance measured** - 1357x speedup!

Now we just need to **harden the assertions** so regressions can't slip through.

---

## 🎉 Bottom Line

**Test Status**: ✅ Passing (but soft)  
**After Fix**: ✅ Passing (and strict)  
**Confidence**: 📈 Production-ready

You already have 95% of what you need - just need to tighten the screws! 🔧

---

**Questions? See the full plan in `AGENT_EXECUTION_TEST_IMPROVEMENTS.md`**
