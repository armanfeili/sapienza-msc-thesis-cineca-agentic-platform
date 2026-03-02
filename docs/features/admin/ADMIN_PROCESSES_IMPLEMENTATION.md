# Admin Processes API Implementation

## Overview

This document describes the complete implementation of the `/v1/admin/processes*` endpoints for managing built-in model processes. The implementation follows best practices for REST API design, RBAC, observability, idempotency, and RFC 7807 error handling.

## Architecture

### Components

1. **Database Layer** (PostgreSQL)
   - `BuiltinManifestActivationHistory`: Timeline of manifest activation operations
   - `BuiltinProcessEvent`: Audit trail of process lifecycle events

2. **Cache Layer** (Redis)
   - Runtime process registry with sliding TTL
   - Recent processes index for quick access
   - Stop-lock mechanism for idempotent operations

3. **Service Layer**
   - `process_service.py`: Business logic for process management
   - Merges runtime (Redis) and persistent (PostgreSQL) state
   - Implements idempotency and concurrency control

4. **Router Layer**
   - `model_processes.py`: FastAPI endpoints with RBAC
   - Request validation and error handling
   - Observability (audit logs, metrics, correlation IDs)

## Redis Key Structure

```
runtime:builtins:processes:live (Set)
  - Active PIDs/process_ids
  
runtime:builtins:process:{pid} (Hash)
  - pid: OS process ID
  - process_id: Stable identifier
  - artifact: Model artifact name
  - port: Listening port
  - status: running|starting|stopping
  - last_heartbeat: Unix timestamp
  - tenant_id: Tenant identifier
  - manifest_version: Manifest version
  - host: Hostname/pod
  
runtime:builtins:processes:recent (Sorted Set)
  - Score: last_heartbeat timestamp
  - Member: process_id
  - Automatically trimmed to 1000 entries
  
runtime:builtins:process:{pid}:stop-lock (String)
  - TTL: 30 seconds
  - Ensures idempotent stop operations
```

## Endpoints

### 1. GET /v1/admin/processes

**Purpose:** List active and recently recorded built-in processes

**Permissions:** `admin:all`

**Query Parameters:**
- `artifact` (optional): Filter by artifact name
- `status` (optional): Filter by status (running|starting|stopping|exited|stale)
- `since` (optional): ISO 8601 timestamp to filter events after
- `tenant_id` (optional): Filter by tenant
- `limit` (optional): Max results (default 100, max 1000)

**Response:** 200 OK
```json
{
  "processes": [
    {
      "id": "llama3-8b-1234",
      "process_id": "builtin:llama3-8b:abc123",
      "artifact": "llama3-8b",
      "pid": 42789,
      "port": 8080,
      "status": "running",
      "ts": "2025-10-21T10:30:00Z",
      "tenant_id": null,
      "manifest_version": "v1.2.3",
      "host": "localhost",
      "last_heartbeat": "2025-10-21T10:35:00Z"
    }
  ],
  "next_cursor": null
}
```

**Data Sources:**
1. Redis `runtime:builtins:processes:live` - active processes
2. Redis `runtime:builtins:processes:recent` - recently recorded
3. PostgreSQL `builtin_process_events` - enrichment and history

**Merge Logic:**
- Runtime (Redis) data takes precedence for active processes
- PostgreSQL enriches with missing metadata
- De-duplicates by `process_id`
- Sorts: running first, then by timestamp descending

### 2. DELETE /v1/admin/processes/{pid}

**Purpose:** Stop a built-in process by OS PID

**Permissions:** `admin:all`

**Path Parameters:**
- `pid`: Operating system process ID (integer > 0)

**Response:** 204 No Content

**Idempotency:** 
- Always returns 204, whether process was just stopped, already stopped, or never existed
- Uses Redis lock (`runtime:builtins:process:{pid}:stop-lock`) with 30s TTL
- Safe for concurrent DELETE requests

**Operations:**
1. Validate PID (must be positive integer)
2. Acquire stop-lock (if locked, treat as already stopping → return 204)
3. Check runtime hash for process metadata
4. If not in runtime, check PostgreSQL for last event
5. Call adapter to unload process (best-effort)
6. Remove from Redis (live set, hash)
7. Record STOP event to PostgreSQL
8. Release stop-lock
9. Return 204

**Error Responses:**
- 422: Invalid PID format (not positive integer)
- 500: Internal error (with RFC 7807 problem details)

### 3. GET /v1/admin/processes/history/manifests

**Purpose:** Get manifest activation history

**Permissions:** `admin:all`

**Query Parameters:**
- `manifest_name` (optional): Filter by manifest name
- `status` (optional): Filter by status (staged|active|rolled_back|failed)
- `since` (optional): ISO 8601 timestamp to filter after
- `limit` (optional): Max results (default 100, max 1000)

**Response:** 200 OK
```json
{
  "manifests": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "manifest_name": "production-builtins",
      "version": "v1.2.3",
      "status": "active",
      "activated_at": "2025-10-21T09:00:00Z",
      "activated_by": "auth0|68c709969225afe265151ed5",
      "notes": "Rolled out new model versions"
    }
  ],
  "next_cursor": null
}
```

**Data Source:** PostgreSQL `builtin_manifest_activation_history`

### 4. GET /v1/admin/processes/history/processes

**Purpose:** Get process lifecycle event history

**Permissions:** `admin:all`

**Query Parameters:**
- `artifact` (optional): Filter by artifact name
- `pid` (optional): Filter by OS process ID
- `process_id` (optional): Filter by stable process identifier
- `tenant_id` (optional): Filter by tenant
- `event` (optional): Filter by event type (start|heartbeat|stop|exit|signal)
- `since` (optional): ISO 8601 timestamp to filter after
- `limit` (optional): Max results (default 100, max 1000)

**Response:** 200 OK
```json
{
  "events": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440000",
      "process_id": "builtin:llama3-8b:abc123",
      "artifact": "llama3-8b",
      "pid": 42789,
      "port": 8080,
      "event": "start",
      "reason": "manifest_activation",
      "exit_code": null,
      "ts": "2025-10-21T10:30:00Z",
      "tenant_id": null,
      "manifest_version": "v1.2.3",
      "host": "localhost"
    }
  ],
  "next_cursor": null
}
```

**Data Source:** PostgreSQL `builtin_process_events`

## RBAC Implementation

All endpoints require the `admin:all` permission. The implementation:

1. Uses `require_admin()` FastAPI dependency
2. Extracts JWT via `get_current_principal()` (validates against Auth0 JWKS)
3. Checks for `admin:all` in permissions/scopes
4. Returns 401 for missing/invalid tokens
5. Returns 403 for valid tokens without admin permission

**Token Scopes:**
- Admin users: `["admin:all", "tools:invoke:all", "user:me"]`
- Regular users: `["tools:invoke:basic", "user:me"]`

## Observability

### Audit Logging
Every operation emits structured audit logs:
```python
logger.info("admin_processes_audit", extra={
    "actor": user.sub,
    "action": "list_processes",
    "resource": "/v1/admin/processes",
    "correlation_id": "...",
    "params": {...},
    "result": "success",
    "duration_ms": 42.5
})
```

### Metrics
Operations emit timing and status metrics:
- `admin_processes.list.duration_ms` (tags: status=success|error)
- `admin_processes.stop.duration_ms` (tags: status=success|error)

### Correlation IDs
- Accepts `X-Correlation-Id` header (or generates UUID)
- Returns `X-Request-Id` and `X-Trace-Id` in responses
- Included in error responses for troubleshooting

## Error Handling

Follows RFC 7807 (Problem Details for HTTP APIs):

```json
{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "Failed to retrieve process list",
  "instance": "/v1/admin/processes",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Database Schema

### builtin_manifest_activation_history
```sql
CREATE TABLE builtin_manifest_activation_history (
    id UUID PRIMARY KEY,
    manifest_name VARCHAR(255) NOT NULL,
    version VARCHAR(100) NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL,
    activated_by TEXT,
    status manifeststatus NOT NULL,  -- staged|active|rolled_back|failed
    notes TEXT
);

CREATE INDEX ix_builtin_manifest_name_activated_at 
    ON builtin_manifest_activation_history (manifest_name, activated_at);
CREATE INDEX ix_builtin_manifest_status 
    ON builtin_manifest_activation_history (status);
```

### builtin_process_events
```sql
CREATE TABLE builtin_process_events (
    id UUID PRIMARY KEY,
    process_id VARCHAR(255) NOT NULL,
    artifact VARCHAR(255) NOT NULL,
    pid INTEGER,
    port INTEGER,
    event processevent NOT NULL,  -- start|heartbeat|stop|exit|signal
    reason TEXT,
    exit_code INTEGER,
    ts TIMESTAMPTZ NOT NULL,
    tenant_id VARCHAR(255),
    manifest_version VARCHAR(100),
    host VARCHAR(255)
);

CREATE INDEX ix_builtin_process_ts ON builtin_process_events (ts);
CREATE INDEX ix_builtin_process_artifact_ts ON builtin_process_events (artifact, ts);
CREATE INDEX ix_builtin_process_pid_ts ON builtin_process_events (pid, ts);
CREATE INDEX ix_builtin_process_process_id ON builtin_process_events (process_id);
```

## Testing

### Test Coverage
- `tests/test_admin_processes.py`: 20+ test cases covering:
  - RBAC: 401/403 for missing/invalid/non-admin tokens
  - GET /admin/processes: success, filtering, pagination
  - DELETE /admin/processes/{pid}: idempotency, invalid PIDs, concurrent calls
  - GET /admin/processes/history/manifests: success, filtering, invalid status
  - GET /admin/processes/history/processes: success, filtering, invalid event
  - Legacy endpoint returns 410 Gone
  - Pagination limit enforcement

### Running Tests
```bash
# Set tokens
export ADMIN_TOKEN="eyJhbGci..."
export USER_TOKEN="eyJhbGci..."

# Run all admin process tests
pytest tests/test_admin_processes.py -v

# Run specific test
pytest tests/test_admin_processes.py::test_stop_process_idempotent -v
```

## Migration

Apply database migration:
```bash
cd db/postgres_control
alembic upgrade head
```

This creates:
- `builtin_manifest_activation_history` table
- `builtin_process_events` table
- `manifeststatus` enum
- `processevent` enum
- All necessary indexes

## Usage Examples

### List all processes
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/processes
```

### List processes for specific artifact
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/v1/admin/processes?artifact=llama3-8b&limit=50"
```

### Stop a process (idempotent)
```bash
curl -X DELETE \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/processes/42789
```

### Get manifest activation history
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/v1/admin/processes/history/manifests?status=active"
```

### Get process event history
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8000/v1/admin/processes/history/processes?artifact=llama3-8b&event=start"
```

## Implementation Checklist

✅ PostgreSQL models with enums and indexes  
✅ Pydantic response models with examples  
✅ Admin permission enforcement helper  
✅ Service layer with Redis/PostgreSQL merge logic  
✅ Idempotent DELETE with Redis lock  
✅ Complete router with RBAC and observability  
✅ Alembic migration for database tables  
✅ Comprehensive test suite (20+ tests)  
✅ RFC 7807 error handling  
✅ Correlation ID support  
✅ Audit logging and metrics  
✅ Pagination with cursor support  
✅ Query filtering on all history endpoints  
✅ Documentation with examples  

## Next Steps

1. **Run migration**: `cd db/postgres_control && alembic upgrade head`
2. **Rebuild Docker**: `docker compose up -d --build --remove-orphans`
3. **Run tests**: `pytest tests/test_admin_processes.py -v`
4. **Verify endpoints** with curl or Postman
5. **Monitor logs** for audit trails and metrics

## Performance Considerations

- **Pagination**: Default limit 100, max 1000 to prevent large result sets
- **Redis TTL**: Process hashes expire after 120s of no heartbeat
- **Index Strategy**: Composite indexes on common query patterns
- **Heartbeat Compression**: Consider bucketing heartbeats by minute in PostgreSQL
- **Recent ZSet Trim**: Automatically trimmed to 1000 entries to prevent unbounded growth

## Security

- **Auth0 Integration**: JWT validation with JWKS
- **Permission Model**: Explicit `admin:all` requirement
- **Audit Trail**: All operations logged with actor and correlation ID
- **PII Scrubbing**: Avoid logging sensitive token data
- **Rate Limiting**: Consider adding per-user rate limits for admin operations
