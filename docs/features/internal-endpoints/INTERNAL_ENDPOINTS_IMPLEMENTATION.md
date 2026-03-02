# Internal Endpoints Implementation Summary

## Overview

This document describes the implementation of internal-ops and internal-db endpoints according to the specification. These endpoints are secured with internal-only access (service tokens) and implement proper RBAC, observability, idempotency, and RFC 7807 error handling.

## Security Implementation

### New Security Module: `src/security/internal.py`

Created a new security module that enforces internal-only access:

- **`has_internal_access(principal)`**: Checks if principal has internal access via:
  - Service token indicator (custom 'service' claim in JWT)
  - `internal:all` scope/permission
  - **Admin tokens (admin:all) do NOT grant internal access**

- **`require_internal()`**: FastAPI dependency that enforces internal access
  - Returns 401 for missing/invalid tokens
  - Returns 403 for non-internal tokens (including admin tokens)

## Database Models

### New PostgreSQL Model: `InternalOpsEvent`

Created `db/postgres_control/models/internal_ops_event.py` for audit trail:

**Fields:**
- `id`: BigInteger primary key
- `kind`: Event type (e.g., 'auto_start_override', 'preview_staged')
- `sub`: Actor subject (who performed the action)
- `enabled`: Boolean flag (for auto_start_override)
- `note`: Optional text note/reason
- `data_json`: Additional structured data (JSONB)
- `ts`: Timestamp with timezone

**Indexes:**
- `idx_internal_ops_events_kind_ts` (kind, ts)
- `idx_internal_ops_events_sub_ts` (sub, ts)

### Database Migration

Created Alembic migration `012_create_internal_ops_events.py`:
- Creates `internal_ops_events` table
- Creates composite indexes
- Includes upgrade and downgrade functions

## Internal-Ops Endpoints

### POST /v1/internal/ops/auto-start-override

**Purpose:** Set temporary auto-start UI override

**Storage:**
- **Redis** (ephemeral):
  - Key: `internal:auto_start_override`
  - Fields: `enabled`, `note`, `set_by_sub`, `set_at`, `ttl_seconds`
  - TTL: Configurable (default 10 minutes), sliding on renewal
  
- **PostgreSQL** (persistent audit):
  - Appends event to `internal_ops_events` table
  - Fields: `kind='auto_start_override'`, `sub`, `enabled`, `note`, `ts`

**Behavior:**
- Validates against `INTERNAL_UI_OVERRIDE_ALLOWED` config
- If disabled → returns `allowed=false`, `enabled=false`, `ttl=0`
- If enabled → stores override in Redis with TTL
- Tracks actor in audit log (not in response)

**Request:**
```json
{
  "enabled": true,
  "note": "Emergency override during incident"
}
```

**Response (200):**
```json
{
  "allowed": true,
  "enabled": true,
  "ttl_seconds": 600
}
```

**Errors:**
- 400: Invalid payload
- 401: Missing/invalid token
- 403: Requires internal access
- 500: Storage failure

### GET /v1/internal/ops/preview-staged

**Purpose:** Preview auto-start recommendations for staged manifests (read-only)

**Storage:**
- **Redis** (optional cache):
  - Key: `internal:preview_staged:cache`
  - Value: JSON list of preview items
  - TTL: 30 seconds (for UX snappiness)
  
- **PostgreSQL:** None (read-only diagnostic)

**Behavior:**
- Reads staged manifests from `builtins:staged`
- Reads current override from `internal:auto_start_override`
- Computes auto-start recommendations based on:
  - Memory/CPU heuristics
  - Whitelist/deny-list
  - Concurrency limits
  - UI override status
- Returns annotated list with reasons
- **No mutations** – pure preview

**Response (200):**
```json
{
  "items": [
    {
      "manifest_id": "llama3-8b",
      "manifest_version": "v1.2.0",
      "model_id": "meta-llama/llama-3-8b",
      "est_mem_mb": 8192,
      "reason": "All checks passed",
      "allowed": true,
      "overridden_by_ui": false,
      "concurrency_ok": true,
      "whitelist_ok": true,
      "resources_ok": true,
      "ts": "2025-10-21T10:30:00Z"
    }
  ]
}
```

**Errors:**
- 401: Missing/invalid token
- 403: Requires internal access
- 500: Heuristics evaluation failed

## Internal-DB Endpoints

### POST /v1/internal/db/jobs

**Purpose:** Create DB job (create or populate)

**Storage:**
- **Redis**:
  - Idempotency map: `internal:db:jobs:idempotency:{key}` → `job_id` (24h TTL)
  - Cancel lock: `internal:db:jobs:{job_id}:cancel-lock` (short TTL, optional)
  
- **PostgreSQL**:
  - Jobs table: Existing `jobs` table with `type='internal.db.{action}'`
  - Fields: `id`, `status`, `owner_sub`, `payload_json`, `idempotency_key`, etc.
  - Job events table: Existing `job_events` for lifecycle tracking

**Behavior:**
- Validates `type` field: must be 'create' or 'populate'
- Honors **Idempotency-Key** header (24h window)
  - If seen → returns same job_id with 202
- Checks runtime capability:
  - If DB utilities unavailable → **501 Not Implemented**
- Creates job in PostgreSQL with status='queued'
- Enqueues background task
- Returns **202 Accepted** with `Location` header

**Request:**
```json
{
  "type": "create",
  "wipe": true,
  "users": 100
}
```

**Response (202):**
```json
{
  "ok": true,
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Headers:**
- `Location: /v1/internal/db/jobs/{job_id}`
- `Idempotency-Key` (in request, optional)
- `X-Request-Id`, `X-Correlation-Id` (out)

**Errors:**
- 400: Invalid type
- 401: Missing/invalid token
- 403: Requires internal access
- 501: DB utilities unavailable
- 500: Storage failure

### GET /v1/internal/db/jobs/{job_id}

**Purpose:** Get DB job status

**Storage:**
- **PostgreSQL**: Read from `jobs` table

**Response (200):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "state": "running",
  "progress": 0.5,
  "started_at": "2025-10-21T10:30:00Z",
  "finished_at": null,
  "message": null,
  "action": "create",
  "params": {"wipe": true, "users": 100}
}
```

**Headers:**
- `Cache-Control: no-store`
- `X-Request-Id`

**Errors:**
- 404: Job not found
- 401: Missing/invalid token
- 403: Requires internal access

### DELETE /v1/internal/db/jobs/{job_id}

**Purpose:** Cancel DB job (idempotent)

**Storage:**
- **Redis**:
  - Cancel signal: `internal:db:jobs:{job_id}:cancel` = `true` (5 min TTL)
  
- **PostgreSQL**:
  - Updates `jobs` row to `status='cancelled'`
  - Sets `completed_at` and `error_json`
  - Appends event to `job_events`

**Behavior:**
- **Always idempotent**:
  - Running/queued → request cancel and return 204
  - Already finished/canceled/not found → still 204
- Sets cancel signal in Redis for runner to check
- Updates job status in PostgreSQL

**Response:** 204 No Content (always)

**Errors:**
- 401: Missing/invalid token (only non-idempotent error)
- 403: Requires internal access

### GET /v1/internal/db/counts

**Purpose:** Get DB node/edge counts

**Storage:**
- **Redis** (optional): Very short cache (5-10s) to reduce burst load
- **PostgreSQL**: None (read-only diagnostic)

**Behavior:**
- If Memgraph client present → return counts
- If Memgraph not present → **501 Not Implemented**
- If query fails → **500** with RFC-7807

**Response (200):**
```json
{
  "ok": true,
  "nodes": 1234,
  "edges": 5678
}
```

**Errors:**
- 401: Missing/invalid token
- 403: Requires internal access
- 501: Memgraph unavailable
- 500: Query failed

## Observability

All endpoints implement:

1. **Audit Logging**:
   - Actor sub
   - Route
   - Parameters (sans secrets)
   - Outcome
   - Latency

2. **Correlation IDs**:
   - `X-Request-Id` (out)
   - `X-Correlation-Id` (in/out)

3. **Metrics**:
   - Counters by route and status code
   - Duration metrics

## Testing

### With Admin Token (Should Fail)

```bash
# This should return 403 Forbidden
curl -X POST "http://localhost:8000/v1/internal/ops/auto-start-override" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"enabled": true}'
```

**Expected:** 403 Forbidden - requires internal access

### With Service Token (Should Succeed)

For proper testing, you need to create a service token with:
- Custom claim `"service": true` in JWT, OR
- Scope/permission `internal:all`

```bash
# Example with service token
curl -X POST "http://localhost:8000/v1/internal/ops/auto-start-override" \
     -H "Authorization: Bearer $SERVICE_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"enabled": true, "note": "Test override"}'
```

**Expected:** 200 OK with override details

### Test Idempotency

```bash
# Create job with idempotency key
curl -X POST "http://localhost:8000/v1/internal/db/jobs" \
     -H "Authorization: Bearer $SERVICE_TOKEN" \
     -H "Idempotency-Key: test-key-123" \
     -H "Content-Type: application/json" \
     -d '{"type": "populate", "users": 10}'

# Repeat with same key - should return same job_id
curl -X POST "http://localhost:8000/v1/internal/db/jobs" \
     -H "Authorization: Bearer $SERVICE_TOKEN" \
     -H "Idempotency-Key: test-key-123" \
     -H "Content-Type: application/json" \
     -d '{"type": "populate", "users": 10}'
```

**Expected:** Both requests return same job_id with 202 Accepted

### Test Idempotent Cancel

```bash
# Cancel a job multiple times
JOB_ID="550e8400-e29b-41d4-a716-446655440000"

curl -X DELETE "http://localhost:8000/v1/internal/db/jobs/$JOB_ID" \
     -H "Authorization: Bearer $SERVICE_TOKEN"

curl -X DELETE "http://localhost:8000/v1/internal/db/jobs/$JOB_ID" \
     -H "Authorization: Bearer $SERVICE_TOKEN"

# Even with invalid ID
curl -X DELETE "http://localhost:8000/v1/internal/db/jobs/invalid-id" \
     -H "Authorization: Bearer $SERVICE_TOKEN"
```

**Expected:** All return 204 No Content

## Acceptance Checklist

- [x] **Security**: All routes reject non-internal tokens (401/403)
- [x] **OpenAPI**: Proper status codes and concrete response models
- [x] **Idempotency**: `POST /internal/db/jobs` supports `Idempotency-Key`
- [x] **Idempotent DELETE**: `DELETE /internal/db/jobs/{id}` always returns 204
- [x] **Audit**: PostgreSQL contains durable records in `internal_ops_events` and `jobs`
- [x] **Redis hygiene**: Keys use prefixes, TTLs honored
- [x] **Observability**: Correlation IDs, audit logs, metrics
- [x] **501 paths**: Returned when runtime lacks DB tools or Memgraph
- [x] **Location header**: Included in 202 responses
- [x] **RFC 7807**: Error responses follow Problem Details format

## Files Modified/Created

### New Files
1. `src/security/internal.py` - Internal access enforcement
2. `db/postgres_control/models/internal_ops_event.py` - Audit table model
3. `db/postgres_control/alembic/versions/012_create_internal_ops_events.py` - Migration

### Modified Files
1. `src/routers/internal_ops.py` - Completely rewritten
2. `src/routers/internal_db.py` - Completely rewritten
3. `db/postgres_control/models/__init__.py` - Added InternalOpsEvent export

## Configuration Variables

Add to your environment or settings:

```bash
# Internal ops configuration
INTERNAL_UI_OVERRIDE_ALLOWED=false  # Set to true to allow UI overrides
INTERNAL_AUTO_START_OVERRIDE_TTL=600  # TTL in seconds (default 10 minutes)

# Auto-start configuration
BUILTIN_AUTO_START=false
BUILTIN_AUTO_START_MAX_CONCURRENT=3
BUILTIN_AUTO_START_MIN_FREE_GB=2.0
BUILTIN_AUTO_START_WHITELIST=""  # Comma-separated list
```

## Notes

1. **Service Token Requirements**: The current admin/user tokens provided do NOT have internal access. You need to create service tokens with either:
   - Custom claim `service: true`
   - Scope `internal:all`

2. **Background Jobs**: DB jobs run in background tasks using the FastAPI BackgroundTasks mechanism. They update job status in PostgreSQL as they progress.

3. **Cancel Semantics**: The cancel endpoint is fully idempotent - it returns 204 even for:
   - Jobs that don't exist
   - Jobs that are already finished
   - Jobs that are already cancelled
   - Invalid job IDs

4. **Preview Caching**: The preview endpoint uses a short 30-second cache to reduce load during UI polling. The cache includes input hashing to prevent stale data.

5. **Deprecation Headers**: The `populate` job type includes deprecation headers when image marks it deprecated.
