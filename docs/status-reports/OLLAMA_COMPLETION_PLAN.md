# Ollama Infrastructure Completion Plan

**Date:** October 13, 2025  
**Status:** Action Plan  
**Context:** Based on master TODO to complete Ollama setup

---

## 🎯 Critical Path (Must Fix First)

### Phase 1: Fix Instance Testing (Blocking Everything)

#### Issue Analysis

The test endpoint `/admin/models/instances/{instance_id}/tests` fails because:

1. **By UUID**: Returns 404 "instance not found"
   - Root cause: Likely UUID parsing issue or cache lookup failure
   - Code location: `src/routers/model_management.py:728` (`instance_test` function)
   - Current flow: `get_instance_by_id(instance_id)` → `_repo.get_instance(instance_id)` → DB query

2. **By name**: Returns 502 "provider not available" with wrong provider
   - Root cause: References `local-llamacpp` instead of registered `ollama-local`
   - The code at line 766 tries: `inst.get("provider") or inst.get("provider_id")`
   - Provider resolution then queries orchestrator's hardcoded `llm_clients`

#### Immediate Fixes Required

**Fix 1: Ensure UUID Lookup Works**
```python
# File: src/routers/model_management.py:730
# Current code tries to fetch instance by ID
inst = get_instance_by_id(instance_id)

# Need to verify:
# 1. instance_id parameter is correctly typed as str (not requiring UUID type hint)
# 2. DB query in model_instance_repo.py:149 handles both UUID and name lookups
# 3. Add comprehensive logging before 404 response
```

**Fix 2: Provider Resolution Must Use Database, Not Orchestrator**
```python
# File: src/routers/model_management.py:766-778
# PROBLEM: Lines 767-768 check orchestrator.llm_clients which has hardcoded providers
provider_name = inst.get("provider") or inst.get("provider_id")
client = getattr(orch, 'llm_clients', {}).get(provider_name) if provider_name else None

# SOLUTION: Skip orchestrator entirely, use provider repository
# Lines 770-783 already do this as fallback - make it primary:
provider_internal = _repo.get_provider_internal(provider_name)
provider_public = _repo.get_provider(provider_name)
```

**Fix 3: Add Comprehensive Tracing**
```python
# Add at start of instance_test function
logger.info(
    "model.instance.test.lookup",
    extra={
        "instance_id": instance_id,
        "instance_id_type": type(instance_id).__name__,
        "lookup_result": "found" if inst else "not_found",
        "instance_provider_id": inst.get("provider_id") if inst else None,
    }
)
```

#### Implementation Steps

1. **Update `get_instance_by_id` to support both UUID and name**
   ```python
   # File: db/postgres_control/repositories/model_instance_repo.py:146
   def get_instance(instance_id: str) -> Optional[Dict[str, Any]]:
       db: Session = next(get_db())
       try:
           # Try UUID first
           try:
               uuid_obj = uuid.UUID(instance_id)
               instance = db.execute(
                   select(ModelInstance).where(ModelInstance.id == uuid_obj)
               ).scalar_one_or_none()
           except ValueError:
               # Fall back to name lookup
               instance = db.execute(
                   select(ModelInstance).where(ModelInstance.instance_name == instance_id)
               ).scalar_one_or_none()
           return _instance_to_dict(instance) if instance else None
       finally:
           db.close()
   ```

2. **Refactor provider resolution to prioritize database**
   ```python
   # File: src/routers/model_management.py:766-790
   # Remove dependency on orchestrator.llm_clients
   # Use _repo.get_provider_internal() and _repo.get_provider() exclusively
   ```

3. **Add cache invalidation on provider mutations**
   ```python
   # File: db/redis_cache/providers_cache.py (create if doesn't exist)
   def invalidate_provider_cache(provider_id: str):
       keys_to_delete = [
           f"providers:by_id:{provider_id}",
           "providers:list:*",
           f"instances:provider:{provider_id}:*",
       ]
       # Delete from Redis
   ```

---

## Phase 2: Database Integrity & Constraints

### Current State
- ✅ Instances table exists with provider_id foreign key
- ⚠️  Unknown if FK has ON DELETE RESTRICT
- ⚠️  Unknown if unique constraint exists on (tenant_id, instance_name)

### Required Migrations

**Migration 1: Add Instance Constraints**
```sql
-- File: db/postgres_control/alembic/versions/XXX_add_instance_constraints.py

-- Add unique constraint
CREATE UNIQUE INDEX IF NOT EXISTS idx_instances_tenant_name 
ON model_instances(tenant_id, instance_name);

-- Ensure FK has proper constraint
ALTER TABLE model_instances
DROP CONSTRAINT IF EXISTS fk_instances_provider;

ALTER TABLE model_instances
ADD CONSTRAINT fk_instances_provider
FOREIGN KEY (provider_id) REFERENCES providers(id)
ON DELETE RESTRICT;
```

**Migration 2: Add Model Defaults Table** (if doesn't exist with tenant support)
```sql
CREATE TABLE IF NOT EXISTS model_defaults (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255),  -- NULL for global
    scope VARCHAR(50) NOT NULL DEFAULT 'global',
    instance_id UUID NOT NULL REFERENCES model_instances(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    etag VARCHAR(64) NOT NULL,
    UNIQUE(tenant_id, scope)
);
```

---

## Phase 3: API Enhancements

### Inline Manifest Staging

**Extend builtins staging endpoint:**
```python
# File: src/routers/manifests.py
# Add to StageRequest schema:
class StageRequest(BaseModel):
    url: Optional[str] = None
    inline: Optional[Dict[str, Any]] = None
    
    @model_validator(mode='after')
    def check_one_source(self):
        if not self.url and not self.inline:
            raise ValueError("Either url or inline manifest required")
        if self.url and self.inline:
            raise ValueError("Provide either url OR inline, not both")
        return self
```

### Tenant-Specific Defaults

**Extend defaults API:**
```python
# File: src/routers/model_management.py
# Update PATCH /admin/models/defaults to accept query param:
@router.patch("/defaults")
async def patch_defaults(
    body: PatchDefaultsBody,
    tenant_id: Optional[str] = Query(None),
    user: UserInfo = Depends(require_perms(["admin:all"]))
):
    # Resolution order: tenant → global → 404
    ...
```

---

## Phase 4: Testing & Validation

### Test Suite Requirements

**1. Instance Test Endpoint**
- ✅ Test by UUID
- ✅ Test by name  
- ✅ Test with deterministic prompts
- ✅ Verify correct provider resolution

**2. Provider Health Check**
```python
# New endpoint: GET /v1/health/providers
# Returns: { "providers": [{"name": "ollama-local", "status": "healthy", ...}] }
```

**3. End-to-End Smoke Tests**
```bash
# Test script: tests/smoke/test_ollama_instances.sh
# For each instance:
#   1. GET instance details
#   2. POST test with "Reply with exactly: OK"
#   3. Verify output == "OK"
#   4. POST test with "12 + 13 = ?"
#   5. Verify output contains "25"
```

---

## Phase 5: Documentation & UX

### User-Facing Documentation

**docs/ollama-models-guide.md:**
```markdown
# Ollama Models Guide

## Available Models

| Model | Size | Best For | Instance Name |
|-------|------|----------|---------------|
| Mistral 7B | 4.4GB | Production, quality responses | mistral-7b |
| Phi-3 Mini | 2.4GB | Development, fast iteration | phi3-mini |
| Qwen 2.5 3B | 2.1GB | NL→Cypher, graph queries | qwen-2.5-3b |
| Llama 3.2 3B | 2.0GB | General purpose, function calling | llama-3.2-3b |

## Selecting a Model

### Default Behavior
If you don't specify a model, the system uses:
- Production tenants: `mistral-7b` (global default)
- Development tenants: `phi3-mini` (tenant default)

### Explicit Selection
```bash
# In tool invocations
POST /v1/tools/nl-to-cypher/invocations
{
  "instance_id": "qwen-2.5-3b",
  "input": "Find users in the Biodiversity domain"
}
```
```

---

## 📋 Acceptance Checklist (Final)

Before marking complete, verify:

- [ ] **Provider Resolution**
  - [ ] Test by UUID returns 200
  - [ ] Test by name returns 200  
  - [ ] Provider traced in logs as `ollama-local`
  - [ ] No references to `local-llamacpp`

- [ ] **Database Integrity**
  - [ ] FK constraints prevent orphaned instances
  - [ ] Unique constraint prevents duplicate names per tenant
  - [ ] Tenant-specific defaults work

- [ ] **API Completeness**
  - [ ] Inline manifest staging works
  - [ ] Health check endpoint exists
  - [ ] Instance selection in tools works

- [ ] **Smoke Tests Pass**
  - [ ] All 4 instances return 200 on test
  - [ ] Deterministic prompts return expected outputs
  - [ ] Latency is reasonable (<2s for simple prompts)

- [ ] **Documentation**
  - [ ] User guide published
  - [ ] API examples updated
  - [ ] Troubleshooting section added

---

## 🚀 Execution Order

1. **Immediate** (hours): Fix provider resolution bug
2. **Same day**: Add database constraints
3. **Next sprint**: Inline manifests, tenant defaults
4. **Ongoing**: Comprehensive testing, documentation

---

## 📞 Support & Troubleshooting

### Debug Commands

```bash
# Check instance in DB
psql -d cineca_agentic_platform -c "SELECT id, instance_name, provider_id, enabled, loaded FROM model_instances;"

# Check provider registration
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/models/providers | jq '.items[] | {name, base_url}'

# Test Ollama directly
curl -X POST http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mistral:7b-instruct","messages":[{"role":"user","content":"test"}],"max_tokens":10}'

# Check logs for test attempts
docker logs cineca-agentic-platform-api-1 | grep "model.instance.test"
```

### Common Issues

**Issue**: 404 on instance test
**Solution**: Check UUID format, verify instance exists in DB, check logs for parsing errors

**Issue**: 502 with wrong provider
**Solution**: Clear Redis cache, restart API service, verify provider_id in instance record

**Issue**: Ollama connection refused
**Solution**: Verify Ollama container running, check `host.docker.internal` resolution

---

## Next Steps

Based on current status (from OLLAMA_SETUP_SUMMARY.md), the immediate priority is:

1. ✅ Fix the provider resolution bug in test endpoint
2. ✅ Verify UUID lookup works correctly
3. ✅ Add comprehensive logging
4. Test all 4 instances successfully
5. Mark project as complete

Estimated time to complete critical path: **2-4 hours**
