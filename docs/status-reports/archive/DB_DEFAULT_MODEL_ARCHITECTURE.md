# DB-Driven Default Model - Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          APPLICATION LAYER                                │
│                                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────┐  ┌─────────────────┐  │
│  │   API       │  │ Orchestrator │  │  Health  │  │   Startup       │  │
│  │  /models/*  │  │   Agent.py   │  │  Check   │  │   Warmup        │  │
│  └──────┬──────┘  └──────┬───────┘  └────┬─────┘  └────────┬────────┘  │
│         │                │                │                  │           │
│         └────────────────┴────────────────┴──────────────────┘           │
│                                   │                                       │
└───────────────────────────────────┼───────────────────────────────────────┘
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    DEFAULT MODEL RESOLVER (DMR)                           │
│                   src/services/default_model_resolver.py                  │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  get_default_model(tenant_id=None) → {model_id, instance_id}   │    │
│  │                                                                  │    │
│  │  1. Check Redis cache: models:default[:tenant:{id}]            │    │
│  │     ├─ HIT  → return cached {model_id, source="redis"}         │    │
│  │     └─ MISS → continue to step 2                               │    │
│  │                                                                  │    │
│  │  2. Query PostgreSQL:                                           │    │
│  │     SELECT mi.model_id, mi.id, mi.provider_id                   │    │
│  │     FROM model_defaults md                                      │    │
│  │     JOIN model_instances mi ON md.instance_id = mi.id          │    │
│  │     WHERE md.scope = 'global' AND md.tenant_id IS NULL         │    │
│  │                                                                  │    │
│  │  3. Cache result in Redis (TTL: 15min)                         │    │
│  │                                                                  │    │
│  │  4. Return {model_id, instance_id, source="db"}                │    │
│  │                                                                  │    │
│  │  5. FALLBACK (if DB unreachable):                              │    │
│  │     ⚠️  LOG WARN: "using env fallback"                          │    │
│  │     ⚠️  Health degraded: source=env_fallback                    │    │
│  │     return {model_id=DEFAULT_MODEL_NAME, source="env_fallback"}│    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  invalidate_cache(scope, tenant_id)                             │    │
│  │  - DEL models:default[:tenant:{id}]                             │    │
│  │  - LOG: "model.default.cache_invalidated"                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  warmup_cache(tenant_id)                                        │    │
│  │  - Call get_default_model() to pre-populate Redis              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└───────────────┬───────────────────────────────────┬───────────────────────┘
                │                                   │
       ┌────────▼────────┐                 ┌────────▼────────┐
       │   PostgreSQL    │                 │  Redis Cache    │
       │   (Authority)   │                 │   (Fast Path)   │
       │                 │                 │                 │
       │ model_instances │                 │ models:default  │
       │ model_defaults  │                 │ TTL: 900s       │
       └─────────────────┘                 └─────────────────┘
```

---

## Write Flow: PATCH /models/defaults

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. Client PATCH /v1/models/defaults                                     │
│    {"chat": {"instance_id": "abc-123"}}                                 │
└────────────────────┬────────────────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. Validate instance exists + enabled                                   │
│    model_instance_repo.get_instance(instance_id)                        │
└────────────────────┬────────────────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. Update PostgreSQL                                                    │
│    model_instance_repo.set_default(instance_id, scope, tenant_id)      │
│    - UPSERT model_defaults table                                       │
│    - Enforce unique constraint (scope, tenant_id)                      │
└────────────────────┬────────────────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. Invalidate Redis cache                                               │
│    dmr.invalidate_cache(scope, tenant_id)                               │
│    - DEL models:default[:tenant:{id}]                                   │
└────────────────────┬────────────────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. Publish event                                                        │
│    event_bus.publish("model.default.changed", {                         │
│      instance_id, scope, tenant_id, timestamp                           │
│    })                                                                    │
└────────────────────┬────────────────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 6. Enqueue warmup task (background)                                     │
│    background_tasks.add_task(warmup_model, instance_id)                 │
└────────────────────┬────────────────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 7. Return 200 OK                                                        │
│    {instance_id, etag, scope}                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Read Flow: Resolution Precedence

```
Application needs model name
         │
         ▼
┌─────────────────────────────────────────┐
│ DMR.get_default_model(tenant_id)        │
└────────────┬────────────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌─────────┐     ┌──────────┐
│ Redis   │     │ Cache    │
│ Cache?  │────▶│ Hit?     │
└─────────┘     └────┬─────┘
                     │
          ┌──────────┴──────────┐
          │ YES                 │ NO
          ▼                     ▼
    ┌──────────┐          ┌──────────────┐
    │ Return   │          │ Query        │
    │ cached   │          │ PostgreSQL   │
    │ result   │          └──────┬───────┘
    └──────────┘                 │
                                 ▼
                           ┌──────────────┐
                           │ Found in DB? │
                           └──────┬───────┘
                                  │
                       ┌──────────┴──────────┐
                       │ YES                 │ NO
                       ▼                     ▼
                 ┌──────────┐          ┌──────────────┐
                 │ Cache in │          │ DB           │
                 │ Redis    │          │ unreachable? │
                 │ (15 min) │          └──────┬───────┘
                 └────┬─────┘                 │
                      │              ┌────────┴────────┐
                      │              │ YES             │ NO
                      │              ▼                 ▼
                      │        ┌──────────┐      ┌──────────┐
                      │        │ ⚠️ Env   │      │ Return   │
                      │        │ Fallback │      │ None     │
                      │        │ + WARN   │      │ (404)    │
                      │        └──────────┘      └──────────┘
                      │
                      ▼
                ┌──────────┐
                │ Return   │
                │ to caller│
                └──────────┘
```

---

## Observability: Log Events

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Event                           │ Level │ Context                        │
├─────────────────────────────────┼───────┼────────────────────────────────┤
│ model.default.resolved          │ INFO  │ model_id, source, cached,      │
│                                 │       │ tenant_id                      │
├─────────────────────────────────┼───────┼────────────────────────────────┤
│ model.default.cache_invalidated │ INFO  │ scope, tenant_id, reason       │
├─────────────────────────────────┼───────┼────────────────────────────────┤
│ model.default.changed           │ INFO  │ instance_id, scope,            │
│                                 │       │ tenant_id, timestamp           │
├─────────────────────────────────┼───────┼────────────────────────────────┤
│ model.default.env_fallback      │ WARN  │ model_id, reason=db_unreachable│
├─────────────────────────────────┼───────┼────────────────────────────────┤
│ provider.model.aligned          │ INFO  │ provider_id, old_model,        │
│                                 │       │ new_model, action=updated      │
├─────────────────────────────────┼───────┼────────────────────────────────┤
│ model.warmup.started            │ INFO  │ model_id, timeout, attempt     │
├─────────────────────────────────┼───────┼────────────────────────────────┤
│ model.warmup.succeeded          │ INFO  │ model_id, duration_ms          │
├─────────────────────────────────┼───────┼────────────────────────────────┤
│ model.warmup.failed             │ ERROR │ model_id, error, duration_ms   │
├─────────────────────────────────┼───────┼────────────────────────────────┤
│ provider_health.refreshed       │ DEBUG │ provider_id, status            │
└─────────────────────────────────┴───────┴────────────────────────────────┘
```

---

## Metrics: Prometheus

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Metric                        │ Type      │ Labels                       │
├───────────────────────────────┼───────────┼──────────────────────────────┤
│ default_model_name            │ Gauge     │ tenant_id                    │
│ - Current default model       │           │                              │
├───────────────────────────────┼───────────┼──────────────────────────────┤
│ model_warmup_seconds          │ Histogram │ model_id, status             │
│ - Warmup duration             │           │                              │
├───────────────────────────────┼───────────┼──────────────────────────────┤
│ provider_health_status        │ Gauge     │ provider_id, provider_name   │
│ - 1=healthy, 0=unhealthy      │           │                              │
├───────────────────────────────┼───────────┼──────────────────────────────┤
│ dmr_cache_hits_total          │ Counter   │ tenant_id                    │
│ - Cache hit count             │           │                              │
├───────────────────────────────┼───────────┼──────────────────────────────┤
│ dmr_cache_misses_total        │ Counter   │ tenant_id                    │
│ - Cache miss count            │           │                              │
└───────────────────────────────┴───────────┴──────────────────────────────┘

Target: Cache hit rate >90% after warmup
Alert: Warmup duration >120s on 2nd+ boot
```

---

## Database Schema

```sql
-- model_instances table (existing)
CREATE TABLE model_instances (
    id UUID PRIMARY KEY,
    tenant_id TEXT,
    instance_name TEXT NOT NULL,
    provider_id UUID NOT NULL,
    model_id TEXT NOT NULL,  -- e.g., "phi3:mini"
    enabled BOOLEAN DEFAULT TRUE,
    loaded BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, instance_name)
);

-- model_defaults table (existing)
CREATE TABLE model_defaults (
    id SERIAL PRIMARY KEY,
    scope TEXT NOT NULL,  -- 'global' or 'tenant'
    tenant_id TEXT,  -- NULL for global
    instance_id UUID NOT NULL REFERENCES model_instances(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    etag TEXT NOT NULL,
    
    -- NEW: Enforce exactly one default per scope
    CONSTRAINT uq_scope_tenant UNIQUE (scope, tenant_id)
);

-- NEW: Partial unique index (migration 007)
CREATE UNIQUE INDEX idx_model_defaults_unique_scope_tenant
ON model_defaults (scope, tenant_id)
WHERE scope IN ('global', 'tenant');
```

---

## Configuration: Environment Variables

```bash
# src/config.py - New fields

# Default Model Resolver
DEFAULT_MODEL_CACHE_TTL_SECONDS=900  # 15 minutes (Redis cache)
DEFAULT_MODEL_ALLOW_ENV_FALLBACK=true  # Emergency fallback

# Model Warmup
LLM_WARMUP_TIMEOUT=300  # 5 minutes for cold starts
LLM_WARMUP_RETRY_MAX=3  # Retry attempts
LLM_WARMUP_RETRY_DELAY=10  # Seconds between retries

# Provider Health
PROVIDER_HEALTH_REFRESH_INTERVAL=3600  # 1 hour (background refresh)
PROVIDER_HEALTH_TTL=7200  # 2 hours (Redis TTL)

# Tool Discovery
CATALOG_CACHE_TTL=1800  # 30 minutes
```

---

## Key Decisions

1. **Single Source of Truth**: PostgreSQL `model_defaults` table
2. **Caching Strategy**: Redis with 15-min TTL + eager invalidation
3. **Fallback Policy**: Env var only if DB unreachable + WARN
4. **Health Model**: Use same default model (end-to-end realism)
5. **Warmup**: Bounded timeout (300s) + retry (3x) + keep-alive
6. **Tool Discovery**: Single call per run + reuse cache
7. **Provider Health**: Long TTL (2h) + background refresh (1h)

---

## References

- Full plan: `DB_DEFAULT_MODEL_IMPLEMENTATION_PLAN.md`
- Checklist: `DB_DEFAULT_MODEL_TODO.md`
- Current code: `src/routers/model_instances.py`, `db/postgres_control/repositories/model_instance_repo.py`
- Test output: See your terminal log
- Requirements: Your TODO list from user prompt
