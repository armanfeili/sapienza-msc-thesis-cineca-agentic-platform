# Schemas Package (`src/schemas/`)

The schemas package provides comprehensive Pydantic data models for the Cineca Agentic Platform API, serving as the canonical source of truth for all request/response structures across the platform.

## Architecture Overview

The schemas package follows strict architectural principles:

- **Single Source of Truth**: All Pydantic models are defined here, never in routers
- **Canonical Models**: Every API endpoint imports models from this package
- **Type Safety**: Comprehensive validation and type hints throughout
- **Documentation**: Rich field descriptions and examples for API documentation
- **Validation**: Input validation, normalization, and business rule enforcement

## Package Organization

### Core Modules

| Module | Purpose | Key Models |
|--------|---------|------------|
| `agents.py` | Agent session and run management | `CreateSessionRequest`, `RunResponse`, `ExecutionMetrics` |
| `auth.py` | Authentication/authorization | `UserInfo` |
| `batch.py` | Bulk operations | `BatchRequest`, `BatchResponse` |
| `jobs.py` | Background job processing | `JobCreateRequest`, `JobResponse` |
| `models.py` | LLM model management | `LoadInstanceRequest`, `ModelInfo`, `TestResponse` |
| `providers.py` | LLM provider configuration | `RegisterProviderRequest`, `Provider`, `ProviderHealth` |
| `tenants.py` | Multi-tenant management | `CreateTenantRequest`, `Tenant` |
| `tools.py` | MCP tool definitions | `ToolInfo`, `ToolInvokeRequest` |

### Import Architecture

```python
# Package-level imports for convenience
from src.schemas import (
    CreateSessionRequest,
    RunResponse,
    JobCreateRequest,
    Provider,
    # ... all commonly used schemas
)

# Module-specific imports when needed
from src.schemas.agents import ExecutionMetrics
from src.schemas.models import LoadInstanceRequest
```

## Core Design Patterns

### Request/Response Separation

Each API operation has distinct request and response models:

```python
class CreateSessionRequest(BaseModel):
    """Input validation and defaults"""
    prompt: str | None = None
    temperature: float = Field(0.2, ge=0.0, le=2.0)

class SessionResponse(BaseModel):
    """Output structure with computed fields"""
    session_id: UUID
    status: str
    created_at: datetime
    etag: str  # Computed server-side
```

### Field Validation and Normalization

Comprehensive validation with custom validators:

```python
@field_validator("type")
@classmethod
def validate_type(cls, v: str) -> str:
    allowed = {"message", "user", "assistant", "tool", "system", "error"}
    if v not in allowed:
        raise ValueError(f"type must be one of {allowed}")
    return v
```

### Model Configuration

Consistent Pydantic configuration across all models:

```python
model_config = ConfigDict(
    from_attributes=True,  # SQLAlchemy ORM support
    populate_by_name=True, # Allow field aliases
    extra="allow"          # Provider-specific extensions
)
```

## Agent Schemas (`agents.py`)

### Session Management

**CreateSessionRequest**: Agent session initialization with configuration
```python
{
    "session_id": "uuid-optional",
    "prompt": "Natural language task description",
    "manager": "planner-llm-name",
    "preferred_workers": ["worker-llm-1", "worker-llm-2"],
    "llm_preferences": {"tool.category": "preferred-llm"},
    "agent_role": "researcher",
    "tools": ["graph.query", "output.format"],
    "temperature": 0.2,
    "max_steps": 8,
    "metadata": {"custom": "data"}
}
```

**SessionResponse**: Complete session state with computed fields
```python
{
    "session_id": "uuid",
    "user_id": "user-identifier",
    "tenant_id": "tenant-scope",
    "status": "active|completed|cancelled|failed",
    "manager": "planner-llm",
    "preferred_workers": ["worker-llms"],
    "llm_preferences": {"tool": "llm"},
    "agent_role": "researcher",
    "tools": ["allowed-tools"],
    "temperature": 0.2,
    "max_steps": 8,
    "metadata": {"session": "data"},
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:30:00Z",
    "last_step_id": "uuid",
    "etag": "cache-token"
}
```

### Step Orchestration

**OrchestrationStepInput/Output**: Detailed execution tracking
```python
{
    "type": "step",
    "step_id": "1",
    "action": "graph.query",
    "input": {"cypher": "MATCH (n) RETURN count(n)"},
    "started_at": "2025-01-15T10:30:01Z",
    "finished_at": "2025-01-15T10:30:02Z",
    "latency_ms": 1500
}
```

### TODO Management

**TodoItem**: Agent planning and task tracking
```python
{
    "task": "Analyze user query and determine required data sources",
    "status": "completed",
    "expect_evidence": true,
    "evidence": ["step-1", "step-2"],
    "meta": {"tool_hints": ["graph.query"]},
    "requires_llm_planning": true,
    "nested_steps": ["Validate query syntax", "Execute query"],
    "fallback_mode": false
}
```

### Performance Metrics

**ExecutionMetrics**: Comprehensive performance tracking
```python
{
    "overall_ms": 5000,
    "llm": [
        {
            "model": "gpt-4o",
            "latency_ms": 1200,
            "success": true,
            "input_tokens": 150,
            "output_tokens": 300,
            "total_tokens": 450,
            "purpose": "todo_creation"
        }
    ],
    "tools": [
        {
            "name": "graph.query",
            "latency_ms": 800,
            "success": true
        }
    ],
    "first_llm_call_ms": 1200,
    "total_llm_calls": 3,
    "tool_calls": 2,
    "planning_ms": 800,
    "execution_ms": 3200
}
```

### Run Execution

**CreateRunRequest**: Agent execution with full configuration
```python
{
    "session_id": "uuid",
    "prompt": "Analyze sales data for Q4",
    "manager": "gpt-4o",
    "preferred_workers": ["claude-3", "llama3"],
    "llm_preferences": {"graph.analytics": "claude-3"},
    "agent_role": "analyst",
    "tools": ["graph.query", "graph.analytics"],
    "temperature": 0.2,
    "max_steps": 8,
    "metadata": {"report_type": "quarterly"},
    "force_full_agentic": false
}
```

**RunResponse**: Complete execution results with provenance
```python
{
    "run_id": "uuid",
    "session_id": "uuid",
    "user_id": "user-id",
    "tenant_id": "tenant-id",
    "model": "gpt-4o",
    "manager": "gpt-4o",
    "latency_ms": 5000,
    "trace_id": "trace-uuid",
    "request_id": "req-uuid",
    "event_id": "evt-uuid",
    "status": "succeeded",
    "started_at": "2025-01-15T10:30:00Z",
    "finished_at": "2025-01-15T10:30:05Z",
    "output": {"analysis": "Q4 sales increased 15%"},
    "steps": [...],  // Orchestration steps
    "todos": [...],  // Completed tasks
    "metrics": {...}, // Performance data
    "errors": [],
    "warnings": [],
    "degraded": false,
    "used_fallback": false
}
```

## Authentication Schemas (`auth.py`)

### User Identity

**UserInfo**: JWT-extracted user context
```python
{
    "sub": "user-uuid",
    "username": null,  // Deprecated
    "tenant_id": "tenant-uuid",
    "scopes": ["read:agents", "write:agents"],
    "roles": ["user", "admin"],
    "permissions": ["agents.create", "agents.read"]
}
```

## Batch Operations (`batch.py`)

### Bulk Processing

**BatchRequest**: Multi-operation transactions
```python
{
    "operations": [
        {
            "operation": "create",
            "resourceType": "model",
            "resourceId": null,
            "data": {"name": "gpt-4o", "provider_id": "uuid"}
        },
        {
            "operation": "update",
            "resourceType": "tenant",
            "resourceId": "tenant-uuid",
            "data": {"name": "Updated Name"}
        }
    ],
    "continueOnError": false,
    "atomic": false
}
```

**BatchResponse**: Operation results with error handling
```python
{
    "totalOperations": 2,
    "successCount": 1,
    "failureCount": 1,
    "results": [
        {
            "operation": "create",
            "resourceType": "model",
            "success": true,
            "statusCode": 201,
            "data": {"id": "model-uuid"}
        },
        {
            "operation": "update",
            "resourceType": "tenant",
            "success": false,
            "statusCode": 404,
            "error": "Tenant not found"
        }
    ]
}
```

## Job Processing (`jobs.py`)

### Background Jobs

**JobCreateRequest**: Asynchronous task submission
```python
{
    "type": "agent.run",
    "payload": {
        "session_id": "uuid",
        "prompt": "Process data",
        "max_steps": 10
    }
}
```

**JobResponse**: Job status and results
```python
{
    "id": "job-uuid",
    "type": "agent.run",
    "status": "finished",
    "owner_sub": "user@example.com",
    "tenant_id": "tenant-uuid",
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:30:10Z",
    "started_at": "2025-01-15T10:30:01Z",
    "completed_at": "2025-01-15T10:30:10Z",
    "result": {"status": "success", "output": "data"},
    "priority": 0,
    "queue_latency_ms": 1000,
    "exec_latency_ms": 9000,
    "etag": "cache-token"
}
```

## Model Management (`models.py`)

### Instance Lifecycle

**LoadInstanceRequest**: Model instance creation
```python
{
    "provider_id": "provider-uuid",
    "instance_name": "gpt-4o-production",
    "model_id": "gpt-4o",
    "model_uri": null,
    "tenant_id": null,
    "parameters": {
        "temperature": 0.7,
        "max_tokens": 4096,
        "top_p": 1.0
    },
    "context_window": 128000,
    "modalities": ["text", "vision", "audio"],
    "description": "GPT-4 Omni for production workloads"
}
```

**ModelInfo**: Unified model catalog entry
```python
{
    "id": "instance-uuid",
    "name": "gpt-4o-production",
    "provider_id": "provider-uuid",
    "model_id": "gpt-4o",
    "provider": "openai",
    "context_window": 128000,
    "modalities": ["text", "vision", "audio"],
    "description": "Latest GPT-4 Omni model",
    "enabled": true,
    "loaded": true,
    "default": false
}
```

### Model Testing

**TestRequest**: Health check and diagnostics
```python
{
    "model": "gpt-4o",
    "prompt": "Explain quantum computing in one sentence.",
    "temperature": 0.0,
    "max_tokens": 32,
    "one_sentence": true,
    "metadata": {"test_type": "health_check"}
}
```

**TestResponse**: Test results with metrics
```python
{
    "model": "gpt-4o",
    "output": "Quantum computing harnesses quantum-mechanical phenomena to solve certain problems faster than classical computers.",
    "usage": {
        "prompt_tokens": 22,
        "completion_tokens": 16,
        "total_tokens": 38
    },
    "trace_id": "trace-uuid",
    "event_id": "event-uuid",
    "provider": "openai",
    "provider_base_url": "https://api.openai.com/v1",
    "latency_ms": 1842.5,
    "parameters": {"temperature": 0.0, "max_tokens": 32}
}
```

### Completions and Embeddings

**CompletionRequest**: Text generation
```python
{
    "prompt": "Write a haiku about programming",
    "model": "gpt-4o",
    "temperature": 0.7,
    "max_tokens": 256,
    "metadata": {"purpose": "creative"}
}
```

**EmbeddingRequest**: Vector generation
```python
{
    "input": "Machine learning is transforming industries",
    "model": "text-embedding-ada-002"
}
```

## Provider Management (`providers.py`)

### Provider Registration

**RegisterProviderRequest**: LLM provider setup
```python
{
    "name": "production-openai",
    "type": "openai_compatible",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4",
    "api_key": "sk-proj-...",
    "tenant_id": null,
    "config": {
        "timeouts": {"connect": 5.0, "read": 30.0},
        "headers": {"X-Custom-Header": "value"},
        "tls": {"verify": true}
    }
}
```

**Provider**: Complete provider configuration
```python
{
    "id": "provider-uuid",
    "name": "production-openai",
    "type": "openai_compatible",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4",
    "tenant_id": null,
    "config": {
        "api_key": "[REDACTED]",
        "timeouts": {"connect": 5.0, "read": 30.0},
        "paths": {"chat_completions": "/v1/chat/completions"},
        "request_templates": {"chat": "..."},
        "response_extract": {"text_jmespath": "choices[0].message.content"}
    },
    "has_api_key": true,
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:30:00Z",
    "health": {
        "reachable": true,
        "status": 200,
        "last_check": 1642150200.0,
        "latency_ms": 450
    }
}
```

### Health Monitoring

**ProviderHealth**: Cached health status
```python
{
    "reachable": true,
    "status": 200,
    "last_check": 1642150200.0,
    "latency_ms": 450,
    "error": null
}
```

## Tenant Management (`tenants.py`)

### Multi-Tenant Configuration

**CreateTenantRequest**: Tenant creation
```python
{
    "name": "ACME Corporation",
    "admin_email": "admin@example.com",
    "metadata": {
        "region": "us-east-1",
        "tier": "premium",
        "contact": {
            "slack": "#acme-admins",
            "phone": "+1-555-0100"
        },
        "features": ["agents", "analytics", "reports"]
    }
}
```

**Tenant**: Tenant information
```python
{
    "id": "tenant-uuid",
    "name": "ACME Corporation",
    "admin_email": "admin@example.com",
    "metadata": {
        "region": "us-east-1",
        "tier": "premium"
    },
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:30:00Z"
}
```

## Tool Management (`tools.py`)

### MCP Tool Registry

**ToolInfo**: Tool metadata and capabilities
```python
{
    "id": "graph.query@1",
    "name": "graph.query",
    "module": "src.adapters.graph",
    "entrypoint": "query_cypher",
    "description": "Execute Cypher queries against the graph database",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "parameters": {"type": "object"}
        },
        "required": ["query"]
    },
    "scopes": ["tools:basic", "tools:graph"],
    "capabilities": ["reads_db"],
    "namespace": false,
    "invokable": true,
    "long_running": false
}
```

**ToolInvokeRequest**: Tool execution
```python
{
    "args": {
        "query": "MATCH (n:Person) RETURN count(n)",
        "parameters": {}
    },
    "timeout_seconds": 30
}
```

**ToolInvokeResponse**: Execution results
```python
{
    "name": "graph.query",
    "ok": true,
    "result": {"count": 42},
    "error": null,
    "duration_ms": 150,
    "trace_id": "trace-uuid",
    "event_id": "event-uuid"
}
```

## Error Handling

### RFC 7807 Problem Details

**ProblemDetails**: Standardized error responses
```python
{
    "type": "https://api.cineca.example.com/errors/validation",
    "title": "Validation Error",
    "status": 422,
    "detail": "Request validation failed",
    "instance": "/api/v1/agents/sessions",
    "extensions": {
        "correlation_id": "req-uuid",
        "field_errors": [...]
    }
}
```

**ValidationProblemDetails**: Field-level validation errors
```python
{
    "type": "https://api.cineca.example.com/errors/validation",
    "title": "Validation Error",
    "status": 422,
    "detail": "Request validation failed",
    "errors": [
        {
            "loc": ["temperature"],
            "msg": "Value must be between 0.0 and 2.0",
            "type": "value_error.const"
        }
    ]
}
```

## Validation and Business Rules

### Field Validators

Custom validation logic ensures data integrity:

```python
@field_validator("tenant_id", mode='before')
@classmethod
def validate_tenant_id(cls, v: str) -> str:
    if not v or (isinstance(v, str) and v.strip() == ""):
        raise ValueError("tenant_id must be non-empty string")
    return v
```

### Model Validators

Cross-field validation and computed fields:

```python
@model_validator(mode='after')
def calculate_latency(self) -> 'OrchestrationStepInput':
    if self.started_at and self.finished_at:
        self.latency_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)
    return self
```

### Normalization

Automatic data normalization:

```python
@field_validator("base_url")
@classmethod
def normalize_base_url(cls, value: str | None) -> str | None:
    if value:
        return value.strip().rstrip("/")
    return value
```

## Security Considerations

### Secret Redaction

Sensitive fields are automatically redacted in responses:

```python
# API key fields show as "[REDACTED]" in responses
"api_key": "[REDACTED]",
"has_api_key": true
```

### Input Validation

Comprehensive validation prevents injection attacks:

- Type checking and constraint validation
- URL format validation for provider endpoints
- Email format validation for tenant contacts
- Length limits on string fields

### Tenant Isolation

Multi-tenant data separation enforced at schema level:

```python
tenant_id: str | None = Field(
    default=None,
    description="Tenant scope (null for global)"
)
```

## Performance Characteristics

### Validation Overhead

- **Lightweight**: Pydantic validation is highly optimized
- **Early Failure**: Invalid requests rejected before processing
- **Caching**: Compiled validators reused across requests

### Memory Usage

- **Efficient**: Models use minimal memory overhead
- **Streaming**: Large responses can be streamed
- **Pagination**: List responses support cursor-based pagination

### Serialization

- **Fast**: Pydantic uses optimized JSON serialization
- **Standards**: RFC 3339 timestamps, ISO 8601 dates
- **Extensions**: Extra fields allowed for provider-specific data

## Integration Patterns

### Router Integration

Routers import and use schemas directly:

```python
from src.schemas.agents import CreateSessionRequest, SessionResponse

@app.post("/sessions", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    user: UserInfo = Depends(get_current_user)
) -> SessionResponse:
    # Implementation uses validated request data
    pass
```

### Database Integration

Models integrate with SQLAlchemy ORM:

```python
model_config = ConfigDict(from_attributes=True)
# Enables: SessionResponse.from_orm(db_session)
```

### API Documentation

Rich schema metadata generates OpenAPI specs:

```python
temperature: float = Field(
    0.2, ge=0.0, le=2.0,
    description="Sampling temperature for stochastic models"
)
```

## Testing and Validation

### Schema Testing

Comprehensive test coverage for validation logic:

```python
def test_temperature_validation():
    # Valid values
    req = CreateSessionRequest(temperature=0.5)
    assert req.temperature == 0.5

    # Invalid values
    with pytest.raises(ValidationError):
        CreateSessionRequest(temperature=3.0)
```

### Integration Testing

End-to-end validation with real data:

```python
def test_session_creation_flow():
    request = CreateSessionRequest(
        prompt="Analyze data",
        temperature=0.7
    )
    response = await create_session(request)
    assert isinstance(response, SessionResponse)
    assert response.status == "active"
```

## Migration and Evolution

### Backward Compatibility

Schema evolution maintains API compatibility:

- Optional fields with defaults
- Alias support for renamed fields
- Extra field allowance for extensions

### Versioning Strategy

- **Additive**: New optional fields don't break existing clients
- **Deprecation**: Old fields marked deprecated with warnings
- **Migration**: Gradual migration with dual support

## API Reference

### Common Patterns

**Pagination**: Cursor-based pagination across all list endpoints
```python
{
    "items": [...],
    "next_page_token": "cursor-string",
    "total": 100
}
```

**ETags**: Conditional requests and caching support
```python
{
    "etag": "cache-token",
    // Other fields...
}
```

**Tracing**: Distributed tracing integration
```python
{
    "trace_id": "trace-uuid",
    "event_id": "event-uuid",
    // Other fields...
}
```

### Response Codes

- `200`: Success
- `201`: Created
- `400`: Bad Request (validation error)
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `422`: Validation Error (detailed field errors)
- `500`: Internal Server Error

This schemas package provides the foundation for type-safe, well-validated, and comprehensively documented APIs across the entire Cineca Agentic Platform.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_schemas.md