# Agents API Finalization - Implementation Roadmap

**Date**: October 20, 2025  
**Phase**: Detailed Implementation Planning  
**Objective**: Execute 14 finalization items with precision  
**Estimated Duration**: 5-13 hours (critical path + optional polish)

---

## 🗺️ Implementation Roadmap by Area

### AREA 1: HTTP Caching & ETags

**Status**: 🔴 NOT IMPLEMENTED  
**Priority**: CRITICAL  
**Complexity**: HIGH (2.5 hours)  
**Risk**: Medium (new middleware component)

#### Current State
- No ETag header generation
- No `If-None-Match` support
- No 304 responses
- Response bodies may contain redundant `etag` fields

#### What Needs to Change
1. **Create ETag generation utility** (`src/utils/etag.py`)
   - Hash function combining: response content + user_id + query params + timestamp
   - Returns stable, opaque tag (e.g., SHA256 or UUID-based)
   
2. **Modify GET endpoints** in:
   - `src/routers/agent.py` → list sessions, detail session
   - `src/routers/agent_runs.py` → detail run
   - `src/routers/tools.py` → list steps in session
   
3. **Remove `etag` from response bodies** (if currently present)
   - Search: `"etag"` in response schemas
   - Remove field from Pydantic models or response builders

4. **Implement response header middleware** or endpoint decorator
   - Check request `If-None-Match` header
   - Compare with computed ETag
   - Return 304 if match (no body)
   - Return 200 with body if no match

#### Files to Create/Modify
```
CREATE:  src/utils/etag.py (100-150 lines)
MODIFY:  src/routers/agent.py (GET endpoints)
MODIFY:  src/routers/agent_runs.py (GET endpoints)
MODIFY:  src/models/ (remove etag fields from response schemas)
MODIFY:  src/middleware/ (or add new caching middleware)
```

#### Code Locations (Approximate)
- Session list: `src/routers/agent.py` line ~150 (`@router.get("/agents/sessions")`)
- Session detail: `src/routers/agent.py` line ~250 (`@router.get("/agents/sessions/{session_id}")`)
- Run detail: `src/routers/agent_runs.py` line ~100 (`@router.get("/agent-runs/{run_id}")`)

#### Verification Checklist
- [ ] `GET /agents/sessions` returns ETag header (first request)
- [ ] Second request with `If-None-Match: <ETag>` returns 304
- [ ] 304 response has no body
- [ ] ETag changes when session data updates
- [ ] Different users get different ETags (user_id included)

---

### AREA 2: Pagination Consistency

**Status**: 🟡 PARTIALLY IMPLEMENTED  
**Priority**: CRITICAL  
**Complexity**: LOW (1 hour)  
**Risk**: Low (naming/schema changes only)

#### Current State
- Request parameter: `cursor` (used)
- Response field: `next_page_token` (inconsistent naming)
- Some confusion between `page_token` and `cursor`

#### What Needs to Change
1. **Rename all `next_page_token` → `next_cursor`** in:
   - Response models/schemas
   - Examples
   - Documentation
   
2. **Verify `cursor` parameter** used consistently in:
   - `GET /agents/sessions` → query param `cursor`
   - `GET /agents/sessions/{id}/steps` → query param `cursor`
   - `GET /agent-runs` → query param `cursor`

#### Files to Modify
```
MODIFY:  src/models/agents.py (or schema file) - Response models
MODIFY:  src/routers/agent.py (response builders)
MODIFY:  src/routers/agent_runs.py (response builders)
SEARCH/REPLACE: grep -r "next_page_token" (all occurrences)
```

#### Code Locations
- Session list response: Search for response builder with pagination
- Run list response: Similar pattern in agent_runs.py

#### Verification Checklist
- [ ] All list endpoints use `cursor` in request
- [ ] All list endpoints use `next_cursor` in response (not `next_page_token`)
- [ ] Round-trip: paginate forward → no skips/dupes
- [ ] Cursor remains opaque/stable across requests
- [ ] Documentation updated with new naming

---

### AREA 3: Resource Creation Semantics (Location Header)

**Status**: 🔴 NOT IMPLEMENTED  
**Priority**: CRITICAL  
**Complexity**: LOW (1 hour)  
**Risk**: Low (header addition only)

#### Current State
- POST endpoints return 201 without `Location` header
- Response body contains resource data but clients must infer URL

#### What Needs to Change
1. **Add `Location` header** to POST 201 responses:
   - `POST /agents/sessions` → `Location: /agents/sessions/{session_id}`
   - `POST /agents/sessions/{id}/steps` → `Location: /agents/sessions/{id}/steps/{step_id}`
   - `POST /agent-runs` → `Location: /agent-runs/{run_id}`

2. **Implementation pattern** (in each POST endpoint):
   ```python
   return JSONResponse(
       status_code=201,
       content=response_body,
       headers={"Location": f"/agents/sessions/{session_id}"}
   )
   ```

#### Files to Modify
```
MODIFY:  src/routers/agent.py - POST /agents/sessions
MODIFY:  src/routers/agent.py - POST /agents/sessions/{id}/steps
MODIFY:  src/routers/agent_runs.py - POST /agent-runs
```

#### Code Locations (Approximate)
- Session creation: `src/routers/agent.py` ~line 120-180 (find `POST /agents/sessions`)
- Step creation: `src/routers/agent.py` ~line 350-420 (find `POST .../steps`)
- Run creation: `src/routers/agent_runs.py` ~line 50-100 (find `POST /agent-runs`)

#### Verification Checklist
- [ ] POST /sessions returns 201 with `Location: /agents/sessions/{id}`
- [ ] POST /sessions/{id}/steps returns 201 with `Location: /agents/sessions/{id}/steps/{sid}`
- [ ] POST /agent-runs returns 201 with `Location: /agent-runs/{id}`
- [ ] Location header is valid URL (can be followed with GET)

---

### AREA 4: Idempotency (Headers + Status)

**Status**: 🟡 PARTIALLY IMPLEMENTED  
**Priority**: CRITICAL  
**Complexity**: MEDIUM (45 minutes)  
**Risk**: Low (middleware enhancement)

#### Current State
✅ **Already working**:
- Original status code preserved on replay (verified)
- Idempotency-Key stored and checked
- Response body cached correctly

❌ **Missing**:
- Echo `Idempotency-Key` header in responses
- Include `Idempotency-Replayed: true` header on replays
- DELETE idempotency (should return 204 both times)

#### What Needs to Change
1. **Enhance idempotency middleware** (`src/middleware/idempotency.py`):
   - Extract `Idempotency-Key` from request headers
   - Echo it back in response headers (always, if present)
   - Add `Idempotency-Replayed: true` on cache hits (replay)
   - Verify DELETE returns 204 on both attempts

2. **Implementation pattern**:
   ```python
   # In middleware/handler
   idempotency_key = request.headers.get("Idempotency-Key")
   if idempotency_key:
       response.headers["Idempotency-Key"] = idempotency_key
   
   if cache_hit:
       response.headers["Idempotency-Replayed"] = "true"
   ```

#### Files to Modify
```
MODIFY:  src/middleware/idempotency.py - Add header echo + replay flag
MODIFY:  src/routers/agent.py - DELETE endpoint (verify 204 idempotency)
TEST:    tests/test_agents_comprehensive.py - Add header verification
```

#### Code Locations
- Idempotency middleware: `src/middleware/idempotency.py` (main logic)
- POST endpoints: Any route decorated with idempotency handling
- DELETE: `src/routers/agent.py` (find `DELETE /agents/sessions/{id}` or similar)

#### Verification Checklist
- [ ] POST with `Idempotency-Key: xyz` → Response includes `Idempotency-Key: xyz`
- [ ] First POST → no `Idempotency-Replayed` header
- [ ] Second POST (same key) → includes `Idempotency-Replayed: true`
- [ ] DELETE twice → 204 both times
- [ ] Status code preserved (201 create, 200 update, 204 delete)

---

### AREA 5: Problem+JSON Uniformity

**Status**: 🟢 MOSTLY IMPLEMENTED  
**Priority**: MEDIUM  
**Complexity**: LOW (20 minutes verify + 30 min fix if needed)  
**Risk**: Low (documentation/verification)

#### Current State
✅ **Already working** (from finalization tasks 1-5):
- RFC-7807 format implemented
- `correlation_id` + `timestamp` in extensions
- `type`, `title`, `status`, `detail`, `instance` fields

❌ **Might need**:
- Replace `type: "about:blank"` with meaningful URLs (optional)
- Verify all error paths return `application/problem+json`
- Ensure `extensions` includes endpoint-specific error codes

#### What Needs to Change
1. **Verify content-type** on all error responses
2. **Check `extensions` includes**:
   - `correlation_id` (required)
   - `timestamp` (required, already added)
   - `error_code` (endpoint-specific, optional but recommended)
   - Any other domain-specific data

3. **Optional enhancement**: Replace generic `about:blank` with specific error types:
   - `urn:cineca:error:session-not-found`
   - `urn:cineca:error:session-not-active`
   - etc.

#### Files to Check
```
CHECK:   src/app.py - Global exception handlers
CHECK:   src/routers/agent.py - Endpoint-specific error handling
CHECK:   tests/ - Error response examples
```

#### Verification Checklist
- [ ] All 4xx responses have `Content-Type: application/problem+json`
- [ ] All 5xx responses have `Content-Type: application/problem+json`
- [ ] All errors include `correlation_id` + `timestamp`
- [ ] Spot-check 3-4 error responses for complete field set

---

### AREA 6: Agent Run Persistence & Retrieval

**Status**: 🟡 NEEDS VERIFICATION  
**Priority**: HIGH  
**Complexity**: MEDIUM (1 hour)  
**Risk**: Medium (atomicity concerns)

#### Current State
- Run creation likely works (POST /agent-runs)
- Need to verify atomicity and session linkage

#### What Needs to Change
1. **Verify transaction handling** in `POST /agent-runs`:
   - Create run record
   - If linked to session: update session.last_step_id, session.status
   - Persist steps atomically
   - All-or-nothing (no orphans)

2. **Verify GET /agent-runs/{run_id}** returns created run
   - Accessible immediately after POST 201
   - Shows correct relations to session

3. **Test atomic updates**:
   - Create run → session fields updated (same transaction)
   - Crash scenario: no orphaned runs/steps

#### Files to Check
```
CHECK:   src/routers/agent_runs.py - POST /agent-runs (transaction handling)
CHECK:   db/postgres_control/ - Run/step models, session update logic
TEST:    tests/ - Run creation and retrieval tests
```

#### Verification Checklist
- [ ] POST /agent-runs → creates run record
- [ ] GET /agent-runs/{id} returns 200 with correct data
- [ ] If run linked to session → session state updated atomically
- [ ] No orphaned runs/steps after DB errors

---

### AREA 7: Field Naming & Defaults

**Status**: 🟡 NEEDS STANDARDIZATION  
**Priority**: MEDIUM  
**Complexity**: LOW (30 minutes)  
**Risk**: Low (schema changes only)

#### Current State
- May have mixed use of `metadata` vs `session_metadata`
- Defaults might vary between request/response (0 vs 0.7)
- `manager` field might not be consistently typed

#### What Needs to Change
1. **Unify field names**:
   - Choose `metadata` for both request and response (replace `session_metadata`)
   - Apply consistently across all session endpoints

2. **Normalize defaults**:
   - `temperature`: 0.7 (consistent between schema and examples)
   - `max_steps`: 10 (or document consistent default)
   - `manager`: enum (`auto`, `manual`) with consistent default

3. **Search and replace**:
   ```bash
   grep -r "session_metadata" src/
   grep -r "temperature.*0" src/  # Check for inconsistencies
   ```

#### Files to Modify
```
SEARCH:  grep -r "session_metadata" (find all)
REPLACE: session_metadata → metadata
MODIFY:  src/models/ - Schema defaults
MODIFY:  src/routers/ - Response builders
```

#### Verification Checklist
- [ ] No `session_metadata` in code (all changed to `metadata`)
- [ ] Create session → GET session shows same field names
- [ ] Defaults consistent (request schema = response examples)

---

### AREA 8: Session State Transitions

**Status**: 🔴 NOT IMPLEMENTED  
**Priority**: CRITICAL  
**Complexity**: MEDIUM (1.5 hours)  
**Risk**: Medium (business logic)

#### Current State
- Probably no state validation on POST /steps
- Can add steps to any session (including cancelled)

#### What Needs to Change
1. **Enforce session state** on `POST /agents/sessions/{id}/steps`:
   - Check `session.status == "active"`
   - Reject if `cancelled` or `completed`
   - Return 409 Conflict with problem+json

2. **State enum** for sessions (likely already exists):
   - `active`, `cancelled`, `completed`, `paused` (etc.)
   - Verify used consistently

3. **Cancellation logic**:
   - Cancel should set status to `cancelled`
   - Prevent further step creation

4. **Error response format**:
   ```json
   {
     "type": "about:blank",
     "title": "Conflict",
     "status": 409,
     "detail": "Cannot add step to cancelled session",
     "instance": "/agents/sessions/{id}/steps",
     "extensions": {
       "correlation_id": "...",
       "timestamp": "...",
       "error_code": "SESSION_NOT_ACTIVE"
     }
   }
   ```

#### Files to Modify
```
MODIFY:  src/routers/agent.py - POST /agents/sessions/{id}/steps (add state check)
CHECK:   src/models/ - Session state enum/field
TEST:    tests/ - Add test for state validation
```

#### Code Locations
- Step creation: `src/routers/agent.py` (find `POST .../steps`)
- Session model: `db/postgres_control/` or `src/models/`

#### Verification Checklist
- [ ] POST /steps on active session → 201 (works)
- [ ] POST /steps on cancelled session → 409 Conflict
- [ ] 409 response is problem+json with `error_code: SESSION_NOT_ACTIVE`
- [ ] Cancel endpoint sets status to `cancelled`
- [ ] After cancel, new POST /steps → 409

---

### AREA 9: Rate-Limit Headers

**Status**: 🟡 PARTIALLY IMPLEMENTED  
**Priority**: MEDIUM  
**Complexity**: LOW (if already present)  
**Risk**: Low

#### Current State
✅ **Likely already implemented**:
- Rate limit middleware probably returns `X-RateLimit-*` headers
- Health endpoint reports rate limits

❌ **To verify**:
- Headers present on success (200)
- Headers present on 429 (including `Retry-After`)

#### What to Check
1. **Headers on 200 responses**:
   - `X-RateLimit-Limit` (max requests in window)
   - `X-RateLimit-Remaining` (requests left)
   - `X-RateLimit-Reset` (unix timestamp of reset time)

2. **Headers on 429 responses**:
   - Same as above
   - Plus `Retry-After` (seconds to wait)

#### Files to Check
```
CHECK:   src/middleware/ - Rate limit middleware
CHECK:   db/redis_cache/rate_limit.py - Rate limit logic
TEST:    tests/ - Spot-check response headers
```

#### Verification Checklist
- [ ] GET /agents/sessions → includes `X-RateLimit-*` headers
- [ ] Forced 429 (exceeded limit) → includes all headers + `Retry-After`
- [ ] `X-RateLimit-Remaining` decrements on each request
- [ ] `X-RateLimit-Reset` is unix timestamp (not relative)

---

### AREA 10: RBAC & Multi-Tenancy Checks

**Status**: 🟢 MOSTLY IMPLEMENTED  
**Priority**: HIGH  
**Complexity**: MEDIUM (1 hour verify)  
**Risk**: Medium (security-critical)

#### Current State
✅ **Likely working**:
- Auth middleware validates tokens
- Permissions checked on endpoints
- Multi-tenant isolation in DB queries

❌ **To verify**:
- List endpoints filter by user/tenant
- Detail endpoints enforce visibility
- Admin scope bypasses restrictions

#### What to Check
1. **List endpoints filter**:
   - `GET /agents/sessions` → only user's sessions (unless admin)
   - `GET /agent-runs` → only user's runs (unless admin)

2. **Detail endpoints enforce**:
   - `GET /agents/sessions/{id}` → 404 or 403 if not owned
   - `GET /agent-runs/{id}` → 404 or 403 if not owned

3. **Admin scope**:
   - `admin:all` scope bypasses filters
   - Can access any resource

#### Files to Check
```
CHECK:   src/middleware/auth.py - Token validation
CHECK:   src/routers/agent.py - Session filtering logic
CHECK:   src/routers/agent_runs.py - Run filtering logic
TEST:    tests/security/ - RBAC tests
```

#### Verification Checklist
- [ ] Non-admin user cannot list other users' sessions
- [ ] Non-admin cannot GET another user's session (403)
- [ ] Admin user can access any session
- [ ] Multi-tenant: tenant filters applied correctly
- [ ] RBAC tests pass (8/8)

---

### AREA 11: Headers Hygiene (X-Request-Id, Vary)

**Status**: 🟡 PARTIALLY IMPLEMENTED  
**Priority**: MEDIUM  
**Complexity**: LOW (30 minutes)  
**Risk**: Low

#### Current State
✅ **Already implemented**:
- `X-Request-Id` header present
- Propagated as `correlation_id` in errors

❌ **Needs enhancement**:
- `Vary: Origin` probably present
- Missing `Vary: Authorization` on cached endpoints

#### What Needs to Change
1. **Add `Authorization` to Vary header**:
   - On cached GET endpoints (those returning ETag)
   - Prevents cross-user cache bleed
   - Combined with Origin: `Vary: Origin, Authorization, X-Default-Scope, X-Tenant-Id`

2. **Verify X-Request-Id**:
   - Generated at request entry
   - Propagated through middleware
   - Included in error responses

#### Files to Modify
```
MODIFY:  src/middleware/ - Add Authorization to Vary (cached endpoints)
CHECK:   src/app.py - Verify X-Request-Id propagation
```

#### Verification Checklist
- [ ] GET /agents/sessions includes `Vary: Origin, Authorization, ...`
- [ ] Different auth tokens don't share cache (304)
- [ ] Same auth token gets cache hits (304)
- [ ] Error responses include `correlation_id`

---

### AREA 12: OpenAPI Spec & Examples

**Status**: 🟡 NEEDS UPDATE  
**Priority**: MEDIUM  
**Complexity**: MEDIUM (1-1.5 hours)  
**Risk**: Low (documentation only)

#### Current State
- OpenAPI spec generated by FastAPI
- May have `"string"` placeholders in examples
- May not document idempotency/Location/ETag semantics

#### What Needs to Change
1. **Update response examples** with realistic values:
   - `session_id`: `"550e8400-e29b-41d4-a716-446655440000"` (not `"string"`)
   - `timestamp`: `"2025-10-20T09:31:45.123456Z"` (ISO-8601)
   - `manager`: `"auto"` or `"manual"` (enum, not `"string"`)
   - `cursor`: `"abc123def456"` or `null` (not `"string"`)

2. **Document headers**:
   - `Idempotency-Key` (request header)
   - `Idempotency-Replayed` (response header)
   - `Location` (response header on POST 201)
   - `ETag` (response header on GET)
   - `X-RateLimit-*` (response headers)

3. **Document error handling**:
   - `problem+json` content-type
   - Example 409 response for invalid state
   - Example 304 Not Modified response

#### Files to Modify
```
MODIFY:  src/routers/agent.py - Endpoint docstrings (response examples)
MODIFY:  src/routers/agent_runs.py - Similar updates
MODIFY:  src/models/ - Schema docstrings with realistic examples
CHECK:   api/openapi.json (regenerated spec)
```

#### Verification Checklist
- [ ] Regenerate OpenAPI: `FastAPI generates spec with new examples`
- [ ] No `"string"` placeholders in spec
- [ ] Headers documented in operations
- [ ] Example responses match actual API responses
- [ ] Error scenarios documented (409, 304, etc.)

---

### AREA 13: Storage Boundaries (Quick Verification)

**Status**: 🟢 LIKELY CORRECT  
**Priority**: LOW  
**Complexity**: LOW (20 minutes verify)  
**Risk**: Low (architectural check)

#### Current State
✅ **Probably correct**:
- PostgreSQL used for durable state (sessions, steps, runs)
- Redis used for temporary data (caching, rate limits)

❌ **To verify**:
- No leakage between stores
- Cold start (Redis empty) still works
- Idempotency keys survive DB writes

#### What to Verify
1. **PostgreSQL responsibilities**:
   - Sessions, steps, runs (durable)
   - Timestamps, relationships
   - User/tenant metadata

2. **Redis responsibilities**:
   - Idempotency cache (with original status + body)
   - Rate-limit counters
   - ETag materialization (optional)
   - Short-lived cursors/tokens

3. **Test scenarios**:
   - Redis flush → DB still has full history
   - Replay after Redis restart → works from DB
   - No orphaned records on failure

#### Files to Check
```
CHECK:   db/postgres_control/ - Session/run models (persistence)
CHECK:   db/redis_cache/ - Idempotency, rate-limit logic
CHECK:   src/routers/ - Query patterns (read from DB vs cache)
```

#### Verification Checklist
- [ ] Session creation → persisted in PostgreSQL immediately
- [ ] Idempotency key + response cached in Redis
- [ ] Redis flush doesn't delete sessions from DB
- [ ] Rate limit state in Redis, not DB
- [ ] Cold start: full session history available

---

### AREA 14: Tests to Add/Update (No Code, Scope Only)

**Status**: 🟡 PARTIAL COVERAGE  
**Priority**: MEDIUM  
**Complexity**: MEDIUM (2-3 hours for comprehensive suite)  
**Risk**: Low (testing)

#### Current Test Coverage
✅ **Already have** (27/27 passing):
- Session CRUD
- Step operations
- Run operations
- Idempotency (basic)
- ETag Caching (likely)
- Rate Limiting
- Error Handling
- RBAC

❌ **Tests to add/enhance**:

1. **ETag 200→304 cycles** (30 min)
   - GET endpoint → store ETag
   - Repeat with If-None-Match → 304
   - Verify no body in 304
   - Different user → 200 (not 304)

2. **Cursor naming & traversal** (20 min)
   - GET /sessions?cursor=null → first page
   - Store `next_cursor` from response
   - GET /sessions?cursor=<next_cursor> → second page
   - Verify no skips/duplicates

3. **Location header on 201s** (15 min)
   - POST /sessions → Location header present
   - Follow Location with GET → 200
   - Verify response matches create body

4. **Idempotent replay** (15 min, already covered but enhance)
   - Verify original status preserved
   - Check `Idempotency-Replayed: true` header

5. **Step creation on cancelled session** (15 min)
   - Create session
   - Cancel it
   - POST /steps → 409 Conflict
   - Verify error is problem+json

6. **Run create → get round-trip** (15 min)
   - POST /agent-runs → 201
   - GET /agent-runs/{id} → 200
   - Verify session linkage

7. **Rate-limit headers on 200/429** (15 min)
   - GET → verify headers present
   - Force 429 → verify headers + Retry-After

8. **Vary header includes Authorization** (10 min)
   - GET with different auth → verify Vary header
   - No cache bleed between users

9. **Error content-type uniformity** (10 min)
   - Spot-check 5 error endpoints
   - Verify `application/problem+json`

#### Test Files
```
CREATE/MODIFY:  tests/test_agents_comprehensive.py
CREATE/MODIFY:  tests/test_etag_caching.py (new, optional)
CREATE/MODIFY:  tests/test_state_validation.py (new, optional)
CREATE/MODIFY:  tests/security/ (enhance RBAC tests)
```

#### Verification Checklist
- [ ] ETag tests: 304 on If-None-Match
- [ ] Pagination tests: cursor works across pages
- [ ] Location tests: header present, followable
- [ ] Idempotency tests: replay has correct header
- [ ] State validation tests: 409 on invalid transition
- [ ] Run tests: create→get round-trip
- [ ] Rate-limit tests: headers present
- [ ] Vary tests: no cross-user cache
- [ ] Error tests: all responses have problem+json
- [ ] All 37+ tests pass (27 original + 10+ new)

---

## 🗂️ File Organization Summary

### Files to Create
```
src/utils/etag.py                    ← ETag generation utility
tests/test_etag_caching.py           ← ETag-specific tests (optional)
tests/test_state_validation.py       ← State enforcement tests (optional)
```

### Files to Modify (Core)
```
src/routers/agent.py                 ← Add Location headers, state validation
src/routers/agent_runs.py            ← Add Location headers, run verification
src/middleware/idempotency.py        ← Add header echo + replay flag
src/middleware/caching.py            ← Add ETag header + 304 support (or modify existing)
src/app.py                           ← Verify problem+json uniformity
```

### Files to Search & Replace
```
src/models/                          ← Remove etag fields, rename pagination
src/routers/                         ← Verify state validation, field naming
db/postgres_control/                 ← Verify atomicity, run persistence
```

### Files to Verify (No Changes Needed)
```
src/middleware/auth.py               ← RBAC logic (likely correct)
db/redis_cache/                      ← Rate limits, idempotency (likely correct)
tests/security/                      ← RBAC tests (verify coverage)
```

---

## ⏱️ Time Budget Breakdown

### Critical Path (Must Do)
| Item | Time | Notes |
|------|------|-------|
| ETag Implementation | 2.5h | Highest complexity |
| Location Headers | 1h | Simple addition |
| Pagination Naming | 1h | Search/replace |
| State Validation | 1h | Business logic |
| **Subtotal** | **5.5h** | Can deploy after this |

### High Priority (Should Do)
| Item | Time | Notes |
|------|------|-------|
| Idempotency Headers | 0.75h | Middleware enhancement |
| Vary Headers | 0.5h | Quick addition |
| Run Persistence | 0.75h | Verification mainly |
| **Subtotal** | **2h** | Adds quality |

### Lower Priority (Nice to Have)
| Item | Time | Notes |
|------|------|-------|
| Field Naming | 0.5h | Low risk |
| Content-Type Verify | 0.5h | Verification |
| OpenAPI Examples | 1.5h | Documentation |
| Test Coverage | 2.5h | Optional for MVP |
| **Subtotal** | **5h** | Polish & docs |

**Total**: ~5.5h critical, ~7.5h with high-priority, ~12.5h with all optional items

---

## 🚀 Recommended Execution Strategy

### Sequence
1. **Start with ETag** (most complex, but core value)
2. **Add Location headers** (quick win while in routers)
3. **Fix pagination naming** (search/replace, low risk)
4. **Add state validation** (business logic)
5. **Run tests** (verify no regressions)
6. **Add idempotency headers** (if time)
7. **Polish & document** (OpenAPI examples, test coverage)

### Daily Target
- **Day 1 (5-6 hours)**: Critical path (items 1-4 + testing)
- **Day 2 (2-3 hours)**: High priority (items 5-6)
- **Day 3 (optional)**: Lower priority & documentation (items 7-14)

---

**Document**: Agents API Finalization - Implementation Roadmap  
**Status**: 📋 Ready for Execution  
**Next Step**: Start with Area 1 (ETag Implementation)
