# Providers API Refactoring Plan

## Status: In Progress

This document tracks the implementation of the comprehensive providers API improvements based on the TODO checklist.

---

## ✅ Completed

### 1. Schemas & Validation (Partial)
- [x] Created `src/schemas/providers.py` with canonical models:
  - `Provider` - Canonical response model
  - `ProviderListResponse` - Paginated list response
  - `RegisterProviderRequest` - Registration request with validation
  - `UpdateProviderRequest` - Update request
  - `SetDefaultProviderRequest` - Set default request
  - `ActionResponse` - Generic action response
  - `GetMainProviderResponse` - Main provider response
  - `ProblemDetails` - RFC 7807 error model
  - `ProviderType` enum - `openai_compatible | custom`
  - `ProviderHealth` - Health status model
  
- [x] Added field validation:
  - `base_url` required for `openai_compatible` type
  - URL normalization (strip trailing slashes)
  - Field length constraints
  - Extra fields forbidden via `ConfigDict(extra="forbid")`

### 2. List Endpoint (`GET /providers`)
- [x] Return type: `ProviderListResponse` with `{items, next_page_token, total}`
- [x] Pagination: page_size (1-1000), page_token
- [x] ETag/If-None-Match caching → 304 Not Modified
- [x] Link header (RFC 5988) for next page
- [x] Secret redaction with `has_api_key` boolean
- [x] Health status included (non-blocking)

---

## 🚧 In Progress

### 3. RBAC & Access Control
**Current State**: Admin endpoints use `require_perms(["admin:all"])`

**TODO**:
- [ ] Verify 403 Forbidden for non-admin on all admin endpoints
- [ ] Optional: Create `/v1/models/providers` (non-admin, redacted)
- [ ] Test with admin vs non-admin tokens

### 4. Register Endpoint (`POST /providers/register`)
**Current State**: Uses old `RegisterLLMRequest`, needs update

**TODO**:
- [ ] Update to use `RegisterProviderRequest` schema
- [ ] Implement idempotency logic:
  - Option A: Upsert (return 200 + note if exists with same config)
  - Option B: 409 Conflict if exists with different config
- [ ] Strong validation:
  - Required fields: `name`, `type`, `base_url` (for openai_compatible)
  - Return 422 with field-level errors (loc, msg, type)
- [ ] Egress allowlist validation (currently partial)
- [ ] Return `event_id`/`trace_id` in response

### 5. Get Main Provider (`GET /providers/main`)
**Current State**: Basic implementation

**TODO**:
- [ ] Document precedence: tenant default → global default → 404
- [ ] Return 404 with proper Problem+JSON if no default found
- [ ] Add ETag support for caching
- [ ] Use `GetMainProviderResponse` schema

### 6. Get Provider (`GET /providers/{provider_id}`)
**Current State**: Returns dict

**TODO**:
- [ ] Return `Provider` schema with proper typing
- [ ] Add ETag support
- [ ] Return 404 with Problem+JSON if not found
- [ ] Include `has_api_key` indicator
- [ ] Redact all secrets

### 7. Update Provider (`PATCH /providers/{provider_id}`)
**Current State**: Uses old `UpdateProviderRequest`

**TODO**:
- [ ] Use new `UpdateProviderRequest` schema
- [ ] Validate merged config
- [ ] Return 404 if provider not found (not 400)
- [ ] Return `event_id`/`trace_id`

### 8. Delete Provider (`DELETE /providers/{provider_id}`)
**Current State**: Returns `ActionResponse`

**CRITICAL**:
- [ ] **Change to return 204 No Content** (or update docs to match 200)
- [ ] Return proper Problem+JSON on errors
- [ ] Include `event_id`/`trace_id` in 204 response headers

### 9. Set Default (`PUT /providers/default`)
**Current State**: Uses old `SetMainLLMRequest`

**TODO**:
- [ ] Use `SetDefaultProviderRequest` schema
- [ ] If `tenant_id` missing → set global default
- [ ] If `tenant_id` present → set tenant-scoped default
- [ ] Return 404 if provider not found
- [ ] Document behavior clearly

---

## 📋 Not Started

### 10. Status Codes & Error Handling
**Requirements**:
- [ ] All Problem+JSON titles match status:
  - 400: "Bad Request"
  - 401: "Unauthorized"
  - 403: "Forbidden"
  - 404: "Not Found"
  - 409: "Conflict"
  - 422: "Validation Error"
  - 500: "Internal Server Error"
- [ ] Use `application/problem+json` media type
- [ ] Include `extensions.correlation_id` in all errors
- [ ] Differentiate 400 (business logic) vs 422 (validation)

### 11. Multi-Tenant Support
**Requirements**:
- [ ] Document tenant scoping rules in OpenAPI
- [ ] Add `tenant_id` query filter to `GET /providers` (admin only)
- [ ] Non-admins only see their tenant's providers
- [ ] Test global vs tenant-scoped providers

### 12. Rate Limiting & Observability
**Requirements**:
- [ ] Document rate limit headers in OpenAPI:
  - `RateLimit-Limit`
  - `RateLimit-Remaining`
  - `RateLimit-Reset`
- [ ] Document `X-Request-Id` header
- [ ] Emit `event_id`/`trace_id` on all mutating ops
- [ ] Include trace IDs in success & error responses

### 13. OpenAPI Documentation
**Requirements**:
- [ ] Replace placeholder examples with valid payloads
- [ ] Add working curl examples for each endpoint
- [ ] Document all path parameters with examples
- [ ] Document request/response headers
- [ ] Add security requirements to OpenAPI
- [ ] Document pagination behavior
- [ ] Document caching behavior (ETags)

### 14. Contract Tests
**Requirements**:
- [ ] Create `tests/test_providers_contract.py`
- [ ] Happy path tests:
  - register → list → get → set default (global) → get main
  - set default (tenant) → get main
  - patch → delete
- [ ] Negative tests:
  - Invalid enum values
  - Bad URLs
  - Missing required fields
  - Unknown provider in set default
  - Unauthorized (no token)
  - Forbidden (non-admin token)
  - Pagination edge cases
  - ETag 304 response

### 15. Non-Admin List Endpoint (Optional)
**Requirements**:
- [ ] Create `GET /v1/models/providers` (non-admin)
- [ ] Return redacted providers (tenant-scoped)
- [ ] Exclude internal metadata (tenant scoping details)
- [ ] Document separately from admin endpoint

---

## Implementation Priority

### Phase 1: Critical Fixes (Do First)
1. **DELETE returns 204** - Breaking change, must align with spec
2. **Problem+JSON titles** - Fix error response consistency
3. **Register idempotency** - Prevent duplicate registration issues
4. **Validation errors (422)** - Field-level error details

### Phase 2: Core Functionality
5. **Get/Main/Set Default** - Use proper schemas
6. **ETag caching** - Complete for GET endpoints
7. **Secret redaction** - Verify all endpoints

### Phase 3: Documentation & Testing
8. **OpenAPI examples** - Valid, working examples
9. **Contract tests** - Comprehensive coverage
10. **Migration guide** - Document breaking changes

---

## Breaking Changes

### ⚠️ API Contract Changes:
1. **DELETE /providers/{id}**: Now returns `204 No Content` (was `200 ActionResponse`)
2. **GET /providers**: Returns `{items, next_page_token, total}` (was array)
3. **Error responses**: Problem+JSON titles now match status codes
4. **Validation errors**: 422 includes field-level `errors` array

### Migration Guide:
- Clients expecting array from `GET /providers` must use `.items`
- Clients checking DELETE response body must handle 204 (no body)
- Error parsing must handle `extensions.correlation_id` (not top-level `traceId`)

---

## Testing Checklist

### Unit Tests:
- [ ] Provider schema validation
- [ ] Secret redaction logic
- [ ] Pagination logic
- [ ] ETag computation

### Integration Tests:
- [ ] Admin-only enforcement
- [ ] Tenant isolation
- [ ] Idempotency behavior
- [ ] Default resolution precedence

### Contract Tests:
- [ ] OpenAPI spec compliance
- [ ] HTTP status codes
- [ ] Response headers
- [ ] Error formats

---

## Files Modified

### Created:
- `src/schemas/providers.py` - Canonical schemas

### Modified:
- `src/routers/model_management.py` - Endpoint implementations
- `src/repositories/models_repo.py` - (May need updates for has_api_key)

### To Create:
- `tests/test_providers_contract.py` - Contract tests
- `docs/api/providers-migration.md` - Migration guide

---

## Next Steps

1. **Complete register_client update** - Use RegisterProviderRequest
2. **Fix DELETE endpoint** - Return 204 No Content
3. **Update remaining endpoints** - Use proper schemas
4. **Add comprehensive tests** - Contract + integration
5. **Update OpenAPI docs** - Examples and descriptions
