# DB-Driven Default Model - Implementation Checklist

**Goal**: PostgreSQL becomes the single source of truth for default model, with Redis caching

**Status**: 🚧 Ready to Start  
**Date**: November 12, 2025

---

## Quick Start

```bash
# 1. Fetch and save tokens
./fetch_auth0_tokens.sh --save-to-env

# 2. Run baseline test (should pass)
docker compose exec -T app bash -c "pytest tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully -v -s --tb=short"

# 3. Implement changes below

# 4. Rebuild and test
docker compose up -d --build --remove-orphans
docker compose exec -T app bash -c "pytest tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully -v -s --tb=short"
```

---

## Implementation Checklist

### Phase 1: Default Model Resolver (Core) ⭐ CRITICAL

- [ ] **1.1 Create DMR Service**
  - File: `src/services/default_model_resolver.py`
  - Methods: `get_default_model()`, `invalidate_cache()`, `warmup_cache()`
  - Redis key: `models:default` (global) or `models:default:tenant:{id}`
  - TTL: 900 seconds (15 min, configurable)
  - Fallback to `settings.DEFAULT_MODEL_NAME` with WARN log
  - Observability: log `model.default.resolved` with source

- [ ] **1.2 Database Constraint Migration**
  - File: `db/postgres_control/alembic/versions/007_enforce_single_default.py`
  - Sanitize existing multi-default data (pick latest `updated_at`)
  - Add partial unique index on `(scope, tenant_id)`
  - Test: attempt to create duplicate defaults → should fail at DB

- [ ] **1.3 Wire PATCH /models/defaults**
  - File: `src/routers/model_instances.py`
  - After `set_default()`: call `dmr.invalidate_cache()`
  - Publish event: `model.default.changed`
  - Enqueue warmup task in background
  - Test: PATCH → verify cache cleared + warmup triggered

- [ ] **1.4 Update All Code Paths to Use DMR**
  - [ ] `src/routers/models.py` → `_resolve_runtime_targets()`
  - [ ] `src/orchestrator/agent.py` → model resolution
  - [ ] `src/health/components.py` → `probe_llm()`
  - [ ] `src/app.py` → startup initialization
  - Remove all direct reads of `settings.LLM_MODEL` or `settings.DEFAULT_MODEL_NAME`

---

### Phase 2: Provider Alignment & Warmup ⭐ HIGH

- [ ] **2.1 Startup Provider Alignment**
  - File: `src/app.py` → `_startup_init_default_model()`
  - Resolve default from DMR (not env var)
  - Compare `provider.model` vs `default.model_id`
  - If mismatch: update provider + trigger warmup
  - Log: `provider.model.aligned`

- [ ] **2.2 Deterministic Warmup Service**
  - File: `src/services/model_warmup.py`
  - Timeout: `settings.LLM_WARMUP_TIMEOUT` (300s)
  - Retry: 3 attempts with 10s delay
  - Set KEEP_ALIVE for Ollama
  - Record metrics: `model_warmup_ms`, `model_warmup_success`
  - Log: `model.warmup.started`, `model.warmup.succeeded`, `model.warmup.failed`

- [ ] **2.3 Health Uses DB Default**
  - File: `src/health/components.py` → `probe_llm()`
  - Use DMR to resolve model (not settings)
  - Health fails if default model unloaded/unreachable
  - Show `default_model_loaded=true` after warmup

---

### Phase 3: Tool Discovery & Caching 🟡 MEDIUM

- [ ] **3.1 Single catalog.discover Per Run**
  - File: `src/orchestrator/agent.py`
  - Add run-scoped cache: `self._tool_cache`
  - Track `self._catalog_discover_called`
  - Reused steps: mark `"reused": true` but don't count in metrics
  - Metric: `tool_calls=1` for catalog.discover

- [ ] **3.2 Cache Configuration**
  - Add env var: `CATALOG_CACHE_TTL` (default: 1800s)
  - Add cache bust endpoint/header for debugging
  - Document in README

---

### Phase 4: Provider Health Durability 🟡 MEDIUM

- [ ] **4.1 Background Health Refresh**
  - File: `src/background/provider_health_scheduler.py`
  - Interval: `PROVIDER_HEALTH_REFRESH_INTERVAL` (default: 3600s)
  - TTL: `PROVIDER_HEALTH_TTL` (default: 7200s)
  - Only run if `settings.SCHEDULER_ENABLED=true`
  - Log: `provider_health.refreshed` (debug level)

- [ ] **4.2 Config Guards**
  - If scheduler disabled: set TTL > longest expected test
  - Document: "Scheduler required for prod, increase TTL for tests"

---

### Phase 5: Observability ⭐ HIGH

- [ ] **5.1 Structured Logging**
  - Add breadcrumbs:
    - `model.default.resolved` (source, cached, model_id)
    - `model.default.changed` (instance_id, scope)
    - `model.default.cache_invalidated` (scope, reason)
    - `provider.model.aligned` (old_model, new_model)
    - `model.warmup.started/succeeded/failed`

- [ ] **5.2 Prometheus Metrics**
  - File: `src/metrics/prometheus.py`
  - `default_model_name` (Gauge, labeled by tenant_id)
  - `model_warmup_seconds` (Histogram, labeled by model_id, status)
  - `provider_health_status` (Gauge, labeled by provider_id)
  - `dmr_cache_hits_total` (Counter)
  - `dmr_cache_misses_total` (Counter)

---

### Phase 6: Config & Safety Rails 🟡 MEDIUM

- [ ] **6.1 Demote DEFAULT_MODEL_NAME**
  - File: `src/config.py`
  - Update description: "EMERGENCY FALLBACK ONLY"
  - DMR: log WARN when env fallback used
  - Health: set degraded when `source=env_fallback`

- [ ] **6.2 Startup Readiness Gate**
  - File: `src/app.py` → `_verify_readiness()`
  - Check: DB reachable + default model resolvable
  - `/readyz` endpoint returns 503 until ready
  - Don't accept traffic before default model set

---

### Phase 7: Testing ⭐ CRITICAL

- [ ] **7.1 Integration Test: DB vs Env Var**
  - File: `tests/integration/test_default_model_precedence.py`
  - Set env var to `llama2`
  - Set DB default to `phi3:mini`
  - Verify DMR returns `phi3:mini` (not env var)
  - Verify health shows `phi3:mini`

- [ ] **7.2 Integration Test: PATCH Invalidation**
  - File: `tests/integration/test_patch_defaults_invalidation.py`
  - Set default to `phi3:mini`
  - Warm cache (call DMR)
  - PATCH to `llama2`
  - Verify cache invalidated (next call uses `llama2`)
  - Verify warmup enqueued
  - Create agent run → uses `llama2`

- [ ] **7.3 Unit Tests**
  - DMR with Redis available
  - DMR with Redis unavailable (fallback)
  - DMR with DB unavailable (env fallback + WARN)
  - Cache invalidation
  - Provider alignment logic
  - Warmup retry logic

---

## Environment Variables to Add

```bash
# Default Model Resolver
DEFAULT_MODEL_CACHE_TTL_SECONDS=900  # 15 minutes
DEFAULT_MODEL_ALLOW_ENV_FALLBACK=true

# Model Warmup
LLM_WARMUP_TIMEOUT=300  # 5 minutes
LLM_WARMUP_RETRY_MAX=3
LLM_WARMUP_RETRY_DELAY=10

# Provider Health
PROVIDER_HEALTH_REFRESH_INTERVAL=3600  # 1 hour
PROVIDER_HEALTH_TTL=7200  # 2 hours

# Tool Discovery
CATALOG_CACHE_TTL=1800  # 30 minutes
```

---

## Validation Commands

```bash
# 1. Check DB default
docker compose exec postgres psql -U cineca_user -d cineca_platform \
  -c "SELECT mi.instance_name, mi.model_id, md.scope 
      FROM model_defaults md 
      JOIN model_instances mi ON md.instance_id = mi.id 
      WHERE md.scope='global';"

# 2. Check health shows DB default
curl http://localhost:8000/health | jq '.llm.model'

# 3. Check Redis cache
docker compose exec redis redis-cli GET models:default

# 4. Test PATCH invalidation
curl -X PATCH http://localhost:8000/v1/models/defaults \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat": {"instance_id": "NEW_INSTANCE_ID"}}'

# 5. Verify new model active
curl http://localhost:8000/health | jq '.llm'

# 6. Check logs for breadcrumbs
docker compose logs app | grep "model.default.resolved"
docker compose logs app | grep "model.warmup"
docker compose logs app | grep "provider.model.aligned"

# 7. Run integration test
docker compose exec -T app bash -c \
  "pytest tests/integration/test_agent_execution.py -v -s --tb=short"
```

---

## Success Criteria (Final Check)

After implementation, verify:

- ✅ No direct reads of `settings.LLM_MODEL` or `settings.DEFAULT_MODEL_NAME` in normal flow
- ✅ PATCH /models/defaults reflects in <1 second
- ✅ Cache hit rate >90% after warmup (check Prometheus)
- ✅ Health shows `default_model_loaded=true` after warmup
- ✅ Tool discovery called exactly once per run (check metrics)
- ✅ Provider health never expires during long tests
- ✅ Warmup completes within `LLM_WARMUP_TIMEOUT` (300s)
- ✅ Structured logs present for all model operations
- ✅ Integration test passes: DB default overrides env var
- ✅ Integration test passes: PATCH invalidates cache + triggers warmup

---

## Rollback Plan

If issues arise:

1. **Quick Revert**:
   ```bash
   # Restore env var precedence temporarily
   docker compose exec app bash -c \
     "echo 'Using env fallback' && export DEFAULT_MODEL_NAME=phi3:mini"
   ```

2. **Database Rollback**:
   ```bash
   docker compose exec postgres psql -U cineca_user -d cineca_platform \
     -c "DROP INDEX IF EXISTS idx_model_defaults_unique_scope_tenant;"
   ```

3. **Clear Redis Cache**:
   ```bash
   docker compose exec redis redis-cli DEL models:default
   docker compose exec redis redis-cli FLUSHDB
   ```

4. **Code Rollback**:
   ```bash
   git revert <commit-hash>
   docker compose up -d --build
   ```

---

## Next Steps

1. ✅ Review this checklist
2. Create feature branch: `feature/db-default-model`
3. Start with Phase 1 (DMR + DB constraint)
4. Run tests after each phase
5. Deploy to staging
6. Monitor metrics for 24h
7. Production rollout

---

**Need Help?**  
- See full implementation details in `DB_DEFAULT_MODEL_IMPLEMENTATION_PLAN.md`
- Check existing code: `src/routers/model_instances.py`, `db/postgres_control/repositories/model_instance_repo.py`
- Reference: Your test output + TODO requirements
