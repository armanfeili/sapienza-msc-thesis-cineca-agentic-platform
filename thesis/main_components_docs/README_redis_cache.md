# Redis Cache Module

> **Version:** 1.0.0  
> **Module:** `db.redis_cache`  
> **Purpose:** Scalable caching, job storage, rate limiting, and distributed coordination for the Cineca Agentic Platform

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Module Structure](#module-structure)
4. [Core Components](#core-components)
   - [Synchronous Client](#synchronous-client-clientpy)
   - [Asynchronous Client](#asynchronous-client-async_clientpy)
   - [Agent Redis Helpers](#agent-redis-helpers-agentspy)
   - [Job Store](#job-store-job_storepy)
   - [Jobs Cache](#jobs-cache-jobs_cachepy)
   - [Tools Cache](#tools-cache-tools_cachepy)
   - [Rate Limiting](#rate-limiting-rate_limitpy)
   - [Lua Scripts](#lua-scripts-lua_scriptspy)
   - [Maintenance Scheduler](#maintenance-scheduler-maintenancepy)
5. [Redis Key Schema](#redis-key-schema)
6. [Data Structures](#data-structures)
7. [TTL Configuration](#ttl-configuration)
8. [Rate Limiting](#rate-limiting-configuration)
9. [Distributed Coordination](#distributed-coordination)
10. [Error Handling & Fallbacks](#error-handling--fallbacks)
11. [Configuration](#configuration)
12. [Public API Reference](#public-api-reference)
13. [Usage Examples](#usage-examples)
14. [Maintenance & Operations](#maintenance--operations)
15. [Performance Considerations](#performance-considerations)
16. [Dependencies](#dependencies)
17. [Related Documentation](#related-documentation)

---

## Overview

The Redis Cache module provides comprehensive Redis-based infrastructure for the Cineca Agentic Platform, enabling:

- **High-Performance Caching**: Fast key-value storage with JSON serialization support
- **Job Storage Backend**: Scalable, TTL-based job document management with ZSET indexes
- **Rate Limiting**: Sliding window algorithm with per-user and per-tenant quotas
- **Distributed Coordination**: Session locks, step sequencing, and cancellation flags
- **Agent State Management**: Session caching, ETag computation, and idempotency
- **SSE Event Streaming**: Ring buffer storage for Server-Sent Events
- **Tool Invocation Management**: Queue management and result caching for tool executions
- **Automatic Maintenance**: Background orphan cleanup and index hygiene

The module implements graceful degradation with in-memory fallbacks when Redis is unavailable, ensuring platform resilience.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Redis Cache Module                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────────────┐ │
│  │  Sync Client    │  │  Async Client    │  │    Agent Helpers            │ │
│  │  (client.py)    │  │  (async_client)  │  │    (agents.py)              │ │
│  │                 │  │                  │  │                             │ │
│  │ • cache_get/set │  │ • get_async_redis│  │ • Session state caching     │ │
│  │ • idem_get/set  │  │ • Connection pool│  │ • Step sequence allocation  │ │
│  │ • JSON helpers  │  │ • Health checks  │  │ • Distributed locks         │ │
│  │ • Local fallback│  │ • Socket timeout │  │ • Cancellation flags        │ │
│  └────────┬────────┘  └────────┬─────────┘  │ • ETag management           │ │
│           │                    │            │ • Idempotency support       │ │
│           │                    │            └──────────────┬──────────────┘ │
│           │                    │                           │                │
│  ┌────────▼────────────────────▼───────────────────────────▼──────────────┐ │
│  │                          Redis Server (REDIS_URL)                      │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │ │
│  │  │  STRING  │ │   HASH   │ │   ZSET   │ │   LIST   │ │   COUNTER    │  │ │
│  │  │ Caching  │ │ Job Docs │ │ Indexes  │ │  Queues  │ │  Sequences   │  │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────────────┐ │
│  │  Job Store      │  │  Tools Cache     │  │    Rate Limiting            │ │
│  │  (job_store.py) │  │  (tools_cache)   │  │    (rate_limit.py)          │ │
│  │                 │  │                  │  │                             │ │
│  │ • RedisJobStore │  │ • Queue mgmt     │  │ • Sliding window algo       │ │
│  │ • IdempotencyS. │  │ • State tracking │  │ • Per-user limits           │ │
│  │ • EventStore    │  │ • Result caching │  │ • Per-tenant quotas         │ │
│  │ • Lua scripts   │  │ • Rate limiting  │  │ • Local fallback            │ │
│  └─────────────────┘  └──────────────────┘  └─────────────────────────────┘ │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                    Maintenance Scheduler (maintenance.py)               ││
│  │    • Periodic orphan cleanup  • Index hygiene  • Background asyncio     ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Module Structure

```
db/redis_cache/
├── __init__.py           # Package exports and public API (86 lines)
├── client.py             # Synchronous Redis client (300 lines)
├── async_client.py       # Asynchronous Redis client with pooling (165 lines)
├── agents.py             # Agent session/step Redis helpers (380 lines)
├── job_store.py          # Redis job storage implementation (734 lines)
├── jobs_cache.py         # Job queue and state helpers (438 lines)
├── tools_cache.py        # Tool invocation cache helpers (494 lines)
├── rate_limit.py         # Rate limiting with sliding window (512 lines)
├── lua_scripts.py        # Atomic Lua scripts for Redis (160 lines)
├── maintenance.py        # Background maintenance scheduler (157 lines)
└── README.md             # This documentation
```

**Total Lines of Code:** ~3,400+ lines

---

## Core Components

### Synchronous Client (`client.py`)

The synchronous Redis client provides low-level caching primitives with automatic JSON serialization and graceful fallback to in-memory storage.

#### Key Features

- **Connection Management**: Lazy initialization with `get_redis()`
- **Health Checks**: `redis_available()` and `redis_health()` functions
- **JSON Serialization**: Custom encoder supporting datetime, UUID, Decimal, dataclasses, Pydantic models
- **Idempotency Support**: `idem_get/set` with local fallback when Redis unavailable
- **TTL Management**: `incr_with_ttl()` for atomic increment with expiration

#### Core Functions

```python
# Connection management
def get_redis() -> Redis:
    """Get synchronous Redis client instance."""

def redis_available() -> bool:
    """Check if Redis is reachable."""

def redis_health() -> dict[str, Any]:
    """Get Redis health information for diagnostics."""

# Basic cache operations
def cache_get(key: str) -> str | None:
    """Get value from Redis cache."""

def cache_set(key: str, value: str, ex: int | None = None) -> bool:
    """Set value in Redis cache with optional TTL."""

def cache_delete(key: str) -> bool:
    """Delete key from Redis cache."""

# JSON cache operations
def cache_get_json(key: str) -> dict[str, Any] | None:
    """Get JSON-decoded value from cache."""

def cache_set_json(key: str, value: dict[str, Any], ex: int | None = None) -> bool:
    """Set JSON-encoded value in cache."""

# Idempotency with fallback
def idem_get(key: str) -> str | None:
    """Get idempotency value (falls back to local dict if Redis unavailable)."""

def idem_set(key: str, value: str, ttl: int | None = None) -> bool:
    """Set idempotency value with TTL."""

# TTL helpers
def incr_with_ttl(key: str, ttl: int) -> int:
    """Atomic increment with TTL set on first increment."""

def ttl(key: str) -> int:
    """Get remaining TTL in seconds (-1 if no expiry, -2 if key doesn't exist)."""
```

#### Custom JSON Encoder

The module includes a sophisticated JSON encoder that handles complex Python types:

```python
def _json_default(obj):
    """Custom JSON encoder for complex types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, Decimal):
        return float(obj)
    elif hasattr(obj, '__dataclass_fields__'):
        return asdict(obj)
    elif hasattr(obj, 'model_dump'):  # Pydantic v2
        return obj.model_dump()
    elif hasattr(obj, 'dict'):  # Pydantic v1
        return obj.dict()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
```

---

### Asynchronous Client (`async_client.py`)

The async client provides non-blocking Redis access with connection pooling, designed for high-concurrency scenarios like job storage.

#### Key Features

- **Connection Pooling**: Maximum 10 connections per pool
- **Socket Timeout**: 5-second timeout with retry on timeout
- **Lazy Initialization**: Connection established on first use
- **Graceful Cleanup**: `close_async_redis()` for application shutdown

#### Core Functions

```python
async def get_async_redis() -> Redis:
    """
    Get async Redis client with connection pooling.
    
    Connection Pool Configuration:
    - max_connections: 10
    - socket_timeout: 5 seconds
    - retry_on_timeout: True
    - decode_responses: True (strings, not bytes)
    """

async def close_async_redis() -> None:
    """Close async Redis connection pool (call during app shutdown)."""

async def async_redis_health() -> dict[str, Any]:
    """Get async Redis health information."""

async def async_redis_available() -> bool:
    """Check if async Redis is reachable."""
```

---

### Agent Redis Helpers (`agents.py`)

Specialized Redis helpers for managing agent sessions, steps, and runs with support for distributed coordination.

#### Session State Caching

```python
def get_session_state(session_id: str) -> dict[str, Any] | None:
    """
    Get cached session state.
    
    Key: agent:session:{session_id}
    TTL: 3600 seconds (1 hour)
    """

def set_session_state(session_id: str, state: dict[str, Any]) -> bool:
    """Cache session state with 1-hour TTL."""

def delete_session_state(session_id: str) -> bool:
    """Invalidate session state cache."""

def update_session_heartbeat(session_id: str) -> bool:
    """Update heartbeat timestamp and refresh TTL."""
```

#### Step Sequence Allocation

```python
def allocate_next_seq(session_id: str) -> int:
    """
    Allocate next step sequence number (atomic INCR).
    
    Key: agent:seq:{session_id}
    TTL: 7 days
    
    Uses Redis INCR for guaranteed uniqueness in distributed environments.
    """
```

#### Distributed Locks

Context managers for session and step-level locking to prevent concurrent modifications:

```python
@contextmanager
def session_lock(session_id: str, timeout: int = 10):
    """
    Acquire session lock with automatic release.
    
    Key: lock:session:{session_id}
    Uses: SET NX EX pattern
    
    Example:
        with session_lock("sess-123", timeout=5):
            # Exclusive access to session
            process_session()
    """

@contextmanager
def step_lock(session_id: str, seq: int, timeout: int = 5):
    """
    Acquire step lock for specific step.
    
    Key: lock:step:{session_id}:{seq}
    """
```

#### Cancellation Flags

```python
def is_session_cancelled(session_id: str) -> bool:
    """Check if cancellation flag is set for session."""

def set_session_cancelled(session_id: str, ttl: int = 3600) -> bool:
    """Set cancellation flag for session (atomic)."""

def clear_session_cancelled(session_id: str) -> bool:
    """Clear cancellation flag."""
```

#### ETag Management

```python
def compute_list_etag(items: list[Any]) -> str:
    """
    Compute ETag from list of items using SHA256.
    
    Used for HTTP caching headers on list endpoints.
    """

def get_sessions_etag(user_id: str) -> str | None:
    """Get cached ETag for user's sessions list."""

def set_sessions_etag(user_id: str, etag: str) -> bool:
    """Cache sessions list ETag (60s TTL)."""

def invalidate_sessions_etag(user_id: str) -> bool:
    """Invalidate ETag when sessions change."""

def get_steps_etag(session_id: str) -> str | None:
    """Get cached ETag for session's steps list."""

def set_steps_etag(session_id: str, etag: str) -> bool:
    """Cache steps list ETag (60s TTL)."""

def invalidate_steps_etag(session_id: str) -> bool:
    """Invalidate ETag when steps change."""
```

#### Idempotency Support

```python
def get_idempotent_response(idempotency_key: str) -> dict[str, Any] | None:
    """
    Get cached response for idempotency key.
    
    Key: idem:agent:{idempotency_key}
    """

def cache_idempotent_response(
    idempotency_key: str, 
    response: dict[str, Any], 
    ttl: int | None = None
) -> bool:
    """
    Cache response for idempotency key.
    
    TTL: settings.IDEMPOTENCY_TTL_SECONDS (default from config)
    """
```

---

### Job Store (`job_store.py`)

Complete Redis-backed implementation of the job storage interfaces, used when `JOB_STORE_BACKEND=redis`.

#### RedisJobStore

```python
class RedisJobStore(JobStore):
    """
    Redis-backed job storage with TTL-based auto-expiry.
    
    Key Schema:
    - job:{id} → HASH with job fields
    - jobs:all → ZSET (score=created_at_ms, member=job_id)
    - jobs:owner:{owner} → ZSET (score=created_at_ms, member=job_id)
    - jobs:status:{status} → ZSET (score=created_at_ms, member=job_id)
    
    All keys expire after JOB_TTL_DAYS.
    """
    
    async def create(self, job: JobDocument, ttl_seconds: int) -> None:
        """
        Store job in Redis with TTL.
        
        Atomic pipeline:
        1. HSET job:{id} with all fields
        2. EXPIRE job:{id}
        3. ZADD jobs:all with score=created_at_ms
        4. ZADD jobs:owner:{owner}
        5. ZADD jobs:status:{status}
        """
    
    async def get(self, job_id: str) -> JobDocument | None:
        """Retrieve job document from Redis HASH."""
    
    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        result: dict | None = None,
        error: str | None = None,
        ttl_seconds: int | None = None,
    ) -> bool:
        """
        Atomically update job status.
        
        Status Transitions:
        1. Read current status from HASH
        2. Update HASH fields (status, updated_at, result, error)
        3. Move ZSET membership from old to new status index
        4. If terminal, optionally extend TTL
        """
    
    async def cancel_job_atomic(self, job_id: str) -> bool:
        """
        Atomically cancel job using Lua CAS (Compare-And-Set).
        
        Safer than update_status() for concurrent cancellation.
        Uses Lua script for atomic check-and-update.
        
        Returns:
            True if job was cancelled (from queued/running)
            False if already terminal or not found
        """
    
    async def list_by_owner(
        self,
        owner: str,
        status: JobStatus | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[list[JobDocument], int]:
        """
        List jobs by owner, newest first.
        
        Uses ZREVRANGE for pagination.
        If status filter, uses ZINTERSTORE with temp key.
        """
    
    async def list_all(
        self,
        status: JobStatus | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[list[JobDocument], int]:
        """List all jobs (admin view), newest first."""
    
    async def delete(self, job_id: str) -> bool:
        """
        Delete job and all related keys.
        
        Removes: job:{id}, entries from all ZSETs, events, event_seq
        """
    
    async def cleanup_orphaned_index_members(
        self,
        index_key: str,
        batch_size: int = 100,
    ) -> int:
        """
        Clean orphaned ZSET members using Lua script.
        
        Orphaned members: job IDs whose job HASH expired/deleted.
        Used by maintenance scheduler.
        """
```

#### RedisIdempotencyStore

```python
class RedisIdempotencyStore(IdempotencyStore):
    """
    Redis-backed idempotency key storage.
    
    Key Format: idem:{owner}:{tenant}:{type}:{payload_hash}:{key}
    Value: job_id
    TTL: IDEMPOTENCY_TTL_HOURS (default 24 hours)
    """
    
    @staticmethod
    def _create_key(
        owner: str,
        tenant: str,
        job_type: str,
        payload: dict,
        idempotency_key: str | None = None,
    ) -> str:
        """
        Generate idempotency key.
        
        Format: idem:{owner}:{tenant}:{type}:{sha256(payload)[:16]}:{key}
        Uses SHA256 hash of JSON-serialized payload for determinism.
        """
    
    async def get_job_id(self, key: str) -> str | None:
        """Check if idempotency key exists, return job_id if so."""
    
    async def store(self, key: str, job_id: str, ttl_seconds: int) -> None:
        """Store idempotency mapping with TTL."""
```

#### RedisEventStore

```python
class RedisEventStore(EventStore):
    """
    Redis-backed SSE event storage with ring buffer.
    
    Key Schema:
    - job:{id}:events → LIST of SSE events (JSON-serialized)
    - job:{id}:event_seq → COUNTER for monotonic event IDs
    
    Ring buffer: LIST trimmed to ring_size after each append.
    """
    
    async def append(self, job_id: str, event: SSEEvent, ring_size: int) -> None:
        """
        Append event to ring buffer.
        
        Uses LPUSH + LTRIM for FIFO ring buffer.
        Newest events at head (index 0).
        """
    
    async def get_next_event_id(self, job_id: str) -> int:
        """
        Get next event ID (atomic INCR).
        
        Guarantees monotonically increasing event IDs.
        """
    
    async def replay_from(self, job_id: str, last_event_id: int) -> list[SSEEvent]:
        """
        Replay events after last_event_id.
        
        Returns events with event_id > last_event_id in chronological order.
        Handles ring buffer gaps gracefully.
        """
    
    async def get_all_events(self, job_id: str) -> list[SSEEvent]:
        """Get all events for a job (debugging/admin)."""
```

---

### Jobs Cache (`jobs_cache.py`)

Synchronous helpers for job queue management, state tracking, and event streaming.

#### Queue Operations

```python
def queue_push_job(job_type: str, job_id: UUID, priority: int = 0) -> int:
    """
    Push job ID to queue for given type.
    
    Key: jobs:queue:{type}
    Uses LPUSH for FIFO ordering.
    """

def queue_pop_job(job_type: str, timeout: int = 0) -> str | None:
    """
    Pop (claim) job ID from queue.
    
    Uses RPOP (non-blocking) or BRPOP (blocking with timeout).
    """

def queue_length(job_type: str) -> int:
    """Get current queue depth for job type."""

def queue_peek(job_type: str, count: int = 10) -> list[str]:
    """Peek at jobs in queue without popping."""
```

#### Job State

```python
def set_job_state(
    job_id: UUID,
    status: str,
    owner_sub: str,
    *,
    progress: int | None = None,
    worker_id: str | None = None,
    ttl_seconds: int = 7200,  # 2 hours
) -> None:
    """
    Set job state in Redis HASH.
    
    Key: jobs:{id}:state
    Fields: status, owner_sub, heartbeat_ts, progress, worker_id
    """

def get_job_state(job_id: UUID) -> dict[str, str] | None:
    """Get job state from Redis."""

def update_heartbeat(job_id: UUID) -> bool:
    """Update heartbeat timestamp for running job."""
```

#### Job Result Cache

```python
def cache_job_result(job_id: UUID, result_data: dict[str, Any], ttl_days: int = 1) -> None:
    """
    Cache job result in Redis.
    
    Key: jobs:{id}:result
    TTL: 1 day default
    """

def get_cached_result(job_id: UUID) -> dict[str, Any] | None:
    """Get cached job result."""
```

#### Job Events Stream

```python
def append_job_event(
    job_id: UUID,
    event_type: str,
    event_data: dict[str, Any],
    seq_id: int,
    maxlen: int = 1000
) -> None:
    """
    Append event to job's event stream.
    
    Key: jobs:{id}:events
    Uses LPUSH + LTRIM for capped list.
    """

def get_job_events(
    job_id: UUID,
    after_seq_id: int | None = None,
    limit: int = 100
) -> list[dict[str, Any]]:
    """Get events for job, optionally filtered by seq_id."""
```

#### Cancel Flag

```python
def set_cancel_flag(job_id: UUID, ttl_seconds: int = 3600) -> bool:
    """
    Set cancel flag for job (atomic NX).
    
    Key: jobs:cancel:{id}
    Returns True if flag was set, False if already set.
    """

def check_cancel_flag(job_id: UUID) -> bool:
    """Check if cancel flag is set."""

def clear_cancel_flag(job_id: UUID) -> None:
    """Clear cancel flag."""

def atomic_cancel_if_not_terminal(job_id: UUID, ttl_seconds: int = 3600) -> bool:
    """
    Atomically set cancel flag only if job not terminal.
    
    Uses Lua script for CAS operation.
    """
```

---

### Tools Cache (`tools_cache.py`)

Redis caching helpers for tool invocations including queue management, state tracking, and result caching.

#### Key Design

```
tools:queue:{name}         - LIST: pending execution IDs for tool
tools:inv:{eid}:state      - STRING: current state (pending/running/finished/failed/cancelled)
tools:inv:{eid}:result     - JSON: cached result (1 hour TTL)
tools:inv:{eid}:error      - JSON: cached error details (1 hour TTL)
tools:idempotency:{key}    - STRING: maps idempotency key to eid (24 hours TTL)
tools:sse:{eid}:cursor     - STRING: SSE event cursor (5 minutes TTL)
tools:rate:{name}:{tenant} - STRING: rate limit counter (1 minute TTL)
```

#### Queue Management

```python
def queue_push_invocation(tool_name: str, eid: str) -> int:
    """Push execution ID to tool's pending queue."""

def queue_pop_invocation(tool_name: str, timeout: int = 0) -> str | None:
    """Pop execution ID from queue (FIFO)."""

def queue_length(tool_name: str) -> int:
    """Get current queue length for tool."""

def queue_peek(tool_name: str, count: int = 10) -> list[str]:
    """Peek at pending invocations without removing."""

def queue_remove_invocation(tool_name: str, eid: str) -> int:
    """Remove specific execution ID (for cancellation)."""
```

#### State Tracking

```python
def set_invocation_state(eid: str, state: str, ttl: int = 7200) -> bool:
    """Set invocation state (pending/running/finished/failed/cancelled)."""

def get_invocation_state(eid: str) -> str | None:
    """Get invocation state."""

def delete_invocation_state(eid: str) -> bool:
    """Delete invocation state."""
```

#### Result & Error Caching

```python
def cache_invocation_result(eid: str, result: dict, ttl: int = 3600) -> bool:
    """Cache invocation result (JSON-serialized, 1 hour default)."""

def get_cached_result(eid: str) -> dict | None:
    """Get cached invocation result."""

def cache_invocation_error(eid: str, error: dict, ttl: int = 3600) -> bool:
    """Cache invocation error details."""

def get_cached_error(eid: str) -> dict | None:
    """Get cached error details."""
```

#### SSE Cursor Tracking

```python
def set_sse_cursor(eid: str, cursor: str, ttl: int = 300) -> bool:
    """Set SSE cursor for invocation streaming (5 min TTL)."""

def get_sse_cursor(eid: str) -> str | None:
    """Get SSE cursor for invocation."""
```

#### Rate Limiting

```python
def check_rate_limit(
    tool_name: str,
    tenant_id: str,
    max_count: int,
    window_secs: int = 60
) -> tuple[bool, int]:
    """
    Check and increment rate limit counter.
    
    Returns: (allowed, current_count)
    """

def get_rate_limit_count(tool_name: str, tenant_id: str) -> int:
    """Get current rate limit count without incrementing."""

def reset_rate_limit(tool_name: str, tenant_id: str) -> bool:
    """Reset rate limit counter for tool/tenant."""
```

#### Bulk Operations

```python
def cleanup_invocation_cache(eid: str) -> int:
    """Delete all Redis keys for an invocation."""

def get_all_queue_lengths() -> dict[str, int]:
    """Get queue lengths for all tools (uses SCAN)."""
```

---

### Rate Limiting (`rate_limit.py`)

Sophisticated rate limiting using the sliding window algorithm with support for per-user and per-tenant quotas.

#### Core Functions

```python
async def check_rate_limit(
    key: str,
    limit: int,
    window: int,
) -> tuple[bool, int, int]:
    """
    Check if rate limit is exceeded using sliding window algorithm.
    
    Uses Redis sorted sets to track timestamps of requests.
    Old entries automatically cleaned up.
    
    Args:
        key: Redis key (e.g., "ratelimit:sessions:user123")
        limit: Maximum requests allowed in window
        window: Time window in seconds
    
    Returns:
        (allowed, remaining, retry_after)
        - allowed: True if request allowed
        - remaining: Requests remaining in window
        - retry_after: Seconds to wait if exceeded (0 if allowed)
    
    Example:
        allowed, remaining, retry = await check_rate_limit(
            "ratelimit:sessions:user123",
            limit=10,
            window=60
        )
        if not allowed:
            raise RateLimitExceeded(10, 60, retry)
    """

async def increment_rate_limit(
    key: str,
    limit: int,
    window: int,
) -> tuple[int, int]:
    """
    Increment rate limit counter unconditionally.
    
    Returns: (current_count, retry_after)
    """

async def get_rate_limit_status(
    key: str,
    limit: int,
    window: int,
) -> tuple[int, int, int]:
    """
    Get rate limit status without incrementing.
    
    Returns: (current, remaining, reset_in)
    """

async def reset_rate_limit(key: str) -> None:
    """Reset rate limit by deleting the key."""
```

#### Rate Limit Configuration

```python
# Production limits
RATE_LIMITS_PROD = {
    # Per-user limits
    "sessions:create": {"limit": 10, "window": 60},
    "steps:create": {"limit": 100, "window": 60},
    "runs:create": {"limit": 20, "window": 60},
    "sessions:list": {"limit": 100, "window": 60},
    "steps:list": {"limit": 100, "window": 60},
    
    # Per-tenant quotas (organization-wide)
    "tenant:sessions:create": {"limit": 1000, "window": 3600},
    "tenant:steps:create": {"limit": 10000, "window": 3600},
    "tenant:runs:create": {"limit": 2000, "window": 3600},
}

# Test limits (much higher for testing)
RATE_LIMITS_TEST = {
    "sessions:create": {"limit": 10000, "window": 60},
    # ... similar pattern
}
```

#### Helper Functions

```python
def get_rate_limit_config(action: str) -> tuple[int, int]:
    """
    Get rate limit config for action.
    
    Respects RATE_LIMIT_MODE environment variable ('prod' or 'test').
    """

def make_rate_limit_key(action: str, user_id: str, resource_id: str | None = None) -> str:
    """
    Create Redis key for rate limiting.
    
    Examples:
        make_rate_limit_key("sessions:create", "user123")
        → 'ratelimit:sessions:create:user123'
        
        make_rate_limit_key("steps:create", "user123", "session456")
        → 'ratelimit:steps:create:user123:session456'
    """

def make_tenant_quota_key(action: str, tenant_id: str) -> str:
    """
    Create Redis key for tenant-level quotas.
    
    Example:
        make_tenant_quota_key("sessions:create", "tenant-acme")
        → 'ratelimit:tenant:sessions:create:tenant-acme'
    """

async def check_tenant_quota(action: str, tenant_id: str) -> tuple[bool, int, int]:
    """Check if tenant quota is exceeded."""
```

#### Local Fallback

When Redis is unavailable, rate limiting falls back to in-memory storage:

```python
_LOCAL_RATE_DATA: dict[str, list[float]] = defaultdict(list)
_LOCAL_DATA_LOCK: asyncio.Lock | None = None

async def _check_rate_limit_local(key, limit, window) -> tuple[bool, int, int]:
    """In-memory fallback when Redis unavailable."""
```

---

### Lua Scripts (`lua_scripts.py`)

Atomic Redis operations implemented as Lua scripts for strict consistency.

#### CANCEL_JOB_SCRIPT

```lua
-- Cancel job atomically (CAS pattern)
-- KEYS[1] = job:{id}
-- ARGV[1] = timestamp, ARGV[2] = result JSON
-- Returns: "cancelled" | "already_terminal" | "not_found"

local current_status = redis.call('HGET', KEYS[1], 'status')

if current_status == 'queued' or current_status == 'running' then
    redis.call('HSET', KEYS[1], 'status', 'cancelled')
    redis.call('HSET', KEYS[1], 'updated_at', ARGV[1])
    redis.call('HSET', KEYS[1], 'result', ARGV[2])
    return "cancelled"
else
    return "already_terminal"
end
```

#### UPDATE_STATUS_SCRIPT

```lua
-- Update job status with ZSET index management
-- Handles status transition and index migration atomically
```

#### CLEANUP_ORPHANS_SCRIPT

```lua
-- Clean orphaned ZSET members whose job HASHes expired
-- Returns count of removed orphans
```

#### DELETE_JOB_SCRIPT

```lua
-- Delete job and all related keys atomically
-- Removes from all indexes, events, and counters
```

#### IDEMPOTENCY_CAS_SCRIPT

```lua
-- Atomically check idempotency key and set if missing
-- Returns existing job_id if key exists, "set" if newly created
```

---

### Maintenance Scheduler (`maintenance.py`)

Background asyncio tasks for Redis health and cleanup.

```python
class RedisMaintenanceScheduler:
    """
    Schedules periodic maintenance tasks for Redis job store.
    
    Tasks:
    - Index orphan cleanup: Remove stale ZSET members whose jobs expired
    - Health checks: Verify Redis connectivity and index consistency
    
    Default Configuration:
    - cleanup_interval_seconds: 3600 (1 hour)
    - batch_size: 500 members per scan
    """
    
    async def start(self):
        """Start maintenance scheduler."""
    
    async def stop(self):
        """Stop maintenance scheduler gracefully."""
    
    async def _maintenance_loop(self):
        """Main loop: run cleanup tasks periodically."""
    
    async def _run_cleanup_cycle(self):
        """
        Execute one cleanup cycle:
        1. Clean global index (jobs:all)
        2. Clean status indexes (jobs:status:*)
        3. Scan and clean owner indexes (jobs:owner:*)
        """

# Application lifecycle functions
async def start_redis_maintenance(
    cleanup_interval_seconds: int = 3600,
    batch_size: int = 500,
):
    """Start Redis maintenance (called from app startup)."""

async def stop_redis_maintenance():
    """Stop Redis maintenance (called from app shutdown)."""
```

---

## Redis Key Schema

### Agent Keys

| Key Pattern | Type | TTL | Description |
|-------------|------|-----|-------------|
| `agent:session:{session_id}` | HASH | 1 hour | Session state cache |
| `agent:seq:{session_id}` | STRING (counter) | 7 days | Step sequence counter |
| `lock:session:{session_id}` | STRING | 5-10 sec | Session distributed lock |
| `lock:step:{session_id}:{seq}` | STRING | 5 sec | Step distributed lock |
| `cancel:session:{session_id}` | STRING | 1 hour | Cancellation flag |
| `etag:sessions:{user_id}` | STRING | 60 sec | Sessions list ETag |
| `etag:steps:{session_id}` | STRING | 60 sec | Steps list ETag |
| `idem:agent:{key}` | JSON | configurable | Idempotency response cache |

### Job Keys

| Key Pattern | Type | TTL | Description |
|-------------|------|-----|-------------|
| `job:{id}` | HASH | JOB_TTL_DAYS | Job document with all fields |
| `jobs:all` | ZSET | JOB_TTL_DAYS | Global job index (score=created_at_ms) |
| `jobs:owner:{owner}` | ZSET | JOB_TTL_DAYS | Per-user job index |
| `jobs:status:{status}` | ZSET | JOB_TTL_DAYS | Status-based job index |
| `job:{id}:events` | LIST | JOB_TTL_DAYS | SSE ring buffer (capped) |
| `job:{id}:event_seq` | STRING (counter) | JOB_TTL_DAYS | Monotonic event IDs |
| `jobs:{id}:state` | HASH | 2 hours | Job state (legacy) |
| `jobs:{id}:result` | JSON | 1 day | Cached job result |
| `jobs:queue:{type}` | LIST | - | Job queue by type |
| `jobs:cancel:{id}` | STRING | 1 hour | Job cancellation flag |
| `jobs:idemp:{owner}:{key}` | STRING | 24 hours | Idempotency mapping |

### Idempotency Keys

| Key Pattern | Type | TTL | Description |
|-------------|------|-----|-------------|
| `idem:{owner}:{tenant}:{type}:{hash}:{key}` | STRING | 24 hours | Full idempotency key |

### Tools Keys

| Key Pattern | Type | TTL | Description |
|-------------|------|-----|-------------|
| `tools:queue:{name}` | LIST | - | Pending execution queue |
| `tools:inv:{eid}:state` | STRING | 2 hours | Invocation state |
| `tools:inv:{eid}:result` | JSON | 1 hour | Cached result |
| `tools:inv:{eid}:error` | JSON | 1 hour | Cached error |
| `tools:idempotency:{key}` | STRING | 24 hours | Idempotency to eid mapping |
| `tools:sse:{eid}:cursor` | STRING | 5 min | SSE event cursor |
| `tools:rate:{name}:{tenant}` | STRING (counter) | 1 min | Rate limit counter |

### Rate Limit Keys

| Key Pattern | Type | TTL | Description |
|-------------|------|-----|-------------|
| `ratelimit:{action}:{user_id}` | ZSET | window | User rate limit (sliding window) |
| `ratelimit:{action}:{user_id}:{resource}` | ZSET | window | Resource-scoped rate limit |
| `ratelimit:tenant:{action}:{tenant_id}` | ZSET | window | Tenant quota (sliding window) |

---

## Data Structures

### JobDocument HASH Fields

```
id           - Job UUID
owner        - Owner user ID
tenant       - Tenant ID
job_type     - Job type (e.g., "agent.run")
status       - Current status (queued/running/finished/failed/cancelled)
payload      - JSON: job payload
result       - JSON: job result (optional)
error        - Error message (optional)
created_at   - ISO 8601 timestamp
updated_at   - ISO 8601 timestamp
```

### SSEEvent JSON Structure

```json
{
    "event_id": 1,
    "event_type": "status",
    "data": {
        "status": "running",
        "progress": 50
    }
}
```

### Job State HASH Fields

```
status       - Current status
owner_sub    - Owner identifier
heartbeat_ts - Last heartbeat (ISO 8601)
progress     - Progress percentage (optional)
worker_id    - Processing worker ID (optional)
```

---

## TTL Configuration

| Context | Default TTL | Configurable Via |
|---------|-------------|------------------|
| Session state | 3600s (1 hour) | Hardcoded |
| Step sequence counter | 7 days | Hardcoded |
| Distributed locks | 5-10 seconds | Function parameter |
| Cancellation flags | 3600s (1 hour) | Function parameter |
| ETags | 60s | Hardcoded |
| Idempotency | IDEMPOTENCY_TTL_SECONDS | `settings.IDEMPOTENCY_TTL_SECONDS` |
| Job documents | JOB_TTL_DAYS × 86400 | `settings.JOB_TTL_DAYS` |
| Job state (legacy) | 7200s (2 hours) | Function parameter |
| Job result cache | 86400s (1 day) | Function parameter |
| Tool invocation state | 7200s (2 hours) | Function parameter |
| Tool result cache | 3600s (1 hour) | Function parameter |
| Tool error cache | 3600s (1 hour) | Function parameter |
| SSE cursor | 300s (5 minutes) | Function parameter |
| Rate limit counters | Window duration | Per-action configuration |

---

## Rate Limiting Configuration

### Production Limits

| Action | Limit | Window | Scope |
|--------|-------|--------|-------|
| `sessions:create` | 10 | 60s | Per-user |
| `steps:create` | 100 | 60s | Per-user |
| `runs:create` | 20 | 60s | Per-user |
| `sessions:list` | 100 | 60s | Per-user |
| `steps:list` | 100 | 60s | Per-user |
| `tenant:sessions:create` | 1000 | 1 hour | Per-tenant |
| `tenant:steps:create` | 10000 | 1 hour | Per-tenant |
| `tenant:runs:create` | 2000 | 1 hour | Per-tenant |

### Test Limits

All limits multiplied by 1000× for testing environments.

### Environment Variable

```bash
RATE_LIMIT_MODE=prod   # Use production limits
RATE_LIMIT_MODE=test   # Use relaxed test limits
```

---

## Distributed Coordination

### Lock Acquisition Pattern

```python
from db.redis_cache.agents import session_lock, step_lock

# Session-level exclusive access
with session_lock("session-uuid-123", timeout=10):
    # Only one process can hold this lock
    process_session_exclusively()

# Step-level lock for specific step
with step_lock("session-uuid-123", seq=5, timeout=5):
    # Prevents concurrent modification of step 5
    update_step_atomically()
```

### Cancellation Pattern

```python
from db.redis_cache.agents import (
    is_session_cancelled,
    set_session_cancelled,
    clear_session_cancelled,
)

# Check cancellation in processing loop
while processing:
    if is_session_cancelled(session_id):
        cleanup_and_exit()
        break
    process_next_item()

# Request cancellation from API
set_session_cancelled(session_id, ttl=3600)

# Clear after processing complete
clear_session_cancelled(session_id)
```

### Sequence Allocation

```python
from db.redis_cache.agents import allocate_next_seq

# Guaranteed unique sequence number across all workers
next_seq = allocate_next_seq(session_id)  # Returns 1, 2, 3, ...
```

---

## Error Handling & Fallbacks

### Redis Unavailability

The module implements graceful degradation when Redis is unavailable:

1. **Idempotency**: Falls back to `_LOCAL_IDEMPOTENCY` in-memory dict
2. **Rate Limiting**: Falls back to `_LOCAL_RATE_DATA` with async lock
3. **Health Checks**: Return `available: False` with error details

### Local Fallback Implementation

```python
# In client.py
_LOCAL_IDEMPOTENCY: dict[str, str] = {}

def idem_get(key: str) -> str | None:
    r = get_redis()
    if r is None:
        return _LOCAL_IDEMPOTENCY.get(key)
    try:
        return r.get(key)
    except Exception:
        return _LOCAL_IDEMPOTENCY.get(key)

# In rate_limit.py
_LOCAL_RATE_DATA: dict[str, list[float]] = defaultdict(list)
_LOCAL_DATA_LOCK: asyncio.Lock | None = None

async def _check_rate_limit_local(key, limit, window):
    """In-memory sliding window when Redis unavailable."""
```

### Warning Emission

Only one warning is emitted per fallback type to avoid log spam:

```python
_LOCAL_WARNING_EMITTED = False

def _log_local_fallback(exc: Exception) -> None:
    global _LOCAL_WARNING_EMITTED
    if not _LOCAL_WARNING_EMITTED:
        logger.warning(
            "Redis unavailable for rate limiting; using in-memory fallback",
            extra={"error": str(exc)},
        )
        _LOCAL_WARNING_EMITTED = True
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `IDEMPOTENCY_TTL_SECONDS` | Idempotency key TTL | 86400 (24 hours) |
| `IDEMPOTENCY_TTL_HOURS` | Idempotency TTL in hours | 24 |
| `JOB_TTL_DAYS` | Job document TTL | 7 |
| `JOB_STORE_BACKEND` | Job storage backend | `"memory"` or `"redis"` |
| `RATE_LIMIT_MODE` | Rate limit profile | `"prod"` or `"test"` |

### Settings Reference

```python
from src.config import settings

# Redis connection
settings.REDIS_URL

# Job configuration
settings.JOB_TTL_DAYS
settings.JOB_STORE_BACKEND

# Idempotency
settings.IDEMPOTENCY_TTL_SECONDS
settings.IDEMPOTENCY_TTL_HOURS
```

---

## Public API Reference

### Package Exports (`__init__.py`)

```python
# Version
__version__ = "1.0.0"

# Synchronous client
from db.redis_cache.client import (
    get_redis,
    redis_available,
    redis_health,
    cache_get,
    cache_set,
    cache_delete,
    cache_get_json,
    cache_set_json,
    idem_get,
    idem_set,
    incr_with_ttl,
    ttl,
)

# Asynchronous client
from db.redis_cache.async_client import (
    get_async_redis,
    close_async_redis,
    async_redis_health,
    async_redis_available,
)

# Agent helpers
from db.redis_cache.agents import (
    get_session_state,
    set_session_state,
    delete_session_state,
    update_session_heartbeat,
    allocate_next_seq,
    session_lock,
    step_lock,
    is_session_cancelled,
    set_session_cancelled,
    clear_session_cancelled,
    compute_list_etag,
    get_sessions_etag,
    set_sessions_etag,
    invalidate_sessions_etag,
    get_steps_etag,
    set_steps_etag,
    invalidate_steps_etag,
    get_idempotent_response,
    cache_idempotent_response,
)

# Job store
from db.redis_cache.job_store import (
    RedisJobStore,
    RedisIdempotencyStore,
    RedisEventStore,
    create_idempotency_key,
)

# Tools cache
from db.redis_cache import tools_cache

# Rate limiting
from db.redis_cache.rate_limit import (
    check_rate_limit,
    increment_rate_limit,
    get_rate_limit_status,
    reset_rate_limit,
    get_rate_limit_config,
    make_rate_limit_key,
    make_tenant_quota_key,
    check_tenant_quota,
    RateLimitExceeded,
)

# Maintenance
from db.redis_cache.maintenance import (
    RedisMaintenanceScheduler,
    start_redis_maintenance,
    stop_redis_maintenance,
)
```

---

## Usage Examples

### Basic Caching

```python
from db.redis_cache import cache_get, cache_set, cache_get_json, cache_set_json

# String caching
cache_set("user:123:name", "Alice", ex=3600)
name = cache_get("user:123:name")

# JSON caching
user_data = {"name": "Alice", "email": "alice@example.com"}
cache_set_json("user:123:profile", user_data, ex=3600)
profile = cache_get_json("user:123:profile")
```

### Session Management

```python
from db.redis_cache import (
    get_session_state,
    set_session_state,
    session_lock,
    allocate_next_seq,
)

# Cache session state
session_state = {
    "user_id": "user-123",
    "status": "active",
    "last_step": 5,
}
set_session_state("session-uuid", session_state)

# Read session state
state = get_session_state("session-uuid")

# Allocate step sequence with lock
with session_lock("session-uuid"):
    seq = allocate_next_seq("session-uuid")
    # Create step with guaranteed unique seq
```

### Rate Limiting

```python
from db.redis_cache.rate_limit import (
    check_rate_limit,
    make_rate_limit_key,
    get_rate_limit_config,
    RateLimitExceeded,
)

async def create_session(user_id: str):
    # Get config
    limit, window = get_rate_limit_config("sessions:create")
    key = make_rate_limit_key("sessions:create", user_id)
    
    # Check rate limit
    allowed, remaining, retry_after = await check_rate_limit(key, limit, window)
    
    if not allowed:
        raise RateLimitExceeded(limit, window, retry_after)
    
    # Proceed with session creation
    return create_session_impl()
```

### Job Management

```python
from db.redis_cache import RedisJobStore, RedisEventStore
from src.jobs.models import JobDocument, JobStatus, SSEEvent

store = RedisJobStore()
event_store = RedisEventStore()

# Create job
job = JobDocument(
    id="job-123",
    owner="user-456",
    tenant="tenant-789",
    job_type="agent.run",
    status=JobStatus.QUEUED,
    payload={"prompt": "Hello"},
)
await store.create(job, ttl_seconds=86400)

# Update status
await store.update_status(
    "job-123",
    JobStatus.RUNNING,
    result=None,
    error=None,
)

# Append SSE event
event_id = await event_store.get_next_event_id("job-123")
event = SSEEvent(
    event_id=event_id,
    event_type="progress",
    data={"percent": 50},
)
await event_store.append("job-123", event, ring_size=100)

# Complete job
await store.update_status(
    "job-123",
    JobStatus.FINISHED,
    result={"output": "Hello, World!"},
)
```

### Tool Invocation Caching

```python
from db.redis_cache import tools_cache

# Queue invocation
tools_cache.queue_push_invocation("calculator", "exec-123")

# Track state
tools_cache.set_invocation_state("exec-123", "running")

# Cache result
tools_cache.cache_invocation_result("exec-123", {"answer": 42})

# Idempotency
tools_cache.set_idempotency_mapping("client-key-abc", "exec-123")
existing = tools_cache.get_idempotency_mapping("client-key-abc")
```

### Maintenance Scheduler

```python
from db.redis_cache import start_redis_maintenance, stop_redis_maintenance

# In application startup
async def startup():
    await start_redis_maintenance(
        cleanup_interval_seconds=3600,  # 1 hour
        batch_size=500,
    )

# In application shutdown
async def shutdown():
    await stop_redis_maintenance()
```

---

## Maintenance & Operations

### Index Cleanup

The maintenance scheduler automatically cleans orphaned ZSET members:

```python
# Manual cleanup if needed
from db.redis_cache import RedisJobStore

store = RedisJobStore()

# Clean specific index
removed = await store.cleanup_orphaned_index_members("jobs:all", batch_size=500)

# Clean all status indexes
for status in ["queued", "running", "finished", "failed", "cancelled"]:
    await store.cleanup_orphaned_index_members(f"jobs:status:{status}")
```

### Health Checks

```python
from db.redis_cache import redis_health, async_redis_health

# Sync health check
health = redis_health()
# Returns: {"available": True, "latency_ms": 1.5, "info": {...}}

# Async health check
health = await async_redis_health()
```

### Monitoring

The module integrates with observability:

```python
# Rate limit metrics
from src.observability.rate_limit_metrics import (
    record_rate_limit_check,
    record_tenant_quota_exceeded,
)

# Job cleanup metrics
from src.jobs.metrics import record_index_cleanup
```

---

## Performance Considerations

### Connection Pooling

- **Async Client**: Max 10 connections, socket timeout 5s
- **Sync Client**: Single connection (lazy initialization)

### Pipeline Usage

All multi-operation sequences use Redis pipelines:

```python
async with redis.pipeline(transaction=True) as pipe:
    pipe.hset(job_key, mapping=hash_dict)
    pipe.expire(job_key, ttl_seconds)
    pipe.zadd("jobs:all", {job.id: score})
    await pipe.execute()  # Single round-trip
```

### Lua Scripts

Atomic operations use pre-loaded Lua scripts:

- Loaded once on first use (lazy initialization)
- Executed via `EVALSHA` for efficiency
- SHA hashes logged for debugging

### Sliding Window Implementation

Rate limiting uses sorted sets for O(log N) operations:

```python
# Cleanup old entries
pipe.zremrangebyscore(key, 0, window_start)
# Count current
pipe.zcard(key)
# Add new timestamp
pipe.zadd(key, {str(now): now})
# Set TTL
pipe.expire(key, window)
```

### Batch Processing

Maintenance cleanup processes in batches to avoid blocking:

```python
# Default: 500 members per scan
await store.cleanup_orphaned_index_members(index_key, batch_size=500)
```

---

## Dependencies

### Required Packages

```
redis>=5.0              # Redis client library
```

### Internal Dependencies

```python
from src.config import settings          # Configuration
from src.jobs.interfaces import (        # Job storage interfaces
    EventStore,
    IdempotencyStore,
    JobStore,
    StorageError,
)
from src.jobs.models import (            # Job data models
    JobDocument,
    JobStatus,
    SSEEvent,
)
from src.observability.rate_limit_metrics import (  # Metrics
    record_rate_limit_check,
    record_tenant_quota_exceeded,
)
```

---

## Related Documentation

- **Job Storage Interfaces**: `src/jobs/interfaces.py`
- **Job Models**: `src/jobs/models.py`
- **Configuration**: `src/config.py`
- **Rate Limit Metrics**: `src/observability/rate_limit_metrics.py`
- **PostgreSQL Control**: `db/postgres_control/README.md`
- **Memgraph Domain**: `db/memgraph_domain/README.md`

---

## Changelog

### Version 1.0.0

- Initial release
- Complete Redis caching infrastructure
- Job store with ZSET indexes
- Sliding window rate limiting
- Agent session management
- Tool invocation caching
- Background maintenance scheduler
- Lua scripts for atomic operations
- Graceful fallback to in-memory storage

---

## License

This module is part of the Cineca Agentic Platform and follows the project's licensing terms.
