# Tools PostgreSQL + Redis Architecture

## Overview

The tools system uses a dual-layer architecture combining PostgreSQL for persistent storage with Redis for caching and ephemeral state management. This provides strong consistency, auditability, and performance.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Application                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ HTTP POST /v1/tools/{name}/invocations
                         │ HTTP GET  /v1/tools/{name}/invocations/{eid}
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Tools Router (FastAPI)                     │
│  • Authentication & Authorization                                │
│  • Idempotency handling                                         │
│  • Request validation                                           │
│  • Metrics & logging                                            │
└──────────┬──────────────────────────────────────┬───────────────┘
           │                                      │
           ▼                                      ▼
┌──────────────────────┐              ┌──────────────────────────┐
│   ToolsRepository     │              │   Redis Cache Layer      │
│   (PostgreSQL)        │              │   (tools_cache.py)       │
│  ──────────────────── │              │  ──────────────────────  │
│  • create_tool()      │              │  • Queue management      │
│  • create_invocation()│              │  • Result caching        │
│  • update_status()    │              │  • Idempotency mapping   │
│  • get_by_eid()       │              │  • Rate limiting         │
│  • list_tools()       │              │  • State tracking        │
│  • audit_events()     │              │                          │
└──────────┬────────────┘              └──────────┬───────────────┘
           │                                      │
           ▼                                      ▼
┌──────────────────────┐              ┌──────────────────────────┐
│    PostgreSQL 16     │              │      Redis 7.x           │
│  ──────────────────── │              │  ──────────────────────  │
│  • tools              │              │  • tools:queue:*         │
│  • tool_invocations   │              │  • tools:result:*        │
│  • tool_audit_events  │              │  • tools:idem:*          │
│  • tenants            │              │  • tools:state:*         │
│                       │              │  • tools:ratelimit:*     │
└───────────────────────┘              └──────────────────────────┘
```

## Data Flow

### 1. Tool Invocation (POST)

```
Client
  │
  │ POST /v1/tools/{name}/invocations
  │ Headers: Authorization, Idempotency-Key (optional)
  │ Body: {"args": {...}}
  ▼
Router
  │
  ├─→ Auth & RBAC check
  │
  ├─→ Check Idempotency (if key provided)
  │   ├─→ PostgreSQL: get_invocation_by_idempotency_key()
  │   │   └─→ If exists with same params: return 200 (replay)
  │   │   └─→ If exists with diff params: return 409 (conflict)
  │   └─→ Redis: idem:tools:{key}:{name}
  │
  ├─→ Execute tool logic
  │
  ├─→ PostgreSQL: create_invocation()
  │   ├─→ Insert into tool_invocations
  │   ├─→ Create audit event
  │   └─→ Return invocation with eid
  │
  ├─→ PostgreSQL: update_invocation_status()
  │   └─→ Set status to "finished" or "failed"
  │
  ├─→ Redis: cache result/error
  │   └─→ tools:result:{eid} or tools:error:{eid}
  │
  ├─→ Redis: set idempotency mapping
  │   └─→ tools:idem:{key} → eid
  │
  └─→ Return response
      ├─→ Status: 200/201
      ├─→ Headers: Location, Idempotency-Key, X-Request-Id
      └─→ Body: {name, ok, result/error, duration_ms, event_id}
```

### 2. Invocation Retrieval (GET)

```
Client
  │
  │ GET /v1/tools/{name}/invocations/{eid}
  │ Headers: Authorization, If-None-Match (optional)
  ▼
Router
  │
  ├─→ Validate UUID format (400 if invalid)
  │
  ├─→ Redis: Check cache first
  │   ├─→ tools:result:{eid}
  │   └─→ If found: record cache hit metric
  │
  ├─→ PostgreSQL: Verify ownership
  │   ├─→ get_invocation_by_eid()
  │   └─→ Check requested_by matches user (404 if not, anti-enumeration)
  │
  ├─→ If cached: Return from cache
  │   └─→ Headers: X-Cache: HIT, ETag, Cache-Control
  │
  ├─→ Else: Fetch from PostgreSQL
  │   ├─→ record cache miss metric
  │   ├─→ Build response from invocation record
  │   └─→ Headers: X-Cache: MISS, ETag, Cache-Control
  │
  └─→ Return response
      ├─→ Status: 200 or 304 (if ETag matches)
      └─→ Body: {name, ok, result, error, duration_ms, event_id}
```

## Idempotency Mechanism

### Purpose
Prevent duplicate processing when clients retry requests due to network issues.

### Implementation

1. **Client sends Idempotency-Key header**:
   ```
   POST /v1/tools/system.health/invocations
   Idempotency-Key: req-abc123
   ```

2. **Router checks PostgreSQL first**:
   ```python
   existing = repo.get_invocation_by_idempotency_key("req-abc123")
   ```

3. **Three outcomes**:

   a. **Key not found** → Create new invocation
      - Store with idempotency_key in tool_invocations
      - Cache mapping in Redis: `tools:idem:req-abc123 → eid`
      - Return 201 Created with Location header

   b. **Key found, params match** → Idempotent replay
      - Validate params_json equals request args
      - Return 200 OK with same Location header
      - Set header: `Idempotency-Replayed: true`

   c. **Key found, params differ** → Conflict
      - Return 409 Conflict
      - Record metric: `tools_idempotency_conflicts_total`
      - Detail: "Idempotency key already used with different parameters"

### Why PostgreSQL First?

- **Strong consistency**: PostgreSQL UNIQUE constraint on idempotency_key prevents race conditions
- **Audit trail**: All invocations with their idempotency keys are in audit log
- **Redis is fallback**: Used only if PostgreSQL check fails (rare)

## Database Schema

### tools table
```sql
CREATE TABLE tools (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL DEFAULT '1',
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(id),
    input_schema JSONB,
    description TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(name, version, tenant_id)
);
```

### tool_invocations table
```sql
CREATE TABLE tool_invocations (
    id SERIAL PRIMARY KEY,
    eid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    tool_name VARCHAR(255) NOT NULL,
    tool_version VARCHAR(50) NOT NULL DEFAULT '1',
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(id),
    params_json JSONB,
    result_json JSONB,
    error_json JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    latency_ms INTEGER,
    requested_by VARCHAR(255),
    idempotency_key VARCHAR(255),
    request_headers JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(idempotency_key, tool_name)  -- Prevents duplicate processing
);

CREATE INDEX idx_tool_invocations_eid ON tool_invocations(eid);
CREATE INDEX idx_tool_invocations_tenant ON tool_invocations(tenant_id);
CREATE INDEX idx_tool_invocations_idem ON tool_invocations(idempotency_key);
```

### tool_audit_events table
```sql
CREATE TABLE tool_audit_events (
    id SERIAL PRIMARY KEY,
    invocation_eid UUID NOT NULL REFERENCES tool_invocations(eid),
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB,
    performed_by VARCHAR(255),
    performed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tool_audit_invocation ON tool_audit_events(invocation_eid);
```

## Redis Key Patterns

| Pattern | Purpose | TTL | Example |
|---------|---------|-----|---------|
| `tools:queue:{name}` | Pending invocations for tool | None | `tools:queue:graph.query` → List of eids |
| `tools:result:{eid}` | Cached invocation result | 1 hour | `tools:result:abc-123` → `{"value": 42}` |
| `tools:error:{eid}` | Cached invocation error | 1 hour | `tools:error:abc-123` → `{"message": "..."}` |
| `tools:idem:{key}` | Idempotency key mapping | 24 hours | `tools:idem:req-xyz` → `eid-abc-123` |
| `tools:state:{eid}` | Invocation state | 1 hour | `tools:state:abc-123` → `"running"` |
| `tools:ratelimit:{user}:{tool}` | Rate limiting counter | 60 seconds | `tools:ratelimit:alice:graph.query` → `5` |

## Observability

### Prometheus Metrics

1. **tools_invocations_total** (Counter)
   - Labels: `tool_name`, `status`, `tenant_id`
   - Tracks total invocations by tool and outcome

2. **tools_invocation_duration_seconds** (Histogram)
   - Labels: `tool_name`, `status`
   - Buckets: 0.1s to 5 minutes
   - Measures invocation latency

3. **tools_queue_depth** (Gauge)
   - Labels: `tool_name`
   - Current number of pending invocations

4. **tools_cache_operations_total** (Counter)
   - Labels: `operation` (get/set/delete), `result` (hit/miss/success/error)
   - Tracks Redis cache effectiveness

5. **tools_idempotency_conflicts_total** (Counter)
   - Labels: `tool_name`
   - Counts 409 responses from idempotency conflicts

### Structured Logging

All logs include correlation IDs:

```json
{
  "event": "tool.invocation.start",
  "tool_name": "graph.query",
  "correlation_id": "req-abc-123",
  "user": "alice",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

Key events:
- `tool.invocation.start` - Invocation begins
- `tool.invocation.success` - Completed successfully
- `tool.invocation.failed` - Execution failed
- `tool.invocation.cache_hit` - Cache hit on GET
- `tool.invocation.cache_miss` - Cache miss on GET

## Performance Characteristics

### Latency

- **POST (new invocation)**: 20-50ms
  - PostgreSQL insert: 5-10ms
  - Tool execution: varies (10-1000ms+)
  - Redis cache: 1-2ms

- **POST (idempotent replay)**: 10-20ms
  - PostgreSQL lookup: 5-10ms
  - No execution
  - Redis cache: 1-2ms

- **GET (cache hit)**: 5-10ms
  - Redis lookup: 1-2ms
  - PostgreSQL ownership check: 3-5ms

- **GET (cache miss)**: 10-20ms
  - PostgreSQL fetch: 5-10ms
  - Response building: 2-5ms

### Scalability

- **Horizontal**: Multiple API instances share PostgreSQL + Redis
- **Read-heavy**: Redis caching reduces DB load by ~70%
- **Write-heavy**: PostgreSQL handles 1000+ writes/sec
- **Concurrent idempotency**: UNIQUE constraint prevents race conditions

## Security

### Authentication & Authorization

- All endpoints require valid JWT token
- Minimum scope: `tools:basic` or `tools:all`
- Admin scope: `admin:all` bypasses ownership checks

### Anti-Enumeration

- Non-owners get 404 (not 403) to prevent enumeration
- UUID validation happens before DB lookup
- Error messages don't leak existence

### Data Privacy

- Invocations are tenant-scoped
- Results cached with user-specific keys
- Audit log tracks all access

## Failure Modes & Recovery

### PostgreSQL Down
- API returns 503 Service Unavailable
- Redis cache still serves recent results (read-only)
- Recovery: Automatic reconnection on DB restore

### Redis Down
- API continues to function (PostgreSQL primary)
- Cache misses on all GETs (slower but functional)
- Idempotency falls back to PostgreSQL
- Recovery: Cache repopulates automatically

### Invocation Timeout
- Status remains "running" in DB
- Background cleanup job marks as "timeout" after threshold
- Client can retry with same idempotency key

## Migration from Legacy System

See [Tools Migration Guide](./tools-migration-guide.md) for detailed migration steps.

Key differences:
- **Before**: In-memory + Redis-only storage
- **After**: PostgreSQL primary + Redis cache
- **Benefit**: Persistence, auditability, strong consistency
