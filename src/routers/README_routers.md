# Routers Directory Documentation

## Overview

The `src/routers` directory contains FastAPI router modules that define the REST API endpoints for the Cineca Agentic Platform. These routers handle various aspects of the platform including model management, tenant administration, tool invocation, and process management.

This directory implements a modular architecture where each router focuses on a specific domain while sharing common patterns for authentication, error handling, observability, and data persistence.

## Architecture Principles

### Dual Routing Pattern
Several routers implement a "dual routing" pattern for backward compatibility:
- User-facing routes at `/v1/models/*` (visible in OpenAPI schema)
- Legacy admin routes at `/v1/admin/models/*` (hidden from schema)

### Authentication & Authorization
- **JWT-based authentication** using `UserInfo` from `src.routers.auth`
- **RBAC (Role-Based Access Control)** with scopes like `user:me`, `admin:all`, `tools:basic`
- **Permission checking** via `require_perms()` and `require_admin()` dependencies
- **Tenant isolation** with `X-Tenant-Id` headers for multi-tenant operations

### Error Handling
- **RFC 7807 Problem Details** format for structured error responses
- **HTTP status codes** following REST conventions
- **Correlation IDs** for request tracing (`X-Request-Id`, `X-Trace-Id`)
- **Provenance logging** for audit trails

### Data Persistence
- **PostgreSQL** as the authoritative data store via repositories
- **Redis** for caching and session management
- **Dual-write patterns** for gradual migration from legacy stores

### Observability
- **Structured logging** with correlation IDs
- **Prometheus metrics** for performance monitoring
- **Provenance events** for audit and debugging
- **ETag/conditional requests** for efficient caching

## Router Modules

### 1. model_instances.py

**Purpose**: Comprehensive model instance management with PostgreSQL backend, supporting CRUD operations, default model resolution, and instance testing.

**Key Features**:
- Dual routing for backward compatibility
- ETag-based caching for performance
- Idempotent instance creation
- Smart default model precedence (user → tenant → global)
- Instance testing with provider validation

#### Endpoints

##### GET /instances
**List model instances with filtering and pagination**

```http
GET /v1/models/instances?page_size=100&page_token=...&enabled=true&provider_id=...
Authorization: Bearer <token>
```

**Query Parameters**:
- `page_size`: Items per page (1-1000, default 100)
- `page_token`: Pagination token
- `tenant_id`: Filter by tenant
- `provider_id`: Filter by provider UUID
- `loaded`: Filter by loaded status
- `enabled`: Filter by enabled status

**Response**:
```json
{
  "items": [
    {
      "id": "uuid",
      "instance_name": "llama-3.2-3b",
      "provider_id": "ollama-local",
      "model_id": "llama3.2:3b-instruct",
      "enabled": true,
      "loaded": true,
      "capabilities": ["chat"],
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 1,
  "etag": "abc123",
  "next_page_token": null
}
```

**Permissions**: `user:me` or `admin:all`

##### POST /instances
**Create/load a new model instance (Admin only)**

```http
POST /v1/models/instances
Authorization: Bearer <admin-token>
Idempotency-Key: create-llama-$(date +%s)
Content-Type: application/json

{
  "instance_name": "llama-3.2-3b",
  "provider_id": "ollama-local",
  "model_id": "llama3.2:3b-instruct",
  "tenant_id": null,
  "enabled": true,
  "capabilities": ["chat"]
}
```

**Features**:
- Idempotent with `Idempotency-Key` header
- Auto-sets as user default if first instance
- Validates provider existence
- Records audit trail

##### GET /defaults
**Get default model with precedence resolution**

```http
GET /v1/models/defaults
Authorization: Bearer <token>
X-Tenant-Id: tenant-123
If-None-Match: "etag-value"
```

**Precedence Order**:
1. User default (user_id + tenant_id)
2. Tenant default (tenant_id only)
3. Global default (no tenant restriction)

**Response Headers**:
- `X-Default-Scope`: `user|tenant|global`
- `ETag`: For caching
- `Vary: Authorization, X-Tenant-Id`

##### PATCH /defaults
**Set default model at specified scope**

```http
PATCH /v1/models/defaults
Authorization: Bearer <token>
X-Default-Scope: user
Content-Type: application/json

{
  "chat": {
    "instance_id": "uuid"
  }
}
```

**Scopes**:
- `user`: Personal default (requires `user:me`)
- `tenant`: Organization default (requires `admin:all`)
- `global`: System-wide default (requires `admin:all`)

##### GET /instances/{id}
**Get detailed instance information**

```http
GET /v1/models/instances/uuid-here
Authorization: Bearer <token>
If-None-Match: "etag-value"
```

**Response**: Full instance metadata including configuration, capabilities, and audit timestamps.

##### DELETE /instances/{id}
**Remove model instance (Admin only)**

```http
DELETE /v1/models/instances/uuid-here
Authorization: Bearer <admin-token>
```

**Behavior**:
- Validates instance exists
- Removes from registry
- Clears any defaults pointing to this instance

##### POST /instances/{id}/tests
**Test model instance connectivity**

```http
POST /v1/models/instances/uuid-here/tests
Authorization: Bearer <token>
Content-Type: application/json

{
  "prompt": "Explain quantum computing in one sentence.",
  "temperature": 0.0,
  "max_tokens": 64
}
```

**Response**:
```json
{
  "model": "llama3.2:3b-instruct",
  "output": "Quantum computing uses quantum-mechanical phenomena...",
  "usage": {
    "prompt_tokens": 32,
    "completion_tokens": 28,
    "total_tokens": 60
  },
  "latency_ms": 1842.5,
  "trace_id": "trace-uuid",
  "event_id": "event-uuid"
}
```

### 2. model_management.py

**Purpose**: Legacy model management endpoints, now largely disabled in favor of `model_instances.py`. Contains provider management and some deprecated endpoints.

**Status**: Most endpoints are commented out. This file serves as a transition layer during migration to PostgreSQL-backed storage.

**Active Endpoints**:

#### Provider Management

##### GET /providers
**List configured LLM providers**

```http
GET /v1/admin/models/providers?page_size=100&page_token=...
Authorization: Bearer <admin-token>
```

**Features**:
- PostgreSQL-backed storage
- Secret redaction (API keys masked)
- Pagination and ETag caching
- Health status snapshots

##### POST /providers/register
**Register new LLM provider**

```http
POST /v1/admin/models/providers/register
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "name": "openai-gpt4",
  "type": "openai_compatible",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "model": "gpt-4-turbo"
}
```

**Idempotency**: Same config returns 200 OK instead of 409 Conflict.

##### PATCH /providers/{id}
**Update provider configuration**

```http
PATCH /v1/admin/models/providers/provider-id
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "model": "gpt-4o",
  "config": {
    "timeout": 30
  }
}
```

##### DELETE /providers/{id}
**Remove provider**

Auto-clears defaults pointing to this provider before deletion.

#### Default Provider Management

##### GET /providers/main
**Get resolved main provider**

##### PUT /providers/default
**Set provider as default**

```http
PUT /v1/admin/models/providers/default
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "provider_id": "openai-gpt4",
  "tenant_id": null
}
```

### 3. model_processes.py

**Purpose**: Lightweight process management for built-in AI models started by the platform.

**Key Features**:
- Process lifecycle tracking (start, heartbeat, stop, exit)
- Audit logging with correlation IDs
- Admin-only access with proper RBAC
- Integration with Redis runtime state and PostgreSQL audit logs

#### Endpoints

##### GET /
**List active and recent processes**

```http
GET /v1/admin/processes?artifact=llama3-8b&status=running&limit=50
Authorization: Bearer <admin-token>
```

**Query Parameters**:
- `artifact`: Model name filter
- `status`: Process status (running, starting, stopping, exited, stale)
- `since`: ISO 8601 timestamp filter
- `tenant_id`: Tenant filter
- `limit`: Max results (1-1000)

**Response**:
```json
{
  "processes": [
    {
      "id": "llama3-8b-1234",
      "process_id": "builtin:llama3-8b:abc123",
      "artifact": "llama3-8b",
      "pid": 42789,
      "port": 8080,
      "status": "running",
      "ts": "2025-10-21T10:30:00Z",
      "tenant_id": null,
      "manifest_version": "v1.2.3",
      "host": "localhost",
      "last_heartbeat": "2025-10-21T10:35:00Z"
    }
  ],
  "next_cursor": null
}
```

##### DELETE /{pid}
**Stop a running process**

```http
DELETE /v1/admin/processes/42789
Authorization: Bearer <admin-token>
X-Correlation-Id: debug-12345
```

**Behavior**:
- Idempotent (safe to call multiple times)
- Uses Redis stop-lock to prevent race conditions
- Graceful shutdown with signal escalation
- Records stop event in audit log

##### GET /history/manifests
**View manifest activation history**

```http
GET /v1/admin/processes/history/manifests?manifest_name=llama-bundle&status=active
Authorization: Bearer <admin-token>
```

##### GET /history/processes
**View process lifecycle events**

```http
GET /v1/admin/processes/history/processes?artifact=whisper&event=start&limit=100
Authorization: Bearer <admin-token>
```

### 4. models.py

**Purpose**: Lightweight LLM inference surface providing completions, embeddings, and chat endpoints.

**Key Features**:
- Provider-agnostic inference API
- Automatic default model resolution
- Rate limiting and observability
- Support for OpenAI-compatible and custom providers
- Tenant-aware request routing

#### Endpoints

##### GET /
**List available models**

```http
GET /v1/models?page_size=50&page_token=...
Authorization: Bearer <token>
If-None-Match: "etag-value"
```

**Response**: Paginated list of model metadata with capabilities and context windows.

##### POST /completions
**Text completion**

```http
POST /v1/models/completions
Authorization: Bearer <token>
Content-Type: application/json

{
  "model": "llama-3.2-3b",
  "prompt": "Explain quantum computing in one sentence.",
  "temperature": 0.0,
  "max_tokens": 64
}
```

**Response**:
```json
{
  "model": "llama3.2:3b-instruct",
  "output": "Quantum computing uses quantum-mechanical phenomena...",
  "usage": {
    "prompt_tokens": 32,
    "completion_tokens": 28,
    "total_tokens": 60
  },
  "latency_ms": 1842.5,
  "trace_id": "trace-uuid",
  "event_id": "event-uuid"
}
```

##### POST /embeddings
**Generate embeddings**

```http
POST /v1/models/embeddings
Authorization: Bearer <token>
Content-Type: application/json

{
  "model": "text-embedding-ada-002",
  "input": ["Hello world", "How are you?"]
}
```

##### POST /chat/completions
**Chat completion**

```http
POST /v1/models/chat/completions
Authorization: Bearer <token>
Content-Type: application/json

{
  "model": "gpt-4",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is AI?"}
  ],
  "temperature": 0.7
}
```

### 5. tenants.py

**Purpose**: Basic tenant management with CRUD operations.

**Note**: This is a simpler implementation. For production use, see `tenants_admin.py`.

#### Endpoints

##### GET /
**List tenants**

##### POST /
**Create tenant**

##### GET /{id}
**Get tenant details**

##### PATCH /{id}
**Update tenant**

##### DELETE /{id}
**Delete tenant**

### 6. tenants_admin.py

**Purpose**: Advanced tenant management with PostgreSQL backend, comprehensive RBAC, pagination, and caching.

**Key Features**:
- Full CRUD operations with audit trails
- ETag-based conditional requests
- Idempotent creation with conflict detection
- Dependency checking before deletion
- Server-generated tenant IDs

#### Endpoints

##### GET /
**List tenants with pagination**

```http
GET /v1/admin/tenants?page_size=100&page_token=...&tenant_id=...
Authorization: Bearer <admin-token>
If-None-Match: "etag-value"
```

**Features**:
- Pagination with Link headers (RFC 5988)
- ETag caching for performance
- Tenant filtering and search

##### POST /
**Create tenant**

```http
POST /v1/admin/tenants
Authorization: Bearer <admin-token>
X-Tenant-Id: admin-tenant
Content-Type: application/json

{
  "name": "ACME Corporation",
  "admin_email": "admin@acme.com",
  "metadata": {
    "region": "us-east-1",
    "tier": "premium"
  }
}
```

**Idempotency**: Same configuration returns 200 OK instead of 409 Conflict.

##### GET /{id}
**Get tenant by ID**

##### PATCH /{id}
**Update tenant (partial)**

```http
PATCH /v1/admin/tenants/tenant-uuid
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "name": "Updated Name",
  "metadata": {
    "tier": "enterprise"
  }
}
```

**Behavior**: Merges metadata, validates email format.

##### DELETE /{id}
**Delete tenant with dependency checking**

**Safety**: Fails with 409 Conflict if tenant has dependent resources (providers, jobs, etc.).

### 7. tools.py

**Purpose**: Generic MCP (Model Context Protocol) style tool dispatcher for executing modular tools.

**Key Features**:
- Dynamic tool discovery from `src.mcp.tools` package
- JSON Schema validation for tool inputs
- Idempotent execution with Redis caching
- Comprehensive audit trails
- Anti-enumeration security (404 instead of 403 for unauthorized access)

#### Endpoints

##### GET /
**List available tools**

```http
GET /v1/tools?page_size=50
Authorization: Bearer <token>
If-None-Match: "etag-value"
```

**Response**:
```json
{
  "items": [
    {
      "id": "graph.query@1",
      "name": "graph.query",
      "entrypoint": "invoke",
      "description": "Execute Cypher queries against the graph database",
      "input_schema": {
        "type": "object",
        "properties": {
          "cypher": {"type": "string"}
        },
        "required": ["cypher"]
      },
      "scopes": ["tools:basic"],
      "capabilities": ["reads_db"],
      "invokable": true,
      "long_running": false
    }
  ],
  "total": 1,
  "has_more": false
}
```

##### POST /{name}/invocations
**Invoke a tool**

```http
POST /v1/tools/graph.query/invocations
Authorization: Bearer <token>
Idempotency-Key: query-session-123
Content-Type: application/json

{
  "args": {
    "cypher": "MATCH (n) RETURN count(n) as total"
  },
  "timeout_seconds": 30
}
```

**Response**:
```json
{
  "name": "graph.query",
  "ok": true,
  "result": {"total": 42},
  "error": null,
  "duration_ms": 150,
  "trace_id": "trace-uuid",
  "event_id": "event-uuid"
}
```

**Features**:
- JSON Schema validation before execution
- Idempotent with 24-hour result caching
- Comprehensive error handling and observability
- Returns `Location` header pointing to result resource

##### GET /{name}/invocations/{id}
**Retrieve invocation result**

```http
GET /v1/tools/graph.query/invocations/event-uuid
Authorization: Bearer <token>
If-None-Match: "etag-value"
```

**Security**: Anti-enumeration - only owner or admin can access (404 for others).

##### GET /{name}
**Get tool metadata**

```http
GET /v1/tools/graph.query
Authorization: Bearer <token>
If-None-Match: "etag-value"
```

Returns detailed tool information including input schema and capabilities.

## Common Patterns

### Authentication Dependencies

```python
from src.routers.auth import get_current_user
from src.security.perm import require_perms, require_admin

# Require authenticated user
user: UserInfo = Depends(get_current_user)

# Require specific permissions
user: UserInfo = Depends(require_perms(["user:me"]))

# Require admin privileges
user: UserInfo = Depends(require_admin)
```

### Error Response Format

All endpoints use RFC 7807 Problem Details:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Invalid request parameters",
  "instance": "/v1/models/instances",
  "extensions": {
    "correlation_id": "req-123",
    "trace_id": "trace-456"
  }
}
```

### Pagination

```python
from src.utils.pagination import make_page

# Paginate results
page_items, next_token = make_page(items, page_size=page_size, page_token=page_token)
return {"items": page_items, "next_page_token": next_token}
```

### Provenance Logging

```python
from src.provenance import record_provenance

ev = record_provenance(
    actor="api",
    action="model.instances.list",
    resource="/models/instances",
    input={"filters": {...}},
    output={"count": len(items)},
    meta={"user": user.sub},
    success=True
)
```

### ETag Caching

```python
from src.utils.pagination import compute_etag

etag = compute_etag(response_data)
response.headers["ETag"] = etag
response.headers["Cache-Control"] = "private, max-age=30"
```

## Dependencies

### Core Dependencies

```python
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from db.postgres_control.database import get_db
```

### Platform-Specific Imports

```python
from src.config import settings
from src.provenance import record_provenance
from src.schemas.auth import UserInfo
from src.security.perm import require_perms
from src.utils.pagination import make_page, compute_etag
```

## Configuration

### Environment Variables

- `LLM_PROVIDER`: Default provider type ("demo", "openai", etc.)
- `SAFE_TOOLS`: Comma-separated list of safe tool names
- `EGRESS_ALLOWLIST`: Allowed outbound URLs for providers
- `RATE_LIMIT_DEFAULT_LIMIT`: Default rate limit per window
- `RATE_LIMIT_DEFAULT_WINDOW`: Rate limit window in seconds
- `ADMIN_DEFAULT_TENANT_ID`: Default admin tenant identifier

### Database Configuration

All routers expect PostgreSQL connectivity via `get_db()` dependency. Redis is used for caching and session management.

## Testing

### Unit Tests

Each router should have corresponding test files in `tests/` directory:

- `tests/api/test_model_instances.py`
- `tests/api/test_tenants.py`
- `tests/api/test_tools.py`

### Test Patterns

```python
import pytest
from fastapi.testclient import TestClient
from src.app import app

client = TestClient(app)

def test_list_instances():
    response = client.get("/v1/models/instances", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
```

### Mock Dependencies

```python
from unittest.mock import patch

@patch("src.repositories.models_repo.list_instances")
def test_with_mock(mock_list):
    mock_list.return_value = [...]
    # Test implementation
```

## Deployment Considerations

### Routing Configuration

Routers are mounted in `src.app.py`:

```python
from src.routers import model_instances, tenants_admin, tools

app.include_router(
    model_instances.router,
    prefix="/v1/models",
    tags=["models-instances"]
)

app.include_router(
    tenants_admin.router,
    prefix="/v1/admin/tenants",
    tags=["admin-tenants"]
)
```

### Middleware Requirements

- Authentication middleware for JWT validation
- CORS middleware for cross-origin requests
- Rate limiting middleware
- Request ID middleware for correlation

### Database Migrations

Ensure database schema is up-to-date:

```bash
# Run migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Add new table"
```

### Health Checks

All routers contribute to platform health via:

- Database connectivity checks
- Redis availability validation
- Provider endpoint reachability tests

## Security Considerations

### RBAC Matrix

| Endpoint | Scope | Description |
|----------|-------|-------------|
| Model listing | `user:me` | View available models |
| Model creation | `admin:all` | Create new model instances |
| Tenant management | `admin:all` | Full tenant CRUD |
| Tool invocation | `tools:basic` | Execute safe tools |
| Admin tools | `admin:all` | Execute privileged tools |

### Data Protection

- API keys and secrets are redacted in responses
- PII is logged only for audit purposes
- Tenant isolation prevents data leakage
- Idempotency prevents duplicate operations

### Rate Limiting

- Applied at route level using Redis-backed counters
- Configurable limits per tenant/user
- Burst allowance with refill rates

## Monitoring and Observability

### Metrics

- **Prometheus counters** for request counts by endpoint/status
- **Histograms** for latency tracking
- **Tool-specific metrics** for invocation success/failure

### Logging

- **Structured logging** with correlation IDs
- **Provenance events** for audit trails
- **Error tracking** with stack traces and context

### Tracing

- **Distributed tracing** with trace IDs
- **Request correlation** across service boundaries
- **Performance profiling** for slow endpoints

## Troubleshooting

### Common Issues

1. **401 Unauthorized**: Check JWT token validity and expiration
2. **403 Forbidden**: Verify user has required scopes
3. **404 Not Found**: Confirm endpoint exists and tenant has access
4. **409 Conflict**: Idempotency key collision or resource conflict
5. **500 Internal Error**: Check database connectivity and logs

### Debug Headers

Enable debug mode to see additional headers:

- `X-Debug: true` - Include stack traces in error responses
- `X-Correlation-Id: custom-id` - Override auto-generated correlation ID

### Health Endpoints

- `GET /health` - Overall platform health
- `GET /v1/admin/processes` - Process status
- `GET /v1/tools` - Tool discovery health

## Future Enhancements

### Planned Features

1. **GraphQL Support**: Alternative query interface for complex operations
2. **Webhook Integration**: Event-driven notifications for model updates
3. **Bulk Operations**: Batch processing for multiple instances/tenants
4. **Advanced Filtering**: Full-text search and complex query support
5. **API Versioning**: Support multiple API versions simultaneously

### Migration Path

1. **Phase 1**: PostgreSQL migration for core entities
2. **Phase 2**: Redis caching layer optimization
3. **Phase 3**: GraphQL API introduction
4. **Phase 4**: Legacy endpoint deprecation

This comprehensive documentation covers all aspects of the routers directory. Each router is designed for maintainability, security, and performance while following platform-wide patterns for consistency.