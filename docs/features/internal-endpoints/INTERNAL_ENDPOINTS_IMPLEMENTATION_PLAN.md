# Internal Endpoints Implementation Plan

**Status**: In Progress  
**Priority**: HIGH  
**Target Date**: October 29, 2025

## Executive Summary

This document outlines the comprehensive implementation plan for hardening and enhancing the internal endpoints (`/v1/internal/*`) based on production readiness requirements. The plan covers security, behavior, storage, observability, documentation, and testing.

## Scope

### Endpoints Covered

* `POST /v1/internal/ops/auto-start-override` - Override auto-start behavior
* `GET /v1/internal/ops/preview-staged` - Preview staged manifests
* `POST /v1/internal/db/jobs` - Create database maintenance jobs
* `GET /v1/internal/db/jobs/{job_id}` - Get job status
* `DELETE /v1/internal/db/jobs/{job_id}` - Cancel database job
* `GET /v1/internal/db/counts` - Get database node/edge counts

---

## ✅ Completed Work

### Security Enhancements

- [x] **Documented leaked Auth0 M2M credentials** (SECURITY_INCIDENT_2025-10-22.md)
  - Created incident report with rotation instructions
  - Added pre-commit hook recommendations for secret scanning
  
- [x] **Enhanced `require_internal()` to explicitly reject admin tokens**
  - Updated `src/security/internal.py::has_internal_access()`
  - Added explicit deny for `admin:all` scope
  - Added explicit deny for user tokens (`user:me`, `tools:invoke:*`)
  - Improved error messages with scope feedback

- [x] **Implemented short TTL enforcement for internal endpoints**
  - Updated `src/security/jwt.py::validate_jwt()` with `enforce_short_ttl` parameter
  - Default maximum TTL: 3600 seconds (1 hour)
  - Configurable via `INTERNAL_TOKEN_MAX_TTL_SECONDS` env var
  - Returns RFC 7807 error with TTL details when exceeded

- [x] **Enhanced JWT aud/iss validation**
  - Added detailed RFC 7807 error responses for invalid issuer
  - Added detailed RFC 7807 error responses for invalid audience
  - Includes expected vs received values in error extensions

### Code Structure

- [x] Created `get_internal_principal()` function for internal endpoint JWT validation
- [x] Updated `require_internal()` to use enhanced principal validation
- [x] All internal endpoints now enforce TTL and aud/iss validation automatically

---

## 🚧 In Progress

### Behavior & Configuration

- [ ] **Make auto-start override TTL configurable** (Priority: HIGH)
  - Read `INTERNAL_UI_OVERRIDE_TTL_SECONDS` from environment
  - Default: 600 seconds (10 minutes)
  - Bounds: 60-3600 seconds (clamp invalid values)
  - Always include `ttl_seconds` in response
  - **Files**: `src/routers/internal_ops.py`, `src/config.py`

---

## 📋 Pending Work

### 🧠 Behavior & Buglets

#### Auto-Start Override Idempotency (Priority: HIGH)
- [ ] Respect `Idempotency-Key` header for `POST /internal/ops/auto-start-override`
- [ ] Store response in Redis with 24h TTL: `idemp:/internal/ops/auto-start-override:{key}`
- [ ] Return cached response with `Idempotency-Replayed: true` header on replay
- [ ] Include timestamp in cached value
- **Files**: `src/routers/internal_ops.py`
- **Tests**: `tests/routers/test_internal_ops_idempotency.py`

#### Preview Cache Coherence (Priority: MEDIUM)
- [ ] Implement `force_refresh=true` to bypass cache
- [ ] Include file mtime or content hash in cached value
- [ ] Invalidate cache when manifest files change
- [ ] Cache key: `internal:preview-staged:v1`
- [ ] Configurable TTL via `INTERNAL_PREVIEW_CACHE_TTL_SECONDS` (default: 90s)
- **Files**: `src/routers/internal_ops.py`

#### DB Counts 501 Enhancement (Priority: LOW)
- [ ] Add `Retry-After: 60` header to 501 response
- [ ] Add `X-Feature: memgraph=unavailable` header
- [ ] Update OpenAPI docs to document 501 behavior
- **Files**: `src/routers/internal_db.py`

---

### 🧱 Storage Model

#### Redis Keys Documentation (Priority: HIGH)
- [ ] Create comprehensive documentation of all Redis key patterns
- [ ] Document schemas (JSON structure) for each key
- [ ] Document TTLs and expiration policies
- [ ] **New File**: `docs/REDIS_KEYS_INTERNAL.md`

**Required Keys**:
```
internal:auto_start_override → JSON {enabled, note, set_by_sub, ts, ttl}
  TTL: INTERNAL_UI_OVERRIDE_TTL_SECONDS (default 600s)

idemp:/internal/ops/auto-start-override:{sha256} → response envelope
  TTL: 24h

idemp:/internal/db/jobs:{sha256} → response envelope
  TTL: 24h

internal:preview-staged:v1 → JSON {items, count, source_hash, ts}
  TTL: INTERNAL_PREVIEW_CACHE_TTL_SECONDS (default 90s)

dbjob:cancel:{job_id} → "1" (cancel flag)
  TTL: 300s (until job finishes)

dbjob:progress:{job_id} → JSON {state, progress, message, ts}
  TTL: 24h
```

#### PostgreSQL Audit Table (Priority: HIGH)
- [ ] Create migration for `internal_ops_events` table
- [ ] Columns: `id`, `event_type`, `actor_sub`, `payload_json`, `created_at`
- [ ] Indexes: `(event_type, created_at DESC)`, `(actor_sub, created_at DESC)`
- [ ] **New File**: `db/postgres_control/migrations/XXX_create_internal_ops_events.py`
- **Model**: `db/postgres_control/models/internal_ops_event.py` (already exists)

#### PostgreSQL DB Jobs Table (Priority: MEDIUM)
- [ ] Enhance existing `jobs` table OR create `internal_db_jobs` table
- [ ] Columns: `job_id`, `action`, `params_json`, `state`, `progress`, `message`, `started_at`, `finished_at`, `created_by_sub`
- [ ] Indexes: `(created_at DESC)`, `(state, created_at DESC)`
- [ ] **File**: Check if existing `jobs` table can be reused

---

### 🪪 RBAC & Claims Handling

#### X-Subject Header (Priority: MEDIUM)
- [ ] Add `X-Subject` header to all internal endpoint responses
- [ ] Extract from `principal.sub`
- [ ] Include in observability middleware
- **Files**: All routers in `src/routers/internal_*.py`

---

### 👁️ Observability & Error Handling

#### RFC 7807 Standardization (Priority: HIGH)
- [ ] Audit all error responses in internal endpoints
- [ ] Ensure format: `{type, title, status, detail, instance, extensions}`
- [ ] Move `correlation_id` to `extensions.correlation_id` (no duplicate fields)
- [ ] Ensure `instance` is the absolute request path
- **Files**: `src/routers/internal_ops.py`, `src/routers/internal_db.py`

#### Observability Headers (Priority: HIGH)
- [ ] Add `X-Request-Id` to all responses (generated if missing)
- [ ] Add `X-Correlation-Id` to all responses (echo if provided, else generate)
- [ ] Add `X-Subject` with authenticated principal sub
- [ ] Add `Idempotency-Replayed: true` when serving cached idempotent response
- [ ] For 501 responses: `Retry-After: 60`, `X-Feature: memgraph=unavailable`
- **Files**: All internal routers

#### Structured Logging (Priority: MEDIUM)
- [ ] Ensure all logs include: `route`, `status`, `sub`, `aud`, `scopes`, `corr_id`
- [ ] Use JSON format for structured logs
- [ ] Filter sensitive fields (never log `authorization` header, credentials)
- **Files**: `src/routers/internal_*.py`, `src/logging_setup.py`

---

### 📜 OpenAPI & Documentation

#### Parameter Documentation (Priority: MEDIUM)
- [ ] Mark required query/path params in OpenAPI schema
- [ ] Ensure Swagger "Try it out" enforces required params
- [ ] Add descriptions to all parameters
- **Files**: All internal routers (decorators and docstrings)

#### Response Examples (Priority: MEDIUM)
- [ ] Add example for valid override request/response
- [ ] Add example for preview with staged items
- [ ] Add example for DB job create (`create` + `wipe`, `populate` + `users`)
- [ ] Document 202 response with `Location` header
- [ ] Add 501 example for counts endpoint
- **Files**: OpenAPI `responses` dict in router decorators

---

### 🧪 Tests

#### Auth Matrix Tests (Priority: HIGH)
- [ ] Test admin token → 403 for all `/v1/internal/*`
- [ ] Test user token → 403 for all `/v1/internal/*`
- [ ] Test M2M token with `internal:all` → 200/202/204/501 as expected
- [ ] **New File**: `tests/security/test_internal_auth_matrix.py`

#### Override Endpoint Tests (Priority: HIGH)
- [ ] Test Redis key creation with TTL
- [ ] Test idempotency: same key returns cached response
- [ ] Test TTL override via environment variable
- [ ] Test audit row insertion to PostgreSQL
- [ ] Test `allowed=false` when feature flag disabled
- **New File**: `tests/routers/test_internal_ops_override.py`

#### Preview Endpoint Tests (Priority: MEDIUM)
- [ ] Test cache hit (no force_refresh)
- [ ] Test cache miss / force_refresh
- [ ] Test cache invalidation when manifest file changes
- [ ] **New File**: `tests/routers/test_internal_ops_preview.py`

#### DB Jobs Endpoint Tests (Priority: HIGH)
- [ ] Test `create` happy path: 202 + `Location` header
- [ ] Test `populate` happy path: 202 + `Location` header
- [ ] Test 400 on invalid `type`
- [ ] Test idempotency: same key returns same job_id
- [ ] Test job status retrieval (GET)
- [ ] Test job cancellation (DELETE) - idempotent 204
- **New File**: `tests/routers/test_internal_db_jobs.py`

#### DB Counts Endpoint Tests (Priority: LOW)
- [ ] Test 200 when Memgraph client mocked
- [ ] Test 501 when Memgraph unavailable
- [ ] Verify headers: `Retry-After`, `X-Feature`
- **New File**: `tests/routers/test_internal_db_counts.py`

---

### ⚙️ Configuration & Environment

#### Config Documentation (Priority: HIGH)
- [ ] Document all internal endpoint configuration flags
- [ ] Add to `docs/environment-variables.md`
- [ ] Add validation/defaults to `src/config.py`

**Required Environment Variables**:
```bash
# Internal Endpoints Configuration
INTERNAL_UI_OVERRIDE_ALLOWED=true|false         # Default: true
INTERNAL_UI_OVERRIDE_TTL_SECONDS=600            # Default: 600, bounds: 60-3600
INTERNAL_PREVIEW_CACHE_TTL_SECONDS=90           # Default: 90
INTERNAL_TOKEN_MAX_TTL_SECONDS=3600             # Default: 3600 (1 hour)
FEATURE_MEMGRAPH_COUNTS=true|false              # Default: true (controls 200 vs 501)
```

#### Config Implementation (Priority: HIGH)
- [ ] Add settings to `src/config.py`
- [ ] Add validation (bounds checking for TTL values)
- [ ] Add defaults with type hints
- **File**: `src/config.py`

---

### 🧹 Code Cleanup

#### Header Normalization (Priority: LOW)
- [ ] Handle header names case-insensitively
- [ ] Use `request.headers.get(key)` with lowercase key
- [ ] Standardize header generation (X-Request-Id, X-Correlation-Id)
- **Files**: All internal routers

#### Error Response Cleanup (Priority: MEDIUM)
- [ ] Ensure `instance` field contains `str(request.url)`
- [ ] Remove duplicate `correlation_id` keys (only in `extensions`)
- [ ] Consistent error type URIs (use `https://cineca.example/errors/*`)
- **Files**: All internal routers

---

## Implementation Order

### Phase 1: Security & Foundation (Week 1)
1. ✅ Security incident documentation
2. ✅ Enhanced RBAC (reject admin tokens)
3. ✅ TTL enforcement
4. ✅ aud/iss validation
5. [ ] Config implementation (environment variables)
6. [ ] Redis keys documentation
7. [ ] PostgreSQL migrations (audit table)

### Phase 2: Behavior & Observability (Week 2)
8. [ ] Auto-start override TTL configuration
9. [ ] Idempotency implementation (override + jobs)
10. [ ] Preview cache coherence
11. [ ] RFC 7807 error standardization
12. [ ] Observability headers (X-Request-Id, X-Correlation-Id, X-Subject)
13. [ ] DB counts 501 enhancement

### Phase 3: Documentation & Testing (Week 3)
14. [ ] OpenAPI documentation (parameters, examples)
15. [ ] Auth matrix tests
16. [ ] Override endpoint tests
17. [ ] Preview endpoint tests
18. [ ] DB jobs tests
19. [ ] DB counts tests

### Phase 4: Polish & Deployment (Week 4)
20. [ ] Header normalization
21. [ ] Error response cleanup
22. [ ] Final code review
23. [ ] Integration testing
24. [ ] Production deployment

---

## Success Criteria

### Security
- [x] Admin tokens rejected with 403 on all `/internal/*`
- [x] User tokens rejected with 403 on all `/internal/*`
- [ ] M2M tokens with `internal:all` work on all endpoints
- [x] Tokens with TTL > 3600s rejected
- [x] Invalid aud/iss rejected with detailed errors

### Behavior
- [ ] Override endpoint respects config TTL (default 600s, bounds 60-3600s)
- [ ] Idempotency works for override and jobs (24h cache)
- [ ] Preview force_refresh bypasses cache
- [ ] Jobs endpoint: 400 on invalid type, 202 + Location on success
- [ ] Counts endpoint: 501 with proper headers when Memgraph unavailable

### Storage
- [ ] Redis keys documented with schemas and TTLs
- [ ] PostgreSQL audit table created with indexes
- [ ] All operations logged to audit table

### Observability
- [ ] All errors follow RFC 7807 format
- [ ] All responses include X-Request-Id, X-Correlation-Id, X-Subject
- [ ] Idempotent responses include Idempotency-Replayed: true
- [ ] Structured logs include route, status, sub, scopes, corr_id

### Documentation
- [ ] OpenAPI schema complete with examples
- [ ] Environment variables documented
- [ ] Redis keys documented
- [ ] Storage model documented

### Testing
- [ ] Auth matrix tests pass (admin/user → 403, M2M → success)
- [ ] Behavior tests pass (idempotency, cache, TTL)
- [ ] Integration tests pass
- [ ] All tests green in CI/CD

---

## Risk Assessment

### High Risk
- **Leaked credentials**: CRITICAL - Must rotate Auth0 M2M secret immediately
- **Admin bypass**: MITIGATED - Code now explicitly rejects admin tokens
- **Token replay**: MEDIUM - Idempotency implementation will mitigate

### Medium Risk
- **Cache coherence**: Preview cache may serve stale data (force_refresh helps)
- **Race conditions**: Multiple operators setting override simultaneously (Redis atomic ops help)

### Low Risk
- **Header case sensitivity**: Minor UX issue, easy to fix
- **Missing audit logs**: Best-effort logging, failure doesn't break endpoints

---

## References

- [SECURITY_INCIDENT_2025-10-22.md](./SECURITY_INCIDENT_2025-10-22.md) - Leaked credentials incident
- [RFC 7807 - Problem Details for HTTP APIs](https://tools.ietf.org/html/rfc7807)
- [Auth0 Security Best Practices](https://auth0.com/docs/secure/security-guidance)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)

---

## Contact

- **Owner**: Platform Engineering Team
- **Tech Lead**: TBD
- **Security Review**: security@cineca.example
- **On-call**: oncall@cineca.example

---

**Last Updated**: October 22, 2025  
**Next Review**: October 29, 2025
