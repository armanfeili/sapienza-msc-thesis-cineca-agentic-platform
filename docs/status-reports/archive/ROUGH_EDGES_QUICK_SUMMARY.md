# Rough Edges: Quick Reference

**12 polish issues** identified in production telemetry. Each with a concrete fix approach (no code implementation, per request).

---

## Quick Index

| # | Issue | Severity | File(s) | Effort |
|---|-------|----------|---------|--------|
| 1 | Misleading Docker token log | Low | `tests/conftest.py` | 15min |
| 2 | Model name inconsistency | High | `src/config.py`, `src/routers/agent_runs.py` | 1hr |
| 3 | Trace ID flips | High | `src/routers/agent_runs.py` | 1hr |
| 4 | Event ID disappears | Medium | `db/tables.py`, `src/routers/agent_runs.py` | 2hr |
| 5 | Output type drift | High | `src/routers/agent_runs.py`, `src/schemas/agents.py` | 1hr |
| 6 | Step timing incomplete | Medium | `src/services/orchestrator.py` | 2hr |
| 7 | Rollup metrics null | Medium | `src/services/orchestrator.py` | 2hr |
| 8 | TODOs without evidence | Medium | `src/services/orchestrator.py` | 1.5hr |
| 9 | Zero-time step latency | Low | `src/services/orchestrator.py` | 30min |
| 10 | Metric duplication | Low | `src/schemas/agents.py` | 1hr |
| 11 | Health log wording | Low | `tests/integration/test_agent_execution.py` | 30min |
| 12 | Create response race | High | `src/routers/agent_runs.py` | 1hr |

**Total Effort**: ~14 hours (2 days)

---

## One-Sentence Fixes

1. **Docker log**: Check if `RUNNING_IN_DOCKER` before logging "failed" → log "skipped" instead
2. **Model names**: Create `normalize_model_name()` and apply at ingestion + validate consistency
3. **Trace ID**: Never overwrite `trace_id` after creation; add separate `request_id` field
4. **Event ID**: Add DB column, persist at creation, remove override in GET response
5. **Output type**: Initialize as `None` (not `""`), validate never empty string, ensure object/null only
6. **Step timing**: Always set `started_at`/`finished_at`, compute `latency_ms`, never leave null
7. **Rollup metrics**: Compute from steps in orchestrator, add helper functions for phase durations
8. **TODO evidence**: Mark completed only if matching step exists; add reconciliation pass
9. **Zero latency**: Set `latency_ms = 0` for same-timestamp steps, add validator
10. **Duplication**: Auto-populate top-level from `metrics.*` in model validator for consistency
11. **Health wording**: Print "warming up" during wait, only "degraded" if timeout with explicit flag
12. **Response race**: Add `db.refresh(run)` after commit, ensure output populated before response

---

## Implementation Phases

### Phase 1: Critical (Day 1 AM)
- **Issue 5**: Output type drift
- **Issue 3**: Trace ID stability
- **Issue 12**: Create response race

### Phase 2: High Value (Day 1 PM)
- **Issue 2**: Model consistency
- **Issue 6**: Step timing
- **Issue 4**: Event ID persistence

### Phase 3: Polish (Day 2)
- **Issue 7**: Rollup metrics
- **Issue 8**: TODO evidence
- **Issue 1**: Docker logs
- **Issue 11**: Health wording
- **Issue 9**: Zero latency
- **Issue 10**: Duplication

---

## Testing Checklist

After each phase, validate:

- [ ] **Schema**: No `output: ""`, all timestamps non-null
- [ ] **Stability**: `trace_id` unchanged across GET requests
- [ ] **Consistency**: Top-level model == LLM metric model
- [ ] **Completeness**: All rollup metrics populated
- [ ] **Evidence**: Every completed TODO has matching step
- [ ] **Logs**: Clean, progressive status messages

**Integration Test**:

```bash
pytest tests/integration/test_agent_execution.py -v
# Expected: PASSED, clean output, no warnings
```

---

## Risk Assessment

**Low Risk**:

- Issues 1, 9, 10, 11 (cosmetic/logging changes)
- Can deploy independently

**Medium Risk**:

- Issues 2, 4, 6, 7, 8 (logic changes with validators)
- Deploy with feature flag: `ENABLE_POLISHED_TELEMETRY=true`

**Higher Risk**:

- Issues 3, 5, 12 (schema changes, race conditions)
- Requires staging validation before prod
- Add backwards-compat fields during transition

**Mitigation**: Implement with feature flag, gradual rollout

---

## Success Criteria

**Before**:

- 12 inconsistencies in logs
- Dashboard queries need normalization
- "Disappeared" trace IDs in support tickets

**After**:

- Zero schema violations
- Single stable trace_id per run
- All metrics non-null
- Clean, professional logs

---

## See Full Details

→ [`ROUGH_EDGES_FIX_PLAN.md`](./ROUGH_EDGES_FIX_PLAN.md) (complete implementation guide)
