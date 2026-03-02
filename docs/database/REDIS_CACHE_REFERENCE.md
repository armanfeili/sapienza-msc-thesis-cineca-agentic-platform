# Redis Cache Reference

**Version**: 1.0  
**Status**: Production  
**Last Updated**: 2025-01-15

## Overview

The Agents API uses Redis for high-performance caching, state management, and distributed locking. This document describes all Redis keys, their purposes, data structures, and TTL configurations.

---

## Key Namespaces

All Redis keys use namespaced prefixes for organization:

| Namespace | Purpose | Example |
|-----------|---------|---------|
| `agent:session:` | Session state cache | `agent:session:abc123` |
| `agent:session:seq:` | Step sequence counters | `agent:session:seq:abc123` |
| `agent:session:lock:` | Session locks | `agent:session:lock:abc123` |
| `agent:session:cancelled:` | Cancellation flags | `agent:session:cancelled:abc123` |
| `agent:etag:sessions:` | List ETags (sessions) | `agent:etag:sessions:user123` |
| `agent:etag:steps:` | List ETags (steps) | `agent:etag:steps:session456` |
| `idempotency:` | Idempotency key cache | `idempotency:key123` |
| `ratelimit:` | Rate limit counters | `ratelimit:sessions:user123` |

---

## Session Management

### Session State Cache

**Key Format**: `agent:session:{session_id}`

**Purpose**: Cache session data to reduce database queries

**Data Structure**: Hash

**Fields**:
```
session_id     → UUID string
user_id        → Auth0 user ID
tenant_id      → Tenant identifier
manager        → Manager name
tools          → JSON array of tools
temperature    → Float (0.0-1.0)
max_steps      → Integer
status         → active|completed|cancelled|failed
metadata       → JSON object
created_at     → ISO 8601 timestamp
updated_at     → ISO 8601 timestamp
```

**TTL**: 3600 seconds (1 hour)

**Example**:
```redis
HGETALL agent:session:550e8400-e29b-41d4-a716-446655440000

1) "session_id"
2) "550e8400-e29b-41d4-a716-446655440000"
3) "user_id"
4) "auth0|123456789"
5) "manager"
6) "auto"
7) "status"
8) "active"
9) "created_at"
10) "2025-01-15T10:30:00Z"
```

**Operations**:
```python
# Set session
await redis.hset(
    f"agent:session:{session_id}",
    mapping={
        "session_id": session_id,
        "user_id": user_id,
        "status": "active",
        ...
    }
)
await redis.expire(f"agent:session:{session_id}", 3600)

# Get session
session_data = await redis.hgetall(f"agent:session:{session_id}")

# Delete session
await redis.delete(f"agent:session:{session_id}")
```

---

### Step Sequence Counter

**Key Format**: `agent:session:seq:{session_id}`

**Purpose**: Generate sequential step numbers atomically

**Data Structure**: Integer (counter)

**TTL**: No expiration (exists for session lifetime)

**Example**:
```redis
GET agent:session:seq:550e8400-e29b-41d4-a716-446655440000
# Returns: "3" (next step will be seq=4)
```

**Operations**:
```python
# Initialize sequence
await redis.set(f"agent:session:seq:{session_id}", 0)

# Get next sequence number
next_seq = await redis.incr(f"agent:session:seq:{session_id}")
# Returns: 1, 2, 3, ... (atomic increment)

# Reset sequence (not typically done)
await redis.delete(f"agent:session:seq:{session_id}")
```

**Atomicity**: `INCR` is atomic - prevents duplicate sequence numbers

---

### Session Lock

**Key Format**: `agent:session:lock:{session_id}`

**Purpose**: Distributed locking for concurrent session operations

**Data Structure**: String (lock token)

**TTL**: 10 seconds (lock timeout)

**Example**:
```redis
SET agent:session:lock:550e8400-e29b-41d4-a716-446655440000 "lock-token-123" NX EX 10
# Returns: OK (lock acquired) or nil (already locked)
```

**Operations**:
```python
import uuid

# Acquire lock
lock_token = str(uuid.uuid4())
acquired = await redis.set(
    f"agent:session:lock:{session_id}",
    lock_token,
    nx=True,  # Set only if not exists
    ex=10,    # Expire after 10 seconds
)

if acquired:
    try:
        # Perform locked operation
        await add_step(session_id, step_data)
    finally:
        # Release lock (with token verification)
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        await redis.eval(script, 1, f"agent:session:lock:{session_id}", lock_token)
```

**Lock Timeout**: Prevents deadlocks if process crashes

---

### Cancellation Flag

**Key Format**: `agent:session:cancelled:{session_id}`

**Purpose**: Fast check if session was cancelled

**Data Structure**: String (flag)

**TTL**: 3600 seconds (1 hour)

**Example**:
```redis
SET agent:session:cancelled:550e8400-e29b-41d4-a716-446655440000 "1" EX 3600
# Returns: OK

GET agent:session:cancelled:550e8400-e29b-41d4-a716-446655440000
# Returns: "1" (cancelled) or nil (not cancelled)
```

**Operations**:
```python
# Set cancellation flag
await redis.set(
    f"agent:session:cancelled:{session_id}",
    "1",
    ex=3600,
)

# Check if cancelled
is_cancelled = await redis.get(f"agent:session:cancelled:{session_id}")
if is_cancelled:
    raise HTTPException(400, "Session is cancelled")

# Clear flag (not typically done)
await redis.delete(f"agent:session:cancelled:{session_id}")
```

---

## ETag Caching

### Sessions List ETag

**Key Format**: `agent:etag:sessions:{user_id}`

**Purpose**: Cache ETag for user's session list

**Data Structure**: String (ETag hash)

**TTL**: 300 seconds (5 minutes)

**Example**:
```redis
SET agent:etag:sessions:auth0|123456789 "abc123def456" EX 300
# Returns: OK

GET agent:etag:sessions:auth0|123456789
# Returns: "abc123def456"
```

**Operations**:
```python
# Generate and store ETag
etag = generate_etag(sessions_data)  # e.g., MD5 hash
await redis.set(
    f"agent:etag:sessions:{user_id}",
    etag,
    ex=300,
)

# Get cached ETag
cached_etag = await redis.get(f"agent:etag:sessions:{user_id}")
if cached_etag == request_etag:
    # Return 304 Not Modified
    return Response(status_code=304)

# Invalidate ETag (on create/delete)
await redis.delete(f"agent:etag:sessions:{user_id}")
```

---

### Steps List ETag

**Key Format**: `agent:etag:steps:{session_id}`

**Purpose**: Cache ETag for session's step list

**Data Structure**: String (ETag hash)

**TTL**: 300 seconds (5 minutes)

**Example**:
```redis
SET agent:etag:steps:550e8400-e29b-41d4-a716-446655440000 "xyz789abc123" EX 300
# Returns: OK

GET agent:etag:steps:550e8400-e29b-41d4-a716-446655440000
# Returns: "xyz789abc123"
```

**Operations**:
```python
# Generate and store ETag
etag = generate_etag(steps_data)
await redis.set(
    f"agent:etag:steps:{session_id}",
    etag,
    ex=300,
)

# Get cached ETag
cached_etag = await redis.get(f"agent:etag:steps:{session_id}")
if cached_etag == request_etag:
    return Response(status_code=304)

# Invalidate ETag (on step creation)
await redis.delete(f"agent:etag:steps:{session_id}")
```

---

## Idempotency

### Idempotency Key Cache

**Key Format**: `idempotency:{idempotency_key}`

**Purpose**: Cache idempotency responses for 24 hours

**Data Structure**: Hash

**Fields**:
```
status         → HTTP status code (e.g., "201")
body           → JSON response body
headers        → JSON headers object
```

**TTL**: 86400 seconds (24 hours)

**Example**:
```redis
HGETALL idempotency:550e8400-e29b-41d4-a716-446655440000

1) "status"
2) "201"
3) "body"
4) "{\"session_id\":\"abc123\",\"status\":\"active\",...}"
5) "headers"
6) "{\"Location\":\"/v1/agents/sessions/abc123\"}"
```

**Operations**:
```python
# Store idempotent response
await redis.hset(
    f"idempotency:{idempotency_key}",
    mapping={
        "status": 201,
        "body": json.dumps(response_data),
        "headers": json.dumps({"Location": location_url}),
    }
)
await redis.expire(f"idempotency:{idempotency_key}", 86400)

# Retrieve cached response
cached = await redis.hgetall(f"idempotency:{idempotency_key}")
if cached:
    return Response(
        status_code=int(cached["status"]),
        content=cached["body"],
        headers={**json.loads(cached["headers"]), "Idempotency-Replayed": "true"},
    )
```

---

## Rate Limiting

### Rate Limit Counter

**Key Format**: `ratelimit:{resource}:{identifier}:{window_start}`

**Purpose**: Sliding window rate limiting

**Data Structure**: Sorted Set (ZSET)

**Members**: Timestamp of each request

**Scores**: Request timestamp (Unix time with milliseconds)

**TTL**: window_seconds + 60 (cleanup buffer)

**Example**:
```redis
ZADD ratelimit:sessions:auth0|123456789:1736687400 1736687401.123 "req1"
ZADD ratelimit:sessions:auth0|123456789:1736687400 1736687402.456 "req2"
ZADD ratelimit:sessions:auth0|123456789:1736687400 1736687403.789 "req3"

ZCOUNT ratelimit:sessions:auth0|123456789:1736687400 1736687400 1736687460
# Returns: 3 (3 requests in window)
```

**Resources**:
- `sessions` - Session creation rate limit
- `steps:{session_id}` - Step creation per session
- `runs` - Run creation rate limit
- `list:sessions` - Session list endpoint
- `list:steps:{session_id}` - Steps list per session

**Operations**:
```python
import time

# Check rate limit
current_time = time.time()
window_start = current_time - window_seconds
key = f"ratelimit:{resource}:{user_id}:{int(current_time)}"

# Remove old entries
await redis.zremrangebyscore(key, 0, window_start)

# Count requests in window
count = await redis.zcount(key, window_start, current_time)

if count >= limit:
    # Calculate retry_after
    oldest_score = await redis.zrange(key, 0, 0, withscores=True)
    retry_after = int(oldest_score[0][1] + window_seconds - current_time)
    
    raise HTTPException(
        429,
        "Rate limit exceeded",
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Window": str(window_seconds),
        }
    )

# Add current request
await redis.zadd(key, {str(uuid.uuid4()): current_time})
await redis.expire(key, window_seconds + 60)

# Calculate remaining
remaining = limit - count - 1
```

**Rate Limits**:

| Resource | Limit | Window |
|----------|-------|--------|
| Create Session | 10 | 60s |
| Create Step (per session) | 100 | 60s |
| Create Run | 20 | 60s |
| List Sessions | 100 | 60s |
| List Steps (per session) | 100 | 60s |

---

## Cache Patterns

### Read-Through Caching

```python
async def get_session(session_id: str):
    # Try cache first
    cached = await redis.hgetall(f"agent:session:{session_id}")
    if cached:
        return parse_session(cached)
    
    # Cache miss - query database
    session = await db.query(AgentSession).filter_by(id=session_id).first()
    if not session:
        return None
    
    # Populate cache
    await redis.hset(
        f"agent:session:{session_id}",
        mapping=session_to_dict(session)
    )
    await redis.expire(f"agent:session:{session_id}", 3600)
    
    return session
```

### Write-Through Caching

```python
async def update_session(session_id: str, updates: dict):
    # Update database
    await db.query(AgentSession).filter_by(id=session_id).update(updates)
    await db.commit()
    
    # Update cache
    await redis.hset(
        f"agent:session:{session_id}",
        mapping=updates
    )
```

### Cache Invalidation

```python
async def delete_session(session_id: str):
    # Delete from database
    await db.query(AgentSession).filter_by(id=session_id).delete()
    await db.commit()
    
    # Invalidate all related caches
    await redis.delete(f"agent:session:{session_id}")
    await redis.delete(f"agent:session:seq:{session_id}")
    await redis.delete(f"agent:session:cancelled:{session_id}")
    await redis.delete(f"agent:etag:steps:{session_id}")
    
    # Get user_id to invalidate session list ETag
    # (Could also store in cache or query from another source)
    await redis.delete(f"agent:etag:sessions:{user_id}")
```

---

## Monitoring and Debugging

### Check Key Existence

```bash
# Redis CLI
redis-cli

# Check if session cached
EXISTS agent:session:550e8400-e29b-41d4-a716-446655440000

# Get TTL
TTL agent:session:550e8400-e29b-41d4-a716-446655440000
# Returns: remaining seconds or -1 (no expiry) or -2 (doesn't exist)
```

### List All Keys (Development Only)

```bash
# List all agent keys (use with caution in production)
redis-cli KEYS "agent:*"

# Count keys by pattern
redis-cli EVAL "return #redis.call('keys', 'agent:session:*')" 0

# Memory usage
redis-cli MEMORY USAGE agent:session:550e8400-e29b-41d4-a716-446655440000
```

### Inspect Key Data

```bash
# Get hash contents
redis-cli HGETALL agent:session:550e8400-e29b-41d4-a716-446655440000

# Get sorted set (rate limit)
redis-cli ZRANGE ratelimit:sessions:user123:1736687400 0 -1 WITHSCORES

# Get string value
redis-cli GET agent:etag:sessions:user123
```

### Monitor Commands

```bash
# Real-time command monitoring
redis-cli MONITOR

# Watch specific key
redis-cli --csv GET agent:session:abc123

# Get statistics
redis-cli INFO stats
```

---

## Performance Tuning

### Connection Pooling

```python
from redis.asyncio import Redis, ConnectionPool

# Create connection pool
pool = ConnectionPool(
    host="localhost",
    port=6379,
    db=0,
    max_connections=50,
    decode_responses=True,
)

redis = Redis(connection_pool=pool)
```

### Pipeline Operations

```python
# Batch multiple operations
pipe = redis.pipeline()
pipe.hgetall(f"agent:session:{session_id}")
pipe.get(f"agent:etag:sessions:{user_id}")
pipe.zcount(f"ratelimit:sessions:{user_id}", window_start, current_time)
results = await pipe.execute()

session_data, etag, rate_count = results
```

### Lua Scripts (Atomic Operations)

```python
# Atomic rate limit check + increment
rate_limit_script = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local current_time = tonumber(ARGV[3])
local window_start = current_time - window

-- Remove old entries
redis.call('ZREMRANGEBYSCORE', key, 0, window_start)

-- Count current requests
local count = redis.call('ZCOUNT', key, window_start, current_time)

if count >= limit then
    return {0, count}  -- Rate limited
end

-- Add current request
redis.call('ZADD', key, current_time, tostring(current_time))
redis.call('EXPIRE', key, window + 60)

return {1, count + 1}  -- Allowed
"""

result = await redis.eval(
    rate_limit_script,
    1,
    key,
    limit,
    window_seconds,
    time.time()
)
allowed, count = result
```

---

## Cache Eviction Policy

**Redis Configuration**:
```
maxmemory 2gb
maxmemory-policy allkeys-lru
```

**LRU Eviction**: Least Recently Used keys evicted when memory limit reached

**Impact**:
- Session cache misses → Query database
- ETag cache misses → Regenerate ETag (no 304 response)
- Rate limit misses → Reset counter (could allow extra requests)

**Monitoring**:
```bash
# Check memory usage
redis-cli INFO memory

# Check eviction stats
redis-cli INFO stats | grep evicted
```

---

## Backup and Recovery

### Session Data

**Primary Storage**: PostgreSQL (source of truth)

**Cache**: Redis (ephemeral)

**Recovery**: Rebuild from database on cache miss

### Idempotency Keys

**Primary Storage**: PostgreSQL `idempotency_keys` table

**Cache**: Redis (performance optimization)

**Recovery**: Query database if Redis cache miss

---

## Best Practices

### 1. Always Set TTL

```python
# Good: Set expiration
await redis.set(key, value, ex=3600)

# Bad: No expiration (memory leak)
await redis.set(key, value)
```

### 2. Use Namespaced Keys

```python
# Good: Clear namespace
key = f"agent:session:{session_id}"

# Bad: Generic key (collision risk)
key = session_id
```

### 3. Handle Cache Misses Gracefully

```python
# Good: Fallback to database
cached = await redis.get(key)
if cached:
    return parse_cached(cached)
else:
    return query_database()

# Bad: Assume cache always present
return parse_cached(await redis.get(key))  # May be None!
```

### 4. Use Pipelines for Multiple Operations

```python
# Good: Batch operations
pipe = redis.pipeline()
pipe.get(key1)
pipe.get(key2)
pipe.get(key3)
results = await pipe.execute()

# Avoid: Multiple round trips
result1 = await redis.get(key1)
result2 = await redis.get(key2)
result3 = await redis.get(key3)
```

### 5. Clean Up Related Keys

```python
# Good: Delete all related keys
await redis.delete(
    f"agent:session:{session_id}",
    f"agent:session:seq:{session_id}",
    f"agent:session:lock:{session_id}",
    f"agent:session:cancelled:{session_id}",
    f"agent:etag:steps:{session_id}",
)

# Bad: Orphaned keys
await redis.delete(f"agent:session:{session_id}")
# Other keys remain in Redis forever
```

---

## Troubleshooting

### Cache Miss Rate Too High

**Symptoms**: Many database queries, slow responses

**Causes**:
- TTL too short
- Memory eviction (maxmemory reached)
- High traffic invalidating caches

**Solutions**:
- Increase TTL for stable data
- Increase Redis memory (`maxmemory`)
- Use read replicas for high traffic

### Rate Limiting Not Working

**Symptoms**: Users bypassing rate limits

**Causes**:
- ZSET cleanup not running
- Clock skew between servers
- Key expiration too short

**Solutions**:
- Ensure ZREMRANGEBYSCORE runs before count
- Use NTP for time synchronization
- Set TTL > window_seconds

### Lock Timeouts

**Symptoms**: Operations failing with "lock timeout"

**Causes**:
- Lock TTL too short (10s)
- Long-running operations inside lock
- Deadlocks (rare with TTL)

**Solutions**:
- Increase lock TTL for slow operations
- Minimize work inside locked section
- Use lock renewal for very long operations

---

## Summary

✅ **7 key namespaces** for different purposes  
✅ **TTL configured** for all cache keys  
✅ **Atomic operations** with INCR, Lua scripts  
✅ **Distributed locking** prevents race conditions  
✅ **ETag caching** reduces bandwidth  
✅ **Rate limiting** with sliding window algorithm  
✅ **PostgreSQL fallback** for cache misses  

**Next Steps**:
- Review [Agents API Guide](./AGENTS_API_GUIDE.md)
- Review [Rate Limiting Documentation](./RATE_LIMITING_IMPLEMENTATION.md)
- Monitor Redis with `redis-cli INFO`
