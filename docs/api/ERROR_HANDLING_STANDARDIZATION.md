# Error Handling Standardization

**Status**: ✅ Complete  
**Date**: 2025-01-15

## Overview

Standardized all error responses in the Agents API to RFC7807 ProblemDetail format with structured error codes. This ensures consistent, machine-readable error responses across all endpoints.

## Implementation

### Error Helper Module (`src/errors/agents.py`)

Created centralized error handling module with:

#### 1. Error Codes (`AgentErrorCode`)

Standardized machine-readable error codes:

```python
# Resource errors (404)
SESSION_NOT_FOUND = "session_not_found"
STEP_NOT_FOUND = "step_not_found"
RUN_NOT_FOUND = "run_not_found"

# State errors (400)
SESSION_NOT_ACTIVE = "session_not_active"
SESSION_ALREADY_EXISTS = "session_already_exists"
INVALID_CURSOR = "invalid_cursor"
INVALID_REQUEST = "invalid_request"

# Conflict errors (409)
DUPLICATE_SESSION = "duplicate_session"
DUPLICATE_IDEMPOTENCY_KEY = "duplicate_idempotency_key"

# Server errors (500)
DATABASE_ERROR = "database_error"
REDIS_ERROR = "redis_error"
INTERNAL_ERROR = "internal_error"
```

#### 2. Helper Functions

**Core Functions**:

- `create_problem_detail()` - Creates RFC7807 ProblemDetail instance
- `raise_problem()` - Raises HTTPException with ProblemDetail

**Convenience Functions**:

- `session_not_found(session_id, instance)` - 404 for missing sessions
- `step_not_found(step_id, session_id, instance)` - 404 for missing steps
- `run_not_found(run_id, instance)` - 404 for missing runs
- `session_not_active(session_id, current_status, instance)` - 400 for invalid state
- `invalid_cursor(cursor, reason, instance)` - 400 for pagination errors
- `duplicate_session(session_id, instance)` - 409 for conflicts
- `database_error(operation, error, instance)` - 500 for DB failures
- `internal_error(detail, instance, extensions)` - 500 for generic errors

## RFC7807 ProblemDetail Structure

All errors follow this structure:

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

### Fields

- **type**: URI reference identifying the problem type (always https://httpstatuses.com/{code})
- **title**: Short, human-readable summary (consistent for same error type)
- **status**: HTTP status code (integer)
- **detail**: Human-readable explanation specific to this occurrence
- **instance**: URI reference identifying specific occurrence (request path)
- **extensions**: Additional error-specific metadata (includes `error_code`)

## Updated Endpoints

### Session Endpoints (`src/routers/agent.py`)

#### POST /agents/sessions

**Before**:
```python
raise HTTPException(
    status_code=409,
    detail=f"Session {session_id} already exists"
)
```

**After**:
```python
agent_errors.duplicate_session(
    session_id=session_id,
    instance=f"/agents/sessions/{session_id}",
)
```

**Response**:
```json
{
  "type": "https://httpstatuses.com/409",
  "title": "Duplicate Session",
  "status": 409,
  "detail": "Session 'abc123' already exists. Use a different session_id or omit it for auto-generation.",
  "instance": "/agents/sessions/abc123",
  "extensions": {
    "error_code": "duplicate_session",
    "session_id": "abc123"
  }
}
```

#### GET /agents/sessions

**Before**:
```python
raise HTTPException(
    status_code=400,
    detail=f"Invalid cursor: {str(e)}"
)
```

**After**:
```python
agent_errors.invalid_cursor(
    cursor=cursor,
    reason=str(e),
    instance="/agents/sessions",
)
```

**Response**:
```json
{
  "type": "https://httpstatuses.com/400",
  "title": "Invalid Cursor",
  "status": 400,
  "detail": "Invalid pagination cursor: 'xyz'. Reason: Invalid format",
  "instance": "/agents/sessions",
  "extensions": {
    "error_code": "invalid_cursor",
    "cursor": "xyz"
  }
}
```

#### GET /agents/sessions/{id}

**Before**:
```python
raise HTTPException(
    status_code=404,
    detail=f"Session {session_id} not found"
)
```

**After**:
```python
agent_errors.session_not_found(
    session_id=session_id,
    instance=f"/agents/sessions/{session_id}",
)
```

**Response**:
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

#### DELETE /agents/sessions/{id}

Same as GET - uses `agent_errors.session_not_found()`

#### GET /agents/sessions/{id}/steps

**Errors Updated**:
1. Session not found → `agent_errors.session_not_found()`
2. Invalid cursor → `agent_errors.invalid_cursor()`

#### POST /agents/sessions/{id}/steps

**Errors Updated**:
1. Session not found → `agent_errors.session_not_found()`
2. Session not active → `agent_errors.session_not_active()`

**Example (Session Not Active)**:
```json
{
  "type": "https://httpstatuses.com/400",
  "title": "Session Not Active",
  "status": 400,
  "detail": "Session 'abc123' is not active (current status: cancelled). Only active sessions can accept new steps.",
  "instance": "/agents/sessions/abc123/steps",
  "extensions": {
    "error_code": "session_not_active",
    "session_id": "abc123",
    "current_status": "cancelled",
    "expected_status": "active"
  }
}
```

### Run Endpoints (`src/routers/agent_runs.py`)

#### POST /agent-runs

**Errors Updated**:
1. Session not found → `agent_errors.session_not_found()`

#### GET /agent-runs/{id}

**Errors Updated**:
1. Invalid run ID format → `agent_errors.raise_problem()` with custom error
2. Run not found → `agent_errors.run_not_found()`

**Example (Invalid Run ID)**:
```json
{
  "type": "https://httpstatuses.com/400",
  "title": "Invalid Run ID",
  "status": 400,
  "detail": "Run ID must be a valid UUID format, got: not-a-uuid",
  "instance": "/agent-runs/not-a-uuid",
  "extensions": {
    "error_code": "invalid_run_id",
    "run_id": "not-a-uuid"
  }
}
```

## Benefits

### 1. Machine-Readable Errors

Clients can programmatically handle errors:

```python
response = requests.post("/agents/sessions", ...)
if response.status_code == 409:
    error = response.json()
    if error["extensions"]["error_code"] == "duplicate_session":
        # Handle duplicate case
        session_id = error["extensions"]["session_id"]
        print(f"Session {session_id} already exists")
```

### 2. Consistent Structure

All errors follow same format:
- Always includes `type`, `title`, `status`, `detail`
- Always includes `error_code` in extensions
- Always includes relevant resource IDs in extensions
- Always includes `instance` (request path)

### 3. Better Debugging

Structured errors include context:

```json
{
  "extensions": {
    "error_code": "session_not_active",
    "session_id": "abc123",
    "current_status": "cancelled",
    "expected_status": "active"
  }
}
```

Developers can see:
- What went wrong (`session_not_active`)
- Which resource (`session_id`)
- Current state (`current_status`)
- Expected state (`expected_status`)

### 4. Standards Compliance

- ✅ RFC 7807: Problem Details for HTTP APIs
- ✅ Consistent with industry best practices
- ✅ Compatible with API gateways and monitoring tools
- ✅ Enables automatic error tracking and aggregation

## Error Code Mapping

| HTTP Status | Error Code | Description |
|------------|------------|-------------|
| 400 | `invalid_cursor` | Invalid pagination cursor format |
| 400 | `session_not_active` | Session in invalid state for operation |
| 400 | `invalid_request` | Malformed request |
| 404 | `session_not_found` | Session doesn't exist or no access |
| 404 | `step_not_found` | Step doesn't exist |
| 404 | `run_not_found` | Run doesn't exist or no access |
| 409 | `duplicate_session` | Session ID already exists |
| 500 | `database_error` | Database operation failed |
| 500 | `internal_error` | Unexpected server error |

## Testing

### Manual Testing

```bash
# Test session not found
curl -X GET http://localhost:8000/v1/agents/sessions/nonexistent \
  -H "Authorization: Bearer $TOKEN" | jq

# Expected:
{
  "type": "https://httpstatuses.com/404",
  "title": "Session Not Found",
  "status": 404,
  "detail": "Agent session 'nonexistent' does not exist or you don't have access to it.",
  "instance": "/agents/sessions/nonexistent",
  "extensions": {
    "error_code": "session_not_found",
    "session_id": "nonexistent"
  }
}

# Test invalid cursor
curl -X GET "http://localhost:8000/v1/agents/sessions?cursor=invalid" \
  -H "Authorization: Bearer $TOKEN" | jq

# Expected:
{
  "type": "https://httpstatuses.com/400",
  "title": "Invalid Cursor",
  "status": 400,
  "detail": "Invalid pagination cursor: 'invalid'. ...",
  "instance": "/agents/sessions",
  "extensions": {
    "error_code": "invalid_cursor",
    "cursor": "invalid"
  }
}
```

### Integration Tests

```python
async def test_session_not_found_error_format():
    response = await client.get("/v1/agents/sessions/nonexistent")
    assert response.status_code == 404
    
    error = response.json()
    assert error["type"] == "https://httpstatuses.com/404"
    assert error["title"] == "Session Not Found"
    assert error["status"] == 404
    assert "extensions" in error
    assert error["extensions"]["error_code"] == "session_not_found"
    assert error["extensions"]["session_id"] == "nonexistent"
    assert error["instance"] == "/agents/sessions/nonexistent"
```

## Client Usage Guide

### JavaScript/TypeScript

```typescript
interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  extensions?: Record<string, any>;
}

async function createSession(data: CreateSessionRequest) {
  try {
    const response = await fetch('/v1/agents/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      const error: ProblemDetail = await response.json();
      
      switch (error.extensions?.error_code) {
        case 'duplicate_session':
          console.log('Session already exists:', error.extensions.session_id);
          break;
        case 'database_error':
          console.error('Database error:', error.detail);
          break;
        default:
          console.error('Unknown error:', error);
      }
      
      throw new Error(error.detail);
    }
    
    return await response.json();
  } catch (error) {
    // Handle network errors
    throw error;
  }
}
```

### Python

```python
import requests

def create_session(data: dict) -> dict:
    response = requests.post('/v1/agents/sessions', json=data)
    
    if response.status_code >= 400:
        error = response.json()
        error_code = error.get('extensions', {}).get('error_code')
        
        if error_code == 'duplicate_session':
            session_id = error['extensions']['session_id']
            print(f"Session {session_id} already exists")
        elif error_code == 'database_error':
            print(f"Database error: {error['detail']}")
        else:
            print(f"Error: {error['detail']}")
        
        raise Exception(error['detail'])
    
    return response.json()
```

## Files Modified

### Created
- ✅ `src/errors/agents.py` (243 lines) - Error helper module

### Modified
- ✅ `src/routers/agent.py` - Replaced 9 HTTPException calls with standardized errors
- ✅ `src/routers/agent_runs.py` - Replaced 3 HTTPException calls with standardized errors

## Summary

**Phase 7 Complete**: ✅

- ✅ Created centralized error handling module
- ✅ Defined 11 structured error codes
- ✅ Implemented RFC7807 ProblemDetail format
- ✅ Updated all 12 error cases in agent endpoints
- ✅ Added convenience functions for common errors
- ✅ Included contextual metadata in all errors
- ✅ Consistent error structure across all endpoints

**Benefits**:
- Machine-readable error codes
- Consistent error structure
- Better debugging with context
- RFC 7807 compliance
- Client-friendly error handling

**Next Phase**: Integration Testing (Phase 8)
