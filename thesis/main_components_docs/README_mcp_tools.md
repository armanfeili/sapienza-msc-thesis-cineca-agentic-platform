# MCP Tools Reference

This document provides comprehensive reference documentation for the Model Context Protocol (MCP) tools implemented in the Cineca Agentic Platform. These tools enable agents to interact with various platform components including graph databases, caching systems, security controls, and data processing utilities.

## Overview

The MCP tools framework provides a standardized interface for agent interactions with platform services. All tools follow consistent patterns:

- **Decorator-based registration**: Tools use `@mcp_tool` decorators with scope-based access control
- **Pydantic validation**: Input payloads are validated using Pydantic schemas
- **Structured responses**: All tools return consistent response formats with `ok`, `action`, and result fields
- **Error handling**: Comprehensive error handling with sanitization and logging
- **Audit logging**: All tool invocations are logged for security and debugging
- **Tenant isolation**: Multi-tenant support with proper data isolation

## Tool Categories

### Agent Tools (`agent.*`)

Tools for context assembly and metadata collection.

#### `agent.context`

Assembles execution context from various sources including user preferences, session data, and system state.

**Actions:**
- `assemble` (default): Collect and merge context from multiple sources

**Payload:**
```json
{
  "action": "assemble",
  "user_id": "string",
  "session_id": "string",
  "include_preferences": true,
  "include_history": true,
  "max_history_items": 50
}
```

**Response:**
```json
{
  "ok": true,
  "action": "assemble",
  "context": {
    "user": {...},
    "session": {...},
    "preferences": {...},
    "history": [...]
  },
  "sources": ["redis", "database"],
  "cached": false
}
```

**Security:** Requires `tools:read` scope. User data is sanitized and PII-scrubbed.

---

### Cache Tools (`cache.*`)

Redis-backed caching operations with tenant namespacing.

#### `cache.manage`

Manages cached data with TTL support and tenant isolation.

**Actions:**
- `get`: Retrieve cached value
- `set`: Store value with TTL
- `delete`: Remove cached value
- `exists`: Check if key exists
- `ttl`: Get remaining TTL
- `keys`: List keys matching pattern

**Payload:**
```json
{
  "action": "set",
  "key": "string",
  "value": "any JSON-serializable",
  "ttl_seconds": 3600,
  "namespace": "optional_custom_namespace"
}
```

**Response:**
```json
{
  "ok": true,
  "action": "set",
  "key": "namespaced:key",
  "ttl_seconds": 3600,
  "expires_at": "2025-01-01T12:00:00Z"
}
```

**Security:** Requires `tools:write` scope for mutations, `tools:read` for reads. Keys are automatically namespaced by tenant.

---

### Catalog Tools (`catalog.*`)

Tool discovery and metadata management.

#### `catalog.discover`

Discovers available MCP tools and their capabilities.

**Actions:**
- `list` (default): List all available tools
- `describe`: Get detailed metadata for specific tool
- `search`: Search tools by name or description

**Payload:**
```json
{
  "action": "describe",
  "tool_name": "graph.query",
  "include_schema": true,
  "include_examples": true
}
```

**Response:**
```json
{
  "ok": true,
  "action": "describe",
  "tool": {
    "name": "graph.query",
    "summary": "Execute read-only Cypher queries",
    "actions": ["execute", "explain"],
    "schema": {...},
    "examples": [...]
  }
}
```

**Security:** Requires `tools:read` scope. Results cached in Redis for performance.

---

### Data Tools (`data.*`)

Data management and quality operations.

#### `data.archive`

Archives graph data with soft-delete semantics.

**Actions:**
- `archive_nodes`: Mark nodes for archival
- `archive_edges`: Mark edges for archival
- `restore`: Restore archived data
- `purge`: Permanently delete archived data

**Payload:**
```json
{
  "action": "archive_nodes",
  "node_ids": ["uuid1", "uuid2"],
  "reason": "user_deletion",
  "archive_metadata": {"deleted_by": "user_123"}
}
```

**Response:**
```json
{
  "ok": true,
  "action": "archive_nodes",
  "archived_count": 2,
  "archive_batch_id": "batch_123"
}
```

**Security:** Requires `data:admin` scope. All operations are audited.

#### `data.quality`

Data quality checks and validation.

**Actions:**
- `check_integrity`: Validate graph integrity
- `find_orphans`: Identify orphaned nodes
- `validate_schema`: Check schema compliance
- `analyze_duplicates`: Find duplicate data

**Payload:**
```json
{
  "action": "check_integrity",
  "scope": "full",
  "sample_size": 10000,
  "parallel_checks": true
}
```

**Response:**
```json
{
  "ok": true,
  "action": "check_integrity",
  "checks": {
    "node_integrity": {"passed": 9500, "failed": 12},
    "edge_integrity": {"passed": 12000, "failed": 0}
  },
  "issues": [...]
}
```

**Security:** Requires `data:read` scope. Read-only operations.

---

### Database Tools (`db.*`)

Database connection management.

#### `db.switch`

Switches active database connections.

**Actions:**
- `switch`: Change active database
- `list`: List available databases
- `status`: Get connection status

**Payload:**
```json
{
  "action": "switch",
  "database": "memgraph_prod",
  "validate_connection": true
}
```

**Response:**
```json
{
  "ok": true,
  "action": "switch",
  "previous_database": "memgraph_dev",
  "current_database": "memgraph_prod",
  "connection_valid": true
}
```

**Security:** Requires `db:admin` scope. Operations are audited.

---

### Error Tools (`errors.*`)

Error reporting and management.

#### `errors.report`

Structured error reporting with sanitization.

**Actions:**
- `report`: Submit error report
- `list`: List recent errors
- `details`: Get error details

**Payload:**
```json
{
  "action": "report",
  "error_type": "validation_error",
  "message": "Invalid input format",
  "context": {"tool": "graph.query", "payload": {...}},
  "severity": "warning"
}
```

**Response:**
```json
{
  "ok": true,
  "action": "report",
  "error_id": "err_123",
  "reported_at": "2025-01-01T12:00:00Z"
}
```

**Security:** Requires `tools:read` scope. PII is automatically scrubbed.

---

### Graph Tools (`graph.*`)

Comprehensive graph database operations.

#### `graph.analytics`

Graph analytics with bounded computation.

**Actions:**
- `centrality`: Calculate node centrality
- `communities`: Detect communities
- `paths`: Find paths between nodes
- `shortest_path`: Calculate shortest paths

**Payload:**
```json
{
  "action": "centrality",
  "algorithm": "degree",
  "limit": 100,
  "timeout_seconds": 30
}
```

**Response:**
```json
{
  "ok": true,
  "action": "centrality",
  "results": [
    {"node_id": "n1", "centrality": 0.85},
    {"node_id": "n2", "centrality": 0.72}
  ],
  "computation_time_ms": 1250
}
```

**Security:** Requires `graph:read` scope. Computation is bounded to prevent resource exhaustion.

#### `graph.bulk`

Bulk graph operations with idempotency.

**Actions:**
- `create_nodes`: Bulk node creation
- `create_edges`: Bulk edge creation
- `update_properties`: Bulk property updates
- `delete`: Bulk deletion

**Payload:**
```json
{
  "action": "create_nodes",
  "nodes": [
    {"id": "n1", "labels": ["Person"], "properties": {"name": "Alice"}},
    {"id": "n2", "labels": ["Person"], "properties": {"name": "Bob"}}
  ],
  "idempotent": true,
  "batch_size": 100
}
```

**Response:**
```json
{
  "ok": true,
  "action": "create_nodes",
  "created_count": 2,
  "batch_id": "bulk_123",
  "idempotent": true
}
```

**Security:** Requires `graph:write` scope. Operations are transactional and audited.

#### `graph.crud`

CRUD operations for Memgraph with RBAC.

**Actions:**
- `create_node`: Create single node
- `read_node`: Read node by ID
- `update_node`: Update node properties
- `delete_node`: Delete node
- `create_edge`: Create edge
- `read_edge`: Read edge
- `update_edge`: Update edge properties
- `delete_edge`: Delete edge

**Payload:**
```json
{
  "action": "create_node",
  "labels": ["Person"],
  "properties": {"name": "Alice", "age": 30},
  "id": "optional_custom_id"
}
```

**Response:**
```json
{
  "ok": true,
  "action": "create_node",
  "node": {
    "id": "generated_uuid",
    "labels": ["Person"],
    "properties": {"name": "Alice", "age": 30}
  }
}
```

**Security:** Requires appropriate `graph:*` scopes based on operation type.

#### `graph.generate_cypher`

Generate Cypher queries from natural language.

**Actions:**
- `generate`: Convert NL to Cypher
- `validate`: Validate generated Cypher
- `explain`: Explain query execution plan

**Payload:**
```json
{
  "action": "generate",
  "query": "Find all people who work at universities",
  "context": {"domain": "academic"},
  "safety_checks": true
}
```

**Response:**
```json
{
  "ok": true,
  "action": "generate",
  "cypher": "MATCH (p:Person)-[:WORKS_AT]->(u:University) RETURN p, u",
  "safety_score": 0.95,
  "validation": "passed"
}
```

**Security:** Requires `graph:read` scope. Generated queries are validated for safety.

#### `graph.query`

Execute read-only Cypher queries.

**Actions:**
- `execute`: Execute Cypher query
- `explain`: Get query execution plan

**Payload:**
```json
{
  "action": "execute",
  "query": "MATCH (p:Person) RETURN p.name LIMIT 10",
  "parameters": {},
  "timeout_seconds": 30
}
```

**Response:**
```json
{
  "ok": true,
  "action": "execute",
  "results": [
    {"p.name": "Alice"},
    {"p.name": "Bob"}
  ],
  "execution_time_ms": 45,
  "row_count": 2
}
```

**Security:** Requires `graph:read` scope. Read-only queries only.

#### `graph.schema`

Schema discovery and management.

**Actions:**
- `get_schema`: Get current schema
- `list_labels`: List node labels
- `list_relationships`: List relationship types
- `get_constraints`: Get schema constraints

**Payload:**
```json
{
  "action": "get_schema",
  "include_properties": true,
  "include_counts": true
}
```

**Response:**
```json
{
  "ok": true,
  "action": "get_schema",
  "schema": {
    "labels": ["Person", "University"],
    "relationships": ["WORKS_AT", "STUDIES_AT"],
    "constraints": [...]
  }
}
```

**Security:** Requires `graph:read` scope.

#### `graph.search`

Read-only search over nodes and edges.

**Actions:**
- `search_nodes`: Search nodes by properties
- `search_edges`: Search edges by properties
- `fulltext_search`: Full-text search

**Payload:**
```json
{
  "action": "search_nodes",
  "label": "Person",
  "properties": {"name": {"$regex": "Alice.*"}},
  "limit": 50,
  "sort_by": "name"
}
```

**Response:**
```json
{
  "ok": true,
  "action": "search_nodes",
  "results": [
    {"id": "n1", "labels": ["Person"], "properties": {"name": "Alice"}}
  ],
  "total_count": 1,
  "page": 1
}
```

**Security:** Requires `graph:read` scope. Results are paginated.

#### `graph.secure_query`

Natural language to Cypher with validation.

**Actions:**
- `query`: Execute NL-to-Cypher query
- `explain`: Explain generated query

**Payload:**
```json
{
  "action": "query",
  "question": "How many people work at each university?",
  "validate_safety": true,
  "max_results": 100
}
```

**Response:**
```json
{
  "ok": true,
  "action": "query",
  "cypher": "MATCH (p:Person)-[:WORKS_AT]->(u:University) RETURN u.name, count(p)",
  "results": [
    {"u.name": "MIT", "count(p)": 150},
    {"u.name": "Stanford", "count(p)": 120}
  ]
}
```

**Security:** Requires `graph:read` scope. Queries are validated for safety.

---

### Model Tools (`model.*`)

Runtime LLM adapter management.

#### `model.manage`

Manage LLM model configurations and switching.

**Actions:**
- `list`: List available models
- `switch`: Switch active model
- `status`: Get model status
- `configure`: Update model settings

**Payload:**
```json
{
  "action": "switch",
  "model_id": "gpt-4",
  "parameters": {"temperature": 0.7, "max_tokens": 1000}
}
```

**Response:**
```json
{
  "ok": true,
  "action": "switch",
  "previous_model": "gpt-3.5-turbo",
  "current_model": "gpt-4",
  "parameters": {"temperature": 0.7, "max_tokens": 1000}
}
```

**Security:** Requires `model:admin` scope.

#### `model.test`

Lightweight LLM testing with simulate mode.

**Actions:**
- `test_completion`: Test text completion
- `test_embedding`: Test embedding generation
- `benchmark`: Run performance benchmark

**Payload:**
```json
{
  "action": "test_completion",
  "prompt": "Hello, world!",
  "max_tokens": 50,
  "simulate": true
}
```

**Response:**
```json
{
  "ok": true,
  "action": "test_completion",
  "response": "Hello! How can I help you today?",
  "tokens_used": 12,
  "latency_ms": 245
}
```

**Security:** Requires `model:read` scope. Simulate mode available for testing.

---

### Output Tools (`output.*`)

Result formatting and summarization.

#### `output.format`

Portable result formatters.

**Actions:**
- `json`: Format as JSON
- `csv`: Format as CSV
- `markdown`: Format as Markdown table
- `text`: Format as plain text

**Payload:**
```json
{
  "action": "csv",
  "data": [
    {"name": "Alice", "age": 30},
    {"name": "Bob", "age": 25}
  ],
  "include_headers": true
}
```

**Response:**
```json
{
  "ok": true,
  "action": "csv",
  "content": "name,age\nAlice,30\nBob,25",
  "content_type": "text/csv",
  "row_count": 2
}
```

**Security:** Requires `tools:read` scope.

#### `output.summarize`

Extractive and abstractive summarization.

**Actions:**
- `extractive`: Extract key sentences
- `abstractive`: Generate summary
- `keywords`: Extract keywords

**Payload:**
```json
{
  "action": "abstractive",
  "text": "Long document text...",
  "max_length": 200,
  "style": "concise"
}
```

**Response:**
```json
{
  "ok": true,
  "action": "abstractive",
  "summary": "Concise summary of the document...",
  "compression_ratio": 0.15,
  "key_points": [...]
}
```

**Security:** Requires `tools:read` scope.

---

### Privacy Tools (`privacy.*`)

Consent management and PII handling.

#### `privacy.consent`

Redis-backed user consent registry.

**Actions:**
- `get`: Get user consent status
- `set`: Set consent preferences
- `revoke`: Revoke consent
- `audit`: Get consent history

**Payload:**
```json
{
  "action": "set",
  "user_id": "user_123",
  "consents": {
    "data_processing": true,
    "analytics": false,
    "marketing": false
  },
  "version": "1.0"
}
```

**Response:**
```json
{
  "ok": true,
  "action": "set",
  "consent_id": "consent_123",
  "recorded_at": "2025-01-01T12:00:00Z"
}
```

**Security:** Requires `privacy:admin` scope. All operations are audited.

---

### Rate Limit Tools (`ratelimit.*`)

Administrative rate limiter controls.

#### `ratelimit.manage`

Manage rate limiting rules and status.

**Actions:**
- `get_limits`: Get current limits
- `set_limits`: Update rate limits
- `reset`: Reset counters
- `status`: Get rate limit status

**Payload:**
```json
{
  "action": "set_limits",
  "scope": "user",
  "identifier": "user_123",
  "limits": {
    "requests_per_minute": 60,
    "requests_per_hour": 1000
  }
}
```

**Response:**
```json
{
  "ok": true,
  "action": "set_limits",
  "scope": "user",
  "identifier": "user_123",
  "effective_at": "2025-01-01T12:00:00Z"
}
```

**Security:** Requires `ratelimit:admin` scope.

---

### Security Tools (`security.*`)

Security operations and audit.

#### `security.allowed_operations`

List operations permitted for current principal.

**Actions:**
- `list`: List allowed operations

**Payload:**
```json
{
  "action": "list",
  "resource_type": "graph",
  "include_scopes": true
}
```

**Response:**
```json
{
  "ok": true,
  "action": "list",
  "operations": ["read", "write"],
  "scopes": ["graph:read", "graph:write"]
}
```

**Security:** Requires `security:read` scope.

#### `security.audit`

Record and query audit events.

**Actions:**
- `log`: Record audit event
- `query`: Query audit logs
- `export`: Export audit data

**Payload:**
```json
{
  "action": "log",
  "event_type": "data_access",
  "resource": "graph.node.123",
  "action": "read",
  "metadata": {"tool": "graph.query"}
}
```

**Response:**
```json
{
  "ok": true,
  "action": "log",
  "event_id": "audit_123",
  "recorded_at": "2025-01-01T12:00:00Z"
}
```

**Security:** Requires `security:audit` scope.

#### `security.check`

Security configuration validation.

**Actions:**
- `validate_config`: Validate security settings
- `check_permissions`: Verify permission setup
- `audit_config`: Audit security configuration

**Payload:**
```json
{
  "action": "validate_config",
  "check_encryption": true,
  "check_network": true,
  "check_access": true
}
```

**Response:**
```json
{
  "ok": true,
  "action": "validate_config",
  "checks": {
    "encryption": {"status": "passed"},
    "network": {"status": "passed"},
    "access": {"status": "warning", "message": "..."}
  }
}
```

**Security:** Requires `security:admin` scope.

#### `security.describe_principal`

Introspect current principal identity.

**Actions:**
- `describe`: Get principal details

**Payload:**
```json
{
  "action": "describe",
  "include_groups": true,
  "include_permissions": true
}
```

**Response:**
```json
{
  "ok": true,
  "action": "describe",
  "principal": {
    "id": "user_123",
    "type": "user",
    "groups": ["admin", "users"],
    "permissions": ["graph:read", "graph:write"]
  }
}
```

**Security:** Requires `security:read` scope.

#### `security.permissions`

Policy-aware permission checking.

**Actions:**
- `check`: Check specific permission
- `list_policies`: List applicable policies
- `evaluate`: Evaluate permission with context

**Payload:**
```json
{
  "action": "check",
  "resource": "graph.node.123",
  "action": "write",
  "context": {"tenant": "tenant_1"}
}
```

**Response:**
```json
{
  "ok": true,
  "action": "check",
  "allowed": true,
  "policies_applied": ["tenant_isolation", "resource_ownership"]
}
```

**Security:** Requires `security:read` scope.

---

### Session Tools (`session.*`)

Session lifecycle management.

#### `session.manage`

Session lifecycle with TTL enforcement.

**Actions:**
- `create`: Create new session
- `get`: Retrieve session data
- `update`: Update session data
- `delete`: Delete session
- `extend`: Extend session TTL

**Payload:**
```json
{
  "action": "create",
  "user_id": "user_123",
  "data": {"preferences": {...}},
  "ttl_seconds": 3600
}
```

**Response:**
```json
{
  "ok": true,
  "action": "create",
  "session_id": "session_123",
  "expires_at": "2025-01-01T13:00:00Z"
}
```

**Security:** Requires `session:write` scope for mutations, `session:read` for reads.

---

### System Tools (`system.*`)

System monitoring and management.

#### `system.backup`

Backup creation and management.

**Actions:**
- `create`: Create backup
- `list`: List backups
- `restore`: Restore from backup
- `delete`: Delete backup
- `export`: Export data
- `import`: Import data

**Payload:**
```json
{
  "action": "create",
  "type": "full",
  "name": "daily_backup_2025_01_01",
  "include_data": true,
  "include_schema": true,
  "compression": "gzip"
}
```

**Response:**
```json
{
  "ok": true,
  "action": "create",
  "backup_id": "backup_123",
  "size_bytes": 1048576,
  "created_at": "2025-01-01T12:00:00Z"
}
```

**Security:** Requires `system:admin` scope. Operations are audited.

#### `system.health`

Liveness and readiness checks.

**Actions:**
- `liveness`: Quick self-check
- `readiness`: Dependency checks
- `details`: Readiness with version info

**Payload:**
```json
{
  "action": "readiness"
}
```

**Response:**
```json
{
  "ok": true,
  "action": "readiness",
  "checked_at": "2025-01-01T12:00:00Z",
  "summary": {"passed": 3, "failed": 0, "skipped": 0},
  "components": {
    "app": {"status": "up", "latency_ms": 0.5},
    "db": {"status": "up", "latency_ms": 12.3},
    "redis": {"status": "up", "latency_ms": 2.1}
  }
}
```

**Security:** Requires `tools:read` scope.

#### `system.metrics`

Prometheus metrics scraping.

**Actions:**
- `scrape`: Get metrics snapshot
- `info`: Get registry info

**Payload:**
```json
{
  "action": "scrape",
  "format": "json",
  "names": ["http_requests_total", "response_time_*"]
}
```

**Response:**
```json
{
  "ok": true,
  "action": "scrape",
  "format": "json",
  "metrics": [
    {
      "name": "http_requests_total",
      "type": "counter",
      "samples": [{"value": 1234}]
    }
  ]
}
```

**Security:** Requires `tools:read` scope.

#### `system.status`

High-level service status snapshot.

**Actions:**
- `status`: Get comprehensive status

**Payload:**
```json
{
  "action": "status",
  "detail": "full"
}
```

**Response:**
```json
{
  "ok": true,
  "action": "status",
  "service": {
    "name": "Cineca Agentic Platform",
    "version": "0.1.0",
    "env": "production",
    "uptime_sec": 3600
  },
  "components": {
    "memgraph": {"enabled": true, "ok": true},
    "redis": {"enabled": true, "ok": true},
    "otel": {"enabled": false}
  }
}
```

**Security:** Requires `tools:read` scope.

---

### Tenancy Tools (`tenancy.*`)

Tenant administration.

#### `tenancy.manage`

Tenant lifecycle management.

**Actions:**
- `list`: List tenants
- `current`: Get current tenant
- `switch`: Switch active tenant
- `create`: Create tenant
- `delete`: Delete tenant
- `set-default`: Set default tenant

**Payload:**
```json
{
  "action": "create",
  "tenant_id": "tenant_123",
  "name": "New Organization",
  "metadata": {"plan": "enterprise"}
}
```

**Response:**
```json
{
  "ok": true,
  "action": "create",
  "tenant": {
    "id": "tenant_123",
    "name": "New Organization",
    "created_at": "2025-01-01T12:00:00Z"
  },
  "idempotent": true
}
```

**Security:** Requires `tools:admin` scope. Soft delete guard prevents accidental deletion.

---

### User Tools (`user.*`)

User profile management.

#### `user.profile`

User preferences and profile store.

**Actions:**
- `get`: Retrieve profile
- `set`: Replace profile
- `update`: Merge profile changes
- `delete`: Delete profile

**Payload:**
```json
{
  "action": "update",
  "user_id": "user_123",
  "patch": {
    "preferences": {"theme": "dark"},
    "last_login": "2025-01-01T12:00:00Z"
  }
}
```

**Response:**
```json
{
  "ok": true,
  "action": "update",
  "profile": {
    "user_id": "user_123",
    "preferences": {"theme": "dark"},
    "updated_at": "2025-01-01T12:00:00Z"
  }
}
```

**Security:** Requires `tools:user` scope. JSONB merge semantics for updates.

---

### Visualization Tools (`viz.*`)

Data visualization utilities.

#### `viz.render`

Render data structures as visualizations.

**Actions:**
- `render_graph`: Render graph as Mermaid/DOT
- `render_table`: Render data as Markdown table
- `sparkline`: Render numbers as Unicode sparkline

**Payload:**
```json
{
  "action": "render_graph",
  "format": "mermaid",
  "graph": {
    "nodes": [{"id": "A", "label": "Node A"}],
    "edges": [{"from": "A", "to": "B", "label": "REL"}]
  }
}
```

**Response:**
```json
{
  "ok": true,
  "action": "render_graph",
  "data": {
    "content_type": "text/mermaid",
    "content": "flowchart LR\n  A[\"Node A\"]\n  A --> B"
  }
}
```

**Security:** Requires `viz:render` scope. Input validation prevents injection attacks.

---

## Common Patterns

### Error Handling

All tools follow consistent error handling:

```json
{
  "ok": false,
  "action": "requested_action",
  "error": "human_readable_message",
  "error_code": "MACHINE_READABLE_CODE",
  "details": {...}
}
```

### Pagination

Tools that return lists support pagination:

```json
{
  "results": [...],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_count": 150,
    "has_next": true,
    "has_prev": false
  }
}
```

### Idempotency

Mutation operations support idempotency where appropriate:

```json
{
  "ok": true,
  "idempotent": true,
  "created": false,  // false = already existed
  "resource_id": "existing_id"
}
```

### Audit Trail

All operations are automatically audited with correlation IDs:

```json
{
  "ok": true,
  "audit": {
    "correlation_id": "corr_123",
    "principal": "user_123",
    "tenant": "tenant_1",
    "timestamp": "2025-01-01T12:00:00Z"
  }
}
```

## Security Considerations

- **Scope-based access control**: All tools require specific scopes
- **Tenant isolation**: Data is automatically isolated by tenant
- **PII scrubbing**: Sensitive data is automatically redacted in logs
- **Input validation**: All inputs are validated and sanitized
- **Rate limiting**: Tools are protected against abuse
- **Audit logging**: All operations are logged for compliance

## Performance Characteristics

- **Caching**: Redis-backed caching for frequently accessed data
- **Pagination**: Large result sets are paginated
- **Timeouts**: Operations have configurable timeouts
- **Resource limits**: Computation is bounded to prevent resource exhaustion
- **Async support**: Long-running operations support async execution

## Monitoring and Observability

All tools emit metrics to Prometheus:
- `mcp_tool_invocations_total`: Total tool invocations by tool and action
- `mcp_tool_duration_seconds`: Tool execution duration histograms
- `mcp_tool_errors_total`: Error counts by tool and error type

Structured logging includes correlation IDs, tenant context, and performance metrics.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/README_mcp_tools.md