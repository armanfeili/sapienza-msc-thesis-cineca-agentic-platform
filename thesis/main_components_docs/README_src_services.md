# Services Package Documentation

## Overview

The `src/services/` package provides the core service layer for the Cineca Agentic Platform, implementing business logic, data orchestration, health monitoring, and integration with external systems. This package follows a modular architecture with lazy-loaded service factories, typed interfaces, and comprehensive error handling.

## Architecture

### Service Base Classes

All services inherit from `ServiceBase` and implement the `ServiceProtocol`:

```python
class ServiceBase:
    """Base class for all services with common functionality."""
    
    def __init__(self, settings: Settings | None = None):
        self.settings = settings
        self._logger = logging.getLogger(self.__class__.__name__)
    
    async def health_check(self) -> ServiceResult[bool]:
        """Basic health check implementation."""
        return ServiceResult.success(True)
```

### Service Factory Pattern

Services are registered and accessed through a lazy-loading factory:

```python
# Service registration
services = ServiceContainer()
services.register('archive', ArchiveService())
services.register('health', HealthService())

# Lazy access with typing
archive_svc = services.get(ArchiveService)
health_svc = services.get(HealthService)
```

## Service Components

### 1. Archive Service (`archive.py`)

**Purpose**: Graph snapshot management and generic file archiving with compression.

**Key Features**:
- On-demand Memgraph graph snapshots
- Gzip compression for storage efficiency
- Retention policy management
- Generic file archiving utilities

**Core Methods**:
```python
async def snapshot_graph(self, label: str = "current") -> ServiceResult[str]:
    """Create a compressed snapshot of the current graph."""
    
async def restore_graph(self, snapshot_path: str) -> ServiceResult[None]:
    """Restore graph from a compressed snapshot."""
    
def make_tar_gz(self, source_dir: str, output_path: str) -> ServiceResult[str]:
    """Create a compressed tar archive."""
```

**Usage**:
```python
archive_svc = services.get(ArchiveService)
result = await archive_svc.snapshot_graph("backup_2024")
```

### 2. Default Model Resolver (`default_model_resolver.py`)

**Purpose**: Single source of truth for default LLM model resolution with Redis caching and PostgreSQL fallback.

**Key Features**:
- Redis-backed caching for performance
- PostgreSQL authoritative source
- Singleton pattern for consistency
- Health monitoring integration

**Core Methods**:
```python
async def get_default_model(self) -> ServiceResult[str]:
    """Get the current default model with caching."""
    
async def invalidate_cache(self) -> ServiceResult[None]:
    """Clear Redis cache for fresh lookup."""
    
async def warmup_cache(self) -> ServiceResult[None]:
    """Pre-populate cache on startup."""
```

**Configuration**:
- Cache TTL: 300 seconds (5 minutes)
- Health check interval: 60 seconds
- Metrics: cache hit/miss rates

### 3. ETL Service (`etl.py`)

**Purpose**: Extract, Transform, Load operations for Memgraph database with batched operations and validation.

**Key Features**:
- CSV and JSONL import support
- Batched MERGE operations for performance
- Node and relationship import
- Graph export to snapshots

**Core Methods**:
```python
async def import_nodes_csv(self, file_path: str, label: str) -> ServiceResult[dict]:
    """Import nodes from CSV file."""
    
async def import_relationships_csv(self, file_path: str, rel_type: str) -> ServiceResult[dict]:
    """Import relationships from CSV file."""
    
async def snapshot_export(self, output_path: str) -> ServiceResult[str]:
    """Export current graph to compressed snapshot."""
```

**Usage**:
```python
etl_svc = services.get(ETLService)
result = await etl_svc.import_nodes_csv("data/nodes.csv", "Protein")
```

### 4. Health Service (`health.py`)

**Purpose**: Comprehensive health monitoring for critical dependencies with liveness and readiness probes.

**Key Features**:
- Redis connectivity checks
- Memgraph database availability
- Caching for performance
- Configurable probe timeouts

**Core Methods**:
```python
async def liveness(self) -> ServiceResult[dict]:
    """Check if service is alive (basic connectivity)."""
    
async def readiness(self) -> ServiceResult[dict]:
    """Check if service is ready (full functionality)."""
    
async def _probe_redis(self) -> ServiceResult[bool]:
    """Internal Redis connectivity probe."""
    
async def _probe_memgraph(self) -> ServiceResult[bool]:
    """Internal Memgraph connectivity probe."""
```

**Health Endpoints**:
- `/health/live` - Liveness check
- `/health/ready` - Readiness check

### 5. Intent Classifier (`intent_classifier.py`)

**Purpose**: Classify user prompts into operational modes for routing decisions.

**Key Features**:
- Pattern-based classification
- LLM fallback for complex cases
- Confidence scoring
- Conversational detection

**Classification Modes**:
- `chat` - Simple conversational queries
- `graph` - Graph database queries
- `admin` - Administrative operations
- `dangerous` - Potentially harmful operations
- `security` - Permission/access questions

**Core Methods**:
```python
async def classify_intent(self, prompt: str, **kwargs) -> IntentResult:
    """Classify user intent with confidence scoring."""
```

**Usage**:
```python
classifier = services.get(IntentClassifier)
result = await classifier.classify_intent("How many proteins are there?")
# Returns: IntentResult(mode="graph", confidence=0.95)
```

### 6. Invocation Store (`invocation_store.py`)

**Purpose**: Tool execution result caching for POST/GET parity with TTL-based expiration.

**Key Features**:
- Redis-backed caching
- In-memory fallback
- TTL-based expiration
- JSON serialization

**Core Methods**:
```python
async def save_invocation(self, key: str, result: Any, ttl_seconds: int = 3600) -> ServiceResult[None]:
    """Cache tool execution result."""
    
async def load_invocation(self, key: str) -> ServiceResult[Any]:
    """Retrieve cached result."""
```

**Cache Key Generation**:
```python
key = f"invocation:{tool_name}:{hash(input_params)}"
```

### 7. Job Store (`job_store.py`)

**Purpose**: In-memory job metadata and SSE event buffering with retention cleaning.

**Key Features**:
- Thread-safe in-memory storage
- Background cleanup tasks
- Event buffering for SSE
- UUID-based job tracking

**Core Methods**:
```python
def create_job_entry(self, job_id: str, metadata: dict) -> None:
    """Create new job entry."""
    
def record_event(self, job_id: str, event: dict) -> None:
    """Record job event for SSE."""
    
def get_events_since(self, job_id: str, since_timestamp: float) -> list[dict]:
    """Get events since timestamp."""
```

### 8. Jobs Service (`jobs_service.py`)

**Purpose**: Business logic for job lifecycle management with PostgreSQL/Redis hybrid persistence.

**Key Features**:
- Idempotent job creation
- Status transition validation
- Event logging
- Cancellation support

**Core Methods**:
```python
async def create_job(self, request: CreateJobRequest) -> ServiceResult[Job]:
    """Create new job with validation."""
    
async def cancel_job(self, job_id: str) -> ServiceResult[None]:
    """Cancel running job."""
    
async def list_jobs(self, filters: JobFilters) -> ServiceResult[list[Job]]:
    """List jobs with filtering."""
```

**Job States**:
- `pending` - Job created, waiting to start
- `running` - Job actively executing
- `completed` - Job finished successfully
- `failed` - Job failed with error
- `cancelled` - Job cancelled by user

### 9. Model Warmup Service (`model_warmup.py`)

**Purpose**: Deterministic LLM model loading and warmup to reduce first-inference latency.

**Key Features**:
- Timeout protection
- Retry logic with exponential backoff
- RAM usage monitoring
- Fallback model selection

**Core Methods**:
```python
async def warmup_model(self, model_name: str) -> ServiceResult[dict]:
    """Warmup specific model."""
    
async def _execute_warmup(self, model_name: str) -> ServiceResult[dict]:
    """Internal warmup execution."""
```

**Warmup Strategy**:
1. Send simple "ping" prompt
2. Monitor for RAM exhaustion
3. Fallback to lighter models if needed
4. Cache warmup status

### 10. Orchestrator (`orchestrator.py`)

**Purpose**: Agent run orchestration coordinating LLM calls, tool execution, and graph operations.

**Key Features**:
- Multi-LLM client management
- Intent-based routing
- Tool execution coordination
- Metrics and observability

**Core Components**:
```python
class Orchestrator:
    def __init__(self, llm_clients: dict, db: Any, cache: Any, audit: Any):
        self.llm_clients = llm_clients
        self.db = db
        self.cache = cache
        self.audit = audit
    
    async def run(self, goal: str, **kwargs) -> ServiceResult[dict]:
        """Execute agent run with full orchestration."""
```

**Routing Modes**:
- **Chat Mode**: Simple conversational responses
- **Graph Mode**: Direct graph queries (4-step pipeline)
- **Admin Mode**: Write operations with RBAC
- **Dangerous Mode**: Refuse harmful operations
- **Security Mode**: Permission questions

**Pipeline Stages**:
1. Intent classification
2. TODO list creation
3. Step execution
4. Response building

### 11. Process Service (`process_service.py`)

**Purpose**: Business logic for builtin process lifecycle management with Redis runtime state and PostgreSQL audit trail.

**Key Features**:
- Process start/stop operations
- Runtime state tracking
- Audit logging
- Stop locks for safety

**Core Methods**:
```python
async def list_processes(self) -> ServiceResult[list[ProcessInfo]]:
    """List all managed processes."""
    
async def stop_process(self, process_id: str) -> ServiceResult[None]:
    """Stop specific process."""
    
async def get_process_history(self, process_id: str) -> ServiceResult[list[ProcessEvent]]:
    """Get process event history."""
```

### 12. Prompt Catalog (`prompt_catalog.py`)

**Purpose**: Memgraph NL prompt catalog management with text-based lookup and category indexing.

**Key Features**:
- JSON catalog loading
- Fuzzy text matching
- Category-based filtering
- Execution hints and policies

**Core Methods**:
```python
def load_prompt_catalog() -> dict:
    """Load and index prompt catalog."""
    
def match_prompt_by_text(text: str, threshold: float = 0.85) -> dict | None:
    """Find matching prompt by text."""
    
def get_prompts_by_category(category: str) -> list[dict]:
    """Get prompts in category."""
```

**Catalog Structure**:
```json
{
  "id": "p01",
  "text": "How many nodes are there?",
  "category": "read_only",
  "expected_cypher_contains": ["count"],
  "limit_hint": 100
}
```

## Integration Patterns

### Service Dependencies

```python
# Most services depend on:
- Redis (caching, state management)
- PostgreSQL (authoritative data)
- Memgraph (graph operations)
- Settings configuration
```

### Error Handling

All services use `ServiceResult[T]` for consistent error handling:

```python
class ServiceResult[T]:
    ok: bool
    data: T | None
    error: str | None
    
    @classmethod
    def success(cls, data: T) -> ServiceResult[T]:
        return cls(ok=True, data=data, error=None)
    
    @classmethod
    def failure(cls, error: str) -> ServiceResult[T]:
        return cls(ok=False, data=None, error=error)
```

### Health Monitoring

Services implement health checks for monitoring:

```python
async def health_check(self) -> ServiceResult[bool]:
    """Implement service-specific health validation."""
    try:
        # Service-specific checks
        return ServiceResult.success(True)
    except Exception as e:
        return ServiceResult.failure(str(e))
```

## Configuration

### Environment Variables

```bash
# Redis configuration
REDIS_URL=redis://localhost:6379

# PostgreSQL configuration  
DATABASE_URL=postgresql://user:pass@localhost/db

# Memgraph configuration
MEMGRAPH_URL=bolt://localhost:7687

# Service timeouts
LLM_STEP_TIMEOUT_SECONDS=120
MEMGRAPH_BUILDER_LLM_TIMEOUT_MS=120000
```

### Settings Integration

Services access configuration through the settings object:

```python
class MyService(ServiceBase):
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.redis_ttl = settings.REDIS_TTL_SECONDS
```

## Testing

Services include comprehensive unit tests with mocking:

```python
@pytest.fixture
async def mock_redis():
    return MockRedis()

@pytest.fixture
async def service(mock_redis):
    return MyService(redis=mock_redis)
```

## Observability

### Metrics

Services emit structured metrics:

```python
# LLM call metrics
{
    "model": "phi3-mini",
    "latency_ms": 1500,
    "success": true,
    "input_tokens": 100,
    "output_tokens": 50
}

# Tool execution metrics
{
    "name": "graph.query",
    "latency_ms": 200,
    "success": true
}
```

### Logging

Structured logging with context:

```python
log.info("service.operation.completed", 
         service="archive",
         operation="snapshot",
         size_bytes=1024000)
```

## Best Practices

### 1. Service Design
- Keep services focused on single responsibility
- Use dependency injection for testability
- Implement comprehensive health checks
- Handle errors gracefully with ServiceResult

### 2. Performance
- Use caching appropriately (Redis for hot data)
- Implement timeouts for external calls
- Batch operations where possible
- Monitor resource usage

### 3. Security
- Validate inputs thoroughly
- Implement RBAC checks
- Audit sensitive operations
- Use parameterized queries

### 4. Observability
- Log structured events
- Emit relevant metrics
- Include correlation IDs
- Monitor error rates

## Migration Notes

### Version A.3 Changes
- Removed environment variable fallback for LLM configuration
- Enforce database-only model configuration
- Enhanced RBAC validation
- Improved error handling and observability

### Breaking Changes
- `LLM_FALLBACK_MODE` environment variable removed
- Model configuration must use database tables
- Enhanced validation may reject previously accepted queries

## Future Enhancements

### Planned Features
- Service mesh integration
- Enhanced metrics collection
- Auto-scaling support
- Advanced caching strategies

### Performance Optimizations
- Connection pooling improvements
- Query result caching
- Batch processing enhancements
- Memory usage optimization