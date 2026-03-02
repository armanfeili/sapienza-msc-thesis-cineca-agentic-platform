# Database-Driven Default Model - Implementation Summary

**Date**: November 12, 2025  
**Status**: 🚧 Ready for Implementation  
**Priority**: ⭐ CRITICAL

---

## 📋 What We're Building

**Current State** (Problem):
- Default model defined in env var `DEFAULT_MODEL_NAME=phi3:mini`
- No single source of truth
- Changes require restart
- Cache invalidation unclear
- Multiple tool discovery calls per run
- Provider health can expire during long tests

**Target State** (Solution):
- PostgreSQL `model_defaults` table is authoritative
- Redis cache with 15-min TTL + eager invalidation
- PATCH /models/defaults reflects immediately
- Env var only as emergency fallback (with WARN)
- Single tool discovery call per run
- Durable provider health with background refresh

---

## 📚 Documents Created

### 1. **DB_DEFAULT_MODEL_IMPLEMENTATION_PLAN.md** (Detailed)
- Full architecture overview with code examples
- All 8 phases explained with acceptance criteria
- Detailed Python snippets for each component
- Observability (logs + metrics)
- Deployment and rollback procedures

**Use When**: You need implementation details, code examples, or architecture decisions

---

### 2. **DB_DEFAULT_MODEL_TODO.md** (Checklist)
- Step-by-step tasks organized by priority
- ⭐ CRITICAL, 🟡 MEDIUM priority markers
- Quick validation commands
- Success criteria checklist
- Rollback procedures

**Use When**: You're implementing and need to track progress

---

### 3. **DB_DEFAULT_MODEL_ARCHITECTURE.md** (Visual)
- ASCII diagrams of data flow
- Write flow (PATCH)
- Read flow (resolution precedence)
- Log events reference
- Prometheus metrics reference
- Database schema
- Configuration reference

**Use When**: You need to understand the system at a glance or explain to others

---

## 🎯 Core Components

### 1. Default Model Resolver (DMR)
**File**: `src/services/default_model_resolver.py`

**Purpose**: Single entry point for all default model resolution

**Key Methods**:
- `get_default_model(tenant_id=None)` → Returns `{model_id, instance_id, source}`
- `invalidate_cache(scope, tenant_id)` → Clear Redis cache
- `warmup_cache(tenant_id)` → Pre-populate Redis

**Flow**:
```
1. Check Redis cache → HIT? Return cached
2. Query PostgreSQL → Found? Cache + return
3. DB unreachable? → Env fallback + WARN
```

---

### 2. Database Constraint (Migration 007)
**File**: `db/postgres_control/alembic/versions/007_enforce_single_default.py`

**Purpose**: Enforce exactly one default per scope (DB-level)

**Actions**:
1. Sanitize existing multi-default data (pick latest `updated_at`)
2. Add partial unique index: `(scope, tenant_id)`

**Result**: Cannot mark two defaults in same scope

---

### 3. PATCH Endpoint Integration
**File**: `src/routers/model_instances.py`

**After `set_default()` Success**:
1. Invalidate Redis cache
2. Publish `model.default.changed` event
3. Enqueue warmup task (background)
4. Return 200 OK

**Result**: Changes reflect immediately (<1s)

---

### 4. Provider Alignment (Startup)
**File**: `src/app.py` → `_startup_init_default_model()`

**On Boot**:
1. Resolve default from DMR (not env var)
2. Compare `provider.model` vs `default.model_id`
3. If mismatch: update provider + trigger warmup
4. Log: `provider.model.aligned`

**Result**: No 404s due to model/provider mismatch

---

### 5. Deterministic Warmup
**File**: `src/services/model_warmup.py`

**Features**:
- Timeout: 300s (configurable)
- Retry: 3 attempts with 10s delay
- Keep-alive: Set for Ollama
- Metrics: `model_warmup_ms`, `model_warmup_success`

**Result**: Predictable cold-start behavior

---

### 6. Single Tool Discovery
**File**: `src/orchestrator/agent.py`

**Implementation**:
- Run-scoped cache: `self._tool_cache`
- Track: `self._catalog_discover_called`
- Reused steps: mark `"reused": true` but don't count

**Result**: Metrics show `tool_calls=1` for catalog.discover

---

### 7. Provider Health Durability
**File**: `src/background/provider_health_scheduler.py`

**Features**:
- Interval: 3600s (1 hour)
- TTL: 7200s (2 hours)
- Only if `SCHEDULER_ENABLED=true`

**Result**: Health never expires during long tests

---

## 🔍 Observability

### Structured Logs (8 Events)
```
model.default.resolved          (INFO)  → source, cached, model_id
model.default.cache_invalidated (INFO)  → scope, reason
model.default.changed           (INFO)  → instance_id, timestamp
model.default.env_fallback      (WARN)  → reason=db_unreachable
provider.model.aligned          (INFO)  → old_model, new_model
model.warmup.started            (INFO)  → timeout, attempt
model.warmup.succeeded          (INFO)  → duration_ms
model.warmup.failed             (ERROR) → error, duration_ms
```

### Prometheus Metrics (5 Metrics)
```
default_model_name              (Gauge)     → labeled by tenant_id
model_warmup_seconds            (Histogram) → labeled by model_id, status
provider_health_status          (Gauge)     → labeled by provider_id
dmr_cache_hits_total            (Counter)   → labeled by tenant_id
dmr_cache_misses_total          (Counter)   → labeled by tenant_id
```

---

## ⚙️ Configuration

### New Environment Variables
```bash
# Default Model Resolver
DEFAULT_MODEL_CACHE_TTL_SECONDS=900
DEFAULT_MODEL_ALLOW_ENV_FALLBACK=true

# Model Warmup
LLM_WARMUP_TIMEOUT=300
LLM_WARMUP_RETRY_MAX=3
LLM_WARMUP_RETRY_DELAY=10

# Provider Health
PROVIDER_HEALTH_REFRESH_INTERVAL=3600
PROVIDER_HEALTH_TTL=7200

# Tool Discovery
CATALOG_CACHE_TTL=1800
```

---

## ✅ Success Criteria

After implementation, verify:

1. ✅ **No env var reads** in normal flow (only emergency fallback)
2. ✅ **PATCH reflects <1s** on subsequent requests
3. ✅ **Cache hit rate >90%** after warmup (Prometheus)
4. ✅ **Health shows model loaded** after warmup
5. ✅ **Tool discovery = 1 call** per run (metrics)
6. ✅ **Provider health never expires** during tests
7. ✅ **Warmup within timeout** (300s)
8. ✅ **Structured logs present** for all operations
9. ✅ **Integration tests pass**:
   - DB default overrides env var
   - PATCH invalidates cache + triggers warmup

---

## 🧪 Testing Strategy

### Integration Tests (2 Required)

1. **test_default_model_precedence.py**
   - Set env var: `llama2`
   - Set DB default: `phi3:mini`
   - Verify DMR returns `phi3:mini` (not env var)
   - Verify health shows `phi3:mini`

2. **test_patch_defaults_invalidation.py**
   - Set default: `phi3:mini`
   - Warm cache
   - PATCH to: `llama2`
   - Verify cache invalidated
   - Verify warmup enqueued
   - Create run → uses `llama2`

### Unit Tests (DMR)
- Redis available
- Redis unavailable (fallback)
- DB unavailable (env fallback + WARN)
- Cache invalidation
- Provider alignment
- Warmup retry logic

---

## 🚀 Implementation Order

### Phase 1: Core (CRITICAL) ⭐
1. Create DMR service
2. Database constraint migration
3. Wire PATCH endpoint
4. Update all code paths to use DMR

**Estimated Time**: 4-6 hours

---

### Phase 2: Provider & Warmup (HIGH) ⭐
1. Startup provider alignment
2. Deterministic warmup service
3. Health uses DB default

**Estimated Time**: 3-4 hours

---

### Phase 3: Tool Discovery (MEDIUM) 🟡
1. Single catalog.discover per run
2. Cache configuration

**Estimated Time**: 2-3 hours

---

### Phase 4: Provider Health (MEDIUM) 🟡
1. Background health refresh scheduler
2. Config guards

**Estimated Time**: 2-3 hours

---

### Phase 5: Observability (HIGH) ⭐
1. Structured logging (8 events)
2. Prometheus metrics (5 metrics)

**Estimated Time**: 2-3 hours

---

### Phase 6: Config & Safety (MEDIUM) 🟡
1. Demote DEFAULT_MODEL_NAME to fallback
2. Startup readiness gate (`/readyz`)

**Estimated Time**: 2-3 hours

---

### Phase 7: Testing (CRITICAL) ⭐
1. Integration test: DB vs env var
2. Integration test: PATCH invalidation
3. Unit tests

**Estimated Time**: 4-6 hours

---

**Total Estimated Time**: 19-28 hours (2.5-3.5 days)

---

## 📊 Validation Commands

```bash
# 1. Check DB default
docker compose exec postgres psql -U cineca_user -d cineca_platform \
  -c "SELECT mi.instance_name, mi.model_id FROM model_defaults md 
      JOIN model_instances mi ON md.instance_id = mi.id 
      WHERE md.scope='global';"

# 2. Check health
curl http://localhost:8000/health | jq '.llm.model'

# 3. Check Redis cache
docker compose exec redis redis-cli GET models:default

# 4. Test PATCH
curl -X PATCH http://localhost:8000/v1/models/defaults \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"chat": {"instance_id": "NEW_ID"}}'

# 5. Verify logs
docker compose logs app | grep "model.default.resolved"
docker compose logs app | grep "model.warmup"

# 6. Run integration test
docker compose exec -T app bash -c \
  "pytest tests/integration/test_agent_execution.py -v -s"
```

---

## 🔄 Rollback Plan

### Quick Revert (Temporary)
```bash
# Restore env var precedence
export DEFAULT_MODEL_NAME=phi3:mini
docker compose restart app
```

### Database Rollback
```bash
# Drop constraint
docker compose exec postgres psql -U cineca_user -d cineca_platform \
  -c "DROP INDEX IF EXISTS idx_model_defaults_unique_scope_tenant;"
```

### Cache Clear
```bash
docker compose exec redis redis-cli DEL models:default
docker compose exec redis redis-cli FLUSHDB
```

### Code Rollback
```bash
git revert <commit-hash>
docker compose up -d --build
```

---

## 🎓 Key Decisions Explained

### Why PostgreSQL as Source of Truth?
- **Durability**: Survives restarts
- **ACID**: Transactions guarantee consistency
- **Constraints**: DB enforces single default
- **Multi-tenancy**: Native support for tenant-scoped defaults

### Why Redis Cache?
- **Performance**: ~1ms vs ~10ms for Postgres
- **TTL**: Auto-expiry prevents stale reads
- **Simplicity**: No complex cache invalidation logic

### Why 15-min Cache TTL?
- **Balance**: Fast reads + tolerable staleness
- **Safety**: Eager invalidation on writes
- **Ops**: Long enough for high-traffic scenarios

### Why Env Var Fallback?
- **Resilience**: App still runs if DB unreachable
- **Observability**: WARN logs + health degradation
- **Safety**: Never silently fails

### Why Same Model for Health?
- **Realism**: End-to-end test of actual model
- **Honesty**: Green health means production-ready
- **Simplicity**: No "health model" vs "default model" confusion

---

## 📞 Support & Questions

- **Full Details**: See `DB_DEFAULT_MODEL_IMPLEMENTATION_PLAN.md`
- **Step-by-Step**: See `DB_DEFAULT_MODEL_TODO.md`
- **Architecture**: See `DB_DEFAULT_MODEL_ARCHITECTURE.md`
- **Existing Code**: `src/routers/model_instances.py`, `db/postgres_control/repositories/model_instance_repo.py`

---

## 🏁 Next Steps

1. ✅ **Review all 3 documents** (this + plan + todo + architecture)
2. Create feature branch: `feature/db-default-model`
3. Start with Phase 1 (DMR + DB constraint)
4. Run tests after each phase
5. Deploy to staging
6. Monitor metrics for 24h
7. Production rollout

---

**Ready to start? Begin with `DB_DEFAULT_MODEL_TODO.md` Phase 1!** 🚀
