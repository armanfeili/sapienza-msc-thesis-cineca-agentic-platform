# Database-Driven Default Model Implementation Plan

**Goal**: Make PostgreSQL the single source of truth for default model resolution, with Redis caching and explicit invalidation on writes.

**Status**: 🚧 Ready for Implementation  
**Date**: November 12, 2025

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   Application Requests                       │
│            (API, Orchestrator, Health, Warmup)              │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│           Default Model Resolver (DMR)                       │
│                                                              │
│  1. Check Redis cache (models:default)                      │
│  2. If miss → Query PostgreSQL (model_instances)            │
│  3. Cache result in Redis (TTL: 10-30min)                   │
│  4. Fallback to env var ONLY if DB unreachable + WARN       │
└─────────────────┬───────────────────────────────────────────┘
                  │
         ┌────────┴────────┐
         ▼                 ▼
┌──────────────┐   ┌──────────────┐
│ PostgreSQL   │   │ Redis Cache  │
│ (Authority)  │   │ (Fast path)  │
└──────────────┘   └──────────────┘
```

---

## Implementation Tasks

### ✅ Phase 1: Core Infrastructure (Priority: CRITICAL)

#### 1.1 Create Default Model Resolver (DMR)

**File**: `src/services/default_model_resolver.py`

**Purpose**: Single entry point for all default model resolution

**Key Methods**:
- `get_default_model()` → Returns model_id + metadata
- `invalidate_cache()` → Clear Redis cache
- `warmup_cache()` → Pre-populate Redis on startup/change
- `get_resolution_source()` → Return "db" | "redis" | "env_fallback"

**Caching Strategy**:
- Redis key: `models:default` (global) or `models:default:tenant:{tenant_id}`
- TTL: 15 minutes (configurable via `DEFAULT_MODEL_CACHE_TTL_SECONDS`)
- Eager invalidation on `PATCH /models/defaults`

**Observability**:
```python
logger.info("model.default.resolved", extra={
    "model_id": "phi3:mini",
    "source": "db",  # or "redis", "env_fallback"
    "cached": True,
    "tenant_id": tenant_id or "global"
})
```

**Acceptance Criteria**:
- ✅ All code paths use DMR (no direct `settings.LLM_MODEL` reads)
- ✅ DB change reflects immediately on next request
- ✅ Metrics show cache hit rate >90% after warmup
- ✅ Health degraded if env fallback active

---

#### 1.2 Wire PATCH /models/defaults to DMR

**File**: `src/routers/model_instances.py`

**Changes**:
1. After successful `model_instance_repo.set_default()`:
   ```python
   # Invalidate cache
   await dmr.invalidate_cache(scope=scope, tenant_id=tenant_id)
   
   # Publish event for subscribers
   await event_bus.publish("model.default.changed", {
       "instance_id": instance_id,
       "scope": scope,
       "tenant_id": tenant_id,
       "timestamp": datetime.utcnow()
   })
   
   # Trigger warmup (async task)
   background_tasks.add_task(warmup_model, instance_id)
   ```

2. Return enriched response with cache invalidation confirmation

**Acceptance Criteria**:
- ✅ `PATCH /models/defaults` invalidates Redis immediately
- ✅ Subsequent `GET /health` shows new model
- ✅ Warmup task enqueued within 100ms of PATCH
- ✅ Event published exactly once (no duplicates)

---

#### 1.3 Database Constraint: Exactly One Default

**File**: `db/postgres_control/alembic/versions/007_enforce_single_default.py`

**Migration**:
```python
def upgrade():
    # 1. Sanitize existing data (pick latest updated_at if multiple defaults)
    op.execute("""
        WITH ranked AS (
            SELECT id, scope, tenant_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY scope, tenant_id 
                       ORDER BY updated_at DESC
                   ) as rn
            FROM model_defaults
        )
        DELETE FROM model_defaults
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
    """)
    
    # 2. Add partial unique index (allows one default per scope+tenant)
    op.create_index(
        'idx_model_defaults_unique_scope_tenant',
        'model_defaults',
        ['scope', 'tenant_id'],
        unique=True,
        postgresql_where=sa.text("scope IN ('global', 'tenant')")
    )
```

**Acceptance Criteria**:
- ✅ Cannot mark two defaults in same scope
- ✅ Existing multi-default data auto-fixed by migration
- ✅ DB-level enforcement (application cannot bypass)

---

### ✅ Phase 2: Provider Alignment (Priority: HIGH)

#### 2.1 Startup Default Model Alignment

**File**: `src/app.py` → `_startup_init_default_model()`

**Changes**:
```python
async def _startup_init_default_model():
    # 1. Resolve default from DMR
    default = await dmr.get_default_model()
    
    if not default:
        logger.warning("startup.no_default_model", extra={
            "action": "using_env_fallback",
            "env_model": settings.DEFAULT_MODEL_NAME
        })
        # Continue with env fallback but mark health as degraded
        health_mod.set_degraded(reason="no_db_default")
        return
    
    model_id = default["model_id"]
    instance_id = default["instance_id"]
    provider_id = default["provider_id"]
    
    # 2. Get provider record
    provider = pg_repo.get_provider(provider_id)
    
    # 3. Check if provider.model matches default
    if provider.get("model") != model_id:
        logger.info("startup.provider_model_mismatch", extra={
            "provider_model": provider.get("model"),
            "default_model": model_id,
            "action": "updating_provider"
        })
        
        # Update provider model
        pg_repo.patch_provider(provider_id, {"model": model_id})
        
        # Trigger warmup
        await warmup_default_model(model_id, provider)
    
    # 4. Verify model is loaded/warm
    health = await check_provider_health(provider)
    if not health.get("ok"):
        logger.error("startup.model_not_ready", extra={
            "model_id": model_id,
            "provider_id": provider_id
        })
        health_mod.set_degraded(reason="model_not_ready")
```

**Acceptance Criteria**:
- ✅ Health endpoint shows `provider.model == db_default` after boot
- ✅ No 404s due to model/provider mismatch
- ✅ Automatic provider update + warmup if mismatch detected

---

### ✅ Phase 3: Model Warmup (Priority: HIGH)

#### 3.1 Deterministic Warmup Workflow

**File**: `src/services/model_warmup.py`

**Implementation**:
```python
class ModelWarmupService:
    def __init__(self):
        self.timeout = settings.LLM_WARMUP_TIMEOUT  # 300s
        self.retry_max = 3
        self.retry_delay = 10  # seconds
    
    async def warmup_model(self, model_id: str, provider: dict) -> bool:
        """Warmup model with bounded time budget and retries."""
        start = time.time()
        
        for attempt in range(1, self.retry_max + 1):
            try:
                logger.info("model.warmup.start", extra={
                    "model_id": model_id,
                    "attempt": attempt,
                    "timeout": self.timeout
                })
                
                # Make warmup call
                result = await self._call_model(
                    model_id, 
                    provider, 
                    timeout=self.timeout
                )
                
                elapsed = time.time() - start
                
                # Update metrics
                self._record_metric("model_warmup_ms", elapsed * 1000)
                self._record_metric("model_warmup_success", 1)
                
                # Set KEEP_ALIVE if Ollama
                if provider.get("type") == "ollama":
                    await self._set_keep_alive(model_id, provider)
                
                logger.info("model.warmup.success", extra={
                    "model_id": model_id,
                    "elapsed_ms": elapsed * 1000
                })
                
                return True
                
            except asyncio.TimeoutError:
                elapsed = time.time() - start
                logger.warning("model.warmup.timeout", extra={
                    "model_id": model_id,
                    "attempt": attempt,
                    "elapsed_s": elapsed
                })
                
                if attempt < self.retry_max:
                    await asyncio.sleep(self.retry_delay)
                    continue
                else:
                    self._record_metric("model_warmup_timeout", 1)
                    return False
                    
            except Exception as e:
                logger.error("model.warmup.failed", extra={
                    "model_id": model_id,
                    "error": str(e)
                })
                self._record_metric("model_warmup_failure", 1)
                return False
```

**Acceptance Criteria**:
- ✅ Warmup completes within `LLM_WARMUP_TIMEOUT` or fails gracefully
- ✅ Health shows `default_model_loaded=true` after success
- ✅ Prometheus metrics: `model_warmup_ms`, `model_warmup_success`
- ✅ Retry with exponential backoff on transient failures

---

#### 3.2 Health Model Policy

**File**: `src/health/components.py` → `probe_llm()`

**Decision**: Use same default model for health checks (end-to-end realism)

**Changes**:
```python
async def probe_llm() -> ComponentCheck:
    """Probe LLM availability using DB-defined default model."""
    try:
        # Resolve default from DMR
        default = await dmr.get_default_model()
        
        if not default:
            return ComponentCheck(
                ok=False,
                status="no_default",
                message="No default model configured",
                details={"source": "none"}
            )
        
        model_id = default["model_id"]
        
        # Make test call with short timeout
        response = await llm_client.chat(
            model=model_id,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
            timeout=10.0
        )
        
        return ComponentCheck(
            ok=True,
            status="healthy",
            message=f"Model {model_id} responsive",
            details={
                "model_id": model_id,
                "latency_ms": response.get("latency_ms"),
                "source": default["source"]
            }
        )
        
    except Exception as e:
        return ComponentCheck(
            ok=False,
            status="unhealthy",
            message=str(e),
            details={"error": str(e)}
        )
```

**Acceptance Criteria**:
- ✅ Health reflects real readiness of default model
- ✅ No green health if default model unloaded
- ✅ Health degrades if warmup failed

---

### ✅ Phase 4: Orchestrator Efficiency (Priority: MEDIUM)

#### 4.1 Single catalog.discover Per Run

**File**: `src/orchestrator/agent.py`

**Changes**:
```python
class Agent:
    def __init__(self):
        self._tool_cache = {}  # Run-scoped cache
        self._catalog_discover_called = False
    
    async def discover_tools(self):
        """Discover tools exactly once per run."""
        if self._catalog_discover_called:
            logger.debug("tool.discover.reused", extra={
                "cached_count": len(self._tool_cache)
            })
            return self._tool_cache
        
        # Real discovery
        start = time.time()
        tools = await self._catalog.discover()
        elapsed = time.time() - start
        
        self._tool_cache = tools
        self._catalog_discover_called = True
        
        # Metrics: count as 1 call
        self._record_metric("tool_calls", {
            "tool": "catalog.discover",
            "count": 1,
            "latency_ms": elapsed * 1000
        })
        
        logger.info("tool.discover.executed", extra={
            "tool_count": len(tools),
            "latency_ms": elapsed * 1000
        })
        
        return tools
```

**Acceptance Criteria**:
- ✅ Metrics show `tool_calls=1` for catalog.discover
- ✅ Reused steps marked with `"reused": true` but not counted
- ✅ No "multiple discover calls" warning

---

### ✅ Phase 5: Provider Health Durability (Priority: MEDIUM)

#### 5.1 Background Health Refresh

**File**: `src/background/provider_health_scheduler.py`

**Implementation**:
```python
class ProviderHealthScheduler:
    """Background task to refresh provider health periodically."""
    
    def __init__(self):
        self.interval = settings.PROVIDER_HEALTH_REFRESH_INTERVAL or 3600  # 1 hour
        self.ttl = settings.PROVIDER_HEALTH_TTL or 7200  # 2 hours
        self._task = None
    
    async def start(self):
        """Start background refresh loop."""
        if not settings.SCHEDULER_ENABLED:
            logger.info("provider_health.scheduler.disabled")
            return
        
        self._task = asyncio.create_task(self._refresh_loop())
    
    async def _refresh_loop(self):
        """Periodic refresh of all provider health."""
        while True:
            try:
                await asyncio.sleep(self.interval)
                
                providers = pg_repo.list_providers()
                
                for provider in providers:
                    try:
                        health = await check_provider_health(provider)
                        
                        # Store in Redis with TTL
                        pg_repo.set_provider_health(
                            provider["id"],
                            health,
                            ttl=self.ttl
                        )
                        
                        logger.debug("provider_health.refreshed", extra={
                            "provider_id": provider["id"],
                            "status": "healthy" if health.get("ok") else "unhealthy"
                        })
                        
                    except Exception as e:
                        logger.warning("provider_health.refresh_failed", extra={
                            "provider_id": provider["id"],
                            "error": str(e)
                        })
                
            except Exception as e:
                logger.error("provider_health.scheduler.error", extra={
                    "error": str(e)
                })
```

**Acceptance Criteria**:
- ✅ Health never expires during long-running tests
- ✅ TTL > longest expected test duration
- ✅ Background refresh without noisy logs

---

### ✅ Phase 6: Observability (Priority: HIGH)

#### 6.1 Structured Logging

**Events to Add**:
```python
# Model resolution
logger.info("model.default.resolved", extra={
    "model_id": "phi3:mini",
    "instance_id": "abc-123",
    "provider_id": "ollama-local",
    "source": "db",  # db | redis | env_fallback
    "cached": True,
    "tenant_id": tenant_id or "global"
})

# Cache invalidation
logger.info("model.default.cache_invalidated", extra={
    "scope": "global",
    "tenant_id": None,
    "reason": "patch_defaults"
})

# Provider alignment
logger.info("provider.model.aligned", extra={
    "provider_id": "ollama-local",
    "old_model": "llama2",
    "new_model": "phi3:mini",
    "action": "updated"
})

# Warmup lifecycle
logger.info("model.warmup.started", extra={
    "model_id": "phi3:mini",
    "timeout": 300
})

logger.info("model.warmup.succeeded", extra={
    "model_id": "phi3:mini",
    "duration_ms": 108234
})

logger.error("model.warmup.failed", extra={
    "model_id": "phi3:mini",
    "error": "timeout",
    "duration_ms": 300000
})
```

---

#### 6.2 Prometheus Metrics

**File**: `src/metrics/prometheus.py`

**New Metrics**:
```python
# Gauge: Current default model name
default_model_name = Gauge(
    "default_model_name",
    "Currently configured default model",
    ["tenant_id"]
)

# Histogram: Model warmup duration
model_warmup_seconds = Histogram(
    "model_warmup_seconds",
    "Time to warm up a model",
    ["model_id", "status"]
)

# Gauge: Provider health status
provider_health_status = Gauge(
    "provider_health_status",
    "Provider health status (1=healthy, 0=unhealthy)",
    ["provider_id", "provider_name"]
)

# Counter: DMR cache hits/misses
dmr_cache_hits = Counter(
    "dmr_cache_hits_total",
    "DMR cache hits",
    ["tenant_id"]
)

dmr_cache_misses = Counter(
    "dmr_cache_misses_total",
    "DMR cache misses",
    ["tenant_id"]
)
```

**Acceptance Criteria**:
- ✅ Grafana dashboard shows current default model
- ✅ Alert if warmup >120s on 2nd+ boot
- ✅ Cache hit rate visible in metrics

---

### ✅ Phase 7: Config Hygiene (Priority: MEDIUM)

#### 7.1 Demote DEFAULT_MODEL_NAME to Fallback

**File**: `src/config.py`

**Changes**:
```python
class Settings(BaseSettings):
    # ... existing fields ...
    
    DEFAULT_MODEL_NAME: str = Field(
        default="phi3:mini",
        description=(
            "EMERGENCY FALLBACK ONLY: Used when DB is unreachable. "
            "Normal operation uses PostgreSQL model_instances table. "
            "This will trigger health degradation and WARN logs."
        )
    )
```

**File**: `src/services/default_model_resolver.py`

```python
async def get_default_model(self, tenant_id: str | None = None):
    # ... Redis check ...
    # ... DB query ...
    
    # Fallback to env var (degraded mode)
    if not default and settings.DEFAULT_MODEL_NAME:
        logger.warning("model.default.env_fallback", extra={
            "model_id": settings.DEFAULT_MODEL_NAME,
            "reason": "db_unreachable",
            "tenant_id": tenant_id or "global"
        })
        
        # Mark health as degraded
        health_mod.set_degraded(reason="default_model_source=env_fallback")
        
        return {
            "model_id": settings.DEFAULT_MODEL_NAME,
            "instance_id": None,
            "provider_id": None,
            "source": "env_fallback"
        }
```

**Acceptance Criteria**:
- ✅ Normal operation never uses env var
- ✅ Health shows `default_model_source=env_fallback` when active
- ✅ Logs contain WARN when fallback used

---

#### 7.2 Startup Readiness Gate

**File**: `src/app.py`

**Changes**:
```python
async def _verify_readiness():
    """Gate readiness on DB + default model resolvable."""
    try:
        # 1. Check DB connection
        db_ok = await health_check_postgres()
        if not db_ok:
            logger.error("readiness.db_unreachable")
            health_mod.set_ready(False)
            return
        
        # 2. Resolve default model
        default = await dmr.get_default_model()
        if not default:
            logger.error("readiness.no_default_model")
            health_mod.set_ready(False)
            return
        
        if default["source"] == "env_fallback":
            logger.warning("readiness.degraded_env_fallback")
            health_mod.set_degraded(reason="env_fallback")
        
        # 3. Mark ready
        health_mod.set_ready(True)
        logger.info("readiness.ready", extra={
            "default_model": default["model_id"],
            "source": default["source"]
        })
        
    except Exception as e:
        logger.error("readiness.check_failed", extra={"error": str(e)})
        health_mod.set_ready(False)

app.add_event_handler("startup", _verify_readiness)
```

**Endpoint**: `/readyz`

```python
@router.get("/readyz")
async def readiness():
    """Kubernetes-style readiness probe."""
    ready = health_mod.is_ready()
    
    if not ready:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "reason": health_mod.get_degradation_reason()
            }
        )
    
    return {"ready": True}
```

**Acceptance Criteria**:
- ✅ `/readyz` returns 503 until DB + default model resolved
- ✅ Deployments don't accept traffic before ready
- ✅ Clear reason in response when not ready

---

### ✅ Phase 8: Test Coverage (Priority: HIGH)

#### 8.1 Integration Test: DB vs Env Var

**File**: `tests/integration/test_default_model_precedence.py`

```python
async def test_db_overrides_env_var():
    """Verify DB default takes precedence over env var."""
    # 1. Set env var to different model
    os.environ["DEFAULT_MODEL_NAME"] = "llama2"
    
    # 2. Set DB default to phi3:mini
    instance = create_instance(
        provider_id=ollama_provider_id,
        instance_name="phi3-test",
        model_id="phi3:mini"
    )
    set_default(instance_id=instance["id"], scope="global")
    
    # 3. Resolve default via DMR
    default = await dmr.get_default_model()
    
    # 4. Verify DB default used (not env var)
    assert default["model_id"] == "phi3:mini"
    assert default["source"] == "db"
    
    # 5. Verify health shows correct model
    health = await client.get("/health")
    assert health["llm"]["model"] == "phi3:mini"
```

---

#### 8.2 Integration Test: PATCH Invalidation

**File**: `tests/integration/test_patch_defaults_invalidation.py`

```python
async def test_patch_invalidates_cache_and_triggers_warmup():
    """Verify PATCH /models/defaults invalidates cache and triggers warmup."""
    # 1. Set initial default
    instance1 = create_instance(model_id="phi3:mini")
    set_default(instance_id=instance1["id"])
    
    # 2. Warm cache
    default1 = await dmr.get_default_model()
    assert default1["model_id"] == "phi3:mini"
    
    # 3. PATCH to new default
    instance2 = create_instance(model_id="llama2")
    response = await client.patch(
        "/v1/models/defaults",
        json={"chat": {"instance_id": instance2["id"]}}
    )
    assert response.status_code == 200
    
    # 4. Verify cache invalidated (next call uses new model)
    default2 = await dmr.get_default_model()
    assert default2["model_id"] == "llama2"
    assert default2["source"] == "db"  # Fresh from DB
    
    # 5. Verify warmup enqueued
    await asyncio.sleep(0.5)
    warmup_logs = get_logs(filter="model.warmup.started")
    assert any("llama2" in log["model_id"] for log in warmup_logs)
    
    # 6. Verify subsequent run uses new model
    run = await client.post("/v1/agent/runs", json={
        "agent_id": "test-agent",
        "input": "hello"
    })
    assert run["model_used"] == "llama2"
```

---

## Environment Variables

### New Config Fields

```bash
# Default Model Resolver
DEFAULT_MODEL_CACHE_TTL_SECONDS=900  # 15 minutes
DEFAULT_MODEL_ALLOW_ENV_FALLBACK=true  # Allow env fallback in emergency

# Model Warmup
LLM_WARMUP_TIMEOUT=300  # 5 minutes for cold starts
LLM_WARMUP_RETRY_MAX=3
LLM_WARMUP_RETRY_DELAY=10

# Provider Health
PROVIDER_HEALTH_REFRESH_INTERVAL=3600  # 1 hour
PROVIDER_HEALTH_TTL=7200  # 2 hours

# Catalog Caching
CATALOG_CACHE_TTL=1800  # 30 minutes
```

---

## Deployment Steps

### 1. Database Migration

```bash
# Generate migration
alembic revision --autogenerate -m "enforce_single_default_constraint"

# Review and apply
alembic upgrade head
```

### 2. Code Deployment

```bash
# Build and deploy
docker compose up -d --build

# Verify DMR working
docker compose logs app | grep "model.default.resolved"
```

### 3. Validation

```bash
# Check health
curl http://localhost:8000/health | jq '.llm.model'

# Verify DB default
docker compose exec postgres psql -U cineca_user -d cineca_platform \
  -c "SELECT instance_name, model_id FROM model_instances WHERE id IN (SELECT instance_id FROM model_defaults WHERE scope='global');"

# Test cache invalidation
curl -X PATCH http://localhost:8000/v1/models/defaults \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"chat": {"instance_id": "new-instance-id"}}'

# Verify new model in use
curl http://localhost:8000/health | jq '.llm.model'
```

---

## Rollback Plan

If issues arise:

1. **Revert Migration**:
   ```bash
   alembic downgrade -1
   ```

2. **Restore Env Var Precedence** (temporary):
   ```python
   # In default_model_resolver.py
   if settings.DEFAULT_MODEL_NAME:
       return {"model_id": settings.DEFAULT_MODEL_NAME, "source": "env"}
   ```

3. **Clear Redis Cache**:
   ```bash
   docker compose exec redis redis-cli DEL models:default
   ```

---

## Success Metrics

After implementation, verify:

- ✅ Zero env var reads for default model in normal operation
- ✅ Cache hit rate >90% after warmup
- ✅ PATCH reflects in <1s on subsequent requests
- ✅ Warmup completes within LLM_WARMUP_TIMEOUT
- ✅ Health shows actual readiness (no false positives)
- ✅ Tool discovery called exactly once per run
- ✅ Provider health never expires during long tests

---

## Next Steps

1. **Review this plan** with team
2. **Create feature branch**: `feature/db-default-model`
3. **Implement Phase 1** (DMR + DB constraint)
4. **Run integration tests**
5. **Deploy to staging**
6. **Monitor metrics for 24h**
7. **Production rollout**

---

**Questions? Issues?**  
Ping @arman or file an issue in the repo.
