# Jobs API Polish & Bug Fixes - Progress Summary

## Completed Items (1-5 of 10)

### ✅ Item 1: Fix DELETE /jobs/{job_id} asyncio.run crash

**Problem:** DELETE endpoint crashed with `RuntimeError: asyncio.run() cannot be called from a running event loop`

**Solution:**
- Removed `asyncio.run()` wrapper from async request handler
- Used direct `await` on async store methods
- Preserved `_run_async()` helper for background worker threads (with updated documentation)

**Tests Created:** `tests/test_delete_job_fix.py` (9 tests, all passing)
- First cancel returns 202 Accepted
- Subsequent cancels return 200 OK (idempotent)
- Proper error handling (400/401/403/404)
- No event loop crashes

**Files Modified:**
- `src/routers/jobs.py` (lines 490-530)

---

### ✅ Item 2: Fix DELETE /admin/jobs/{job_id} proxy

**Status:** Already correct - no changes needed

**Verification:**
- Admin DELETE properly delegates to canonical handler with `await`
- Preserves 202/200 status codes
- Guards with `admin:all` permission
- No asyncio.run() issues

**Implementation:** `src/routers/admin_jobs.py` (lines 344-362)

---

### ✅ Item 3: OpenAPI & docs consistency

**Changes Made:**

1. **SSE endpoint (`/v1/jobs/{job_id}/events`):**
   - ✅ OpenAPI advertises only `text/event-stream` (verified)
   - ✅ Updated deployment note to clarify Redis vs memory behavior:
     - **Redis**: Ring buffer and IDs are durable, multi-replica safe
     - **Memory**: Single-process only, not safe for horizontal scaling

2. **POST endpoint (`/v1/jobs`):**
   - ✅ Retention docs already mention dual backend (10d Redis, 7d memory)
   - ✅ References `JOB_STORE_BACKEND` environment variable

3. **Admin jobs list (`/v1/admin/jobs`):**
   - ✅ Parameter validation docs list only `status`, `limit`, `page_token`

**Verification:**
```bash
python -c "from src.app import app; print(app.openapi()['paths']['/v1/jobs/{job_id}/events']['get']['responses']['200']['content'].keys())"
# Output: dict_keys(['text/event-stream'])
```

**Files Modified:**
- `src/routers/jobs.py` (lines 920-930: deployment note)

---

### ✅ Item 4: ETag, caching, Vary headers parity

**Verification Results:**

1. **Vary: Authorization header:**
   - ✅ `GET /v1/jobs/{job_id}` - present
   - ✅ `GET /v1/admin/jobs` - present
   - ✅ All GET endpoints include it

2. **ETag behavior:**
   - ✅ ETags are weak (prefixed with `W/"`)
   - ✅ ETags are stable for identical content
   - ✅ `If-None-Match` returns 304 Not Modified
   - ✅ 304 responses include stable ETag and Vary header

3. **Cache-Control:**
   - ✅ Job detail: `private, max-age=15`
   - ✅ Job list: `private, max-age=30`
   - ✅ 304 responses also include Cache-Control

**Tests Created:** `tests/test_etag_caching.py` (7 tests, all passing)
- Vary: Authorization on all GET routes
- Weak ETags are stable
- If-None-Match returns 304 with matching ETag
- Cache-Control headers appropriate

**No code changes needed** - behavior already correct!

---

### ✅ Item 5: Idempotency correctness (admin proxy)

**Verification Results:**

1. **Admin POST proxy (`/v1/admin/jobs`):**
   - ✅ Passes through `Idempotency-Key` header
   - ✅ Passes through `Idempotency-Replayed` header
   - ✅ Passes through `Location` header
   - ✅ Preserves status codes (202 fresh, 200 replay)

2. **Cross-endpoint consistency:**
   - ✅ Admin POST with same Idempotency-Key as canonical POST returns same job
   - ✅ Headers match canonical behavior exactly

**Tests Created:** `tests/test_admin_idempotency.py` (6 tests, all passing)
- Idempotency-Key passthrough
- Idempotency-Replayed on replay (200 vs 202)
- Location header present
- Status codes preserved
- Identical behavior to canonical POST

**No code changes needed** - implementation already correct!

---

## Remaining Items (6-10)

### 🔲 Item 6: SSE behavior checks
- Verify retry header (1000-60000 ms)
- Monotonic event IDs
- Last-Event-ID resume
- Heartbeats every 15s (non-terminal only)
- Single `event: end` then close

### 🔲 Item 7: Error semantics & problem responses
- 400 for malformed UUID
- 404 for not found
- 403 for missing admin:all
- Use application/problem+json

### 🔲 Item 8: Tests - extend and parametrize
- Parametrize for memory/redis backends
- SSE resume tests
- More comprehensive coverage

### 🔲 Item 9: CI & smoke updates
- CI matrix for both backends
- Smoke script updates

### 🔲 Item 10: Observability & ops notes
- Metrics verification
- Documentation updates

---

## Test Summary

**Total Tests Created:** 22 tests across 3 files
**All Tests Passing:** ✅

1. **test_delete_job_fix.py** - 9 tests
   - DELETE endpoint behavior (202→200)
   - Error handling (400/401/403/404)
   - No asyncio.run() crashes

2. **test_etag_caching.py** - 7 tests
   - Vary: Authorization headers
   - ETag stability and 304 responses
   - Cache-Control headers

3. **test_admin_idempotency.py** - 6 tests
   - Idempotency header passthrough
   - Status code preservation
   - Cross-endpoint consistency

---

## Files Modified

1. **src/routers/jobs.py**
   - Fixed DELETE asyncio.run() crash
   - Updated SSE deployment note

2. **tests/** (3 new files)
   - test_delete_job_fix.py
   - test_etag_caching.py
   - test_admin_idempotency.py

3. **Documentation**
   - DELETE_FIX_SUMMARY.md (detailed bug fix doc)

---

## Next Steps

Items 6-10 remain. These focus on:
- SSE behavior verification (streaming, resume, heartbeats)
- Error response standardization (problem+json)
- Backend parametrization for tests
- CI/smoke test updates
- Observability metrics and documentation

**Progress: 5/10 items complete (50%)**
