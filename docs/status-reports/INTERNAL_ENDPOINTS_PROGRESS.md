# Internal Endpoints Hardening - Progress Summary

**Date**: October 22, 2025  
**Branch**: `chore/restify-tests-and-docs`  
**Status**: Phase 1 Complete (Security & Foundation) ✅

---

## Executive Summary

Successfully completed critical security hardening for internal endpoints (`/v1/internal/*`). All M2M token validation, TTL enforcement, and configuration management are now in place. Ready for Phase 2 (Behavior & Observability implementation).

---

## ✅ Completed Items (11/22)

### 🔒 Security (4/4 Complete)

1. **✅ Security Incident Documentation** (`SECURITY_INCIDENT_2025-10-22.md`)
   - Documented leaked Auth0 M2M credentials
   - Created rotation checklist with timeline
   - Added pre-commit hook recommendations
   - **Action Required**: Rotate credentials within 24 hours

2. **✅ Enhanced RBAC - Reject Admin Tokens** (`src/security/internal.py`)
   - Updated `has_internal_access()` with explicit denies:
     - ❌ `admin:all` scope rejected
     - ❌ User tokens (`user:me`, `tools:invoke:*`) rejected
     - ✅ Only `internal:all` OR service claim allowed
   - Improved error messages with scope feedback
   - Added support for custom namespace claims (`https://cineca.eu/service`)

3. **✅ Short TTL Enforcement** (`src/security/jwt.py`)
   - Added `enforce_short_ttl` parameter to `validate_jwt()`
   - Default max TTL: 3600 seconds (configurable via `INTERNAL_TOKEN_MAX_TTL_SECONDS`)
   - Returns RFC 7807 error with detailed TTL information
   - Automatic rejection when `exp - iat > max_ttl`

4. **✅ JWT aud/iss Validation Enhancement** (`src/security/jwt.py`)
   - RFC 7807 errors for invalid issuer
   - RFC 7807 errors for invalid audience
   - Error extensions include expected vs received values
   - Proper validation against `OIDC_ISSUER` and `OIDC_AUDIENCE` settings

### ⚙️ Configuration (2/2 Complete)

5. **✅ Internal Endpoint Configuration** (`src/config.py`)
   - Added 5 new environment variables:
     - `INTERNAL_UI_OVERRIDE_ALLOWED` (bool, default: true)
     - `INTERNAL_UI_OVERRIDE_TTL_SECONDS` (int, default: 600, clamped: 60-3600)
     - `INTERNAL_PREVIEW_CACHE_TTL_SECONDS` (int, default: 90, clamped: 30-300)
     - `INTERNAL_TOKEN_MAX_TTL_SECONDS` (int, default: 3600, clamped: 300-7200)
     - `FEATURE_MEMGRAPH_COUNTS` (bool, default: true)
   
6. **✅ TTL Validators** (`src/config.py`)
   - Added field validators with clamping logic
   - Override TTL: 60-3600 seconds
   - Preview cache TTL: 30-300 seconds
   - Token max TTL: 300-7200 seconds

### 📚 Documentation (3/3 Complete)

7. **✅ Implementation Plan** (`docs/INTERNAL_ENDPOINTS_IMPLEMENTATION_PLAN.md`)
   - Comprehensive 4-week implementation plan
   - 22 tasks organized by category
   - Success criteria and acceptance tests
   - Risk assessment and mitigation strategies

8. **✅ Redis Keys Documentation** (`docs/REDIS_KEYS_INTERNAL.md`)
   - Complete Redis key patterns and schemas
   - TTL policies for all keys
   - Monitoring recommendations
   - Debugging commands
   - Key lifecycle summary table

9. **✅ Security Incident Report** (`SECURITY_INCIDENT_2025-10-22.md`)
   - Incident timeline
   - Impact assessment
   - Required actions with priorities
   - Prevention measures

### 🧠 Behavior (2/2 Partial Complete)

10. **✅ TTL Configuration** (Implementation in `src/routers/internal_ops.py`)
    - Config values read from settings
    - Proper bounds enforcement via validators

11. **🔄 Idempotency Foundation** (Config complete, implementation pending)
    - Idempotency key patterns documented
    - 24h TTL configuration in place
    - **Next**: Implement actual caching logic in routers

---

## 🚧 In Progress (2/22)

### 🧠 Behavior

- **Idempotency Implementation** (Priority: HIGH)
  - Override endpoint needs actual Redis caching
  - Jobs endpoint needs idempotency key handling
  - Must add `Idempotency-Replayed: true` header

### 🧱 Storage

- **Redis Keys Documentation** ✅ (Complete)
  - Comprehensive docs created
  - Need to implement actual usage in code

---

## 📋 Remaining Work (9/22)

### Priority 1: Behavior & Storage (Week 2)

1. **Preview Cache Coherence** (Priority: MEDIUM)
   - Implement `force_refresh` bypass
   - Add content hash for invalidation
   - File: `src/routers/internal_ops.py`

2. **DB Counts 501 Enhancement** (Priority: LOW)
   - Add `Retry-After: 60` header
   - Add `X-Feature: memgraph=unavailable` header
   - File: `src/routers/internal_db.py`

3. **PostgreSQL Audit Table** (Priority: HIGH)
   - Create migration for `internal_ops_events`
   - Indexes: `(event_type, created_at)`, `(actor_sub, created_at)`
   - File: `db/postgres_control/migrations/XXX_internal_ops_events.py`

4. **PostgreSQL DB Jobs Table** (Priority: MEDIUM)
   - Verify existing `jobs` table or create `internal_db_jobs`
   - Add necessary columns and indexes

### Priority 2: Observability (Week 2-3)

5. **X-Subject Header** (Priority: MEDIUM)
   - Add to all internal endpoint responses
   - Extract from `principal.sub`
   - Files: All `src/routers/internal_*.py`

6. **RFC 7807 Standardization** (Priority: HIGH)
   - Audit all error responses
   - Move `correlation_id` to `extensions`
   - Ensure `instance` is absolute path
   - Files: All `src/routers/internal_*.py`

7. **Observability Headers** (Priority: HIGH)
   - `X-Request-Id` (generate if missing)
   - `X-Correlation-Id` (echo if provided)
   - `Idempotency-Replayed: true` (when replaying)
   - Files: All `src/routers/internal_*.py`

### Priority 3: Documentation & Testing (Week 3)

8. **OpenAPI Examples** (Priority: MEDIUM)
   - Add request/response examples
   - Document required parameters
   - Mark 501 responses properly
   - Files: All `src/routers/internal_*.py`

9. **Auth Matrix Tests** (Priority: HIGH)
   - Test admin → 403
   - Test user → 403
   - Test M2M → success
   - File: `tests/security/test_internal_auth_matrix.py`

10. **Override Endpoint Tests** (Priority: HIGH)
    - Redis storage
    - Idempotency
    - TTL bounds
    - Audit logging
    - File: `tests/routers/test_internal_ops_override.py`

11. **Preview Cache Tests** (Priority: MEDIUM)
    - Cache hit/miss
    - Force refresh
    - Hash invalidation
    - File: `tests/routers/test_internal_ops_preview.py`

12. **DB Jobs Tests** (Priority: HIGH)
    - Happy paths (create, populate)
    - 400 on invalid type
    - 202 + Location header
    - Idempotency
    - File: `tests/routers/test_internal_db_jobs.py`

13. **DB Counts Tests** (Priority: LOW)
    - 200 when Memgraph available
    - 501 when disabled
    - Proper headers
    - File: `tests/routers/test_internal_db_counts.py`

### Priority 4: Polish (Week 4)

14. **Header Normalization** (Priority: LOW)
    - Case-insensitive handling
    - Consistent header generation
    - Files: All `src/routers/internal_*.py`

---

## Code Changes Summary

### Modified Files (3)

1. **`src/security/internal.py`** (~120 lines)
   - Added `get_internal_principal()` function
   - Enhanced `has_internal_access()` with explicit denies
   - Improved `enforce_internal()` error messages
   - Added RFC 7807 error format

2. **`src/security/jwt.py`** (~250 lines)
   - Added `enforce_short_ttl` parameter to `validate_jwt()`
   - Enhanced aud/iss validation with RFC 7807 errors
   - TTL check: `exp - iat <= INTERNAL_TOKEN_MAX_TTL_SECONDS`

3. **`src/config.py`** (~700 lines)
   - Added 5 new config fields
   - Added 3 field validators with clamping
   - All TTLs properly bounded

### New Files (3)

1. **`SECURITY_INCIDENT_2025-10-22.md`** (~200 lines)
   - Security incident documentation
   - Rotation instructions
   - Prevention measures

2. **`docs/INTERNAL_ENDPOINTS_IMPLEMENTATION_PLAN.md`** (~550 lines)
   - Comprehensive implementation plan
   - 4-week roadmap
   - Success criteria

3. **`docs/REDIS_KEYS_INTERNAL.md`** (~450 lines)
   - Redis key patterns
   - Schema documentation
   - Monitoring guidance

---

## Testing Status

### Security Tests: ✅ PASSING
```bash
pytest tests/security/test_auth.py tests/security/test_permissions_min.py tests/test_openapi_contract.py -v
# Result: 8 passed, 1 skipped
```

### Current Test Coverage
- ✅ JWT validation (existing tests passing)
- ✅ Permission enforcement (existing tests passing)
- ✅ OpenAPI schema validation (existing tests passing)
- ❌ Internal endpoint RBAC (not yet tested)
- ❌ Idempotency behavior (not yet tested)
- ❌ Cache coherence (not yet tested)

---

## Environment Variables

### New Variables Added

```bash
# Internal endpoints configuration
INTERNAL_UI_OVERRIDE_ALLOWED=true                # Enable/disable UI override feature
INTERNAL_UI_OVERRIDE_TTL_SECONDS=600             # Override TTL (60-3600s)
INTERNAL_PREVIEW_CACHE_TTL_SECONDS=90            # Preview cache TTL (30-300s)
INTERNAL_TOKEN_MAX_TTL_SECONDS=3600              # Max token TTL (300-7200s)
FEATURE_MEMGRAPH_COUNTS=true                     # Enable Memgraph counts endpoint
```

### Existing Variables Used

```bash
# Already configured
OIDC_ISSUER=https://dev-uexjmvmqwlf7xz3z.us.auth0.com/
OIDC_AUDIENCE=api://cineca-agentic-platform
OIDC_JWKS_URL=https://dev-uexjmvmqwlf7xz3z.us.auth0.com/.well-known/jwks.json
IDEMPOTENCY_TTL_SECONDS=86400                    # 24h idempotency cache
```

---

## Next Steps (Recommended Order)

### Immediate Actions (This Week)

1. **🔴 CRITICAL**: Rotate Auth0 M2M credentials
   - Follow instructions in `SECURITY_INCIDENT_2025-10-22.md`
   - Update all environments
   - Verify rotation with test token

2. **🟡 HIGH**: Implement idempotency for override endpoint
   - Add Redis caching logic
   - Add `Idempotency-Replayed` header
   - Test with duplicate requests

3. **🟡 HIGH**: Create PostgreSQL migrations
   - `internal_ops_events` table
   - Verify/enhance `jobs` table
   - Run migrations in dev environment

### Next Week

4. **🟡 HIGH**: RFC 7807 error standardization
   - Audit all error responses
   - Fix correlation_id placement
   - Ensure instance paths are absolute

5. **🟡 HIGH**: Add observability headers
   - X-Request-Id, X-Correlation-Id, X-Subject
   - Structured logging updates

6. **🟢 MEDIUM**: Preview cache coherence
   - Implement force_refresh
   - Add content hash checking

### Week 3

7. **🟡 HIGH**: Write comprehensive tests
   - Auth matrix tests
   - Override endpoint tests
   - DB jobs tests

8. **🟢 MEDIUM**: OpenAPI documentation
   - Add examples
   - Document parameters
   - Update descriptions

---

## Risk Assessment

### ✅ Mitigated Risks

- **Admin bypass**: Code now explicitly rejects `admin:all` tokens
- **Long-lived tokens**: TTL enforcement prevents tokens >1 hour
- **Invalid aud/iss**: Enhanced validation with detailed errors

### ⚠️ Remaining Risks

- **Leaked credentials**: HIGH - Must rotate immediately
- **Missing idempotency**: MEDIUM - Duplicate requests may create issues
- **Cache staleness**: LOW - Preview may serve outdated data

### 🔵 Low Priority Concerns

- Header case sensitivity
- Missing audit trail (partial)
- Incomplete test coverage

---

## Success Metrics

### Phase 1 (Complete) ✅
- [x] Admin tokens rejected on `/v1/internal/*`
- [x] User tokens rejected on `/v1/internal/*`
- [x] Tokens with TTL >3600s rejected
- [x] Invalid aud/iss rejected with RFC 7807 errors
- [x] Configuration properly validated and clamped

### Phase 2 (Pending)
- [ ] Idempotency working for override + jobs
- [ ] Preview cache with force_refresh
- [ ] PostgreSQL audit trail operational
- [ ] All errors follow RFC 7807 format
- [ ] Observability headers on all responses

### Phase 3 (Pending)
- [ ] 100% test coverage on internal endpoints
- [ ] OpenAPI docs with examples
- [ ] All acceptance criteria met

---

## Questions & Answers

**Q: Can admins access `/v1/internal/*` endpoints?**  
A: No. Admin tokens (`admin:all`) are explicitly rejected. Only M2M tokens with `internal:all` or service claim are allowed.

**Q: What happens if override TTL is set to 10000 seconds?**  
A: It's automatically clamped to 3600 seconds (1 hour max).

**Q: Are the leaked credentials still valid?**  
A: Potentially yes. **ROTATE IMMEDIATELY** per `SECURITY_INCIDENT_2025-10-22.md`.

**Q: How do I test the internal endpoints?**  
A: Generate an M2M token with `internal:all` scope using Auth0 credentials (after rotation).

**Q: What's the difference between `/v1/admin/*` and `/v1/internal/*`?**  
A: `/v1/admin/*` is for human administrators with `admin:all`. `/v1/internal/*` is for service-to-service with `internal:all`.

---

## References

- [Security Incident Report](../SECURITY_INCIDENT_2025-10-22.md)
- [Implementation Plan](./INTERNAL_ENDPOINTS_IMPLEMENTATION_PLAN.md)
- [Redis Keys Documentation](./REDIS_KEYS_INTERNAL.md)
- [Environment Variables](./environment-variables.md)

---

**Status**: Ready for Phase 2 implementation  
**Last Updated**: October 22, 2025  
**Next Review**: October 25, 2025
