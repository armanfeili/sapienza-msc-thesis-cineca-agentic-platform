# Cineca Agentic Platform - API Documentation

This folder contains the OpenAPI 3.1.0 specifications for the **Cineca Agentic Platform**, a comprehensive AI-powered platform for managing LLM providers, agents, tools, jobs, and multi-tenant configurations.

---

## Table of Contents

- [Overview](#overview)
- [OpenAPI Files](#openapi-files)
- [API Versions](#api-versions)
- [Authentication](#authentication)
- [Base URLs](#base-urls)
- [API Categories](#api-categories)
  - [Health & Monitoring](#health--monitoring)
  - [Authentication](#authentication-1)
  - [Tools](#tools)
  - [Jobs](#jobs)
  - [AI Models & Instances](#ai-models--instances)
  - [Model Providers](#model-providers)
  - [Model Manifests](#model-manifests)
  - [Agent Sessions & Runs](#agent-sessions--runs)
  - [Tenant Management](#tenant-management)
  - [Process Management](#process-management)
  - [Batch Operations](#batch-operations)
  - [Export/Import](#exportimport)
  - [Internal/Admin Operations](#internaladmin-operations)
- [Common Response Codes](#common-response-codes)
- [Data Schemas](#data-schemas)
- [Rate Limiting](#rate-limiting)
- [Caching & Conditional Requests](#caching--conditional-requests)
- [Idempotency](#idempotency)
- [Examples](#examples)
- [Error Handling](#error-handling)

---

## Overview

The Cineca Agentic Platform provides a unified REST API for:

- **AI Model Management**: Register, configure, and manage multiple LLM providers (OpenAI, Ollama, Azure, etc.)
- **Agent Orchestration**: Create sessions, runs, and multi-step conversations with AI agents
- **Tool Invocation**: Discover and invoke MCP tools with full audit trails
- **Job Processing**: Manage background jobs with real-time SSE streaming
- **Multi-Tenancy**: Full tenant isolation with per-tenant configurations
- **Health Monitoring**: Comprehensive health checks for Kubernetes/Docker deployments

---

## OpenAPI Files

| File | Description |
|------|-------------|
| `openapi.json` | **Main/Complete API specification** - Full v1 API with all endpoints |
| `openapi_v1.json` | v1 API specification (subset) |
| `openapi_v2.json` | v2 API specification (preview/experimental) |
| `openapi_with_batch_export.json` | Extended API with batch and export operations |
| `openapi_admin_processes_preview.json` | Admin processes preview (empty/placeholder) |

---

## API Versions

### v1 (Stable)
The primary API version with full feature support:
- All production endpoints
- Full RBAC and multi-tenancy support
- Comprehensive health checks
- Complete audit logging

### v2 (Preview)
Experimental version with simplified interfaces:
- Currently contains health liveness probe only
- Used for testing new API patterns

---

## Authentication

The API uses **JWT Bearer Token** authentication.

### Security Schemes

```yaml
securitySchemes:
  HTTPBearer:
    type: http
    scheme: bearer
    bearerFormat: JWT
```

### Usage

```bash
# Include token in Authorization header
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     https://api.example.com/v1/endpoint
```

### Scopes

| Scope | Description |
|-------|-------------|
| `user:me` | Basic user access to own resources |
| `tools:basic` | Basic tool discovery and invocation |
| `tools:all` | Full tool access |
| `jobs:read` | Read job status |
| `admin:all` | Full administrative access |
| `internal:all` | Internal service-to-service access |

---

## Base URLs

```yaml
servers:
  - url: /v1  # Primary API version
  - url: /v2  # Preview API version
  - url: /{version}  # Dynamic version selection
```

---

## API Categories

### Health & Monitoring

Health endpoints for container orchestration and monitoring systems.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/` | API service metadata and documentation links |
| GET | `/v1/health/live` | Liveness probe (process alive check) |
| GET | `/v1/health/ready` | Readiness probe (dependencies check) |
| GET | `/v1/health/startup` | Startup probe with diagnostics |
| GET | `/v1/health/components` | All components health status |
| GET | `/v1/health/components/{name}` | Single component health status |
| GET | `/v2/health/live` | v2 liveness probe |

#### Liveness Probe (`/v1/health/live`)
- **Purpose**: Container crash detection for Kubernetes/Docker
- **Response**: Plain text `ok`
- **Latency**: < 1ms (no external calls)
- **No authentication required**

#### Readiness Probe (`/v1/health/ready`)
- **Purpose**: Traffic routing decisions
- **Checks**: PostgreSQL, Redis, Memgraph connectivity
- **Response Codes**: 200 (ready), 503 (not ready)
- **Fallback Mode**: `HEALTH_ALLOW_MG_HEALTH_FALLBACK=1`

#### Startup Probe (`/v1/health/startup`)
- **Purpose**: Deployment validation
- **Includes**: Rate limit config, migration status, environment info
- **Use Case**: CI/CD pipelines, provisioning scripts

---

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/auth/me` | Get current user claims from token |

#### Get Current User (`/v1/auth/me`)
Returns information from the authenticated JWT token:

```json
{
  "sub": "user123",
  "scopes": ["user:me", "jobs:read"],
  "roles": ["developer"],
  "permissions": ["jobs:read", "user:me"],
  "tenant_id": "tenant-abc"
}
```

---

### Tools

MCP (Model Context Protocol) tools discovery and invocation.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/tools` | List available tools |
| GET | `/v1/tools/{name}` | Get tool metadata and input schema |
| POST | `/v1/tools/{name}/invocations` | Invoke a tool |
| GET | `/v1/tools/{name}/invocations/{eid}` | Get invocation result |

#### Tool Discovery (`/v1/tools`)

```bash
curl -H "Authorization: Bearer $TOKEN" \
     https://api.example.com/v1/tools
```

Response:
```json
{
  "items": [
    {
      "id": "system.health@1",
      "name": "system.health",
      "entrypoint": "invoke",
      "description": "MCP Tool: system.health",
      "input_schema": {
        "type": "object",
        "properties": {},
        "additionalProperties": false
      },
      "scopes": ["tools:basic"],
      "capabilities": ["system_info"],
      "invokable": true,
      "long_running": false
    }
  ],
  "total": 1,
  "has_more": false
}
```

#### Tool Invocation (`POST /v1/tools/{name}/invocations`)

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: unique-key-123" \
     -d '{"args": {"cypher": "MATCH (n) RETURN count(n)"}}' \
     https://api.example.com/v1/tools/graph.query/invocations
```

Response includes:
- `trace_id` and `event_id` for provenance
- `duration_ms` for timing
- `Location` header pointing to invocation resource

---

### Jobs

Background job management with real-time streaming.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/jobs` | List your jobs |
| POST | `/v1/jobs` | Create a background job |
| GET | `/v1/jobs/{job_id}` | Get job status |
| DELETE | `/v1/jobs/{job_id}` | Cancel a job |
| GET | `/v1/jobs/{job_id}/events` | SSE stream of job events |

#### Create Job (`POST /v1/jobs`)

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: my-unique-key" \
     -d '{"type": "demo", "payload": {"duration_ms": 2000}}' \
     https://api.example.com/v1/jobs
```

Response:
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "queued",
  "owner": "user@example.com"
}
```

#### SSE Events (`GET /v1/jobs/{job_id}/events`)

Real-time job progress via Server-Sent Events:

```bash
curl -N -H "Authorization: Bearer $TOKEN" \
     "https://api.example.com/v1/jobs/{job_id}/events?retry_ms=5000"
```

Event stream format:
```
retry: 5000
id: 1
event: status
data: {"job_id": "123e4567...", "status": "running"}

: heartbeat 1
id: 2
event: end
data: {"job_id": "123e4567...", "final": "finished"}
```

Features:
- Resume capability via `Last-Event-ID` header
- Heartbeats every 15 seconds
- Auto-close after terminal state

#### Admin Jobs (`/v1/admin/jobs`)

Admin endpoints for system-wide job visibility:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/admin/jobs` | List all users' jobs |
| POST | `/v1/admin/jobs` | Create job (admin proxy) |
| DELETE | `/v1/admin/jobs/{job_id}` | Cancel any job |

---

### AI Models & Instances

Manage AI model instances across providers.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/models/instances` | List model instances |
| POST | `/v1/models/instances` | Load/create model instance (Admin) |
| GET | `/v1/models/instances/{instance_id}` | Get instance details |
| DELETE | `/v1/models/instances/{instance_id}` | Delete instance (Admin) |
| POST | `/v1/models/instances/{instance_id}/tests` | Test model with prompt |
| GET | `/v1/models/defaults` | Get default model (with precedence) |
| PATCH | `/v1/models/defaults` | Set default model |

#### Model Instance List (`GET /v1/models/instances`)

```bash
curl -H "Authorization: Bearer $TOKEN" \
     "https://api.example.com/v1/models/instances?provider_id=ollama-local&enabled=true"
```

Response:
```json
{
  "items": [
    {
      "id": "6491b020-bbe3-47fe-991e-e7c21a15260c",
      "instance_name": "llama-3.2-3b",
      "provider_id": "ollama-local",
      "model_id": "llama3.2:3b-instruct",
      "tenant_id": null,
      "enabled": true,
      "loaded": true,
      "capabilities": ["chat"]
    }
  ],
  "total": 1,
  "has_more": false
}
```

#### Default Model Resolution (`GET /v1/models/defaults`)

Precedence order:
1. **User default** - Personal preference
2. **Tenant default** - Organization-wide
3. **Global default** - System fallback

Response includes `X-Default-Scope` header indicating which level was used.

#### Test Model (`POST /v1/models/instances/{instance_id}/tests`)

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Explain quantum computing in one sentence.", "temperature": 0.0, "max_tokens": 64}' \
     "https://api.example.com/v1/models/instances/{id}/tests"
```

---

### Model Providers

Configure external LLM backends.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/admin/models/providers` | List LLM providers |
| POST | `/v1/admin/models/providers/register` | Register new provider |
| GET | `/v1/admin/models/providers/main` | Get default provider |
| GET | `/v1/admin/models/providers/{provider_id}` | Get provider details |
| PATCH | `/v1/admin/models/providers/{provider_id}` | Update provider |
| DELETE | `/v1/admin/models/providers/{provider_id}` | Delete provider |
| PUT | `/v1/admin/models/providers/default` | Set default provider |

#### Register Provider (`POST /v1/admin/models/providers/register`)

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "openai-main",
       "type": "openai_compatible",
       "base_url": "https://api.openai.com/v1",
       "api_key": "sk-xxx",
       "model": "gpt-4",
       "tenant_id": null
     }' \
     "https://api.example.com/v1/admin/models/providers/register"
```

Features:
- **Tenant scoping**: `tenant_id: null` = global, specific ID = tenant-only
- **Idempotent**: Same `(tenant_id, name)` with identical config returns 200 OK
- **Secret redaction**: `api_key` never returned in responses

---

### Model Manifests

Manage built-in model manifest deployments.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/admin/models/manifests/builtins` | List built-in manifests |
| POST | `/v1/admin/models/manifests/builtins/staged` | Stage remote manifest |
| POST | `/v1/admin/models/manifests/builtins/activations` | Activate staged manifest |
| POST | `/v1/admin/models/manifests/builtins/rollbacks` | Rollback to previous |
| GET | `/v1/admin/models/manifests/builtins/history` | Activation history |

Workflow:
1. **Stage**: Fetch and validate remote manifest
2. **Review**: Preview staged changes
3. **Activate**: Promote staged to active
4. **Rollback**: Revert if issues occur

---

### Agent Sessions & Runs

Multi-turn conversations and one-off agent executions.

#### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/agents/sessions` | Create a new session |
| GET | `/v1/agents/sessions` | List sessions |
| GET | `/v1/agents/sessions/{session_id}` | Get session details |
| DELETE | `/v1/agents/sessions/{session_id}` | Cancel session |
| GET | `/v1/agents/sessions/{session_id}/steps` | List session steps |
| POST | `/v1/agents/sessions/{session_id}/steps` | Add step to session |

#### Create Session (`POST /v1/agents/sessions`)

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Research Assistant",
       "model": "gpt-4",
       "temperature": 0.7,
       "max_steps": 10,
       "tools": ["web.search", "file.read"]
     }' \
     "https://api.example.com/v1/agents/sessions"
```

#### Runs (One-off Executions)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/agent-runs` | Create and execute a run |
| GET | `/v1/agent-runs/{run_id}` | Get run details |
| GET | `/v1/agent-runs/{run_id}/steps` | Get execution steps |

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "prompt": "Analyze the market trends for Q4 2024",
       "model": "gpt-4"
     }' \
     "https://api.example.com/v1/agent-runs"
```

---

### Tenant Management

Multi-tenant organization management (Admin only).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/admin/tenants` | List tenants |
| POST | `/v1/admin/tenants` | Create tenant |
| GET | `/v1/admin/tenants/{tenant_id}` | Get tenant |
| PATCH | `/v1/admin/tenants/{tenant_id}` | Update tenant |
| DELETE | `/v1/admin/tenants/{tenant_id}` | Delete tenant |

#### Create Tenant (`POST /v1/admin/tenants`)

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -H "X-Tenant-Id: tenant-admin-root" \
     -d '{
       "name": "ACME Corporation",
       "admin_email": "admin@acme.com",
       "metadata": {
         "region": "us-east-1",
         "tier": "premium"
       }
     }' \
     "https://api.example.com/v1/admin/tenants"
```

Features:
- **Auto-generated ID**: Format `tenant-xxxxxxxx`
- **Idempotent**: Identical data returns existing tenant
- **Conflict detection**: 409 if name exists with different config
- **Dependency checking**: Cannot delete tenant with active resources

---

### Process Management

Monitor and control running model processes.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/admin/processes` | List active processes |
| DELETE | `/v1/admin/processes/{pid}` | Stop a process |
| GET | `/v1/admin/processes/history/manifests` | Manifest activation history |
| GET | `/v1/admin/processes/history/processes` | Process lifecycle events |

#### List Processes (`GET /v1/admin/processes`)

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     "https://api.example.com/v1/admin/processes?artifact=llama3-8b&status=running"
```

Response includes:
- Process ID, PID, port
- Artifact name, status
- Manifest version
- Last heartbeat timestamp

---

### Batch Operations

Efficient bulk operations for multiple resources.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/batch/operations` | Execute mixed batch operations |
| POST | `/v1/batch/models/bulk-create` | Bulk create models |
| DELETE | `/v1/batch/models/bulk-delete` | Bulk delete models |
| POST | `/v1/batch/tools/bulk-create` | Bulk create tools |

#### Batch Operations (`POST /v1/batch/operations`)

```json
{
  "operations": [
    {
      "operation": "create",
      "resourceType": "model",
      "data": {
        "instanceId": "model-1",
        "modelName": "gpt-4",
        "providerId": "provider-1"
      }
    },
    {
      "operation": "delete",
      "resourceType": "model",
      "resourceId": "old-model-1"
    }
  ],
  "continueOnError": true
}
```

Limits:
- Maximum 100 operations per batch
- Operations processed sequentially

---

### Export/Import

Configuration backup and migration.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/export/export` | Export platform configurations |
| POST | `/v1/export/export/tenant/{tenant_id}` | Export single tenant |
| POST | `/v1/export/import` | Import configurations |

#### Export (`POST /v1/export/export`)

```json
{
  "includeModels": true,
  "includeProviders": true,
  "includeTools": true,
  "includeAgents": true,
  "format": "json"
}
```

Formats:
- `json`: Single JSON file
- `zip`: ZIP archive with separate files

#### Import (`POST /v1/export/import`)

```json
{
  "data": { "...exported data..." },
  "overwriteExisting": false,
  "skipErrors": true,
  "dryRun": false
}
```

---

### Internal/Admin Operations

Internal endpoints for service-to-service communication.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/internal/ops/auto-start-override` | Override auto-start behavior |
| GET | `/v1/internal/ops/preview-staged` | Preview staged manifests |
| POST | `/v1/internal/db/jobs` | Create DB maintenance job |
| GET | `/v1/internal/db/jobs/{job_id}` | Get DB job status |
| DELETE | `/v1/internal/db/jobs/{job_id}` | Cancel DB job |
| GET | `/v1/internal/db/counts` | Get database counts |

Admin proxies are also available:
- `/v1/admin/ops/auto-start-override`
- `/v1/admin/ops/preview-staged`
- `/v1/admin/db/jobs`
- `/v1/admin/db/counts`

---

## Common Response Codes

| Code | Description |
|------|-------------|
| 200 | OK - Request successful |
| 201 | Created - Resource created |
| 202 | Accepted - Request accepted for processing |
| 204 | No Content - Successful deletion |
| 304 | Not Modified - ETag matched, use cached version |
| 400 | Bad Request - Invalid input or business logic error |
| 401 | Unauthorized - Missing or invalid token |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 409 | Conflict - Resource conflict |
| 422 | Unprocessable Entity - Validation error |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error - Unexpected failure |
| 501 | Not Implemented - Feature unavailable |
| 503 | Service Unavailable - Dependencies unavailable |

---

## Data Schemas

### Key Models

#### ActionResponse
```json
{
  "ok": true,
  "message": "Operation completed successfully",
  "details": {},
  "trace_id": "abc-123",
  "event_id": "evt-456"
}
```

#### ProblemDetails (RFC 7807)
```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Resource not found",
  "instance": "/v1/resource/123",
  "traceId": "trace-abc-123"
}
```

#### UserInfo
```json
{
  "sub": "user123",
  "username": "deprecated",
  "tenant_id": "tenant-abc",
  "scopes": ["user:me"],
  "roles": ["developer"],
  "permissions": ["read", "write"]
}
```

#### ToolInfo
```json
{
  "name": "graph.query",
  "module": null,
  "entrypoint": "invoke",
  "description": "Execute Cypher queries",
  "input_schema": {"type": "object"},
  "scopes": ["tools:basic"],
  "namespace": false,
  "invokable": true,
  "long_running": false
}
```

#### JobResponse
```json
{
  "id": "uuid",
  "type": "demo",
  "status": "running",
  "owner": "user@example.com",
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:01:00Z",
  "result": {}
}
```

#### SessionInfo
```json
{
  "session_id": "sess-123",
  "status": "active"
}
```

#### Tenant
```json
{
  "id": "tenant-abc",
  "name": "ACME Corporation",
  "admin_email": "admin@acme.com",
  "metadata": {},
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z"
}
```

---

## Rate Limiting

The API enforces rate limits to prevent abuse:

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/v1/auth/me` | 30 requests | 60 seconds |
| `/v1/tools/*/invocations` | 5 requests | (configurable) |

Rate limit headers:
- `RateLimit-Limit`: Maximum requests allowed
- `RateLimit-Remaining`: Requests remaining
- `RateLimit-Reset`: Unix timestamp when limit resets

Configuration:
- `RATE_LIMIT_MODE`: `prod` (strict) or `test` (relaxed)
- `RATE_LIMIT_BACKEND`: `redis` (recommended) or `memory`

---

## Caching & Conditional Requests

The API supports HTTP caching for efficiency.

### ETag Support

Request with If-None-Match:
```bash
curl -H "Authorization: Bearer $TOKEN" \
     -H 'If-None-Match: "abc123"' \
     https://api.example.com/v1/tools
```

Response: `304 Not Modified` if unchanged.

### Cache-Control Headers

```
Cache-Control: private, max-age=30
Vary: Authorization
ETag: W/"abc123def456"
```

---

## Idempotency

Prevent duplicate operations with idempotency keys.

### Usage

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Idempotency-Key: unique-operation-123" \
     -H "Content-Type: application/json" \
     -d '{"type": "demo"}' \
     https://api.example.com/v1/jobs
```

### Behavior

| Scenario | Response Code | Header |
|----------|---------------|--------|
| First request | 201/202 | `Idempotency-Replayed: false` |
| Replay (same key) | 200 | `Idempotency-Replayed: true` |

Idempotency keys are cached for **24 hours**.

---

## Examples

### Complete Workflow: Create and Monitor a Job

```bash
# 1. Create a job
JOB_RESPONSE=$(curl -s -X POST \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"type": "demo", "payload": {"duration_ms": 5000}}' \
     https://api.example.com/v1/jobs)

JOB_ID=$(echo $JOB_RESPONSE | jq -r '.id')

# 2. Poll for status
curl -H "Authorization: Bearer $TOKEN" \
     https://api.example.com/v1/jobs/$JOB_ID

# 3. Or stream events via SSE
curl -N -H "Authorization: Bearer $TOKEN" \
     https://api.example.com/v1/jobs/$JOB_ID/events
```

### Complete Workflow: Agent Session

```bash
# 1. Create session
SESSION=$(curl -s -X POST \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "Research", "model": "gpt-4"}' \
     https://api.example.com/v1/agents/sessions)

SESSION_ID=$(echo $SESSION | jq -r '.session_id')

# 2. Add user message
curl -X POST \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"type": "user", "content": "What is machine learning?"}' \
     https://api.example.com/v1/agents/sessions/$SESSION_ID/steps

# 3. List steps to see response
curl -H "Authorization: Bearer $TOKEN" \
     https://api.example.com/v1/agents/sessions/$SESSION_ID/steps
```

### Register Provider and Create Model Instance

```bash
# 1. Register provider
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "ollama-local",
       "type": "openai_compatible",
       "base_url": "http://localhost:11434/v1"
     }' \
     https://api.example.com/v1/admin/models/providers/register

# 2. Create model instance
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "llama-3.2-3b",
       "provider_id": "ollama-local",
       "model_id": "llama3.2:3b-instruct",
       "capabilities": ["chat"]
     }' \
     https://api.example.com/v1/models/instances

# 3. Set as default
curl -X PATCH -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"chat": {"name": "llama-3.2-3b"}}' \
     https://api.example.com/v1/models/defaults
```

---

## Error Handling

### ProblemDetails Format (RFC 7807)

All errors follow the RFC 7807 Problem Details format:

```json
{
  "type": "https://example.com/probs/validation",
  "title": "Validation Error",
  "status": 422,
  "detail": "Request validation failed",
  "instance": "/v1/admin/tenants",
  "extensions": {
    "correlation_id": "req-123",
    "errors": [
      {
        "type": "value_error",
        "loc": ["body", "admin_email"],
        "msg": "value is not a valid email address"
      }
    ]
  }
}
```

### Anti-Enumeration

For security, many endpoints return `404 Not Found` instead of `403 Forbidden` when a resource exists but the caller lacks permission. This prevents resource ID enumeration attacks.

### Correlation IDs

All responses include correlation IDs for debugging:
- `X-Request-Id`: Unique request identifier
- `X-Trace-Id`: Distributed trace identifier
- `X-Event-Id`: Provenance event identifier

---

## Additional Resources

- **Interactive Documentation**: Available at `/v1/docs` when enabled
- **Metrics**: Available at `/metrics` when enabled
- **OpenAPI Spec**: This folder contains complete specifications

---

## Changelog

For API changes and versioning information, see the main project [CHANGELOG.md](../CHANGELOG.md).

---

## License

See the main project [LICENSE](../LICENSE) file.
