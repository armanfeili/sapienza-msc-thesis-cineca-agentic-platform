# 🤖 Agents API - Complete Implementation Guide

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [What's Implemented](#whats-implemented)
- [Architecture](#architecture)
- [Testing](#testing)
- [Next Steps](#next-steps)
- [API Reference](#api-reference)

---

## 🚀 Quick Start

### 1. Apply Database Migration

```bash
cd db/postgres_control
alembic upgrade head
```

### 2. Verify Setup

```bash
# Run automated tests
python scripts/test_agents_setup.py
```

Expected output:
```
╔══════════════════════════════════════════════════════╗
║            Agents API Setup Verification             ║
╚══════════════════════════════════════════════════════╝

✅ Database migration test PASSED
✅ Redis helpers test PASSED
✅ Schema test PASSED

🎉 All tests PASSED! Agents API foundation is ready.
```

### 3. Manual Verification

```bash
# Check tables exist
docker exec -it postgres psql -U cineca_user -d cineca_platform -c "\dt agent_*"

# Test Redis
docker exec -it redis redis-cli PING
```

---

## ✅ What's Implemented

### Phase 1: Foundation (COMPLETE)

#### Database Layer ✅
- **4 PostgreSQL Tables**
  - `agent_sessions` - Stateful agent conversations
  - `agent_steps` - Individual actions in a session
  - `agent_runs` - Execution tracking and metrics
  - `idempotency_keys` - Request deduplication

- **Key Features**
  - Composite indexes for fast queries
  - Foreign key cascades for cleanup
  - CHECK constraints for data integrity
  - Auto-update triggers for timestamps
  - ETag columns for HTTP caching

#### Redis Layer ✅
- **Session Management**
  - State caching with TTL
  - Heartbeat tracking
  - Distributed locks

- **Step Sequencing**
  - Atomic allocation via INCR
  - No gaps or duplicates guaranteed

- **Performance**
  - ETag computation and caching
  - Idempotency response caching
  - Cancellation flags

#### API Schemas ✅
- **Pydantic Models**
  - Request/response for all endpoints
  - Type validation with custom validators
  - RFC7807 error responses

#### Documentation ✅
- Implementation plan (10 phases)
- Quick start guide
- Architecture diagrams
- Test scripts

---

## 🏗️ Architecture

### Data Flow

```
┌──────────────────────────────────────────────────────────┐
│                    Client Request                         │
│         POST /agents/sessions/{id}/steps                  │
└────────────────────┬─────────────────────────────────────┘
                     │
        ┌────────────▼────────────┐
        │   FastAPI Router        │
        │   (src/routers/)        │
        └────────────┬────────────┘
                     │
     ┌───────────────┼───────────────┐
     │               │               │
┌────▼────┐    ┌────▼────┐    ┌────▼────┐
│  RBAC   │    │  Idem.  │    │  Rate   │
│  Check  │    │  Check  │    │  Limit  │
└────┬────┘    └────┬────┘    └────┬────┘
     │               │               │
     └───────────────┼───────────────┘
                     │
        ┌────────────▼────────────┐
        │   Repository Layer      │
        │   (db/repositories/)    │
        └────────────┬────────────┘
                     │
          ┌──────────┴──────────┐
          │                     │
     ┌────▼─────┐         ┌────▼─────┐
     │PostgreSQL│         │  Redis   │
     │ (durable)│         │(ephemeral)│
     └──────────┘         └──────────┘
```

### Components

| Layer | Purpose | Files |
|-------|---------|-------|
| **Models** | DB schema | `db/postgres_control/models/agent_*.py` |
| **Schemas** | API contracts | `src/schemas/agents.py` |
| **Cache** | Performance | `db/redis_cache/agents.py` |
| **Routers** | HTTP handlers | `src/routers/agent*.py` (Phase 4-6) |
| **Repos** | Data access | `db/repositories/agents.py` (Phase 2) |

---

## 🧪 Testing

### Automated Tests

```bash
# Run full verification
python scripts/test_agents_setup.py

# Expected: All tests PASS
```

### Manual Tests

#### 1. Database

```python
from db.postgres_control.database import get_db_context
from db.postgres_control.models import AgentSession
import uuid

with get_db_context() as db:
    session = AgentSession(
        user_id="test-user",
        tenant_id="tenant-admin-root",
        status="active",
        temperature=0.2,
        max_steps=10
    )
    db.add(session)
    db.commit()
    print(f"Created session: {session.session_id}")
```

#### 2. Redis

```python
from db.redis_cache.agents import allocate_next_seq, session_lock
import uuid

session_id = uuid.uuid4()

# Test sequence allocation
seq1 = allocate_next_seq(session_id)  # Returns 1
seq2 = allocate_next_seq(session_id)  # Returns 2
print(f"Sequences: {seq1}, {seq2}")

# Test locking
with session_lock(session_id):
    print("Lock acquired!")
```

#### 3. Schemas

```python
from src.schemas.agents import CreateSessionRequest, CreateStepRequest

# Valid request
req = CreateSessionRequest(
    prompt="Hello",
    temperature=0.5,
    max_steps=10
)
print(f"Valid: {req.temperature}")

# Invalid type (raises ValidationError)
try:
    step = CreateStepRequest(type="invalid", message="Test")
except Exception as e:
    print(f"Validation error: {e}")
```

---

## 📚 Next Steps

### Implementation Phases

See [`docs/AGENTS_TODO_IMPLEMENTATION_PLAN.md`](./AGENTS_TODO_IMPLEMENTATION_PLAN.md) for detailed steps.

| Phase | Component | Effort | Files |
|-------|-----------|--------|-------|
| **2** | Repository Layer | 3h | `db/repositories/agents.py` |
| **3** | Idempotency | 2h | `src/middleware/idempotency.py` |
| **4** | Session Endpoints | 4h | `src/routers/agent.py` (update) |
| **5** | Step Endpoints | 4h | `src/routers/agent.py` (update) |
| **6** | Run Endpoints | 3h | `src/routers/agent_runs.py` (update) |
| **7** | Rate Limiting | 2h | `src/middleware/rate_limit.py` |
| **8** | Error Handling | 2h | All routers |
| **9** | Testing | 6h | `tests/agents/` |
| **10** | Documentation | 2h | OpenAPI updates |

**Total**: ~28 hours

### Immediate Next Step

**Phase 2: Repository Layer**

Create `db/postgres_control/repositories/agents.py`:

```python
class AgentSessionRepository:
    """CRUD operations for agent sessions."""
    
    def create(self, db: Session, **kwargs) -> AgentSession:
        """Create new session."""
        
    def list_by_user(
        self, 
        db: Session, 
        user_id: str,
        page_size: int,
        cursor: Optional[str]
    ) -> tuple[List[AgentSession], Optional[str]]:
        """List sessions with cursor pagination."""
        
    # ... more methods
```

Reference: `db/postgres_control/repositories/` for existing patterns.

---

## 📖 API Reference

### Planned Endpoints (Phase 4-6)

#### Sessions

```http
POST /v1/agents/sessions
GET /v1/agents/sessions
GET /v1/agents/sessions/{session_id}
DELETE /v1/agents/sessions/{session_id}
```

#### Steps

```http
GET /v1/agents/sessions/{session_id}/steps
POST /v1/agents/sessions/{session_id}/steps
```

#### Runs

```http
POST /v1/agent-runs
GET /v1/agent-runs/{run_id}
```

### Request Examples

#### Create Session

```json
POST /v1/agents/sessions
Content-Type: application/json
Idempotency-Key: unique-key-123

{
  "prompt": "Analyze this dataset",
  "temperature": 0.2,
  "max_steps": 10,
  "tools": ["graph.search", "system.metrics"],
  "manager": "planner"
}
```

Response:
```json
HTTP/1.1 201 Created
Location: /v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000
X-Request-Id: abc123

{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-123",
  "tenant_id": "tenant-admin-root",
  "status": "active",
  "temperature": 0.2,
  "max_steps": 10,
  ...
}
```

#### Add Step

```json
POST /v1/agents/sessions/{session_id}/steps
Content-Type: application/json
Idempotency-Key: step-key-456

{
  "type": "user",
  "message": "What is the status?",
  "input": {"query": "status"}
}
```

Response:
```json
HTTP/1.1 202 Accepted
Location: /v1/agents/sessions/{session_id}/steps/{step_id}

{
  "step_id": "...",
  "seq": 1,
  "status": "queued"
}
```

#### List Sessions

```http
GET /v1/agents/sessions?page_size=20&page_token=abc
If-None-Match: "etag-xyz"
```

Response (Cache Hit):
```http
HTTP/1.1 304 Not Modified
ETag: "etag-xyz"
```

Response (Cache Miss):
```json
HTTP/1.1 200 OK
ETag: "etag-new"

{
  "items": [...],
  "next_page_token": "def"
}
```

---

## 🔧 Configuration

Add to `.env`:

```bash
# Idempotency
IDEMPOTENCY_TTL_SECONDS=86400  # 24 hours

# Agent limits (to be added in Phase 7)
AGENT_MAX_STEPS_DEFAULT=8
AGENT_MAX_STEPS_LIMIT=64
AGENT_SESSION_TTL_DAYS=7
AGENT_STEP_RATE_LIMIT=60   # per minute
AGENT_RUN_RATE_LIMIT=10    # per minute
```

---

## 📁 File Structure

```
Cineca-Agentic-Platform/
├── db/
│   ├── postgres_control/
│   │   ├── models/
│   │   │   ├── agent_session.py       ✅ NEW
│   │   │   ├── agent_step.py          ✅ NEW
│   │   │   ├── agent_run.py           ✅ NEW
│   │   │   └── idempotency_key.py     ✅ NEW
│   │   ├── alembic/versions/
│   │   │   └── 008_create_agent_tables.py ✅ NEW
│   │   └── repositories/
│   │       └── agents.py              ⏳ Phase 2
│   └── redis_cache/
│       └── agents.py                  ✅ NEW
├── src/
│   ├── schemas/
│   │   └── agents.py                  ✅ NEW
│   ├── middleware/
│   │   ├── idempotency.py             ⏳ Phase 3
│   │   └── rate_limit.py              ⏳ Phase 7
│   └── routers/
│       ├── agent.py                   ⏳ Phase 4-5 (update)
│       └── agent_runs.py              ⏳ Phase 6 (update)
├── tests/
│   └── agents/                        ⏳ Phase 9
│       ├── test_sessions.py
│       ├── test_steps.py
│       └── test_runs.py
├── scripts/
│   └── test_agents_setup.py           ✅ NEW
└── docs/
    ├── AGENTS_TODO_IMPLEMENTATION_PLAN.md     ✅ NEW
    ├── AGENTS_QUICKSTART.md                   ✅ NEW
    ├── AGENTS_IMPLEMENTATION_SUMMARY.md       ✅ NEW
    └── AGENTS_README.md                       ✅ NEW (this file)
```

**Legend:**
- ✅ NEW - Created in Phase 1
- ⏳ Phase N - To be implemented

---

## 🐛 Troubleshooting

### Migration Fails

```bash
# Check current version
cd db/postgres_control
alembic current

# If showing wrong version
alembic stamp 007
alembic upgrade head
```

### Redis Connection Errors

```bash
# Check Redis is running
docker compose ps redis

# Test connectivity
docker exec -it redis redis-cli PING

# Restart if needed
docker compose restart redis
```

### Import Errors

```bash
# Rebuild containers
docker compose build app
docker compose up -d app

# Check logs
docker logs app
```

### Test Script Fails

```bash
# Ensure services are running
docker compose up -d

# Wait for services to be ready
sleep 10

# Run test again
python scripts/test_agents_setup.py
```

---

## 📞 Support

For implementation help:

1. **Documentation**
   - [`AGENTS_TODO_IMPLEMENTATION_PLAN.md`](./AGENTS_TODO_IMPLEMENTATION_PLAN.md) - Detailed phases
   - [`AGENTS_QUICKSTART.md`](./AGENTS_QUICKSTART.md) - Quick reference
   - [`AGENTS_IMPLEMENTATION_SUMMARY.md`](./AGENTS_IMPLEMENTATION_SUMMARY.md) - Overview

2. **Reference Code**
   - `src/routers/jobs.py` - Similar CRUD patterns
   - `db/postgres_control/repositories/` - Repository examples
   - `src/security/perm.py` - RBAC patterns

3. **Community**
   - Project issue tracker
   - Internal documentation wiki

---

## 📊 Progress Tracker

- [x] Phase 1: Foundation (Complete)
  - [x] Database models
  - [x] Alembic migration
  - [x] Redis helpers
  - [x] Pydantic schemas
  - [x] Documentation
  - [x] Test scripts

- [ ] Phase 2: Repository Layer
- [ ] Phase 3: Idempotency Middleware
- [ ] Phase 4: Session Endpoints
- [ ] Phase 5: Step Endpoints
- [ ] Phase 6: Run Endpoints
- [ ] Phase 7: Rate Limiting
- [ ] Phase 8: Error Handling
- [ ] Phase 9: Testing
- [ ] Phase 10: Documentation

**Completion**: 10% (Phase 1 of 10)

---

**Status**: ✅ Phase 1 Complete - Foundation Ready  
**Next**: Phase 2 - Repository Layer Implementation  
**ETA**: ~28 hours for full implementation (Phases 2-10)

🚀 **Ready to build!**
