# Rough Edges: Issue Dependency Map

```
                     ┌──────────────────────────────────┐
                     │   12 Rough Edges Identified     │
                     │     (Production Telemetry)       │
                     └─────────────┬────────────────────┘
                                   │
                 ┌─────────────────┼─────────────────┐
                 │                 │                 │
        ┌────────▼────────┐  ┌────▼─────┐  ┌───────▼────────┐
        │  Data Integrity │  │   UX     │  │  Observability │
        │   (HIGH RISK)   │  │  (LOW)   │  │   (MEDIUM)     │
        └────────┬────────┘  └────┬─────┘  └───────┬────────┘
                 │                │                 │
     ┌───────────┼────────┐       │       ┌────────┼─────────┐
     │           │        │       │       │        │         │
  ┌──▼──┐    ┌──▼──┐  ┌──▼──┐  ┌─▼──┐  ┌─▼──┐  ┌─▼──┐   ┌──▼──┐
  │ #5  │    │ #3  │  │ #12 │  │ #1 │  │ #2 │  │ #6 │   │ #7  │
  │Out- │    │Trace│  │Race │  │Log │  │Mod-│  │Tim-│   │Roll-│
  │put  │    │ ID  │  │Cond │  │Msg │  │ els│  │ing │   │ up  │
  │Type │    │Flip │  │     │  │    │  │    │  │    │   │     │
  └──┬──┘    └──┬──┘  └──┬──┘  └─┬──┘  └─┬──┘  └─┬──┘   └──┬──┘
     │          │        │       │       │      │         │
  ┌──▼──┐    ┌──▼──┐  ┌──▼──┐  ┌─▼──┐  ┌─▼──┐  ┌─▼──┐   ┌──▼──┐
  │ #4  │    │ #8  │  │ #9  │  │#11 │  │#10 │  │    │   │     │
  │Even-│    │TODO │  │Zero │  │Hlth│  │Dup │  │    │   │     │
  │t ID │    │Evid │  │Lat  │  │Log │  │    │  │    │   │     │
  └─────┘    └─────┘  └─────┘  └────┘  └────┘  └────┘   └─────┘

┌─────────────────────────────────────────────────────────────────┐
│                    IMPLEMENTATION ORDER                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Phase 1 (Critical - 4 hours)      Phase 2 (High Value - 5 hrs) │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━      ━━━━━━━━━━━━━━━━━━━━━━━━━━   │
│                                                                  │
│  ┌─────┐  ┌─────┐  ┌─────┐       ┌─────┐  ┌─────┐  ┌─────┐   │
│  │  5  │─▶│  3  │─▶│ 12  │       │  2  │─▶│  6  │─▶│  4  │   │
│  │Out- │  │Trace│  │Race │       │Mod- │  │Tim- │  │Even-│   │
│  │put  │  │ ID  │  │Cond │       │ els │  │ing  │  │t ID │   │
│  └─────┘  └─────┘  └─────┘       └─────┘  └─────┘  └─────┘   │
│                                                                  │
│  Phase 3 (Polish - 5 hours)                                     │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━                                   │
│                                                                  │
│  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐        │
│  │  7  │─▶│  8  │─▶│  1  │─▶│ 11  │─▶│  9  │─▶│ 10  │        │
│  │Roll-│  │TODO │  │Log  │  │Hlth │  │Zero │  │Dup  │        │
│  │ up  │  │Evid │  │Msg  │  │Log  │  │Lat  │  │    │         │
│  └─────┘  └─────┘  └─────┘  └─────┘  └─────┘  └─────┘        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      FILE IMPACT ANALYSIS                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  High Impact (Core Logic)          Medium Impact (Schema)       │
│  ━━━━━━━━━━━━━━━━━━━━━━━          ━━━━━━━━━━━━━━━━━━━━━        │
│                                                                  │
│  src/routers/agent_runs.py         src/schemas/agents.py        │
│    Issues: 3,4,5,12 (4 fixes)        Issues: 2,5,9,10 (4 fixes) │
│    Lines: ~100 changes                Lines: ~50 changes         │
│    Risk: MEDIUM-HIGH                  Risk: MEDIUM               │
│                                                                  │
│  src/services/orchestrator.py       tests/integration/...py     │
│    Issues: 2,6,7,8,9 (5 fixes)        Issues: 1,11 (2 fixes)    │
│    Lines: ~80 changes                 Lines: ~30 changes         │
│    Risk: MEDIUM                       Risk: LOW                  │
│                                                                  │
│  Low Impact (DB/Config)                                         │
│  ━━━━━━━━━━━━━━━━━━━━━                                         │
│                                                                  │
│  db/postgres_control/tables.py     src/config.py                │
│    Issues: 4 (1 fix)                  Issues: 2 (1 fix)          │
│    Lines: ~10 changes (migration)     Lines: ~20 changes         │
│    Risk: LOW (has rollback)           Risk: LOW                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     ISSUE RELATIONSHIPS                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Dependency Chain:                                              │
│                                                                  │
│  #5 (Output Type) ─┬─▶ #12 (Race Condition)                    │
│                    │                                             │
│                    └─▶ #3 (Trace ID) ─▶ #4 (Event ID)          │
│                                                                  │
│  #2 (Model Names) ──▶ #10 (Duplication) ──▶ #7 (Rollups)       │
│                                                                  │
│  #6 (Step Timing) ─┬─▶ #9 (Zero Latency)                       │
│                    │                                             │
│                    └─▶ #8 (TODO Evidence)                       │
│                                                                  │
│  Independent:                                                   │
│                                                                  │
│  #1 (Log Msg)  ──  No dependencies                              │
│  #11 (Health)  ──  No dependencies                              │
│                                                                  │
│  Recommendation: Fix in dependency order to avoid rework        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      TESTING STRATEGY                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Unit Tests (per issue)          Integration Tests              │
│  ━━━━━━━━━━━━━━━━━━━━━━          ━━━━━━━━━━━━━━━━━━            │
│                                                                  │
│  test_output_type_consistency     test_rough_edges_validation   │
│  test_trace_id_stability          ├─ Schema validation          │
│  test_event_id_persistence        ├─ Field consistency          │
│  test_model_name_consistency      ├─ Timing completeness        │
│  test_step_timing_completeness    ├─ Evidence matching          │
│  test_rollup_metrics_populated    └─ Log cleanliness            │
│  test_todo_completion_evidence                                  │
│  test_zero_duration_step_latency                                │
│  test_rollup_metrics_consistency                                │
│  test_create_response_consistency                               │
│                                                                  │
│  Contract Tests                                                 │
│  ━━━━━━━━━━━━━━━                                               │
│                                                                  │
│  test_response_contracts.py                                     │
│  ├─ Output never empty string                                   │
│  ├─ Model names match everywhere                                │
│  ├─ Trace/Event IDs stable                                      │
│  ├─ Timestamps always present                                   │
│  └─ Rollups match granular                                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      SUCCESS METRICS                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  BEFORE                             AFTER                       │
│  ━━━━━━                             ━━━━━                       │
│                                                                  │
│  ❌ 12 inconsistencies              ✅ Zero schema violations    │
│  ❌ Dashboard normalization         ✅ Single stable trace_id    │
│  ❌ Trace IDs disappear             ✅ All metrics non-null      │
│  ❌ Empty string outputs            ✅ Clean progressive logs    │
│  ❌ Null timing fields              ✅ Evidence for all TODOs    │
│  ❌ "Degraded" during warmup        ✅ Consistent model names    │
│                                                                  │
│  Key Performance Indicators:                                    │
│  ────────────────────────────                                   │
│                                                                  │
│  • Test pass rate: 100% (no schema errors)                      │
│  • Trace ID stability: 100% (no flips)                          │
│  • Metric completeness: 100% (no nulls in rollups)              │
│  • TODO evidence: 100% (all completed have steps)               │
│  • Log quality: Zero warnings during normal operation           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

Legend:
━━━ Section divider
─▶  Dependency (implement first → then)
┌─┐ Box boundary
│   Vertical connection
─   Horizontal connection
