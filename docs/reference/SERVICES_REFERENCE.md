# Cineca Agentic Platform - Services Reference

**Last Updated:** 2025-10-24  
**Purpose:** Comprehensive reference for all service components in the platform

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Service Modules](#service-modules)
   - [Service Bootstrap](#service-bootstrap)
   - [Orchestrator](#orchestrator)
   - [Session Management](#session-management)
   - [Jobs Service](#jobs-service)
   - [ETL Service](#etl-service)
   - [Archive Service](#archive-service)
   - [Health Service](#health-service)
   - [LLM Registry](#llm-registry)
   - [Process Service](#process-service)
   - [Status Service](#status-service)
   - [Service Metrics](#service-metrics)
   - [Tenant Management](#tenant-management)
   - [Invocation Store](#invocation-store)
   - [Job Store](#job-store)
4. [Integration Patterns](#integration-patterns)
5. [Configuration Reference](#configuration-reference)

---

## Overview

The Cineca Agentic Platform services layer provides core business logic for:

- **Orchestration**: Multi-agent workflow coordination with LLM integration
- **Session Management**: Chat session lifecycle with Redis/memory backend
- **Job Processing**: Asynchronous task execution with PostgreSQL + Redis
- **ETL Operations**: Data import/export for Memgraph graph database
- **Archive & Backup**: Graph snapshots with compression and rotation
- **Health Monitoring**: Dependency probes for Redis and Memgraph
- **LLM Registry**: Built-in model manifest management
- **Process Management**: Lifecycle tracking for built-in LLM processes
- **Metrics**: Prometheus instrumentation for observability
- **Multi-Tenancy**: Tenant isolation and metadata management

**Key Design Principles:**
- **Lazy Loading**: Services use PEP 562 `__getattr__` for efficient imports
- **ServiceBase Protocol**: Shared lifecycle (start/stop) and health checks
- **Dual Backends**: Redis primary with in-memory fallback
- **Async-First**: All public APIs use `async/await`
- **Dependency Tolerance**: Graceful degradation when optional deps unavailable

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────┐         │
│  │            Orchestrator Service                   │         │
│  │  (Planning, Tool Exec, Multi-LLM Coordination)   │         │
│  └──────────────────────────────────────────────────┘         │
│         ↓                ↓                 ↓                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │   Session    │  │     Jobs     │  │  LLM Registry│        │
│  │   Service    │  │   Service    │  │              │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│         ↓                ↓                 ↓                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │     ETL      │  │   Archive    │  │    Health    │        │
│  │   Service    │  │   Service    │  │   Service    │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│         ↓                ↓                 ↓                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │   Process    │  │   Metrics    │  │   Tenants    │        │
│  │   Service    │  │   Service    │  │   Service    │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│                                                                │
└─────────────────────────────────────────────────────────────────┘
         ↓                      ↓                      ↓
   ┌──────────┐          ┌──────────┐          ┌──────────┐
   │  Redis   │          │ Memgraph │          │PostgreSQL│
   │  Cache   │          │  Graph   │          │  Control │
   └──────────┘          └──────────┘          └──────────┘
```

### Service Lifecycle

1. **Initialization** → Lazy loading via `__getattr__`
2. **Start** → `ServiceBase.start()` for setup
3. **Health Checks** → `liveness()`, `readiness()`, `check()`
4. **Operation** → Business logic execution
5. **Stop** → `ServiceBase.stop()` for cleanup

---

## Service Modules

### Service Bootstrap

**File:** `src/services/__init__.py`

#### Features

- **Lazy Import System**: PEP 562 `__getattr__` for on-demand loading
- **Shared Types**: `ServiceError`, `ServiceResult[T]`, `ServiceStatus`, `ServiceBase`
- **Typed Getters**: Factory functions for all services
- **Lifecycle Hooks**: Standard `start()`, `stop()`, health checks

#### Core Types

```python
# Service Result (generic)
@dataclass
class ServiceResult[T]:
    ok: bool
    data: Optional[T] = None
    error: Optional[str] = None
    code: Optional[str] = None

# Service Base Protocol
class ServiceBase:
    name: str
    
    async def start(self) -> None:
        """Initialize service resources"""
    
    async def stop(self) -> None:
        """Cleanup service resources"""
    
    async def liveness(self) -> ServiceResult[Dict[str, Any]]:
        """Quick health check (is service responsive?)"""
    
    async def readiness(self) -> ServiceResult[Dict[str, Any]]:
        """Dependency health check (can service handle requests?)"""
    
    async def check(self) -> ServiceResult[Dict[str, Any]]:
        """Detailed status check"""
```

#### Service Getters

```python
from src.services import (
    get_orchestrator,
    get_session_service,
    get_etl_service,
    get_archive_service,
    get_health_service,
    get_service_metrics,
    get_status_service
)

# Usage
orchestrator = get_orchestrator()
sessions = get_session_service()
```

---

### Orchestrator

**File:** `src/services/orchestrator.py`

#### Features

- **Multi-LLM Coordination**: Named LLM clients with routing
- **Tool Registry**: Register sync/async Python callables
- **Planning**: LLM-based step generation from natural language goals
- **Execution**: Sequential step execution with context passing
- **Streaming**: Yield results after each step
- **Fallback**: Automatic fallback to main LLM on failure
- **ACL**: Tool access control per LLM client
- **Built-in Integration**: Auto-register built-in models from manifest

#### Core Models

```python
@dataclass
class Step:
    id: str
    action: str
    input: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class OrchestrationContext:
    goal: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tenant_id: Optional[str] = None
    vars: Dict[str, Any] = field(default_factory=dict)

@dataclass
class OrchestrationResult:
    goal: str
    steps: List[Step] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    started_at: str
    finished_at: Optional[str] = None
    error: Optional[str] = None
    manager: Optional[str] = None  # LLM that produced plan
```

#### Usage Examples

**Basic Orchestration**
```python
from src.services import get_orchestrator

orch = get_orchestrator()

# Run with planning
result = await orch.run(
    goal="Find all users named John and count them",
    user_id="user-123",
    session_id="sess-abc",
    tenant_id="acme"
)

if result.ok:
    print(f"Completed {len(result.data['outputs'])} steps")
```

**Tool Registration**
```python
# Register sync tool
def calculator(a: int, b: int, op: str) -> Dict[str, Any]:
    if op == "add":
        return {"result": a + b}
    elif op == "multiply":
        return {"result": a * b}
    return {"error": "Unknown operation"}

orch.register_tool("calculator", calculator)

# Register async tool
async def query_database(query: str, **kwargs) -> Dict[str, Any]:
    rows = await db.query(query)
    return {"rows": rows, "count": len(rows)}

orch.register_tool("query_db", query_database)
```

**Multi-LLM Setup**
```python
# Environment configuration
LLM_CLIENTS = "planner=http://localhost:8000,worker=http://localhost:8001"
LLM_TOOL_PREFERENCES = "calculator=worker,query_db=planner"
LLM_TOOL_ACL = "planner=query_db|analyze,worker=calculator|transform"

# Programmatic registration
orch.register_llm(
    name="custom-gpt4",
    base_url="https://api.openai.com/v1",
    model="gpt-4",
    api_key="sk-...",
    tenant_id="acme"
)

# Set tenant main LLM
orch.set_main_llm("custom-gpt4", tenant_id="acme")
```

**Streaming Execution**
```python
async for event in orch.stream(goal="Analyze user behavior"):
    if event["type"] == "plan":
        print(f"Plan: {len(event['steps'])} steps")
    elif event["type"] == "step":
        print(f"Step {event['step']['id']}: {event['output']}")
    elif event["type"] == "error":
        print(f"Error: {event['error']}")
    elif event["type"] == "done":
        print("Orchestration complete")
```

#### Configuration

```python
# LLM clients (comma-separated name=url pairs)
LLM_CLIENTS = "default=http://localhost:8000,planner=http://localhost:8001"
DEFAULT_MODEL = "gpt-4"

# Tool preferences (which LLM handles which tool)
LLM_TOOL_PREFERENCES = '{"calculator": "worker", "query": "planner"}'

# Agent roles (system prompts)
LLM_AGENT_ROLES = '{"analyst": "You are a data analyst...", "coder": "You write code..."}'

# Tool ACL (client -> allowed tools)
LLM_TOOL_ACL = '{"planner": ["query", "analyze"], "worker": ["calculator", "transform"]}'
```

---

### Session Management

**File:** `src/services/session.py`

#### Features

- **Chat Sessions**: Multi-turn conversation tracking
- **Message History**: Role-based messages (user/assistant/system/tool)
- **TTL Management**: Automatic expiration with configurable lifetime
- **Max Messages**: Sliding window with system message preservation
- **Metadata**: Extensible session metadata with deep merge
- **Token Tracking**: Best-effort token counters
- **Dual Backend**: Redis (distributed) or in-memory (process-local)

#### Models

```python
@dataclass
class ChatMessage:
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    ts: str = field(default_factory=lambda: utc_now().isoformat())
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Session:
    id: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    created_at: str
    updated_at: str
    expires_at: Optional[str] = None
    title: Optional[str] = None
    metadata: Dict[str, Any]
    messages: List[ChatMessage]
    tokens_in: int = 0
    tokens_out: int = 0
    turns: int = 0
    closed: bool = False
    max_messages: int = 500
```

#### Usage Examples

**Create Session**
```python
from src.services import get_session_service

sessions = get_session_service()

result = await sessions.create_session(
    user_id="user-123",
    tenant_id="acme",
    title="Customer Support Chat",
    metadata={"source": "web", "priority": "high"},
    ttl_seconds=86400,  # 24 hours
    system_prompt="You are a helpful customer support agent."
)

session_id = result.data["id"]
```

**Append Messages**
```python
# User message
await sessions.append_message(
    session_id=session_id,
    role="user",
    content="How do I reset my password?",
    tokens_incr=8
)

# Assistant response
await sessions.append_message(
    session_id=session_id,
    role="assistant",
    content="You can reset your password by...",
    tokens_out_incr=25,
    meta={"model": "gpt-4", "temperature": 0.7}
)
```

**Retrieve Session**
```python
result = await sessions.get_session(session_id)
if result.ok:
    session = result.data
    print(f"Session: {session['title']}")
    print(f"Messages: {len(session['messages'])}")
    print(f"Turns: {session['turns']}")
```

**List Sessions**
```python
result = await sessions.list_sessions(
    user_id="user-123",
    limit=10,
    offset=0
)

for session in result.data["items"]:
    print(f"{session['id']}: {session['title']}")
```

#### Configuration

```python
SESSION_TTL_SECONDS = 604800  # 7 days
MAX_MESSAGES_DEFAULT = 500
REDIS_URL = "redis://redis:6379/0"
REDIS_PREFIX = "cineca"
```

---

### Jobs Service

**File:** `src/services/jobs_service.py`

#### Features

- **Dual Storage**: PostgreSQL (authoritative) + Redis (cache/queue)
- **Idempotency**: Client-provided idempotency keys
- **Priority Queues**: Priority-based job ordering
- **Event Log**: Append-only event stream per job
- **Status Transitions**: Queued → Running → Completed/Failed/Cancelled
- **ETag Support**: List caching with ETags
- **Owner Scoping**: Job access control by owner

#### Models

```python
# PostgreSQL Models (db/postgres_control/models.py)
class Job(Base):
    id: UUID
    owner_sub: str
    tenant_id: str
    type: str
    payload_json: Dict
    status: str  # queued, running, completed, failed, cancelled
    result_json: Optional[Dict]
    idempotency_key: Optional[str]
    priority: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

class JobEvent(Base):
    id: int
    job_id: UUID
    seq_id: int  # Auto-incrementing per job
    event_type: str  # status, log, progress, error
    event_data: Dict
    ts: datetime
```

#### Usage Examples

**Create Job**
```python
from src.services.jobs_service import JobsService
from db.postgres_control import get_db

db = next(get_db())
jobs_svc = JobsService(db)

job, is_new = jobs_svc.create_job(
    owner_sub="user-123",
    tenant_id="acme",
    job_type="data_export",
    payload={"format": "csv", "table": "users"},
    idempotency_key="export-users-20251024",  # Optional
    priority=5
)

if is_new:
    print(f"Created job {job.id}")
else:
    print(f"Idempotent replay: {job.id}")
```

**List Jobs**
```python
jobs, total, has_more = jobs_svc.list_jobs(
    owner_sub="user-123",
    tenant_id="acme",
    status=["running", "queued"],
    limit=25,
    offset=0
)

for job in jobs:
    print(f"{job.id}: {job.status} ({job.type})")
```

**Cancel Job**
```python
job, first_cancel = jobs_svc.cancel_job(
    job_id=job.id,
    owner_sub="user-123"
)

if first_cancel:
    print("Job cancelled")
else:
    print("Job already terminal")
```

**Event Stream**
```python
events = jobs_svc.get_events(
    job_id=job.id,
    after_seq_id=0,  # Get all events
    limit=100
)

for event in events:
    print(f"[{event.seq_id}] {event.event_type}: {event.event_data}")
```

#### Configuration

```python
# PostgreSQL
DATABASE_URL = "postgresql://user:pass@localhost/cineca"

# Redis
REDIS_URL = "redis://redis:6379/0"
```

---

### ETL Service

**File:** `src/services/etl.py`

#### Features

- **CSV Import**: Nodes and relationships from CSV files
- **JSONL Import**: Bulk import from JSONL format
- **Snapshot Export**: Full graph export to JSON
- **CSV Export**: Nodes/relationships to CSV
- **Graph Validation**: Integrity checks and statistics
- **Deduplication**: Remove duplicate nodes by property
- **Batch Processing**: Configurable batch size (default: 500)
- **Idempotent Upserts**: MERGE semantics for imports

#### Usage Examples

**Import Nodes from CSV**
```python
from src.services import get_etl_service

etl = get_etl_service()

result = await etl.import_nodes_csv(
    csv_path="/data/users.csv",
    label="User",
    id_column="user_id",
    property_mapping={
        "name": "full_name",
        "email": "email_address",
        "age": "user_age"
    },
    batch_size=500
)

print(f"Imported {result.data['nodes_created']} users")
```

**Import Relationships from CSV**
```python
result = await etl.import_relationships_csv(
    csv_path="/data/friendships.csv",
    rel_type="FRIENDS_WITH",
    source_id_column="user_a",
    target_id_column="user_b",
    source_label="User",
    target_label="User",
    property_mapping={"since": "friendship_date"},
    batch_size=500
)

print(f"Created {result.data['relationships_created']} friendships")
```

**Snapshot Export**
```python
result = await etl.snapshot_export(
    output_path="/backups/graph-snapshot.json",
    compress=True  # Optional gzip compression
)

print(f"Exported {result.data['nodes']} nodes, {result.data['relationships']} rels")
```

**Graph Validation**
```python
result = await etl.validate_graph()

stats = result.data
print(f"Nodes: {stats['node_count']}")
print(f"Relationships: {stats['relationship_count']}")
print(f"Labels: {stats['labels']}")
print(f"Relationship types: {stats['rel_types']}")
print(f"Orphaned nodes: {stats['orphaned_nodes']}")
```

#### Configuration

```python
ETL_BATCH_SIZE = 500
ETL_TIMEOUT_SECONDS = 300
```

---

### Archive Service

**File:** `src/services/archive.py`

#### Features

- **Graph Snapshots**: Export Memgraph to gzip-compressed JSON
- **Tar Archives**: Create tar.gz from arbitrary paths
- **Rotation**: Keep N most recent backups
- **Restore**: Rebuild graph from snapshot JSON
- **Batch MERGE**: Idempotent upserts during restore
- **Configurable Compression**: Enable/disable gzip

#### Usage Examples

**Create Snapshot**
```python
from src.services import get_archive_service

archive = get_archive_service()

result = await archive.snapshot_graph(
    output_name="backup-20251024",
    compress=True
)

snapshot_path = result.data["snapshot_path"]
print(f"Snapshot saved to {snapshot_path}")
```

**Restore from Snapshot**
```python
result = await archive.restore_graph(
    snapshot_path="/backups/backup-20251024.json.gz",
    clear_first=True,  # Clear existing graph
    batch_size=500
)

print(f"Restored {result.data['nodes']} nodes, {result.data['relationships']} rels")
```

**List Backups**
```python
backups = await archive.list_backups()

for backup in backups.data:
    print(f"{backup['name']}: {backup['size_mb']} MB ({backup['created_at']})")
```

**Rotate Backups**
```python
await archive.rotate(keep_count=7)  # Keep 7 most recent
```

#### Configuration

```python
ARCHIVE_BASE_DIR = "/var/backups/cineca"
ARCHIVE_COMPRESS = True
ARCHIVE_BATCH_SIZE = 500
```

---

### Health Service

**File:** `src/services/health.py`

#### Features

- **Dependency Probes**: Redis and Memgraph health checks
- **Latency Metrics**: Record probe response times
- **Caching**: 5-second TTL to avoid probe storms
- **Graceful Degradation**: Configurable fallback on unavailable deps
- **Lazy Initialization**: Adapters loaded on first check

#### Usage Examples

**Liveness Check (Quick)**
```python
from src.services import get_health_service

health = get_health_service()

result = await health.liveness()
# Returns: {"status": "ok"} (always succeeds if service responsive)
```

**Readiness Check (Dependencies)**
```python
result = await health.readiness()

if result.ok:
    print("All dependencies healthy")
else:
    print(f"Degraded: {result.error}")

# Example response:
# {
#   "status": "ok",
#   "checks": {
#     "redis": {"status": "ok", "latency_ms": 2.5},
#     "memgraph": {"status": "ok", "latency_ms": 5.1}
#   }
# }
```

**Detailed Check**
```python
result = await health.check()

checks = result.data["checks"]
for dep_name, check in checks.items():
    print(f"{dep_name}: {check['status']} ({check.get('latency_ms')}ms)")
```

#### Configuration

```python
HEALTH_ALLOW_REDIS_HEALTH_FALLBACK = True
HEALTH_ALLOW_MG_HEALTH_FALLBACK = True
HEALTH_CACHE_TTL_SECONDS = 5
```

---

### LLM Registry

**File:** `src/services/llm_registry.py`

#### Features

- **Manifest Management**: YAML-based built-in LLM definitions
- **Staging**: Remote manifest updates cached in Redis
- **Activation**: Promote staged manifest to active
- **Rollback**: Revert to previous manifest version
- **Audit Trail**: Memgraph records of activations
- **Auto-Start**: Automatic local model process spawning
- **Alias Resolution**: Map friendly names to versioned models

#### Models

```python
@dataclass
class BuiltinEntry:
    id: str
    version: str
    display_name: str
    backend: str  # "llamacpp", "ollama", "vllm"
    artifact: Optional[str] = None  # Local model path
    endpoint: Optional[str] = None  # API endpoint
    recommended_for: List[str] = None  # ["cpu", "gpu", "dev", "prod"]
    license: Optional[str] = None
    raw: Dict[str, Any] = None
```

#### Usage Examples

**Load Local Manifest**
```python
from src.services.llm_registry import get_registry

registry = get_registry()

manifest = registry.load_local_manifest()
print(f"Version: {manifest['version']}")
print(f"Builtins: {len(manifest.get('builtins', []))}")
```

**Stage Remote Manifest**
```python
manifest = registry.stage_remote_manifest(
    url="https://registry.cineca.eu/manifests/v2.yaml"
)

print(f"Staged manifest version {manifest['version']}")
```

**Activate Staged Manifest**
```python
active = registry.activate_staged()
print(f"Activated version {active['version']}")
# Auto-start processes if configured
```

**List Built-ins**
```python
builtins = registry.list_builtins()

for b in builtins:
    print(f"{b['id']} ({b['version']}): {b['display_name']}")
    print(f"  Backend: {b['backend']}")
    print(f"  Recommended for: {b.get('recommended_for', [])}")
```

**Resolve Alias**
```python
model = registry.resolve_alias("fast-chat")
# Returns model definition if alias exists
```

#### Manifest Format

```yaml
version: "2.0"
builtins:
  - id: "phi-3-mini"
    version: "v1"
    display_name: "Phi-3 Mini (4K context)"
    backend: "llamacpp"
    artifact: "/models/phi-3-mini-4k-instruct.gguf"
    recommended_for: ["cpu", "dev"]
    license: "MIT"
    estimated_footprint_gb: 2.5

  - id: "llama-3-8b"
    version: "v1"
    display_name: "Llama 3 8B"
    backend: "vllm"
    endpoint: "http://localhost:8000"
    recommended_for: ["gpu", "prod"]
    license: "Llama 3 Community License"

aliases:
  fast-chat: "phi-3-mini@v1"
  production: "llama-3-8b@v1"
```

#### Configuration

```python
BUILTIN_MANIFEST_PATH = "ops/builtins/manifest.yaml"
BUILTIN_MANIFEST_AUTO_CHECK = False
BUILTIN_MANIFEST_URL = "https://registry.cineca.eu/manifests/latest.yaml"
BUILTIN_AUTO_START = False
BUILTIN_AUTO_START_MAX_CONCURRENT = 3
BUILTIN_AUTO_START_MIN_FREE_GB = 2.0
```

---

### Process Service

**File:** `src/services/process_service.py`

#### Features

- **Process Tracking**: Runtime state in Redis + persistent audit in PostgreSQL
- **Lifecycle Events**: START, STOP, EXIT with timestamps
- **Idempotent Stop**: Lock-based deduplication
- **Manifest History**: Activation audit trail
- **Pagination**: Cursor-based pagination for lists
- **Staleness Detection**: Mark processes without recent heartbeat

#### Usage Examples

**List Processes**
```python
from src.services.process_service import list_processes
from db.postgres_control import get_db

db = next(get_db())

processes, next_cursor = list_processes(
    db=db,
    limit=50,
    artifact="phi-3-mini",
    status="running"
)

for proc in processes:
    print(f"{proc['id']}: {proc['status']} (PID {proc['pid']})")
```

**Stop Process**
```python
from src.services.process_service import stop_process

success = stop_process(
    db=db,
    pid=12345,
    actor="admin@cineca.eu"
)

if success:
    print("Process stopped")
```

**Get Process History**
```python
from src.services.process_service import get_process_history

events, next_cursor = get_process_history(
    db=db,
    process_id="proc-abc-123",
    limit=100
)

for event in events:
    print(f"[{event.ts}] {event.event}: {event.reason}")
```

#### Configuration

```python
PROCESS_TTL_SECONDS = 120  # Runtime state TTL
STOP_LOCK_TTL_SECONDS = 30  # Stop operation lock duration
```

---

### Status Service

**File:** `src/services/status.py`

#### Features

- **Aggregate Status**: Combine health checks, metrics, build info
- **Metadata**: App name, version, environment
- **Health Integration**: Leverage HealthService for dependency checks
- **Metrics Snapshot**: Optional ServiceMetrics integration

#### Usage Examples

**Get Full Status**
```python
from src.services import get_status_service

status = get_status_service()

result = await status.get_status()

data = result.data
print(f"App: {data['app']['name']} v{data['app']['version']}")
print(f"Environment: {data['app']['environment']}")
print(f"Health: {data['services']['health']['ok']}")
print(f"Dependencies: {data['health']['checks']}")
```

#### Configuration

```python
APP_NAME = "Cineca Agentic Platform"
APP_VERSION = "1.0.0"
APP_ENV = "production"  # or "dev", "staging"
```

---

### Service Metrics

**File:** `src/services/service_metrics.py`

#### Features

- **Prometheus Integration**: Counters, gauges, histograms
- **API Metrics**: Request count/duration by route/method/status
- **Dependency Metrics**: Health and latency gauges
- **Job Metrics**: Background job duration by status
- **Context Managers**: `time_request()`, `time_job()`
- **Build Info**: Version metadata gauge

#### Metrics Exposed

```python
# API requests
cineca_api_requests_total{route, method, status_class}
cineca_api_request_duration_seconds{route, method}

# Service events
cineca_service_events_total{service, event}

# Background jobs
cineca_job_duration_seconds{job, status}

# Dependencies
cineca_dependency_up{name}
cineca_dependency_latency_seconds{name}

# Service health
cineca_service_up{service}

# Build info
cineca_build_info{version}
```

#### Usage Examples

**Record API Request**
```python
from src.services import get_service_metrics

metrics = get_service_metrics()

metrics.record_request(
    route="/api/tools/invoke",
    method="POST",
    status_code=200,
    duration_seconds=0.125
)
```

**Context Manager**
```python
with metrics.time_request(route="/api/agents/run", method="POST") as done:
    # Handler logic
    result = execute_agent_run()
    done(status_code=200)
```

**Background Job Timing**
```python
with metrics.time_job(job="data_export", status_on_success="completed"):
    export_data_to_csv()
```

**Update from Health**
```python
health_payload = await health.readiness()
metrics.update_from_health(health_payload.data)
```

#### Configuration

```python
APP_VERSION = "1.0.0"
PROMETHEUS_ENABLED = True
```

---

### Tenant Management

**File:** `src/services/tenants.py`

#### Features

- **CRUD Operations**: Create, read, update, delete tenants
- **Idempotent Creation**: Same config returns existing tenant
- **Metadata Management**: Deep merge for metadata updates
- **Dependency Checks**: Block deletion if tenant has resources
- **In-Memory Store**: Simple dict-based storage (prototype)

#### Models

```python
@dataclass
class Tenant:
    id: str
    name: str
    admin_email: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str
    updated_at: str
```

#### Usage Examples

**Create Tenant**
```python
from src.services.tenants import create_tenant

tenant = create_tenant(
    name="Acme Corporation",
    admin_email="admin@acme.com",
    metadata={"industry": "tech", "plan": "enterprise"}
)

print(f"Created tenant: {tenant['id']}")
```

**Update Tenant**
```python
from src.services.tenants import update_tenant

updated = update_tenant(
    id="tenant-abc123",
    name="Acme Corp (Updated)",
    metadata={"plan": "premium"}  # Merged with existing
)
```

**Delete Tenant**
```python
from src.services.tenants import delete_tenant

try:
    delete_tenant(id="tenant-abc123", check_dependencies=True)
    print("Tenant deleted")
except ValueError as e:
    print(f"Cannot delete: {e}")
```

---

### Invocation Store

**File:** `src/services/invocation_store.py`

#### Features

- **POST/GET Parity**: Persist tool invocation results for replay
- **Owner Scoping**: Anti-enumeration via `owner_sub`
- **Dual Backend**: Redis JSON (primary) + in-memory (fallback)
- **TTL**: Configurable retention period
- **Primary Key**: `(tool_name, event_id)`

#### Usage Examples

**Save Invocation**
```python
from src.services.invocation_store import save_invocation

save_invocation(
    name="calculator",
    eid="evt-123",
    owner_sub="user-456",
    body={"result": 42, "operation": "add"},
    ttl_s=86400  # 24 hours
)
```

**Load Invocation**
```python
from src.services.invocation_store import load_invocation

body = load_invocation(name="calculator", eid="evt-123")
if body:
    print(f"Result: {body['result']}")
```

#### Configuration

```python
RETENTION_DAYS = 7  # Invocation TTL
REDIS_URL = "redis://redis:6379/0"
```

---

### Job Store

**File:** `src/services/job_store.py`

#### Features

- **In-Memory Store**: Simple dict-based job metadata
- **SSE Event Buffering**: Ring buffer of recent events per job
- **Retention Cleaner**: Background thread for expiration
- **Test-Friendly**: Singleton for shared state across test instances

**⚠️ Production Warning**: In-memory only - NOT suitable for multi-process/multi-replica deployments

#### Usage Examples

**Create Job Entry**
```python
from src.services.job_store import create_job_entry

job_id = create_job_entry(
    subj="user-123",
    job_type="data_export",
    payload={"format": "csv"},
    tenant="acme",
    retention_days=7
)

print(f"Job created: {job_id}")
```

**Record Event**
```python
from src.services.job_store import record_event

record_event(
    job_id=job_id,
    ev_id=1,
    ev_type="status",
    payload='{"status": "running"}'
)
```

**Get Events Since**
```python
from src.services.job_store import get_events_since

events = get_events_since(job_id=job_id, last_seen=0)
for event in events:
    print(f"[{event['id']}] {event['event']}: {event['data']}")
```

---

## Integration Patterns

### 1. Multi-Agent Orchestration with Sessions

```python
from src.services import get_orchestrator, get_session_service

orch = get_orchestrator()
sessions = get_session_service()

# Create session
session_result = await sessions.create_session(
    user_id="user-123",
    tenant_id="acme",
    system_prompt="You are a helpful AI assistant."
)
session_id = session_result.data["id"]

# User input
await sessions.append_message(
    session_id=session_id,
    role="user",
    content="Find all users named John"
)

# Orchestrate with context
result = await orch.run(
    goal="Find all users named John",
    user_id="user-123",
    session_id=session_id,
    context_vars={"session_id": session_id}
)

# Store assistant response
await sessions.append_message(
    session_id=session_id,
    role="assistant",
    content=result.data["outputs"][-1]["output"]["text"],
    tokens_out_incr=100
)
```

### 2. Background Job Processing with Status Updates

```python
from src.services.jobs_service import JobsService
from src.services.invocation_store import save_invocation

jobs_svc = JobsService(db)

# Create job
job, _ = jobs_svc.create_job(
    owner_sub="user-123",
    tenant_id="acme",
    job_type="data_export",
    payload={"format": "csv", "table": "users"},
    idempotency_key=f"export-{uuid.uuid4()}"
)

# Transition to running
jobs_svc.transition_status(
    job_id=job.id,
    from_status="queued",
    to_status="running"
)

# Append progress events
jobs_svc.append_event(
    job_id=job.id,
    event_type="progress",
    event_data={"percent": 50, "message": "Processing rows..."}
)

# Complete job
jobs_svc.transition_status(
    job_id=job.id,
    from_status="running",
    to_status="completed"
)

# Save result for GET parity
save_invocation(
    name=f"job:{job.type}",
    eid=str(job.id),
    owner_sub=job.owner_sub,
    body={"result": "export_complete.csv"},
    ttl_s=604800  # 7 days
)
```

### 3. Graph ETL with Archive Snapshots

```python
from src.services import get_etl_service, get_archive_service

etl = get_etl_service()
archive = get_archive_service()

# Import data
await etl.import_nodes_csv(
    csv_path="/data/users.csv",
    label="User",
    id_column="id",
    property_mapping={"name": "full_name"}
)

await etl.import_relationships_csv(
    csv_path="/data/follows.csv",
    rel_type="FOLLOWS",
    source_id_column="follower",
    target_id_column="followee",
    source_label="User",
    target_label="User"
)

# Validate import
stats = await etl.validate_graph()
print(f"Imported {stats.data['node_count']} nodes")

# Create snapshot
snapshot = await archive.snapshot_graph(
    output_name="after-import",
    compress=True
)

# Rotate old backups
await archive.rotate(keep_count=5)
```

### 4. Health-Driven Metrics

```python
from src.services import get_health_service, get_service_metrics

health = get_health_service()
metrics = get_service_metrics()

# Periodic health check
health_result = await health.readiness()

# Update Prometheus gauges
metrics.update_from_health(health_result.data)

# Manual dependency marking
if not health_result.ok:
    metrics.mark_dependency("memgraph", up=False)
    metrics.mark_event("health", "degraded")
```

### 5. LLM Registry with Orchestrator Integration

```python
from src.services.llm_registry import get_registry
from src.services import get_orchestrator

registry = get_registry()
orch = get_orchestrator()

# Stage and activate manifest
manifest = registry.stage_remote_manifest(
    url="https://registry.cineca.eu/manifests/latest.yaml"
)
active = registry.activate_staged()

# Builtins auto-registered in orchestrator
builtins = registry.list_builtins()
for b in builtins:
    print(f"Registered: llm:{b['id']}")

# Use built-in model
result = await orch.run(
    goal="Summarize this text",
    params={"manager": "builtin:phi-3-mini"}
)
```

---

## Configuration Reference

### Orchestrator

```python
LLM_CLIENTS = "default=http://localhost:8000,planner=http://localhost:8001"
DEFAULT_MODEL = "gpt-4"
OPENAI_API_KEY = "sk-..."
LLM_TOOL_PREFERENCES = '{"calculator": "worker"}'
LLM_AGENT_ROLES = '{"analyst": "You are a data analyst..."}'
LLM_TOOL_ACL = '{"planner": ["query", "analyze"]}'
```

### Session Service

```python
SESSION_TTL_SECONDS = 604800  # 7 days
MAX_MESSAGES_DEFAULT = 500
REDIS_URL = "redis://redis:6379/0"
REDIS_PREFIX = "cineca"
CACHE_TTL_SECONDS = 600
```

### Jobs Service

```python
DATABASE_URL = "postgresql://user:pass@localhost/cineca"
REDIS_URL = "redis://redis:6379/0"
```

### ETL Service

```python
ETL_BATCH_SIZE = 500
ETL_TIMEOUT_SECONDS = 300
MEMGRAPH_URL = "bolt://memgraph:7687"
```

### Archive Service

```python
ARCHIVE_BASE_DIR = "/var/backups/cineca"
ARCHIVE_COMPRESS = True
ARCHIVE_BATCH_SIZE = 500
```

### Health Service

```python
HEALTH_ALLOW_REDIS_HEALTH_FALLBACK = True
HEALTH_ALLOW_MG_HEALTH_FALLBACK = True
HEALTH_CACHE_TTL_SECONDS = 5
```

### LLM Registry

```python
BUILTIN_MANIFEST_PATH = "ops/builtins/manifest.yaml"
BUILTIN_MANIFEST_AUTO_CHECK = False
BUILTIN_MANIFEST_URL = "https://registry.cineca.eu/manifests/latest.yaml"
BUILTIN_AUTO_START = False
BUILTIN_AUTO_START_MAX_CONCURRENT = 3
BUILTIN_AUTO_START_MIN_FREE_GB = 2.0
BUILTIN_AUTO_START_WHITELIST = "phi-3-mini,llama-3-8b"
HAS_GPU = False
APP_ENV = "dev"  # or "prod"
```

### Status Service

```python
APP_NAME = "Cineca Agentic Platform"
APP_VERSION = "1.0.0"
APP_ENV = "production"
```

### Service Metrics

```python
APP_VERSION = "1.0.0"
PROMETHEUS_ENABLED = True
```

### Invocation Store

```python
RETENTION_DAYS = 7
REDIS_URL = "redis://redis:6379/0"
```

### Job Store

```python
RETENTION_DAYS = 7
EVENT_BUFFER_MAX = 100
```

---

## Best Practices

### 1. Service Lifecycle Management
- Always call `start()` before using services
- Use `liveness()` for quick health checks
- Use `readiness()` for dependency validation
- Call `stop()` during graceful shutdown

### 2. Error Handling
- Check `ServiceResult.ok` before accessing `.data`
- Use `.error` and `.code` for structured error handling
- Wrap service calls in try/except for `ServiceError`

### 3. Async/Await Discipline
- All service methods are async - always `await`
- Use `asyncio.gather()` for parallel service calls
- Don't block event loop with sync operations

### 4. Resource Cleanup
- Close database sessions after use
- Clear Redis keys with appropriate TTLs
- Rotate archived backups regularly

### 5. Monitoring & Observability
- Instrument all critical paths with metrics
- Use structured logging for debugging
- Monitor dependency health probes
- Track job completion rates

---

## Troubleshooting

### Service Not Loading

**Problem:** `AttributeError` when importing service

**Solutions:**
- Check lazy import in `src/services/__init__.py`
- Verify service module exists and has getter function
- Ensure no circular import issues

### Redis Connection Failures

**Problem:** Services degrade to in-memory mode

**Solutions:**
- Check `REDIS_URL` configuration
- Verify Redis server is running
- Check network connectivity
- Review Redis logs for errors

### PostgreSQL Connection Issues

**Problem:** Jobs service fails to initialize

**Solutions:**
- Verify `DATABASE_URL` configuration
- Check PostgreSQL server status
- Run migrations: `alembic upgrade head`
- Verify database exists and user has permissions

### Memgraph Query Failures

**Problem:** ETL/Archive operations fail

**Solutions:**
- Check Memgraph connectivity
- Verify Cypher syntax
- Check transaction limits
- Review Memgraph logs

### LLM Registry Manifest Issues

**Problem:** Built-ins not registering

**Solutions:**
- Validate manifest YAML syntax
- Check file path in `BUILTIN_MANIFEST_PATH`
- Verify Redis availability for staging
- Check `APP_ENV` and `HAS_GPU` filters

---

## Appendix

### Service Module File Sizes

```
src/services/
├── __init__.py           (bootstrap, 5KB)
├── orchestrator.py       (orchestration, 45KB)
├── session.py            (sessions, 18KB)
├── jobs_service.py       (jobs, 12KB)
├── etl.py                (ETL, 15KB)
├── archive.py            (archival, 10KB)
├── health.py             (health checks, 8KB)
├── llm_registry.py       (LLM manifest, 22KB)
├── process_service.py    (process mgmt, 18KB)
├── status.py             (status, 6KB)
├── service_metrics.py    (metrics, 10KB)
├── tenants.py            (tenancy, 6KB)
├── invocation_store.py   (invocations, 4KB)
└── job_store.py          (job store, 4KB)

Total: 14 files, ~183KB
```

### Related Documentation

- [MCP Tools Reference](./MCP_TOOLS_REFERENCE.md) - Complete MCP tool catalog
- [Security Reference](./SECURITY_REFERENCE.md) - Security components
- [API Best Practices](./API_BEST_PRACTICES.md) - REST API design
- [Deployment Checklist](./DEPLOYMENT_CHECKLIST.md) - Production readiness

---

**Document Version:** 1.0  
**Last Updated:** 2025-10-24  
**Maintainer:** Cineca Agentic Platform Team
