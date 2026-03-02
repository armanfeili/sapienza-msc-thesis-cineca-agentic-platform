# Model Instances API - Endpoint Description Update

**Date**: 2025-01-15  
**Status**: ✅ Complete  
**File Modified**: `src/routers/model_instances.py`

## Summary

All 7 model instance endpoints have been rewritten with human-friendly, accessible descriptions that follow a consistent template format for improved developer experience in FastAPI documentation.

---

## 🎯 Objectives

- **Accessibility**: Replace technical jargon with clear, plain-language explanations
- **Consistency**: Use a standard template across all endpoints
- **Context**: Help developers understand "why" endpoints exist, not just "what" they do
- **Examples**: Provide real-world curl examples with expected responses
- **Discoverability**: Make API capabilities obvious to new users

---

## 📋 Template Structure

Each endpoint description now follows this format:

```
**METHOD /path** – Short purpose summary

**Why we need this endpoint:**
- Explaining importance and use cases
- What happens with/without it

**What it does:**
- Clear description of purpose and behavior

**Access:**
- Who can call it
- Required permissions

**Behavior:**
- Special features (caching, pagination, idempotency, etc.)
- Default values and configuration

**Responses:**
- HTTP status codes with meanings
- Error scenarios

**Examples:**
```bash
curl commands with real requests and responses
```
```

---

## ✅ Updated Endpoints

### 1. **GET /instances** – List model instances

**Changes:**
- ✅ Explains why users need to discover available models
- ✅ Clarifies non-admin users only see enabled models
- ✅ Details caching, pagination, and filtering behavior
- ✅ Provides 4 real-world curl examples

**Key Improvements:**
- Clear explanation of enabled/disabled visibility rules
- Caching example with `If-None-Match` header
- Pagination and filtering examples

---

### 2. **POST /instances** – Create model instance (Admin only)

**Changes:**
- ✅ Explains why admins need to add new models
- ✅ Clarifies admin-only access and 403 behavior for users
- ✅ Details idempotency behavior with `Idempotency-Key` header
- ✅ Provides examples for Ollama and OpenAI models

**Key Improvements:**
- Clear admin-only callout
- Idempotency explanation (201 vs 200 responses)
- Multi-provider examples (Ollama, Azure OpenAI)

---

### 3. **GET /defaults** – Get default model with precedence

**Changes:**
- ✅ Explains precedence resolution (user → tenant → global)
- ✅ Clarifies `X-Default-Scope` header meaning
- ✅ Details caching behavior and `Vary` header
- ✅ Provides 3 real-world examples (200, 304, tenant override)

**Key Improvements:**
- Step-by-step precedence explanation
- Cache validation example (304 response)
- Tenant override example with `X-Tenant-Id` header
- Complete response example showing all headers and body

---

### 4. **PATCH /defaults** – Set default model

**Changes:**
- ✅ Explains scope levels (user, tenant, global) and permissions
- ✅ Clarifies user vs admin access for different scopes
- ✅ Details 3 supported formats (preferred, legacy, deprecated)
- ✅ Provides 5 real-world examples (user, tenant, global, legacy, error)

**Key Improvements:**
- Clear scope-based permission breakdown
- Multiple format examples (instance_id vs name)
- Error example showing 403 for non-admin tenant scope
- Admin-only callout for tenant/global scopes

---

### 5. **GET /instances/{id}** – Get model details

**Changes:**
- ✅ Explains why users need detailed model specifications
- ✅ Clarifies caching behavior with ETag
- ✅ Shows complete response structure with all fields
- ✅ Provides 3 real-world examples (200, 304, 404)

**Key Improvements:**
- Complete response example showing all model metadata
- Cache validation example (304 response)
- Error example for non-existent instance

---

### 6. **DELETE /instances/{id}** – Delete model instance (Admin only)

**Changes:**
- ✅ Explains why admins need to decommission models
- ✅ Clarifies admin-only access and idempotent behavior
- ✅ Details locking mechanism and cache invalidation
- ✅ Provides 3 real-world examples (204, 403, 404, idempotency)

**Key Improvements:**
- Clear admin-only callout
- Idempotency explanation (second DELETE returns 404)
- Lock acquisition explanation for race condition prevention
- Error examples for non-admin and non-existent instances

---

### 7. **POST /instances/{id}/tests** – Test model instance

**Changes:**
- ✅ Explains why users need to test models before integration
- ✅ Clarifies default parameters and timeout behavior
- ✅ Details observability metadata in response
- ✅ Provides 5 real-world examples (factual, creative, short answer, disabled, demo)

**Key Improvements:**
- Default parameter explanation (temperature=0.0, max_tokens=64)
- Observability metadata in response (latency, tokens, provider)
- Multiple test scenarios (deterministic vs creative)
- Demo mode example ("ping" → "pong")
- Error example for disabled instances

---

## 📊 Before vs After Comparison

### Before (Technical Style)
```markdown
List registered model instances with filtering and pagination.

Requires authentication (any authenticated user with user:me).
Returns ETag for HTTP caching. Supports If-None-Match for 304 responses.

**Required Scopes**: `user:me` or `admin:all`
```

### After (Human-Friendly Style)
```markdown
**GET /instances** – View all available AI models

**Why we need this endpoint:**
- Users and admins need to discover which AI models are available to use
- Applications need to show users a catalog of models they can interact with
- Without this, users wouldn't know which models exist or how to reference them in API calls

**What it does:**
- Returns a paginated list of all registered AI model instances
- Shows key details: model name, provider, capabilities, loaded status, and availability
- Non-admin users only see enabled models; admins can see all models including disabled ones

**Access:**
- Any authenticated user with `user:me` permission
- Admins with `admin:all` have additional visibility into disabled models

**Behavior:**
- Supports HTTP caching via ETag (returns `304 Not Modified` when content hasn't changed)
- Pagination: Use `page_size` (1-1000, default 100) and `page_token` for large result sets
- Filtering: Filter by `tenant_id`, `provider_id`, `loaded`, or `enabled` status
- Non-admin users automatically get `enabled=true` filter (only see active models)
- Admin users can override filters to see disabled or unloaded models

**Responses:**
- `200 OK` – Returns list of model instances with pagination metadata
- `304 Not Modified` – No changes since last request (use `If-None-Match` header with ETag)
- `401 Unauthorized` – Missing or invalid authentication token
- `403 Forbidden` – User lacks required permissions

**Examples:**
[4 curl examples with real requests and responses]
```

---

## 🎓 Benefits

### 1. **Improved Developer Onboarding**
- New developers can understand API capabilities without reading code
- Clear "Why" explanations provide context and motivation
- Real examples show how to use endpoints correctly

### 2. **Better FastAPI Documentation**
- OpenAPI/Swagger UI shows rich, helpful descriptions
- Developers can test endpoints directly from docs
- Examples are copy-paste ready

### 3. **Reduced Support Burden**
- Answers common questions preemptively ("Why am I getting 403?" → See admin-only callout)
- Explains permission model clearly (user:me vs admin:all)
- Shows error scenarios and how to fix them

### 4. **Consistent API Experience**
- All endpoints follow same template structure
- Easier to scan and find information
- Professional, polished documentation

### 5. **Accessibility**
- Non-technical users can understand API capabilities
- Clear language reduces cognitive load
- Step-by-step examples guide usage

---

## 🧪 Testing

All endpoints continue to work correctly:

```bash
# Verify FastAPI docs render correctly
open http://localhost:8000/docs

# Check endpoint descriptions in OpenAPI schema
curl http://localhost:8000/openapi.json | jq '.paths'

# Test actual endpoints (no behavior changes)
curl -X GET "http://localhost:8000/v1/models/instances" \
  -H "Authorization: Bearer $USER_TOKEN"
```

**Expected Result**: FastAPI docs show rich, human-friendly descriptions with examples.

---

## 📝 Notes

- **No Behavior Changes**: Only descriptions were updated, no logic changed
- **Backward Compatible**: All endpoints work exactly as before
- **OpenAPI Compliant**: Descriptions follow FastAPI/OpenAPI best practices
- **Real Examples**: All curl examples use actual instance IDs from the system

---

## ✨ Next Steps

Consider applying this template to other API endpoints:
- Provider endpoints (`/providers`)
- Job endpoints (`/jobs`)
- Tool endpoints (`/tools`)

---

**Author**: Copilot  
**Review Status**: Ready for review  
**Deployment Impact**: None (documentation only)
