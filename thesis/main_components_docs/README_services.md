# Services Framework

The services package provides the core business logic and orchestration capabilities for the Cineca Agentic Platform. It implements a service-oriented architecture with dependency-tolerant components that gracefully degrade when optional dependencies are unavailable.

## Architecture Overview

The services framework follows these design principles:

- **Lazy Loading**: Services are imported and initialized only when needed
- **Dependency Tolerance**: Components work with minimal dependencies and degrade gracefully
- **Async-First**: All public APIs are async for scalability
- **Type Safety**: Comprehensive use of dataclasses and type hints
- **Shared Types**: Common result and error types across all services
- **Lifecycle Management**: Service base class with start/stop and health check methods

## Core Components

### 1. Service Infrastructure (`__init__.py`)

#### Shared Types
- **`ServiceResult[T]`**: Generic result wrapper with success/failure states
- **`ServiceStatus`**: Service health status with timestamp
- **`ServiceError`**: Base exception for service-level errors
- **`ServiceBase`**: Abstract base class providing lifecycle hooks

#### Lazy Loading
```python
from src.services import get_orchestrator, get_session_service

# Services loaded on-demand
orchestrator = get_orchestrator()
session_svc = get_session_service()
```

### 2. Orchestrator (`orchestrator.py`)

The central orchestration engine coordinating agent runs, tool execution, and LLM interactions.

#### Key Features
- **Multi-LLM Support**: Named LLM clients with automatic failover
- **Tool Integration**: MCP-style tool invocation with async/sync adapters
- **Caching**: Redis-backed result caching with TTL
- **Graph Queries**: Memgraph integration for knowledge graph operations
- **Intent Classification**: Automatic routing based on user intent
- **Audit Logging**: Comprehensive security and operational logging
- **Timeout Management**: Configurable timeouts with device-aware defaults
- **Metrics Collection**: Detailed telemetry for observability

#### Core Data Types
```python
@dataclass
class OrchestrationContext:
    goal: str
    user_id: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None
    run_id: str | None = None
    principal: dict[str, Any] | None = None

@dataclass
class OrchestrationResult:
    goal: str
    steps: list[Step]
    outputs: list[dict[str, Any]]
    errors: list[str]
    warnings: list[str]
    llm_metrics: list[dict[str, Any]]
    tool_metrics: list[dict[str, Any]]
    total_llm_calls: int
    tool_calls: int
    degraded: bool = False
    used_fallback: bool = False
```

#### Initialization
```python
# Factory method with environment detection
orchestrator = Orchestrator.from_env()

# Manual construction
orchestrator = Orchestrator(
    llm_clients={"default": llm_client},
    cache=redis_cache,
    audit=audit_logger
)
```

### 3. Session Service (`session.py`)

Lightweight chat session management with optional Redis persistence.

#### Features
- **Message Storage**: Role-based message history with timestamps
- **TTL Support**: Automatic expiration with configurable TTL
- **Dual Storage**: Redis-backed or in-memory fallback
- **Thread Safety**: Async locks for concurrent access
- **Metadata**: Custom metadata and token/budget tracking

#### Data Models
```python
@dataclass
class ChatMessage:
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    ts: str
    meta: dict[str, Any]

@dataclass
class Session:
    id: str
    user_id: str | None = None
    tenant_id: str | None = None
    messages: list[ChatMessage]
    tokens_in: int = 0
    tokens_out: int = 0
    turns: int = 0
    closed: bool = False
```

### 4. Intent Classifier (`intent_classifier.py`)

Heuristic-based intent classification for routing user requests.

#### Classification Modes
- **`CHAT`**: General conversation and greetings
- **`GRAPH`**: Memgraph database queries and graph operations
- **`SECURITY`**: Permission and access control queries
- **`ADMIN`**: Administrative operations and schema changes
- **`DANGEROUS`**: Heavy or destructive operations

#### Classification Flow
1. **Catalog Match**: Pre-classified prompts from prompt catalog
2. **Pattern Matching**: Regex-based keyword detection
3. **LLM Fallback**: Optional LLM-based classification for ambiguous cases
4. **Default**: Falls back to CHAT with low confidence

#### Usage
```python
from src.services.intent_classifier import classify_intent

result = await classify_intent(
    text="Show me all Blast nodes",
    user_id="user123",
    tenant_id="tenant456"
)

print(result.mode)  # IntentMode.GRAPH
print(result.confidence)  # 0.95
print(result.source)  # ClassificationSource.PATTERNS
```

### 5. Default Model Resolver (`default_model_resolver.py`)

Centralized service for resolving the current default LLM model.

#### Resolution Strategy
1. **Redis Cache**: Fast lookup (~1ms) with 15-minute TTL
2. **PostgreSQL**: Authoritative source from model_defaults table
3. **Environment Fallback**: Emergency fallback when DB unavailable

#### Features
- **Tenant Awareness**: Global and tenant-scoped defaults
- **Caching**: Redis-backed performance optimization
- **Resilience**: Graceful degradation with fallback modes
- **Metrics**: Resolution timing and cache hit/miss tracking

#### Usage
```python
from src.services.default_model_resolver import get_dmr

dmr = get_dmr()
default = await dmr.get_default_model(tenant_id="tenant123")

# Returns model configuration with provider, instance, and URLs
```

### 6. Additional Services

#### Health Service (`health.py`)
- Service health monitoring and readiness checks
- Dependency verification (database, cache, LLM clients)
- Graceful degradation reporting

#### ETL Service (`etl.py`)
- Data extraction, transformation, and loading operations
- Batch processing with progress tracking
- Error handling and retry logic

#### Archive Service (`archive.py`)
- Long-term data archiving and retrieval
- Compression and storage optimization
- Retention policy management

#### Job Store (`job_store.py`)
- Background job queuing and execution tracking
- Status monitoring and result storage
- Priority-based job scheduling

#### Prompt Catalog (`prompt_catalog.py`)
- Pre-classified prompt templates for common operations
- Intent mapping for efficient routing
- Template variable substitution

#### Process Service (`process_service.py`)
- Admin process management and monitoring
- Process lifecycle control (start/stop/restart)
- Resource usage tracking

#### Status Service (`status.py`)
- System-wide status aggregation
- Component health rollup
- Alert generation and notification

#### Tenants Service (`tenants.py`)
- Multi-tenant configuration management
- Tenant isolation and resource quotas
- Billing and usage tracking

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_DEVICE` | `cpu` | Device for LLM execution |
| `LLM_MAX_TOKENS` | `2048` | Maximum tokens per LLM call |
| `LLM_MAX_STEPS` | `10` | Maximum orchestration steps |
| `DEFAULT_MODEL_CACHE_TTL_SECONDS` | `900` | DMR cache TTL (15 minutes) |
| `INTENT_LLM_FALLBACK_ENABLED` | `false` | Enable LLM-based intent classification |

### Database Configuration

Services rely on PostgreSQL for persistent configuration:

- **Model Instances**: Available LLM models and providers
- **Model Defaults**: Default model selection per tenant/scope
- **Sessions**: Chat session storage (optional Redis override)
- **Jobs**: Background job status and results

## Usage Examples

### Basic Orchestration
```python
from src.services import get_orchestrator

orchestrator = get_orchestrator()

result = await orchestrator.run(
    goal="Analyze the Blast database schema",
    context=OrchestrationContext(
        user_id="user123",
        tenant_id="tenant456",
        session_id="session789"
    )
)

print(f"Completed in {result.overall_ms}ms")
print(f"LLM calls: {result.total_llm_calls}")
print(f"Tool calls: {result.tool_calls}")
```

### Session Management
```python
from src.services import get_session_service

session_svc = get_session_service()

# Create new session
session = await session_svc.create_session(
    user_id="user123",
    tenant_id="tenant456",
    title="Blast Analysis Session"
)

# Add messages
await session_svc.add_message(
    session_id=session.id,
    message=ChatMessage(
        role="user",
        content="Show me protein interactions"
    )
)
```

### Intent Classification
```python
from src.services.intent_classifier import classify_intent

classification = await classify_intent(
    text="DELETE all nodes WHERE id > 1000",
    user_id="admin",
    tenant_id="system"
)

if classification.mode == IntentMode.DANGEROUS:
    # Require additional authorization
    await require_admin_permissions(classification)
```

## Dependencies

### Required
- `structlog`: Structured logging
- `httpx`: HTTP client for external API calls
- `tenacity`: Retry logic for resilient operations

### Optional
- `db.redis_cache`: Redis caching and session storage
- `db.postgres_control`: PostgreSQL persistence
- `src.adapters.llm`: LLM client integration
- `src.adapters.db_memgraph`: Graph database operations
- `src.security.audit`: Audit logging
- `src.services.intent_classifier`: Intent classification
- `src.services.prompt_catalog`: Prompt templates

## Error Handling

Services use a consistent error handling pattern:

```python
from src.services import ServiceResult

async def some_operation() -> ServiceResult[DataType]:
    try:
        result = await do_something()
        return ServiceResult.success(result)
    except Exception as e:
        return ServiceResult.failure(f"Operation failed: {e}")
```

## Performance Characteristics

- **Orchestrator**: Device-aware timeouts (CPU: 120s, GPU: 30s)
- **Session Service**: O(1) Redis operations, O(n) for message history
- **Intent Classifier**: Sub-millisecond pattern matching
- **DMR**: ~1ms cache hits, ~10ms database queries
- **Memory Usage**: Bounded by configurable limits and TTL

## Security Considerations

- **RBAC Integration**: Principal validation in orchestration context
- **Audit Logging**: Comprehensive action tracking
- **Input Validation**: Type-safe dataclasses prevent injection
- **Tenant Isolation**: Multi-tenant data separation
- **Permission Checking**: Intent-based access control

## Monitoring and Observability

Services integrate with the observability framework:

- **Metrics**: Per-service operation counters and latency histograms
- **Tracing**: Distributed tracing for cross-service operations
- **Logging**: Structured logs with correlation IDs
- **Health Checks**: Readiness and liveness probes

### Key Metrics
- `orchestrator_runs_total`: Orchestration execution counts
- `session_operations_total`: Session CRUD operations
- `intent_classifications_total`: Classification attempts
- `dmr_cache_hits_total`: Model resolution cache performance
- `service_health_status`: Service availability indicators

## Testing

Services are designed for comprehensive testing:

- **Mock Dependencies**: Optional imports allow isolated unit testing
- **ServiceResult Pattern**: Consistent error handling for assertions
- **Async Testing**: Full async/await support in test suites
- **Fixture Support**: Test fixtures for common service configurations

## Migration and Compatibility

- **Backwards Compatible**: Service interfaces maintain API stability
- **Graceful Degradation**: Missing dependencies don't break core functionality
- **Version Pinning**: Explicit version handling for model configurations
- **Fallback Modes**: Emergency operation modes when primary systems fail</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_services.md