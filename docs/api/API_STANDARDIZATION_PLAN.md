# API Standardization & Polish Plan

**Date**: October 13, 2025  
**Status**: Implementation Plan  
**Priority**: High - Production Readiness

---

## Executive Summary

This document outlines a comprehensive plan to standardize and polish all admin APIs (Tenants, Providers, Manifests, Instances, Tests) for production readiness. The plan addresses response format inconsistencies, ETag behavior, cache invalidation, RBAC enforcement, and documentation alignment.

---

## Current State Analysis

### Response Format Inconsistencies ❌

| Endpoint | Current Format | Status |
|----------|---------------|---------|
| `/admin/tenants` | `{items, total, next_page_token}` | ✅ Correct |
| `/admin/models/providers` | `{items, total, next_page_token}` | ✅ Correct |
| `/admin/models/manifests/builtins` | `{manifests, count, etag}` | ❌ Inconsistent |
| `/admin/models/instances` | `{instances, count, etag, next_page_token}` | ❌ Inconsistent |

**Target Format**: `{items, total, etag?, next_page_token?}`

### Known Issues

1. **Providers**: `demo-openai` provider keeps reappearing, some providers use `tenant_id="global"` instead of `null`
2. **Manifests**: Missing pagination, no pruning mechanism for archived entries
3. **Instances**: No cache invalidation on mutations, inconsistent schema (context_window in two places)
4. **Tests**: Non-deterministic outputs, missing observability fields
5. **Documentation**: Examples don't match actual response shapes

---

## Implementation Plan

### Phase 1: Critical Fixes (Priority 1)

#### 1.1 Standardize List Response Formats

**Goal**: All list endpoints return `{items, total, etag?, next_page_token?}`

**Changes Required**:

**File**: `src/routers/manifests.py`
```python
# BEFORE
class ListBuiltinsResponse(BaseModel):
    manifests: List[Dict[str, Any]]
    count: int
    etag: str

# AFTER
class ListBuiltinsResponse(BaseModel):
    items: List[Dict[str, Any]] = Field(..., alias="manifests")  # Back-compat
    total: int = Field(..., alias="count")  # Back-compat
    etag: str
    next_page_token: Optional[str] = None
```

**File**: `src/routers/model_instances.py`
```python
# BEFORE
class ListInstancesResponse(BaseModel):
    instances: List[Dict[str, Any]]
    count: int
    etag: str
    next_page_token: Optional[str] = None

# AFTER
class ListInstancesResponse(BaseModel):
    items: List[Dict[str, Any]] = Field(..., alias="instances")  # Back-compat
    total: int = Field(..., alias="count")  # Back-compat
    etag: str
    next_page_token: Optional[str] = None
```

**Migration Strategy**:
- Use Pydantic `alias` for backward compatibility
- Add `x-deprecated` annotations in OpenAPI for old field names
- Document migration in CHANGELOG with deprecation timeline (v2.0.0)

---

#### 1.2 Fix Provider tenant_id Validation

**Goal**: Prevent `tenant_id="global"`, enforce `null` for global scope

**File**: `db/postgres_control/repositories/provider_repo.py`

Add validation in `create_provider()` and `update_provider()`:
```python
def _validate_tenant_id(tenant_id: Optional[str]) -> Optional[str]:
    """Validate and normalize tenant_id."""
    if tenant_id == "global":
        raise ValueError("tenant_id cannot be 'global'; use null for global scope")
    return tenant_id
```

**Migration SQL**:
```sql
-- Update existing providers
UPDATE providers 
SET tenant_id = NULL 
WHERE tenant_id = 'global';

-- Add check constraint
ALTER TABLE providers 
ADD CONSTRAINT chk_tenant_id_not_global 
CHECK (tenant_id != 'global' OR tenant_id IS NULL);
```

---

#### 1.3 Prevent demo-openai Recreation

**Investigation Needed**:
- Check initialization scripts in `ops/builtins/` or `scripts/`
- Check if seeding happens on container startup
- Add `.gitignore` or persistent volume to prevent re-seeding

**Immediate Fix**:
```bash
# Add to docker-entrypoint.sh or initialization
if [ "$SEED_DEMO_DATA" != "true" ]; then
  echo "Skipping demo data seeding"
  exit 0
fi
```

---

#### 1.4 Test Endpoint Determinism

**Goal**: Make test outputs predictable and concise

**File**: `src/routers/model_instances.py` (in `test_instance()` function)

```python
# BEFORE
test_params = {
    "temperature": payload.temperature or 0.7,
    "max_tokens": payload.max_tokens or 512,
}

# AFTER (deterministic mode)
test_params = {
    "temperature": payload.temperature if payload.temperature is not None else 0.0,  # Force deterministic
    "max_tokens": min(payload.max_tokens or 64, 64),  # Cap at 64 for tests
    "stop": ["\n\n", "```", "---"],  # Prevent code dumps
}
```

**Response Enhancement**:
```python
class TestInstanceResponse(BaseModel):
    ok: bool = True
    response: str
    provider: str = Field(..., description="Provider used")
    model_ref: str = Field(..., description="Model identifier")
    latency_ms: int = Field(..., description="Request latency")
    trace_id: str = Field(..., description="Trace ID for correlation")
    parameters: Dict[str, Any] = Field(..., description="Actual parameters used")
```

---

### Phase 2: Cache & ETag Improvements (Priority 2)

#### 2.1 Instance Cache Invalidation

**Goal**: Invalidate Redis cache on instance mutations

**File**: `db/postgres_control/repositories/model_instance_repo.py`

Add invalidation functions:
```python
def _redis_invalidate_instance(instance_id: str) -> None:
    """Invalidate cached instance data."""
    if not redis_available():
        return
    
    try:
        redis = get_redis()
        # Invalidate specific instance
        redis.delete(f"instance:{instance_id}")
        # Invalidate list caches
        redis.delete("instances:list:*")
        redis.delete("instances:etag")
        logger.debug(f"Invalidated cache for instance {instance_id}")
    except Exception as exc:
        logger.warning(f"Cache invalidation failed: {exc}")

def _redis_invalidate_all_instances() -> None:
    """Invalidate all instance caches."""
    if not redis_available():
        return
    
    try:
        redis = get_redis()
        pattern = "instance:*"
        for key in redis.scan_iter(match=pattern):
            redis.delete(key)
        redis.delete("instances:*")
        logger.debug("Invalidated all instance caches")
    except Exception as exc:
        logger.warning(f"Cache invalidation failed: {exc}")
```

Call in mutations:
- `load_instance()` → `_redis_invalidate_all_instances()`
- `update_instance()` → `_redis_invalidate_instance(instance_id)` + list
- `delete_instance()` → `_redis_invalidate_instance(instance_id)` + list

---

#### 2.2 Comprehensive ETag Tests

**File**: `tests/integration/test_etag_behavior.py` (new)

```python
import pytest
from httpx import AsyncClient

class TestETagBehavior:
    """Test ETag and 304 behavior across all list endpoints."""
    
    @pytest.mark.asyncio
    async def test_tenants_etag_roundtrip(self, client: AsyncClient, admin_token):
        """Test tenants ETag: GET -> ETag -> GET with If-None-Match -> 304"""
        # First GET
        resp1 = await client.get("/v1/admin/tenants", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp1.status_code == 200
        etag1 = resp1.headers.get("etag")
        assert etag1 is not None
        
        # Second GET with If-None-Match
        resp2 = await client.get(
            "/v1/admin/tenants",
            headers={"Authorization": f"Bearer {admin_token}", "If-None-Match": etag1}
        )
        assert resp2.status_code == 304
        
        # Mutate (PATCH tenant)
        resp3 = await client.patch(
            "/v1/admin/tenants/tenant-67e5ca68",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"metadata": {"updated": True}}
        )
        assert resp3.status_code == 200
        
        # GET again - should return 200 with new ETag
        resp4 = await client.get(
            "/v1/admin/tenants",
            headers={"Authorization": f"Bearer {admin_token}", "If-None-Match": etag1}
        )
        assert resp4.status_code == 200
        etag2 = resp4.headers.get("etag")
        assert etag2 != etag1
    
    # Similar tests for providers, instances, manifests...
```

---

#### 2.3 Pagination Tests

**File**: `tests/integration/test_pagination.py` (new)

```python
@pytest.mark.asyncio
async def test_tenants_pagination(self, client: AsyncClient, admin_token):
    """Test pagination with >100 tenants."""
    # Seed 150 tenants
    for i in range(150):
        await client.post(
            "/v1/admin/tenants",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": f"Tenant {i}", "admin_email": f"admin{i}@example.com"}
        )
    
    # GET page 1
    resp1 = await client.get("/v1/admin/tenants?page_size=100", headers={"Authorization": f"Bearer {admin_token}"})
    data1 = resp1.json()
    assert len(data1["items"]) == 100
    assert data1["next_page_token"] is not None
    
    # GET page 2
    resp2 = await client.get(
        f"/v1/admin/tenants?page_size=100&page_token={data1['next_page_token']}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    data2 = resp2.json()
    assert len(data2["items"]) == 50
    assert data2["next_page_token"] is None
    
    # Verify Link header
    assert "Link" in resp1.headers
    assert "rel=\"next\"" in resp1.headers["Link"]
```

---

### Phase 3: Schema & Validation (Priority 2)

#### 3.1 Instance Schema Normalization

**Goal**: `context_window` in one place only (parameters)

**File**: `db/postgres_control/models.py`

```python
# Remove top-level context_window column (migration required)
class ModelInstance(Base):
    __tablename__ = "model_instances"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ... other fields ...
    # context_window = Column(Integer, nullable=True)  # REMOVE THIS
    parameters = Column(JSONB, nullable=True, default={})  # Keep context_window here
```

**Migration**:
```sql
-- Migrate data
UPDATE model_instances
SET parameters = jsonb_set(
    COALESCE(parameters, '{}'::jsonb),
    '{context_window}',
    to_jsonb(context_window)
)
WHERE context_window IS NOT NULL AND (parameters->>'context_window') IS NULL;

-- Drop column
ALTER TABLE model_instances DROP COLUMN context_window;
```

---

#### 3.2 Provider FK Integrity

**Goal**: Prevent provider deletion if instances exist

**File**: `src/routers/model_management.py` (or provider router)

Add pre-delete check:
```python
@router.delete('/providers/{provider_id}', ...)
async def delete_provider(provider_id: str, ...):
    # Check for dependent instances
    instances = model_instance_repo.list_instances(provider_id=provider_id)
    if instances:
        instance_names = [inst["instance_name"] for inst in instances[:5]]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "type": "about:blank",
                "title": "Provider In Use",
                "detail": f"Cannot delete provider {provider_id}; {len(instances)} instance(s) depend on it",
                "blocking_instances": instance_names,
            }
        )
    
    # Proceed with deletion
    ...
```

---

### Phase 4: Observability & Features (Priority 3)

#### 4.1 Manifest Filtering & Pruning

**File**: `src/routers/manifests.py`

Add query parameters:
```python
@router.get("/builtins", ...)
async def list_builtins(
    state: Optional[str] = Query(None, regex="^(active|staged|archived)$"),
    limit: int = Query(100, ge=1, le=1000),
    ...
):
    manifests, etag = manifest_repo.list_builtins(state=state, limit=limit)
    ...
```

Add pruning endpoint:
```python
@router.delete(
    "/builtins/archived",
    response_model=Dict[str, Any],
    summary="Prune archived manifests",
    description="Delete archived manifests, keeping N most recent",
)
async def prune_archived(
    keep: int = Query(10, ge=0, le=100, description="Number of archived to keep"),
    user: UserInfo = Depends(get_current_user),
    _: None = Depends(require_perms("admin:all")),
):
    deleted_count = manifest_repo.prune_archived(keep=keep)
    return {"ok": True, "deleted": deleted_count, "kept": keep}
```

---

#### 4.2 Provider Health Endpoint

**File**: `src/routers/health.py` or `src/routers/health_v2.py`

```python
@router.get("/providers", response_model=Dict[str, Any])
async def check_providers():
    """Ping all providers and return health status."""
    providers = provider_repo.list_providers()
    results = {}
    
    for provider in providers:
        try:
            # Ping with minimal request
            start = time.time()
            response = await httpx.post(
                f"{provider['base_url']}/chat/completions",
                json={
                    "model": provider.get("model", "gpt-3.5-turbo"),
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=5.0,
            )
            latency = int((time.time() - start) * 1000)
            
            results[provider["id"]] = {
                "status": "healthy" if response.status_code == 200 else "degraded",
                "latency_ms": latency,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            results[provider["id"]] = {
                "status": "unhealthy",
                "error": str(exc),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
    
    return {"providers": results}
```

**Populate in list**:
Cache health results in Redis with 5-minute TTL, include in provider list response.

---

### Phase 5: Documentation & OpenAPI (Priority 3)

#### 5.1 Update OpenAPI Spec

**Files**: `api/openapi.json`, `api/openapi_v1.json`, `api/openapi_v2.json`

Regenerate from FastAPI:
```bash
python -c "from src.app import app; import json; print(json.dumps(app.openapi(), indent=2))" > api/openapi.json
```

Verify schemas match actual responses.

---

#### 5.2 Update Inline Documentation

**Files to Update**:
- `docs/getting-started.md`
- `docs/configuration.md`
- `README.md`

**Key Updates**:
- Replace all examples with `{items, total}` format
- Add ETag usage examples (`If-None-Match` → 304)
- Document manifest behavior: "One active manifest contains N models"
- Update pagination examples with `next_page_token`

---

### Phase 6: RBAC & Security (Priority 1-2)

#### 6.1 RBAC Test Coverage

**File**: `tests/security/test_admin_endpoints_rbac.py` (new)

```python
@pytest.mark.asyncio
async def test_tenants_requires_admin(self, client: AsyncClient, user_token):
    """Non-admin user cannot list tenants."""
    resp = await client.get("/v1/admin/tenants", headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 403
    data = resp.json()
    assert data["title"] == "Forbidden"

@pytest.mark.asyncio
async def test_providers_requires_admin(self, client: AsyncClient, user_token):
    """Non-admin user cannot list providers."""
    resp = await client.get("/v1/admin/models/providers", headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 403

# Similar for manifests, instance mutations...
```

---

#### 6.2 Token Safety Audit

**File**: `src/middleware/logging.py` (check existing)

Verify:
- `Authorization` header is redacted in access logs
- Tokens never appear in exception messages
- Audit logs use `user.sub` not raw tokens

---

## Acceptance Criteria

### Checklist for Production Sign-Off

- [ ] **Response Formats**: All list endpoints use `{items, total, etag?, next_page_token?}`
- [ ] **Provider Validation**: `tenant_id` cannot be `"global"`, must be `null`
- [ ] **Demo Data**: `demo-openai` does not reappear on restart
- [ ] **Test Determinism**: Test outputs are <64 tokens, temperature=0, include observability fields
- [ ] **Cache Invalidation**: Instance mutations invalidate Redis cache
- [ ] **ETag Behavior**: 304 responses work correctly, ETags change after mutations
- [ ] **Pagination**: `next_page_token` works, `Link` header present
- [ ] **Schema Consistency**: `context_window` in parameters only
- [ ] **FK Integrity**: Cannot delete provider with dependent instances
- [ ] **RBAC**: Non-admin users get 403 on admin endpoints
- [ ] **Documentation**: Examples match actual response shapes
- [ ] **Manifest Behavior**: Documented that one active manifest contains N models

---

## Implementation Timeline

| Phase | Effort | Dependencies | Priority |
|-------|--------|--------------|----------|
| Phase 1: Critical Fixes | 2-3 days | None | P0 |
| Phase 2: Cache & ETag | 2 days | Phase 1 | P1 |
| Phase 3: Schema & Validation | 1-2 days | Phase 1 | P1 |
| Phase 4: Observability | 1 day | Phase 1 | P2 |
| Phase 5: Documentation | 1 day | All phases | P2 |
| Phase 6: RBAC & Security | 1 day | None | P1 |

**Total Estimated Effort**: 8-10 days

---

## Rollout Strategy

### Step 1: Develop & Test Locally
- Implement Phase 1 fixes
- Run comprehensive test suite
- Validate ETag behavior manually

### Step 2: Deploy to Staging
- Deploy with feature flags for response format changes
- Run acceptance tests
- Monitor for errors

### Step 3: Gradual Production Rollout
- Enable response format aliases (backward compatible)
- Monitor metrics (error rate, latency)
- Communicate deprecation timeline to API consumers

### Step 4: Deprecation & Cleanup
- Version 2.0.0: Remove old field names
- Update all documentation
- Final validation

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking changes in response format | High | Use Pydantic aliases for backward compatibility |
| Cache invalidation bugs | Medium | Comprehensive testing, gradual rollout |
| Database migrations fail | High | Test migrations on staging, have rollback plan |
| Performance regression | Medium | Monitor latency metrics, optimize queries |
| Documentation drift | Low | Automate OpenAPI generation, review PRs |

---

## Monitoring & Success Metrics

### Metrics to Track

1. **API Response Times**: P50, P95, P99 for all list endpoints
2. **Cache Hit Rate**: Redis cache effectiveness after invalidation
3. **Error Rate**: 4xx and 5xx responses by endpoint
4. **ETag Usage**: % of 304 responses vs 200
5. **Test Determinism**: Variance in test output lengths

### Alerts

- Error rate > 1% for any admin endpoint
- P95 latency > 500ms for list endpoints
- Cache hit rate < 80%

---

## Next Steps

1. **Review**: Get stakeholder approval on plan
2. **Prioritize**: Confirm phase priorities and timeline
3. **Implement**: Start with Phase 1 (Critical Fixes)
4. **Test**: Run comprehensive test suite after each phase
5. **Document**: Update docs incrementally as features are implemented
6. **Deploy**: Follow rollout strategy with gradual release

---

**Document Version**: 1.0  
**Last Updated**: October 13, 2025  
**Author**: GitHub Copilot (Agentic Platform Team)  
**Reviewed By**: [Pending]  
**Approved For Implementation**: [Pending]
