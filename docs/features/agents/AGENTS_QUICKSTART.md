# Agents API - Phase 1 Complete ✅

This document provides a quick overview of the completed Phase 1 implementation and next steps.

## What Was Implemented (Phase 1)

### 1. Database Schema

**New Tables:**
- `agent_sessions` - Stateful agent sessions with configuration and metadata
- `agent_steps` - Individual steps in a session (sequenced, typed)
- `agent_runs` - Execution tracking for agent invocations
- `idempotency_keys` - Request deduplication for POST operations

**Files:**
- `db/postgres_control/models/agent_session.py`
- `db/postgres_control/models/agent_step.py`
- `db/postgres_control/models/agent_run.py`
- `db/postgres_control/models/idempotency_key.py`
- `db/postgres_control/alembic/versions/008_create_agent_tables.py`

**Features:**
- Proper indexes for performance (DESC on timestamps, composite indexes)
- CHECK constraints for status/type validation
- Foreign key cascades for cleanup
- Auto-update triggers for `updated_at`
- ETag columns for HTTP caching
- Unique constraints for idempotency

### 2. Redis Layer

**File:** `db/redis_cache/agents.py`

**Capabilities:**
- Session state caching with TTL
- Atomic step sequence allocation (`INCR`)
- Distributed locks (session-level and step-level)
- Cancellation flags
- ETag computation and caching
- Idempotency response caching

### 3. API Schemas

**File:** `src/schemas/agents.py`

**Models:**
- `CreateSessionRequest` / `SessionResponse` / `SessionListResponse`
- `CreateStepRequest` / `StepResponse` / `StepListResponse`
- `CreateRunRequest` / `RunResponse`
- `ProblemDetail` (RFC7807 errors)

## Quick Start

### Apply Database Migration

```bash
# Navigate to Postgres control directory
cd db/postgres_control

# Run migration
alembic upgrade head

# Verify tables created
docker exec -it postgres psql -U cineca_user -d cineca_platform -c "\dt agent_*"
```

Expected output:
```
             List of relations
 Schema |       Name        | Type  |    Owner
--------+-------------------+-------+-------------
 public | agent_runs        | table | cineca_user
 public | agent_sessions    | table | cineca_user
 public | agent_steps       | table | cineca_user
 public | idempotency_keys  | table | cineca_user
```

### Test Redis Helpers

```python
from db.redis_cache.agents import allocate_next_seq, session_lock, set_session_state
import uuid

# Test sequence allocation
session_id = uuid.uuid4()
seq1 = allocate_next_seq(session_id)  # Returns 1
seq2 = allocate_next_seq(session_id)  # Returns 2
print(f"Allocated sequences: {seq1}, {seq2}")

# Test distributed lock
with session_lock(session_id, timeout=5):
    print("Lock acquired successfully!")
    # Perform atomic operations here

# Test session caching
state = {
    "status": "active",
    "last_seq": 2,
    "heartbeat_ts": 1234567890
}
set_session_state(session_id, state, ttl=3600)
```

## Next Steps (Phase 2+)

See [`docs/AGENTS_TODO_IMPLEMENTATION_PLAN.md`](./AGENTS_TODO_IMPLEMENTATION_PLAN.md) for detailed implementation phases.

### Priority Order:

1. **Phase 2: Repository Layer** - Database access with cursor pagination
2. **Phase 3: Idempotency Middleware** - Request deduplication for POST operations
3. **Phase 4: Session Endpoints** - Full CRUD with RBAC, ETags, pagination
4. **Phase 5: Step Endpoints** - Sequencing with concurrency safety
5. **Phase 6: Run Endpoints** - Integration with orchestrator
6. **Phase 7-10**: Rate limiting, error handling, testing, documentation

### Estimated Timeline:

- **Phase 2-3**: 5 hours
- **Phase 4-5**: 8 hours
- **Phase 6**: 3 hours
- **Phase 7-10**: 12 hours
- **Total**: ~28 hours

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│              FastAPI Routers                    │
│  /agents/sessions, /agents/sessions/:id/steps   │
│  /agent-runs                                    │
└──────────────┬──────────────────────────────────┘
               │
               ├─────────────┬──────────────┬──────────────┐
               │             │              │              │
         ┌─────▼─────┐ ┌────▼────┐  ┌─────▼──────┐ ┌────▼─────┐
         │   RBAC    │ │ Idem.   │  │ Rate Limit │ │  ETag    │
         │ Middleware│ │Middleware│  │ Middleware │ │  Cache   │
         └─────┬─────┘ └────┬────┘  └─────┬──────┘ └────┬─────┘
               │            │              │             │
         ┌─────▼────────────▼──────────────▼─────────────▼─────┐
         │              Repository Layer                        │
         │  AgentSessionRepo, AgentStepRepo, AgentRunRepo      │
         └──────────────┬──────────────────────────────────────┘
                        │
          ┌─────────────┴─────────────┐
          │                           │
    ┌─────▼──────┐            ┌───────▼────────┐
    │ PostgreSQL │            │     Redis      │
    │  (durable) │            │  (ephemeral)   │
    └────────────┘            └────────────────┘
         │                            │
    Sessions, Steps,          Seq counters, Locks,
    Runs, Idempotency         ETags, Cancel flags
```

## Data Flow Example

### Creating a Session with Steps

```
1. POST /agents/sessions
   ├─> Check Idempotency-Key header
   ├─> Verify RBAC (user:me or admin:all)
   ├─> Create session in PostgreSQL
   ├─> Initialize Redis state (seq=0)
   ├─> Return 201 + Location header

2. POST /agents/sessions/{id}/steps (×5 concurrent)
   ├─> Check ownership + status=active
   ├─> Acquire session lock (Redis)
   ├─> Allocate seq via INCR (1,2,3,4,5)
   ├─> Create step in PostgreSQL
   ├─> Update session.last_step_id
   ├─> Release lock
   ├─> Return 202 + {step_id, seq}

3. GET /agents/sessions/{id}/steps?page_size=20
   ├─> Check If-None-Match header
   ├─> Query PostgreSQL (ORDER BY seq ASC)
   ├─> Compute ETag, cache in Redis
   ├─> Return 200 + ETag header + items

4. DELETE /agents/sessions/{id}
   ├─> Acquire session lock
   ├─> Set Redis cancel flag
   ├─> Update PostgreSQL status=cancelled
   ├─> Invalidate ETags
   ├─> Return 204
```

## Configuration

Add these to your `.env` or environment variables:

```bash
# Idempotency TTL (seconds)
IDEMPOTENCY_TTL_SECONDS=86400  # 24 hours

# Agent-specific settings (add to config.py later)
AGENT_MAX_STEPS_DEFAULT=8
AGENT_MAX_STEPS_LIMIT=64
AGENT_SESSION_TTL_DAYS=7
AGENT_STEP_RATE_LIMIT=60   # per minute
AGENT_RUN_RATE_LIMIT=10    # per minute
```

## Testing the Migration

```bash
# Check migration status
cd db/postgres_control
alembic current

# Should show: 008 (head)

# Inspect a table
docker exec -it postgres psql -U cineca_user -d cineca_platform

cineca_platform=# \d agent_sessions
```

Expected schema:
```
Column          | Type                     | Nullable | Default
----------------+--------------------------+----------+------------------------
session_id      | uuid                     | not null | gen_random_uuid()
user_id         | character varying(255)   | not null |
tenant_id       | character varying(255)   | not null |
status          | character varying(50)    | not null | 'active'::character varying
manager         | character varying(255)   |          |
...
```

## Troubleshooting

### Migration fails with "relation already exists"

```bash
# Check current version
alembic current

# If stuck on 007, manually mark as upgraded
alembic stamp head
```

### Redis connection errors

```bash
# Test Redis connectivity
docker exec -it redis redis-cli PING

# Should return: PONG
```

### Import errors for new models

```bash
# Rebuild Docker containers
docker compose build app
docker compose up -d app
```

## Files Summary

```
Phase 1 Implementation Files:

db/postgres_control/
├── models/
│   ├── agent_session.py          (New)
│   ├── agent_step.py              (New)
│   ├── agent_run.py               (New)
│   ├── idempotency_key.py         (New)
│   └── __init__.py                (Updated)
└── alembic/versions/
    └── 008_create_agent_tables.py (New)

db/redis_cache/
└── agents.py                      (New)

src/schemas/
└── agents.py                      (New)

docs/
├── AGENTS_TODO_IMPLEMENTATION_PLAN.md  (New)
└── AGENTS_QUICKSTART.md                (This file)
```

## Support

For questions or issues:
1. Check the implementation plan: `docs/AGENTS_TODO_IMPLEMENTATION_PLAN.md`
2. Review existing patterns in `src/routers/jobs.py` (similar CRUD operations)
3. Consult Redis helpers: `db/redis_cache/client.py`
4. Check auth patterns: `src/security/perm.py`

---

**Status**: ✅ Phase 1 Complete - Ready for Phase 2 implementation
**Next**: Implement repository layer with cursor pagination
