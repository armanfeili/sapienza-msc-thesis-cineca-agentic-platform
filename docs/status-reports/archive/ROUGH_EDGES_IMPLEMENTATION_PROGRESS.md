# Production Rough Edges - Implementation Progress

**Session Status**: 7 of 12 issues complete (58%)  
**Date**: November 10, 2025  
**Total Tests Created**: 49 tests, all passing ✅

## Phase 1: Critical Fixes (COMPLETE ✅)

### Issue #5: Output Type Drift
**Status**: ✅ COMPLETE  
**Tests**: 7/7 passing

**Problem**: `output` field flipping between empty string `""` and `None`, causing type inconsistency in telemetry.

**Solution**:
- Changed initialization from `output_text: str = ""` to `output_text: str | None = None`
- Removed `str` from output type union: `dict | list | None`
- Added `@field_validator` to convert empty strings to `None` before type validation
- Added `@model_validator` to log warnings when status=succeeded but output=None

**Files Modified**:
- `src/schemas/agents.py` (lines 335-352)
- `src/routers/agent_runs.py` (line 216)

**Test File**: `tests/test_output_type_consistency.py`

---

### Issue #3: Trace ID Stability
**Status**: ✅ COMPLETE  
**Tests**: 6/6 passing

**Problem**: `trace_id` flipping between provenance event ID and HTTP request ID across requests.

**Solution**:
- Generate stable UUID once at run creation: `stable_trace_id = str(uuid.uuid4())`
- Pass to `AgentRunRepository.create(..., trace_id=stable_trace_id)`
- Added separate `request_id` field to RunResponse schema for HTTP correlation
- Removed trace_id from `update_status` parameters (preserves stability)
- Use `run.trace_id` from database in provenance recording

**Files Modified**:
- `src/schemas/agents.py` (added request_id field, updated descriptions)
- `src/routers/agent_runs.py` (lines 191-201, 401, 424, 426)

**Test File**: `tests/test_trace_id_stability.py`

---

### Issue #12: Create Response Race Condition
**Status**: ✅ COMPLETE  
**Tests**: 7/7 passing

**Problem**: POST response serialized before output committed to database, causing stale reads.

**Solution**:
- Added `db.expire_all()` to clear SQLAlchemy L1 cache after commit
- Enhanced `db.refresh(run)` to force fresh read from database
- Added validation check: warn if status=succeeded but output is None/empty
- Use `run.output` from database object (not in-memory `output_text` variable)

**Files Modified**:
- `src/routers/agent_runs.py` (lines 408-421)

**Test File**: `tests/test_create_response_consistency.py`

---

## Phase 2: Medium Priority (4/5 complete)

### Issue #2: Model Name Format Inconsistency
**Status**: ✅ COMPLETE  
**Tests**: 8/8 passing

**Problem**: Model names appearing as both "phi3-mini" (kebab) and "phi3:mini" (colon) in telemetry.

**Solution**:
- Added `@field_validator` for `model` field in RunResponse
- Normalizes Ollama model names (phi3, llama3, mistral, etc.) to colon format
- Converts "phi3-mini" → "phi3:mini", "llama3-8b" → "llama3:8b"
- Preserves OpenAI model names (gpt-4) unchanged
- Idempotent: "phi3:mini" stays "phi3:mini"

**Files Modified**:
- `src/schemas/agents.py` (lines 306-336, normalize_model_name validator)

**Test File**: `tests/test_model_name_normalization.py`

---

### Issue #6: Step Timing Incomplete/Inconsistent
**Status**: ✅ COMPLETE  
**Tests**: 8/8 passing

**Problem**: Step latency_ms incomplete - some steps missing timing data despite having timestamps.

**Solution**:
- Added `@model_validator` to both `OrchestrationStepInput` and `OrchestrationStepOutput`
- Calculates `latency_ms` from `started_at` and `finished_at` if missing
- Logs warning if stored latency inconsistent with calculated value (>10ms tolerance)
- Ensures all steps with timestamps have latency populated

**Files Modified**:
- `src/schemas/agents.py` (lines 150-176 for StepInput, 196-222 for StepOutput)

**Test File**: `tests/test_step_timing_consistency.py`

---

### Issue #4: Event ID Disappears After Creation
**Status**: ✅ COMPLETE  
**Tests**: 6/6 passing

**Problem**: `event_id` present in POST response but missing in subsequent GET requests.

**Solution**:
- Added `event_id` parameter to `AgentRunRepository.update_status()` method
- Moved `record_provenance()` call BEFORE `update_status()` to capture event_id
- Pass `ev.event_id` to `update_status(..., event_id=ev.event_id)`
- Persist event_id to database: `run.event_id = event_id`
- Remove manual assignment in response (comes from database via model_validate)

**Files Modified**:
- `db/postgres_control/repositories/agents.py` (lines 619, 663-664)
- `src/routers/agent_runs.py` (lines 394-407, 442)

**Test File**: `tests/test_event_id_persistence.py`

---

### Issue #7: Rollup Metrics Stay Null
**Status**: ✅ COMPLETE  
**Tests**: 7/7 passing

**Problem**: `total_llm_calls`, `tool_calls`, `tool_errors` fields in response are null despite having detailed metrics.

**Solution**:
- Enhanced `extract_rollup_metrics` validator in RunResponse
- If rollup fields null, calculate from `metrics.llm` and `metrics.tools` lists
- `total_llm_calls = len(metrics.llm)` if not explicitly set
- `tool_calls = len(metrics.tools)` if not explicitly set
- `tool_errors = count(tool for tool in tools if not tool.success)` if not set
- Preserves explicitly set values (backwards compatible)

**Files Modified**:
- `src/schemas/agents.py` (lines 357-384, enhanced calculate logic)

**Test File**: `tests/test_rollup_metrics_calculation.py`

---

### Issue #8: TODOs Marked Completed Without Evidence
**Status**: 🔄 IN PROGRESS  
**Tests**: Not yet created

**Problem**: TODOs show `completed_at` timestamp but lack completion evidence/validation.

**Next Steps**:
1. Add validator to TodoItem schema
2. Ensure `completed_at` only set when TODO actually completed
3. Add validation: if completed_at present, validate completion evidence
4. Create unit tests

---

## Phase 3: Polish Issues (Not Started)

### Remaining Issues:
- **Issue #1**: Token counts intermittently null
- **Issue #11**: Agent run status stays "running" indefinitely
- **Issue #9**: Tenant ID sometimes missing in telemetry
- **Issue #10**: Provider field sometimes null

---

## Test Coverage Summary

| Issue | Priority | Tests | Status |
|-------|----------|-------|--------|
| #5 Output type drift | Critical | 7/7 ✅ | Complete |
| #3 Trace ID stability | Critical | 6/6 ✅ | Complete |
| #12 Race condition | Critical | 7/7 ✅ | Complete |
| #2 Model names | Medium | 8/8 ✅ | Complete |
| #6 Step timing | Medium | 8/8 ✅ | Complete |
| #4 Event ID | Medium | 6/6 ✅ | Complete |
| #7 Rollup metrics | Medium | 7/7 ✅ | Complete |
| #8 TODO validation | Medium | 0 | In Progress |
| #1 Token counts | Polish | 0 | Not Started |
| #11 Stuck status | Polish | 0 | Not Started |
| #9 Tenant ID | Polish | 0 | Not Started |
| #10 Provider field | Polish | 0 | Not Started |

**Total Tests**: 49 passing, 0 failing

---

## Implementation Quality

### ✅ Production-Ready Standards Met:
- Comprehensive unit tests for each fix
- Pydantic validators for automatic enforcement
- Backwards compatibility maintained
- Structured logging for debugging
- Database consistency (cache management, refresh)
- Type safety (no `Any` types, strict unions)
- Documentation (docstrings, comments)

### 🔧 Technical Approach:
- **Schema Validators**: Pydantic `@field_validator` and `@model_validator`
- **Database Safety**: SQLAlchemy `expire_all()` + `refresh()`
- **Separation of Concerns**: `trace_id` (stable) vs `request_id` (per-request)
- **Defensive Programming**: Validate consistency, log warnings
- **Idempotency**: Normalization functions are idempotent

---

## Key Architectural Decisions

1. **Output Type Safety**: Removed `str` from union, enforce `dict | list | None` only
2. **Trace ID Design**: Separate `trace_id` (stable provenance) from `request_id` (HTTP)
3. **Event ID Persistence**: Store in database, not just response transient field
4. **Rollup Metrics**: Calculate from detailed lists when explicit values missing
5. **Cache Management**: Explicit `expire_all()` prevents stale reads

---

## Next Session Priorities

1. ✅ **Complete Issue #8**: TODO completion validation
2. **Phase 3 Polish**: Issues #1, #11, #9, #10
3. **Integration Testing**: Test fixes in production-like environment
4. **Performance Validation**: Ensure validators don't impact latency
5. **Documentation**: Update API docs with new fields

---

## Files Modified Summary

### Core Schemas:
- `src/schemas/agents.py` (multiple validators added)

### API Routers:
- `src/routers/agent_runs.py` (race condition fix, trace_id stability)

### Database Repositories:
- `db/postgres_control/repositories/agents.py` (event_id persistence)

### Test Files Created (7 files, 49 tests):
- `tests/test_output_type_consistency.py`
- `tests/test_trace_id_stability.py`
- `tests/test_create_response_consistency.py`
- `tests/test_model_name_normalization.py`
- `tests/test_step_timing_consistency.py`
- `tests/test_event_id_persistence.py`
- `tests/test_rollup_metrics_calculation.py`
