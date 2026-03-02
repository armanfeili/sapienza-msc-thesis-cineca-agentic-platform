# GitHub Issue Template: Agent Execution Test Hardening

Use this template to create tracking issues for each TODO.

---

## Issue #1: Cache catalog.discover to prevent redundant calls

**Priority**: 🔴 Critical  
**Labels**: `testing`, `performance`, `bug`

### Problem
Currently making 3 catalog.discover calls per run (1 real + 2 reused with null latency). Should cache and reuse from context.

**Current behavior**:
```json
{
  "step_id": "todo-0-discover",
  "latency_ms": 79
},
{
  "step_id": "todo-1-discover-reused",
  "latency_ms": null  // ← Should be 0
}
```

### Acceptance Criteria
- [ ] Only 1 real catalog.discover call per run (latency > 0)
- [ ] Reused calls have `latency_ms: 0` (not null)
- [ ] Test assertion fails if > 1 real call
- [ ] Cache hit flag or metric proves reuse

### Implementation
1. **Backend**: Cache catalog in orchestrator per run_id
2. **Test**: Add assertion counting real vs reused calls

---

## Issue #2: Propagate request_id through execution lifecycle

**Priority**: 🔴 Critical  
**Labels**: `testing`, `tracing`, `bug`

### Problem
`request_id` is present in create response (`x-request-id` header) but null in final status.

**Evidence**:
- Create: `x-request-id: 7c83dc72-cf76-476a-ac68-b537e491781f`
- Final: `"request_id": null`

### Acceptance Criteria
- [ ] Final status has non-null request_id
- [ ] request_id matches x-request-id from creation
- [ ] Test validates propagation

### Files to Change
- `src/routers/agent_runs.py`: Capture request_id from headers
- `src/orchestrator/*.py`: Pass request_id to run record
- `tests/integration/test_agent_execution.py`: Add validation

---

## Issue #3: Fill timing fields for reused steps

**Priority**: 🔴 Critical  
**Labels**: `testing`, `data-quality`, `bug`

### Problem
Reused steps have `null` timing fields instead of zero-duration timestamps.

**Current**:
```json
{
  "started_at": null,
  "finished_at": null,
  "latency_ms": null
}
```

**Expected**:
```json
{
  "started_at": "2025-11-12T16:21:17.719Z",
  "finished_at": "2025-11-12T16:21:17.719Z",
  "latency_ms": 0
}
```

### Acceptance Criteria
- [ ] No timing fields are null for any step
- [ ] Reused steps have started_at == finished_at
- [ ] Reused steps have latency_ms == 0
- [ ] Test validates all steps have valid timing

### Implementation
Update orchestrator when creating reused step records.

---

## Issue #4: Populate or remove null metrics fields

**Priority**: 🔴 Critical  
**Labels**: `testing`, `metrics`, `bug`

### Problem
`todo_creation_ms` and `todo_execution_ms` are always null.

### Options
**A**: Measure and populate these fields  
**B**: Remove them entirely (if unused)

### Acceptance Criteria
- [ ] Both fields are numeric OR omitted (never null)
- [ ] Test validates no null metrics
- [ ] Schema updated accordingly

---

## Issue #5: Deduplicate model_warmup_ms location

**Priority**: 🟡 Important  
**Labels**: `testing`, `refactor`

### Problem
`model_warmup_ms` appears in both root and `metrics` object.

### Decision Needed
Keep in `metrics.model_warmup_ms` OR root level (not both).

### Acceptance Criteria
- [ ] Value exists in exactly one location
- [ ] Test enforces single location
- [ ] Documentation updated

---

## Issue #6: Add hard assertion for LLM latency budget

**Priority**: 🔴 Critical  
**Labels**: `testing`, `performance`

### Problem
Latency check is soft (just prints ✅), doesn't fail when budget exceeded.

### Requirements
- Cold start budget: 120,000ms (2 minutes)
- Warning threshold: 90,000ms (1.5 minutes)
- Warm call budget: 30,000ms (30 seconds)

### Acceptance Criteria
- [ ] Test FAILS when first LLM > 120s
- [ ] Test WARNS when first LLM > 90s
- [ ] Assertion includes helpful error message

---

## Issue #7: Security path smoke tests

**Priority**: 🟢 Security  
**Labels**: `security`, `testing`

### Requirements
Test `graph.secure_query` with:

1. ✅ Benign read → should pass
2. ❌ Write attempt → should block (400/403)
3. ❌ `CALL dbms.stop()` → should block
4. ❌ `DETACH DELETE` → should block
5. 🔐 Role-gated reads → validate permissions
6. 📝 All calls audited → check security.audit

### Acceptance Criteria
- [ ] All negative cases blocked
- [ ] Positive case passes
- [ ] All calls logged in audit
- [ ] Test is in separate file: `test_security_paths.py`

---

## Issue #8: Provider health expectations

**Priority**: 🟡 Important  
**Labels**: `testing`, `health`

### Requirements
- Assert provider list is non-empty
- Each provider lists at least one model
- If env specifies count, validate it

### Acceptance Criteria
- [ ] Test fails on empty provider set
- [ ] Test fails if provider has no models
- [ ] Test adapts to environment config

---

## Issue #9: Tool list contract validation

**Priority**: 🟡 Important  
**Labels**: `testing`, `contract`

### Required Tools
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
```

### Acceptance Criteria
- [ ] All required tools exist
- [ ] Each has non-empty description (>10 chars)
- [ ] Each has correct category
- [ ] Test fails if any missing or invalid

---

## Issue #10: Structured output enforcement

**Priority**: 🟡 Important  
**Labels**: `testing`, `data-quality`

### Requirements
Validate all outputs are pure JSON (no prose).

**Forbidden prose indicators**:
- "i will", "let me", "here is"
- "sure", "certainly", "i can"
- "step 1", "step 2", "first", "then"

### Acceptance Criteria
- [ ] Validator function created
- [ ] Applied to all outputs
- [ ] Test fails on prose detection

---

## Issue #11: Traceability validation

**Priority**: 🟡 Important  
**Labels**: `testing`, `tracing`

### Requirements
- `trace_id` present, non-empty, UUID format
- `event_id` present, non-empty
- `trace_id` stable across requests for same run

### Acceptance Criteria
- [ ] Both fields validated
- [ ] trace_id stability verified
- [ ] Test fails if missing or inconsistent

---

## Issue #12: Metrics roll-up consistency (hard assertion)

**Priority**: 🔴 Critical  
**Labels**: `testing`, `metrics`

### Requirements
Convert soft check to hard assertion:
`overall_ms ≈ (finished_at - started_at)` within ±5%

### Acceptance Criteria
- [ ] Test FAILS when drift > 5%
- [ ] Error message includes expected range
- [ ] Tolerance configurable via env var

---

## Issue #13: Catalog count guardrail

**Priority**: 🟡 Important  
**Labels**: `testing`, `validation`

### Requirements
- Range: 25-60 tools
- Membership: All required tools present

### Acceptance Criteria
- [ ] Range validation
- [ ] Membership validation
- [ ] Test fails if outside range or missing tools

---

## Issue #14: Status summary parity check

**Priority**: 🟡 Important  
**Labels**: `testing`, `data-quality`

### Requirements
Validate `tools_count == len(tools)` everywhere:
- Create output
- Final status output
- Tool discovery output

### Acceptance Criteria
- [ ] Parity checked in all 3 locations
- [ ] Test fails on mismatch
- [ ] Clear error message

---

## Meta Issue: Test Hardening Complete

**Priority**: 🎯 Epic  
**Labels**: `epic`, `testing`

### Checklist
- [ ] All 14 issues resolved
- [ ] Test passes with strict assertions
- [ ] Documentation updated
- [ ] Code review complete
- [ ] Merged to main

---

## How to Use

1. Copy each issue section to GitHub
2. Assign to developer
3. Link issues to this Epic
4. Track progress in project board
5. Celebrate when all ✅!

