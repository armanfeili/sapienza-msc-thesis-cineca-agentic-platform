# Agent API Best Practices Guide

**Date:** October 20, 2025  
**Audience:** API Consumers, SDK Developers, Integration Teams  
**Level:** Intermediate to Advanced

---

## Table of Contents

1. [Authentication & Authorization](#authentication)
2. [Idempotency for Safe Retries](#idempotency)
3. [ETag Caching for Efficiency](#caching)
4. [Cursor-Based Pagination](#pagination)
5. [Rate Limiting Awareness](#rate-limiting)
6. [Error Handling & Recovery](#errors)
7. [Debugging with Trace IDs](#tracing)
8. [Common Workflows](#workflows)
9. [Performance Optimization](#performance)
10. [Migration Guide](#migration)

---

## Authentication & Authorization

### Bearer Token Authentication

All endpoints require HTTP Bearer authentication:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/agents/sessions
```

### Getting a Token

**Development:**
```bash
# Using Auth0 (if configured)
export AUTH0_DOMAIN="your-tenant.auth0.com"
export AUTH0_CLIENT_ID="your-client-id"
export AUTH0_CLIENT_SECRET="your-secret"

./scripts/get_auth0_tokens_with_model_scopes.sh

# Token saved to: ~/.auth0-token
TOKEN=$(cat ~/.auth0-token | jq -r '.access_token')
```

### Scope-Based Authorization

The API uses scopes to control what users can do:

- **`user:me`** – Read own resources (default for all users)
- **`admin:all`** – Full admin access across all users/tenants

**How it works:**

```
┌─────────────────┐
│  User Request   │
└────────┬────────┘
         │ Bearer Token
         ↓
    ┌────────────┐
    │ Validate   │ → Extract user.scopes from JWT
    │ Token      │
    └────────────┘
         │
         ├─→ Has "admin:all"? → Access ALL resources
         │
         └─→ Only "user:me"? → Access only OWN resources
```

### Permission Errors

- **401 Unauthorized** – Invalid or missing token
- **403 Forbidden** – Valid token but insufficient scopes

**Example:**
```json
{
  "type": "https://example.com/problems/insufficient-permissions",
  "title": "Forbidden",
  "detail": "Requires 'admin:all' scope",
  "status": 403
}
```

---

## Idempotency for Safe Retries

### The Problem

Network failures are unpredictable. If a request fails mid-transfer, you don't know if:
- The request never reached the server
- The request reached but the response didn't return
- The server successfully processed it

**Without idempotency:** Retrying creates duplicates  
**With idempotency:** Retrying returns the same result

### The Solution: Idempotency-Key Header

Use the `Idempotency-Key` header on POST requests:

```bash
curl -X POST http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: session-abc-123" \
  -H "Content-Type: application/json" \
  -d '{...}'

# Result: 201 Created (first time)

# Network fails. Retry:
curl -X POST http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: session-abc-123" \
  -H "Content-Type: application/json" \
  -d '{...}'

# Result: 200 OK (same response as before, no duplicate created!)
```

### Generating Idempotency Keys

Good practices:
- **Use UUIDs:** `12345678-1234-1234-1234-123456789012`
- **Use scoped IDs:** `user-123:session-456`
- **Use timestamps:** `req-20251020-153000-abc123`
- **Make them unique:** Each request should have a different key

Bad practices:
- ❌ Same key for different requests
- ❌ Reusing keys across time periods
- ❌ Non-deterministic generation

### Endpoints Supporting Idempotency

✅ **POST /agents/sessions** – Create session  
✅ **POST /agents/sessions/{session_id}/steps** – Add step  
✅ **POST /agent-runs** – Create run

### Idempotency Timeout

Idempotent responses are cached for **24 hours**. After that:
- Same key may return 201 (new resource) instead of 200 (cached)
- Store the resource ID immediately after creation

---

## ETag Caching for Efficiency

### The Problem

Polling GET endpoints repeatedly wastes bandwidth, especially for large responses:

```
Request: GET /agents/sessions (returns 10MB list)
Response: 200 OK (10MB)
[Wait 1 minute]
Request: GET /agents/sessions (exact same data)
Response: 200 OK (10MB) ← Wasteful!
```

### The Solution: ETag (Entity Tag)

ETags are like checksums for responses:

```bash
# First request
curl -X GET http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN"

# Response includes:
# ETag: "sessions-list-v2-abc123def456"

# Store the ETag...

# Later, check if unchanged:
curl -X GET http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "If-None-Match: \"sessions-list-v2-abc123def456\""

# Response: 304 Not Modified ← No body, save bandwidth!
```

### How to Use ETags

**Step 1: Store the ETag from response headers**
```bash
ETag=$(curl -sD - http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" | grep -i "^etag:" | cut -d' ' -f2)

echo "Saved ETag: $ETag"
```

**Step 2: Use If-None-Match header on next request**
```bash
curl -X GET http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "If-None-Match: $ETag"

# If unchanged → 304 Not Modified (no body)
# If changed → 200 OK (with new body + new ETag)
```

### Endpoints Supporting ETag

✅ **GET /agents/sessions** – List sessions  
✅ **GET /agents/sessions/{session_id}** – Get session  
✅ **GET /agents/sessions/{session_id}/steps** – List steps  
✅ **GET /agent-runs/{run_id}** – Get run

### ETag Best Practices

- Always store the ETag from responses
- Include ETag when polling the same resource
- Handle 304 responses (no new data to process)
- Don't hardcode ETags (they change when data changes)
- Refresh ETag periodically even if 304 (max every hour)

---

## Cursor-Based Pagination

### The Problem

Lists can have thousands of items. Fetching all at once:
- Takes time (slow)
- Uses memory (wasteful)
- May timeout (unreliable)

**Solution:** Pagination (fetch in smaller chunks)

### How Cursor-Based Pagination Works

```
Request 1: GET /agents/sessions?limit=20
Response:
{
  "items": [...20 items...],
  "next_cursor": "eyJsYXN0X2lkIjogIjEyMyJ9"
}

Request 2: GET /agents/sessions?limit=20&cursor=eyJsYXN0X2lkIjogIjEyMyJ9
Response:
{
  "items": [...next 20 items...],
  "next_cursor": "eyJsYXN0X2lkIjogIjQ1NiJ9"
}

Request 3: GET /agents/sessions?limit=20&cursor=eyJsYXN0X2lkIjogIjQ1NiJ9
Response:
{
  "items": [...final 10 items...],
  "next_cursor": null  ← No more pages
}
```

### Using Cursor Pagination in Code

**Bash:**
```bash
#!/bin/bash
TOKEN=$1
LIMIT=50
CURSOR=""

while true; do
  # Build URL
  if [ -z "$CURSOR" ]; then
    URL="http://localhost:8000/v1/agents/sessions?limit=$LIMIT"
  else
    URL="http://localhost:8000/v1/agents/sessions?limit=$LIMIT&cursor=$CURSOR"
  fi

  # Fetch page
  RESPONSE=$(curl -s "$URL" -H "Authorization: Bearer $TOKEN")

  # Process items
  echo "$RESPONSE" | jq -r '.items[] | .session_id'

  # Check for more pages
  CURSOR=$(echo "$RESPONSE" | jq -r '.next_cursor // empty')
  [ -z "$CURSOR" ] && break
done
```

**Python:**
```python
import requests

def fetch_all_sessions(token):
    cursor = None
    limit = 50
    
    while True:
        params = {'limit': limit}
        if cursor:
            params['cursor'] = cursor
        
        response = requests.get(
            'http://localhost:8000/v1/agents/sessions',
            headers={'Authorization': f'Bearer {token}'},
            params=params
        )
        
        data = response.json()
        yield from data['items']
        
        cursor = data.get('next_cursor')
        if not cursor:
            break
```

### Pagination Parameters

- **`limit`** – Items per page (default varies by endpoint)
  - Min: 1, Max: 100
  - Tip: Use larger limits for faster iteration (50-100)
- **`cursor`** – Opaque token for next page
  - Don't parse or modify cursors
  - Pass exactly as returned in `next_cursor`

### Endpoints Supporting Pagination

✅ **GET /agents/sessions** – `limit=20` default  
✅ **GET /agents/sessions/{session_id}/steps** – `limit=50` default

---

## Rate Limiting Awareness

### The Problem

Unlimited requests can overload the server. Rate limiting protects the system.

### How It Works

Each user gets a quota of requests per minute. Exceeding it returns **429 Too Many Requests**.

### Rate Limit Response Headers

Every response includes rate limit info:

```
X-RateLimit-Limit: 100          ← Your quota per minute
X-RateLimit-Remaining: 87       ← Requests left in current window
X-RateLimit-Reset: 1634567890   ← Unix timestamp when limit resets
```

### Checking Rate Limits

```bash
curl -sD - http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" | grep -i "x-ratelimit"

# Output:
# X-RateLimit-Limit: 100
# X-RateLimit-Remaining: 99
# X-RateLimit-Reset: 1634567890
```

### Handling 429 Responses

```python
import requests
import time

def call_api_with_retry(url, token, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(
            url,
            headers={'Authorization': f'Bearer {token}'}
        )
        
        if response.status_code == 429:
            # Rate limited
            reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
            wait_seconds = max(reset_time - time.time(), 1)
            
            print(f"Rate limited. Waiting {wait_seconds}s...")
            time.sleep(wait_seconds)
            continue
        
        return response
    
    raise Exception("Max retries exceeded")
```

### Rate Limit Strategy

**Best practices:**
- ✅ Check `X-RateLimit-Remaining` before requests
- ✅ Back off exponentially on 429 responses
- ✅ Batch requests when possible
- ✅ Cache responses (use ETags)

**Avoid:**
- ❌ Sending requests in tight loops
- ❌ Ignoring rate limit headers
- ❌ Hammering the same endpoint

---

## Error Handling & Recovery

### Error Response Format (RFC 7807)

All errors return standardized Problem Detail format:

```json
{
  "type": "https://example.com/problems/session-not-found",
  "title": "Session Not Found",
  "detail": "Session 550e8400-e29b-41d4-a716-446655440000 does not exist",
  "status": 404,
  "instance": "/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000",
  "extensions": {
    "error_code": "RESOURCE_NOT_FOUND",
    "correlation_id": "corr-xyz789",
    "timestamp": "2025-10-20T15:30:45.123456Z"
  }
}
```

### Common HTTP Status Codes

| Code | Meaning | When It Happens | What To Do |
|------|---------|-----------------|-----------|
| 200 | OK | Request succeeded | Process response |
| 201 | Created | Resource created | Store resource ID |
| 204 | No Content | Deletion succeeded | Done (no body) |
| 304 | Not Modified | Cached version valid | Use cached data |
| 400 | Bad Request | Invalid parameters | Fix request body |
| 401 | Unauthorized | Missing/invalid token | Get new token |
| 403 | Forbidden | Insufficient permissions | Use admin account |
| 404 | Not Found | Resource doesn't exist | Verify resource ID |
| 409 | Conflict | Resource already exists | Use existing resource |
| 429 | Too Many Requests | Rate limited | Wait before retrying |
| 500 | Server Error | Internal failure | Retry with backoff |

### Resilient Error Handling

```python
import requests
import time
from requests.exceptions import ConnectionError, Timeout

def call_api_resilient(url, token, method='GET', data=None, max_retries=3):
    """Call API with automatic retry and exponential backoff."""
    
    for attempt in range(max_retries):
        try:
            response = requests.request(
                method,
                url,
                headers={'Authorization': f'Bearer {token}'},
                json=data,
                timeout=30
            )
            
            # Handle different status codes
            if response.status_code == 429:
                # Rate limited - wait and retry
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait = max(reset_time - time.time(), 1)
                print(f"Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            
            elif response.status_code >= 500:
                # Server error - retry with backoff
                if attempt < max_retries - 1:
                    wait = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    print(f"Server error ({response.status_code}). Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
            
            # Success or client error - return response
            return response
        
        except (ConnectionError, Timeout) as e:
            # Network error - retry with backoff
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"Network error: {e}. Retrying in {wait}s...")
                time.sleep(wait)
                continue
            else:
                raise
    
    raise Exception(f"Failed after {max_retries} attempts")
```

---

## Debugging with Trace IDs

### The Problem

Errors in production are hard to debug. You need to correlate:
- Your request
- Server logs
- Monitoring systems

### The Solution: Correlation IDs

Every response includes `X-Correlation-Id` and `X-Request-Id` headers:

```bash
curl -sD - http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" | grep -i "x-.*id"

# Output:
# X-Request-Id: req-abc123-def456
# X-Correlation-Id: corr-xyz789
```

### Using Trace IDs for Debugging

**Save trace IDs with errors:**
```python
response = requests.get(
    'http://localhost:8000/v1/agents/sessions/invalid-id',
    headers={'Authorization': f'Bearer {token}'}
)

if response.status_code >= 400:
    # Extract trace ID
    trace_id = response.headers.get('X-Correlation-Id', 'unknown')
    request_id = response.headers.get('X-Request-Id', 'unknown')
    
    # Log error with trace IDs
    print(f"ERROR [trace={trace_id}] [request={request_id}]")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
```

**Pass trace ID to support:**
```
"Error getting session. Trace ID: corr-xyz789"
```

**Support team can:**
1. Search server logs for `corr-xyz789`
2. Find the request and response
3. Understand what went wrong
4. Fix it faster

---

## Common Workflows

### Workflow 1: Interactive Session (Multi-step Conversation)

```bash
#!/bin/bash
TOKEN=$1

# 1. Create a session
SESSION_ID=$(curl -s -X POST http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: session-$(date +%s)" \
  -d '{
    "temperature": 0.2,
    "max_steps": 10,
    "tools": ["web_search", "python_repl"]
  }' | jq -r '.session_id')

echo "Created session: $SESSION_ID"

# 2. Add user message
curl -s -X POST http://localhost:8000/v1/agents/sessions/$SESSION_ID/steps \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: step-1-$(date +%s)" \
  -d '{
    "type": "message",
    "message": "What is the capital of France?"
  }' > /dev/null

echo "Added step 1"

# 3. Add another message
curl -s -X POST http://localhost:8000/v1/agents/sessions/$SESSION_ID/steps \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: step-2-$(date +%s)" \
  -d '{
    "type": "message",
    "message": "Tell me more about its history"
  }' > /dev/null

echo "Added step 2"

# 4. List all steps
curl -s -X GET http://localhost:8000/v1/agents/sessions/$SESSION_ID/steps \
  -H "Authorization: Bearer $TOKEN" | jq '.items[] | {type, message}'

# 5. Cancel session when done
curl -s -X DELETE http://localhost:8000/v1/agents/sessions/$SESSION_ID \
  -H "Authorization: Bearer $TOKEN"

echo "Cancelled session"
```

### Workflow 2: One-Off Query (Single Request/Response)

```bash
#!/bin/bash
TOKEN=$1

# Execute a single task without session management
RUN_ID=$(curl -s -X POST http://localhost:8000/v1/agent-runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: run-$(date +%s)" \
  -d '{
    "prompt": "What is the square root of 144?",
    "tools": ["python_repl"],
    "temperature": 0.1
  }' | jq -r '.run_id')

echo "Created run: $RUN_ID"

# Later, retrieve results
curl -s -X GET http://localhost:8000/v1/agent-runs/$RUN_ID \
  -H "Authorization: Bearer $TOKEN" | jq '.output'
```

### Workflow 3: Monitoring Sessions with Pagination

```bash
#!/bin/bash
TOKEN=$1

# Get first page
RESPONSE=$(curl -s -X GET "http://localhost:8000/v1/agents/sessions?limit=10" \
  -H "Authorization: Bearer $TOKEN")

# Process all pages
while true; do
  # Show current page
  echo "$RESPONSE" | jq '.items[] | "\(.session_id): \(.status)"'
  
  # Check for next page
  CURSOR=$(echo "$RESPONSE" | jq -r '.next_cursor // empty')
  [ -z "$CURSOR" ] && break
  
  # Get next page
  RESPONSE=$(curl -s -X GET "http://localhost:8000/v1/agents/sessions?limit=10&cursor=$CURSOR" \
    -H "Authorization: Bearer $TOKEN")
done
```

---

## Performance Optimization

### 1. Reduce API Calls

❌ **Bad:** Poll endpoint in loop every second
```python
while True:
    response = requests.get(...).json()
    time.sleep(1)  # Wastes 1 call per second
```

✅ **Good:** Use webhooks or push notifications (when available)

### 2. Use Pagination Efficiently

❌ **Bad:** Fetch 1 item at a time
```python
for i in range(1000):
    response = requests.get(f'/sessions?limit=1&cursor=...{i}')
    # 1000 requests!
```

✅ **Good:** Fetch larger pages
```python
for page in paginate(requests.get('/sessions?limit=100')):
    # ~10 requests
```

### 3. Cache Aggressively

❌ **Bad:** Fetch same data repeatedly
```python
for _ in range(100):
    response = requests.get('/sessions/123')  # Same 100 times
```

✅ **Good:** Cache with ETag
```python
cached_data = fetch_with_etag('/sessions/123')
# Reuse from cache until ETag changes
```

### 4. Batch Operations

When possible, combine multiple requests:

```
❌ Create 10 sessions → 10 requests
✅ Create 10 sessions in one batch → 1 request (if API supports)
```

### 5. Connection Pooling

Reuse HTTP connections instead of creating new ones:

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()

# Configure retry strategy
retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"],
    backoff_factor=1
)

adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

# Use session for multiple requests
response1 = session.get('http://...')
response2 = session.get('http://...')
# Connection reused!
```

---

## Migration Guide

### From Hardcoded IDs to Dynamic IDs

❌ **Old (brittle):**
```python
SESSION_ID = "550e8400-e29b-41d4-a716-446655440000"
response = requests.get(f'/agents/sessions/{SESSION_ID}', ...)
```

✅ **New (robust):**
```python
# Create session dynamically
response = requests.post(
    '/agents/sessions',
    json={...},
    headers={'Idempotency-Key': generate_unique_key()}
)
session_id = response.json()['session_id']

# Use returned ID
response = requests.get(f'/agents/sessions/{session_id}', ...)
```

### From Polling to Event-Driven

❌ **Old (wasteful):**
```python
while True:
    status = requests.get(f'/agents/sessions/{id}').json()['status']
    if status == 'completed':
        break
    time.sleep(5)  # Poll every 5 seconds
```

✅ **New (efficient):**
```python
# Use webhooks (when available)
register_webhook(f'sessions/{id}/completed', callback)

# Or check once with caching
response = requests.get(
    f'/agents/sessions/{id}',
    headers={'If-None-Match': saved_etag}
)
if response.status_code != 304:
    status = response.json()['status']
```

### From Manual Error Handling to Resilient Patterns

❌ **Old (fragile):**
```python
response = requests.get(url, timeout=10)
data = response.json()  # Crashes on network error
```

✅ **New (robust):**
```python
response = call_api_resilient(url, token, max_retries=3)
data = response.json() if response.ok else handle_error(response)
```

---

## Checklist for API Integration

Use this checklist when building integrations:

### Authentication
- [ ] Use Bearer tokens from Auth0 or identity provider
- [ ] Store tokens securely (not in code)
- [ ] Refresh tokens before expiry
- [ ] Handle 401/403 errors gracefully

### Reliability
- [ ] Implement idempotency keys for POST requests
- [ ] Handle rate limiting (429 responses) with backoff
- [ ] Implement exponential backoff for server errors (5xx)
- [ ] Handle network timeouts and connection errors
- [ ] Log correlation IDs for debugging

### Efficiency
- [ ] Use ETag caching for GET requests
- [ ] Use cursor pagination instead of fetching all at once
- [ ] Check X-RateLimit-Remaining before requests
- [ ] Batch operations when possible
- [ ] Use HTTP connection pooling

### Correctness
- [ ] Validate response schema before use
- [ ] Handle all documented status codes
- [ ] Check for required fields in responses
- [ ] Implement proper error handling (try/catch)
- [ ] Test with both success and failure scenarios

### Monitoring
- [ ] Log API calls (method, path, status, latency)
- [ ] Track error rates and types
- [ ] Monitor rate limit consumption
- [ ] Alert on elevated error rates (>1%)
- [ ] Use correlation IDs in logs

---

**Last Updated:** October 20, 2025  
**Related Documents:**
- ENDPOINT_DESCRIPTIONS.md – Detailed endpoint guide
- ENDPOINT_QUICK_REFERENCE.md – Quick lookup reference
- docs/INCIDENT_RESPONSE.md – Common issues and fixes
