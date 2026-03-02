# DB Default Model - Quick Reference Card

## 🎯 Goal
Make PostgreSQL the **single source of truth** for default model (with Redis caching)

---

## 📦 What You Get

**4 Documents Created**:
1. `DB_DEFAULT_MODEL_SUMMARY.md` ← **START HERE** (overview + decisions)
2. `DB_DEFAULT_MODEL_TODO.md` ← **IMPLEMENTATION CHECKLIST** (step-by-step)
3. `DB_DEFAULT_MODEL_IMPLEMENTATION_PLAN.md` ← **DETAILED DESIGN** (code examples)
4. `DB_DEFAULT_MODEL_ARCHITECTURE.md` ← **DIAGRAMS** (visual reference)

---

## ⚡ Quick Start (3 Commands)

```bash
# 1. Run baseline test (should pass)
docker compose exec -T app bash -c \
  "pytest tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully -v -s"

# 2. Implement changes (see TODO.md)
# ... your implementation work ...

# 3. Validate (should still pass + new behavior)
docker compose up -d --build --remove-orphans
docker compose exec -T app bash -c \
  "pytest tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully -v -s"
```

---

## 🔑 Core Component: Default Model Resolver (DMR)

**File**: `src/services/default_model_resolver.py`

```python
class DefaultModelResolver:
    async def get_default_model(self, tenant_id=None):
        # 1. Check Redis cache → HIT? return
        # 2. Query PostgreSQL → Found? cache + return
        # 3. DB unreachable? → Env fallback + WARN
```

**Usage Everywhere**:
- ✅ API: `src/routers/models.py`
- ✅ Orchestrator: `src/orchestrator/agent.py`
- ✅ Health: `src/health/components.py`
- ✅ Startup: `src/app.py`

**NO MORE**: Direct reads of `settings.LLM_MODEL` or `settings.DEFAULT_MODEL_NAME`

---

## 🗄️ Database Change: Single Default Constraint

**Migration**: `007_enforce_single_default.py`

```sql
-- Enforces exactly one default per (scope, tenant_id)
CREATE UNIQUE INDEX idx_model_defaults_unique_scope_tenant
ON model_defaults (scope, tenant_id);
```

**Before**: Multiple defaults possible (data integrity risk)  
**After**: DB enforces single default (guaranteed consistency)

---

## 🔄 Write Flow: PATCH /models/defaults

```
1. Validate instance exists
2. Update PostgreSQL
3. Invalidate Redis cache          ← Key change!
4. Publish "model.default.changed"
5. Enqueue warmup task
6. Return 200 OK
```

**Result**: Changes reflect in <1 second (no restart needed)

---

## 📖 Read Flow: Resolution Precedence

```
Request → DMR.get_default_model()
         ├─ Check Redis cache
         │  └─ HIT → return (fast path ~1ms)
         ├─ Query PostgreSQL
         │  └─ Found → cache + return (~10ms)
         └─ DB unreachable?
            └─ Env fallback + WARN (~0ms, degraded)
```

---

## 📊 Observability (What You'll See)

### Logs (8 Events)
```
model.default.resolved          → source=db|redis|env_fallback
model.default.cache_invalidated → PATCH triggered
model.default.changed           → Event published
provider.model.aligned          → Startup alignment
model.warmup.started            → Warmup begin
model.warmup.succeeded          → Warmup done
```

### Metrics (5 Key Metrics)
```
default_model_name              → Current model (Gauge)
model_warmup_seconds            → Warmup duration (Histogram)
dmr_cache_hits_total            → Cache performance (Counter)
provider_health_status          → Provider status (Gauge)
```

---

## ⚙️ Configuration (7 New Env Vars)

```bash
DEFAULT_MODEL_CACHE_TTL_SECONDS=900  # 15 min Redis cache
LLM_WARMUP_TIMEOUT=300               # 5 min warmup timeout
LLM_WARMUP_RETRY_MAX=3               # Retry attempts
PROVIDER_HEALTH_REFRESH_INTERVAL=3600 # 1 hour background refresh
PROVIDER_HEALTH_TTL=7200             # 2 hour Redis TTL
CATALOG_CACHE_TTL=1800               # 30 min tool cache
```

---

## ✅ Success Criteria (7 Key Tests)

After implementation:

1. ✅ **No env var reads** in normal operation
2. ✅ **PATCH reflects <1s** on next request
3. ✅ **Cache hit rate >90%** after warmup
4. ✅ **Health shows model loaded** after warmup
5. ✅ **Tool discovery = 1 call** per run
6. ✅ **Provider health never expires** during tests
7. ✅ **Integration tests pass** (DB precedence + PATCH invalidation)

---

## 🧪 Validation Commands (Copy-Paste)

```bash
# 1. Check DB default
docker compose exec postgres psql -U cineca_user -d cineca_platform \
  -c "SELECT mi.model_id FROM model_defaults md 
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

# 5. Verify new model active
curl http://localhost:8000/health | jq '.llm.model'

# 6. Check logs
docker compose logs app | grep "model.default.resolved"
```

---

## 🚀 Implementation Phases (Order Matters)

### Phase 1: Core (CRITICAL) ⭐ ~ 4-6h
- DMR service
- DB constraint migration
- PATCH integration
- Update all code paths

### Phase 2: Provider & Warmup (HIGH) ⭐ ~ 3-4h
- Startup alignment
- Deterministic warmup
- Health uses DB default

### Phase 3: Tool Discovery (MEDIUM) 🟡 ~ 2-3h
- Single catalog.discover per run
- Cache configuration

### Phase 4: Provider Health (MEDIUM) 🟡 ~ 2-3h
- Background refresh scheduler

### Phase 5: Observability (HIGH) ⭐ ~ 2-3h
- Structured logs (8 events)
- Prometheus metrics (5 metrics)

### Phase 6: Config & Safety (MEDIUM) 🟡 ~ 2-3h
- Demote env var to fallback
- Startup readiness gate

### Phase 7: Testing (CRITICAL) ⭐ ~ 4-6h
- Integration tests (2 required)
- Unit tests

**Total**: 19-28 hours (2.5-3.5 days)

---

## 🔄 Rollback (If Needed)

```bash
# Quick: Restore env var
export DEFAULT_MODEL_NAME=phi3:mini
docker compose restart app

# Database: Drop constraint
docker compose exec postgres psql -U cineca_user -d cineca_platform \
  -c "DROP INDEX IF EXISTS idx_model_defaults_unique_scope_tenant;"

# Cache: Clear Redis
docker compose exec redis redis-cli FLUSHDB

# Code: Git revert
git revert <commit-hash>
docker compose up -d --build
```

---

## 🎓 Key Design Decisions

| Decision | Why |
|----------|-----|
| PostgreSQL source of truth | Durability + ACID + constraints |
| Redis cache (15 min TTL) | Performance (~1ms) + auto-expiry |
| Eager invalidation on PATCH | Consistency > cache staleness |
| Env var emergency fallback | Resilience (app runs if DB down) |
| Same model for health | End-to-end realism |
| Single tool discovery | Efficiency + determinism |
| Background health refresh | Never expires during long tests |

---

## 📞 Need Help?

1. **Overview**: `DB_DEFAULT_MODEL_SUMMARY.md`
2. **Step-by-step**: `DB_DEFAULT_MODEL_TODO.md` ← **Start here**
3. **Code examples**: `DB_DEFAULT_MODEL_IMPLEMENTATION_PLAN.md`
4. **Diagrams**: `DB_DEFAULT_MODEL_ARCHITECTURE.md`

---

## 🏁 Next Action

```bash
# Read the TODO checklist
cat DB_DEFAULT_MODEL_TODO.md

# Create feature branch
git checkout -b feature/db-default-model

# Start Phase 1
# 1. Create src/services/default_model_resolver.py
# 2. Create migration 007_enforce_single_default.py
# 3. Update PATCH endpoint
# 4. Update all code paths to use DMR
```

---

**Ready? Start with Phase 1 in `DB_DEFAULT_MODEL_TODO.md`!** 🚀
