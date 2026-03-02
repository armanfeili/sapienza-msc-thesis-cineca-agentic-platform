# Model Test Quality Improvements - Progress Report

**Date**: October 14, 2025  
**Status**: 🚧 In Progress  
**Branch**: `chore/restify-tests-and-docs`

## Summary

Implementing comprehensive improvements to model test endpoint quality based on TODO requirements. Current focus: route conflict resolution and applying improvements to the active endpoint.

## Completed Work

### 1. Created Helper Module (`src/utils/test_helpers.py`) ✅

Implemented comprehensive helper functions for:

#### A) Request Normalization
- `normalize_request_to_messages()`: Converts prompt to OpenAI chat format with system message
- `build_system_message()`: Model-specific system prompts (Qwen, Phi-3 optimizations)
- `get_stop_sequences()`: Smart stop sequences (one-sentence mode, model-specific)

#### B) Response Extraction
- `extract_text_from_response()`: Handles dict/string JSON responses (Mistral fix)
- `normalize_output_text()`: Strips chat tokens (`<|assistant|>`, etc.), collapses whitespace
- `truncate_to_sentence()`: Enforces single-sentence constraint

#### C) Observability
- `hash_prompt()`: SHA256 hash for PII-safe logging
- `estimate_usage()`: Fallback token estimation when provider doesn't return usage

#### D) Performance
- `should_warmup()` / `mark_warmed()`: Warm-up cache (5-minute TTL)

### 2. Updated Request/Response Models ✅

**TestInstanceRequest** (new fields):
- `prompt`: Optional (alternative to messages)
- `messages`: Optional pre-formatted chat messages
- `temperature`: Default 0.0 (deterministic)
- `max_tokens`: Default 32 (reduced from 64)
- `stop`: Optional (smart defaults if None)
- `one_sentence`: Boolean (default True) - enforces single-sentence responses
- `no_system`: Boolean (default False) - skip system message
- `format_hint`: Optional ("poem", "list", etc.)

**TestInstanceResponse** (new fields):
- `provider_base_url`: For debugging
- Updated examples with realistic outputs

### 3. Implemented Improved Endpoint Logic ✅

**In `src/routers/model_instances.py`**:
- Normalize prompt/messages to chat format
- Model-specific system prompts (Qwen anti-followup, Phi-3 poetry-only)
- Smart stop sequences (one-sentence adds `"\n"`)
- Retry logic (1 retry for connection errors)
- Timeout: 20s read, 5s connect
- Usage estimation fallback
- Prompt hashing for PII-safe logs
- Warm-up tracking
- Enhanced error handling (502, 504 with provider context)

## Current Issue: Route Conflict 🔍

### Problem
Two routers define the same endpoint:

1. **`model_management.py`**:
   - No router prefix
   - Mounted at `/models` in admin.py
   - Final path: `/v1/admin/models/instances/{instance_id}/tests`
   - **Currently active** (logs show this is being hit)

2. **`model_instances.py`**:
   - Router prefix: `/models`
   - Mounted at `` (empty) in admin.py
   - Final path: `/v1/admin/models/instances/{instance_id}/tests`
   - **Not active** (shadowed by model_management)

### Evidence
```
app  | {"event": "model.instance.test.lookup", "level": "info", 
       "logger": "src.routers.model_management", ...}
```

Logs clearly show `model_management` is handling the requests.

### Resolution Options

**Option A**: Comment out test endpoint in `model_management.py`
- Pro: Clean separation, model_instances.py is the canonical location
- Con: Need to verify model_management.py endpoint isn't used elsewhere

**Option B**: Apply improvements to `model_management.py` endpoint
- Pro: Minimal disruption, working endpoint stays in same file
- Con: Duplicate logic exists in model_instances.py

**Option C**: Merge both implementations, keep one
- Pro: Best of both worlds
- Con: More complex refactor

**Recommended**: Option B (apply to model_management.py)

## Remaining Tasks

### High Priority
- [ ] **Fix route conflict**: Apply improvements to active endpoint (`model_management.py`)
- [ ] **Test with all 4 models**: Verify one-sentence outputs
- [ ] **Measure latency**: Confirm ≤6s p95 with warm-up

### Medium Priority
- [ ] **Integration tests**: Golden tests for each model (G15-G16)
- [ ] **Documentation**: Update endpoint docs with new parameters (I19-I20)
- [ ] **Instance hygiene**: Remove test duplicates, set descriptions (H17-H18)

### Low Priority  
- [ ] **Warm-up optimization**: Implement actual 1-token warm-up call (E11)
- [ ] **Metrics dashboard**: Visualize latency improvements

## Test Requirements (Acceptance Criteria)

From original TODO:

✅ **Implemented**:
- [x] max_tokens=32 default
- [x] one-sentence system instruction
- [x] stop=["\n"] when one_sentence=true
- [x] Strip special tokens & trailing whitespace
- [x] Qwen: anti-followup system prompt
- [x] Phi-3: poetry-only hint for format_hint="poem"
- [x] Usage estimation fallback
- [x] Prompt hash logging (PII-safe)
- [x] provider_base_url in response
- [x] Retry logic with timeout

⏳ **Pending verification**:
- [ ] All 4 models: exactly one sentence, no trailing newlines
- [ ] Phi-3 haiku: 3 clean lines, no `<|assistant|>`
- [ ] Qwen: no self-questions
- [ ] Mistral: no raw JSON blob
- [ ] Latency ≤6s p95 (warmed)
- [ ] usage.total_tokens always present

## Next Steps

1. **Immediate**: Apply improvements to `model_management.py:instance_test()`
2. **Test**: Run all 4 models with new implementation
3. **Validate**: Check acceptance criteria
4. **Document**: Update OpenAPI examples and docs
5. **PR**: Create comprehensive PR with before/after examples

## Files Modified

- ✅ `src/utils/test_helpers.py` - New helper module
- ✅ `src/routers/model_instances.py` - Updated models & logic (not active)
- ⏳ `src/routers/model_management.py` - Needs updates (active endpoint)
- ⏳ `docs/TEST_ENDPOINT_DOCUMENTATION_UPDATE.md` - Needs refresh

## Timeline

- **Completed**: Helper module, models, endpoint logic (2 hours)
- **Remaining**: Route fix, testing, documentation (1-2 hours)
- **Total**: 3-4 hours for complete implementation

---

**Status**: Helper infrastructure complete, endpoint logic implemented but not active due to route conflict. Next: Apply to active endpoint and test.
