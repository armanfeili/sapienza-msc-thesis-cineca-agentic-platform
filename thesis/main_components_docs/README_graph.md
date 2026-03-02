# Graph Tools Reference

This document provides comprehensive reference documentation for the Graph MCP tools implemented in the Cineca Agentic Platform. These tools provide complete graph database operations over Memgraph, including analytics, bulk operations, CRUD, Cypher generation, query execution, schema discovery, search, and secure natural language querying.

## Overview

The Graph tools framework provides a comprehensive interface for interacting with Memgraph graph databases through the Model Context Protocol (MCP). All tools follow consistent patterns:

- **Decorator-based registration**: Tools use `@mcp_tool` decorators with scope-based access control
- **Pydantic validation**: Input payloads are validated using Pydantic schemas
- **Structured responses**: All tools return consistent response formats with `ok`, `action`, and result fields
- **Error handling**: Comprehensive error handling with sanitization and logging
- **Audit logging**: All tool invocations are logged for security and debugging
- **Tenant isolation**: Multi-tenant support with proper data isolation
- **Read-only enforcement**: Many tools enforce read-only operations for safety

## Tool Categories

### Analytics Tools (`graph.analytics`)

Graph analytics operations with bounded computation for performance and safety.

#### `graph.analytics` - Core Analytics Tool

Provides graph analytics capabilities with timeout and size limits to prevent resource exhaustion.

**Actions:**
- `degree_distribution`: Compute degree distribution statistics
- `shortest_path`: Find shortest path between nodes
- `top_k_degree`: Get top-k highest degree nodes
- `label_counts`: Count nodes by label
- `relationship_counts`: Count relationships by type

**Payload Structure:**
```json
{
  "action": "degree_distribution",
  "label": "User",
  "row_limit": 1000,
  "timeout_ms": 5000,
  "principal": "user-123",
  "tenant": "tenant-1"
}
```

**Response Structure:**
```json
{
  "ok": true,
  "action": "degree_distribution",
  "label": "User",
  "summary": {
    "min": 0,
    "max": 45,
    "avg": 12.3
  },
  "distribution": [
    {"degree": 1, "count": 150},
    {"degree": 2, "count": 89}
  ]
}
```

**Security:** Requires `tools:basic` scope. All operations are read-only with bounded computation.

**Features:**
- **Bounded computation**: Timeout limits and row caps prevent resource exhaustion
- **Label filtering**: Optional filtering by node labels
- **Statistical summaries**: Min/max/average calculations for distributions
- **Pagination support**: Row limits for large result sets

---

### Bulk Operations (`graph.bulk`)

Batch operations for efficient data ingestion and updates with idempotency support.

#### `graph.bulk` - Bulk Data Operations

Handles large-scale data operations with batching, validation, and error handling.

**Actions:**
- `ingest_nodes`: Bulk create/update nodes with MERGE semantics
- `ingest_edges`: Bulk create/update relationships with MERGE semantics
- `upsert_nodes`: Idempotent node operations with duplicate detection
- `upsert_edges`: Idempotent relationship operations with duplicate detection

**Payload Structure:**
```json
{
  "action": "ingest_nodes",
  "nodes": [
    {
      "labels": ["Person"],
      "orig_id": "person-1",
      "props": {"name": "Alice", "age": 30}
    }
  ],
  "batch_size": 100,
  "idempotency_key": "batch-123",
  "dry_run": false,
  "fail_fast": true,
  "principal": "user-123",
  "tenant": "tenant-1"
}
```

**Response Structure:**
```json
{
  "ok": true,
  "action": "ingest_nodes",
  "processed": 100,
  "succeeded": 98,
  "failed": 2,
  "skipped": 0,
  "errors": ["Node 5: invalid label format"],
  "elapsed_ms": 1250,
  "batch_id": "bulk-123"
}
```

**Security:** Requires `tools:write` scope. All operations are audited.

**Features:**
- **Batch processing**: Configurable batch sizes (1-1000) for optimal performance
- **Idempotency**: Optional idempotency keys prevent duplicate processing
- **Dry-run mode**: Validation without actual data modification
- **Error handling**: Continue-on-error or fail-fast modes
- **Progress tracking**: Detailed success/failure/skipped counts
- **Metadata injection**: Automatic tenant and user tracking

---

### CRUD Operations (`graph.crud`)

Focused Create, Read, Update, Delete operations with strict RBAC enforcement.

#### `graph.crud` - Graph CRUD Operations

Provides atomic CRUD operations for nodes and relationships with full audit trails.

**Actions:**
- `create_node`: Create new node with labels and properties
- `update_node`: Update existing node properties (merge or replace)
- `delete_node`: Delete node with optional DETACH
- `create_relationship`: Create relationship between nodes
- `delete_relationship`: Delete relationship between nodes

**Payload Structure:**
```json
{
  "action": "create_node",
  "labels": ["Person"],
  "properties": {
    "orig_id": "person-1",
    "name": "Alice",
    "email": "alice@example.com"
  },
  "principal": "user-123",
  "tenant": "tenant-1"
}
```

**Response Structure:**
```json
{
  "ok": true,
  "operation": "create_node",
  "created": true,
  "node": {
    "orig_id": "person-1",
    "labels": ["Person"],
    "properties": {
      "name": "Alice",
      "email": "alice@example.com",
      "created_by": "user-123",
      "tenant": "tenant-1"
    }
  },
  "elapsed_ms": 45
}
```

**Security:** Requires `tools:write` scope. All operations are audited and tenant-isolated.

**Features:**
- **MERGE semantics**: Idempotent creation with conflict resolution
- **Flexible matching**: Match by orig_id or label + property conditions
- **Merge vs replace**: Choose between property merging or full replacement
- **Relationship management**: Bidirectional relationship operations
- **Metadata tracking**: Automatic created_by, updated_by, timestamps

---

### Cypher Generation (`graph.generate_cypher`)

Safe Cypher query generation from natural language or structured inputs.

#### `graph.generate_cypher` - Cypher Query Generation

Generates parameterized Cypher queries without execution, ensuring safety and portability.

**Actions:**
- `select`: Generate SELECT queries with filtering and projection
- `insert_node`: Generate node creation queries
- `update_node`: Generate node update queries
- `delete_node`: Generate node deletion queries
- `upsert_rel`: Generate relationship upsert queries
- `match_rel`: Generate relationship matching queries
- `count_by_label`: Generate label counting queries
- `schema_inventory`: Generate comprehensive schema inventory

**Payload Structure:**
```json
{
  "action": "select",
  "label": "Person",
  "where": {"status": "active"},
  "return": ["orig_id", "name", "email"],
  "limit": 100
}
```

**Response Structure:**
```json
{
  "ok": true,
  "action": "select",
  "read_only": true,
  "cypher": "MATCH (n:`Person`) WHERE n.`status` = $status RETURN n.`orig_id` AS orig_id, n.`name` AS name, n.`email` AS email LIMIT $limit",
  "params": {
    "status": "active",
    "limit": 100
  }
}
```

**Security:** Requires `tools:basic` scope. Generates only safe, parameterized queries.

**Features:**
- **Parameterization**: Automatic parameter extraction for security
- **Label escaping**: Safe handling of special characters in labels
- **Read-only enforcement**: Clear separation of read vs write operations
- **Flexible projections**: Custom return field selection
- **Schema awareness**: Context-aware query generation

---

### Query Execution (`graph.query`)

Thin execution layer for ad-hoc Cypher queries with safety controls.

#### `graph.query` - Cypher Query Execution

Executes Cypher queries with write detection, timeout controls, and result formatting.

**Actions:**
- `run`: Execute Cypher query and return results
- `explain`: Get query execution plan
- `profile`: Get detailed query execution profile

**Payload Structure:**
```json
{
  "action": "run",
  "cypher": "MATCH (n:Person) WHERE n.status = $status RETURN n.name LIMIT $limit",
  "params": {"status": "active", "limit": 50},
  "read_only": true,
  "timeout_ms": 5000,
  "limit": 1000
}
```

**Response Structure:**
```json
{
  "ok": true,
  "action": "run",
  "columns": ["n.name"],
  "rows": [
    {"n.name": "Alice"},
    {"n.name": "Bob"}
  ],
  "rowcount": 2,
  "truncated": false,
  "read_only": true
}
```

**Security:** Requires `tools:basic` scope. Write operation detection and blocking.

**Features:**
- **Write detection**: Pattern-based identification of write operations
- **Timeout protection**: Configurable query timeouts
- **Result limiting**: Client-side row truncation
- **Parameter validation**: Safe parameter handling
- **Execution planning**: EXPLAIN and PROFILE support

---

### Schema Discovery (`graph.schema`)

Comprehensive schema discovery utilities for Memgraph databases.

#### `graph.schema` - Schema Information

Provides detailed schema information including labels, relationships, properties, and constraints.

**Actions:**
- `labels`: List all node labels
- `relationship_types`: List all relationship types
- `node_properties`: Get properties for node labels
- `relationship_properties`: Get properties for relationship types
- `node_counts`: Count nodes by label
- `relationship_counts`: Count relationships by type
- `indexes`: List database indexes
- `constraints`: List database constraints
- `inventory`: Comprehensive schema inventory

**Payload Structure:**
```json
{
  "action": "node_properties",
  "label": "Person"
}
```

**Response Structure:**
```json
{
  "ok": true,
  "action": "node_properties",
  "label": "Person",
  "items": ["name", "email", "age", "created_at"]
}
```

**Security:** Requires `tools:basic` scope. All operations are read-only.

**Features:**
- **Comprehensive coverage**: Labels, types, properties, counts
- **Index information**: Database index details and state
- **Constraint discovery**: Schema constraint enumeration
- **Inventory generation**: Portable schema documentation
- **Fallback handling**: Graceful degradation for unsupported features

---

### Search Operations (`graph.search`)

Query-builder style search with filtering, pagination, and projections.

#### `graph.search` - Advanced Search

Provides structured search capabilities with advanced filtering and result formatting.

**Actions:**
- `nodes`: Search nodes with label/property filters and pagination
- `edges`: Search relationships with type/property filters
- `count`: Count matching nodes or edges
- `distinct`: Get distinct values for properties

**Payload Structure:**
```json
{
  "action": "nodes",
  "label": "Person",
  "where": {"status": "active", "department": "engineering"},
  "select": ["orig_id", "name", "email"],
  "order_by": "name",
  "order_desc": false,
  "page": 1,
  "page_size": 25,
  "principal": "user-123",
  "tenant": "tenant-1"
}
```

**Response Structure:**
```json
{
  "ok": true,
  "action": "nodes",
  "items": [
    {
      "orig_id": "person-1",
      "labels": ["Person"],
      "name": "Alice",
      "email": "alice@example.com"
    }
  ],
  "page": 1,
  "page_size": 25,
  "total": 150,
  "count": 25
}
```

**Security:** Requires `tools:basic` scope. All operations are read-only.

**Features:**
- **Advanced filtering**: Multiple label support, complex property conditions
- **Flexible projections**: Custom field selection and renaming
- **Pagination**: Full pagination metadata and controls
- **Sorting**: Configurable ordering by properties
- **Distinct queries**: Unique value extraction for properties

---

### Secure Query (`graph.secure_query`)

End-to-end secure natural language to Cypher pipeline with validation and execution.

#### `graph.secure_query` - Secure NL-to-Cypher

Provides the complete secure query pipeline from natural language to validated results.

**Actions:**
- `ask`: End-to-end NL query processing (generate → validate → execute)
- `generate`: Generate Cypher from natural language
- `validate`: Validate Cypher queries for safety
- `execute`: Execute pre-validated queries

**Payload Structure:**
```json
{
  "action": "ask",
  "prompt": "Show me all active users in the engineering department",
  "principal": "user-123",
  "tenant": "tenant-1",
  "max_rows": 100,
  "return_format": "rows"
}
```

**Response Structure:**
```json
{
  "ok": true,
  "action": "ask",
  "prompt": "Show me all active users in the engineering department",
  "cypher": "MATCH (n:Person) WHERE n.status = $status AND n.department = $department RETURN n.name, n.email",
  "params": {"status": "active", "department": "engineering"},
  "columns": ["n.name", "n.email"],
  "rows": [
    {"n.name": "Alice", "n.email": "alice@example.com"},
    {"n.name": "Bob", "n.email": "bob@example.com"}
  ],
  "rowcount": 2,
  "validation": {
    "read_only": true,
    "safe": true,
    "allowed": true
  }
}
```

**Security:** Requires `tools:basic` scope. Comprehensive safety validation and permission checking.

**Features:**
- **NL-to-Cypher**: LLM-powered query generation from natural language
- **Safety validation**: Multi-layer security checks (write detection, forbidden clauses)
- **Permission enforcement**: RBAC integration with role-based access control
- **Result formatting**: Multiple output formats (rows, JSON, CSV, Markdown)
- **Audit trail**: Complete audit logging of all operations
- **Rate limiting**: Built-in rate limiting protection
- **Timeout controls**: Configurable execution timeouts

## Common Patterns

### Error Handling

All Graph tools follow consistent error handling:

```json
{
  "ok": false,
  "action": "requested_action",
  "error": "human_readable_message",
  "error_code": "VALIDATION_ERROR",
  "details": {
    "field": "cypher",
    "reason": "write_operation_detected"
  }
}
```

### Pagination

Search and analytics tools support pagination:

```json
{
  "items": [...],
  "pagination": {
    "page": 1,
    "page_size": 25,
    "total_count": 150,
    "has_next": true,
    "has_prev": false
  }
}
```

### Idempotency

Bulk operations support idempotency:

```json
{
  "processed": 100,
  "succeeded": 95,
  "failed": 3,
  "skipped": 2,
  "idempotency_key": "batch-123"
}
```

### Validation Results

Secure query provides detailed validation:

```json
{
  "validation": {
    "read_only": true,
    "safe": true,
    "allowed": true,
    "checks": {
      "write_operations": false,
      "forbidden_clauses": [],
      "tenant_scoped": true
    }
  }
}
```

## Security Considerations

- **Scope-based access**: `tools:basic` for read operations, `tools:write` for mutations
- **Tenant isolation**: All operations are tenant-scoped with automatic filtering
- **Write detection**: Pattern-based identification and blocking of write operations
- **Parameter safety**: All queries use parameterization to prevent injection
- **Audit logging**: Complete audit trail for all operations
- **Rate limiting**: Built-in protection against abuse
- **Timeout protection**: All operations have configurable timeouts

## Performance Characteristics

- **Batch processing**: Bulk operations use configurable batch sizes
- **Query optimization**: Efficient Cypher generation with proper indexing
- **Result limiting**: Client and server-side result size controls
- **Timeout management**: Configurable timeouts prevent runaway operations
- **Connection pooling**: Efficient database connection management
- **Caching**: Schema information caching for performance

## Monitoring and Observability

All Graph tools emit detailed metrics:

- `graph_tool_invocations_total`: Tool invocation counts by tool and action
- `graph_tool_duration_seconds`: Execution duration histograms
- `graph_tool_errors_total`: Error counts by type
- `graph_query_rows_returned`: Result set sizes
- `graph_bulk_operations`: Bulk operation metrics

Structured logging includes:
- Query execution times
- Result counts
- Error details with context
- Principal and tenant information
- Performance metrics

## Integration Examples

### Basic Node Search
```python
from src.mcp.tools.graph import search

result = search.invoke({
  "action": "nodes",
  "label": "Person",
  "where": {"status": "active"},
  "page_size": 10
})
```

### Bulk Data Import
```python
from src.mcp.tools.graph import bulk

result = bulk.invoke({
  "action": "ingest_nodes",
  "nodes": [...],
  "batch_size": 100,
  "idempotency_key": "import-2025-01-01"
})
```

### Natural Language Query
```python
from src.mcp.tools.graph import secure_query

result = secure_query.invoke({
  "action": "ask",
  "prompt": "How many users are in each department?",
  "return_format": "markdown"
})
```

### Schema Discovery
```python
from src.mcp.tools.graph import schema

labels = schema.invoke({"action": "labels"})
counts = schema.invoke({"action": "node_counts"})
```

This comprehensive Graph tools framework provides complete coverage of graph database operations while maintaining security, performance, and usability standards.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_graph.md