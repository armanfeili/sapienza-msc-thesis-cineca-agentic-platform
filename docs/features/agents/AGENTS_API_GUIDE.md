# Agents API Complete Guide

**Version**: 1.0  
**Status**: Production Ready  
**Last Updated**: 2025-01-15

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Authentication](#authentication)
4. [Core Concepts](#core-concepts)
5. [API Endpoints](#api-endpoints)
6. [Features](#features)
7. [Error Handling](#error-handling)
8. [Best Practices](#best-practices)
9. [Examples](#examples)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The Agents API enables stateful, multi-step agent orchestration with robust production features:

- **Stateful Sessions**: Long-running agent workflows with persistent state
- **Step Sequencing**: Ordered execution tracking with automatic sequence numbers
- **Run Execution**: Execute agent tasks linked to sessions
- **Idempotency**: Safe retries with Idempotency-Key header
- **Rate Limiting**: RFC 6585 compliant with sliding window algorithm
- **ETag Caching**: Efficient list operations with 304 Not Modified
- **Cursor Pagination**: Scalable pagination for large datasets
- **RBAC**: Fine-grained permission control
- **RFC 7807 Errors**: Structured, machine-readable error responses

### Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ HTTP/REST
       ▼
┌─────────────────────────────────┐
│      FastAPI Application        │
│  ┌──────────────────────────┐  │
│  │   Agent Endpoints        │  │
│  │  - Sessions (/sessions)  │  │
│  │  - Steps (/steps)        │  │
│  │  - Runs (/agent-runs)    │  │
│  └──────────────────────────┘  │
│  ┌──────────────────────────┐  │
│  │   Middleware             │  │
│  │  - RBAC                  │  │
│  │  - Rate Limiting         │  │
│  │  - Idempotency           │  │
│  └──────────────────────────┘  │
└───────┬──────────────┬──────────┘
        │              │
   ┌────▼────┐    ┌────▼────┐
   │PostgreSQL│    │  Redis  │
   │(Sessions,│    │(State,  │
   │ Steps,   │    │ Cache,  │
   │ Runs)    │    │ Locks)  │
   └──────────┘    └─────────┘
```

---

## Quick Start

### 1. Create a Session

```bash
curl -X POST http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "manager": "auto",
    "tools": ["calculator", "web_search"],
    "temperature": 0.7,
    "max_steps": 20
  }'
```

Response:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "auth0|123456",
  "tenant_id": "default",
  "manager": "auto",
  "tools": ["calculator", "web_search"],
  "temperature": 0.7,
  "max_steps": 20,
  "status": "active",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

### 2. Add Steps to Session

```bash
curl -X POST http://localhost:8000/v1/agents/sessions/{session_id}/steps \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "message",
    "input": {
      "text": "What is 2+2?"
    },
    "output": {
      "result": "4"
    }
  }'
```

Response:
```json
{
  "step_id": "660e8400-e29b-41d4-a716-446655440001",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "seq": 1,
  "type": "message",
  "input": {"text": "What is 2+2?"},
  "output": {"result": "4"},
  "created_at": "2025-01-15T10:31:00Z"
}
```

### 3. Execute a Run

```bash
curl -X POST http://localhost:8000/v1/agent-runs \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "prompt": "Calculate the square root of 144",
    "manager": "auto"
  }'
```

---

## Authentication

### Required Scopes

| Scope | Description |
|-------|-------------|
| `agents:run` | Create sessions, steps, and runs |
| `admin:all` | Full access to all sessions (admin only) |

### Authentication Header

```http
Authorization: Bearer <your-jwt-token>
```

### Example: Get Token (Auth0)

```bash
curl --request POST \
  --url https://your-tenant.auth0.com/oauth/token \
  --header 'content-type: application/json' \
  --data '{
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "audience": "api://cineca-agentic-platform",
    "grant_type": "client_credentials"
  }'
```

---

## Core Concepts

### Sessions

**Sessions** represent long-running agent workflows:

- **Lifecycle**: `active` → `completed` | `cancelled` | `failed`
- **Persistence**: Stored in PostgreSQL + Redis state cache
- **Ownership**: Users see only their own sessions (unless admin)
- **Metadata**: Custom JSON metadata supported

**Use Cases**:
- Interactive chat sessions
- Multi-step workflows
- Long-running tasks
- Stateful agent orchestration

### Steps

**Steps** are individual actions within a session:

- **Sequencing**: Automatically numbered (1, 2, 3, ...)
- **Types**: `message`, `tool_call`, `function`, etc.
- **Input/Output**: Structured JSON data
- **Immutable**: Cannot be modified once created

**Use Cases**:
- Conversation turns
- Tool invocations
- Decision points
- State transitions

### Runs

**Runs** execute agent tasks:

- **Linked to Sessions**: Every run has a session
- **Auto-Session**: Creates session if none provided
- **Execution**: Synchronous or asynchronous
- **Results**: Output, status, latency tracked

**Use Cases**:
- Execute agent prompt
- Background tasks
- Batch processing
- API integrations

---

## API Endpoints

### Sessions

#### POST /v1/agents/sessions

Create a new agent session.

**Request**:
```json
{
  "session_id": "optional-custom-id",
  "manager": "auto",
  "tools": ["calculator"],
  "temperature": 0.7,
  "max_steps": 20,
  "metadata": {
    "user_context": "value"
  }
}
```

**Response**: `201 Created`
```json
{
  "session_id": "...",
  "status": "active",
  ...
}
```

**Headers**:
- `Location`: `/v1/agents/sessions/{session_id}`
- `X-RateLimit-Limit`: `10`
- `X-RateLimit-Remaining`: `9`
- `X-RateLimit-Window`: `60`

**Rate Limit**: 10 requests/minute

---

#### GET /v1/agents/sessions

List user's sessions with pagination.

**Query Parameters**:
- `limit` (optional): Max items (default: 20, max: 100)
- `cursor` (optional): Pagination cursor

**Request**:
```bash
curl -X GET "http://localhost:8000/v1/agents/sessions?limit=20" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response**: `200 OK`
```json
{
  "items": [
    {
      "session_id": "...",
      "status": "active",
      "created_at": "2025-01-15T10:00:00Z",
      ...
    }
  ],
  "next_page_token": "eyJjcmVhdGVkX2F0IjoiMjAyNS0wMS0xNVQxMDowMDowMFoiLCJpZCI6Ii4uLiJ9"
}
```

**Headers**:
- `ETag`: `"abc123def456"`
- `X-RateLimit-Limit`: `100`

**ETag Support**:
```bash
# First request
curl -X GET /v1/agents/sessions -H "Authorization: Bearer ..."
# ETag: "abc123"

# Subsequent request with If-None-Match
curl -X GET /v1/agents/sessions \
  -H "Authorization: Bearer ..." \
  -H "If-None-Match: \"abc123\""
# Returns: 304 Not Modified (if unchanged)
```

**Rate Limit**: 100 requests/minute

---

#### GET /v1/agents/sessions/{session_id}

Get session details by ID.

**Response**: `200 OK`
```json
{
  "session_id": "...",
  "user_id": "...",
  "status": "active",
  "created_at": "...",
  "updated_at": "...",
  ...
}
```

**Errors**:
- `404 Not Found`: Session doesn't exist or no access

---

#### DELETE /v1/agents/sessions/{session_id}

Cancel a session (idempotent).

**Response**: `204 No Content`

**Side Effects**:
- Sets session status to `cancelled`
- Sets cancellation flag in Redis
- Invalidates list ETag

**Idempotent**: Multiple DELETE requests succeed

---

### Steps

#### POST /v1/agents/sessions/{session_id}/steps

Add a step to a session.

**Request**:
```json
{
  "type": "message",
  "input": {
    "text": "User message"
  },
  "output": {
    "response": "Agent response"
  }
}
```

**Response**: `201 Created`
```json
{
  "step_id": "...",
  "session_id": "...",
  "seq": 1,
  "type": "message",
  "input": {...},
  "output": {...},
  "created_at": "..."
}
```

**Headers**:
- `Location`: `/v1/agents/sessions/{session_id}/steps/{step_id}`
- `X-RateLimit-Limit`: `100`
- `X-RateLimit-Remaining`: `99`

**Requirements**:
- Session must be in `active` status
- Steps are auto-sequenced

**Rate Limit**: 100 requests/minute per session

**Errors**:
- `400 Bad Request`: Session not active
- `404 Not Found`: Session doesn't exist

---

#### GET /v1/agents/sessions/{session_id}/steps

List steps for a session.

**Query Parameters**:
- `limit` (optional): Max items (default: 50)
- `cursor` (optional): Sequence number for pagination

**Response**: `200 OK`
```json
{
  "items": [
    {
      "step_id": "...",
      "seq": 1,
      "type": "message",
      ...
    }
  ],
  "next_page_token": "2"
}
```

**Ordering**: Steps ordered by sequence number (ascending)

**Headers**:
- `ETag`: Cached per session

**Rate Limit**: 100 requests/minute per session

---

### Runs

#### POST /v1/agent-runs

Execute an agent run.

**Request**:
```json
{
  "session_id": "optional-existing-session",
  "prompt": "Your task description",
  "manager": "auto",
  "tools": ["calculator"],
  "temperature": 0.7,
  "max_steps": 10,
  "metadata": {}
}
```

**Response**: `201 Created`
```json
{
  "run_id": "...",
  "session_id": "...",
  "status": "succeeded",
  "model": "gpt-4",
  "latency_ms": 1234,
  "output": "Agent response text",
  "trace_id": "...",
  "event_id": "...",
  "created_at": "..."
}
```

**Headers**:
- `Location`: `/v1/agent-runs/{run_id}`
- `X-RateLimit-Limit`: `20`

**Behavior**:
- If `session_id` provided: Links to existing session
- If `session_id` omitted: Creates new session automatically

**Rate Limit**: 20 requests/minute

---

#### GET /v1/agent-runs/{run_id}

Get run details by ID.

**Response**: `200 OK`
```json
{
  "run_id": "...",
  "session_id": "...",
  "status": "succeeded",
  "output": "...",
  ...
}
```

**Errors**:
- `400 Bad Request`: Invalid UUID format
- `404 Not Found`: Run doesn't exist or no access

---

## Features

### Idempotency

Prevent duplicate operations with `Idempotency-Key` header.

**Usage**:
```bash
curl -X POST http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Idempotency-Key: unique-key-123" \
  -H "Content-Type: application/json" \
  -d '{"manager": "auto", "tools": []}'
```

**First Request**:
- `201 Created`
- Resource created
- No `Idempotency-Replayed` header

**Subsequent Requests** (same key):
- `201 Created`
- **Same resource returned**
- `Idempotency-Replayed: true` header

**Key Format**:
- UUID v4 recommended: `550e8400-e29b-41d4-a716-446655440000`
- Max length: 255 characters
- Case-sensitive

**TTL**: Idempotency keys cached for 24 hours

**Supported Endpoints**:
- ✅ POST `/agents/sessions`
- ✅ POST `/agents/sessions/{id}/steps`
- ✅ POST `/agent-runs`

---

### Rate Limiting

RFC 6585 compliant rate limiting with sliding window algorithm.

**Limits**:

| Endpoint | Limit | Window |
|----------|-------|--------|
| Create Session | 10 | 60s |
| Create Step | 100 | 60s (per session) |
| Create Run | 20 | 60s |
| List Sessions | 100 | 60s |
| List Steps | 100 | 60s (per session) |

**Headers** (on success):
```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Window: 60
```

**429 Response**:
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

**Client Handling**:
```python
import time
import requests

def create_session_with_retry(data, max_retries=3):
    for attempt in range(max_retries):
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 201:
            return response.json()
        
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            print(f"Rate limited. Waiting {retry_after}s...")
            time.sleep(retry_after)
            continue
        
        response.raise_for_status()
    
    raise Exception("Max retries exceeded")
```

---

### ETag Caching

Efficient list operations with HTTP ETag caching.

**How It Works**:
1. First request returns `ETag` header
2. Client stores ETag value
3. Subsequent requests include `If-None-Match: ETag`
4. Server returns `304 Not Modified` if unchanged

**Example**:
```bash
# Request 1
curl -X GET /v1/agents/sessions \
  -H "Authorization: Bearer ..."
# Response: 200 OK
# ETag: "abc123def456"

# Request 2 (with cached ETag)
curl -X GET /v1/agents/sessions \
  -H "Authorization: Bearer ..." \
  -H "If-None-Match: \"abc123def456\""
# Response: 304 Not Modified (no body)
```

**ETag Invalidation**:
- Sessions list: Invalidated when user creates/deletes session
- Steps list: Invalidated when step added to session

**Benefits**:
- Reduced bandwidth
- Faster responses
- Lower server load

**Supported Endpoints**:
- ✅ GET `/agents/sessions`
- ✅ GET `/agents/sessions/{id}/steps`

---

### Cursor Pagination

Scalable pagination for large datasets.

**Pattern**:
```bash
# Page 1
GET /agents/sessions?limit=20
# Returns: items + next_page_token

# Page 2
GET /agents/sessions?limit=20&cursor={next_page_token}
# Returns: next page of items
```

**Response Structure**:
```json
{
  "items": [...],
  "next_page_token": "base64_encoded_cursor"
}
```

**Cursor Format**:
- Base64-encoded timestamp + ID
- Opaque to client (do not parse)
- Valid for pagination session only

**Best Practices**:
- Use reasonable `limit` (10-100)
- Don't rely on cursor format
- Handle missing `next_page_token` (last page)

**Example (Python)**:
```python
def fetch_all_sessions():
    sessions = []
    cursor = None
    
    while True:
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        
        response = requests.get(url, params=params, headers=headers)
        data = response.json()
        
        sessions.extend(data["items"])
        
        cursor = data.get("next_page_token")
        if not cursor:
            break
    
    return sessions
```

---

## Error Handling

All errors follow RFC 7807 Problem Details format.

### Error Structure

```json
{
  "type": "https://httpstatuses.com/404",
  "title": "Session Not Found",
  "status": 404,
  "detail": "Agent session 'abc123' does not exist or you don't have access to it.",
  "instance": "/agents/sessions/abc123",
  "extensions": {
    "error_code": "session_not_found",
    "session_id": "abc123"
  }
}
```

### Error Codes

| Code | Status | Description |
|------|--------|-------------|
| `session_not_found` | 404 | Session doesn't exist or no access |
| `step_not_found` | 404 | Step doesn't exist |
| `run_not_found` | 404 | Run doesn't exist or no access |
| `session_not_active` | 400 | Session not in active state |
| `invalid_cursor` | 400 | Invalid pagination cursor |
| `duplicate_session` | 409 | Session ID already exists |
| `database_error` | 500 | Database operation failed |
| `internal_error` | 500 | Unexpected server error |

### Client Error Handling

```typescript
interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  extensions?: {
    error_code?: string;
    [key: string]: any;
  };
}

async function createSession(data: any) {
  const response = await fetch('/v1/agents/sessions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });
  
  if (!response.ok) {
    const error: ProblemDetail = await response.json();
    
    switch (error.extensions?.error_code) {
      case 'duplicate_session':
        console.log('Session already exists');
        break;
      case 'database_error':
        console.error('Database error:', error.detail);
        break;
      default:
        console.error('Error:', error.title);
    }
    
    throw new Error(error.detail);
  }
  
  return await response.json();
}
```

---

## Best Practices

### 1. Use Idempotency Keys

Always use idempotency keys for create operations:

```python
import uuid

idempotency_key = str(uuid.uuid4())
headers = {
    "Authorization": f"Bearer {token}",
    "Idempotency-Key": idempotency_key,
    "Content-Type": "application/json",
}
```

### 2. Handle Rate Limits

Implement exponential backoff:

```python
import time

def exponential_backoff(func, max_retries=5):
    for attempt in range(max_retries):
        response = func()
        
        if response.status_code != 429:
            return response
        
        wait_time = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
        time.sleep(wait_time)
    
    raise Exception("Rate limit exceeded")
```

### 3. Cache with ETags

Store and reuse ETags:

```python
etag_cache = {}

def list_sessions():
    etag = etag_cache.get('sessions_list')
    headers = {"Authorization": f"Bearer {token}"}
    
    if etag:
        headers["If-None-Match"] = etag
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 304:
        # Use cached data
        return cached_sessions
    
    if response.status_code == 200:
        etag_cache['sessions_list'] = response.headers.get('ETag')
        return response.json()
```

### 4. Paginate Efficiently

Use reasonable page sizes:

```python
# Good: 20-50 items per page
GET /agents/sessions?limit=50

# Avoid: Very large pages
GET /agents/sessions?limit=1000  # May timeout
```

### 5. Clean Up Resources

Cancel sessions when done:

```python
try:
    session = create_session(...)
    # Use session
    add_steps(session['session_id'], ...)
finally:
    # Always clean up
    delete_session(session['session_id'])
```

### 6. Monitor Rate Limit Headers

Track remaining quota:

```python
response = requests.post(url, ...)
remaining = int(response.headers.get('X-RateLimit-Remaining', 0))

if remaining < 5:
    print(f"Warning: Only {remaining} requests remaining")
    # Slow down or wait
```

---

## Examples

### Complete Workflow

```python
import requests
import uuid

BASE_URL = "http://localhost:8000/v1"
TOKEN = "your_token_here"

def complete_agent_workflow():
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    
    # 1. Create session
    session_resp = requests.post(
        f"{BASE_URL}/agents/sessions",
        json={
            "manager": "auto",
            "tools": ["calculator", "web_search"],
            "temperature": 0.7,
            "max_steps": 20,
        },
        headers={
            **headers,
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    session = session_resp.json()
    session_id = session["session_id"]
    print(f"Created session: {session_id}")
    
    try:
        # 2. Add steps
        for i in range(3):
            step_resp = requests.post(
                f"{BASE_URL}/agents/sessions/{session_id}/steps",
                json={
                    "type": "message",
                    "input": {"text": f"Step {i+1}"},
                    "output": {"result": f"Result {i+1}"},
                },
                headers={
                    **headers,
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
            step = step_resp.json()
            print(f"Added step {step['seq']}")
        
        # 3. List steps
        steps_resp = requests.get(
            f"{BASE_URL}/agents/sessions/{session_id}/steps",
            headers=headers,
        )
        steps = steps_resp.json()
        print(f"Total steps: {len(steps['items'])}")
        
        # 4. Execute run
        run_resp = requests.post(
            f"{BASE_URL}/agent-runs",
            json={
                "session_id": session_id,
                "prompt": "Summarize the conversation",
                "manager": "auto",
            },
            headers={
                **headers,
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        run = run_resp.json()
        print(f"Run completed: {run['status']}")
        print(f"Output: {run['output']}")
    
    finally:
        # 5. Clean up
        delete_resp = requests.delete(
            f"{BASE_URL}/agents/sessions/{session_id}",
            headers=headers,
        )
        print(f"Session cancelled: {delete_resp.status_code == 204}")

if __name__ == "__main__":
    complete_agent_workflow()
```

---

## Troubleshooting

### Common Issues

#### 1. 401 Unauthorized

**Cause**: Missing or invalid token

**Solution**:
```bash
# Check token is set
echo $TOKEN

# Verify token hasn't expired
jwt decode $TOKEN

# Get new token
curl --request POST \
  --url https://your-tenant.auth0.com/oauth/token \
  ...
```

#### 2. 429 Too Many Requests

**Cause**: Rate limit exceeded

**Solution**:
- Check `Retry-After` header
- Implement exponential backoff
- Reduce request frequency
- Contact admin for limit increase

#### 3. 400 Session Not Active

**Cause**: Trying to add step to cancelled/completed session

**Solution**:
```python
# Check session status before adding steps
session = get_session(session_id)
if session['status'] != 'active':
    print(f"Session is {session['status']}, cannot add steps")
    # Create new session instead
```

#### 4. Invalid Cursor

**Cause**: Using outdated or malformed cursor

**Solution**:
- Don't parse or modify cursors
- Restart pagination if cursor invalid
- Use fresh cursor from latest response

#### 5. Connection Timeout

**Cause**: Server overloaded or network issues

**Solution**:
```python
# Increase timeout
requests.post(url, json=data, timeout=30)

# Retry with backoff
import time
for attempt in range(3):
    try:
        response = requests.post(url, json=data, timeout=10)
        break
    except requests.Timeout:
        time.sleep(2 ** attempt)
```

---

## Summary

The Agents API provides enterprise-grade agent orchestration with:

✅ **Production Features**: Idempotency, rate limiting, ETag caching  
✅ **Developer-Friendly**: RFC 7807 errors, cursor pagination, clear docs  
✅ **Scalable**: Sliding window rate limits, efficient caching  
✅ **Reliable**: PostgreSQL persistence, Redis state management  
✅ **Secure**: RBAC, per-user isolation, JWT authentication  

**Next Steps**:
- Review [Rate Limiting Documentation](./RATE_LIMITING_IMPLEMENTATION.md)
- Review [Error Handling Guide](./ERROR_HANDLING_STANDARDIZATION.md)
- Review [Testing Guide](./TESTING_GUIDE.md)
- Try the [API Examples](#examples)

**Support**:
- API Status: https://status.example.com
- Documentation: https://docs.example.com
- Issues: https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform/issues
