# Agents API Implementation Progress

## Completed ✅

### 1. Database Layer (Phase 1)

**SQLAlchemy Models** (`db/postgres_control/models/`)
- ✅ `agent_session.py` - Session state with configuration, metadata, relationships
- ✅ `agent_step.py` - Step tracking with sequence numbers, type checking
- ✅ `agent_run.py` - Run execution tracking with metrics
- ✅ `idempotency_key.py` - Request deduplication
- ✅ Updated `__init__.py` to export new models

**Alembic Migration** (`db/postgres_control/alembic/versions/`)
- ✅ `008_create_agent_tables.py` - Full schema with:
  - All tables with proper constraints (CHECK, FOREIGN KEY, UNIQUE)
  - Performance indexes (DESC ordering for time-based queries)
  - Triggers for auto-updating updated_at timestamps
  - Proper cascade delete behavior

### 2. Redis Layer (Phase 1)

**Redis Helpers** (`db/redis_cache/agents.py`)
- ✅ Session state caching with TTL
- ✅ Step sequence allocation (atomic INCR)
- ✅ Distributed locks (session and step-level)
- ✅ Cancellation flags with TTL
- ✅ ETag computation and caching for lists
- ✅ Idempotency response caching

### 3. Schema Layer (Phase 1)

**Pydantic Schemas** (`src/schemas/agents.py`)
- ✅ `CreateSessionRequest` - Session creation with full config
- ✅ `SessionResponse` - Complete session details
- ✅ `SessionListItem` / `SessionListResponse` - Paginated lists
- ✅ `CreateStepRequest` / `StepResponse` / `StepListResponse` - Step operations
- ✅ `CreateRunRequest` / `RunResponse` - Run operations
- ✅ `ProblemDetail` - RFC7807 error responses

---

## TODO - Implementation Phases

### Phase 2: Repository Layer (NEXT)

Create `db/postgres_control/repositories/agents.py` with:

```python
class AgentSessionRepository:
    def create(self, db: Session, *, user_id, tenant_id, ...) -> AgentSession
    def get_by_id(self, db: Session, session_id: UUID) -> Optional[AgentSession]
    def list_by_user(self, db: Session, user_id: str, page_size: int, cursor: str) -> tuple[List[AgentSession], Optional[str]]
    def update_status(self, db: Session, session_id: UUID, status: str) -> AgentSession
    def delete(self, db: Session, session_id: UUID) -> None

class AgentStepRepository:
    def create(self, db: Session, *, session_id, seq, type, ...) -> AgentStep
    def get_by_id(self, db: Session, step_id: UUID) -> Optional[AgentStep]
    def list_by_session(self, db: Session, session_id: UUID, page_size: int, cursor: str) -> tuple[List[AgentStep], Optional[str]]
    def update_status(self, db: Session, step_id: UUID, status: str, output: Dict, ...) -> AgentStep

class AgentRunRepository:
    def create(self, db: Session, *, user_id, session_id, ...) -> AgentRun
    def get_by_id(self, db: Session, run_id: UUID) -> Optional[AgentRun]
    def update_status(self, db: Session, run_id: UUID, status: str, ...) -> AgentRun

class IdempotencyRepository:
    def get_or_create(self, db: Session, key: str, owner_user_id: str, ...) -> tuple[IdempotencyKey, bool]
    def mark_replayed(self, db: Session, key: str) -> None
```

**Cursor Pagination Utility:**
- Base64-encoded JSON with `{last_created_at, last_id}` for stable ordering
- Decrypt/validate cursors to prevent tampering

### Phase 3: Idempotency Middleware

Create `src/middleware/idempotency.py`:

```python
async def idempotency_middleware(request: Request, call_next):
    """
    Check Idempotency-Key header on POST requests.
    - Hash request body
    - Check Redis cache first (fast path)
    - Check PostgreSQL if not in cache
    - If replay: return cached response with Idempotency-Replayed: true header
    - If new: proceed, then cache response
    """
```

Alternative: Use dependency injection pattern instead of middleware:

```python
async def handle_idempotency(
    request: Request,
    response: Response,
    user: UserInfo,
    idem_key: Optional[str] = Header(None, alias="Idempotency-Key")
) -> Optional[Dict]:
    # Returns cached response or None
```

### Phase 4: Session Endpoints

Update `src/routers/agent.py`:

**POST /agents/sessions**
```python
@router.post("/sessions", status_code=201)
async def create_session(
    req: CreateSessionRequest,
    request: Request,
    response: Response,
    user: UserInfo = Depends(require_perms(["agents:run", "admin:all"])),
    db: Session = Depends(get_db),
):
    # 1. Handle idempotency (check header)
    # 2. If session_id provided and owned -> return 200 (idempotent)
    # 3. Create new session in DB
    # 4. Initialize Redis state (status=active, seq=0)
    # 5. Set Location header
    # 6. Invalidate user's sessions ETag
    # 7. Return 201 with SessionResponse
```

**GET /agents/sessions**
```python
@router.get("/sessions")
async def list_sessions(
    page_size: int = Query(20, ge=1, le=100),
    page_token: Optional[str] = None,
    request: Request,
    response: Response,
    user: UserInfo = Depends(require_perms(["agents:run", "admin:all"])),
    db: Session = Depends(get_db),
):
    # 1. Check If-None-Match header vs cached ETag
    # 2. If match -> return 304
    # 3. Query DB with cursor pagination (user_id filter unless admin)
    # 4. Compute new ETag, cache it
    # 5. Set ETag header
    # 6. Return SessionListResponse
```

**GET /agents/sessions/{session_id}**
```python
@router.get("/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    user: UserInfo = Depends(require_perms(["agents:run", "admin:all"])),
    db: Session = Depends(get_db),
):
    # 1. Fetch from DB
    # 2. Check ownership (404 if not owner and not admin)
    # 3. Enrich with Redis volatile state (heartbeat, last_seq)
    # 4. Return SessionResponse
```

**DELETE /agents/sessions/{session_id}**
```python
@router.delete("/sessions/{session_id}", status_code=204)
async def cancel_session(
    session_id: UUID,
    user: UserInfo = Depends(require_perms(["agents:run", "admin:all"])),
    db: Session = Depends(get_db),
):
    # 1. Check ownership
    # 2. Acquire session lock
    # 3. Set Redis cancel flag
    # 4. Update DB status to 'cancelled'
    # 5. Invalidate ETags
    # 6. Return 204 (idempotent)
```

### Phase 5: Step Endpoints

**GET /agents/sessions/{session_id}/steps**
```python
@router.get("/sessions/{session_id}/steps")
async def list_steps(
    session_id: UUID,
    page_size: int = Query(50, ge=1, le=100),
    page_token: Optional[str] = None,
    request: Request,
    response: Response,
    user: UserInfo = Depends(require_perms(["agents:run", "admin:all"])),
    db: Session = Depends(get_db),
):
    # 1. Check session ownership
    # 2. Check If-None-Match vs steps ETag
    # 3. Query steps with pagination (ORDER BY seq ASC)
    # 4. Compute and cache ETag
    # 5. Return StepListResponse
```

**POST /agents/sessions/{session_id}/steps**
```python
@router.post("/sessions/{session_id}/steps", status_code=202)
async def create_step(
    session_id: UUID,
    req: CreateStepRequest,
    request: Request,
    response: Response,
    user: UserInfo = Depends(require_perms(["agents:run", "admin:all"])),
    db: Session = Depends(get_db),
):
    # 1. Handle idempotency
    # 2. Check session ownership and status=active
    # 3. Acquire session lock
    # 4. Check max_steps not exceeded
    # 5. Allocate seq via Redis INCR
    # 6. Create step in DB (status=queued)
    # 7. Update session.last_step_id
    # 8. Update Redis session cache
    # 9. Invalidate steps ETag
    # 10. Enqueue to worker (if orchestrator available)
    # 11. Return 202 with {step_id, seq, status: "queued"}
```

### Phase 6: Run Endpoints

Update `src/routers/agent_runs.py`:

**POST /agent-runs**
```python
@router.post("", status_code=201)
async def create_agent_run(
    req: CreateRunRequest,
    request: Request,
    response: Response,
    user: UserInfo = Depends(require_perms(["agents:run", "admin:all"])),
    db: Session = Depends(get_db),
):
    # 1. Handle idempotency
    # 2. If no session_id -> create session first
    # 3. Create AgentRun record
    # 4. Invoke orchestrator (if available)
    # 5. Update run status and latency
    # 6. Set Location header
    # 7. Return RunResponse with steps
```

**GET /agent-runs/{run_id}**
```python
@router.get("/{run_id}")
async def get_agent_run(
    run_id: UUID,
    user: UserInfo = Depends(require_perms(["agents:run", "admin:all"])),
    db: Session = Depends(get_db),
):
    # 1. Fetch run from DB
    # 2. Check ownership
    # 3. Optionally join session and steps
    # 4. Return RunResponse
```

### Phase 7: Rate Limiting

Create `src/middleware/rate_limit_agents.py`:

```python
async def check_agent_rate_limit(user_id: str, route: str) -> None:
    """
    Redis-based token bucket rate limiter.
    - Key: rl:agent:{user_id}:{route}
    - Limit: configurable per-route (e.g., 60/min for POST steps, 10/min for POST runs)
    - Headers: RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset
    - Response: 429 with Retry-After if exceeded
    """
```

Use as dependency:
```python
Depends(check_agent_rate_limit)
```

### Phase 8: Error Handling

Update all endpoints to use RFC7807 format:

```python
from src.schemas.agents import ProblemDetail

def raise_problem(status: int, title: str, detail: str, request_id: str):
    raise HTTPException(
        status_code=status,
        detail=ProblemDetail(
            type=f"https://api.example.com/problems/{title.lower().replace(' ', '-')}",
            title=title,
            status=status,
            detail=detail,
            instance=request.url.path,
            extensions={"correlation_id": request_id, "X-Request-Id": request_id}
        ).dict()
    )
```

### Phase 9: Testing

Create `tests/agents/` with:

**test_sessions.py**
- `test_create_session_201`
- `test_create_session_idempotent_200`
- `test_list_sessions_pagination`
- `test_list_sessions_etag_304`
- `test_get_session_ownership`
- `test_cancel_session_idempotent`

**test_steps.py**
- `test_create_step_202`
- `test_create_step_exceed_max_steps_409`
- `test_list_steps_pagination_asc`
- `test_step_sequencing_concurrent`
- `test_step_idempotency_replay`

**test_runs.py**
- `test_create_run_with_session`
- `test_create_run_without_session_auto_create`
- `test_get_run_by_id`
- `test_run_ownership_404`

**test_rbac.py**
- `test_user_cannot_access_other_user_session`
- `test_admin_can_access_all_sessions`

**test_rate_limit.py**
- `test_post_steps_rate_limit_429`

**test_concurrency.py**
- `test_parallel_step_posts_unique_seqs`

### Phase 10: OpenAPI Documentation

Update router docstrings and add examples:

```python
@router.post(
    "/sessions",
    status_code=201,
    response_model=SessionResponse,
    responses={
        201: {
            "description": "Session created",
            "headers": {
                "Location": {"description": "URI of created session"},
                "X-Request-Id": {"description": "Request correlation ID"}
            }
        },
        200: {
            "description": "Existing session returned (idempotent)",
            "headers": {"Idempotency-Replayed": {"description": "true"}}
        },
        400: {"model": ProblemDetail},
        401: {"model": ProblemDetail},
        403: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
    },
    summary="Create agent session",
    description="Create a new agent session or return existing if session_id provided...",
)
```

Add OpenAPI examples:
```python
class CreateSessionRequest(BaseModel):
    ...
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "prompt": "Analyze this dataset",
                    "manager": "planner",
                    "temperature": 0.2,
                    "max_steps": 10,
                    "tools": ["graph.search", "system.metrics"]
                }
            ]
        }
```

---

## Migration Steps

### 1. Apply Database Migration

```bash
cd db/postgres_control
alembic upgrade head  # Applies 008_create_agent_tables.py
```

### 2. Verify Tables Created

```bash
docker exec -it postgres psql -U cineca_user -d cineca_platform
\dt agent_*
\d agent_sessions
```

### 3. Test Redis Helpers

```python
from db.redis_cache.agents import allocate_next_seq, session_lock
import uuid

session_id = uuid.uuid4()
seq1 = allocate_next_seq(session_id)  # Should be 1
seq2 = allocate_next_seq(session_id)  # Should be 2

with session_lock(session_id):
    print("Lock acquired")
```

### 4. Integration Test Plan

Run full end-to-end test:
1. Create session with idempotency key
2. Replay with same key -> 200 + replay header
3. Add 5 steps with concurrent requests
4. List steps with pagination
5. Verify seq is 1-5 without gaps
6. Cancel session
7. Verify status=cancelled
8. Attempt to add step -> 409

---

## Configuration

Add to `src/config.py`:

```python
# Agent-specific settings
AGENT_MAX_STEPS_DEFAULT: int = Field(default=8)
AGENT_MAX_STEPS_LIMIT: int = Field(default=64)
AGENT_SESSION_TTL_DAYS: int = Field(default=7)
AGENT_STEP_RATE_LIMIT: int = Field(default=60)  # per minute
AGENT_RUN_RATE_LIMIT: int = Field(default=10)  # per minute
```

---

## Next Steps

1. **Implement Phase 2 (Repositories)** - Database access layer with cursor pagination
2. **Implement Phase 3 (Idempotency)** - Middleware or dependency for POST deduplication
3. **Implement Phase 4 (Sessions)** - Full CRUD with RBAC, ETags, pagination
4. **Implement Phase 5 (Steps)** - Sequencing with Redis locks and concurrency safety
5. **Implement Phase 6 (Runs)** - Integrate with orchestrator
6. **Implement Phase 7 (Rate Limiting)** - Token bucket with Redis
7. **Implement Phase 8 (Error Handling)** - RFC7807 standardization
8. **Implement Phase 9 (Testing)** - Comprehensive integration tests
9. **Implement Phase 10 (Documentation)** - OpenAPI examples and descriptions

---

## Files Created So Far

```
db/postgres_control/models/agent_session.py       ✅
db/postgres_control/models/agent_step.py          ✅
db/postgres_control/models/agent_run.py           ✅
db/postgres_control/models/idempotency_key.py     ✅
db/postgres_control/models/__init__.py            ✅ (updated)
db/postgres_control/alembic/versions/008_create_agent_tables.py ✅
db/redis_cache/agents.py                          ✅
src/schemas/agents.py                             ✅
docs/AGENTS_TODO_IMPLEMENTATION_PLAN.md           ✅ (this file)
```

## Estimated Effort

- **Phase 1 (Done)**: Database + Redis + Schemas - 4 hours ✅
- **Phase 2**: Repositories - 3 hours
- **Phase 3**: Idempotency - 2 hours
- **Phase 4**: Session endpoints - 4 hours
- **Phase 5**: Step endpoints - 4 hours
- **Phase 6**: Run endpoints - 3 hours
- **Phase 7**: Rate limiting - 2 hours
- **Phase 8**: Error handling - 2 hours
- **Phase 9**: Testing - 6 hours
- **Phase 10**: Documentation - 2 hours

**Total**: ~32 hours remaining for full implementation

---

## Key Design Decisions

1. **Cursor Pagination**: Base64-encoded `{created_at, id}` tuples for stable, opaque cursors
2. **Redis for Speed**: Hot path (seq allocation, locks, ETags) uses Redis; durable state in Postgres
3. **Idempotency**: Hybrid - Redis cache (short TTL) + Postgres (long retention)
4. **RBAC**: Leverage existing `require_perms()` with user:me and admin:all
5. **Error Format**: RFC7807 with extensions for correlation_id and X-Request-Id
6. **Concurrency**: Redis locks prevent race conditions on session mutations
7. **ETags**: List-level (not item-level) for performance; invalidated on mutations
8. **Status Lifecycle**: active → completed/cancelled/failed (terminal states)
9. **Steps Ordering**: Always ascending by seq for reproducibility
10. **Runs**: Can be one-shot (no session_id) or session-bound
