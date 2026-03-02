# Jobs Framework Reference

This document provides comprehensive reference documentation for the Jobs framework implemented in the Cineca Agentic Platform. The Jobs framework provides asynchronous job management with multiple storage backends, Server-Sent Events (SSE) for real-time updates, idempotency guarantees, and comprehensive monitoring.

## Overview

The Jobs framework is a comprehensive asynchronous job management system designed for long-running operations in the Cineca Agentic Platform. It provides:

- **Storage Abstraction**: Clean separation between domain models and storage backends
- **Multiple Backends**: In-memory (development/testing) and Redis (production) implementations
- **Idempotency**: Duplicate request prevention with configurable TTL
- **Real-time Updates**: Server-Sent Events (SSE) with Last-Event-ID resume support
- **Multi-tenancy**: Tenant-scoped job isolation
- **Comprehensive Monitoring**: Prometheus metrics and structured logging
- **RBAC Integration**: Owner-based access control

## Architecture

### Core Components

The Jobs framework consists of several key components:

- **Domain Models** (`models.py`): Storage-agnostic business entities
- **Storage Interfaces** (`interfaces.py`): Abstract contracts for persistence
- **Storage Implementations**: Memory and Redis backends
- **Factory Pattern** (`factory.py`): Backend selection and dependency injection
- **Metrics** (`metrics.py`): Prometheus instrumentation

### Storage Backends

The framework supports two storage backends configured via `JOB_STORE_BACKEND`:

#### Memory Backend (`memory`)
- **Use Case**: Development, testing, single-instance deployments
- **Features**: No persistence, no TTL, fast operations
- **Limitations**: Data lost on restart, no multi-instance support

#### Redis Backend (`redis`)
- **Use Case**: Production deployments with multiple instances
- **Features**: Persistence, TTL-based expiry, multi-instance support
- **Requirements**: Redis server with TTL support

## Domain Models

### JobDocument

The core job entity representing a single asynchronous operation.

```python
class JobDocument(BaseModel):
    id: str                    # Unique job identifier (UUID)
    owner: str                 # Owner subject (from JWT sub claim)
    tenant_id: str             # Tenant identifier for multi-tenancy
    type: str                  # Job type (e.g., 'demo', 'training')
    status: JobStatus          # Current job status
    payload: dict[str, Any]    # Job input parameters
    result: dict[str, Any]     # Job output (set on completion)
    created_at: datetime       # Job creation timestamp (UTC)
    updated_at: datetime       # Last status change timestamp (UTC)
    error: str                 # Error message if status=failed
```

### JobStatus Enum

Represents the lifecycle states of a job:

```python
class JobStatus(str, Enum):
    QUEUED = "queued"      # Job created, waiting to start
    RUNNING = "running"    # Job actively executing
    FINISHED = "finished"  # Job completed successfully
    FAILED = "failed"      # Job failed with error
    CANCELLED = "cancelled" # Job cancelled by user/system
```

### SSEEvent

Represents Server-Sent Events for real-time job status updates.

```python
class SSEEvent(BaseModel):
    event_id: int           # Monotonic event sequence number
    event_type: str         # Event type: 'status', 'end', 'error'
    data: dict[str, Any]    # Event payload (job_id, status, etc.)
    timestamp: datetime     # Event emission time (UTC)
```

## Storage Interfaces

### JobStore Interface

Abstract interface for job document persistence.

```python
class JobStore(ABC):
    async def create(self, job: JobDocument, ttl_seconds: int) -> None:
        """Persist a new job with automatic expiry."""

    async def get(self, job_id: str) -> JobDocument | None:
        """Retrieve job by ID."""

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: dict | None = None,
        error: str | None = None,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Atomically update job status and optional result/error."""

    async def list_by_owner(
        self,
        owner: str,
        status: JobStatus | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[list[JobDocument], int]:
        """List jobs for a specific owner, newest first."""

    async def list_all(
        self,
        status: JobStatus | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[list[JobDocument], int]:
        """List all jobs (admin view), newest first."""

    async def delete(self, job_id: str) -> bool:
        """Delete job and all associated indices."""
```

### IdempotencyStore Interface

Manages idempotency keys to prevent duplicate job creation.

```python
class IdempotencyStore(ABC):
    async def get_job_id(self, key: str) -> str | None:
        """Check if idempotency key exists and return associated job_id."""

    async def store(self, key: str, job_id: str, ttl_seconds: int) -> None:
        """Store idempotency key pointing to job_id with expiry."""
```

### EventStore Interface

Manages Server-Sent Events in ring buffers for resume support.

```python
class EventStore(ABC):
    async def append(
        self,
        job_id: str,
        event: SSEEvent,
        ring_size: int,
    ) -> None:
        """Append event to job's ring buffer, capping at ring_size."""

    async def get_next_event_id(self, job_id: str) -> int:
        """Get next monotonic event ID for this job."""

    async def replay_from(
        self,
        job_id: str,
        last_event_id: int,
    ) -> list[SSEEvent]:
        """Retrieve events with event_id > last_event_id."""

    async def get_all_events(self, job_id: str) -> list[SSEEvent]:
        """Get all buffered events for a job (for debugging/testing)."""
```

## Storage Implementations

### MemoryJobStore

In-memory implementation using Python dictionaries. Wraps the existing global `_JOBS` dictionary for backward compatibility.

**Key Features:**
- No persistence (data lost on restart)
- No TTL enforcement
- Fast operations for testing
- Maintains existing global state

**Storage Format:**
```python
_JOBS[job_id] = {
    "id": job.id,
    "owner_sub": job.owner,
    "metadata": {"tenant": job.tenant_id},
    "type": job.type,
    "status": job.status.value,
    "payload": job.payload,
    "result": job.result,
    "created_at": job.created_at.isoformat(),
    "updated_at": job.updated_at.isoformat(),
    "error": job.error,
}
```

### MemoryIdempotencyStore

In-memory idempotency key storage using a global dictionary.

**Storage Format:**
```python
_IDEMPOTENCY_KEYS[key] = job_id
```

### MemoryEventStore

In-memory SSE event storage with configurable ring buffer size.

**Storage Format:**
```python
_EVENTS[job_id] = [SSEEvent, ...]  # Ring buffer, max ring_size
_EVENT_SEQ[job_id] = next_event_id  # Monotonic sequence counter
```

## Factory Pattern

### Backend Selection

The `get_stores()` factory function selects appropriate implementations based on configuration:

```python
def get_stores() -> tuple[JobStore, IdempotencyStore, EventStore]:
    backend = settings.JOB_STORE_BACKEND.lower()

    if backend == "memory":
        return (
            MemoryJobStore(),
            MemoryIdempotencyStore(),
            MemoryEventStore(ring_size=settings.SSE_RING_SIZE),
        )

    elif backend == "redis":
        return (
            RedisJobStore(),
            RedisIdempotencyStore(),
            RedisEventStore(ring_size=settings.SSE_RING_SIZE),
        )
```

### Configuration

**Environment Variables:**
- `JOB_STORE_BACKEND`: `"memory"` or `"redis"` (default: `"memory"`)
- `JOB_TTL_DAYS`: Job expiry in days (default: 10)
- `SSE_RING_SIZE`: SSE event ring buffer size (default: 100)

## Idempotency System

### Key Generation

Idempotency keys are generated deterministically from request context:

```python
def create_idempotency_key(
    owner: str,
    tenant: str,
    job_type: str,
    payload: dict,
    idempotency_key: str | None = None,
) -> str:
    # Format: idem:{owner}:{tenant}:{type}:{payload_hash}:{key_suffix}
    payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()[:16]
    key_suffix = idempotency_key or payload_hash
    return f"idem:{owner}:{tenant}:{job_type}:{payload_hash}:{key_suffix}"
```

### Duplicate Prevention

When creating jobs, the system checks for existing idempotency keys:

1. Generate key from request context
2. Check if key exists in IdempotencyStore
3. If exists, return existing job_id (HTTP 200)
4. If not exists, create new job and store key (HTTP 201)

## Server-Sent Events (SSE)

### Event Types

- **`status`**: Job status changes (queued → running → finished/failed/cancelled)
- **`end`**: Terminal event indicating job completion
- **`error`**: Error events during job execution

### Event Format

Events follow the SSE wire protocol:

```
id: 42
event: status
data: {"job_id": "123", "status": "running", "timestamp": "2025-01-01T12:00:00Z"}
```

### Ring Buffer Management

Events are stored in ring buffers to prevent unbounded growth:

- **Ring Size**: Configurable via `SSE_RING_SIZE` (default: 100)
- **Rotation**: Oldest events are discarded when buffer is full
- **Resume Support**: `Last-Event-ID` header allows clients to resume from specific event

### Resume Mechanism

Clients can resume SSE connections using the `Last-Event-ID` header:

1. Client connects with `Last-Event-ID: 42`
2. Server replays events with `event_id > 42`
3. If gap exists (events rotated out), server sends gap comment
4. Server continues with live events

## Metrics and Monitoring

### Prometheus Metrics

The framework provides comprehensive Prometheus instrumentation:

#### Job Operation Metrics
```python
job_create_total = Counter("job_create_total", "Total job creations", ["backend", "status"])
job_get_total = Counter("job_get_total", "Total job retrievals", ["backend", "status"])
job_list_total = Counter("job_list_total", "Total job list queries", ["backend", "scope"])
job_cancel_total = Counter("job_cancel_total", "Total job cancellations", ["backend", "first_time"])
```

#### Latency Histograms
```python
job_create_duration_seconds = Histogram("job_create_duration_seconds", "Job creation latency", ["backend"])
job_get_duration_seconds = Histogram("job_get_duration_seconds", "Job retrieval latency", ["backend"])
job_list_duration_seconds = Histogram("job_list_duration_seconds", "Job list query latency", ["backend", "scope"])
```

#### SSE Metrics
```python
sse_connections_active = Gauge("sse_connections_active", "Active SSE connections", ["backend"])
sse_resume_hits_total = Counter("sse_resume_hits_total", "Successful Last-Event-ID resumes", ["backend"])
sse_gap_events_total = Counter("sse_gap_events_total", "SSE ring buffer gaps", ["backend"])
sse_heartbeat_total = Counter("sse_heartbeat_total", "SSE heartbeats sent", ["backend"])
sse_terminal_events_total = Counter("sse_terminal_events_total", "SSE terminal end events", ["backend", "status"])
```

#### Backend Health
```python
job_backend_info = Info("job_backend", "Current job storage backend")
redis_operations_total = Counter("redis_operations_total", "Total Redis operations", ["operation", "status"])
redis_connection_errors_total = Counter("redis_connection_errors_total", "Redis connection errors", ["error_type"])
```

### Metric Decorators

Operations are automatically instrumented using decorators:

```python
@track_job_create(backend="redis")
async def create_job(job: JobDocument) -> None:
    # Implementation
```

### SSE Connection Tracking

SSE connections are tracked with context managers:

```python
with track_sse_connection(backend="redis"):
    # SSE connection handling
```

## Multi-tenancy and Security

### Tenant Isolation

All jobs are scoped to tenants:

- **Storage Keys**: Jobs are stored with tenant prefixes
- **Access Control**: Users can only access jobs in their tenant
- **RBAC Integration**: Owner-based permissions within tenants

### Owner-based Access

Jobs are owned by the creating user (from JWT `sub` claim):

- **List Operations**: `list_by_owner()` filters by owner
- **Admin Access**: `list_all()` provides tenant-wide admin view
- **Update Permissions**: Only owners can update their jobs

## Error Handling

### Storage Errors

Custom exceptions for storage layer issues:

```python
class StorageError(Exception):
    """Base exception for storage layer errors."""

class JobNotFoundError(StorageError):
    """Raised when job doesn't exist or has expired."""

class IdempotencyConflictError(StorageError):
    """Raised when idempotency key already exists with different job_id."""
```

### Graceful Degradation

The factory pattern provides fallback to memory storage if Redis is unavailable:

```python
try:
    # Try Redis
    from db.redis_cache.job_store import RedisJobStore
    return RedisJobStore()
except ImportError:
    # Fallback to memory
    return MemoryJobStore()
```

## Configuration

### Environment Variables

```bash
# Storage backend selection
JOB_STORE_BACKEND=memory  # or "redis"

# Job lifecycle
JOB_TTL_DAYS=10          # Job expiry in days

# SSE configuration
SSE_RING_SIZE=100        # Event ring buffer size

# Redis connection (if using redis backend)
REDIS_URL=redis://localhost:6379/0
```

### Settings Integration

The framework integrates with the platform's settings system:

```python
from src.config import settings

backend = settings.JOB_STORE_BACKEND.lower()
ttl_days = settings.JOB_TTL_DAYS
ring_size = settings.SSE_RING_SIZE
```

## Usage Examples

### Creating Jobs

```python
from src.jobs.factory import get_stores
from src.jobs.models import JobDocument, JobStatus

job_store, idem_store, event_store = get_stores()

# Create a new job
job = JobDocument(
    id=str(uuid.uuid4()),
    owner="user-123",
    tenant_id="tenant-1",
    type="training",
    payload={"model": "gpt-4", "dataset": "finance"},
)

await job_store.create(job, ttl_seconds=864000)  # 10 days
```

### Listing Jobs

```python
# List user's jobs
jobs, total = await job_store.list_by_owner(
    owner="user-123",
    status=JobStatus.RUNNING,
    offset=0,
    limit=25
)

# Admin view
all_jobs, total = await job_store.list_all(
    status=None,
    offset=0,
    limit=50
)
```

### SSE Event Handling

```python
# Append status event
event = SSEEvent(
    event_id=await event_store.get_next_event_id(job_id),
    event_type="status",
    data={"job_id": job_id, "status": "running"}
)

await event_store.append(job_id, event, ring_size=100)

# Replay events for resume
events = await event_store.replay_from(job_id, last_event_id=42)
```

### Idempotency Check

```python
from src.jobs.memory_store import create_idempotency_key

# Generate idempotency key
key = create_idempotency_key(
    owner="user-123",
    tenant="tenant-1",
    job_type="training",
    payload={"model": "gpt-4"},
    idempotency_key="user-provided-key"
)

# Check if exists
existing_job_id = await idem_store.get_job_id(key)
if existing_job_id:
    # Return existing job
    return existing_job_id

# Create new job and store key
await idem_store.store(key, new_job_id, ttl_seconds=86400)
```

## Performance Considerations

### Memory Backend
- **Pros**: Fast operations, no network latency
- **Cons**: No persistence, single-instance only
- **Use Case**: Development, testing, demos

### Redis Backend
- **Pros**: Persistence, multi-instance support, TTL expiry
- **Cons**: Network latency, Redis dependency
- **Use Case**: Production deployments

### Optimization Strategies

1. **Batch Operations**: Use Redis pipelines for multiple operations
2. **Connection Pooling**: Reuse Redis connections
3. **TTL Management**: Automatic cleanup of expired jobs
4. **Ring Buffer Sizing**: Balance memory usage vs. resume capability

## Migration and Extensibility

### Adding New Backends

To add a new storage backend (e.g., PostgreSQL):

1. **Implement Interfaces**: Create classes implementing `JobStore`, `IdempotencyStore`, `EventStore`
2. **Update Factory**: Add new backend case in `get_stores()`
3. **Add Configuration**: Support new backend in settings
4. **Add Metrics**: Update metrics decorators for new backend

### Backward Compatibility

The memory implementation maintains compatibility with existing global `_JOBS` dictionary, ensuring smooth migration paths.

## Monitoring and Debugging

### Health Checks

Monitor backend connectivity and performance:

```python
# Check Redis connectivity
redis_ping = await redis_client.ping()

# Monitor queue depths
active_jobs = await job_store.list_all(status=JobStatus.RUNNING)
```

### Debugging Tools

```python
# Get all events for debugging
events = await event_store.get_all_events(job_id)

# Inspect job storage
job = await job_store.get(job_id)
print(job.model_dump_json(indent=2))
```

### Log Analysis

Structured logging includes:
- Job creation/deletion events
- Status transitions
- SSE connection events
- Storage operation failures
- Idempotency key operations

## Integration Patterns

### FastAPI Integration

```python
from fastapi import APIRouter, Depends
from src.jobs.factory import get_stores

router = APIRouter()

@router.post("/jobs")
async def create_job(
    request: JobCreateRequest,
    stores = Depends(get_stores)
):
    job_store, idem_store, event_store = stores
    # Implementation
```

### Worker Integration

```python
# Worker updates job status
await job_store.update_status(
    job_id=job.id,
    status=JobStatus.RUNNING
)

# Emit SSE event
event = SSEEvent(...)
await event_store.append(job_id, event, ring_size)
```

### Testing

```python
# Use memory backend for tests
import pytest
from src.jobs.factory import get_stores

@pytest.fixture
def job_stores():
    # Override settings for testing
    return get_stores()  # Will use memory backend
```

This comprehensive Jobs framework provides a robust foundation for asynchronous job management with excellent scalability, monitoring, and developer experience.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_jobs.md