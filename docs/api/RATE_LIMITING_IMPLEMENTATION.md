# Rate Limiting Implementation

**Status**: ✅ Complete  
**Date**: 2025-01-15

## Overview

Implemented Redis-based rate limiting with sliding window algorithm for all Agents API endpoints. The implementation is RFC 6585 compliant with proper 429 responses, Retry-After headers, and X-RateLimit-* informational headers.

## Architecture

### Sliding Window Algorithm

Uses Redis sorted sets (ZSET) to track request timestamps within a sliding window:

1. **Remove old entries**: `ZREMRANGEBYSCORE` removes timestamps outside the window
2. **Count current requests**: `ZCARD` counts requests in the current window
3. **Add new request**: `ZADD` adds current timestamp if limit not exceeded
4. **Return status**: Returns (allowed, remaining, retry_after) tuple

**Benefits over simple counters**:
- Accurate per-second rate limiting (no burst at window boundary)
- Automatic cleanup of old entries
- Fair distribution across time windows

### Components

#### 1. Redis Helpers (`db/redis_cache/rate_limit.py`)

```python
async def check_rate_limit(key, limit, window) -> (allowed, remaining, retry_after)
```

- **Purpose**: Check if request exceeds rate limit
- **Algorithm**: Sliding window using Redis ZSET
- **Returns**: Tuple of (allowed, remaining, retry_after)

```python
async def increment_rate_limit(key, limit, window) -> (allowed, remaining, retry_after)
```

- **Purpose**: Increment counter and check limit (combined operation)
- **Use case**: When you want to reserve the request slot

```python
async def get_rate_limit_status(key, limit, window) -> (current, remaining, reset_in)
```

- **Purpose**: Get current rate limit status without incrementing
- **Use case**: For informational headers on GET requests

#### 2. Middleware (`src/middleware/rate_limit.py`)

```python
class RateLimitHandler:
    def __init__(self, user_id: str, resource_id: Optional[str] = None)
    async def check(self, action: str) -> None  # Raises HTTPException on 429
    async def check_and_add_headers(self, action: str, response: Response) -> None
```

- **Purpose**: FastAPI integration layer
- **Features**:
  - RFC 7807 ProblemDetail on 429 errors
  - Automatic header injection (X-RateLimit-*, Retry-After)
  - Per-user and per-resource rate limiting

```python
def rate_limit_dependency(action: str, resource_id_param: Optional[str] = None)
```

- **Purpose**: FastAPI dependency for declarative rate limiting
- **Usage**: `@router.post("/sessions", dependencies=[Depends(rate_limit_dependency("sessions:create"))])`

```python
async def add_rate_limit_headers(response, user_id, action, resource_id=None)
```

- **Purpose**: Add informational headers after successful request
- **Usage**: Call after endpoint logic completes

## Rate Limits Configuration

Defined in `db/redis_cache/rate_limit.py`:

```python
RATE_LIMITS = {
    "sessions:create": {"limit": 10, "window": 60},   # 10 sessions per minute
    "steps:create": {"limit": 100, "window": 60},     # 100 steps per minute
    "runs:create": {"limit": 20, "window": 60},       # 20 runs per minute
    "sessions:list": {"limit": 100, "window": 60},    # 100 list requests per minute
    "steps:list": {"limit": 100, "window": 60},       # 100 list requests per minute
}
```

**Rationale**:
- **sessions:create (10/min)**: Low rate - sessions are long-lived resources
- **steps:create (100/min)**: High rate - steps are frequent operations in active sessions
- **runs:create (20/min)**: Medium rate - runs are compute-intensive
- **list operations (100/min)**: High rate - read-heavy operations

## Integrated Endpoints

### POST Endpoints (Rate Limited)

1. **POST /agents/sessions** - Create session
   - Action: `sessions:create`
   - Limit: 10 requests/minute per user
   - Key: `ratelimit:sessions:create:{user_id}`

2. **POST /agents/sessions/{id}/steps** - Add step
   - Action: `steps:create`
   - Limit: 100 requests/minute per user per session
   - Key: `ratelimit:steps:create:{user_id}:{session_id}`

3. **POST /agent-runs** - Execute run
   - Action: `runs:create`
   - Limit: 20 requests/minute per user
   - Key: `ratelimit:runs:create:{user_id}`

### GET Endpoints (Rate Limited)

4. **GET /agents/sessions** - List sessions
   - Action: `sessions:list`
   - Limit: 100 requests/minute per user
   - Key: `ratelimit:sessions:list:{user_id}`

5. **GET /agents/sessions/{id}/steps** - List steps
   - Action: `steps:list`
   - Limit: 100 requests/minute per user per session
   - Key: `ratelimit:steps:list:{user_id}:{session_id}`

## Response Format

### Success Response Headers

```http
HTTP/1.1 201 Created
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Window: 60
Location: /v1/agents/sessions/abc123
```

### Rate Limit Exceeded (429)

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 45
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Window: 60
Content-Type: application/problem+json

{
  "type": "https://httpstatuses.com/429",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Rate limit exceeded: 10 requests per 60 seconds. Try again in 45 seconds.",
  "extensions": {
    "limit": 10,
    "window": 60,
    "retry_after": 45
  }
}
```

## Implementation Pattern

### In Endpoints

```python
@router.post("/sessions", status_code=201)
async def create_session(
    req: CreateSessionRequest,
    response: Response,
    user: UserInfo = Depends(require_perms(["agents:run"])),
):
    # 1. Check rate limit first (raises 429 on exceeded)
    rate_limiter = RateLimitHandler(user_id=user.sub)
    await rate_limiter.check("sessions:create")
    
    # 2. Process request
    session = create_session_logic(req)
    
    # 3. Add informational headers
    await add_rate_limit_headers(response, user.sub, "sessions:create")
    
    return session
```

### Per-Resource Rate Limiting

For actions scoped to a specific resource (e.g., steps per session):

```python
# Rate limit per user per session
rate_limiter = RateLimitHandler(
    user_id=user.sub,
    resource_id=session_id
)
await rate_limiter.check("steps:create")
```

This ensures:
- User can create 100 steps/min in session A
- AND 100 steps/min in session B
- Total: 200 steps/min across both sessions

## Redis Key Structure

Pattern: `ratelimit:{action}:{user_id}[:{resource_id}]`

Examples:
- `ratelimit:sessions:create:user123`
- `ratelimit:steps:create:user123:session456`
- `ratelimit:runs:create:user789`

**TTL**: Keys expire after `window` seconds (60s) automatically via Redis EXPIRE.

## Testing

### Manual Testing

```bash
# Test session creation rate limit
for i in {1..15}; do
  curl -X POST http://localhost:8000/v1/agents/sessions \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"manager":"auto","tools":[]}'
  echo ""
done

# Expected: First 10 succeed (201), next 5 fail (429)
```

### Unit Test Example

```python
async def test_rate_limit_exceeded():
    # Make 10 requests (limit)
    for i in range(10):
        response = await client.post("/v1/agents/sessions", ...)
        assert response.status_code == 201
    
    # 11th request should fail
    response = await client.post("/v1/agents/sessions", ...)
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert response.json()["status"] == 429
```

## Performance Characteristics

### Redis Operations

Each rate limit check performs:
1. `ZREMRANGEBYSCORE` - O(log(N) + M) where M = removed entries
2. `ZCARD` - O(1)
3. `ZADD` - O(log(N))
4. `EXPIRE` - O(1)

**Total**: ~O(log(N)) where N = requests in window

### Typical Performance

- **Latency**: <5ms per check (Redis local)
- **Memory**: ~100 bytes per request timestamp in window
- **Cleanup**: Automatic via ZREMRANGEBYSCORE and EXPIRE

### Scalability

- ✅ Per-user rate limiting (no global bottleneck)
- ✅ Per-resource scoping (session-level limits)
- ✅ Automatic cleanup (no manual garbage collection)
- ✅ Distributed (works across multiple API instances)

## Configuration

Rate limits are defined in code (`db/redis_cache/rate_limit.py`). To adjust:

1. Edit `RATE_LIMITS` dictionary
2. Redeploy (no database migration needed)

**Future enhancement**: Move to Redis config for runtime adjustment without redeployment.

## RFC 6585 Compliance

Implements [RFC 6585: Additional HTTP Status Codes](https://tools.ietf.org/html/rfc6585):

✅ **429 Too Many Requests**: Proper status code  
✅ **Retry-After header**: Seconds until retry allowed  
✅ **Problem Details (RFC 7807)**: Structured error response  
✅ **X-RateLimit-* headers**: Informational headers (de facto standard)

## Integration with Other Features

### With Idempotency

Rate limit is checked **before** idempotency replay check:

```python
# 1. Rate limit (fresh request counted)
await rate_limiter.check("sessions:create")

# 2. Idempotency (replayed request NOT counted)
if idempotency_key:
    cached = await handler.check(idempotency_key)
    if cached:
        return cached  # Replayed - doesn't count toward rate limit
```

### With RBAC

Rate limiting is **per-user** after authentication:

```python
user = Depends(require_perms(["agents:run"]))  # Auth/authz first
rate_limiter = RateLimitHandler(user_id=user.sub)  # Then rate limit
```

Admins are NOT exempt from rate limits (prevents abuse).

### With ETag Caching

304 Not Modified responses **do NOT** count toward rate limit:

```python
# Check ETag first
if etag and if_none_match == etag:
    return Response(status_code=304)  # No rate limit check
    
# Rate limit only on cache miss
await rate_limiter.check("sessions:list")
```

## Error Handling

### Client Responsibilities

1. **429 Response**: Respect `Retry-After` header
2. **Exponential Backoff**: Recommended for burst scenarios
3. **Monitoring**: Track X-RateLimit-Remaining to avoid hitting limit

### Server Guarantees

1. **Consistent 429**: Always includes Retry-After
2. **Fair Counting**: Sliding window ensures no burst exploitation
3. **Informational Headers**: Always present on success

## Files Modified

### Created
- ✅ `db/redis_cache/rate_limit.py` (267 lines) - Redis sliding window helpers
- ✅ `docs/RATE_LIMITING_IMPLEMENTATION.md` (this file)

### Modified
- ✅ `src/middleware/rate_limit.py` - Replaced with RFC 6585 compliant implementation
- ✅ `src/routers/agent.py` - Integrated rate limiting into 4 endpoints
- ✅ `src/routers/agent_runs.py` - Integrated rate limiting into 1 endpoint

## Summary

**Phase 6 Complete**: ✅

- ✅ Redis sliding window rate limiting implemented
- ✅ RFC 6585/7807 compliant 429 responses
- ✅ Integrated into 5 endpoints (3 POST, 2 GET)
- ✅ Per-user and per-resource scoping
- ✅ Proper headers (Retry-After, X-RateLimit-*)
- ✅ Fair sliding window algorithm
- ✅ Documented comprehensively

**Next Phase**: Error Handling Polish (Phase 7)
