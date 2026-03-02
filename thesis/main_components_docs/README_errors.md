# Errors Framework Reference

This document provides comprehensive reference documentation for the Errors framework implemented in the Cineca Agentic Platform. The Errors framework provides standardized error responses for Agents API using RFC7807 ProblemDetail format, with structured error codes and consistent error handling patterns.

## Overview

The Errors framework provides a standardized approach to error handling and reporting in the Agents API. It implements RFC7807 ProblemDetail format for structured error responses, with predefined error codes, consistent error formatting, and FastAPI integration.

## Architecture

### Core Components

The Errors framework consists of several key components:

- **Error Codes** (`AgentErrorCode`): Standardized error codes for agent operations
- **ProblemDetail Model**: RFC7807-compliant error response format
- **Convenience Functions**: Pre-built error raisers for common scenarios
- **FastAPI Integration**: HTTPException-based error responses

### RFC7807 ProblemDetail Format

The framework uses RFC7807 ProblemDetail format for all error responses:

```json
{
  "type": "https://httpstatuses.com/404",
  "title": "Session Not Found",
  "status": 404,
  "detail": "Agent session 'session-123' does not exist or you don't have access to it.",
  "instance": "https://api.example.com/agents/sessions/session-123",
  "extensions": {
    "error_code": "session_not_found",
    "session_id": "session-123"
  }
}
```

## Error Codes

### AgentErrorCode Enum

Standardized error codes for agent operations:

```python
class AgentErrorCode:
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

## Core Functions

### create_problem_detail()

Creates RFC7807 ProblemDetail instances:

```python
def create_problem_detail(
    status_code: int,
    title: str,
    detail: str,
    error_code: str | None = None,
    instance: str | None = None,
    extensions: dict[str, Any] | None = None,
) -> ProblemDetail:
    """
    Create RFC7807 ProblemDetail with consistent structure.

    Args:
        status_code: HTTP status code
        title: Short, human-readable summary
        detail: Human-readable explanation specific to this occurrence
        error_code: Machine-readable error code
        instance: URI reference identifying specific occurrence
        extensions: Additional error-specific data

    Returns:
        ProblemDetail instance
    """
```

### raise_problem()

Raises HTTPException with ProblemDetail:

```python
def raise_problem(
    status_code: int,
    title: str,
    detail: str,
    error_code: str | None = None,
    instance: str | None = None,
    extensions: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    """
    Raise HTTPException with RFC7807 ProblemDetail.

    Args:
        status_code: HTTP status code
        title: Short, human-readable summary
        detail: Human-readable explanation
        error_code: Machine-readable error code
        instance: URI reference identifying specific occurrence
        extensions: Additional error-specific data
        headers: Optional HTTP headers to include

    Raises:
        HTTPException with ProblemDetail as detail
    """
```

## Convenience Functions

### Resource Not Found Errors (404)

#### session_not_found()
Raises 404 for missing agent sessions:

```python
def session_not_found(session_id: str, instance: str | None = None) -> None:
    """Raise 404 for session not found."""
    raise_problem(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Session Not Found",
        detail=f"Agent session '{session_id}' does not exist or you don't have access to it.",
        error_code=AgentErrorCode.SESSION_NOT_FOUND,
        instance=instance,
        extensions={"session_id": session_id},
    )
```

**Example Response**:
```json
{
  "type": "https://httpstatuses.com/404",
  "title": "Session Not Found",
  "status": 404,
  "detail": "Agent session 'session-123' does not exist or you don't have access to it.",
  "extensions": {
    "error_code": "session_not_found",
    "session_id": "session-123"
  }
}
```

#### step_not_found()
Raises 404 for missing agent steps:

```python
def step_not_found(step_id: str, session_id: str | None = None, instance: str | None = None) -> None:
    """Raise 404 for step not found."""
    ext = {"step_id": step_id}
    if session_id:
        ext["session_id"] = session_id

    raise_problem(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Step Not Found",
        detail=f"Agent step '{step_id}' does not exist.",
        error_code=AgentErrorCode.STEP_NOT_FOUND,
        instance=instance,
        extensions=ext,
    )
```

#### run_not_found()
Raises 404 for missing agent runs:

```python
def run_not_found(run_id: str, instance: str | None = None) -> None:
    """Raise 404 for run not found."""
    raise_problem(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Run Not Found",
        detail=f"Agent run '{run_id}' does not exist or you don't have access to it.",
        error_code=AgentErrorCode.RUN_NOT_FOUND,
        instance=instance,
        extensions={"run_id": run_id},
    )
```

### State Validation Errors (400)

#### session_not_active()
Raises 400 when session is not in active state:

```python
def session_not_active(session_id: str, current_status: str, instance: str | None = None) -> None:
    """Raise 400 for session not in active state."""
    raise_problem(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Session Not Active",
        detail=f"Session '{session_id}' is not active (current status: {current_status}). Only active sessions can accept new steps.",
        error_code=AgentErrorCode.SESSION_NOT_ACTIVE,
        instance=instance,
        extensions={
            "session_id": session_id,
            "current_status": current_status,
            "expected_status": "active",
        },
    )
```

#### invalid_cursor()
Raises 400 for invalid pagination cursors:

```python
def invalid_cursor(cursor: str, reason: str | None = None, instance: str | None = None) -> None:
    """Raise 400 for invalid pagination cursor."""
    detail = f"Invalid pagination cursor: '{cursor}'"
    if reason:
        detail += f". {reason}"

    raise_problem(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Invalid Cursor",
        detail=detail,
        error_code=AgentErrorCode.INVALID_CURSOR,
        instance=instance,
        extensions={"cursor": cursor},
    )
```

### Conflict Errors (409)

#### duplicate_session()
Raises 409 for duplicate session IDs:

```python
def duplicate_session(session_id: str, instance: str | None = None) -> None:
    """Raise 409 for duplicate session ID."""
    raise_problem(
        status_code=status.HTTP_409_CONFLICT,
        title="Duplicate Session",
        detail=f"Session '{session_id}' already exists. Use a different session_id or omit it for auto-generation.",
        error_code=AgentErrorCode.DUPLICATE_SESSION,
        instance=instance,
        extensions={"session_id": session_id},
    )
```

### Server Errors (500)

#### database_error()
Raises 500 for database operation failures:

```python
def database_error(operation: str, error: str, instance: str | None = None) -> None:
    """Raise 500 for database errors."""
    raise_problem(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Database Error",
        detail=f"Failed to {operation}: {error}",
        error_code=AgentErrorCode.DATABASE_ERROR,
        instance=instance,
        extensions={"operation": operation},
    )
```

#### internal_error()
Raises 500 for internal server errors:

```python
def internal_error(detail: str, instance: str | None = None, extensions: dict[str, Any] | None = None) -> None:
    """Raise 500 for internal server errors."""
    raise_problem(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Internal Server Error",
        detail=detail,
        error_code=AgentErrorCode.INTERNAL_ERROR,
        instance=instance,
        extensions=extensions,
    )
```

## FastAPI Integration

### Router-Level Error Handling

```python
from fastapi import APIRouter, HTTPException
from src.errors.agents import session_not_found, database_error

router = APIRouter()

@router.get("/agents/sessions/{session_id}")
async def get_session(session_id: str):
    """Get agent session by ID."""
    try:
        session = await get_session_from_db(session_id)
        if not session:
            session_not_found(session_id)
        return session
    except DatabaseError as e:
        database_error("retrieve session", str(e))
```

### Global Exception Handlers

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.errors.agents import AgentErrorCode

app = FastAPI()

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Convert HTTPException to ProblemDetail format."""
    if hasattr(exc.detail, 'model_dump'):
        # Already a ProblemDetail
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail.model_dump(mode="json", exclude_none=True),
            headers=exc.headers
        )
    
    # Convert plain string detail to ProblemDetail
    from src.errors.agents import create_problem_detail
    problem = create_problem_detail(
        status_code=exc.status_code,
        title="Error",
        detail=str(exc.detail),
        error_code=AgentErrorCode.INTERNAL_ERROR
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump(mode="json", exclude_none=True),
        headers=exc.headers
    )
```

## Error Response Format

### Standard ProblemDetail Structure

All error responses follow RFC7807 ProblemDetail format:

```json
{
  "type": "URI",           // Error type URI
  "title": "string",       // Short, human-readable summary
  "status": number,        // HTTP status code
  "detail": "string",      // Human-readable explanation
  "instance": "URI",       // Specific occurrence identifier
  "extensions": {          // Additional error data
    "error_code": "string",    // Machine-readable error code
    "field_name": "value",     // Field-specific error details
    ...other extensions
  }
}
```

### Type URIs

Error types use HTTP status code URIs:

- `400`: `https://httpstatuses.com/400`
- `404`: `https://httpstatuses.com/404`
- `409`: `https://httpstatuses.com/409`
- `500`: `https://httpstatuses.com/500`

### Extensions Field

The `extensions` field contains additional error-specific data:

```json
{
  "extensions": {
    "error_code": "session_not_found",
    "session_id": "session-123",
    "current_status": "completed",
    "expected_status": "active"
  }
}
```

## Usage Patterns

### Error Handling in Service Layer

```python
from src.errors.agents import session_not_found, session_not_active

class AgentService:
    async def add_step(self, session_id: str, step_data: dict) -> dict:
        """Add a step to an agent session."""
        
        # Check if session exists
        session = await self.session_repo.get(session_id)
        if not session:
            session_not_found(session_id)
        
        # Check if session is active
        if session.status != "active":
            session_not_active(session_id, session.status)
        
        # Proceed with step creation
        return await self.step_repo.create(session_id, step_data)
```

### Validation Error Handling

```python
from pydantic import ValidationError
from src.errors.agents import raise_problem, AgentErrorCode

def validate_request_data(data: dict) -> None:
    """Validate request data and raise appropriate errors."""
    try:
        # Pydantic validation
        validated = RequestModel(**data)
    except ValidationError as e:
        # Convert to ProblemDetail
        raise_problem(
            status_code=400,
            title="Validation Error",
            detail="Request data failed validation",
            error_code=AgentErrorCode.INVALID_REQUEST,
            extensions={
                "validation_errors": e.errors(),
                "field_errors": {err["loc"][0]: err["msg"] for err in e.errors()}
            }
        )
```

### Database Error Handling

```python
from src.errors.agents import database_error

async def get_session(session_id: str) -> dict:
    """Get session with error handling."""
    try:
        return await self.db.query_one(
            "SELECT * FROM agent_sessions WHERE id = $1",
            [session_id]
        )
    except DatabaseConnectionError as e:
        database_error("connect to database", str(e))
    except DatabaseQueryError as e:
        database_error("execute query", str(e))
```

## Client Integration

### JavaScript/TypeScript Client

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

async function apiCall(endpoint: string): Promise<any> {
  try {
    const response = await fetch(endpoint);
    if (!response.ok) {
      const problem: ProblemDetail = await response.json();
      throw new ApiError(problem);
    }
    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      // Handle structured error
      console.error(`${error.problem.title}: ${error.problem.detail}`);
      if (error.problem.extensions?.error_code === 'session_not_found') {
        // Handle session not found specifically
        redirectToSessionList();
      }
    }
    throw error;
  }
}

class ApiError extends Error {
  constructor(public problem: ProblemDetail) {
    super(problem.detail);
  }
}
```

### Python Client

```python
from typing import Any
import httpx

class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
    
    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Get session with error handling."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/agents/sessions/{session_id}")
            
            if response.status_code >= 400:
                problem = response.json()
                raise ApiError(problem)
            
            return response.json()

class ApiError(Exception):
    def __init__(self, problem: dict[str, Any]):
        self.problem = problem
        self.status_code = problem.get("status", 500)
        self.error_code = problem.get("extensions", {}).get("error_code")
        super().__init__(problem.get("detail", "API Error"))
    
    def is_not_found(self) -> bool:
        """Check if this is a 404 error."""
        return self.status_code == 404
    
    def is_session_not_found(self) -> bool:
        """Check if session was not found."""
        return self.error_code == "session_not_found"
```

## Testing Error Responses

### Unit Testing Error Functions

```python
import pytest
from fastapi import HTTPException
from src.errors.agents import session_not_found, AgentErrorCode

def test_session_not_found():
    """Test session_not_found error function."""
    with pytest.raises(HTTPException) as exc_info:
        session_not_found("session-123")
    
    assert exc_info.value.status_code == 404
    problem = exc_info.value.detail
    assert problem.title == "Session Not Found"
    assert problem.status == 404
    assert problem.extensions["error_code"] == AgentErrorCode.SESSION_NOT_FOUND
    assert problem.extensions["session_id"] == "session-123"
```

### Integration Testing

```python
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_get_nonexistent_session():
    """Test API returns proper error for nonexistent session."""
    response = client.get("/agents/sessions/nonexistent")
    
    assert response.status_code == 404
    problem = response.json()
    assert problem["type"] == "https://httpstatuses.com/404"
    assert problem["title"] == "Session Not Found"
    assert problem["status"] == 404
    assert problem["extensions"]["error_code"] == "session_not_found"
    assert problem["extensions"]["session_id"] == "nonexistent"
```

## Error Monitoring

### Structured Logging

All errors are logged with structured data:

```json
{
  "event": "agent.error.session_not_found",
  "session_id": "session-123",
  "user_id": "user-456",
  "tenant_id": "tenant-789",
  "error_code": "session_not_found",
  "status_code": 404
}
```

### Metrics Collection

Error metrics can be collected for monitoring:

```python
# Prometheus counters
agent_errors_total = Counter(
    "agent_errors_total",
    "Total agent API errors",
    ["error_code", "status_code"]
)

# Usage
agent_errors_total.labels(
    error_code="session_not_found",
    status_code=404
).inc()
```

## Best Practices

### Error Message Guidelines

1. **Be Specific**: Include relevant identifiers (session_id, step_id, etc.)
2. **Be Actionable**: Explain what the client can do to resolve the error
3. **Be Consistent**: Use standardized error codes and titles
4. **Don't Leak Information**: Avoid exposing internal details or sensitive data

### Error Code Usage

1. **Machine-Readable**: Use error codes for programmatic error handling
2. **Hierarchical**: Group related errors with consistent prefixes
3. **Stable**: Don't change error codes once established
4. **Documented**: Maintain documentation for all error codes

### HTTP Status Code Selection

- **400 Bad Request**: Client sent invalid data or request
- **404 Not Found**: Requested resource doesn't exist
- **409 Conflict**: Request conflicts with current state
- **500 Internal Server Error**: Unexpected server error

### Extensions Usage

Use the `extensions` field for additional context:

```python
raise_problem(
    status_code=400,
    title="Validation Error",
    detail="Request contains invalid data",
    error_code="invalid_request",
    extensions={
        "field": "temperature",
        "provided_value": -5,
        "valid_range": "0-2"
    }
)
```

This comprehensive Errors framework provides consistent, structured error handling with excellent developer experience and client integration capabilities.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_errors.md