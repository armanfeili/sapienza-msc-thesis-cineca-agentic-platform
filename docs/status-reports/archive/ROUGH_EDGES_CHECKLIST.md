# Rough Edges: Validation Checklist

Use this checklist to validate each fix. Check off items as you verify them.

---

## Pre-Implementation

- [ ] Read `ROUGH_EDGES_FIX_PLAN.md` completely
- [ ] Review `ROUGH_EDGES_DIAGRAM.md` for dependencies
- [ ] Create feature flag: `ENABLE_POLISHED_TELEMETRY=false` (default)
- [ ] Set up staging environment with flag enabled
- [ ] Backup production database before any migrations

---

## Issue 1: Misleading Docker Token Log

### Implementation

- [ ] Modified `tests/conftest.py` (lines ~108-116)
- [ ] Added check for `RUNNING_IN_DOCKER` env var
- [ ] Changed message to "Skipping Auth0 token fetch (using Docker env vars)"
- [ ] Kept original warning behavior for non-Docker environments

### Validation

- [ ] Run test in Docker: `docker compose exec app pytest tests/integration/test_agent_execution.py`
- [ ] Verify log shows "⏩ Skipping" message (not "⚠ failed")
- [ ] Run test locally: Should still show warning if script fails
- [ ] No functional changes, only log message

---

## Issue 2: Model Name Format Inconsistency

### Implementation

- [ ] Created `normalize_model_name(name: str) -> str` in `src/config.py`
- [ ] Applied normalization in `src/routers/agent_runs.py` (line ~401)
- [ ] Applied normalization in `src/services/orchestrator.py` (LLM metric creation)
- [ ] Added validator in `RunResponse`: `assert self.model == self.metrics.llm_calls[0].model`

### Validation

- [ ] Create agent run with `phi3-mini-q4`
- [ ] Verify response: `model: "phi3:mini"` (top-level)
- [ ] Verify response: `metrics.llm_calls[0].model: "phi3:mini"`
- [ ] Test all variants: `phi3-mini`, `phi3-mini-instruct`, `phi3:mini` → all normalize to `phi3:mini`
- [ ] Run unit test: `pytest tests/test_model_normalization.py -v`

---

## Issue 3: Trace ID Flips Between Responses

### Implementation

- [ ] Modified `src/routers/agent_runs.py` (lines 400-430)
- [ ] Set `trace_id` once at run creation (use stable UUID, not request_id)
- [ ] Added `request_id` field to `RunResponse` schema
- [ ] Set `result.request_id = request_id` (from context)
- [ ] Removed `result.trace_id = ev.trace_id` override (line 424)

### Validation

- [ ] POST `/agent-runs` → Save `trace_id` and `request_id` from response
- [ ] GET `/agent-runs/{id}` → Verify `trace_id` **unchanged**
- [ ] Verify `request_id` present in both responses
- [ ] Verify `X-Request-Id` header matches response `request_id`
- [ ] Run unit test: `pytest tests/test_trace_id_stability.py -v`

---

## Issue 4: Event ID Disappears

### Implementation

- [ ] Created migration: `ALTER TABLE agent_runs ADD COLUMN event_id TEXT NULL`
- [ ] Applied migration: `alembic upgrade head`
- [ ] Modified `src/routers/agent_runs.py` (line ~401) to persist event_id
- [ ] Removed `result.event_id = ev.event_id` override (line 425)

### Validation

- [ ] POST `/agent-runs` → Save `event_id` from response
- [ ] Verify `event_id` is non-null UUID string
- [ ] GET `/agent-runs/{id}` → Verify `event_id` **matches** POST response
- [ ] Check database: `SELECT event_id FROM agent_runs WHERE run_id = '...'`
- [ ] Run unit test: `pytest tests/test_event_id_persistence.py -v`

---

## Issue 5: Output Type Drift

### Implementation

- [ ] Modified `src/routers/agent_runs.py` (line 216): `output_text: str | None = None`
- [ ] Modified line 427: `result.output = final_output_obj if final_output_obj else None`
- [ ] Updated `RunResponse.output` type: `dict | list | None` (removed `str`)
- [ ] Added schema validator: Reject empty strings `""`

### Validation

- [ ] POST `/agent-runs` (immediate response) → Verify `output: null` (not `""`)
- [ ] GET `/agent-runs/{id}` (completed) → Verify `output` is dict or list
- [ ] Verify no response ever has `output: ""`
- [ ] Run schema test: `pytest tests/test_output_type_consistency.py -v`

---

## Issue 6: Step Timing Incomplete/Inconsistent

### Implementation

- [ ] Modified `src/services/orchestrator.py` (all step creation points)
- [ ] Always set `started_at = datetime.now(timezone.utc)` at step start
- [ ] Always set `finished_at = datetime.now(timezone.utc)` at step end
- [ ] Compute `latency_ms = (finished - started).total_seconds() * 1000`
- [ ] Added validator: If zero duration, set `latency_ms = 0` (not null)

### Validation

- [ ] Create agent run → Inspect all steps
- [ ] Verify every step has non-null `started_at`, `finished_at`
- [ ] Verify every step has `latency_ms >= 0` (never null)
- [ ] Verify `finished_at >= started_at` for all steps
- [ ] Run unit test: `pytest tests/test_step_timing_completeness.py -v`

---

## Issue 7: Rollup Metrics Stay Null

### Implementation

- [ ] Added helper functions in `src/services/orchestrator.py`:
  - `compute_warmup_duration(steps)`
  - `compute_todo_creation_duration(steps)`
  - `compute_todo_execution_duration(steps)`
- [ ] Modified `final_metrics` dict (line ~391) to populate rollup fields
- [ ] Persisted to database via `run.metrics`

### Validation

- [ ] Create agent run → Verify `metrics.model_warmup_ms` is non-null positive int
- [ ] Verify `metrics.todo_creation_ms` is non-null positive int
- [ ] Verify `metrics.todo_execution_ms` is non-null positive int
- [ ] Verify rollups match sum of granular timings (within 10ms tolerance)
- [ ] Run unit test: `pytest tests/test_rollup_metrics_populated.py -v`

---

## Issue 8: TODOs Marked Completed Without Evidence

### Implementation

- [ ] Modified `src/services/orchestrator.py` (TODO tracking logic)
- [ ] Added status variants: `completed`, `skipped`, `not_applicable`
- [ ] Added post-execution reconciliation pass
- [ ] Mark `completed` only if matching step exists

### Validation

- [ ] Create agent run → Inspect `todos` array
- [ ] For each TODO with `status: "completed"`:
  - [ ] Find matching step in `steps` array (by tool name)
  - [ ] Verify step exists and executed successfully
- [ ] If TODO marked `skipped` or `not_applicable`, verify has `reason` field
- [ ] Run unit test: `pytest tests/test_todo_completion_evidence.py -v`

---

## Issue 9: Zero-Time Step Has Null Latency

### Implementation

- [ ] Modified `src/services/orchestrator.py` (step finalization)
- [ ] Added logic: If `started_at == finished_at`, set `latency_ms = 0`
- [ ] Added validator in `OrchestrationStepOutput` model

### Validation

- [ ] Create agent run with fast steps
- [ ] Find any step with `started_at == finished_at`
- [ ] Verify that step has `latency_ms: 0` (not null)
- [ ] Run unit test: `pytest tests/test_zero_duration_step_latency.py -v`

---

## Issue 10: Top-Level Metric Duplication

### Implementation

- [ ] Modified `src/schemas/agents.py` (RunResponse schema)
- [ ] Added model validator to auto-populate top-level from metrics:
  - `self.total_llm_calls = len(self.metrics.llm_calls or [])`
  - `self.tool_calls = len(self.metrics.tool_calls or [])`
  - `self.tool_errors = sum(...)`

### Validation

- [ ] Create agent run → Verify both locations populated
- [ ] Verify `response.total_llm_calls == len(response.metrics.llm_calls)`
- [ ] Verify `response.tool_calls == len(response.metrics.tool_calls)`
- [ ] Verify `response.tool_errors == sum(1 for tc in metrics.tool_calls if tc.error)`
- [ ] Run contract test: `pytest tests/test_rollup_metrics_consistency.py -v`

---

## Issue 11: Health/Warmup Log Polish

### Implementation

- [ ] Modified `tests/integration/test_agent_execution.py` (lines 326-360)
- [ ] Changed status message: Show "⏳ Providers warming up..." instead of raw "degraded"
- [ ] Modified `src/health/components.py`: Return `"warming_up"` during initial load
- [ ] Only show "degraded" if timeout AND explicit `ALLOW_DEGRADED_PROVIDERS` flag

### Validation

- [ ] Run integration test in Docker
- [ ] Verify log shows: "⏳ Providers warming up... (checking every 2s)"
- [ ] Verify log shows: "✅ All providers healthy (Ollama ready)" when done
- [ ] Verify NO "degraded" message during normal warmup
- [ ] Only see "degraded" if we give up after 30s

---

## Issue 12: Create Response Already "Succeeded" with Empty Output

### Implementation

- [ ] Modified `src/routers/agent_runs.py` (lines 390-435)
- [ ] Added `db.expire_all()` after `db.commit()` (line 403)
- [ ] Added `db.refresh(run)` to re-read from database
- [ ] Ensured `final_output_obj` fully populated before setting `run.output`
- [ ] Added assertion: If `status == "succeeded"`, then `output` must be non-null

### Validation

- [ ] POST `/agent-runs` → Verify response
- [ ] If `status: "succeeded"`, verify `output` is non-null dict/list
- [ ] If `status: "succeeded"`, verify `finished_at` is non-null
- [ ] Verify no race condition (output matches final state)
- [ ] Run unit test: `pytest tests/test_create_response_consistency.py -v`

---

## Integration Testing

### Comprehensive Validation Test

- [ ] Created `tests/integration/test_rough_edges_validation.py`
- [ ] Test validates all 12 fixes in single agent run
- [ ] Run: `pytest tests/integration/test_rough_edges_validation.py -v`

### Checks Performed

- [ ] Schema validation: No `output: ""`, all timestamps non-null
- [ ] Stability: `trace_id` unchanged across GET requests
- [ ] Consistency: Top-level model == LLM metric model
- [ ] Completeness: All rollup metrics populated
- [ ] Evidence: Every completed TODO has matching step
- [ ] Logs: Clean, progressive status messages
- [ ] Timing: All steps have complete timing info
- [ ] No warnings during normal operation

---

## Staging Deployment

### Pre-Deployment

- [ ] All unit tests pass: `pytest tests/ -v`
- [ ] All integration tests pass: `pytest tests/integration/ -v`
- [ ] No linting errors: `ruff check src/`
- [ ] No type errors: `mypy src/`
- [ ] Database migrations applied: `alembic current` shows latest

### Deployment

- [ ] Set `ENABLE_POLISHED_TELEMETRY=true` in staging `.env`
- [ ] Restart staging services: `docker compose restart`
- [ ] Verify app starts successfully
- [ ] Check logs for errors: `docker compose logs -f app`

### Staging Validation

- [ ] Create test agent run via API
- [ ] Verify all 12 fixes applied correctly
- [ ] Monitor for 48 hours
- [ ] Check metrics: Response times, error rates, log volume
- [ ] Gather feedback from team

---

## Production Rollout

### Phase 1: Canary (10%)

- [ ] Enable feature flag for 10% of traffic
- [ ] Monitor for 24 hours
- [ ] Key metrics: Error rate < 0.1%, no schema violations
- [ ] Rollback plan ready if issues detected

### Phase 2: Expansion (50%)

- [ ] Increase to 50% of traffic
- [ ] Monitor for 24 hours
- [ ] Validate: Trace ID stability, output consistency
- [ ] Check dashboard: Metrics populating correctly

### Phase 3: Full Rollout (100%)

- [ ] Enable for 100% of traffic
- [ ] Monitor for 7 days
- [ ] Gather user feedback
- [ ] Document lessons learned

### Post-Deployment

- [ ] Remove feature flag (make permanent)
- [ ] Update API documentation
- [ ] Update dashboard queries (use normalized model names)
- [ ] Archive old code branches
- [ ] Close tracking tickets

---

## Rollback Procedure

If issues detected at any stage:

### Immediate Actions

- [ ] Set `ENABLE_POLISHED_TELEMETRY=false` in environment
- [ ] Restart affected services
- [ ] Verify old behavior restored
- [ ] Document issue for root cause analysis

### Database Rollback (if Issue 4 deployed)

- [ ] Run down migration: `alembic downgrade -1`
- [ ] Verify column removed: `\d agent_runs` (psql)
- [ ] Restart services

### Post-Rollback

- [ ] Analyze root cause
- [ ] Fix issue in staging
- [ ] Re-validate before retry
- [ ] Update rollback documentation

---

## Success Criteria

### Quantitative

- [ ] Test pass rate: 100% (no schema errors)
- [ ] Trace ID stability: 100% (no flips across requests)
- [ ] Metric completeness: 100% (no nulls in rollups)
- [ ] TODO evidence: 100% (all completed have matching steps)
- [ ] Zero production incidents related to these fixes

### Qualitative

- [ ] Clean, professional logs (no confusing messages)
- [ ] Dashboard queries simplified (no normalization needed)
- [ ] Support tickets reduced (no "disappeared" trace IDs)
- [ ] Team feedback positive

---

## Sign-Off

### Implementation Team

- [ ] Developer: _________________ Date: _______
- [ ] Code Review: _________________ Date: _______
- [ ] QA Lead: _________________ Date: _______

### Deployment Team

- [ ] Staging: _________________ Date: _______
- [ ] Production: _________________ Date: _______
- [ ] Verification: _________________ Date: _______

### Final Approval

- [ ] Product Owner: _________________ Date: _______
- [ ] Tech Lead: _________________ Date: _______

---

**Notes**:

- Use this checklist in order (dependencies matter)
- Check off items as you complete them
- Document any deviations in Notes section
- Keep this file updated throughout implementation
