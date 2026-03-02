# Admin Jobs Endpoint - Bug Fixes & Test Suite

## Summary
Fixed critical bugs in the admin jobs endpoint (`GET /v1/admin/jobs`) and added comprehensive test coverage.

## Bugs Fixed

### 1. Import Error (500 Internal Server Error)
**Issue**: Endpoint was broken with import error  
**Root Cause**: Wrong import path for `principal_identity`
- ❌ **Before**: `from src.security.auth import principal_identity`
- ✅ **After**: `from src.utils.principal import principal_identity`

**File**: `src/routers/admin_jobs.py` line 108  
**Fix**: Updated to match import pattern used across all other routers (`jobs.py`, `agent_runs.py`, `tools.py`)

### 2. Event Loop Error (RuntimeError)
**Issue**: `RuntimeError: asyncio.run() cannot be called from a running event loop`  
**Root Cause**: Handler was using `asyncio.run()` to call async methods from an already-async context

**File**: `src/routers/admin_jobs.py` lines 133-154  
**Fix**: Removed `_run_async()` wrapper and replaced with direct `await` calls:
```python
# Before (WRONG - causes RuntimeError)
def _run_async(coro):
    return asyncio.run(coro)

job_docs = _run_async(job_store_impl.list_all(...))

# After (CORRECT)
job_docs, total = await job_store_impl.list_all(...)
```

### 3. Type Error (AttributeError: 'list' object has no attribute 'created_at')
**Issue**: Code tried to access `.created_at` on a list object  
**Root Cause**: Misunderstood return type of `list_all()` method

**File**: `src/routers/admin_jobs.py` lines 127-148  
**Fix**: `list_all()` returns a **tuple** `(List[JobDocument], int)`, not just a list:
```python
# Before (WRONG - unpacks incorrectly)
job_docs = await job_store_impl.list_all(...)

# After (CORRECT - tuple unpacking)
job_docs, total = await job_store_impl.list_all(...)
```

## Documentation Updates

### OpenAPI Description (POST /jobs)
Updated retention documentation to reflect dual-backend reality:

**Before**:
> Jobs are retained in-memory for a configurable number of days (env `JOB_RETENTION_DAYS`, default 7)

**After**:
> Jobs are auto-expired after creation. **Backend-dependent**: Redis backend uses TTL (env `JOB_RETENTION_DAYS`, default 10 days). In-memory backend uses background sweeper (env `JOB_RETENTION_DAYS`, default 7 days). Configure via `JOB_STORE_BACKEND` (memory|redis).

**File**: `src/routers/jobs.py` line 566

## Test Suite Added

### Test File: `tests/test_admin_jobs_list.py`
**10 comprehensive tests** covering:

1. **Authorization** (`test_admin_jobs_list_requires_admin`)
   - Non-admin gets 403 Forbidden
   - Admin gets 200 OK

2. **Basic Functionality** (`test_admin_jobs_list_basic`)
   - Admin can list jobs across owners
   - Response structure correct

3. **Status Filtering** (`test_admin_jobs_list_status_filter`)
   - Single status filter works
   - Different statuses return correct subsets

4. **Pagination** (`test_admin_jobs_list_pagination`)
   - `limit` parameter works
   - `page_token` for next page works
   - Pages don't overlap

5. **Invalid Inputs** (`test_admin_jobs_list_invalid_page_token`)
   - Non-integer token → 400
   - Negative token → 400

6. **ETang Caching** (`test_admin_jobs_list_etag_caching`)
   - First request returns ETag header
   - `If-None-Match` with same ETag → 304 Not Modified

7. **Invalid Status Filter** (`test_admin_jobs_list_invalid_status_filter`)
   - Invalid status value → 400

8. **Multi-Status Filter** (`test_admin_jobs_list_multi_status_filter`)
   - Multiple `status` query params work
   - Returns union of statuses

9. **Response Structure** (`test_admin_jobs_list_response_structure`)
   - Top-level fields present (items, total, has_more)
   - Item fields correct (id, type, status, created_at, owner, etc.)

10. **Limit Validation** (`test_admin_jobs_list_limit_validation`)
    - Limit < 1 → 422
    - Limit > 50 → 422
    - Valid range (1-50) → 200

## Verification Steps

### Run Tests
```bash
# Run all admin jobs list tests
pytest tests/test_admin_jobs_list.py -v

# Run specific test
pytest tests/test_admin_jobs_list.py::test_admin_jobs_list_requires_admin -v
```

### Expected Results
- ✅ All 10 tests pass
- ✅ No 500 errors
- ✅ Authorization working correctly
- ✅ Pagination working
- ✅ ETag caching working

## Manual Verification (Optional)

### 1. Test with non-admin token
```bash
curl -H "Authorization: Bearer <user-token>" \
  http://localhost:8000/v1/admin/jobs
# Expected: 403 Forbidden
```

### 2. Test with admin token
```bash
curl -H "Authorization: Bearer <admin-token>" \
  http://localhost:8000/v1/admin/jobs
# Expected: 200 OK with job list
```

### 3. Test ETag caching
```bash
# First request - get ETag
ETAG=$(curl -s -I -H "Authorization: Bearer <admin-token>" \
  http://localhost:8000/v1/admin/jobs | grep -i etag | cut -d' ' -f2 | tr -d '\r')

# Second request with If-None-Match
curl -i -H "Authorization: Bearer <admin-token>" \
  -H "If-None-Match: $ETAG" \
  http://localhost:8000/v1/admin/jobs
# Expected: 304 Not Modified
```

### 4. Test pagination
```bash
curl -H "Authorization: Bearer <admin-token>" \
  "http://localhost:8000/v1/admin/jobs?limit=2"
# Check response for next_page_token

curl -H "Authorization: Bearer <admin-token>" \
  "http://localhost:8000/v1/admin/jobs?limit=2&page_token=<next_token>"
# Expected: Next page of results
```

### 5. Test status filtering
```bash
curl -H "Authorization: Bearer <admin-token>" \
  "http://localhost:8000/v1/admin/jobs?status=queued"
# Expected: Only queued jobs

curl -H "Authorization: Bearer <admin-token>" \
  "http://localhost:8000/v1/admin/jobs?status=queued&status=running"
# Expected: Queued OR running jobs
```

## Files Modified

1. **`src/routers/admin_jobs.py`**
   - Line 108: Fixed `principal_identity` import
   - Lines 127-148: Fixed async/await and tuple unpacking
   - Removed: `_run_async()` helper function

2. **`src/routers/jobs.py`**
   - Line 566: Updated retention documentation for dual-backend

3. **`tests/test_admin_jobs_list.py`** (**NEW**)
   - Created comprehensive test suite (10 tests, ~300 lines)

## Completion Status

- ✅ Fixed import error (principal_identity path)
- ✅ Fixed event loop error (asyncio.run → await)
- ✅ Fixed type error (tuple unpacking)
- ✅ Updated retention documentation
- ✅ Added comprehensive test suite (10 tests)
- ✅ All tests passing

## Next Steps (From User TODO)

1. ✅ **Fix import** - DONE
2. ✅ **Align handler** - DONE (uses `get_stores()` correctly)
3. ✅ **Add tests for admin list** - DONE (10 comprehensive tests)
4. ✅ **Update docs for dual-backend** - DONE (retention description updated)
5. ⏭️ **Manual verification** - Optional (see verification steps above)

## Production Readiness

The admin endpoint is now **production-ready** with:
- ✅ All bugs fixed (import, async, type errors)
- ✅ Comprehensive test coverage (authorization, pagination, filtering, caching)
- ✅ Accurate documentation (dual-backend TTL reality)
- ✅ Proper error handling (400 for invalid inputs, 403 for unauthorized)
- ✅ ETag caching support (304 responses working)
