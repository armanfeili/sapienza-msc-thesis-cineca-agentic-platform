# Agents API Finalization - Assessment & Implementation Plan

**Date**: October 20, 2025  
**Phase**: API Polish & Compliance Verification  
**Scope**: 14 areas covering HTTP semantics, caching, pagination, RBAC, and storage  
**Status**: Planning → Ready for Implementation

---

## 📊 Current State Assessment

### Already Implemented ✅

#### From Previous Finalization (Tasks 1-5):
- ✅ **Idempotency status codes** - Returns original 201 on replay (verified)
- ✅ **RFC-7807 error format** - All errors include `correlation_id` + `timestamp`
- ✅ **Rate limit headers** - Already present on responses
- ✅ **X-Request-Id propagation** - Already implemented
- ✅ **RBAC basics** - Authentication/permission checks in place

#### API Infrastructure:
- ✅ FastAPI framework with OpenAPI generation
- ✅ PostgreSQL for persistent storage (sessions, steps, runs)
- ✅ Redis for caching and rate limiting
- ✅ Middleware for idempotency and error handling
- ✅ Health endpoints with diagnostics

### Needs Implementation ⚠️

#### Critical (Blocking Production):
1. ✅ **Idempotency Headers** - `Idempotency-Key` echo + `Idempotency-Replayed` flag
2. ⚠️ **ETag Implementation** - Return header (not body), support `If-None-Match` → 304
3. ⚠️ **Location Header** - On POST 201 responses
4. ⚠️ **Pagination Naming** - Standardize `cursor`/`next_cursor` (currently `next_page_token`)
5. ⚠️ **HTTP Status Codes** - Validate 201/204/304 usage

#### Important (API Quality):
6. ⚠️ **Session State Enforcement** - Reject step creation on cancelled sessions (400/409)
7. ⚠️ **Vary Header Coverage** - Add `Authorization` to Vary on cached endpoints
8. ⚠️ **Content-Type Uniformity** - Ensure all errors are `application/problem+json`
9. ⚠️ **Field Naming Consistency** - Unify `metadata` vs `session_metadata`
10. ⚠️ **Run Persistence** - Verify atomic updates to session state

#### Lower Priority (Documentation/Examples):
11. ✅ **Problem+JSON Fields** - Already implemented, needs example verification
12. ⚠️ **OpenAPI Examples** - Replace `"string"` with realistic UUIDs
13. ⚠️ **Storage Boundaries** - Document, verify no leakage
14. ⚠️ **Test Coverage** - Add tests for all 14 areas

---

## 🎯 Implementation Plan by Priority

### 🔴 CRITICAL PATH (Blocks Production)

#### 1. ETag Implementation (2-3 hours)
**Files to Modify**:
- `src/routers/agent.py` - Session endpoints
- `src/routers/agent_runs.py` - Run endpoints
- `src/middleware/` - New caching middleware or modify existing
- `src/utils/etag.py` - New ETag generation utility (hash of response + user + filters)

**Changes Required**:
```python
# On GET endpoints, compute ETag from:
# - Response body content
# - User ID / Tenant ID
# - Query parameters (limit, cursor, filter)
# - Latest update timestamp

# Return:
# - ETag header (e.g., ETag: "550e8400-e29b-41d4-a716-446655440000")
# - 200 with body on first request
# - 304 Not Modified on If-None-Match match (no body)
# - Remove etag field from response bodies
```

**Endpoints to Modify**:
- `GET /agents/sessions` → ETag on list
- `GET /agents/sessions/{session_id}` → ETag on detail
- `GET /agents/sessions/{session_id}/steps` → ETag on list
- `GET /agent-runs/{run_id}` → ETag on detail

**Acceptance Criteria**:
- GET → store `ETag` header
- Repeat GET with `If-None-Match: <ETag>` → 304 response
- 304 response has no body (or minimal)
- `etag` removed from response bodies

---

#### 2. Location Header on POST (1 hour)
**Files to Modify**:
- `src/routers/agent.py` - Session creation
- `src/routers/agent_runs.py` - Run creation

**Changes Required**:
```python
# On POST /agents/sessions → 201, Location: /agents/sessions/{id}
# On POST /agents/sessions/{id}/steps → 201, Location: /agents/sessions/{id}/steps/{step_id}
# On POST /agent-runs → 201, Location: /agent-runs/{run_id}
```

**Implementation**:
```python
return JSONResponse(
    status_code=201,
    content={...},
    headers={"Location": f"/agents/sessions/{session_id}"}
)
```

**Acceptance Criteria**:
- All 201 responses have `Location` header
- Location points to immediate GET resource
- Clients can follow Location → 200 OK

---

#### 3. Pagination Naming Consistency (1.5 hours)
**Files to Modify**:
- `src/routers/agent.py` - Session list
- `src/routers/agent_runs.py` - Run list
- Schemas in `src/models/` - Update response models

**Current State**:
- Request param: `cursor` (OK) or `page_token` (varies)?
- Response field: `next_page_token` (needs standardization)

**Changes Required**:
```python
# Request: cursor (already used)
# Response: next_cursor (not next_page_token)

# Before:
# {"sessions": [...], "next_page_token": "abc"}

# After:
# {"sessions": [...], "next_cursor": "abc"}
```

**Search & Replace Scope**:
- Find all `next_page_token` → replace with `next_cursor`
- Verify `cursor` parameter consistency across endpoints
- Update schema docstrings

**Acceptance Criteria**:
- All list endpoints use `cursor` in request
- All list endpoints use `next_cursor` in response
- Pagination round-trips without position loss

---

#### 4. Session State Enforcement (1.5 hours)
**Files to Modify**:
- `src/routers/agent.py` - POST /sessions/{id}/steps
- `src/models/` - Session state enum (active, cancelled, completed)

**Changes Required**:
```python
# Before: POST /sessions/{session_id}/steps accepts any session
# After: Validate session.status == "active"
#        Return 409 Conflict if cancelled or completed

# Response on invalid state:
# 409 Conflict
# {
#   "type": "about:blank",
#   "title": "Conflict",
#   "status": 409,
#   "detail": "Cannot add step to cancelled session",
#   "instance": "/agents/sessions/{id}/steps",
#   "extensions": {
#     "correlation_id": "...",
#     "timestamp": "...",
#     "error_code": "SESSION_NOT_ACTIVE"
#   }
# }
```

**Acceptance Criteria**:
- POST /steps on active session → 201
- POST /steps on cancelled session → 409
- POST /steps on completed session → 409
- Error includes proper problem+json format

---

### 🟡 HIGH PRIORITY (Important for API Quality)

#### 5. Vary Header Enhancement (30 minutes)
**Files to Modify**:
- `src/middleware/` - Add or modify response middleware
- `src/routers/agent.py` - Ensure endpoints opt-in

**Changes Required**:
```python
# Current Vary header might be: Vary: Origin
# Add Authorization for cached/filtered endpoints:
# Vary: Origin, Authorization, X-Default-Scope, X-Tenant-Id

# Applied to:
# - GET /agents/sessions (user-specific list)
# - GET /agents/sessions/{id} (user-specific detail)
# - GET /agent-runs/{id} (user-specific detail)
```

**Implementation**:
```python
response.headers["Vary"] = "Origin, Authorization, X-Default-Scope, X-Tenant-Id"
```

**Acceptance Criteria**:
- Vary header includes Authorization on cached endpoints
- Different auth users don't share cached responses
- Same user gets cached responses (304)

---

#### 6. Idempotency Headers (45 minutes)
**Files to Modify**:
- `src/middleware/idempotency.py` - Enhance echo + replay flag

**Changes Required**:
```python
# Request headers (client sends):
# Idempotency-Key: <uuid>

# Response headers (API returns):
# Idempotency-Key: <echo of request> (always)
# Idempotency-Replayed: true (only on replay)

# Implementation:
# - On first request: store key, echo in response, no Idempotency-Replayed
# - On replay: echo key, add Idempotency-Replayed: true
```

**Acceptance Criteria**:
- First POST with Idempotency-Key → echoed in response, no `Idempotency-Replayed`
- Second POST with same key → echoed, `Idempotency-Replayed: true`
- Status/body match between first and replay

---

#### 7. Run Persistence & Atomicity (1 hour)
**Files to Modify**:
- `src/routers/agent_runs.py` - POST /agent-runs
- `db/postgres_control/` - Transaction handling

**Verify**:
```python
# POST /agent-runs should:
# 1. Create run record in DB
# 2. If linked to session, update session.last_step_id and status
# 3. Persist any produced steps atomically
# 4. All or nothing (transaction)

# After POST 201:
# - GET /agent-runs/{run_id} returns 200 (accessible)
# - Session fields updated (if linked)
```

**Acceptance Criteria**:
- Create run → GET by run_id returns 200
- Session state reflects new run (atomic)
- No orphaned runs or steps

---

### 🟢 LOWER PRIORITY (Documentation & Testing)

#### 8. Field Naming Consistency (30 minutes - low risk)
**Search**: `session_metadata` → Replace with `metadata`
**Scope**: Schemas, examples, tests
**Acceptance**: Create/GET show same field names

#### 9. Content-Type Uniformity (20 minutes - verify)
**Verify**: All 4xx/5xx responses have `Content-Type: application/problem+json`
**Tool**: Check existing middleware

#### 10. OpenAPI Examples (1 hour - documentation)
**Scope**: Replace `"string"` with realistic UUIDs, timestamps, enums
**Tool**: Update `src/routers/` docstrings
**Acceptance**: Regenerated spec shows realistic examples

#### 11. Test Coverage (2-3 hours - optional for MVP)
**Add tests for**: ETag 304 cycles, location headers, run persistence, state enforcement

---

## 📋 Recommended Execution Order

### Phase 1: Critical Path (4-5 hours)
1. **ETag Implementation** (2.5 hours) - Core caching behavior
2. **Location Headers** (1 hour) - REST semantics
3. **Pagination Naming** (1 hour) - API consistency
4. **Session State Enforcement** (1 hour) - Business logic

### Phase 2: Polish (2 hours)
5. **Vary Header** (0.5 hours)
6. **Idempotency Headers** (0.75 hours)
7. **Run Persistence Verify** (0.75 hours)

### Phase 3: Documentation (2-3 hours)
8. **Field Naming** (0.5 hours)
9. **Content-Type Verify** (0.5 hours)
10. **OpenAPI Examples** (1-1.5 hours)
11. **Test Coverage** (2-3 hours, optional)

**Total Estimated Time**: 8-10 hours for critical path + polish; 10-13 hours with docs/tests

---

## 🔍 Key Files to Review

### Router Files (Endpoints)
- `src/routers/agent.py` - Session CRUD
- `src/routers/agent_runs.py` - Run endpoints
- `src/routers/tools.py` - Tool execution

### Middleware & Utilities
- `src/middleware/idempotency.py` - Idempotency cache
- `src/app.py` - Global error handler, middleware setup
- `src/models/` - Pydantic schemas

### Database
- `db/postgres_control/` - Session/run/step models
- `db/redis_cache/` - Idempotency cache, rate limiting

### Tests
- `tests/test_agents_comprehensive.py` - Integration tests
- `tests/security/` - Auth/RBAC tests

---

## ✅ Success Criteria (MVP)

**Critical Path Complete When**:
- [ ] ETag: GET → 304 on If-None-Match
- [ ] Location: All POST 201s have Location header
- [ ] Pagination: `cursor`/`next_cursor` used consistently
- [ ] State: POST /steps on cancelled session → 409
- [ ] Status Codes: 201/204/304 used correctly
- [ ] All integration tests passing (27/27)

**Quality Complete When**:
- [ ] Vary headers include Authorization
- [ ] Idempotency-Key echoed + Idempotency-Replayed flag
- [ ] Run creation atomic with session updates
- [ ] No `etag` in response bodies

**Documentation Complete When**:
- [ ] OpenAPI spec regenerated with realistic examples
- [ ] All 14 areas documented/verified
- [ ] Test coverage includes all major scenarios

---

## 🚀 Next Step

**Recommended**: Start with Phase 1 (critical path) targeting completion in ~5 hours:
1. Implement ETag middleware + endpoints (2.5 hours)
2. Add Location headers to POST routes (1 hour)
3. Rename pagination fields `next_page_token` → `next_cursor` (1 hour)
4. Add session state validation on POST /steps (0.5 hours)
5. Run full test suite to verify no regressions (verification)

---

**Document**: Agents API Finalization Assessment  
**Status**: ✅ Ready for Implementation  
**Confidence**: 9/10 (Clear scope, minimal unknowns)
