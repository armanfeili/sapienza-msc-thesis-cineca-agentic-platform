# Orchestrator Service (`src/services/orchestrator.py`)

## Overview

The Orchestrator service is the central coordination engine for the Cineca Agentic Platform, responsible for executing complex agent runs that combine LLM planning, tool invocations, and graph database operations. It implements a sophisticated orchestration pipeline with dependency-tolerant design, supporting optional Redis caching, Memgraph database access, and comprehensive audit logging.

## Architecture

### Core Components

- **Orchestrator Class**: Main orchestration engine with factory method `from_env()` for dependency injection
- **Execution Modes**: Chat, security, admin, dangerous, and graph handlers with intent-based routing
- **Planning System**: LLM-driven TODO list creation and execution with timeout protection
- **Tool Registry**: MCP-compatible tool execution with async/sync handling and security validation
- **Metrics Tracking**: Comprehensive LLM call, tool execution, and performance metrics with latency analysis

### Data Types

```python
@dataclass
class Step:
    id: str
    action: str
    input: dict[str, Any]
    meta: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None
    latency_ms: int | None = None

@dataclass
class OrchestrationContext:
    goal: str
    user_id: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None
    run_id: str | None = None
    principal: dict[str, Any] | None = None
    force_full_agentic: bool = False
    vars: dict[str, Any] | None = None

@dataclass
class OrchestrationResult:
    goal: str
    steps: list[Step] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    todos: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    current_stage: str = ""
    finished_at: str | None = None
    overall_ms: int = 0
    manager: str | None = None
    # Metrics and tracking
    llm_call_count: int = 0
    llm_metrics: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: int = 0
    tool_errors: int = 0
    tool_metrics: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

@dataclass
class GraphResultEnvelope:
    primary: GraphResultItem
    aux: list[GraphResultItem] | None = None
    goal: str = ""
    cypher: str = ""
```

## Configuration

### Timeout Configuration

The orchestrator uses device-aware timeouts with soft latency budgets:

```python
# CPU-based inference (slower, more forgiving)
LLM_SOFT_LATENCY_BUDGET_MS = 1200000  # 20 minutes

# GPU-based inference (faster, stricter)
# Configurable via environment variables
STEP_TIMEOUT_SECONDS = 1200  # 20 minutes default
```

### Environment Variables

- `LLM_PLANNER_TEMPERATURE`: Controls planning creativity (default: 0.2)
- `LLM_PLANNER_MAX_TOKENS`: Maximum tokens for planning (default: 640)
- `LLM_TODO_LIST_MAX_TOKENS`: Maximum tokens for TODO creation (default: 640)
- `MEMGRAPH_RESPONSE_MODE`: Response builder mode (`llm-best-effort`, `llm-required`, `fallback-only`)
- `MEMGRAPH_NL_VERBOSE_ANSWER`: Enable verbose natural language responses
- `FORCE_LLM_MEMGRAPH_TESTS`: Force LLM usage in Memgraph tests

## Execution Pipeline

### 1. Intent Classification

The orchestrator classifies user intent to determine routing:

```python
intent = self._classify_user_intent(goal, ctx, params)
# Returns: {"mode": "chat|graph|admin|dangerous|security", "confidence": float, "reasoning": str}
```

### 2. Mode-Specific Handlers

#### Chat Mode
- Simple conversational queries
- Direct LLM response without tool execution
- Confidence threshold: 0.6

#### Security Mode  
- Permission and access control questions
- Uses `security.describe_principal` and `security.allowed_operations`
- Confidence threshold: 0.75

#### Admin Mode
- Administrative write operations on graph database
- Requires admin role validation
- Audits all operations with `audit_event()`
- Confidence threshold: 0.7

#### Dangerous Mode
- Potentially harmful queries (unbounded, destructive operations)
- Refuses execution and provides EXPLAIN alternatives
- Analyzes danger reasons and suggests safer approaches
- Confidence threshold: 0.7

#### Graph Mode
- Read-only graph queries with streamlined 4-step pipeline:
  1. Generate Cypher from natural language
  2. Validate against security policy
  3. Execute validated query
  4. Build natural language response

### 3. Planning and Execution

For complex queries, the orchestrator creates and executes TODO lists:

```python
# Create TODO list via LLM
todos = await self._create_agent_todo_list(goal, ctx, result)

# Execute each TODO with timeout protection
await self._execute_todo_with_steps(todos, goal, ctx, result)
```

### 4. Tool Execution

Tools are executed with comprehensive error handling and metrics:

```python
# MCP-compatible tool execution
result = await self.execute_tool(
    name="graph.query",
    payload={
        "cypher": cypher,
        "principal": ctx.principal,
        "tenant": ctx.tenant_id
    }
)
```

## Tool Registry

### Built-in Tools

- `graph.query`: Execute Cypher queries
- `graph.secure_query`: Execute queries with security validation
- `graph.generate_cypher`: Generate Cypher from natural language
- `catalog.discover`: Discover available MCP tools
- `system.metrics`: System performance metrics
- `system.health`: Health check endpoints
- `model.manage`: LLM model management
- `cache.manage`: Cache operations
- `security.describe_principal`: Principal information
- `security.allowed_operations`: Permission checking

### Tool ACLs

Tools can be restricted by LLM client:

```python
self.tool_acl = {
    "llm:gpt-4": ["graph.query", "catalog.discover"],
    "llm:claude": ["graph.secure_query", "system.health"]
}
```

## LLM Client Management

### Client Registration

```python
# Register new LLM client
await orchestrator.register_llm(
    name="custom-llm",
    base_url="https://api.example.com",
    model="custom-model",
    api_key="secret-key",
    tenant_id="tenant-123"
)

# Set as tenant main LLM
orchestrator.set_main_llm("custom-llm", "tenant-123")
```

### Client Resolution

The orchestrator resolves LLM clients in priority order:
1. Explicit `manager` parameter
2. Tenant-specific main LLM (from Redis/Memgraph)
3. Global main LLM
4. First available client

## Metrics and Monitoring

### Performance Metrics

```python
result.metrics = {
    "overall_ms": 1500,
    "llm_attempted_calls": 3,
    "llm_successful_calls": 3,
    "tool_calls": 2,
    "tool_errors": 0,
    "timeout_stage": "none",
    "first_llm_call_ms": 450  # Warmup time
}
```

### Tool Metrics

```python
tool_metric = {
    "name": "graph.query",
    "latency_ms": 250,
    "success": True,
    "error": None  # Only present on failure
}
```

### Audit Logging

All operations are audited:

```python
await self.audit_event(
    "orchestrator.run.start",
    goal=goal,
    user_id=user_id,
    session_id=session_id,
    tenant_id=tenant_id
)
```

## Security Features

### Principal Enrichment

```python
ctx.principal = _enrich_principal(
    ctx.principal,
    user_id=ctx.user_id,
    tenant_id=ctx.tenant_id
)
```

### Graph Access Policy

Queries are validated against security policies:

```python
validation = validate_for_principal(cypher, ctx.principal)
if not validation.is_safe:
    # Query blocked
    return ServiceResult.failure(f"Query blocked: {validation.denial_reason}")
```

### Dangerous Query Detection

The orchestrator analyzes queries for dangerous patterns:

```python
danger_reasons = self._analyze_danger_reasons(goal, cypher)
# Returns formatted list of safety concerns
```

## Error Handling

### Timeout Protection

All operations have configurable timeouts:

```python
try:
    result = await asyncio.wait_for(
        self._execute_step(step, ctx),
        timeout=STEP_TIMEOUT_SECONDS
    )
except asyncio.TimeoutError:
    # Handle timeout with detailed metrics
    result.timeout_stage = "step_execution"
```

### Graceful Degradation

- LLM failures fall back to deterministic responses
- Tool failures are tracked but don't stop execution
- Partial failures are reported with detailed error information

## Integration Patterns

### Fast Graph Queries

For simple read-only queries, bypass TODO planning:

```python
# Direct graph mode execution
if intent.get("mode") == "graph" and self._is_simple_graph_query(goal, params):
    return await self._handle_graph_mode(goal, ctx, result, intent)
```

### Memgraph NL Responses

Build natural language responses from graph data:

```python
response_text = await self.build_memgraph_nl_response(
    goal=goal,
    cypher=cypher,
    rows=rows,
    rowcount=count,
    steps=result.steps,
    role=role,
    todos=todos,
    prompt_id=prompt_id,
    verbose=verbose,
    result=result
)
```

### Tool Discovery

Dynamic tool discovery with caching:

```python
# Discover available tools
tools_result = await self.execute_tool(
    "catalog.discover",
    payload={"names_only": False, "include_schemas": True}
)

# Cache for future requests
ctx.vars["discovered_tools"] = tools_result.get("items", [])
```

## Usage Examples

### Basic Orchestration

```python
from src.services.orchestrator import get_orchestrator_instance

orchestrator = get_orchestrator_instance()

result = await orchestrator.run(
    goal="How many Blast nodes are in the database?",
    user_id="user-123",
    session_id="session-456",
    tenant_id="tenant-789",
    principal={"id": "user-123", "scopes": ["read"]}
)

print(f"Result: {result.data}")
```

### Tool Execution

```python
# Execute tool directly
result = await orchestrator.execute_tool(
    "graph.query",
    payload={
        "cypher": "MATCH (n:Blast) RETURN count(n)",
        "principal": "user-123",
        "tenant": "tenant-789"
    }
)
```

### Custom LLM Registration

```python
# Register custom LLM
await orchestrator.register_llm(
    name="my-llm",
    base_url="https://my-llm.example.com/v1",
    model="my-model",
    api_key="my-api-key",
    tenant_id="tenant-789"
)

# Use in orchestration
result = await orchestrator.run(
    goal="Analyze the data",
    params={"manager": "my-llm"}
)
```

## Dependencies

### Required Components

- **LLM Clients**: At least one configured LLM client for planning and responses
- **Tool Registry**: Configured tools for execution (graph, security, system)
- **Database**: Optional Memgraph for graph operations and tenant management
- **Cache**: Optional Redis for performance optimization and tenant defaults
- **Audit Logger**: Optional audit logging for compliance

### Optional Components

- **Prompt Catalog**: For intent classification and query hints
- **Security Policies**: For graph access control
- **Metrics Collection**: For performance monitoring
- **Health Checks**: For system monitoring

## Configuration Files

The orchestrator integrates with several configuration sources:

- **Environment Variables**: Timeout and behavior configuration
- **Prompt Catalog**: Query templates and security policies (`src/services/prompt_catalog.py`)
- **Security Policies**: Graph access control (`src/security/graph_access_policy.py`)
- **LLM Adapters**: Client configurations (`src/adapters/llm/`)
- **Database Schemas**: Tenant and model management

## Testing

The orchestrator includes comprehensive testing patterns:

- **Unit Tests**: Individual component testing
- **Integration Tests**: Full pipeline testing with mocked dependencies
- **Timeout Tests**: Timeout behavior validation
- **Security Tests**: Access control and policy enforcement
- **Performance Tests**: Metrics collection and latency analysis

## Monitoring and Observability

### Logging

Structured logging with context:

```python
log.info(
    "orchestrator.run.complete",
    goal=goal,
    outputs=len(result.outputs),
    todos=len(todos),
    llm_call_count=self.llm_call_count
)
```

### Metrics Collection

Comprehensive metrics for monitoring:

- LLM call counts and latencies
- Tool execution success/failure rates
- Overall orchestration performance
- Timeout and error tracking
- Cache hit rates and database performance

### Health Checks

System health monitoring:

```python
# Health check integration
health_result = await orchestrator.execute_tool(
    "system.health",
    payload={"component": "orchestrator"}
)
```

## Future Enhancements

### Planned Features

- **Streaming Responses**: Real-time output streaming
- **Workflow Templates**: Predefined orchestration patterns
- **Advanced Planning**: Multi-step dependency resolution
- **Federated Execution**: Cross-tenant orchestration
- **Performance Optimization**: Query result caching and parallel execution

### Extensibility

The orchestrator is designed for extension:

- **Custom Tools**: Easy registration of new MCP-compatible tools
- **Custom Handlers**: Additional execution modes via intent classification
- **Custom Metrics**: Extensible metrics collection
- **Plugin Architecture**: Modular component loading

## Troubleshooting

### Common Issues

1. **LLM Timeouts**: Check `STEP_TIMEOUT_SECONDS` configuration
2. **Tool Failures**: Verify tool registration and ACL permissions
3. **Security Blocks**: Review graph access policies and principal scopes
4. **Performance Issues**: Monitor metrics and optimize cache usage

### Debug Mode

Enable verbose logging:

```python
import logging
logging.getLogger("orchestrator").setLevel(logging.DEBUG)
```

### Health Checks

Verify system health:

```bash
# Check orchestrator health
curl http://localhost:8000/health/orchestrator

# Check tool availability
curl http://localhost:8000/tools/available
```

## API Reference

### Main Methods

- `run()`: Execute orchestration pipeline
- `stream()`: Streaming orchestration execution
- `execute_tool()`: Direct tool execution
- `register_llm()`: Register LLM client
- `set_main_llm()`: Set tenant main LLM

### Configuration Methods

- `set_tool_preferences()`: Configure tool preferences
- `set_agent_roles()`: Configure agent roles
- `set_tool_acl()`: Configure tool access control

### Utility Methods

- `list_llms()`: List configured LLM clients
- `get_main_llm()`: Get tenant main LLM
- `cache_get/set()`: Cache operations
- `audit_event()`: Audit logging

This orchestrator service provides a robust, scalable foundation for complex agent orchestration in the Cineca Agentic Platform, with comprehensive error handling, security controls, and performance monitoring capabilities.