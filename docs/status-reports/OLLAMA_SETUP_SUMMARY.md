# Ollama Model Infrastructure Setup - Summary

**Date:** October 13, 2025  
**Status:** ⚠️  PARTIALLY COMPLETE (Instances created but testing failed)

---

## ✅ Completed Tasks

### 1. Environment Setup
- ✅ Admin token exported and verified
- ✅ API access confirmed (v1 endpoints)

### 2. Tenants Configuration
- ✅ 3 tenants configured (4 total exist, 1 test tenant has dependencies and couldn't be deleted):
  - **Global** (`tenant-67e5ca68`) - env: platform
  - **Development** (`tenant-7456e4e0`) - env: dev  
  - **CINECA Biodiversity BLAST (Prod)** (`tenant-8ec78fbf`) - env: prod
  - ⚠️ **Cineca Test** (`tenant-f224ee23`) - has dependencies, kept

### 3. Provider Registration
- ✅ Registered **ollama-local** provider
  - Type: `openai_compatible`
  - Base URL: `http://host.docker.internal:11434/v1`
  - Tenant: `null` (global)
  - Status: Active

### 4. Model Instances Created (4 total)
All instances created successfully with global scope:

| Instance Name | Provider | Model ID | Temperature | Max Tokens | Context Window | ID |
|--------------|----------|----------|-------------|------------|----------------|-----|
| `mistral-7b` | ollama-local | mistral:7b-instruct | 0.3 | 2048 | 8192 | b6404706-8e96-48ab-b6f2-8f796ec64b5e |
| `phi3-mini` | ollama-local | phi3:mini-instruct | 0.2 | 1024 | 4096 | f1813b48-f16a-410f-824f-c8d07329c045 |
| `qwen-2.5-3b` | ollama-local | qwen2.5:3b-instruct | 0.3 | 2048 | 8192 | 60e4142c-f32b-44b9-889c-f07df76a55cb |
| `llama-3.2-3b` | ollama-local | llama3.2:3b-instruct | 0.3 | 2048 | 8192 | 6491b020-bbe3-47fe-991e-e7c21a15260c |

All instances show `enabled: true` and `loaded: true`.

### 5. Default Model Configuration
- ✅ Global default set to `mistral-7b`
- Instance ID: `b6404706-8e96-48ab-b6f2-8f796ec64b5e`
- Provider: `ollama-local`
- Model: `mistral:7b-instruct`

---

## ⚠️ Issues Encountered

### 1. Manifest Staging Skipped
**Issue:** The manifest staging endpoint (`/v1/admin/models/manifests/builtins/staged`) requires HTTPS URLs only.

**Impact:** Could not stage model manifests via the builtins flow. Created instances directly instead.

**Workaround:** Created model instances directly via `/v1/admin/models/instances` endpoint, bypassing manifest staging.

### 2. Testing Endpoint Issues
**Issue:** When testing instances via `/v1/admin/models/instances/{instance_id}/tests`:
- By UUID: Returns `404 instance not found`
- By name: Returns `502 provider not available` and mentions `local-llamacpp` instead of `ollama-local`

**Diagnosis:** The platform appears to have hardcoded or cached provider references to `local-llamacpp` that conflict with our `ollama-local` provider.

**Verification:** Direct Ollama API calls work correctly:
```bash
curl -X POST http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mistral:7b-instruct","messages":[{"role":"user","content":"test"}]}'
# Returns valid response
```

### 3. Tenant-Specific Defaults
**Issue:** The `/v1/admin/models/defaults` API doesn't support tenant-specific defaults (no `tenant_id` parameter).

**Impact:** Cannot set different defaults for Development vs Production tenants as requested in requirements.

**Current State:** Only global default is set.

---

## 🔧 Verification Commands

### List Tenants
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/tenants | jq '.items[] | {name, env: .metadata.env}'
```

### List Providers
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/models/providers | jq '.items[]'
```

### List Instances
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/models/instances | jq '.instances[] | {instance_name, provider_id, model_id, enabled, loaded}'
```

### Get Default
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/models/defaults | jq '.chat'
```

### Test Ollama Directly
```bash
curl -X POST http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral:7b-instruct",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'
```

---

## 📋 Acceptance Checklist Status

| Requirement | Status | Notes |
|------------|--------|-------|
| 3 clean tenants | ⚠️  Partial | 3 main tenants correct, 1 test tenant couldn't be deleted |
| 1 Ollama provider | ✅ Complete | `ollama-local` registered globally |
| 4 model manifests | ⚠️ Skipped | HTTPS requirement blocked staging |
| 4 model instances | ✅ Complete | All 4 created and showing as loaded |
| Global default set | ✅ Complete | Mistral-7b set as default |
| Tenant defaults | ❌ Not Available | API doesn't support tenant-specific defaults |
| Instance tests pass | ❌ Failed | 404/502 errors, provider mismatch issue |

---

## 🚀 Next Steps / Recommendations

1. **Investigate Provider Resolution**
   - Debug why tests reference `local-llamacpp` instead of `ollama-local`
   - Check for cached/hardcoded provider references
   - Review instance-to-provider mapping logic

2. **Fix Testing Flow**
   - Resolve UUID vs name lookup issues
   - Ensure instances properly resolve to registered providers
   - Consider restarting services to clear any caches

3. **Manifest Staging (Future)**
   - Set up HTTPS endpoint or local certificate for manifest serving
   - Or extend API to accept manifest content directly (not just URL)
   - Create proper manifest files for the 4 models

4. **Tenant-Specific Defaults (Future)**
   - Extend defaults API to support `tenant_id` parameter
   - Or use tenant metadata for storing tenant-specific preferences

5. **Cleanup**
   - Investigate and resolve `tenant-f224ee23` dependencies
   - Consider deleting once dependencies are cleared

---

## 📊 Available Ollama Models

```
mistral:7b-instruct       (4.4 GB)
phi3:mini-instruct        (2.4 GB)
qwen2.5:3b-instruct       (2.1 GB)
llama3.2:3b-instruct      (2.0 GB)
```

All models verified accessible via Ollama API on `localhost:11434`.

---

## 🔗 Related Documentation

- Provider API: `/docs` → Models → Providers
- Instances API: `/docs` → Models → Instances  
- Manifests API: `/docs` → Models → Manifests
- Ollama docs: `docs/ollama.md`
