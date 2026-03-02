# MCP Tools Reference

**Last Updated**: October 26, 2025  
**Version**: 1.0.0  
**Pattern**: P3 (MCP Decorator with ToolContext)

---

## Overview

This document provides comprehensive reference documentation for all MCP (Model Context Protocol) tools in the Cineca Agentic Platform. All tools follow the P3 pattern with:

- **MCP Decorator**: `@mcp_tool(tool_name="...", required_scope="...")`
- **ToolContext**: Audit trail, user tracking, tenant isolation
- **Action-based**: Internal `_act_*` functions for each operation
- **Security**: Scope-based access control, rate limiting, input validation
- **Backward Compatible**: Legacy function wrappers maintained

---

## Tool Categories

### P1: Graph Query & Generation (Priority 1)
- [graph.query](#graphquery) - Execute Cypher queries
- [graph.generate_cypher](#graphgenerate_cypher) - NL→Cypher conversion
- [graph.secure_query](#graphsecure_query) - Secure NL→Cypher→Execute

### P4: System & Operations Tools
- [system.health](#systemhealth) - Health checks and diagnostics
- [system.config](#systemconfig) - Configuration management
- [ops.backup](#opsbackup) - Backup operations
- [ops.restore](#opsrestore) - Restore operations

### P5: Model Layer Tools
- [model.manage](#modelmanage) - Model lifecycle management
- [model.test](#modeltest) - Model testing and validation

### P6: User, Session & Platform Tools
- [user.profile](#userprofile) - User profile management
- [session.manage](#sessionmanage) - Session lifecycle
- [tenancy.manage](#tenancymanage) - Multi-tenancy operations
- [cache.manage](#cachemanage) - Cache operations
- [catalog.discover](#catalogdiscover) - Tool catalog discovery
- [agent.context](#agentcontext) - Agent context management

### P7: Output & Visualization Tools
- [output.format](#outputformat) - Data formatting (JSON/CSV/Markdown/Text)
- [output.summarize](#outputsummarize) - Text summarization
- [viz.render](#vizrender) - Graph and table visualization

---

## Security & Rate Limiting

### Scope Requirements

Each tool requires specific OAuth2 scopes:

| Tool | Required Scope | Admin Override |
|------|----------------|----------------|
| `graph.query` | `graph:query` | `admin:all` |
| `graph.generate_cypher` | `graph:generate` | `admin:all` |
| `graph.secure_query` | `graph:query` | `admin:all` |
| `system.health` | `system:read` | `admin:all` |
| `system.config` | `system:admin` | `admin:all` |
| `ops.backup` | `ops:backup` | `admin:all` |
| `ops.restore` | `ops:restore` | `admin:all` |
| `model.manage` | `model:admin` | `admin:all` |
| `model.test` | `model:test` | `admin:all` |
| `user.profile` | `user:profile` | `admin:all` |
| `session.manage` | `session:manage` | `admin:all` |
| `tenancy.manage` | `tenancy:admin` | `admin:all` |
| `cache.manage` | `cache:admin` | `admin:all` |
| `catalog.discover` | `catalog:read` | `admin:all` |
| `agent.context` | `agent:context` | `admin:all` |
| `output.format` | `output:format` | `admin:all` |
| `output.summarize` | `output:summarize` | `admin:all` |
| `viz.render` | `viz:render` | `admin:all` |

### Rate Limits

Default rate limits per tool class:

- **Query Tools** (graph.query): 100 req/min per user
- **Generation Tools** (graph.generate_cypher): 20 req/min per user
- **System Tools**: 10 req/min per user
- **Model Tools**: 5 req/min per user (expensive operations)
- **User/Session Tools**: 50 req/min per user
- **Output Tools**: 30 req/min per user

Rate limits can be adjusted per tenant in tenant configuration.

---

## P1: Graph Query & Generation Tools

### graph.query

**Purpose**: Execute Cypher queries against the Memgraph database.

**Module**: `src.mcp.tools.graph.query`  
**Scope**: `graph:query`

#### Actions

##### execute

Execute a Cypher query and return results.

**Payload**:
```json
{
  "action": "execute",
  "cypher": "MATCH (n:Person) RETURN n.name LIMIT 5",
  "params": {},
  "timeout": 30
}
```

**Parameters**:
- `cypher` (string, required): Cypher query to execute
- `params` (object, optional): Query parameters (prevents injection)
- `timeout` (integer, optional): Query timeout in seconds (default: 30)

**Returns**:
```json
{
  "status": "success",
  "results": [
    {"n.name": "Alice"},
    {"n.name": "Bob"}
  ],
  "count": 2,
  "execution_time_ms": 45,
  "metadata": {
    "query_hash": "abc123...",
    "cached": false
  }
}
```

**Security Notes**:
- Always use `params` for user input to prevent injection
- Read-only queries recommended for untrusted users
- Queries are logged for audit

**Example**:
```python
from src.mcp.tools.graph.query import invoke

result = invoke({
    "action": "execute",
    "cypher": "MATCH (n:Person {name: $name}) RETURN n",
    "params": {"name": "Alice"}
})
```

---

### graph.generate_cypher

**Purpose**: Convert natural language to Cypher queries using LLM.

**Module**: `src.mcp.tools.graph.generate_cypher`  
**Scope**: `graph:generate`

#### Actions

##### generate

Generate Cypher from natural language description.

**Payload**:
```json
{
  "action": "generate",
  "nl_query": "Find all people who work at Acme Corp",
  "schema_context": "optional: graph schema hints",
  "validate": true
}
```

**Parameters**:
- `nl_query` (string, required): Natural language query
- `schema_context` (string, optional): Graph schema hints for better generation
- `validate` (boolean, optional): Validate generated Cypher syntax (default: true)

**Returns**:
```json
{
  "status": "success",
  "cypher": "MATCH (p:Person)-[:WORKS_AT]->(c:Company {name: 'Acme Corp'}) RETURN p",
  "confidence": 0.95,
  "explanation": "This query finds all Person nodes connected to Acme Corp via WORKS_AT relationship",
  "metadata": {
    "model_used": "gpt-4",
    "generation_time_ms": 850
  }
}
```

**Security Notes**:
- Generated queries should be reviewed before execution
- Rate limits apply (20 req/min)
- LLM costs tracked per tenant

---

### graph.secure_query

**Purpose**: End-to-end NL→Cypher→Execute with safety guardrails.

**Module**: `src.mcp.tools.graph.secure_query`  
**Scope**: `graph:query`

#### Actions

##### secure_execute

Execute natural language query with safety validation.

**Payload**:
```json
{
  "action": "secure_execute",
  "nl_query": "Show me users in the admin role",
  "max_results": 100,
  "dry_run": false
}
```

**Parameters**:
- `nl_query` (string, required): Natural language query
- `max_results` (integer, optional): Maximum results to return (default: 100)
- `dry_run` (boolean, optional): Return Cypher without executing (default: false)

**Returns**:
```json
{
  "status": "success",
  "nl_query": "Show me users in the admin role",
  "generated_cypher": "MATCH (u:User)-[:HAS_ROLE]->(r:Role {name: 'admin'}) RETURN u LIMIT 100",
  "results": [...],
  "count": 15,
  "safety_checks": {
    "mutation_detected": false,
    "expensive_ops": false,
    "approved": true
  }
}
```

**Security Notes**:
- Automatically detects and blocks mutation queries (CREATE/DELETE/SET)
- Expensive operations (Cartesian products) flagged
- All queries logged with user attribution

---

## P4: System & Operations Tools

### system.health

**Purpose**: System health checks and diagnostics.

**Module**: `src.mcp.tools.system.health`  
**Scope**: `system:read`

#### Actions

##### check_all

Check health of all system components.

**Payload**:
```json
{
  "action": "check_all",
  "include_details": true
}
```

**Returns**:
```json
{
  "status": "healthy",
  "components": {
    "database": {"status": "up", "latency_ms": 5},
    "redis": {"status": "up", "latency_ms": 2},
    "memgraph": {"status": "up", "latency_ms": 8}
  },
  "timestamp": "2025-10-26T20:00:00Z"
}
```

---

### system.config

**Purpose**: Configuration management and retrieval.

**Module**: `src.mcp.tools.system.config`  
**Scope**: `system:admin`

#### Actions

##### get

Retrieve configuration values.

**Payload**:
```json
{
  "action": "get",
  "key": "rate_limits.graph_query",
  "masked": true
}
```

**Security Notes**:
- Secrets are masked by default
- Admin-only access

---

### ops.backup

**Purpose**: Database backup operations.

**Module**: `src.mcp.tools.ops.backup`  
**Scope**: `ops:backup`

#### Actions

##### create

Create database backup.

**Payload**:
```json
{
  "action": "create",
  "include_metadata": true,
  "compression": "gzip"
}
```

**Returns**:
```json
{
  "status": "success",
  "backup_id": "backup_20251026_200000",
  "size_bytes": 1048576,
  "location": "s3://backups/backup_20251026_200000.tar.gz"
}
```

---

### ops.restore

**Purpose**: Database restore operations.

**Module**: `src.mcp.tools.ops.restore`  
**Scope**: `ops:restore`

#### Actions

##### execute

Restore from backup.

**Payload**:
```json
{
  "action": "execute",
  "backup_id": "backup_20251026_200000",
  "verify": true
}
```

**Security Notes**:
- Requires confirmation
- Destructive operation - logged extensively

---

## P5: Model Layer Tools

### model.manage

**Purpose**: Model lifecycle management (register, activate, deactivate, delete).

**Module**: `src.mcp.tools.model.manage`  
**Scope**: `model:admin`

#### Actions

##### register

Register new model provider/instance.

**Payload**:
```json
{
  "action": "register",
  "provider_id": "openai",
  "instance_name": "gpt-4",
  "config": {
    "api_key": "sk-...",
    "base_url": "https://api.openai.com/v1"
  }
}
```

##### activate

Activate model instance.

**Payload**:
```json
{
  "action": "activate",
  "instance_id": "gpt-4-instance-1"
}
```

##### deactivate

Deactivate model instance (soft delete).

**Payload**:
```json
{
  "action": "deactivate",
  "instance_id": "gpt-4-instance-1"
}
```

---

### model.test

**Purpose**: Model testing and validation.

**Module**: `src.mcp.tools.model.test`  
**Scope**: `model:test`

#### Actions

##### run_tests

Run test suite against model instance.

**Payload**:
```json
{
  "action": "run_tests",
  "instance_id": "gpt-4-instance-1",
  "test_suite": "basic",
  "max_tokens": 100
}
```

**Returns**:
```json
{
  "status": "passed",
  "tests_run": 5,
  "tests_passed": 5,
  "latency_p50": 250,
  "latency_p95": 450
}
```

---

## P6: User, Session & Platform Tools

### user.profile

**Purpose**: User profile management with JSONB merge.

**Module**: `src.mcp.tools.user.profile`  
**Scope**: `user:profile`

#### Actions

##### get

Get user profile.

**Payload**:
```json
{
  "action": "get",
  "user_id": "user_123"
}
```

##### update

Update user profile (JSONB merge).

**Payload**:
```json
{
  "action": "update",
  "user_id": "user_123",
  "profile_data": {
    "preferences": {"theme": "dark"},
    "metadata": {"last_login": "2025-10-26T20:00:00Z"}
  },
  "merge": true
}
```

**P6 Features**:
- JSONB merge for partial updates
- Input sanitation (HTML escape)
- Validation for required fields

---

### session.manage

**Purpose**: Session lifecycle with TTL enforcement.

**Module**: `src.mcp.tools.session.manage`  
**Scope**: `session:manage`

#### Actions

##### create

Create new session.

**Payload**:
```json
{
  "action": "create",
  "user_id": "user_123",
  "ttl_seconds": 3600,
  "metadata": {"device": "mobile"}
}
```

##### list

List sessions with pagination.

**Payload**:
```json
{
  "action": "list",
  "user_id": "user_123",
  "page": 1,
  "page_size": 20
}
```

**P6 Features**:
- TTL enforcement (default 1h, max 24h)
- Pagination for large result sets
- Automatic cleanup of expired sessions

---

### tenancy.manage

**Purpose**: Multi-tenancy operations with idempotent create.

**Module**: `src.mcp.tools.tenancy.manage`  
**Scope**: `tenancy:admin`

#### Actions

##### create

Create tenant (idempotent).

**Payload**:
```json
{
  "action": "create",
  "tenant_id": "acme-corp",
  "name": "Acme Corporation",
  "config": {"rate_limit": 1000}
}
```

**P6 Features**:
- Idempotent create (upsert behavior)
- Soft delete guards (prevent duplicate creation)
- Namespace isolation

---

### cache.manage

**Purpose**: Cache operations with TTL policy.

**Module**: `src.mcp.tools.cache.manage`  
**Scope**: `cache:admin`

#### Actions

##### set

Set cache entry.

**Payload**:
```json
{
  "action": "set",
  "key": "user:123:profile",
  "value": {...},
  "ttl_seconds": 300
}
```

##### invalidate_pattern

Invalidate by pattern.

**Payload**:
```json
{
  "action": "invalidate_pattern",
  "pattern": "user:*:profile"
}
```

**P6 Features**:
- TTL policy enforcement
- Pattern matching for bulk operations
- Cache hit/miss tracking

---

### catalog.discover

**Purpose**: Tool catalog discovery with manifest caching.

**Module**: `src.mcp.tools.catalog.discover`  
**Scope**: `catalog:read`

#### Actions

##### list_tools

List available tools.

**Payload**:
```json
{
  "action": "list_tools",
  "category": "graph",
  "include_deprecated": false
}
```

**P6 Features**:
- Manifest caching (5 min TTL)
- Category filtering
- Metadata enrichment

---

### agent.context

**Purpose**: Agent context management with caching and invalidation.

**Module**: `src.mcp.tools.agent.context`  
**Scope**: `agent:context`

#### Actions

##### get_context

Get agent context.

**Payload**:
```json
{
  "action": "get_context",
  "agent_id": "agent_123",
  "include_history": true
}
```

**P6 Features**:
- Context counts (messages, tools, memory)
- Caching with smart invalidation
- History compression

---

## P7: Output & Visualization Tools

### output.format

**Purpose**: Format data as JSON/CSV/Markdown/Text with deterministic output.

**Module**: `src.mcp.tools.output.format`  
**Scope**: `output:format`

#### Actions

##### json

Format as JSON or NDJSON.

**Payload**:
```json
{
  "action": "json",
  "data": [{"name": "Alice", "age": 30}],
  "ndjson": false,
  "sort_keys": true,
  "indent": 2
}
```

**P7 Features**:
- Deterministic output (sorted keys)
- Unicode safety (ensure_ascii=False)
- NDJSON support for streaming

##### csv

Format as CSV.

**Payload**:
```json
{
  "action": "csv",
  "data": [{"name": "Alice", "age": 30}],
  "delimiter": ",",
  "include_bom": false
}
```

**P7 Features**:
- Deterministic column order (alphabetically sorted)
- Unicode BOM support
- Custom delimiters

##### markdown

Format as Markdown table.

**Payload**:
```json
{
  "action": "markdown",
  "data": [{"name": "Alice", "age": 30}],
  "max_col_width": 50,
  "code_fence": false
}
```

**P7 Features**:
- Width caps with ellipsis (…)
- Pipe escaping
- Code fence option

---

### output.summarize

**Purpose**: Text summarization with deterministic simulate mode.

**Module**: `src.mcp.tools.output.summarize`  
**Scope**: `output:summarize`

#### Actions

##### extract

Extractive summarization.

**Payload**:
```json
{
  "action": "extract",
  "text": "Long document...",
  "ratio": 0.3
}
```

##### abstractive

Abstractive summarization (LLM-based).

**Payload**:
```json
{
  "action": "abstractive",
  "text": "Long document...",
  "simulate": true,
  "style": "bullets"
}
```

**P7 Features**:
- Deterministic simulate (hash-based)
- Multiple styles (plain, bullets, keypoints, academic)

##### map_reduce

Map-reduce for large documents.

**Payload**:
```json
{
  "action": "map_reduce",
  "text": "Very long document...",
  "chunk_chars": 1000,
  "overlap": 100
}
```

**P7 Features**:
- Chunking with configurable overlap
- Per-chunk summarization
- Final recombination

---

### viz.render

**Purpose**: Graph and table visualization with validation and escaping.

**Module**: `src.mcp.tools.viz.render`  
**Scope**: `viz:render`

#### Actions

##### graph_mermaid

Render Mermaid flowchart.

**Payload**:
```json
{
  "action": "graph_mermaid",
  "nodes": [{"id": "A"}, {"id": "B"}],
  "edges": [{"from": "A", "to": "B", "label": "rel"}],
  "direction": "LR",
  "max_nodes": 100
}
```

**P7 Features**:
- Input validation (required fields)
- HTML escaping (prevent XSS)
- Size caps (100 nodes, 200 edges)
- ID sanitization

##### table_markdown

Render Markdown table.

**Payload**:
```json
{
  "action": "table_markdown",
  "rows": [{"name": "Alice", "age": 30}],
  "columns": ["name", "age"],
  "max_rows": 1000
}
```

**P7 Features**:
- Deterministic column order
- Cell truncation (200 chars)
- Pipe escaping

---

## Error Handling

All tools return standardized error responses:

```json
{
  "status": "error",
  "error_code": "INVALID_INPUT",
  "message": "Missing required field: cypher",
  "details": {
    "field": "cypher",
    "constraint": "required"
  }
}
```

### Common Error Codes

- `INVALID_INPUT`: Validation error
- `UNAUTHORIZED`: Insufficient scope
- `RATE_LIMITED`: Rate limit exceeded
- `TIMEOUT`: Operation timeout
- `NOT_FOUND`: Resource not found
- `INTERNAL_ERROR`: Server error

---

## Best Practices

### 1. Always Use Parameterized Queries

```python
# ✅ Good
invoke({
    "action": "execute",
    "cypher": "MATCH (n:Person {name: $name}) RETURN n",
    "params": {"name": user_input}
})

# ❌ Bad (SQL injection risk)
invoke({
    "action": "execute",
    "cypher": f"MATCH (n:Person {{name: '{user_input}'}}) RETURN n"
})
```

### 2. Handle Errors Gracefully

```python
result = invoke(payload)
if result["status"] == "error":
    logger.error(f"Tool error: {result['message']}")
    return fallback_response()
return result
```

### 3. Use Pagination for Large Results

```python
# For large datasets
result = invoke({
    "action": "list",
    "page": 1,
    "page_size": 100
})
```

### 4. Respect Rate Limits

```python
# Implement exponential backoff
import time

def retry_with_backoff(payload, max_retries=3):
    for i in range(max_retries):
        result = invoke(payload)
        if result["status"] != "RATE_LIMITED":
            return result
        time.sleep(2 ** i)
    raise Exception("Max retries exceeded")
```

---

## Troubleshooting

### Common Issues

1. **Scope Errors**: Ensure user has required OAuth2 scope
2. **Rate Limits**: Implement retry logic with backoff
3. **Timeouts**: Adjust timeout parameter or optimize query
4. **Validation Errors**: Check payload schema against this reference

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger("mcp.tools").setLevel(logging.DEBUG)
```

---

## Changelog

### Version 1.0.0 (October 26, 2025)

- Initial comprehensive reference
- Documented all 18 tools across P1, P4, P5, P6, P7
- Added security notes, rate limits, best practices
- Included examples and error handling patterns

---

**For operational runbooks and SLOs, see**: `docs/ops/runbooks/`  
**For quickstart guides, see**: `docs/quickstarts/`  
**For architecture details, see**: `docs/tools-architecture.md`
