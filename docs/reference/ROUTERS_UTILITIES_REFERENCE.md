# Cineca Agentic Platform - Routers & Utilities Reference

**Last Updated:** 2025-10-24  
**Purpose:** Comprehensive reference for all HTTP routers and utility modules

---

## Table of Contents

1. [Overview](#overview)
2. [Router Architecture](#router-architecture)
3. [Core Routers](#core-routers)
   - [Authentication Router](#authentication-router)
   - [Health Router](#health-router)
   - [Jobs Router](#jobs-router)
   - [Agent Router](#agent-router)
   - [Agent Runs Router](#agent-runs-router)
   - [Admin Router](#admin-router)
   - [Internal DB Router](#internal-db-router)
   - [Internal Ops Router](#internal-ops-router)
   - [Tools Router](#tools-router)
   - [Models Router](#models-router)
   - [Tenants Router](#tenants-router)
4. [Utility Modules](#utility-modules)
   - [Deprecation Utility](#deprecation-utility)
   - [ETag Utility](#etag-utility)
   - [Idempotency Utility](#idempotency-utility)
   - [Pagination Utility](#pagination-utility)
   - [Principal Utility](#principal-utility)
   - [Provider Resolver](#provider-resolver)
5. [Integration Patterns](#integration-patterns)
6. [Best Practices](#best-practices)

---

## Overview

The Cineca Agentic Platform routers layer provides HTTP API endpoints for:

- **Authentication**: OIDC-based user identity and token validation
- **Health Monitoring**: Liveness, readiness, and dependency health checks
- **Job Management**: Background task creation, monitoring, and cancellation
- **Agent Orchestration**: Multi-turn conversation sessions and workflow runs
- **Administrative Operations**: Platform management and internal tooling
- **Model Management**: LLM provider and instance configuration
- **Multi-Tenancy**: Tenant isolation and resource scoping

**Key Design Principles:**
- **RESTful API**: Standard HTTP methods (GET, POST, DELETE) with proper status codes
- **OpenAPI Documentation**: Auto-generated schemas with FastAPI
- **Authentication**: OAuth2/OIDC bearer tokens with scope-based authorization
- **Idempotency**: Support for `Idempotency-Key` headers on mutations
- **Caching**: ETag-based conditional requests (304 Not Modified)
- **Rate Limiting**: Per-user throttling with Redis backend
- **Error Handling**: RFC 7807 Problem Details for errors

---

## Router Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │    Health    │  │     Auth     │  │     Jobs     │         │
│  │   (public)   │  │  (authn/z)   │  │   (users)    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         │                │                  │                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │    Agent     │  │  Agent Runs  │  │    Tools     │         │
│  │  (sessions)  │  │ (one-shot)   │  │(MCP invoke)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         │                │                  │                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │    Admin     │  │   Internal   │  │   Tenants    │         │
│  │  (admin:all) │  │(internal:all)│  │(multi-tenant)│         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
         ↓                      ↓                      ↓
   ┌──────────┐          ┌──────────┐          ┌──────────┐
   │  Redis   │          │PostgreSQL│          │ Memgraph │
   │  Cache   │          │  Control │          │  Graph   │
   └──────────┘          └──────────┘          └──────────┘
```

### Router Lifecycle

1. **Import** → Lazy loading via `src.app` (avoid circular deps)
2. **Mount** → Application includes router with prefix
3. **Request** → FastAPI routes to handler with dependencies
4. **Response** → JSON/streaming with headers (ETag, Location, etc.)

---

## Core Routers

### Authentication Router

**File:** `src/routers/auth.py`  
**Mount:** `/v1/auth`  
**Tags:** `auth`

#### Features

- **OIDC Token Validation**: JWT signature/issuer/audience verification
- **User Identity Extraction**: Subject, scopes, roles from token claims
- **Permission Resolution**: Map scopes/roles to effective permissions
- **Bearer Auth**: HTTP Authorization header (RFC 6750)

#### Models

```python
class UserInfo(BaseModel):
    sub: Optional[str]  # Token subject (stable user ID)
    username: Optional[str]  # Deprecated legacy field
    tenant_id: Optional[str]  # Resolved tenant from context
    scopes: List[str]  # Granted OAuth scopes
    roles: List[str]  # Roles array from token
    permissions: List[str]  # Effective permissions (computed)
```

#### Endpoints

**GET /auth/me** - Get current user claims
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://api.example.com/v1/auth/me

# Response:
{
  "sub": "user123",
  "scopes": ["user:me", "jobs:read"],
  "roles": ["developer"],
  "permissions": ["jobs:read", "user:me"]
}
```

#### Dependencies

```python
# Get current user (relaxed validator - signature only)
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> UserInfo:
    """Validate Bearer token and return identity."""
    # Validates signature, iss, aud via OIDC JWKS or legacy HS256
    # Extracts permissions from scope/scopes/permissions/roles claims
```

#### Configuration

```python
# OIDC (Auth0, Keycloak, etc.)
OIDC_JWKS_URL = "https://tenant.auth0.com/.well-known/jwks.json"
JWT_AUDIENCE = "https://api.example.com"
JWT_ISSUER = "https://tenant.auth0.com/"

# Legacy HS256 fallback
JWT_SECRET = "your-secret-key"
JWT_ALGORITHM = "HS256"
```

---

### Health Router

**File:** `src/routers/health.py`  
**Mount:** `/v1/health` (versioned) or root path (legacy)  
**Tags:** `health`

#### Features

- **Liveness Probe**: Lightweight "am I alive?" check (no I/O)
- **Readiness Probe**: Dependency health checks (Redis, Memgraph, PostgreSQL)
- **Startup Check**: Enhanced diagnostics with rate limit config
- **Database Health**: Isolated PostgreSQL connectivity check
- **Provider Health**: LLM provider registry status and cache stats
- **Redis Health**: Job queue monitoring with per-type lengths
- **Migration Gating**: Block traffic until migrations applied
- **Admin Control**: Toggle readiness via `/health/startup/readiness`

#### Endpoints

**GET /health/live** - Liveness (always 200)
```bash
curl https://api.example.com/v1/health/live
# → ok
```

**GET /health/ready** - Readiness with dependency checks
```bash
curl https://api.example.com/v1/health/ready
# Response:
{
  "service": "cineca-agentic-platform",
  "status": "ok",
  "time": "2025-10-24T12:00:00Z",
  "checks": {
    "memgraph": {"ok": true, "status": "ok"},
    "redis": {"ok": true, "status": "ok"},
    "postgresql": {"ok": true, "status": "ok"}
  }
}
```

**GET /health/startup** - Startup diagnostics with rate limit info
```bash
curl https://api.example.com/v1/health/startup
# Includes environment.rate_limit_mode, limits, etc.
```

**GET /health/db** - PostgreSQL-specific check
```bash
curl https://api.example.com/v1/health/db
# → {"ok": true, "database": "postgresql"}
```

**GET /health/providers** - Provider registry health
```bash
curl https://api.example.com/v1/health/providers
# Response:
{
  "ok": true,
  "total_providers": 5,
  "healthy": 4,
  "unhealthy": 1,
  "by_type": {"openai": 2, "anthropic": 1},
  "cache_hit_rate": 0.85
}
```

**GET /health/redis** - Redis and queue status
```bash
curl https://api.example.com/v1/health/redis
# Response:
{
  "ok": true,
  "queues": {"demo": 0, "test": 2, "long-running": 1}
}
```

**POST /health/startup/readiness** - Admin toggle (requires `admin` scope or `X-Admin-Token`)
```bash
curl -X POST "https://api.example.com/v1/health/startup/readiness?state=not-ready" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
# → {"status": "not ready"}
```

#### Configuration

```python
# Dependency fallback
HEALTH_ALLOW_REDIS_HEALTH_FALLBACK = True
HEALTH_ALLOW_MG_HEALTH_FALLBACK = True
HEALTH_CACHE_TTL_SECONDS = 5

# Migration enforcement
ENFORCE_MIGRATIONS = "0"  # "1" to block traffic until migrations done
MIGRATIONS_APPLIED = "false"  # Set to "true" after migrations

# Admin token (optional)
ADMIN_TOKEN = "secret-admin-token"
```

---

### Jobs Router

**File:** `src/routers/jobs.py`  
**Mount:** `/v1/jobs`  
**Tags:** `jobs`

#### Features

- **Job Creation**: POST with idempotency support
- **Job Listing**: GET with status filters and pagination
- **Job Cancellation**: DELETE with idempotent behavior
- **Event Streaming**: SSE (Server-Sent Events) for real-time updates
- **Dual Backend**: Redis (default) or PostgreSQL (feature flag)
- **ETag Caching**: Conditional GET with 304 Not Modified
- **Rate Limiting**: Per-user throttling

#### Models

```python
class JobRequest(BaseModel):
    type: str  # Job type (e.g., "demo", "test")
    payload: Dict = {}  # Arbitrary JSON payload

class JobResponse(BaseModel):
    id: str  # UUID
    type: str
    status: str  # queued, running, finished, failed, cancelled
    created_at: str  # ISO 8601
    updated_at: Optional[str]
    tenant_id: Optional[str]
    owner: str  # Token subject
    result: Optional[Dict]  # Output when complete
```

#### Endpoints

**POST /jobs** - Create job with idempotency
```bash
curl -X POST https://api.example.com/v1/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: unique-key-123" \
  -d '{"type": "demo", "payload": {"duration_ms": 2000}}'

# Response (202 Accepted):
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "queued",
  "type": "demo",
  "owner": "user@example.com",
  "created_at": "2025-10-24T12:00:00Z"
}
```

**GET /jobs** - List user's jobs with filters
```bash
# All jobs
curl -H "Authorization: Bearer $TOKEN" \
  https://api.example.com/v1/jobs

# Filter by status
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.example.com/v1/jobs?status=running&status=queued"

# With ETag caching
curl -H "Authorization: Bearer $TOKEN" \
  -H "If-None-Match: W/\"abc123\"" \
  https://api.example.com/v1/jobs
# → 304 Not Modified (if unchanged)
```

**DELETE /jobs/{job_id}** - Cancel job (idempotent)
```bash
curl -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  https://api.example.com/v1/jobs/123e4567-e89b-12d3-a456-426614174000

# First call: 202 Accepted (job cancelled)
# Subsequent calls: 200 OK (already cancelled)
```

**GET /jobs/{job_id}/events** - Stream job events (SSE)
```bash
curl -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  https://api.example.com/v1/jobs/123e4567-.../events

# SSE stream:
event: status
data: {"status": "running"}

event: progress
data: {"percent": 50, "message": "Processing..."}

event: done
data: {"status": "finished", "result": {...}}
```

#### Configuration

```python
# Backend selection
USE_POSTGRES_JOBS = False  # True for PostgreSQL, False for Redis

# Allowed job types
ALLOWED_JOB_TYPES = "demo,test,long-running"

# Retention
JOB_RETENTION_DAYS = 7
```

---

### Agent Router

**File:** `src/routers/agent.py`  
**Mount:** `/v1/agents`  
**Tags:** `agents`

#### Features

- **Session Management**: Create stateful multi-turn conversations
- **Step Tracking**: Append messages/tool calls to sessions
- **Session Lifecycle**: Active, completed, cancelled states
- **ETag Support**: Conditional GET for sessions and steps
- **Pagination**: Cursor-based for sessions and steps
- **Cancellation**: Graceful session termination

#### Models

```python
class CreateSessionRequest(BaseModel):
    session_id: Optional[str]  # Optional client-provided ID
    manager: Optional[str]  # LLM manager name
    tools: List[str] = []  # Allowed tool names
    temperature: float = 0.7
    max_steps: int = 10
    metadata: Dict = {}

class SessionResponse(BaseModel):
    session_id: str
    status: str  # active, completed, cancelled
    created_at: datetime
    updated_at: datetime
    last_step_seq: int
    manager: Optional[str]
    tools: List[str]
    temperature: float
    max_steps: int

class CreateStepRequest(BaseModel):
    type: str  # message, user, assistant, tool, system, error
    message: Optional[str]
    tool: Optional[str]
    input: Optional[Dict]
    output: Optional[Dict]

class StepResponse(BaseModel):
    step_id: str
    session_id: str
    seq: int  # Auto-incrementing sequence
    type: str
    message: Optional[str]
    tool: Optional[str]
    input: Optional[Dict]
    output: Optional[Dict]
    created_at: datetime
```

#### Endpoints

**POST /agents/sessions** - Create session
```bash
curl -X POST https://api.example.com/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "manager": "gpt-4",
    "tools": ["calculator", "search"],
    "temperature": 0.8,
    "max_steps": 15
  }'

# Response (201 Created):
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "active",
  "created_at": "2025-10-24T12:00:00Z",
  "manager": "gpt-4",
  "tools": ["calculator", "search"]
}
```

**GET /agents/sessions** - List sessions
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.example.com/v1/agents/sessions?limit=20"

# Response:
{
  "items": [...],
  "next_cursor": "cursor_token_here"
}
```

**GET /agents/sessions/{id}** - Get session details
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://api.example.com/v1/agents/sessions/550e8400-...
```

**DELETE /agents/sessions/{id}** - Cancel session
```bash
curl -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  https://api.example.com/v1/agents/sessions/550e8400-...
# → 204 No Content
```

**POST /agents/sessions/{id}/steps** - Add step
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  https://api.example.com/v1/agents/sessions/550e8400-.../steps \
  -d '{
    "type": "user",
    "message": "What is 2+2?"
  }'

# Response (201 Created):
{
  "step_id": "660e8400-...",
  "seq": 1,
  "type": "user",
  "message": "What is 2+2?"
}
```

**GET /agents/sessions/{id}/steps** - List steps
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.example.com/v1/agents/sessions/550e8400-.../steps?limit=50"
```

#### Configuration

```python
SESSION_TTL_SECONDS = 604800  # 7 days
MAX_MESSAGES_DEFAULT = 500
```

---

### Agent Runs Router

**File:** `src/routers/agent_runs.py`  
**Mount:** `/v1/agent-runs`  
**Tags:** `agents`

#### Features

- **One-Shot Execution**: Create and run agent in single request
- **Auto-Session Creation**: Optionally link to existing or auto-create session
- **Orchestrator Integration**: Delegates to orchestration service
- **Demo Fallback**: Returns echo response when orchestrator unavailable
- **Idempotency**: Support for `Idempotency-Key` header
- **Tracing**: Returns `trace_id` and `event_id` for provenance

#### Models

```python
class CreateRunRequest(BaseModel):
    prompt: str  # User input
    session_id: Optional[str]  # Link to session or auto-create
    manager: Optional[str]  # LLM manager
    tools: List[str] = []
    temperature: float = 0.7
    max_steps: int = 10
    metadata: Dict = {}
    preferred_workers: Optional[List[str]]
    llm_preferences: Optional[Dict]
    agent_role: Optional[str]

class RunResponse(BaseModel):
    run_id: str
    session_id: str
    model: Optional[str]  # Model that executed
    status: str  # succeeded, failed
    output: str  # Final result
    latency_ms: int
    trace_id: str  # Provenance trace
    event_id: str  # Provenance event
    created_at: datetime
```

#### Endpoints

**POST /agent-runs** - Create and execute run
```bash
curl -X POST https://api.example.com/v1/agent-runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: run-123" \
  -d '{
    "prompt": "Calculate 2+2",
    "tools": ["calculator"],
    "temperature": 0.7
  }'

# Response (201 Created):
{
  "run_id": "770e8400-...",
  "session_id": "880e8400-...",
  "status": "succeeded",
  "output": "The result is 4",
  "model": "gpt-4",
  "latency_ms": 1250,
  "trace_id": "trace-abc",
  "event_id": "event-123"
}
```

**GET /agent-runs/{run_id}** - Get run details
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://api.example.com/v1/agent-runs/770e8400-...

# Response:
{
  "run_id": "770e8400-...",
  "output": "The result is 4",
  "status": "succeeded",
  "latency_ms": 1250
}
```

---

### Admin Router

**File:** `src/routers/admin.py`  
**Mount:** `/v1/admin`  
**Tags:** `admin-*`  
**Authentication:** Requires `admin:all` scope

#### Features

- **Aggregator Router**: Composes multiple admin sub-routers
- **Model Management**: Admin-level model/provider operations
- **Process Management**: Built-in LLM process control
- **Job Management**: System-wide job visibility and control
- **Tenant Management**: Multi-tenant administration
- **Database Operations**: Admin proxy for internal DB maintenance

#### Sub-Routers Included

```python
# Model management (providers, instances)
router.include_router(model_management, prefix="/models")

# Built-in manifest management
router.include_router(manifests, prefix="")  # Already prefixed

# Process control
router.include_router(model_processes, prefix="/processes")

# Admin jobs (system-wide visibility)
router.include_router(admin_jobs, prefix="/jobs")

# Tenant management
router.include_router(tenants_admin, prefix="/tenants")
```

#### Access Control

All admin routes require `admin:all` scope via Security dependency:
```python
_admin_guard = Security(require_scopes(None), scopes=["admin:all"])
```

---

### Internal DB Router

**File:** `src/routers/internal_db.py`  
**Mount:** `/v1/internal/db`  
**Tags:** `internal`  
**Authentication:** Requires `internal:all` permission (service tokens only)

#### Features

- **Database Job Management**: Create/populate database operations
- **Background Processing**: Async job execution with progress tracking
- **Idempotency**: 24h idempotency key caching
- **Audit Trail**: PostgreSQL event logging for all operations
- **Job Cancellation**: Graceful stop with Redis cancel signals
- **Correlation IDs**: Request tracing across distributed systems

#### Models

```python
class DBJobRequest(BaseModel):
    type: Literal["create", "populate"]  # Job type
    wipe: Optional[bool]  # For create: wipe existing DB
    users: Optional[int]  # Number of users to generate

class DBJobResponse(BaseModel):
    ok: bool
    job_id: str  # UUID

class DBJobStatusResponse(BaseModel):
    job_id: str
    state: str  # queued, running, finished, failed, cancelled
    progress: float  # 0.0-1.0
    started_at: Optional[str]
    finished_at: Optional[str]
    message: Optional[str]
    action: str
    params: Dict
```

#### Endpoints

**POST /internal/db/jobs** - Create database job
```bash
curl -X POST https://api.example.com/v1/internal/db/jobs \
  -H "Authorization: Bearer $SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: db-create-20251024" \
  -d '{
    "type": "create",
    "wipe": true,
    "users": 100
  }'

# Response (202 Accepted):
{
  "ok": true,
  "job_id": "990e8400-e29b-41d4-a716-446655440000"
}
```

**GET /internal/db/jobs/{job_id}** - Get job status
```bash
curl -H "Authorization: Bearer $SERVICE_TOKEN" \
  https://api.example.com/v1/internal/db/jobs/990e8400-...

# Response:
{
  "job_id": "990e8400-...",
  "state": "running",
  "progress": 0.65,
  "message": "Persisting graph: 65/100 batches",
  "started_at": "2025-10-24T12:00:00Z",
  "action": "populate",
  "params": {"type": "populate", "users": 100}
}
```

**DELETE /internal/db/jobs/{job_id}** - Cancel job (idempotent)
```bash
curl -X DELETE \
  -H "Authorization: Bearer $SERVICE_TOKEN" \
  https://api.example.com/v1/internal/db/jobs/990e8400-...
# → 204 No Content
```

**GET /internal/db/counts** - Get database counts
```bash
curl -H "Authorization: Bearer $SERVICE_TOKEN" \
  https://api.example.com/v1/internal/db/counts

# Response:
{
  "ok": true,
  "nodes": 1234,
  "edges": 5678
}
```

#### Configuration

```python
# Feature toggle
INTERNAL_DB_UTILS_ENABLED = True  # Enable DB utilities

# Job processing
JOB_RETENTION_DAYS = 7
```

---

### Internal Ops Router

**File:** `src/routers/internal_ops.py`  
**Mount:** `/v1/internal/ops`  
**Tags:** `internal`  
**Authentication:** Requires `internal:all` permission (service tokens only)

#### Features

- **Auto-Start Override**: Control built-in model auto-start behavior
- **Manifest Preview**: Inspect staged manifests before deployment
- **Redis-Based State**: Ephemeral override storage with TTL
- **Audit Logging**: PostgreSQL event trail for all operations
- **Cache Coherence**: Directory mtime tracking for preview cache
- **UI/CLI Control**: Enable operators to override auto-start policies

#### Models

```python
class AutoStartOverrideRequest(BaseModel):
    enabled: bool  # Enable/disable auto-start
    note: Optional[str]  # Reason (max 200 chars)

class AutoStartOverrideResponse(BaseModel):
    allowed: bool  # Feature enabled in config
    enabled: bool  # Current override value
    ttl_seconds: int  # TTL of override (0 if disabled/error)
    error: Optional[str]  # "cache_unavailable" if Redis down

class PreviewStagedItem(BaseModel):
    manifest_id: str
    model_id: str
    est_mem_mb: int
    reason: str  # Why allowed/denied
    allowed: bool
    overridden_by_ui: bool
    concurrency_ok: bool
    whitelist_ok: bool
    resources_ok: bool

class PreviewStagedResponse(BaseModel):
    items: List[PreviewStagedItem]
    count: int
    timestamp: str
```

#### Endpoints

**POST /internal/ops/auto-start-override** - Set auto-start override
```bash
curl -X POST \
  -H "Authorization: Bearer $SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  https://api.example.com/v1/internal/ops/auto-start-override \
  -d '{
    "enabled": false,
    "note": "Disable auto-start for maintenance"
  }'

# Response (200 OK):
{
  "allowed": true,
  "enabled": false,
  "ttl_seconds": 600,
  "error": null
}
```

**GET /internal/ops/preview-staged** - Preview staged manifests
```bash
curl -H "Authorization: Bearer $SERVICE_TOKEN" \
  "https://api.example.com/v1/internal/ops/preview-staged?force_refresh=false"

# Response:
{
  "items": [
    {
      "manifest_id": "llama3.2",
      "model_id": "llama3.2-3b",
      "est_mem_mb": 2500,
      "reason": "UI_override=deny; default_auto_start=true",
      "allowed": false,
      "overridden_by_ui": true,
      "concurrency_ok": true
    }
  ],
  "count": 1,
  "timestamp": "2025-10-24T12:00:00Z"
}
```

#### Configuration

```python
# Feature control
INTERNAL_UI_OVERRIDE_ALLOWED = True  # Enable UI override feature
INTERNAL_UI_OVERRIDE_TTL_SECONDS = 600  # 10 minutes

# Cache tuning
INTERNAL_PREVIEW_CACHE_TTL_SECONDS = 60  # 1 minute
```

---

### Tools Router

**File:** `src/routers/tools.py`  
**Mount:** `/v1/tools`  
**Tags:** `tools`

#### Features

- **MCP Tool Discovery**: List available tools from registry
- **Tool Invocation**: Execute tools with input/output tracking
- **Idempotency**: POST/GET parity via `Idempotency-Key`
- **Caching**: ETag support for tool list
- **Provider Integration**: Delegate to MCP servers
- **Result Persistence**: Store invocation results in Redis

#### Models

```python
class ToolInvokeRequest(BaseModel):
    tool: str  # Tool name
    input: Dict  # Tool input parameters
    metadata: Optional[Dict]

class ToolInvokeResponse(BaseModel):
    tool: str
    status: str  # success, error
    output: Optional[Dict]
    error: Optional[str]
    invocation_id: str
```

#### Endpoints

**GET /tools** - List available tools
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://api.example.com/v1/tools

# Response:
{
  "tools": [
    {"name": "calculator", "description": "Perform calculations"},
    {"name": "search", "description": "Search the web"}
  ]
}
```

**POST /tools/invoke** - Invoke tool
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  https://api.example.com/v1/tools/invoke \
  -d '{
    "tool": "calculator",
    "input": {"a": 2, "b": 2, "op": "add"}
  }'

# Response:
{
  "tool": "calculator",
  "status": "success",
  "output": {"result": 4},
  "invocation_id": "inv-123"
}
```

---

### Models Router

**File:** `src/routers/models.py`  
**Mount:** `/v1/models`  
**Tags:** `models`

#### Features

- **Provider Management**: CRUD for LLM providers (OpenAI, Anthropic, Ollama, etc.)
- **Instance Management**: Model instance lifecycle (create, list, delete)
- **Chat Completions**: Unified chat API across providers
- **Streaming**: SSE-based streaming responses
- **Provider Health**: Health checks for configured providers
- **Model Listing**: List available models per provider

See MCP_TOOLS_REFERENCE.md for detailed model operations.

---

### Tenants Router

**File:** `src/routers/tenants.py`  
**Mount:** `/v1/tenants`  
**Tags:** `tenants`

#### Features

- **Tenant CRUD**: Create, read, update, delete tenants
- **Metadata Management**: Extensible JSON metadata per tenant
- **Dependency Checks**: Block deletion if tenant has resources
- **Admin Endpoints**: Admin-level tenant management under `/admin/tenants`

#### Models

```python
class TenantCreate(BaseModel):
    name: str
    admin_email: str
    metadata: Dict = {}

class TenantResponse(BaseModel):
    id: str
    name: str
    admin_email: str
    metadata: Dict
    created_at: str
    updated_at: str
```

#### Endpoints

**POST /tenants** - Create tenant (admin only)
**GET /tenants** - List tenants
**GET /tenants/{id}** - Get tenant details
**PATCH /tenants/{id}** - Update tenant
**DELETE /tenants/{id}** - Delete tenant

---

## Utility Modules

### Deprecation Utility

**File:** `src/utils/deprecation.py`

#### Purpose

Generate standardized HTTP deprecation headers per RFC specifications.

#### Functions

```python
def deprecation_headers(
    replacement: Optional[str] = None,
    sunset: Optional[str] = None,
    sunset_days: int = 45
) -> Dict[str, str]:
    """Return Deprecation, Sunset, and Link headers.
    
    Args:
        replacement: Canonical path for successor endpoint
        sunset: ISO date string (or auto-compute from sunset_days)
        sunset_days: Days until sunset (default 45)
    
    Returns:
        Dict with headers: Deprecation, Sunset, Link
    
    Example:
        headers = deprecation_headers(
            replacement="/v2/models",
            sunset_days=30
        )
        # → {
        #   "Deprecation": "true",
        #   "Sunset": "Fri, 23 Nov 2025 12:00:00 GMT",
        #   "Link": "</v2/models>; rel=\"successor-version\""
        # }
    """
```

#### Usage

```python
from src.utils.deprecation import deprecation_headers

@router.get("/legacy-endpoint")
async def legacy_handler(response: Response):
    # Add deprecation headers
    for key, value in deprecation_headers(
        replacement="/v2/new-endpoint",
        sunset_days=30
    ).items():
        response.headers[key] = value
    
    return {"message": "This endpoint is deprecated"}
```

---

### ETag Utility

**File:** `src/utils/etag.py`

#### Purpose

Generate and validate ETags for HTTP caching (RFC 7232).

#### Functions

```python
def generate_etag(obj: Any, weak: bool = False) -> str:
    """Generate ETag from JSON-serializable object.
    
    Args:
        obj: Object to hash (dict/list/etc.)
        weak: If True, returns weak ETag (W/"...")
    
    Returns:
        ETag string: "abc123" or W/"abc123"
    
    Example:
        etag = generate_etag({"id": "123", "name": "test"})
        # → "\"a1b2c3d4e5f6...\""
    """

def etag_for_list(items: List[Any], weak: bool = False) -> str:
    """Generate ETag for list of items.
    
    Example:
        etag = etag_for_list([{"id": "1"}, {"id": "2"}])
    """

def validate_etag(if_none_match: Optional[str], current_etag: str) -> bool:
    """Check if ETag matches If-None-Match header.
    
    Returns:
        True if matched (return 304), False otherwise
    
    Example:
        if validate_etag(request.headers.get("If-None-Match"), etag):
            return Response(status_code=304)
    """

def extract_etag_value(etag: str) -> str:
    """Extract hash from ETag (removes quotes and W/ prefix).
    
    Example:
        extract_etag_value('W/"abc123"')
        # → 'abc123'
    """
```

#### Usage

```python
from src.utils.etag import generate_etag, validate_etag

@router.get("/data")
async def get_data(
    if_none_match: Optional[str] = Header(None, alias="If-None-Match")
):
    data = {"items": [1, 2, 3]}
    etag = generate_etag(data)
    
    # Check if client has cached version
    if validate_etag(if_none_match, etag):
        return Response(status_code=304, headers={"ETag": etag})
    
    # Return fresh data
    return JSONResponse(
        content=data,
        headers={"ETag": etag, "Cache-Control": "max-age=60"}
    )
```

---

### Idempotency Utility

**File:** `src/utils/idempotency.py`

#### Purpose

Decorator-based idempotency for FastAPI endpoints using `Idempotency-Key` header.

#### Functions

```python
def idempotent(
    key_fn: Callable[..., str],
    ttl: int = 24 * 3600
) -> Callable:
    """Decorator factory for idempotent endpoints.
    
    Args:
        key_fn: Function to generate cache key from idempotency_key and args
        ttl: Cache TTL in seconds (default 24h)
    
    Example:
        @router.post("/resource")
        @idempotent(
            key_fn=lambda idem_key, **kwargs: f"create:{idem_key}",
            ttl=86400
        )
        async def create_resource(
            request: Request,
            idempotency_key: Optional[str] = Header(None)
        ):
            # Logic here - will be cached if idempotency_key provided
            return {"id": "new-resource"}
    """
```

#### How It Works

1. Extracts `Idempotency-Key` from request headers
2. Generates cache key via `key_fn`
3. Checks cache for existing response envelope
4. If cached: returns stored response with `Idempotency-Replayed: true`
5. If not cached: executes handler, stores envelope, returns result

#### Storage

- **Primary:** In-memory dict (`_IN_MEMORY_STORE`)
- **Production:** Override with Redis backend

---

### Pagination Utility

**File:** `src/utils/pagination.py`

#### Purpose

Stateless cursor-based pagination for collections.

#### Functions

```python
def make_page(
    items: List[Any],
    page_size: int = 50,
    page_token: Optional[str] = None
) -> Tuple[List[Any], Optional[str]]:
    """Paginate list with offset-based cursor.
    
    Args:
        items: Full item list
        page_size: Items per page
        page_token: Offset as string (e.g., "50")
    
    Returns:
        (page_items, next_page_token)
    
    Example:
        items = range(100)
        page, next_token = make_page(list(items), page_size=25)
        # → ([0..24], "25")
    """

def compute_etag(
    obj: Any,
    context: Optional[Dict[str, Any]] = None
) -> str:
    """Compute weak ETag with route/filter context.
    
    Args:
        obj: Primary object (response body)
        context: Route/filter context (e.g., {"route": "jobs", "status": "running"})
    
    Returns:
        Weak ETag: W/"hash"
    
    Example:
        etag = compute_etag(
            {"items": [...]},
            context={"route": "user_jobs", "status": "running"}
        )
    """
```

#### Usage

```python
from src.utils.pagination import make_page, compute_etag

@router.get("/items")
async def list_items(
    page_token: Optional[str] = None,
    limit: int = 25
):
    all_items = fetch_all_items()  # Get full list
    
    # Paginate
    page, next_token = make_page(all_items, page_size=limit, page_token=page_token)
    
    # Compute ETag
    etag = compute_etag(
        {"items": page, "next": next_token},
        context={"route": "items"}
    )
    
    return JSONResponse(
        content={"items": page, "next_page_token": next_token},
        headers={"ETag": etag}
    )
```

---

### Principal Utility

**File:** `src/utils/principal.py`

#### Purpose

Extract safe, human-friendly principal identifier from user objects.

#### Functions

```python
def principal_identity(p: Any) -> str:
    """Get principal identifier with fallback chain.
    
    Preference order:
    1. sub (OAuth subject)
    2. email
    3. name
    4. username
    5. subject (alias)
    6. "unknown"
    
    Args:
        p: Principal/user object
    
    Returns:
        String identifier
    
    Example:
        user = UserInfo(sub="user-123", email="user@example.com")
        identity = principal_identity(user)
        # → "user-123"
    """
```

#### Usage

```python
from src.utils.principal import principal_identity
from src.provenance import record_provenance

@router.post("/action")
async def perform_action(user: UserInfo = Depends(get_current_user)):
    # Use in audit logging
    record_provenance(
        actor=principal_identity(user),
        action="perform_action",
        resource="/action"
    )
    
    return {"ok": True}
```

---

### Provider Resolver

**File:** `src/utils/provider_resolver.py`

#### Purpose

Common utilities for LLM provider configuration at runtime.

#### Functions

```python
def is_ollama_provider(provider: Any) -> bool:
    """Detect if provider is Ollama-based.
    
    Checks id, name, type, base_url for "ollama" substring.
    """

def resolve_provider_base_url(provider: Any) -> Optional[str]:
    """Get effective base URL with Ollama overrides.
    
    Returns:
        Base URL (trailing slash stripped)
    
    Example:
        url = resolve_provider_base_url(provider)
        # For Ollama: reads OLLAMA_BASE_URL env var override
    """

def timeout_for_provider(
    provider: Any,
    default: Optional[httpx.Timeout] = None
) -> httpx.Timeout:
    """Get appropriate timeout for provider.
    
    Ollama providers use OLLAMA_TIMEOUT_SECS (default 60s).
    Others use DEFAULT_HTTPX_TIMEOUT.
    """

def resolve_upstream_model_id(
    provider: Any,
    resolved_model: Optional[str],
    requested_model: Optional[str],
    instance: Optional[Dict]
) -> Optional[str]:
    """Translate logical model IDs to provider-specific IDs.
    
    For Ollama: checks OLLAMA_MODEL_MAP for aliases.
    """

def debug_log_provider_call(
    logger: Any,
    event: str,
    trace_meta: Optional[Dict] = None,
    base_url: Optional[str] = None,
    resolved_model: Optional[str] = None,
    elapsed_ms: Optional[int] = None,
    status_code: Optional[int] = None,
    error: Optional[str] = None,
    **kwargs
) -> None:
    """Best-effort debug logging for provider calls.
    
    Only logs when logger.isEnabledFor(DEBUG) is True.
    """
```

#### Usage

```python
from src.utils.provider_resolver import (
    resolve_provider_base_url,
    timeout_for_provider,
    debug_log_provider_call
)

# Resolve provider config
base_url = resolve_provider_base_url(provider)
timeout = timeout_for_provider(provider)

# Make HTTP call
async with httpx.AsyncClient(timeout=timeout) as client:
    start = time.time()
    try:
        response = await client.post(
            f"{base_url}/v1/chat/completions",
            json=payload
        )
        elapsed_ms = int((time.time() - start) * 1000)
        
        debug_log_provider_call(
            logger,
            event="provider_call",
            base_url=base_url,
            elapsed_ms=elapsed_ms,
            status_code=response.status_code
        )
    except Exception as e:
        debug_log_provider_call(
            logger,
            event="provider_error",
            base_url=base_url,
            error=str(e)
        )
```

---

## Integration Patterns

### Pattern 1: Idempotent Job Creation

```python
from src.routers.jobs import JobRequest, JobResponse
from src.middleware.idempotency import IdempotencyHandler

@router.post("/jobs")
async def create_job(
    req: JobRequest,
    request: Request,
    response: Response,
    user: UserInfo = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    # Check cache
    handler = IdempotencyHandler(request, response, user.sub, db, idempotency_key)
    if idempotency_key:
        cached = handler.check()
        if cached:
            response.headers["Idempotency-Replayed"] = "true"
            return JobResponse(**cached["response"])
    
    # Create job
    job = create_job_in_db(req, user.sub)
    
    # Cache result
    if idempotency_key:
        await handler.cache(
            request_body=req.model_dump(),
            response_body=job.model_dump(),
            status_code=201
        )
    
    return job
```

### Pattern 2: ETag-Cached Listing

```python
from src.utils.etag import generate_etag, validate_etag

@router.get("/items")
async def list_items(
    response: Response,
    if_none_match: Optional[str] = Header(None, alias="If-None-Match")
):
    # Fetch data
    items = fetch_items_from_db()
    
    # Generate ETag
    etag = generate_etag({"items": items}, weak=False)
    
    # Check cache
    if validate_etag(if_none_match, etag):
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": "max-age=30"}
        )
    
    # Return fresh data
    return JSONResponse(
        content={"items": items},
        headers={
            "ETag": etag,
            "Cache-Control": "max-age=30",
            "Vary": "Authorization"
        }
    )
```

### Pattern 3: Paginated Collection with Filtering

```python
from src.utils.pagination import make_page, compute_etag

@router.get("/jobs")
async def list_jobs(
    status_filter: Optional[List[str]] = Query(None, alias="status"),
    limit: int = Query(25, ge=1, le=50),
    page_token: Optional[str] = None,
    user: UserInfo = Depends(get_current_user)
):
    # Fetch filtered jobs
    all_jobs = fetch_jobs(owner=user.sub, status=status_filter)
    
    # Paginate
    page, next_token = make_page(all_jobs, page_size=limit, page_token=page_token)
    
    # Build response
    result = {
        "items": page,
        "next_page_token": next_token,
        "has_more": next_token is not None,
        "total": len(all_jobs)
    }
    
    # Compute ETag with filter context
    etag = compute_etag(
        result,
        context={"route": "user_jobs", "status": status_filter}
    )
    
    return JSONResponse(
        content=result,
        headers={"ETag": etag, "Cache-Control": "private, max-age=15"}
    )
```

### Pattern 4: Admin Endpoint with Audit Logging

```python
from src.security.admin import require_admin
from src.provenance import record_provenance

@router.post("/admin/resource")
async def admin_create_resource(
    req: ResourceRequest,
    principal: Principal = Depends(require_admin()),
    request_id: Optional[str] = Header(None, alias="X-Request-Id")
):
    start_time = time.time()
    
    try:
        # Perform admin operation
        resource = create_resource(req)
        
        # Audit success
        record_provenance(
            actor=principal.sub,
            action="admin.create_resource",
            resource=f"/admin/resource/{resource.id}",
            input=req.model_dump(),
            output={"id": resource.id},
            duration_ms=int((time.time() - start_time) * 1000),
            success=True
        )
        
        return resource
    
    except Exception as e:
        # Audit failure
        record_provenance(
            actor=principal.sub,
            action="admin.create_resource",
            resource="/admin/resource",
            input=req.model_dump(),
            error=str(e),
            duration_ms=int((time.time() - start_time) * 1000),
            success=False
        )
        raise
```

### Pattern 5: Streaming SSE Response

```python
from fastapi.responses import StreamingResponse

@router.get("/jobs/{job_id}/events")
async def stream_job_events(
    job_id: str,
    user: UserInfo = Depends(get_current_user)
):
    async def event_generator():
        # SSE format
        while True:
            event = await get_next_job_event(job_id)
            if not event:
                break
            
            # Yield SSE-formatted event
            yield f"event: {event['type']}\n"
            yield f"data: {json.dumps(event['data'])}\n\n"
            
            if event['type'] == 'done':
                break
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
```

---

## Best Practices

### 1. Authentication & Authorization

- **Always validate tokens**: Use `Depends(get_current_user)` or `Depends(require_admin())`
- **Scope-based access**: Check permissions before operations
- **Service tokens**: Use `require_internal()` for M2M endpoints
- **Multi-tenancy**: Respect tenant isolation via `request.state.tenant_id`

### 2. Idempotency

- **Support Idempotency-Key**: All POST/PUT/DELETE mutations should honor it
- **24h TTL**: Standard cache duration for idempotency keys
- **Replay headers**: Set `Idempotency-Replayed: true` for cached responses
- **Request fingerprinting**: Include request body hash in cache key

### 3. Caching

- **Use ETags**: Generate with `generate_etag()` for GET endpoints
- **Validate If-None-Match**: Return 304 when ETag matches
- **Include context**: Filter/route context in ETag for correct invalidation
- **Cache-Control**: Set appropriate max-age (e.g., 15-60s for lists)
- **Vary header**: Always set `Vary: Authorization` for user-scoped data

### 4. Error Handling

- **RFC 7807 Problem Details**: Use structured error responses
- **Correlation IDs**: Include `X-Request-Id` in error responses
- **Appropriate status codes**: 400 (bad request), 404 (not found), 500 (internal error)
- **Error logging**: Log with structured fields for debugging
- **User-friendly messages**: Don't expose internal details

### 5. Observability

- **Structured logging**: Use `logger.info()` with `extra={}` dict
- **Provenance tracking**: Record audit trail with `record_provenance()`
- **Request IDs**: Generate and propagate `X-Request-Id` headers
- **Duration tracking**: Log operation latency in milliseconds
- **Metrics**: Emit Prometheus metrics for critical paths

### 6. API Design

- **Versioned paths**: Use `/v1/` prefix for stability
- **Resource-oriented**: Nouns in paths (e.g., `/jobs`, `/sessions`)
- **HTTP methods**: GET (read), POST (create), PATCH (update), DELETE (delete)
- **Pagination**: Cursor-based with `next_page_token` for scalability
- **Filtering**: Repeatable query params (e.g., `?status=running&status=queued`)
- **OpenAPI docs**: Rich descriptions with examples

---

## Appendix

### Router File Sizes

```
src/routers/
├── __init__.py             (bootstrap, 1KB)
├── admin_db.py             (admin DB proxy, 13KB)
├── admin_jobs.py           (admin jobs, 22KB)
├── admin_ops.py            (admin ops proxy, 8KB)
├── admin.py                (admin aggregator, 3KB)
├── agent_runs.py           (one-shot agent runs, 16KB)
├── agent.py                (agent sessions/steps, 35KB)
├── auth.py                 (authentication, 6KB)
├── health_v2.py            (v2 health, 0.2KB)
├── health.py               (health checks, 26KB)
├── internal_db.py          (internal DB ops, 32KB)
├── internal_ops.py         (internal ops, 18KB)
├── jobs.py                 (jobs management, 60KB)
├── manifests.py            (built-in manifests)
├── model_instances.py      (model instances)
├── model_management.py     (provider management)
├── model_processes.py      (process control)
├── models.py               (unified models API)
├── tenants_admin.py        (admin tenants)
├── tenants.py              (tenant CRUD)
└── tools.py                (MCP tool invoke)

Total: 21 files, ~240KB
```

### Utility File Sizes

```
src/utils/
├── deprecation.py          (deprecation headers, 1KB)
├── etag.py                 (ETag generation, 3KB)
├── idempotency.py          (idempotency decorator, 4KB)
├── pagination.py           (pagination helpers, 1KB)
├── principal.py            (principal identity, 0.6KB)
├── provider_resolver.py    (provider utilities, 5KB)
└── test_helpers.py         (test utilities)

Total: 7 files, ~15KB
```

### Related Documentation

- [MCP Tools Reference](./MCP_TOOLS_REFERENCE.md) - MCP tool catalog
- [Security Reference](./SECURITY_REFERENCE.md) - Security components
- [Services Reference](./SERVICES_REFERENCE.md) - Business logic services
- [API Best Practices](./API_BEST_PRACTICES.md) - REST API design

---

**Document Version:** 1.0  
**Last Updated:** 2025-10-24  
**Maintainer:** Cineca Agentic Platform Team
