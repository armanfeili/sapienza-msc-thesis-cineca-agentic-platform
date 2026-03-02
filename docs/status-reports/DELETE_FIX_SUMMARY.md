# DELETE Endpoint asyncio.run() Fix - Summary

## Problem Statement

The `DELETE /jobs/{job_id}` endpoint was crashing with:
```
RuntimeError: asyncio.run() cannot be called from a running event loop
```

This occurred because the async request handler was calling `asyncio.run()` to execute async store operations, which is not allowed within an already-running event loop (FastAPI's async context).

## Root Cause

In `src/routers/jobs.py`, the `cancel_job()` async handler used a helper function `_run_async()` that wrapped async operations with `asyncio.run()`:

```python
def _run_async(coro):
    return asyncio.run(coro)

async def cancel_job(job_id: str, user = Depends(...)) -> Response:
    # ...
    job_doc = _run_async(job_store_impl.get(job_id))  # ❌ CRASH!
    # ...
    first_cancel = _run_async(job_store_impl.cancel_job_atomic(job_id))  # ❌ CRASH!
    # ...
    _run_async(job_store_impl.update_status(...))  # ❌ CRASH!
```

## Solution Applied

### 1. Fixed DELETE /jobs/{job_id} (Lines 490-530)

**Changed:**
- Removed `_run_async()` wrapper calls
- Used direct `await` on async store methods
- Removed unused `import asyncio` from the handler

**Code diff:**
```python
# BEFORE:
async def cancel_job(...):
    import asyncio
    
    def _run_async(coro):
        return asyncio.run(coro)
    
    job_doc = _run_async(job_store_impl.get(job_id))
    first_cancel = _run_async(job_store_impl.cancel_job_atomic(job_id))
    _run_async(job_store_impl.update_status(...))

# AFTER:
async def cancel_job(...):
    job_doc = await job_store_impl.get(job_id)
    first_cancel = await job_store_impl.cancel_job_atomic(job_id)
    await job_store_impl.update_status(...)
```

### 2. Preserved _run_async() for Background Workers (Lines 40-48)

The `_run_async()` helper is **still needed** for background worker threads spawned via `threading.Thread`. Updated the docstring to clarify safe usage:

```python
def _run_async(coro):
    """Helper to run async operations in sync context (for worker threads).
    
    IMPORTANT: This is ONLY safe to use in background worker threads spawned
    by threading.Thread, NOT in FastAPI request handlers which already run
    in an async event loop. Request handlers should use 'await' directly.
    """
    return asyncio.run(coro)
```

**Why this is safe:**
- Background workers run in separate threads (not in the main event loop)
- Each thread creates its own event loop via `asyncio.run()`
- No conflict with FastAPI's request handling event loop

### 3. Admin DELETE Endpoint Already Correct

The admin endpoint (`DELETE /admin/jobs/{job_id}`) correctly delegates to the canonical handler:

```python
async def cancel_job_proxy(job_id: str, user: UserInfo = Depends(...)):
    return await cancel_job_canonical(job_id, user)  # ✅ Correct!
```

No changes needed - it was already using `await` properly.

## Tests Added

Created `tests/test_delete_job_fix.py` with 9 comprehensive tests:

1. ✅ `test_delete_job_first_cancel_202` - First DELETE returns 202 Accepted
2. ✅ `test_delete_job_subsequent_cancel_200` - Subsequent DELETE returns 200 OK (idempotent)
3. ✅ `test_delete_job_already_finished_200` - DELETE on finished job returns 200
4. ✅ `test_delete_job_invalid_uuid_400` - Invalid UUID returns 400 Bad Request
5. ✅ `test_delete_job_not_found_404` - Non-existent job returns 404 Not Found
6. ✅ `test_delete_job_no_auth_401` - No auth returns 401 Unauthorized
7. ✅ `test_delete_job_insufficient_perms_403` - Missing admin:all returns 403 Forbidden
8. ✅ `test_delete_job_cache_control_header` - Response has Cache-Control: no-store
9. ✅ `test_delete_no_asyncio_crash` - No event loop crash with multiple concurrent DELETEs

**All tests pass:** `9 passed, 3 warnings`

## Behavior Verification

### Memory Backend (default)
- First cancel: queued/running → cancelled (202 Accepted)
- Subsequent cancels: already cancelled (200 OK)
- Already finished: stays finished (200 OK)

### Redis Backend
- First cancel: atomic Lua script CAS (202 Accepted)
- Subsequent cancels: idempotent (200 OK)
- Concurrency safe: Lua script ensures atomic state transitions

## Files Modified

1. **src/routers/jobs.py**
   - Line 490-530: Fixed `cancel_job()` handler (removed asyncio.run, added await)
   - Line 40-48: Updated `_run_async()` docstring (clarified thread-only usage)

2. **tests/test_delete_job_fix.py**
   - Created: 9 comprehensive tests for DELETE endpoint

## Admin Endpoint Status

The admin endpoint (`DELETE /admin/jobs/{job_id}`) was already correct:
- ✅ Properly delegates to canonical handler with `await`
- ✅ Preserves 202/200 status codes
- ✅ Guards with `admin:all` permission
- ✅ No asyncio.run() issues

## Definition of Done - Status

✅ **Item 1: Fix DELETE /jobs/{job_id}** - COMPLETE
- No asyncio.run() in request handler
- Uses await for all async operations
- Returns 202 on first cancel, 200 on subsequent
- Works with both memory and Redis backends
- 9 comprehensive tests pass

✅ **Item 2: Fix DELETE /admin/jobs/{job_id}** - COMPLETE (Already correct)
- Admin proxy uses await (no asyncio.run)
- Delegates to canonical handler
- Preserves 202/200 status codes
- No changes needed

## Next Steps

Continue with remaining TODO items:
- Item 3: OpenAPI & docs consistency
- Item 4: ETag, caching, Vary headers parity
- Item 5: Idempotency correctness (admin proxy)
- Item 6: SSE behavior checks
- Item 7: Error semantics & problem responses
- Item 8: Tests: extend and parametrize
- Item 9: CI & smoke updates
- Item 10: Observability & ops notes
