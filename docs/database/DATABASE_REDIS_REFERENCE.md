# Cineca Agentic Platform - Redis Database Reference

**Last Updated:** 2025-10-24  
**Purpose:** Comprehensive reference for Redis cache and storage implementation

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Modules](#core-modules)
   - [Synchronous Client](#synchronous-client)
   - [Asynchronous Client](#asynchronous-client)
   - [Job Store](#job-store)
   - [Rate Limiting](#rate-limiting)
   - [Lua Scripts](#lua-scripts)
4. [Data Structures](#data-structures)
5. [Usage Patterns](#usage-patterns)
6. [Best Practices](#best-practices)

---

## Overview

Redis is used in the Cineca Agentic Platform as a high-performance in-memory data store for:

- **Job Storage**: Background job tracking with TTL-based auto-expiry
- **Rate Limiting**: Sliding window rate limiters per user/action
- **Caching**: ETag-based HTTP caching and idempotency keys
- **Session Storage**: Agent conversation sessions and event streams
- **Distributed Locks**: Coordination across multiple workers

**Technology Stack:**

- **Database:** Redis 7.x (in-memory key-value store)
- **Python Client:** redis-py >= 5.0 (sync + async)
- **Data Structures:** STRING, HASH, ZSET, LIST
- **Features:** TTL expiry, Lua scripts, pipelining, transactions

**Use Cases:**

- Job queue management (jobs:all, jobs:owner:{user})
- Idempotency tracking (idem:{owner}:{type}:{key})
- SSE event streaming (job:{id}:events LIST)
- Rate limit buckets (ratelimit:{action}:{user} ZSET)
- Cache storage (cache:{key}, provider cache)

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Redis Container (Port 6379)              │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │   In-Memory Data Structures                           │ │
│  │                                                         │ │
│  │   • HASH:  job:{id} → {status, owner, result, ...}   │ │
│  │   • ZSET:  jobs:all → {job_id: created_at_ms}        │ │
│  │   • LIST:  job:{id}:events → [SSE events]            │ │
│  │   • STRING: idem:{key} → job_id                       │ │
│  │   • ZSET:  ratelimit:{action}:{user} → timestamps    │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         ↑                              ↑
         │ redis-py (sync)              │ redis.asyncio
         │                              │
    ┌────────────┐              ┌──────────────┐
    │   Sync     │              │    Async     │
    │   Client   │              │    Client    │
    └────────────┘              └──────────────┘
         ↑                              ↑
         │                              │
  ┌──────┴──────┐              ┌────────┴────────┐
  │ Rate Limit  │              │   Job Store     │
  │ Cache Ops   │              │   Event Stream  │
  │ Idempotency │              │   Async Ops     │
  └─────────────┘              └─────────────────┘
```

### Data Flow

1. **Configuration** → Settings provide REDIS_URL
2. **Client Init** → Lazy connection on first use (sync or async)
3. **Storage Operations** → Set/get with TTL, atomic operations via Lua
4. **Expiry** → Automatic TTL-based cleanup (no manual GC needed)
5. **Health Checks** → PING commands for liveness probes

---

## Core Modules

### Synchronous Client

**File:** `db/redis_cache/client.py`  
**Lines:** 280  
**Purpose:** Synchronous Redis client for blocking operations

#### Features

- **Lazy Initialization**: Client created on first use
- **Health Checks**: `redis_available()`, `redis_health()`
- **JSON Helpers**: `cache_set_json()`, `cache_get_json()`
- **Idempotency**: `idem_set()`, `idem_get()` with in-memory fallback
- **Rate Limiting**: `incr_with_ttl()`, `ttl()` primitives

#### Client Factory

```python
def get_redis() -> redis.Redis:
    """
    Get or create the global sync Redis client.
    
    Features:
    - Decode responses to str (not bytes)
    - Connection pooling
    - Lazy initialization
    
    Raises:
        RuntimeError: If Redis not installed or REDIS_URL not set
    
    Usage:
        r = get_redis()
        r.set("key", "value", ex=3600)
        value = r.get("key")
    """
```

#### Cache Helpers

```python
def cache_set(key: str, value: str, ex: Optional[int] = None) -> bool:
    """Set string value with optional TTL."""
    r = get_redis()
    return bool(r.set(name=key, value=value, ex=ex))

def cache_get(key: str) -> Optional[str]:
    """Get string value or None if missing."""
    r = get_redis()
    return r.get(name=key)

def cache_delete(key: str) -> int:
    """Delete key, returns number of keys removed (0/1)."""
    r = get_redis()
    return int(r.delete(key))
```

#### JSON Helpers

```python
def cache_set_json(key: str, obj: Any, ex: Optional[int] = None) -> bool:
    """
    Serialize object as JSON and store.
    
    Features:
    - Compact JSON (no whitespace)
    - Sorted keys (deterministic)
    - UTF-8 encoding
    """
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return cache_set(key, data, ex=ex)

def cache_get_json(key: str, default: Any = None) -> Any:
    """
    Fetch and parse JSON value.
    
    Returns default if key missing or JSON invalid.
    """
    raw = cache_get(key)
    if raw is None:
        return default
    
    try:
        return json.loads(raw)
    except:
        return default
```

#### Idempotency Helpers

```python
_LOCAL_IDEMPOTENCY: Dict[str, tuple[str, Optional[float]]] = {}

def idem_set(key: str, obj: Any, ex: Optional[int] = None) -> bool:
    """
    Set idempotency value with in-memory fallback.
    
    Primary: Redis with TTL
    Fallback: In-memory dict with expiry timestamp
    """
    # Try Redis first
    try:
        ok = cache_set_json(key, obj, ex=ex)
        if ok:
            return True
    except:
        pass
    
    # Fallback to in-memory
    data = json.dumps(obj, sort_keys=True)
    expires_at = time.time() + ex if ex else None
    _LOCAL_IDEMPOTENCY[key] = (data, expires_at)
    return True

def idem_get(key: str, default: Any = None) -> Any:
    """
    Get idempotency value with in-memory fallback.
    
    Checks Redis first, then in-memory store.
    """
    # Try Redis
    try:
        val = cache_get_json(key)
        if val is not None:
            return val
    except:
        pass
    
    # Check in-memory fallback
    entry = _LOCAL_IDEMPOTENCY.get(key)
    if not entry:
        return default
    
    data_str, expires_at = entry
    
    # Check expiry
    if expires_at is not None and time.time() > expires_at:
        _LOCAL_IDEMPOTENCY.pop(key, None)
        return default
    
    try:
        return json.loads(data_str)
    except:
        return default
```

#### Rate Limit Primitives

```python
def incr_with_ttl(key: str, ttl_seconds: int) -> int:
    """
    Increment counter and ensure TTL.
    
    Atomic operation using pipeline:
    1. INCR key
    2. EXPIRE key ttl_seconds
    
    Returns:
        Counter value after increment, or -1 if Redis unavailable
    """
    r = get_redis()
    
    with r.pipeline() as pipe:
        pipe.incr(key)
        pipe.expire(key, ttl_seconds)
        results = pipe.execute()
    
    return int(results[0])

def ttl(key: str) -> int:
    """
    Get key TTL in seconds.
    
    Returns:
        -2: Key does not exist
        -1: No TTL set (key persists forever)
        >0: Remaining seconds
        -999: Redis unavailable
    """
    r = get_redis()
    return int(r.ttl(key))
```

#### Health Checks

```python
def redis_available() -> bool:
    """Quick check if Redis is reachable."""
    client = _build_client()
    if client is None:
        return False
    
    try:
        return bool(client.ping())
    except:
        return False

def redis_health() -> Dict[str, Any]:
    """
    Detailed health check for monitoring.
    
    Returns:
        {
            "ok": bool,
            "url": str,
            "error": str (if not ok)
        }
    """
    url = settings.REDIS_URL or ""
    info = {"ok": False, "url": url}
    
    if not url or redis is None:
        info["error"] = "redis package missing or REDIS_URL unset"
        return info
    
    try:
        client = get_redis()
        info["ok"] = bool(client.ping())
    except Exception as exc:
        info["error"] = str(exc)
    
    return info
```

---

### Asynchronous Client

**File:** `db/redis_cache/async_client.py`  
**Lines:** 180  
**Purpose:** Async Redis client for non-blocking I/O operations

#### Features

- **Async/Await Support**: Fully async API for FastAPI endpoints
- **Connection Pooling**: Shared pool across application
- **Graceful Shutdown**: `close_async_redis()` for cleanup
- **Health Checks**: `async_redis_health()` with latency measurement
- **Lazy Init**: Client created on first await

#### Client Factory

```python
_async_client: Optional[Redis] = None
_async_pool: Optional[ConnectionPool] = None

async def get_async_redis() -> Redis:
    """
    Get or create the global async Redis client.
    
    Features:
    - Connection pooling (max 10 connections)
    - Socket timeout: 5s
    - Decode responses to str
    - Auto-retry on timeout
    
    Raises:
        RuntimeError: If redis.asyncio not available or REDIS_URL not set
    """
    global _async_client, _async_pool
    
    if _async_client is not None:
        return _async_client
    
    if Redis is None:
        raise RuntimeError("redis.asyncio not available")
    
    url = settings.REDIS_URL.strip()
    if not url:
        raise RuntimeError("REDIS_URL not configured")
    
    # Create connection pool
    _async_pool = ConnectionPool.from_url(
        url,
        decode_responses=True,
        max_connections=10,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        retry_on_timeout=True,
    )
    
    _async_client = Redis(connection_pool=_async_pool)
    
    # Test connection
    await _async_client.ping()
    logger.info("Async Redis client initialized", extra={"url": url})
    
    return _async_client
```

#### Graceful Shutdown

```python
async def close_async_redis() -> None:
    """
    Close async Redis client and connection pool.
    
    Call during application shutdown (lifespan event).
    """
    global _async_client, _async_pool
    
    if _async_client is not None:
        try:
            await _async_client.close()
            logger.info("Async Redis client closed")
        except Exception as exc:
            logger.warning(f"Error closing async Redis: {exc}")
        finally:
            _async_client = None
    
    if _async_pool is not None:
        try:
            await _async_pool.disconnect()
            logger.info("Async Redis pool disconnected")
        except Exception as exc:
            logger.warning(f"Error disconnecting pool: {exc}")
        finally:
            _async_pool = None
```

#### Health Checks

```python
async def async_redis_health() -> Dict[str, Any]:
    """
    Check async Redis health with latency measurement.
    
    Returns:
        {
            "ok": bool,
            "url": str,
            "latency_ms": float,
            "error": str (if not ok)
        }
    """
    import time
    
    url = settings.REDIS_URL.strip()
    info = {"ok": False, "url": url}
    
    if not url or Redis is None:
        info["error"] = "redis.asyncio not available or REDIS_URL not set"
        return info
    
    try:
        start = time.perf_counter()
        client = await get_async_redis()
        pong = await client.ping()
        latency_ms = (time.perf_counter() - start) * 1000
        
        info["ok"] = bool(pong)
        info["latency_ms"] = round(latency_ms, 2)
    except Exception as exc:
        info["error"] = str(exc)
    
    return info

async def async_redis_available() -> bool:
    """Quick availability check."""
    try:
        client = await get_async_redis()
        return await client.ping()
    except:
        return False
```

---

### Job Store

**File:** `db/redis_cache/job_store.py`  
**Lines:** 850  
**Purpose:** Redis-backed job storage with TTL and indexing

#### Architecture

**Key Schema:**

```
job:{id}                          → HASH (job document)
jobs:all                          → ZSET (global index, score=created_at_ms)
jobs:owner:{owner}                → ZSET (per-user index)
jobs:status:{status}              → ZSET (status index)
job:{id}:events                   → LIST (SSE events, ring buffer)
job:{id}:event_seq                → COUNTER (monotonic event IDs)
idem:{owner}:{tenant}:{type}:{hash}:{key} → STRING (idempotency, 24h TTL)
```

#### RedisJobStore Class

**Create Job:**

```python
async def create(self, job: JobDocument, ttl_seconds: int) -> None:
    """
    Store job in Redis with TTL and indexes.
    
    Atomic pipeline:
    1. HSET job:{id} (job fields)
    2. EXPIRE job:{id} ttl_seconds
    3. ZADD jobs:all {job_id: created_at_ms}
    4. ZADD jobs:owner:{owner} {job_id: created_at_ms}
    5. ZADD jobs:status:{status} {job_id: created_at_ms}
    """
    redis = await get_async_redis()
    job_key = f"job:{job.id}"
    hash_dict = job.to_hash_dict()
    score = int(job.created_at.timestamp() * 1000)
    
    async with redis.pipeline(transaction=True) as pipe:
        pipe.hset(job_key, mapping=hash_dict)
        pipe.expire(job_key, ttl_seconds)
        pipe.zadd("jobs:all", {job.id: score})
        pipe.zadd(f"jobs:owner:{job.owner}", {job.id: score})
        pipe.zadd(f"jobs:status:{job.status.value}", {job.id: score})
        await pipe.execute()
```

**Get Job:**

```python
async def get(self, job_id: str) -> Optional[JobDocument]:
    """Retrieve job from Redis HASH."""
    redis = await get_async_redis()
    job_key = f"job:{job_id}"
    
    hash_data = await redis.hgetall(job_key)
    
    if not hash_data:
        return None
    
    # Convert bytes to str
    hash_dict = {
        k.decode("utf-8") if isinstance(k, bytes) else k:
        v.decode("utf-8") if isinstance(v, bytes) else v
        for k, v in hash_data.items()
    }
    
    return JobDocument.from_hash_dict(hash_dict)
```

**Update Status:**

```python
async def update_status(
    self,
    job_id: str,
    status: JobStatus,
    result: Optional[dict] = None,
    error: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
) -> bool:
    """
    Atomically update job status.
    
    Steps:
    1. Get current job (to know old status)
    2. Update HASH fields
    3. Move ZSET membership from old status to new status
    4. Optionally extend TTL for terminal states
    """
    redis = await get_async_redis()
    job_key = f"job:{job_id}"
    
    current_job = await self.get(job_id)
    if not current_job:
        return False
    
    old_status = current_job.status
    updated_at = datetime.utcnow().isoformat()
    
    updates = {
        "status": status.value,
        "updated_at": updated_at,
    }
    
    if result is not None:
        updates["result"] = json.dumps(result)
    
    if error is not None:
        updates["error"] = error
    
    # Update HASH
    async with redis.pipeline(transaction=True) as pipe:
        pipe.hset(job_key, mapping=updates)
        
        # Get score from old index
        pipe.zscore(f"jobs:status:{old_status.value}", job_id)
        
        # Remove from old index
        pipe.zrem(f"jobs:status:{old_status.value}", job_id)
        
        results = await pipe.execute()
    
    # Add to new index with same score
    if old_status != status:
        score = results[-2]
        if score is not None:
            new_status_key = f"jobs:status:{status.value}"
            await redis.zadd(new_status_key, {job_id: score})
            
            if ttl_seconds:
                await redis.expire(new_status_key, ttl_seconds)
    
    # Extend TTL for terminal states
    if status.is_terminal and ttl_seconds:
        await redis.expire(job_key, ttl_seconds)
    
    return True
```

**List Jobs:**

```python
async def list_by_owner(
    self,
    owner: str,
    status: Optional[JobStatus] = None,
    offset: int = 0,
    limit: int = 25,
) -> Tuple[List[JobDocument], int]:
    """
    List jobs by owner with optional status filter.
    
    Uses ZSET intersection for filtering:
    - jobs:owner:{owner} ∩ jobs:status:{status}
    
    Returns newest first (ZREVRANGE).
    """
    redis = await get_async_redis()
    
    owner_key = f"jobs:owner:{owner}"
    
    if status:
        # Intersect owner + status indexes
        status_key = f"jobs:status:{status.value}"
        temp_key = f"jobs:temp:{owner}:{status.value}:{int(time.time() * 1000)}"
        
        await redis.zinterstore(temp_key, [owner_key, status_key])
        await redis.expire(temp_key, 60)
        
        source_key = temp_key
    else:
        source_key = owner_key
    
    # Get total count
    total = await redis.zcard(source_key)
    
    # Get page (ZREVRANGE for newest first)
    job_ids = await redis.zrevrange(source_key, offset, offset + limit - 1)
    
    # Fetch job documents
    jobs = []
    for job_id_bytes in job_ids:
        job_id = job_id_bytes.decode("utf-8") if isinstance(job_id_bytes, bytes) else job_id_bytes
        job = await self.get(job_id)
        if job:
            jobs.append(job)
    
    # Cleanup temp key
    if status:
        await redis.delete(temp_key)
    
    return jobs, total
```

**Delete Job:**

```python
async def delete(self, job_id: str) -> bool:
    """
    Delete job and all indexes.
    
    Removes:
    - job:{id} HASH
    - Entries from all ZSET indexes
    - job:{id}:events LIST
    - job:{id}:event_seq COUNTER
    """
    redis = await get_async_redis()
    job_key = f"job:{job_id}"
    
    job = await self.get(job_id)
    if not job:
        return False
    
    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(job_key)
        pipe.zrem("jobs:all", job_id)
        pipe.zrem(f"jobs:owner:{job.owner}", job_id)
        pipe.zrem(f"jobs:status:{job.status.value}", job_id)
        pipe.delete(f"job:{job_id}:events")
        pipe.delete(f"job:{job_id}:event_seq")
        await pipe.execute()
    
    return True
```

#### RedisEventStore Class

**Append Event:**

```python
async def append(self, job_id: str, event: SSEEvent, ring_size: int) -> None:
    """
    Append event to ring buffer.
    
    Uses LPUSH + LTRIM to maintain FIFO:
    - LPUSH job:{id}:events event_json (prepend)
    - LTRIM job:{id}:events 0 ring_size-1 (keep newest N)
    - EXPIRE job:{id}:events ttl
    """
    redis = await get_async_redis()
    events_key = f"job:{job_id}:events"
    event_json = event.to_storage_json()
    
    async with redis.pipeline(transaction=True) as pipe:
        pipe.lpush(events_key, event_json)
        pipe.ltrim(events_key, 0, ring_size - 1)
        pipe.expire(events_key, self._ttl_seconds)
        await pipe.execute()
```

**Get Next Event ID:**

```python
async def get_next_event_id(self, job_id: str) -> int:
    """
    Atomic counter increment.
    
    Uses INCR on job:{id}:event_seq.
    """
    redis = await get_async_redis()
    seq_key = f"job:{job_id}:event_seq"
    
    event_id = await redis.incr(seq_key)
    
    # Set TTL on first event
    if event_id == 1:
        await redis.expire(seq_key, self._ttl_seconds)
    
    return event_id
```

**Replay Events:**

```python
async def replay_from(self, job_id: str, last_event_id: int) -> List[SSEEvent]:
    """
    Replay events after last_event_id.
    
    Returns events with event_id > last_event_id in chronological order.
    """
    redis = await get_async_redis()
    events_key = f"job:{job_id}:events"
    
    # Get all events (LRANGE 0 -1)
    event_jsons = await redis.lrange(events_key, 0, -1)
    
    events = []
    for event_json_bytes in reversed(event_jsons):  # Chronological order
        event_json = event_json_bytes.decode("utf-8") if isinstance(event_json_bytes, bytes) else event_json_bytes
        event_dict = json.loads(event_json)
        
        event = SSEEvent(
            event_id=event_dict["event_id"],
            event_type=event_dict["event_type"],
            data=event_dict["data"],
        )
        
        if event.event_id > last_event_id:
            events.append(event)
    
    events.sort(key=lambda e: e.event_id)
    return events
```

---

### Rate Limiting

**File:** `db/redis_cache/rate_limit.py`  
**Lines:** 320  
**Purpose:** Sliding window rate limiting using Redis sorted sets

#### Algorithm

**Sliding Window:**

1. Use ZSET with timestamps as scores
2. Remove entries outside window: `ZREMRANGEBYSCORE key 0 (now - window)`
3. Count remaining entries: `ZCARD key`
4. If under limit, add current timestamp: `ZADD key {now: now}`
5. Set TTL on key: `EXPIRE key window`

#### Functions

**Check Rate Limit:**

```python
async def check_rate_limit(
    key: str,
    limit: int,
    window: int,
) -> Tuple[bool, int, int]:
    """
    Check if rate limit is exceeded.
    
    Args:
        key: Redis key (e.g., "ratelimit:sessions:user123")
        limit: Max requests in window
        window: Window size in seconds
    
    Returns:
        (allowed, remaining, retry_after)
        - allowed: True if request allowed
        - remaining: Requests remaining
        - retry_after: Seconds to wait (0 if allowed)
    """
    redis = await get_async_redis()
    now = time.time()
    window_start = now - window
    
    pipe = redis.pipeline()
    
    # Remove old entries
    pipe.zremrangebyscore(key, 0, window_start)
    
    # Count current entries
    pipe.zcard(key)
    
    # Get oldest entry for retry calculation
    pipe.zrange(key, 0, 0, withscores=True)
    
    results = await pipe.execute()
    current_count = results[1]
    oldest_entries = results[2]
    
    if current_count >= limit:
        # Rate limit exceeded
        if oldest_entries:
            oldest_timestamp = oldest_entries[0][1]
            retry_after = int(oldest_timestamp + window - now) + 1
        else:
            retry_after = window
        
        return False, 0, retry_after
    
    # Add current request
    await redis.zadd(key, {str(now): now})
    await redis.expire(key, window)
    
    remaining = limit - current_count - 1
    return True, remaining, 0
```

**Rate Limit Configuration:**

```python
RATE_LIMIT_MODE = os.environ.get("RATE_LIMIT_MODE", "prod").lower()

_RATE_LIMIT_CONFIGS = {
    "prod": {
        "sessions:create": {"limit": 10, "window": 60},
        "steps:create": {"limit": 100, "window": 60},
        "runs:create": {"limit": 20, "window": 60},
    },
    "test": {
        "sessions:create": {"limit": 10000, "window": 60},
        "steps:create": {"limit": 10000, "window": 60},
        "runs:create": {"limit": 10000, "window": 60},
    }
}

def get_rate_limit_config(action: str) -> Tuple[int, int]:
    """Get (limit, window) for action."""
    rate_limits = _RATE_LIMIT_CONFIGS[RATE_LIMIT_MODE]
    config = rate_limits[action]
    return config["limit"], config["window"]
```

**Key Generation:**

```python
def make_rate_limit_key(
    action: str,
    user_id: str,
    resource_id: Optional[str] = None
) -> str:
    """
    Create Redis key for rate limiting.
    
    Examples:
        make_rate_limit_key("sessions:create", "user123")
        → "ratelimit:sessions:create:user123"
        
        make_rate_limit_key("steps:create", "user123", "session456")
        → "ratelimit:steps:create:user123:session456"
    """
    if resource_id:
        return f"ratelimit:{action}:{user_id}:{resource_id}"
    return f"ratelimit:{action}:{user_id}"
```

---

### Lua Scripts

**File:** `db/redis_cache/lua_scripts.py`  
**Lines:** 250  
**Purpose:** Atomic operations using Lua scripts

#### Cancel Job Script

```lua
-- KEYS[1] = job:{id}
-- ARGV[1] = timestamp
-- ARGV[2] = result JSON

local job = redis.call('HGETALL', KEYS[1])

if #job == 0 then
    return 'not_found'
end

-- Convert flat array to dict
local job_dict = {}
for i = 1, #job, 2 do
    job_dict[job[i]] = job[i + 1]
end

local status = job_dict['status']

-- Check if terminal
if status == 'finished' or status == 'failed' or status == 'cancelled' then
    return 'already_terminal'
end

-- Update status to cancelled
redis.call('HSET', KEYS[1], 'status', 'cancelled', 'updated_at', ARGV[1], 'result', ARGV[2])

return 'cancelled'
```

#### Cleanup Orphans Script

```lua
-- KEYS[1] = index key (ZSET)
-- ARGV[1] = batch_size

local members = redis.call('ZRANGE', KEYS[1], 0, ARGV[1] - 1)
local removed = 0

for i, member in ipairs(members) do
    local job_key = 'job:' .. member
    local exists = redis.call('EXISTS', job_key)
    
    if exists == 0 then
        redis.call('ZREM', KEYS[1], member)
        removed = removed + 1
    end
end

return removed
```

---

## Data Structures

### Job HASH

```
job:550e8400-e29b-41d4-a716-446655440000 → HASH
  id: "550e8400-e29b-41d4-a716-446655440000"
  type: "demo"
  status: "running"
  owner: "user@example.com"
  tenant_id: "tenant_123"
  created_at: "2025-10-24T12:00:00Z"
  updated_at: "2025-10-24T12:05:00Z"
  result: "{...}" (JSON)
  error: null
```

### Job Indexes (ZSET)

```
jobs:all → ZSET (score = created_at epoch ms)
  550e8400-e29b-41d4-a716-446655440000: 1729771200000
  660e8400-e29b-41d4-a716-446655440001: 1729771260000

jobs:owner:user@example.com → ZSET
  550e8400-e29b-41d4-a716-446655440000: 1729771200000

jobs:status:running → ZSET
  550e8400-e29b-41d4-a716-446655440000: 1729771200000
```

### Event LIST

```
job:550e8400-...:events → LIST
  [0]: {"event_id": 3, "event_type": "progress", "data": {...}}
  [1]: {"event_id": 2, "event_type": "status", "data": {...}}
  [2]: {"event_id": 1, "event_type": "created", "data": {...}}
```

### Idempotency STRING

```
idem:user@example.com:tenant123:demo:a1b2c3:key123 → STRING
  "550e8400-e29b-41d4-a716-446655440000"
```

### Rate Limit ZSET

```
ratelimit:sessions:create:user123 → ZSET
  1729771200.123: 1729771200.123
  1729771205.456: 1729771205.456
  1729771210.789: 1729771210.789
```

---

## Usage Patterns

### Pattern 1: Job Creation with Idempotency

```python
from db.redis_cache.job_store import RedisJobStore, RedisIdempotencyStore

store = RedisJobStore()
idem_store = RedisIdempotencyStore()

# Generate idempotency key
idem_key = f"idem:{owner}:{tenant}:{job_type}:{hash}:{key}"

# Check for existing job
existing_job_id = await idem_store.get_job_id(idem_key)
if existing_job_id:
    job = await store.get(existing_job_id)
    return job  # Return cached result

# Create new job
job = JobDocument(...)
await store.create(job, ttl_seconds=7*86400)

# Store idempotency key
await idem_store.store(idem_key, job.id, ttl_seconds=24*3600)

return job
```

### Pattern 2: Rate Limiting

```python
from db.redis_cache.rate_limit import check_rate_limit, make_rate_limit_key

key = make_rate_limit_key("sessions:create", user_id)
limit, window = get_rate_limit_config("sessions:create")

allowed, remaining, retry_after = await check_rate_limit(key, limit, window)

if not allowed:
    raise RateLimitExceeded(limit, window, retry_after)

# Proceed with operation
```

### Pattern 3: SSE Event Streaming

```python
from db.redis_cache.job_store import RedisEventStore

event_store = RedisEventStore(ring_size=100)

# Append event
event_id = await event_store.get_next_event_id(job_id)
event = SSEEvent(
    event_id=event_id,
    event_type="progress",
    data={"percent": 50}
)
await event_store.append(job_id, event, ring_size=100)

# Replay events from last_event_id
events = await event_store.replay_from(job_id, last_event_id=5)
for event in events:
    yield f"id: {event.event_id}\n"
    yield f"event: {event.event_type}\n"
    yield f"data: {json.dumps(event.data)}\n\n"
```

---

## Best Practices

### 1. Always Set TTL

```python
# Good: Expire after 7 days
await redis.setex("job:123", 7*86400, value)

# Bad: Key persists forever
await redis.set("job:123", value)
```

### 2. Use Pipelining

```python
# Good: Batch operations
async with redis.pipeline(transaction=True) as pipe:
    pipe.set("key1", "val1")
    pipe.set("key2", "val2")
    pipe.incr("counter")
    await pipe.execute()

# Bad: Multiple round trips
await redis.set("key1", "val1")
await redis.set("key2", "val2")
await redis.incr("counter")
```

### 3. Handle Graceful Degradation

```python
try:
    redis = await get_async_redis()
    value = await redis.get("key")
except:
    # Fallback to in-memory or skip cache
    value = None
```

### 4. Monitor Memory Usage

```python
info = await redis.info("memory")
used_memory_mb = info["used_memory"] / 1024 / 1024
print(f"Redis memory: {used_memory_mb:.2f} MB")
```

---

**Document Version:** 1.0  
**Last Updated:** 2025-10-24  
**Maintainer:** Cineca Agentic Platform Team
