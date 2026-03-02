# Schemas Directory Documentation

## Overview

The `src/schemas` directory contains all canonical Pydantic models (DTOs) used across the Cineca Agentic Platform API. This directory serves as the single source of truth for request/response schemas, ensuring consistency and type safety throughout the application.

### Architectural Principles

**ALL Pydantic request/response models MUST live in schemas/*.py**
**Routers MUST only import these models, never define new Pydantic models**

This strict separation ensures:
- **Type consistency** across all API endpoints
- **Schema validation** at the API boundary
- **Documentation generation** from a single source
- **Maintainability** through centralized schema management

### Organization

The schemas are organized by domain:

- `agents.py`: Agent session, step, and run schemas with comprehensive metrics
- `auth.py`: Authentication/authorization models
- `batch.py`: Batch operation schemas
- `jobs.py`: Background job management (PostgreSQL-backed)
- `models.py`: LLM model instance and inference schemas
- `providers.py`: LLM provider management schemas
- `tenants.py`: Multi-tenant management schemas
- `tools.py`: MCP tool management and invocation schemas

## Core Package Structure

### __init__.py

The package initializer provides convenient re-exports of commonly used schemas:

```python
from src.schemas.agents import (
    CreateRunRequest,
    RunResponse,
    # ... other agent schemas
)
from src.schemas.jobs import (
    JobCreateRequest,
    JobResponse,
    # ... other job schemas
)
# ... additional re-exports
```

**Key Exports**:
- Agent lifecycle schemas (sessions, steps, runs)
- Job management schemas
- Provider and tenant management
- Authentication models

## Agent Schemas (agents.py)

### Purpose
Comprehensive Pydantic models for the agent orchestration system, including session management, step execution, run tracking, and detailed performance metrics.

### Key Features
- **Session lifecycle** management with idempotent creation
- **Step orchestration** with input/output tracking
- **Performance metrics** including LLM calls, tool invocations, and latency
- **TODO management** with evidence validation
- **Error handling** with RFC 7807 Problem Details

### Core Models

#### Session Management

##### CreateSessionRequest
Request to create a new agent session with optional configuration.

```python
class CreateSessionRequest(BaseModel):
    session_id: UUID | None = None  # Optional client-provided ID
    prompt: str | None = None       # Natural-language input
    manager: str | None = None      # Planner LLM name
    preferred_workers: list[str] | None = None  # Worker preferences
    llm_preferences: dict[str, str] | None = None  # Tool -> LLM mapping
    agent_role: str | None = None   # Agent role (researcher, coder, etc.)
    tools: list[str] | None = None  # Allowed tool names
    temperature: float = 0.2        # Sampling temperature (0.0-2.0)
    max_steps: int = 8             # Maximum steps (1-64)
    metadata: dict[str, Any] = {}   # Arbitrary metadata
```

**Validation Rules**:
- `temperature`: Must be between 0.0 and 2.0
- `max_steps`: Must be between 1 and 64

##### SessionResponse
Complete session state with all configuration and metadata.

```python
class SessionResponse(BaseModel):
    session_id: UUID
    user_id: str
    tenant_id: str
    status: str  # active, completed, cancelled, failed
    manager: str | None
    preferred_workers: list[str] | None
    llm_preferences: dict[str, str] | None
    agent_role: str | None
    tools: list[str] | None
    temperature: float
    max_steps: int
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_step_id: UUID | None
    etag: str | None
```

##### SessionListResponse
Paginated session listings with minimal metadata.

```python
class SessionListResponse(BaseModel):
    items: list[SessionListItem]
    next_cursor: str | None
```

#### Step Management

##### CreateStepRequest
Add a new step to an existing session.

```python
class CreateStepRequest(BaseModel):
    type: str  # message, user, assistant, tool, system, error
    message: str | None
    tool: str | None
    input: dict[str, Any] | None
    output: dict[str, Any] | None
```

**Type Validation**:
Must be one of: `message`, `user`, `assistant`, `tool`, `system`, `error`

##### StepResponse
Complete step information from database.

```python
class StepResponse(BaseModel):
    step_id: UUID
    session_id: UUID
    seq: int  # Sequence number within session
    type: str
    message: str | None
    tool: str | None
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    status: str  # queued, running, completed, failed, cancelled
    error: dict[str, Any] | None
    created_at: datetime
    completed_at: datetime | None
```

#### Run Orchestration

##### OrchestrationStepInput
Represents a planned orchestration step with timing and metadata.

```python
class OrchestrationStepInput(BaseModel):
    type: Literal["step"] = "step"
    step_id: str  # Can be "1", "2", "create-todos", etc.
    action: str   # Tool/action to execute
    input: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    latency_ms: int | None
```

**Automatic Latency Calculation**:
Calculates `latency_ms` from timestamps if missing, with consistency validation.

##### OrchestrationStepOutput
Execution results from completed steps.

```python
class OrchestrationStepOutput(BaseModel):
    type: Literal["output"] = "output"
    step_id: str
    output: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    latency_ms: int | None
```

#### TODO Management

##### TodoItem
Represents a task in the agent's execution plan.

```python
class TodoItem(BaseModel):
    task: str  # Description of the task
    status: Literal["pending", "in_progress", "completed", "failed"] | None
    expect_evidence: bool = True  # Whether evidence is expected
    evidence: list[str] = []      # Step IDs or summaries supporting completion
    meta: dict[str, Any] | None   # Guidance metadata
    requires_llm_planning: bool = True  # Whether LLM planning is needed
    nested_steps: list[str] = []  # Nested step descriptions
    fallback_mode: bool = False   # Skip evidence warnings
```

#### Performance Metrics

##### LLMCallMetrics
Detailed metrics for individual LLM API calls.

```python
class LLMCallMetrics(BaseModel):
    model: str
    latency_ms: int
    success: bool
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    purpose: str | None  # e.g., "todo_list_creation"
    error: str | None
```

**Automatic Token Calculation**:
Calculates `total_tokens` from input/output if missing.

##### ToolCallMetrics
Metrics for tool invocations.

```python
class ToolCallMetrics(BaseModel):
    name: str
    latency_ms: int
    success: bool
```

##### ExecutionMetrics
Comprehensive run performance metrics.

```python
class ExecutionMetrics(BaseModel):
    overall_ms: int
    llm: list[LLMCallMetrics] = []
    tools: list[ToolCallMetrics] = []
    # Legacy fields for backward compatibility
    model_warmup_ms: int | None
    first_llm_call_ms: int | None
    total_llm_calls: int | None
    llm_call_count: int | None
    llm_attempted_calls: int | None
    llm_successful_calls: int | None
    tool_calls: int | None
    tool_errors: int | None
    timeout_stage: str | None
    configured_run_timeout_seconds: int | None
    configured_step_timeout_seconds: int | None
    run_timeout_budget_ms: int | None
    planning_ms: int | None
    execution_ms: int | None
    timeout_reason: str | None
    llm_error_type: str | None
    llm_error_message: str | None
    llm_latency: dict[str, Any] | None
```

#### Run Response

##### CreateRunRequest
Request to initiate a new agent run.

```python
class CreateRunRequest(BaseModel):
    session_id: UUID | None = None
    prompt: str  # Required natural-language input
    manager: str | None = None
    preferred_workers: list[str] | None = None
    llm_preferences: dict[str, str] | None = None
    agent_role: str | None = None
    tools: list[str] | None = None
    temperature: float = 0.2
    max_steps: int = 8
    metadata: dict[str, Any] = {}
    force_full_agentic: bool = False
```

##### RunResponse
Comprehensive run result with orchestration artifacts.

```python
class RunResponse(BaseModel):
    run_id: UUID
    session_id: UUID | None
    user_id: str
    tenant_id: str  # Validated to be non-empty
    model: str | None
    manager: str | None
    latency_ms: int | None
    trace_id: str | None
    request_id: str | None
    event_id: str | None
    status: str  # running, succeeded, failed, cancelled
    started_at: datetime
    finished_at: datetime | None
    output: dict | list | None  # Structured result
    steps: list[OrchestrationStepInput | OrchestrationStepOutput] | None
    todos: list[TodoItem] | None
    metrics: ExecutionMetrics | None
    metadata: dict[str, Any] | None
    errors: list[str] | None
    warnings: list[str] | None
    degraded: bool | None
    used_fallback: bool | None
    # Rollup metrics for backward compatibility
    total_llm_calls: int | None
    llm_call_count: int | None
    tool_calls: int | None
    tool_errors: int | None
```

**Key Validations**:
- `tenant_id` must be non-empty string
- `model` names are normalized (kebab-case to colon-separated)
- `output` is normalized to dict/list/None
- Rollup metrics are calculated from detailed metrics
- TODO completion evidence is validated

#### Error Handling

##### ProblemDetail
RFC 7807 Problem Details for structured error responses.

```python
class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    extensions: dict[str, Any] | None = None
```

## Authentication Schemas (auth.py)

### Purpose
Simple but essential models for user identity and permissions extracted from JWT tokens.

### UserInfo Model

```python
class UserInfo(BaseModel):
    sub: str | None = None          # Subject (stable principal identifier)
    username: str | None = None     # Deprecated legacy username
    tenant_id: str | None = None    # Resolved tenant ID from header/middleware
    scopes: list[str] = []          # Granted OAuth scopes
    roles: list[str] = []           # Roles from token
    permissions: list[str] = []     # Effective permissions (admin routes only)
```

**Usage**:
- Extracted from JWT tokens by authentication middleware
- Passed to route handlers via `Depends(get_current_user)`
- Used for authorization checks and tenant isolation

## Batch Operation Schemas (batch.py)

### Purpose
Models for bulk operations across multiple resources, supporting atomic and non-atomic execution patterns.

### Core Models

#### BatchOperation
Individual operation within a batch.

```python
class BatchOperation(BaseModel):
    operation: str  # create, update, delete
    resourceType: str  # model, tenant, tool, agent
    resourceId: str | None
    data: dict[str, Any] | None
```

#### BatchRequest
Complete batch request with execution options.

```python
class BatchRequest(BaseModel):
    operations: list[BatchOperation]
    continueOnError: bool = False
    atomic: bool = False  # Not yet supported
```

#### BatchOperationResult
Result of individual operation execution.

```python
class BatchOperationResult(BaseModel):
    operation: str
    resourceType: str
    resourceId: str | None
    success: bool
    statusCode: int
    message: str | None
    data: dict[str, Any] | None
    error: str | None
```

#### BatchResponse
Aggregate batch execution results.

```python
class BatchResponse(BaseModel):
    totalOperations: int
    successCount: int
    failureCount: int
    results: list[BatchOperationResult]
    errors: list[str] = []
```

## Job Management Schemas (jobs.py)

### Purpose
PostgreSQL-backed background job management with comprehensive status tracking and event logging.

### Key Features
- **Job lifecycle** management (queued → running → finished/failed/cancelled)
- **Event streaming** with sequence IDs and timestamps
- **Pagination** support for large job lists
- **ETag caching** for efficient polling
- **Latency tracking** (queue time, execution time)

### Core Models

#### JobCreateRequest
Create a new background job.

```python
class JobCreateRequest(BaseModel):
    type: str  # e.g., "agent.run", "demo"
    payload: dict = {}  # Arbitrary JSON payload
```

#### JobResponse
Complete job information with all metadata.

```python
class JobResponse(BaseModel):
    id: str  # Job UUID
    type: str
    status: str  # queued, running, finished, failed, cancelled
    owner_sub: str  # Job owner (token subject)
    tenant_id: str
    created_at: str  # ISO 8601 timestamps
    updated_at: str | None
    started_at: str | None
    completed_at: str | None
    payload: dict | None
    result: dict | None
    error: dict | None
    priority: int
    queue_latency_ms: int | None
    exec_latency_ms: int | None
    etag: str
```

#### JobListResponse
Paginated job listings.

```python
class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
    next_page_token: str | None
```

#### JobEventResponse
Individual job lifecycle events.

```python
class JobEventResponse(BaseModel):
    seq_id: int  # Event sequence ID
    job_id: str
    event_type: str  # status, log, progress, heartbeat, end
    event_json: dict  # Event payload
    created_at: str
```

## Model Management Schemas (models.py)

### Purpose
Comprehensive schemas for LLM model lifecycle management, instance configuration, inference operations, and performance tracking.

### Key Features
- **Model instance lifecycle** (create, load, test, delete)
- **Default model resolution** with precedence rules
- **Inference operations** (completions, embeddings, chat)
- **Token usage tracking** and performance metrics
- **Provider abstraction** for multiple LLM backends

### Core Models

#### Model Instance Management

##### LoadInstanceRequest
Create/load a model instance with full configuration.

```python
class LoadInstanceRequest(BaseModel):
    provider_id: str  # Provider UUID
    instance_name: str  # Human-readable name
    model_id: str  # Provider-specific model identifier
    model_uri: str | None  # Optional model URI
    tenant_id: str | None  # Tenant scope (null = global)
    parameters: dict[str, Any] | None  # Model parameters
    context_window: int | None = None  # Token limit
    modalities: list[str] | None = None  # text, vision, audio, tool
    description: str | None = None
```

##### InstanceDetail
Complete instance information.

```python
class InstanceDetail(BaseModel):
    id: str
    instance_name: str
    provider_id: str
    model_id: str
    model_uri: str | None
    tenant_id: str | None
    parameters: dict[str, Any] | None
    context_window: int | None
    modalities: list[str] | None
    description: str | None
    enabled: bool
    loaded: bool
    created_at: str
    updated_at: str | None
    created_by: str | None
```

#### Default Model Selection

##### SetDefaultRequest
Set default model with precedence support.

```python
class SetDefaultRequest(BaseModel):
    chat: dict[str, str] | None = None  # Preferred: {"instance_id": "<uuid>"}
    name: str | None = None  # DEPRECATED
    instance_id: str | None = None  # DEPRECATED
```

**Important**: Send raw JSON, not wrapped in summary/value structure.

#### Model Testing

##### TestRequest
Health check and diagnostic testing.

```python
class TestRequest(BaseModel):
    model: str | None = None
    prompt: str | None = None
    messages: list[dict[str, Any]] | None = None
    temperature: float = 0.0
    max_tokens: int = 32
    stop: list[str] | None = None
    one_sentence: bool = True
    no_system: bool = False
    format_hint: str | None = None
    metadata: dict[str, Any] = {}
```

##### TestResponse
Test execution results with usage metrics.

```python
class TestResponse(BaseModel):
    model: str
    output: str
    usage: Usage
    trace_id: str
    event_id: str
    provider: str | None
    provider_base_url: str | None
    latency_ms: float | None
    parameters: dict[str, Any]
```

#### Inference Operations

##### CompletionRequest
Text completion request.

```python
class CompletionRequest(BaseModel):
    prompt: str
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int = 256
    metadata: dict[str, Any] = {}
```

##### EmbeddingRequest
Text embedding request.

```python
class EmbeddingRequest(BaseModel):
    input: str
    model: str | None = None
```

##### EmbeddingResponse
Embedding results with vector data.

```python
class EmbeddingResponse(BaseModel):
    data: list[EmbeddingVector]
    latency_ms: int
    trace_id: str
    event_id: str
    usage: Usage | None
```

## Provider Management Schemas (providers.py)

### Purpose
Comprehensive schemas for LLM provider registration, configuration, health monitoring, and management.

### Key Features
- **Provider lifecycle** (register, update, delete)
- **Configuration management** with secret redaction
- **Health monitoring** with cached status
- **Custom integrations** via flexible config schema
- **Pagination** and ETag caching

### Core Models

#### Provider Configuration

##### ProviderConfig
Extensible provider configuration with nested models.

```python
class ProviderConfig(BaseModel):
    base_url: str | None = None
    api_key: str | None = None  # Redacted in responses
    headers: dict[str, Any] | None = None
    auth: AuthConfig | None = None
    timeouts: Timeouts | None = None
    tls: TLSConfig | None = None
    paths: Paths | None = None
    request_templates: RequestTemplates | None = None
    response_extract: ResponseExtract | None = None
```

**Secret Redaction**: `api_key`, `headers.authorization`, `auth.token` are masked in API responses.

##### ProviderHealth
Cached health status from last connectivity check.

```python
class ProviderHealth(BaseModel):
    reachable: bool
    status: int | None  # HTTP status code
    last_check: float | None  # Unix timestamp
    latency_ms: int | None
    error: str | None
```

#### Provider CRUD

##### RegisterProviderRequest
Register a new LLM provider.

```python
class RegisterProviderRequest(BaseModel):
    name: str  # 1-255 characters
    type: ProviderType  # openai_compatible, custom
    base_url: str | None = None  # Required for openai_compatible
    model: str | None = None
    api_key: str | None = None
    tenant_id: str | None = None
    config: dict[str, Any] | None = None
```

**Validation**:
- `base_url` required for `openai_compatible` type
- URL format validation with HTTP/HTTPS requirement

##### Provider
Complete provider information for responses.

```python
class Provider(BaseModel):
    id: str
    name: str
    type: ProviderType
    base_url: str | None
    model: str | None
    tenant_id: str | None
    config: ProviderConfig | None
    has_api_key: bool  # Indicator (actual key redacted)
    created_at: str | float
    updated_at: str | float
    health: ProviderHealth | None
```

#### Error Handling

##### ProblemDetails
RFC 7807 structured error responses.

```python
class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    extensions: dict[str, Any] | None = None
```

## Tenant Management Schemas (tenants.py)

### Purpose
Multi-tenant management with comprehensive CRUD operations, validation, and metadata support.

### Key Features
- **Tenant lifecycle** management
- **Email validation** for admin contacts
- **Metadata support** with arbitrary key-value pairs
- **Pagination** and conditional requests
- **RFC 7807 error responses**

### Core Models

#### Tenant
Complete tenant information.

```python
class Tenant(BaseModel):
    id: str  # Server-generated UUID
    name: str
    admin_email: str  # RFC 5322 validated
    metadata: dict[str, Any] = {}
    created_at: str  # ISO 8601
    updated_at: str
```

#### CreateTenantRequest
Tenant creation with required fields.

```python
class CreateTenantRequest(BaseModel):
    name: str  # 1-255 characters
    admin_email: EmailStr  # RFC 5322 validation
    metadata: dict[str, Any] = {}
```

**Validation**:
- `name`: 1-255 characters
- `admin_email`: Valid email format
- `metadata`: Must be dictionary

#### UpdateTenantRequest
Partial tenant updates.

```python
class UpdateTenantRequest(BaseModel):
    name: str | None = None
    admin_email: EmailStr | None = None
    metadata: dict[str, Any] | None = None
```

## Tool Management Schemas (tools.py)

### Purpose
MCP (Model Context Protocol) tool discovery, management, and invocation schemas.

### Key Features
- **Tool discovery** with metadata and capabilities
- **Invocation requests** with timeout support
- **Result handling** with success/failure tracking
- **Permission-based access** control

### Core Models

#### ToolInfo
Tool metadata and capabilities.

```python
class ToolInfo(BaseModel):
    id: str  # e.g., "graph.query@1"
    name: str  # e.g., "graph.query"
    module: str | None = None  # Python import path
    entrypoint: str | None = None
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    scopes: list[str] = []  # Required permissions
    capabilities: list[str] = []  # e.g., ["reads_db", "writes_db"]
    namespace: bool = False  # Non-invokable namespace
    invokable: bool = False  # Can be invoked
    long_running: bool = False  # Async/job execution
```

#### ToolInvokeRequest
Tool execution request.

```python
class ToolInvokeRequest(BaseModel):
    args: dict[str, Any] = {}
    timeout_seconds: int | None = None  # 1-3600 seconds
```

#### ToolInvokeResponse
Tool execution result.

```python
class ToolInvokeResponse(BaseModel):
    name: str
    ok: bool
    result: Any = None
    error: str | None = None
    duration_ms: int
    trace_id: str
    event_id: str
```

## Common Patterns

### Validation Rules

#### Field Validators
Most schemas use Pydantic field validators for business logic:

```python
@field_validator("temperature")
@classmethod
def validate_temperature(cls, v: float) -> float:
    if not (0.0 <= v <= 2.0):
        raise ValueError("temperature must be between 0.0 and 2.0")
    return v
```

#### Model Validators
Complex cross-field validation:

```python
@model_validator(mode='after')
def validate_completion_evidence(self) -> 'RunResponse':
    # Validate TODO completion has supporting evidence
    pass
```

### Error Handling

#### RFC 7807 Problem Details
All error responses follow RFC 7807:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Invalid request parameters",
  "instance": "/v1/agents/runs",
  "extensions": {
    "correlation_id": "req-123",
    "field_errors": [...]
  }
}
```

### Pagination

#### Cursor-Based Pagination
Used for large result sets:

```python
class PaginatedResponse(BaseModel):
    items: list[Any]
    next_page_token: str | None = None
    total: int | None = None
```

### Metadata Support

#### Arbitrary Metadata
Many models support extensible metadata:

```python
metadata: dict[str, Any] = Field(default_factory=dict)
```

This allows:
- Custom fields without schema changes
- Forward compatibility
- Domain-specific extensions

### Timestamp Handling

#### ISO 8601 Timestamps
All timestamps use ISO 8601 format:

```python
created_at: str  # "2025-01-15T10:30:00Z"
updated_at: str | None
```

#### Automatic Timestamps
Server-generated timestamps are handled by database triggers.

## Usage Guidelines

### Import Patterns

#### Direct Imports
Import specific schemas from their modules:

```python
from src.schemas.agents import CreateRunRequest, RunResponse
from src.schemas.models import LoadInstanceRequest
```

#### Convenience Imports
Use package-level imports for common schemas:

```python
from src.schemas import CreateRunRequest, JobCreateRequest
```

### Schema Extension

#### Adding New Fields
When extending schemas:

1. **Add to appropriate module** (e.g., `agents.py` for agent-related)
2. **Use Field descriptions** for API documentation
3. **Add validation** if business rules apply
4. **Update __init__.py** if widely used
5. **Maintain backward compatibility**

#### Creating New Schemas

1. **Choose appropriate module** or create new one
2. **Follow naming conventions** (Request/Response suffixes)
3. **Add comprehensive field descriptions**
4. **Include JSON schema examples**
5. **Add to __all__ exports**

### Validation Best Practices

#### Required vs Optional
- Use `...` for truly required fields
- Use `None` defaults for optional fields
- Consider business requirements carefully

#### Type Hints
- Use `str | None` instead of `Optional[str]`
- Use `list[str]` instead of `List[str]`
- Use `dict[str, Any]` for flexible objects

#### Field Constraints
- Use `min_length`, `max_length` for strings
- Use `ge`, `le` for numeric ranges
- Use `examples` for documentation

## Testing

### Schema Validation Testing

```python
def test_create_run_request_validation():
    # Valid request
    req = CreateRunRequest(prompt="Test prompt")
    assert req.prompt == "Test prompt"
    
    # Invalid temperature
    with pytest.raises(ValidationError):
        CreateRunRequest(prompt="Test", temperature=3.0)
```

### Integration Testing

```python
def test_agent_run_response_serialization():
    response = RunResponse(
        run_id=uuid4(),
        user_id="user123",
        tenant_id="tenant456",
        status="succeeded",
        started_at=datetime.now(),
        output={"result": "success"}
    )
    
    # Test JSON serialization
    json_str = response.model_dump_json()
    parsed = RunResponse.model_validate_json(json_str)
    assert parsed.run_id == response.run_id
```

## Migration and Compatibility

### Backward Compatibility
- **Never remove fields** without deprecation period
- **Use default values** for new optional fields
- **Maintain enum values** (add new ones, don't remove)
- **Version API endpoints** for breaking changes

### Schema Evolution
- **Add new fields** with defaults
- **Deprecate old fields** with clear migration path
- **Use aliases** for renamed fields
- **Document breaking changes** in changelog

## Performance Considerations

### Model Configuration
- Use `model_config` for Pydantic optimization:

```python
model_config = ConfigDict(
    from_attributes=True,  # SQLAlchemy integration
    populate_by_name=True,  # Allow field aliases
    extra="forbid"  # Reject unknown fields
)
```

### Validation Performance
- **Validate at API boundary** only
- **Use efficient validators** (avoid complex computations)
- **Cache compiled schemas** for repeated use

### Memory Usage
- **Use streaming** for large response lists
- **Paginate** results appropriately
- **Avoid circular references** in model definitions

This comprehensive documentation covers all schemas in the Cineca Agentic Platform, providing the foundation for type-safe, well-validated API interactions across the entire system.