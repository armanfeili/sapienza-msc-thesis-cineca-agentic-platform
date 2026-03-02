# Adapters Framework Reference

This document provides comprehensive reference documentation for the Adapters framework implemented in the Cineca Agentic Platform. The Adapters framework provides lazy-loaded, dependency-light interfaces to external services including databases, LLM providers, and MCP tools.

## Overview

The Adapters framework centralizes access to external dependencies through a lazy-loading pattern that avoids import-time side effects and keeps application startup fast. It provides unified interfaces for:

- **Memgraph Database**: Graph database operations with connection pooling and health checks
- **LLM Services**: Multi-provider LLM completion with OpenAI, Ollama, and demo fallback
- **MCP Tools**: Model Context Protocol tool discovery and invocation
- **Redis Cache**: Key-value caching with JSON serialization support

## Architecture

### Lazy Loading Pattern

The framework uses PEP 562 `__getattr__` for lazy imports, ensuring adapters are only loaded when first accessed:

```python
from src.adapters import get_client, complete, get_mcp_client

# No imports occur until first access
mg = get_client()  # Memgraph client loaded here
result = complete(prompt="Hello")  # LLM adapter loaded here
```

### Adapter Categories

#### Database Adapters
- **Memgraph**: Graph database with Cypher query support
- **Redis**: Key-value cache with TTL and JSON operations

#### AI/ML Adapters
- **LLM**: Multi-provider language model completions
- **MCP Client**: Tool discovery and invocation system

## Memgraph Adapter

### Overview

The Memgraph adapter provides a centralized interface to the Memgraph graph database using the `gqlalchemy` library. It implements connection pooling, health checks, and ergonomic query helpers.

### Connection Management

#### get_client()
Returns a process-wide Memgraph client singleton:

```python
from src.adapters import get_client

mg = get_client()  # Returns gqlalchemy.Memgraph instance
```

**Configuration**:
- Host: `settings.MG_HOST` (default: "memgraph")
- Port: `settings.MG_PORT` (default: 7687)
- Username: `settings.MG_USER` or `settings.MG_USERNAME`
- Password: `settings.MG_PASSWORD`

#### close_client()
Closes and clears the process-wide client:

```python
from src.adapters import close_client

close_client()  # Useful for testing or shutdown
```

### Health Checks

#### mg_health()
Performs connectivity verification:

```python
from src.adapters import mg_health

status = mg_health()
# Returns: {"ok": bool, "host": str, "port": int, "error": str|None}
```

**Example Response**:
```python
{
    "ok": True,
    "host": "memgraph",
    "port": 7687
}
```

### Query Operations

#### query()
Execute Cypher queries and return results:

```python
from src.adapters import query

# Simple query
rows = query("MATCH (n) RETURN count(n) AS total")

# Parameterized query
rows = query(
    "MATCH (u:User {id: $user_id}) RETURN u.name",
    params={"user_id": "123"}
)
```

**Returns**: `list[dict[str, Any]]` - List of result row dictionaries

#### query_one()
Return the first result row or None:

```python
from src.adapters import query_one

user = query_one(
    "MATCH (u:User {id: $id}) RETURN u.name, u.email",
    params={"id": "123"}
)
# Returns: {"name": "Alice", "email": "alice@example.com"} or None
```

#### execute()
Execute write queries and return affected row count:

```python
from src.adapters import execute

count = execute("CREATE (u:User {name: $name})", params={"name": "Alice"})
# Returns: 1 (rows yielded, 0 for pure writes)
```

### CRUD Helpers

#### ensure_index()
Create database indexes:

```python
from src.adapters import ensure_index

ensure_index("User", "email")  # Creates index on :User(email)
```

#### upsert_node()
Merge nodes with stable key properties:

```python
from src.adapters import upsert_node

# Simple upsert
upsert_node(
    ["User"],
    key="orig_id",
    props={"orig_id": "123", "name": "Alice", "email": "alice@example.com"}
)

# Multi-label upsert
upsert_node(
    ["User", "Person"],
    key="user_id",
    props={"user_id": "456", "name": "Bob", "age": 30}
)
```

#### upsert_relationship()
Merge relationships between nodes:

```python
from src.adapters import upsert_relationship

# Create relationship between existing nodes
upsert_relationship(
    start_key="user-1",
    rel_type="FOLLOWS",
    end_key="user-2",
    start_labels=["User"],
    end_labels=["User"]
)

# With relationship properties
upsert_relationship(
    start_key="alice",
    rel_type="RATED",
    end_key="movie-1",
    props={"rating": 5, "date": "2024-01-01"},
    start_labels=["User"],
    end_labels=["Movie"]
)
```

#### wipe_all()
**Dangerous**: Remove all nodes and relationships:

```python
from src.adapters import wipe_all

wipe_all()  # Removes ALL data - use with extreme caution
```

### Exception Handling

#### DBError
Generic database operation errors:

```python
from src.adapters import DBError

try:
    query("INVALID CYPHER")
except DBError as e:
    print(f"Database error: {e}")
```

#### DBUnavailable
Connection establishment failures:

```python
from src.adapters import DBUnavailable

try:
    get_client()
except DBUnavailable as e:
    print(f"Cannot connect to Memgraph: {e}")
```

### MemgraphAdapter Class

Lightweight OO wrapper for health checks and tools:

```python
from src.adapters.db_memgraph import MemgraphAdapter

adapter = MemgraphAdapter()
if adapter.ping():
    results = adapter.query("MATCH (n) RETURN count(n)")
```

**Methods**:
- `ping() -> bool`: Test connectivity
- `query(cypher, params, run_id, timeout_ms) -> list[dict]`: Execute queries
- `info() -> dict`: Connection information

## LLM Adapter

### Overview

The LLM adapter provides a unified interface for language model completions across multiple providers, with automatic fallback to demo mode when no API keys are configured.

### Provider Support

#### OpenAI
- Uses Chat Completions API
- Supports GPT-4, GPT-4o, GPT-4o-mini models
- Configurable via `OPENAI_API_KEY` and `OPENAI_BASE_URL`

#### Ollama
- Local model server support
- Automatic model verification to prevent auto-pulls
- Configurable via base URL and model name

#### Demo Fallback
- Deterministic echo responses
- No external dependencies
- Always available for development

### Model Management

#### list_models()
Return available models for the current provider:

```python
from src.adapters import list_models

models = list_models()
# Returns: [{"name": "gpt-4o-mini", "provider": "openai", "enabled": true, ...}]
```

**Model Information**:
```python
{
    "name": "gpt-4o-mini",
    "provider": "openai",
    "context_window": 128000,
    "modalities": ["text"],
    "enabled": true,
    "loaded": null,
    "description": "OpenAI model",
    "default": false
}
```

#### get_default_model()
Get the currently configured default model:

```python
from src.adapters import get_default_model

model = get_default_model()  # e.g., "gpt-4o-mini"
```

#### set_default_model()
Change the default model:

```python
from src.adapters import set_default_model

set_default_model("gpt-4-turbo")
```

#### load_model()
Prepare a model for use (validation only):

```python
from src.adapters import load_model

status = load_model("gpt-4o-mini")
# Returns: {"ok": true, "message": "openai model 'gpt-4o-mini' ready"}
```

#### unload_model()
Unload a model (no-op for remote providers):

```python
from src.adapters import unload_model

status = unload_model("gpt-4o-mini")
# Returns: {"ok": true, "message": "model 'gpt-4o-mini' unloaded (noop)"}
```

### Completions

#### complete()
Generate text completions:

```python
from src.adapters import complete

result = complete(
    prompt="Explain quantum computing",
    model="gpt-4o-mini",
    temperature=0.7,
    max_tokens=256,
    metadata={"run_id": "abc-123"},
    user={"id": "user-456"}
)

# Returns:
{
    "text": "Quantum computing uses quantum mechanics...",
    "output": "Quantum computing uses quantum mechanics...",
    "usage": {
        "prompt_tokens": 4,
        "completion_tokens": 150,
        "total_tokens": 154
    },
    "model": "gpt-4o-mini",
    "provider": "openai"
}
```

**Parameters**:
- `prompt`: Input text
- `model`: Model name (optional, uses default)
- `temperature`: Sampling temperature (0.0-1.0)
- `max_tokens`: Maximum output tokens
- `timeout_seconds`: Request timeout
- `metadata`: Additional context for logging
- `user`: User information for tracking

#### test()
Quick completion test with default parameters:

```python
from src.adapters import test

result = test(prompt="ping", model="gpt-4o-mini")
```

### LLMClient Class

Async client wrapper for orchestrators:

```python
from src.adapters.llm import LLMClient

client = LLMClient(model="gpt-4o-mini", base_url="https://api.openai.com/v1")

response = await client.complete(
    "Explain recursion",
    temperature=0.5,
    max_tokens=128
)
```

**Features**:
- Automatic model verification for Ollama
- Configurable timeouts and parameters
- Structured logging and error handling
- Support for Ollama-specific options

### LLMAdapter Class

Process-based adapter for local model servers:

```python
from src.adapters.llm import LLMAdapter

adapter = LLMAdapter(model="llama2:7b")

# Load a model
status = adapter.load_model("llama2:7b", artifact="/path/to/model.gguf")
# Returns: {"ok": true, "pid": 12345, "port": 8080}

# Check health
health = adapter.health()
# Returns: {"ok": true, "processes": {"llama2:7b": {"alive": true, "pid": 12345}}}
```

## MCP Client Adapter

### Overview

The MCP (Model Context Protocol) client provides tool discovery and invocation capabilities for Python-based tools organized under `src.mcp.tools`.

### Tool Discovery

#### discover()
Walk the tools package and return available tools:

```python
from src.adapters import get_mcp_client

client = get_mcp_client()
tools = client.discover()

# Returns: [ToolInfo(name="graph.query", module="src.mcp.tools.graph.query", ...)]
```

**ToolInfo Structure**:
```python
@dataclass(frozen=True)
class ToolInfo:
    name: str        # e.g., "graph.query"
    module: str      # e.g., "src.mcp.tools.graph.query"
    entrypoint: str | None  # e.g., "invoke"
    description: str | None # First line of module docstring
```

### Tool Invocation

#### invoke()
Execute a tool by name:

```python
from src.adapters import get_mcp_client

client = get_mcp_client()

result = await client.invoke(
    name="graph.query",
    args={"cypher": "MATCH (n) RETURN count(n)"},
    timeout=30.0,
    provenance_meta={"run_id": "abc-123"}
)
```

**Parameters**:
- `name`: Dotted tool name (e.g., "graph.query")
- `args`: Arguments dictionary passed to tool
- `timeout`: Execution timeout in seconds
- `provenance_meta`: Additional metadata for provenance tracking

### Tool Conventions

Tools follow these conventions:

**Location**: `src/mcp/tools/<namespace>/<name>.py`

**Entrypoints** (checked in order):
1. `invoke(payload: dict, **kwargs)`
2. `run(**kwargs)`
3. `handle(**kwargs)`
4. `main(**kwargs)`

**Example Tool**:
```python
"""
Query the graph database.
"""
def invoke(payload: dict) -> dict:
    """Execute a Cypher query."""
    cypher = payload.get("cypher", "")
    # Implementation...
    return {"results": []}
```

### Exception Handling

#### ToolNotFound
Raised when tool cannot be resolved:

```python
from src.adapters import ToolNotFound

try:
    await client.invoke("nonexistent.tool")
except ToolNotFound as e:
    print(f"Tool not found: {e}")
```

#### ToolInvocationError
Raised when tool execution fails:

```python
from src.adapters import ToolInvocationError

try:
    await client.invoke("graph.query", args={})
except ToolInvocationError as e:
    print(f"Tool execution failed: {e}")
```

### Provenance Integration

Tool invocations are automatically recorded via the provenance system:

```python
# Automatic provenance recording includes:
{
    "actor": "mcp",
    "action": "tool.graph.query",
    "resource": "mcp_client.invoke",
    "input": {"args": {"cypher": "MATCH (n) RETURN n"}},
    "output": {"results": [...]},
    "success": true,
    "duration_ms": 150
}
```

## Redis Adapter

### Overview

The Redis adapter provides key-value caching with TTL support and JSON serialization.

### Connection Management

#### get_redis()
Get Redis client instance:

```python
from src.adapters import get_redis

redis_client = get_redis()
```

### Cache Operations

#### cache_set()
Store a value with optional TTL:

```python
from src.adapters import cache_set

# Simple string
cache_set("key", "value")

# With TTL (seconds)
cache_set("temp_key", "value", ttl=300)

# With JSON serialization
cache_set("user:123", {"name": "Alice", "email": "alice@example.com"})
```

#### cache_get()
Retrieve a value:

```python
from src.adapters import cache_get

value = cache_get("key")  # Returns stored value or None
```

#### cache_delete()
Remove a key:

```python
from src.adapters import cache_delete

cache_delete("key")
```

#### cache_set_json() / cache_get_json()
JSON-specific operations:

```python
from src.adapters import cache_set_json, cache_get_json

# Store JSON data
cache_set_json("user_data", {"id": 123, "active": True})

# Retrieve and parse JSON
data = cache_get_json("user_data")  # Returns dict or None
```

#### incr_with_ttl()
Atomic increment with TTL:

```python
from src.adapters import incr_with_ttl

# Increment counter, set TTL if new
count = incr_with_ttl("requests:2024-01-01", ttl=86400)
```

#### ttl()
Get remaining TTL for a key:

```python
from src.adapters import ttl

remaining_seconds = ttl("key")  # Returns TTL or -1 if no TTL
```

### Health Checks

#### redis_health()
Check Redis connectivity:

```python
from src.adapters import redis_health

status = redis_health()
# Returns: {"ok": bool, "host": str, "port": int, "error": str|None}
```

#### redis_available()
Quick availability check:

```python
from src.adapters import redis_available

if redis_available():
    # Redis is available
    pass
```

## Configuration

### Environment Variables

#### Memgraph
```bash
MG_HOST=memgraph
MG_PORT=7687
MG_USER=  # Optional
MG_PASSWORD=  # Optional
```

#### LLM
```bash
LLM_PROVIDER=openai  # or "ollama" or "demo"
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
DEFAULT_MODEL_NAME=gpt-4o-mini
LLM_CLIENT_TIMEOUT_SECONDS=1200
OLLAMA_NUM_PREDICT=128
OLLAMA_TOP_K=40
```

#### Redis
```bash
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=  # Optional
REDIS_DB=0
```

### Settings Integration

All adapters respect configuration from `src.config.settings`:

```python
from src.config import settings

# Adapter configurations are read from settings at runtime
assert hasattr(settings, 'MG_HOST')
assert hasattr(settings, 'OPENAI_API_KEY')
```

## Error Handling

### Common Patterns

```python
from src.adapters import (
    DBError, DBUnavailable,  # Memgraph
    MCPError, ToolNotFound, ToolInvocationError,  # MCP
)

# Memgraph operations
try:
    results = query("MATCH (n) RETURN n")
except DBUnavailable:
    # Handle connection issues
    pass
except DBError:
    # Handle query errors
    pass

# MCP operations
try:
    result = await get_mcp_client().invoke("tool.name", args={})
except ToolNotFound:
    # Tool doesn't exist
    pass
except ToolInvocationError:
    # Tool execution failed
    pass
```

### Logging Integration

All adapters integrate with structured logging:

```python
# Automatic logging includes:
# - Query execution times
# - Error details
# - Performance metrics
# - Provenance tracking
```

## Performance Considerations

### Connection Pooling
- Memgraph: Process-wide singleton client
- Redis: Connection pooling via redis-py
- LLM: HTTP client reuse with timeouts

### Caching Strategy
- Lazy loading prevents startup delays
- Model verification caching for Ollama
- Connection reuse across requests

### Timeout Management
- Configurable timeouts for all operations
- Graceful degradation on failures
- Background health monitoring

## Testing

### Mock Adapters

```python
# Override adapters for testing
import src.adapters
src.adapters._EXPORTS["get_client"] = ("tests.mocks", "mock_memgraph_client")

# Or patch at module level
from unittest.mock import patch
with patch('src.adapters.get_client', return_value=mock_client):
    # Test code
    pass
```

### Health Check Testing

```python
from src.adapters import mg_health, redis_health

def test_database_health():
    status = mg_health()
    assert status["ok"] is True
    assert "host" in status
```

## Best Practices

### Import Strategy
```python
# Prefer lazy imports
from src.adapters import get_client

# Avoid direct module imports that bypass lazy loading
# import src.adapters.db_memgraph  # Not recommended
```

### Error Handling
```python
# Always handle connection errors
try:
    client = get_client()
    results = query("MATCH (n) RETURN n")
except DBUnavailable:
    # Fallback logic
    results = []
except DBError as e:
    logger.error("Query failed", error=str(e))
    raise
```

### Resource Management
```python
# Close connections in teardown
import atexit

@atexit.register
def cleanup():
    from src.adapters import close_client
    close_client()
```

### Configuration
```python
# Validate configuration at startup
from src.adapters import redis_available, mg_health

def validate_dependencies():
    if not redis_available():
        raise RuntimeError("Redis unavailable")
    
    mg_status = mg_health()
    if not mg_status["ok"]:
        raise RuntimeError(f"Memgraph unavailable: {mg_status.get('error')}")
```

This comprehensive Adapters framework provides reliable, performant access to external dependencies with consistent error handling, monitoring, and fallback mechanisms.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_adapters.md