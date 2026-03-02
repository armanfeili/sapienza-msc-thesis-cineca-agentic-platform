# MCP Tools Reference Documentation

> **Comprehensive documentation for all available MCP (Model Context Protocol) tools in the Cineca Agentic Platform**

**Version:** 0.1.0  
**Last Updated:** October 24, 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Tool Categories](#tool-categories)
4. [Tool Catalog](#tool-catalog)
   - [Agent Tools](#agent-tools)
   - [Cache Tools](#cache-tools)
   - [Catalog Tools](#catalog-tools)
   - [Data Tools](#data-tools)
   - [Database Tools](#database-tools)
   - [Error Tools](#error-tools)
   - [Graph Tools](#graph-tools)
   - [Model Tools](#model-tools)
   - [Output Tools](#output-tools)
   - [Privacy Tools](#privacy-tools)
   - [Rate Limit Tools](#rate-limit-tools)
   - [Security Tools](#security-tools)
   - [Session Tools](#session-tools)
   - [System Tools](#system-tools)
   - [Tenancy Tools](#tenancy-tools)
   - [User Tools](#user-tools)
   - [Visualization Tools](#visualization-tools)

---

## Overview

The MCP Tools package (`src/mcp/tools`) provides a comprehensive collection of **lightweight, composable tools** designed for agent orchestration, graph operations, security, monitoring, and system administration within the Cineca Agentic Platform.

### Key Principles

- **Modularity**: Each tool is self-contained and can be used independently
- **Portability**: Tools use plain Cypher queries where possible (Memgraph/Neo4j compatible)
- **Safety**: Built-in guards, read-only modes, and audit trails
- **Graceful Degradation**: Tools adapt when dependencies are unavailable
- **Consistent Interface**: All tools expose `invoke(payload, **kwargs)` entry point

---

## Architecture

### Directory Structure

```
src/mcp/tools/
├── __init__.py           # Tool discovery and resolution
├── agent/                # Agent context and capabilities
├── cache/                # Redis-backed caching
├── catalog/              # Tool discovery and introspection
├── data/                 # Data archival and quality checks
├── db/                   # Database connection management
├── errors/               # Structured error reporting
├── graph/                # Memgraph operations (CRUD, analytics, search)
├── model/                # LLM adapter management
├── output/               # Formatting and summarization
├── privacy/              # Consent management
├── ratelimit/            # Rate limiter administration
├── security/             # Audit, permissions, security checks
├── session/              # Session management
├── system/               # Health, metrics, backup, status
├── tenancy/              # Multi-tenancy administration
├── user/                 # User profile management
└── viz/                  # Visualization rendering
```

### Tool Resolution

The main `__init__.py` provides utilities for discovering and loading tools:

- **`module_name_for_tool(tool_name)`**: Convert MCP name to Python module path
- **`load(tool_name)`**: Import and return (module, callable)
- **`discover()`**: Return all available tools with metadata
- **`list_tools()`**: List all tool names (e.g., `"graph.query"`)

### Common Conventions

Each tool module typically exposes:
- `invoke(payload: dict, **kwargs) -> dict` (primary entry point)
- Back-compat aliases: `run` and `handle`
- Best-effort imports with graceful fallbacks
- Structured logging via `src.logging_setup.get_logger`
- Audit events via `src.security.audit.audit_access`

---

## Tool Categories

| Category | Tool Count | Purpose |
|----------|------------|---------|
| **Agent** | 1 | Agent execution context and capabilities |
| **Cache** | 1 | Redis/memory caching operations |
| **Catalog** | 1 | Tool discovery and metadata |
| **Data** | 2 | Archival, quality checks |
| **Database** | 1 | Connection switching |
| **Errors** | 1 | Structured error reporting |
| **Graph** | 8 | Memgraph CRUD, analytics, search, schema, secure NL queries |
| **Model** | 2 | LLM adapter management and testing |
| **Output** | 2 | Formatting and summarization |
| **Privacy** | 1 | Consent registry |
| **Rate Limit** | 1 | Rate limiter administration |
| **Security** | 3 | Audit, permissions, security checks |
| **Session** | 1 | Session store |
| **System** | 4 | Health, metrics, backup, status |
| **Tenancy** | 1 | Multi-tenancy management |
| **User** | 1 | User profile store |
| **Visualization** | 1 | Graph and table rendering |

---

## Tool Catalog

---

## Agent Tools

### `agent.context`

**Module:** `src.mcp.tools.agent.context`

**Purpose:** Assemble lightweight execution context for agents, including available tools, models, policies, tenant info, and runtime metadata.

#### Actions

- **Default** (always executes): Returns comprehensive agent context

#### Payload Options

```json
{
  "include_tools": true,        // Include MCP tools manifest
  "include_models": true,       // Include LLM models list
  "include_policies": false,    // Include security policies
  "include_env": true,          // Include runtime environment info
  "include_tenant": true,       // Include current tenant
  "include_user_scopes": true,  // Include user scopes/roles
  "user": { ... }               // Optional user object
}
```

#### Return Shape

```json
{
  "ok": true,
  "time": 1729785600,
  "agent_context": {
    "env": {
      "app_version": "0.1.0",
      "python": "3.11.9",
      "platform": "macOS-14.5-arm64",
      "pid": 12345,
      "time": 1729785600
    },
    "rate_limit_backend": "redis",
    "tools": {
      "count": 45,
      "names": ["graph.query", "..."],
      "categories": ["graph", "security", "..."],
      "manifest": { ... }
    },
    "models": {
      "count": 3,
      "default": "gpt-4",
      "names": ["gpt-4", "gpt-3.5-turbo", "claude-3"]
    },
    "policies": { ... },
    "tenant": "default",
    "user": {
      "username": "alice",
      "role": "analyst",
      "scopes": ["graph:read", "tools:invoke"]
    }
  }
}
```

#### Use Cases

- Agent initialization: gather capabilities before planning
- Debugging: understand current runtime configuration
- Capability discovery: what tools/models are available?

---

## Cache Tools

### `cache.manage`

**Module:** `src.mcp.tools.cache.manage`

**Purpose:** Simple cache operations with Redis backend (when available) and in-memory fallback. All keys are automatically namespaced by tenant.

#### Actions

| Action | Description |
|--------|-------------|
| `get` | Retrieve value by key |
| `set` | Store value with optional TTL |
| `delete` | Remove key |
| `keys` | List keys matching pattern |

#### Payload Examples

```json
// GET
{
  "action": "get",
  "key": "session:abc123",
  "tenant": "acme"  // optional; defaults to current tenant
}

// SET
{
  "action": "set",
  "key": "cache:user:profile",
  "value": "{ ... }",
  "ttl": 3600,  // seconds; optional
  "tenant": "acme"
}

// DELETE
{
  "action": "delete",
  "key": "temp:data"
}

// KEYS (pattern matching)
{
  "action": "keys",
  "key": "session:*"
}
```

#### Return Shape

```json
{
  "ok": true,
  "action": "get",
  "backend": "redis",
  "tenant": "acme",
  "key": "session:abc123",
  "namespaced_key": "t:acme:session:abc123",
  "value": "{ ... }"
}
```

#### Features

- **Automatic tenantization**: Keys are prefixed with `t:{tenant}:`
- **Dual backend**: Redis when available, in-memory fallback
- **TTL support**: Automatic expiration (Redis) or manual cleanup (memory)
- **Pattern matching**: `fnmatch`-style patterns for key listing

---

## Catalog Tools

### `catalog.discover`

**Module:** `src.mcp.tools.catalog.discover`

**Purpose:** Return catalog of available MCP tools as declared in the manifest, with optional filtering and enrichment.

#### Actions

- **Default**: Discover tools with filters

#### Payload Options

```json
{
  "prefix": "graph.",           // Filter by name prefix
  "names_only": false,          // Return just names
  "categories_only": false,     // Return just categories
  "include_schemas": false,     // Include input/output schemas
  "include_scopes": true,       // Include required scopes
  "include_modules": false,     // Include Python module paths
  "sort": "name",               // "name" | "category"
  "limit": 100                  // Max results
}
```

#### Return Shape

```json
{
  "ok": true,
  "count": 7,
  "items": [
    {
      "name": "graph.query",
      "description": "Execute Cypher queries...",
      "category": "graph",
      "scope": "graph:execute",
      "input_schema": { ... },    // if include_schemas=true
      "output_schema": { ... },   // if include_schemas=true
      "module": "src.mcp.tools.graph.query"  // if include_modules=true
    }
  ],
  "categories": ["graph", "security", "system"],
  "manifest": {
    "id": "cineca-agentic-platform",
    "version": "1.0.0",
    "schema_version": "1.0"
  }
}
```

#### Use Cases

- Tool browser UI
- Agent capability discovery
- Documentation generation
- API introspection

---

## Data Tools

### `data.archive`

**Module:** `src.mcp.tools.data.archive`

**Purpose:** Soft-delete (archive), restore, purge, and inspect archived nodes in Memgraph.

#### Actions

| Action | Description |
|--------|-------------|
| `mark` | Set `archived=true` on nodes |
| `restore` | Set `archived=false` on nodes |
| `purge` | Permanently delete nodes |
| `status` | Report archived counts |
| `list` | Sample archived nodes |

#### Payload Examples

```json
// MARK (archive)
{
  "action": "mark",
  "label": "User",
  "where": { "status": "inactive" },
  "orig_ids": ["user-123", "user-456"]
}

// RESTORE
{
  "action": "restore",
  "label": "User",
  "orig_ids": ["user-123"]
}

// PURGE (destructive!)
{
  "action": "purge",
  "label": "User",
  "only_archived": true,
  "older_than_days": 30
}

// STATUS
{
  "action": "status",
  "label": "User"  // optional
}

// LIST
{
  "action": "list",
  "label": "User",
  "limit": 50
}
```

#### Safety Features

- Requires at least one filter (label, where, or orig_ids) for mark/restore
- `only_archived` defaults to `true` for purge
- Timestamps stored as integer epoch seconds

---

### `data.quality`

**Module:** `src.mcp.tools.data.quality`

**Purpose:** Lightweight data quality checks for the Memgraph graph.

#### Actions

| Action | Description |
|--------|-------------|
| `stats` | Global counts by label and relationship |
| `missing_props` | Find nodes missing required properties |
| `degree` | Degree distribution and statistics |
| `dangling` | Nodes with zero degree (isolates) |
| `duplicates` | Duplicate property values |
| `sample` | Random sample of nodes |

#### Payload Examples

```json
// STATS
{
  "action": "stats"
}

// MISSING_PROPS
{
  "action": "missing_props",
  "label": "User",
  "properties": ["user_id", "email"],
  "sample": 5  // optional; return sample orig_ids
}

// DEGREE
{
  "action": "degree",
  "label": "User"  // optional
}

// DANGLING
{
  "action": "dangling",
  "label": "File"  // optional
}

// DUPLICATES
{
  "action": "duplicates",
  "label": "User",
  "property": "email",
  "limit": 100
}

// SAMPLE
{
  "action": "sample",
  "label": "User",
  "limit": 10
}
```

#### Use Cases

- Data validation before production
- Quality monitoring dashboards
- Debugging import issues
- Schema evolution planning

---

## Database Tools

### `db.switch`

**Module:** `src.mcp.tools.db.switch`

**Purpose:** Developer utility to inspect and temporarily switch Memgraph connection profile at runtime.

#### Actions

| Action | Description |
|--------|-------------|
| `get` | Return current connection config |
| `set` | Update connection parameters |
| `switch` | Use preset (local, docker, default) |
| `test` | Test connection |

#### Payload Examples

```json
// GET
{
  "action": "get"
}

// SET
{
  "action": "set",
  "host": "memgraph",
  "port": 7687,
  "user": "admin",
  "password": "secret",
  "test": true  // optional; test after setting
}

// SWITCH (preset)
{
  "action": "switch",
  "target": "local",  // "local" | "docker" | "default"
  "user": "admin",    // optional overrides
  "password": "secret"
}

// TEST
{
  "action": "test",
  "host": "localhost",  // optional; test specific config
  "port": 7687
}
```

#### Presets

- **`local`**: `host=127.0.0.1, port=7687`
- **`docker`**: `host=memgraph, port=7687`
- **`default`**: Read from current settings/env

#### Notes

- Changes persist to process environment (`MG_HOST`, `MG_PORT`, etc.)
- Does not edit files; affects current process only
- Password is masked in responses

---

## Error Tools

### `errors.report`

**Module:** `src.mcp.tools.error.report`

**Purpose:** Accept structured error payloads, sanitize, log, and emit audit events with correlation IDs.

#### Payload Schema

```json
{
  "message": "Human-readable error description",  // required
  "code": "E_GRAPH_TIMEOUT",                      // optional short code
  "severity": "error",                            // info|warning|error|critical
  "category": "graph",                            // application|mcp|graph|security|system|external
  "resource": "graph.query",                      // logical target
  "principal": "alice@example.org",               // user/subject if known
  "trace_id": "req-12345",                        // correlation id
  "context": { "query": "MATCH ..." },            // arbitrary dict; PII-scrubbed
  "exception": {                                  // optional structured exception
    "type": "TimeoutError",
    "message": "Query timed out",
    "stack": "..."
  },
  "capture_stack": false                          // capture current stack
}
```

#### Return Shape

```json
{
  "ok": true,
  "event": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": 1729785600,
    "message": "Human-readable error description",
    "code": "E_GRAPH_TIMEOUT",
    "severity": "error",
    "category": "graph",
    "resource": "graph.query",
    "principal": "alice@example.org",
    "trace_id": "req-12345",
    "context": { ... },  // scrubbed
    "exception": { ... }
  }
}
```

#### Features

- Automatic PII scrubbing via `src.security.pii_scrubber`
- Structured logging with severity mapping
- Audit event emission (best-effort)
- UUID correlation for log aggregation

---

## Graph Tools

The **Graph** category provides comprehensive tools for interacting with Memgraph using portable Cypher queries.

### `graph.analytics`

**Module:** `src.mcp.tools.graph.analytics`

**Purpose:** Pragmatic graph analytics using portable Cypher (no vendor-specific procedures).

#### Actions

| Action | Description |
|--------|-------------|
| `degree_distribution` | Degree summary and histogram |
| `top_hubs` | Highest-degree nodes |
| `rel_triplets` | Relationship pattern frequencies |
| `shortest_path` | Shortest path between two nodes |
| `k_hop` | K-hop neighborhood expansion |
| `neighbors` | Direct neighbors of a node |

#### Payload Examples

```json
// DEGREE_DISTRIBUTION
{
  "action": "degree_distribution",
  "label": "User"  // optional
}

// TOP_HUBS
{
  "action": "top_hubs",
  "label": "User",
  "limit": 25,
  "include_props": ["user_name", "email"]
}

// SHORTEST_PATH
{
  "action": "shortest_path",
  "src": "user-123",
  "dst": "inst-456",
  "max_hops": 6
}

// K_HOP
{
  "action": "k_hop",
  "src": "user-123",
  "k": 3
}

// NEIGHBORS
{
  "action": "neighbors",
  "src": "user-123",
  "limit": 50,
  "rel_types": ["RUNS", "WORKS_AT"]  // optional filter
}
```

---

### `graph.bulk`

**Module:** `src.mcp.tools.graph.bulk`

**Purpose:** Bulk upsert operations for nodes and relationships, index management, and graph wipe.

#### Actions

| Action | Description |
|--------|-------------|
| `nodes` | Upsert list of nodes |
| `relationships` | Upsert list of relationships |
| `ensure_index` | Create index if not exists |
| `ensure_indexes_for_labels` | Create indexes for multiple labels |
| `wipe` | Delete all nodes and relationships |

#### Payload Examples

```json
// NODES
{
  "action": "nodes",
  "nodes": [
    {
      "labels": ["User"],
      "orig_id": "user-123",
      "props": { "firstName": "Alice", "email": "alice@example.org" }
    },
    {
      "labels": ["User"],
      "orig_id": "user-456",
      "props": { "firstName": "Bob" }
    }
  ],
  "batch_size": 500
}

// RELATIONSHIPS
{
  "action": "relationships",
  "relationships": [
    {
      "start_orig_id": "user-123",
      "end_orig_id": "inst-789",
      "type": "WORKS_AT",
      "props": { "since": "2024-01-01" }
    }
  ],
  "batch_size": 500
}

// ENSURE_INDEX
{
  "action": "ensure_index",
  "label": "User",
  "property": "orig_id"  // defaults to "orig_id"
}

// WIPE (destructive!)
{
  "action": "wipe",
  "confirm": true
}
```

#### Features

- MERGE semantics (upsert by `orig_id`)
- Batch processing for performance
- Portable Cypher (no vendor procedures)
- Fail-fast with detailed error counts

---

### `graph.crud`

**Module:** `src.mcp.tools.graph.crud`

**Purpose:** Focused, portable CRUD helpers for individual nodes and relationships.

#### Actions

| Action | Description |
|--------|-------------|
| `upsert_node` | Create or update single node |
| `get_node` | Retrieve node(s) by orig_id or filters |
| `delete_node` | Delete node by orig_id |
| `list_nodes` | List nodes with filters |
| `upsert_rel` | Create or update relationship |
| `delete_rel` | Delete relationship |
| `list_node_rels` | List relationships for a node |

#### Payload Examples

```json
// UPSERT_NODE
{
  "action": "upsert_node",
  "labels": ["User"],
  "orig_id": "user-123",
  "props": { "firstName": "Alice" }
}

// GET_NODE (by orig_id)
{
  "action": "get_node",
  "orig_id": "user-123"
}

// GET_NODE (by label + where)
{
  "action": "get_node",
  "label": "User",
  "where": { "email": "alice@example.org" },
  "limit": 1
}

// DELETE_NODE
{
  "action": "delete_node",
  "orig_id": "user-123"
}

// LIST_NODES
{
  "action": "list_nodes",
  "label": "User",
  "where": { "status": "active" },
  "limit": 25
}

// UPSERT_REL
{
  "action": "upsert_rel",
  "start_orig_id": "user-123",
  "end_orig_id": "task-456",
  "type": "RUNS",
  "props": { "since": "2024-01-01" }
}

// LIST_NODE_RELS
{
  "action": "list_node_rels",
  "orig_id": "user-123",
  "direction": "both",  // "in" | "out" | "both"
  "types": ["RUNS", "WORKS_AT"],
  "limit": 100
}
```

---

### `graph.generate_cypher`

**Module:** `src.mcp.tools.graph.generate_cypher`

**Purpose:** Generate safe, parameterized Cypher snippets **without executing them**.

#### Actions

| Action | Description |
|--------|-------------|
| `select` | Generate SELECT-like query |
| `insert_node` | Generate node creation query |
| `update_node` | Generate node update query |
| `delete_node` | Generate node deletion query |
| `upsert_rel` | Generate relationship upsert query |
| `match_rel` | Generate relationship matching query |
| `count_by_label` | Generate label count query |
| `schema_inventory` | Generate multi-query schema report |

#### Payload Examples

```json
// SELECT
{
  "action": "select",
  "label": "User",
  "where": { "status": "active" },
  "return": ["orig_id", "email"],
  "limit": 25
}

// INSERT_NODE
{
  "action": "insert_node",
  "labels": ["User"],
  "orig_id": "user-123",
  "props": { "firstName": "Alice" },
  "mode": "merge"  // "merge" | "create"
}

// UPDATE_NODE
{
  "action": "update_node",
  "orig_id": "user-123",
  "props": { "email": "new@example.org" }
}

// DELETE_NODE
{
  "action": "delete_node",
  "orig_id": "user-123",
  "detach": true
}
```

#### Return Shape

```json
{
  "ok": true,
  "action": "select",
  "read_only": true,
  "cypher": "MATCH (n:`User`) WHERE n.`status` = $w_0 RETURN n.`orig_id`, n.`email` LIMIT $limit",
  "params": { "w_0": "active", "limit": 25 }
}
```

---

### `graph.query`

**Module:** `src.mcp.tools.graph.query`

**Purpose:** Thin execution surface for ad-hoc Cypher queries with safety knobs.

#### Actions

| Action | Description |
|--------|-------------|
| `run` | Execute Cypher query |
| `explain` | EXPLAIN query plan |
| `profile` | PROFILE query execution |

#### Payload Examples

```json
// RUN
{
  "action": "run",
  "cypher": "MATCH (n:User) WHERE n.status = $status RETURN n LIMIT 10",
  "params": { "status": "active" },
  "read_only": false,
  "timeout_ms": 5000,
  "limit": 1000  // client-side row cap
}

// EXPLAIN
{
  "action": "explain",
  "cypher": "MATCH (n:User) RETURN n"
}

// PROFILE
{
  "action": "profile",
  "cypher": "MATCH (n:User) RETURN count(n)"
}
```

#### Safety Features

- `read_only` mode blocks obvious write operations (heuristic)
- Client-side row limit (slices results without modifying query)
- Per-query timeout support
- Execution audit trails

---

### `graph.schema`

**Module:** `src.mcp.tools.graph.schema`

**Purpose:** Schema discovery utilities using portable Cypher.

#### Actions

| Action | Description |
|--------|-------------|
| `labels` | List all node labels |
| `relationship_types` | List all relationship types |
| `node_properties` | List properties for a label |
| `relationship_properties` | List properties for a rel type |
| `node_counts` | Count nodes by label |
| `relationship_counts` | Count relationships by type |
| `indexes` | List indexes (uses SHOW INDEX INFO) |
| `constraints` | List constraints (enterprise-only) |
| `inventory` | Comprehensive schema report |

#### Payload Examples

```json
// LABELS
{
  "action": "labels"
}

// NODE_PROPERTIES
{
  "action": "node_properties",
  "label": "User"  // optional
}

// NODE_COUNTS
{
  "action": "node_counts"
}

// INDEXES
{
  "action": "indexes"
}

// INVENTORY (comprehensive)
{
  "action": "inventory"
}
```

---

### `graph.search`

**Module:** `src.mcp.tools.graph.search`

**Purpose:** Portable text/property search helpers using plain Cypher (no full-text engine required).

#### Actions

| Action | Description |
|--------|-------------|
| `node_text` | Full-text-ish search across node properties |
| `rel_text` | Search relationship properties |
| `by_property` | Exact/substring/regex match on property |
| `autocomplete_property_values` | Autocomplete values by prefix |
| `ids` | Lookup by partial orig_id |

#### Payload Examples

```json
// NODE_TEXT
{
  "action": "node_text",
  "q": "alice",
  "labels": ["User", "Institution"],
  "properties": ["name", "email"],
  "limit": 50
}

// BY_PROPERTY
{
  "action": "by_property",
  "label": "User",
  "property": "email",
  "op": "contains",  // "eq" | "contains" | "prefix" | "suffix" | "regex"
  "value": "example.org",
  "case_sensitive": false,
  "limit": 50
}

// AUTOCOMPLETE_PROPERTY_VALUES
{
  "action": "autocomplete_property_values",
  "label": "User",
  "property": "user_name",
  "prefix": "al",
  "limit": 25
}

// IDS (partial orig_id lookup)
{
  "action": "ids",
  "q": "user-123",
  "labels": ["User"],
  "limit": 25
}
```

#### Features

- Case-insensitive matching by default
- Scoring for relevance (simple tf-like)
- No external full-text engine required
- Regex support for advanced patterns

---

### `graph.secure_query`

**Module:** `src.mcp.tools.graph.secure_query`

**Purpose:** Safely answer user prompts over Memgraph: NL→Cypher, validate (read-only + safety + permissions), execute if allowed, return results.

**Scope:** `tools:basic` (read-only access)

**Rate Limit:** Recommended 10/min per principal

#### Actions

| Action | Description |
|--------|-------------|
| `ask` | End-to-end: Generate Cypher from NL, validate, execute, return formatted results |
| `generate` | Generate Cypher from NL prompt (no execution) |
| `validate` | Validate Cypher for safety and permissions (no execution) |
| `execute` | Execute pre-validated Cypher query |

#### Security Features

- **Read-only enforcement**: All queries validated to be read-only; write operations blocked
- **Forbidden clause detection**: Blocks dangerous operations (DROP, DELETE, CREATE INDEX, etc.)
- **Tenant scoping**: Ensures queries are properly scoped to user's tenant
- **Permission checks**: Verifies principal has necessary permissions
- **Timeout protection**: Default 5s timeout on all queries
- **Row limits**: Results capped at max_rows (default 1000)
- **Audit trail**: All invocations logged and audited

#### Payload Examples

```json
// ASK (end-to-end)
{
  "action": "ask",
  "prompt": "Show me all active users",
  "principal": "alice@example.org",
  "tenant": "default",
  "max_rows": 1000,
  "timeout_ms": 5000,
  "return_format": "rows"  // "rows" | "markdown" | "csv" | "json"
}

// GENERATE (NL→Cypher)
{
  "action": "generate",
  "prompt": "Find users who work at institutions in Boston",
  "principal": "alice@example.org",
  "tenant": "default"
}

// VALIDATE
{
  "action": "validate",
  "cypher": "MATCH (n:User) WHERE n.status = 'active' RETURN n LIMIT 10",
  "principal": "alice@example.org",
  "tenant": "default",
  "params": {}
}

// EXECUTE
{
  "action": "execute",
  "cypher": "MATCH (n:User) RETURN n.orig_id, n.email LIMIT 10",
  "params": {},
  "principal": "alice@example.org",
  "tenant": "default",
  "max_rows": 1000,
  "timeout_ms": 5000,
  "return_format": "markdown"
}
```

#### Return Shapes

**ASK:**
```json
{
  "ok": true,
  "action": "ask",
  "prompt": "Show me all active users",
  "cypher": "MATCH (n:User) WHERE n.status = 'active' RETURN n LIMIT 100",
  "params": {},
  "columns": ["orig_id", "email", "status"],
  "rows": [...],
  "rowcount": 15,
  "truncated": false,
  "format": "rows",
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

**GENERATE:**
```json
{
  "ok": true,
  "action": "generate",
  "prompt": "Find users...",
  "cypher": "MATCH (u:User)-[:WORKS_AT]->(i:Institution) WHERE i.city = 'Boston' RETURN u",
  "params": {}
}
```

**VALIDATE:**
```json
{
  "ok": true,
  "action": "validate",
  "cypher": "...",
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

#### Use Cases

- **Natural language querying**: Enable non-technical users to query the graph using plain English
- **Safe exploration**: Provide sandboxed read-only access to the knowledge graph
- **Agent integration**: Allow AI agents to safely query graph data with automatic validation
- **Audit compliance**: Track all queries with full audit trail

#### Notes

- Requires LLM adapter for NL→Cypher generation
- For write operations, use `graph.crud` or `graph.bulk` with `tools:all` scope
- Validation is heuristic-based; not a formal Cypher parser
- Production deployments should enforce rate limiting at router level

---

## Model Tools

### `model.manage`

**Module:** `src.mcp.tools.model.manage`

**Purpose:** Runtime management surface for the LLM adapter (config, models, capabilities).

#### Actions

| Action | Description |
|--------|-------------|
| `info` | Current LLM config |
| `get_config` | Alias for info |
| `set_config` | Update config (model, temperature, max_tokens) |
| `reset_config` | Clear overrides, re-read from env |
| `list_models` | List available models |
| `capabilities` | List adapter features |
| `health` | Adapter health probe |

#### Payload Examples

```json
// INFO
{
  "action": "info"
}

// SET_CONFIG
{
  "action": "set_config",
  "model": "gpt-4",
  "temperature": 0.7,
  "max_tokens": 2048
}

// LIST_MODELS
{
  "action": "list_models"
}

// CAPABILITIES
{
  "action": "capabilities"
}
```

#### Notes

- Changes are in-memory only (not persisted to disk)
- Adapter-agnostic (works with any `src.adapters.llm.LLMAdapter`)

---

### `model.test`

**Module:** `src.mcp.tools.model.test`

**Purpose:** Lightweight checks against configured LLM adapter. Safe by default (`simulate=true`).

#### Actions

| Action | Description |
|--------|-------------|
| `ping` | Quick health check |
| `canary` | Simple prompt test |
| `tokens` | Token counting |
| `embeddings` | Embedding generation test |
| `latency` | Measure round-trip latency |

#### Payload Examples

```json
// PING
{
  "action": "ping"
}

// CANARY
{
  "action": "canary",
  "prompt": "Say OK",
  "simulate": true,  // default: true (no live API call)
  "temperature": 0.0,
  "max_tokens": 16
}

// TOKENS
{
  "action": "tokens",
  "text": "Hello, world!",
  "approx": true  // use heuristic vs. actual tokenizer
}

// LATENCY
{
  "action": "latency",
  "iterations": 3,
  "simulate": true
}
```

#### Features

- **Simulation mode**: Avoid live API calls during testing
- **Latency stats**: p50, p90, p99, avg, min, max
- **Token estimation**: Quick heuristic or accurate count

---

## Output Tools

### `output.format`

**Module:** `src.mcp.tools.output.format`

**Purpose:** Portable formatters for common result shapes (JSON, CSV, Markdown, Text).

#### Actions

| Action | Description |
|--------|-------------|
| `json` | JSON / NDJSON output |
| `csv` | RFC4180-ish CSV |
| `markdown` | GitHub-style table |
| `text` | Plain text rows |
| `normalize` | Return {columns, rows} from arbitrary input |

#### Payload Examples

```json
// JSON
{
  "action": "json",
  "data": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
  "ndjson": false,
  "indent": 2,
  "sort_keys": false
}

// CSV
{
  "action": "csv",
  "data": [{"id": 1, "name": "Alice"}],
  "delimiter": ",",
  "header": true,
  "include_bom": false
}

// MARKDOWN
{
  "action": "markdown",
  "data": [{"id": 1, "name": "Alice"}],
  "max_col_width": 40,
  "code_fence": true
}

// TEXT
{
  "action": "text",
  "data": [{"id": 1, "name": "Alice"}],
  "separator": "\n",
  "key_value_sep": ": "
}
```

#### Features

- **Flatten nested objects**: Dot notation (e.g., `user.email`)
- **Column ordering**: Explicit or auto-inferred
- **Row limiting**: Cap output size
- **orjson support**: Fast JSON serialization when available

---

### `output.summarize`

**Module:** `src.mcp.tools.output.summarize`

**Purpose:** Portable summarization helpers (extractive and abstractive).

#### Actions

| Action | Description |
|--------|-------------|
| `extract` | Extractive summary (no model) |
| `abstractive` | Abstractive summary (LLM-based) |
| `map_reduce` | Chunk → summarize → combine |
| `keywords` | Extract top keywords |
| `tl_dr` | Ultra-compact 1-2 sentence summary |

#### Payload Examples

```json
// EXTRACT
{
  "action": "extract",
  "text": "Long document...",
  "sentences": 5,  // or "ratio": 0.2
  "lower": true
}

// ABSTRACTIVE
{
  "action": "abstractive",
  "text": "Long document...",
  "simulate": true,  // default: true
  "sentences": 5,
  "style": "plain",  // "plain" | "bullets" | "keypoints" | "academic"
  "temperature": 0.2,
  "max_tokens": 256
}

// MAP_REDUCE (long documents)
{
  "action": "map_reduce",
  "text": "Very long document...",
  "simulate": true,
  "chunk_chars": 3200,
  "overlap": 200,
  "sentences": 5
}

// KEYWORDS
{
  "action": "keywords",
  "text": "Document...",
  "top_k": 15,
  "lower": true
}

// TL_DR
{
  "action": "tl_dr",
  "text": "Document...",
  "simulate": true
}
```

#### Features

- **Simulation mode**: Local processing without API calls
- **Multiple styles**: Plain, bullets, key points, academic
- **Chunking**: Handle documents larger than context window
- **Keyword extraction**: Simple tf-idf-like scoring

---

## Privacy Tools

### `privacy.consent`

**Module:** `src.mcp.tools.privacy.consent`

**Purpose:** Lightweight consent registry backed by Redis (with in-process fallback).

#### Actions

| Action | Description |
|--------|-------------|
| `status` | Get consent status |
| `set` | Set consent flags |
| `grant` | Grant specific consents |
| `revoke` | Revoke specific consents |
| `history` | Audit trail of changes |
| `erase` | RTBF (right to be forgotten) |
| `prompt` | Generate consent prompt text |

#### Payload Examples

```json
// STATUS
{
  "action": "status",
  "subject_id": "user-123",
  "tenant": "default"
}

// SET
{
  "action": "set",
  "subject_id": "user-123",
  "tenant": "default",
  "flags": { "analytics": true, "research": false },
  "actor": "admin@example.org",
  "note": "bulk update"
}

// GRANT
{
  "action": "grant",
  "subject_id": "user-123",
  "flags": ["analytics", "research"],
  "tenant": "default"
}

// REVOKE
{
  "action": "revoke",
  "subject_id": "user-123",
  "flags": ["analytics"],
  "tenant": "default"
}

// HISTORY
{
  "action": "history",
  "subject_id": "user-123",
  "tenant": "default",
  "limit": 50
}

// ERASE (RTBF)
{
  "action": "erase",
  "subject_id": "user-123",
  "tenant": "default",
  "actor": "admin@example.org",
  "note": "GDPR request"
}

// PROMPT
{
  "action": "prompt",
  "purpose": "analytics",  // "improve_models" | "analytics" | "research" | "custom"
  "style": "markdown",
  "lang": "en",
  "app_name": "Cineca Agentic Platform"
}
```

#### Redis Keys

- `consent:{tenant}:{subject_id}` → JSON document
- `consent:{tenant}:{subject_id}:history` → List of events

---

## Rate Limit Tools

### `ratelimit.manage`

**Module:** `src.mcp.tools.ratelimit.manage`

**Purpose:** Administrative surface to inspect and tune the global rate limiter at runtime.

#### Actions

| Action | Description |
|--------|-------------|
| `status` | Current limiter config and counters |
| `enable` | Enable enforcement |
| `disable` | Disable enforcement |
| `set` | Update limits (rate, burst, window) |
| `reset` | Clear all counters |
| `check` | Probe limiter for a key |

#### Payload Examples

```json
// STATUS
{
  "action": "status",
  "verbose": true
}

// ENABLE/DISABLE
{
  "action": "enable"
}

// SET
{
  "action": "set",
  "rate": 5.0,    // requests per second
  "burst": 20,    // max burst tokens
  "window": 60,   // sliding window (seconds)
  "dry_run": false
}

// RESET
{
  "action": "reset"
}

// CHECK
{
  "action": "check",
  "key": "user:alice",
  "cost": 1
}
```

---

## Security Tools

### `security.audit`

**Module:** `src.mcp.tools.security.audit`

**Purpose:** Record and retrieve security audit events.

#### Actions

| Action | Description |
|--------|-------------|
| `access` | Record access/control decision |
| `custom` | Record free-form event |
| `list` | List recent events with filters |
| `stats` | Aggregate statistics |
| `clear` | Remove events (admin-only, requires confirm) |

#### Payload Examples

```json
// ACCESS
{
  "action": "access",
  "principal": "alice@example.org",
  "resource": "mcp.tools.graph.query",
  "action": "invoke",
  "allowed": true,
  "reason": "policy:allow",
  "attributes": { "route": "/mcp/graph/query" },
  "tenant": "default",
  "ip": "203.0.113.5",
  "user_agent": "curl/8.6.0"
}

// CUSTOM
{
  "action": "custom",
  "name": "model.updated",
  "data": { "old": "gpt-3.5", "new": "gpt-4" },
  "tenant": "default",
  "principal": "admin"
}

// LIST
{
  "action": "list",
  "limit": 100,
  "offset": 0,
  "tenant": "default",
  "principal": "alice@example.org",
  "action": "invoke",
  "resource_substr": "graph",
  "allowed": true,
  "since": "2025-08-02T00:00:00Z",
  "until": "2025-08-09T23:59:59Z"
}

// STATS
{
  "action": "stats",
  "tenant": "default"
}

// CLEAR (destructive!)
{
  "action": "clear",
  "confirm": true,
  "tenant": "default"
}
```

---

### `security.check`

**Module:** `src.mcp.tools.security.check`

**Purpose:** Lightweight, offline security checks for requests and runtime config.

#### Actions

| Action | Description |
|--------|-------------|
| `headers` | Validate HTTP security headers |
| `tls` | TLS/transport checks |
| `config` | Platform config security review |
| `rate_limit` | Rate limiter config review |
| `all` | Run all checks and aggregate |

#### Payload Examples

```json
// HEADERS
{
  "action": "headers",
  "headers": {
    "Content-Security-Policy": "default-src 'self'",
    "X-Frame-Options": "DENY"
  },
  "url": "https://example.org/api"
}

// TLS
{
  "action": "tls",
  "url": "https://example.org",
  "headers": { "X-Forwarded-Proto": "https" }
}

// CONFIG
{
  "action": "config"
}

// ALL (comprehensive)
{
  "action": "all"
}
```

#### Return Shape

```json
{
  "ok": true,
  "action": "all",
  "score": 85,  // 0-100
  "findings": [
    {
      "severity": "warning",
      "category": "headers",
      "message": "Missing X-Content-Type-Options header",
      "recommendation": "Add X-Content-Type-Options: nosniff"
    }
  ]
}
```

---

### `security.permissions`

**Module:** `src.mcp.tools.security.permissions`

**Purpose:** Policy-aware permission helper using loaded policy sets.

#### Actions

| Action | Description |
|--------|-------------|
| `check` | Evaluate permission |
| `resolve` | Compute effective permissions |
| `list_roles` | List defined roles |
| `reload` | Reload policies from disk |

#### Payload Examples

```json
// CHECK
{
  "action": "check",
  "principal": "alice@example.org",
  "roles": ["analyst"],
  "action": "invoke",
  "resource": "mcp.tools.graph.query",
  "context": { "tenant": "default" }
}

// RESOLVE
{
  "action": "resolve",
  "roles": ["viewer", "analyst"],
  "resources": ["mcp.tools.*", "/api/*"],
  "actions": ["invoke", "read"]
}

// LIST_ROLES
{
  "action": "list_roles"
}

// RELOAD
{
  "action": "reload"
}
```

#### Pattern Matching

Supports fnmatch-style patterns:
- `mcp.tools.graph.query` (exact)
- `mcp.tools.*` (glob)
- `action:invoke resource:mcp.*` (field-aware)
- Deny rules override allow rules

---

## Session Tools

### `session.manage`

**Module:** `src.mcp.tools.session.manage`

**Purpose:** Lightweight session store with optional Redis backend.

#### Actions

| Action | Description |
|--------|-------------|
| `create` | Create new session |
| `read` / `get` | Retrieve session |
| `update` | Update session |
| `delete` | Remove session |
| `set_pref` | Set preference key |
| `get_pref` | Get preference value |
| `set_context` | Update context dict |
| `clear_context` | Clear context |
| `touch` | Update last_accessed timestamp |
| `exists` | Check if session exists |
| `list` | List sessions for tenant |

#### Payload Examples

```json
// CREATE
{
  "action": "create",
  "session_id": "sess-abc123",  // optional; auto-generated if omitted
  "principal": "alice@example.org",
  "roles": ["analyst"],
  "tenant": "default",
  "context": { "lang": "en" },
  "prefs": { "theme": "dark" }
}

// READ
{
  "action": "read",
  "session_id": "sess-abc123",
  "tenant": "default"
}

// UPDATE
{
  "action": "update",
  "session_id": "sess-abc123",
  "context": { "last_query": "MATCH (n) RETURN n" },
  "replace": false  // merge vs. replace
}

// SET_PREF
{
  "action": "set_pref",
  "session_id": "sess-abc123",
  "key": "theme",
  "value": "light"
}

// TOUCH
{
  "action": "touch",
  "session_id": "sess-abc123"
}

// LIST
{
  "action": "list",
  "tenant": "default",
  "limit": 100
}
```

#### Redis Keys

- `session:{tenant}:{session_id}` → JSON document
- Optional TTL via `settings.SESSION_TTL_SECONDS`

---

## System Tools

### `system.backup`

**Module:** `src.mcp.tools.system.backup`

**Purpose:** Create, list, and purge application/database backups.

#### Actions

| Action | Description |
|--------|-------------|
| `create` | Create new backup |
| `list` | List backups |
| `purge` | Remove old backups |
| `restore` | (placeholder/no-op) |

#### Payload Examples

```json
// CREATE
{
  "action": "create",
  "label": "pre-migration",  // optional
  "method": "auto"  // "auto" | "script" | "export"
}

// LIST
{
  "action": "list",
  "limit": 50
}

// PURGE
{
  "action": "purge",
  "older_than_days": 30  // defaults to settings.BACKUP_RETENTION_DAYS
}
```

#### Backup Methods

- **`script`**: Execute `settings.BACKUP_SCRIPT` or `src/scripts/backup_db.sh`
- **`export`**: Online Memgraph export (JSONL format)
- **`auto`**: Prefer script, fallback to export

#### Storage

- Backups stored in `settings.BACKUP_DIR` (default: `./backups`)
- Each backup has timestamped subdirectory

---

### `system.health`

**Module:** `src.mcp.tools.system.health`

**Purpose:** Liveness/readiness checks for the platform and dependencies.

#### Actions

| Action | Description |
|--------|-------------|
| `liveness` | Quick self-check (default) |
| `readiness` | Deep dependency checks |
| `details` | Readiness + version/env info |

#### Payload Examples

```json
// LIVENESS
{
  "action": "liveness"
}

// READINESS
{
  "action": "readiness"
}

// DETAILS
{
  "action": "details"
}
```

#### Return Shape

```json
{
  "ok": true,
  "action": "readiness",
  "checked_at": "2025-08-09T10:42:00Z",
  "summary": { "passed": 3, "failed": 0, "skipped": 0 },
  "components": {
    "app": { "status": "up", "latency_ms": 0.1 },
    "db": { "status": "up", "latency_ms": 12.3 },
    "redis": { "status": "up", "latency_ms": 2.1 }
  },
  "info": {  // only for action=details
    "version": "0.1.0",
    "python": "3.11.9",
    "env": "dev"
  }
}
```

---

### `system.metrics`

**Module:** `src.mcp.tools.system.metrics`

**Purpose:** Scrape Prometheus metrics from default registry.

#### Actions

| Action | Description |
|--------|-------------|
| `scrape` | Return metrics snapshot (default) |
| `info` | Lightweight registry info |

#### Payload Examples

```json
// SCRAPE (text format)
{
  "action": "scrape",
  "format": "text",  // "text" | "json"
  "names": ["http_requests_total", "process_cpu_seconds_total"]  // optional filter
}

// SCRAPE (json format)
{
  "action": "scrape",
  "format": "json"
}

// INFO
{
  "action": "info"
}
```

#### Return Shape (JSON)

```json
{
  "ok": true,
  "action": "scrape",
  "format": "json",
  "checked_at": "2025-08-09T10:42:00Z",
  "metrics": [
    {
      "name": "http_requests_total",
      "type": "counter",
      "documentation": "Total HTTP requests",
      "samples": [
        {
          "name": "http_requests_total",
          "labels": { "method": "GET", "status": "200" },
          "value": 12345
        }
      ]
    }
  ]
}
```

---

### `system.status`

**Module:** `src.mcp.tools.system.status`

**Purpose:** Comprehensive service status snapshot.

#### Payload

```json
{
  "detail": "full"  // "basic" | "full" (default: "full")
}
```

#### Return Shape

```json
{
  "ok": true,
  "checked_at": "2025-08-09T10:42:00Z",
  "service": {
    "name": "Cineca Agentic Platform",
    "version": "0.1.0",
    "env": "dev",
    "debug": false,
    "log_level": "INFO",
    "uptime_sec": 3600.5,
    "process": {
      "pid": 12345,
      "threads": 8,
      "memory_mb": 256
    },
    "build": {
      "git_commit": "abc123",
      "git_branch": "main",
      "build_date": "2025-08-09"
    }
  },
  "endpoints": {
    "http": {
      "health": "/health",
      "ready": "/ready",
      "metrics": "/metrics",
      "docs": "/docs"
    }
  },
  "components": {
    "memgraph": { "enabled": true, "ok": true, "host": "memgraph", "port": 7687 },
    "redis": { "enabled": true, "ok": true, "host": "redis", "port": 6379, "db": 0 },
    "otel": { "enabled": false, "endpoint": null }
  },
  "warnings": []
}
```

---

## Tenancy Tools

### `tenancy.manage`

**Module:** `src.mcp.tools.tenancy.manage`

**Purpose:** Lightweight tenancy administration for multi-tenant deployments.

#### Actions

| Action | Description |
|--------|-------------|
| `list` | List all tenants |
| `current` | Get current tenant |
| `switch` | Switch tenant context |
| `create` | Create new tenant |
| `delete` | Remove tenant |
| `set-default` | Set default tenant |

#### Payload Examples

```json
// LIST
{
  "action": "list"
}

// CURRENT
{
  "action": "current"
}

// SWITCH
{
  "action": "switch",
  "tenant_id": "acme"
}

// CREATE
{
  "action": "create",
  "tenant_id": "acme",
  "name": "Acme Corporation",
  "metadata": { "plan": "enterprise" }
}

// DELETE
{
  "action": "delete",
  "tenant_id": "acme"
}

// SET-DEFAULT
{
  "action": "set-default",
  "tenant_id": "public"
}
```

---

## User Tools

### `user.profile`

**Module:** `src.mcp.tools.user.profile`

**Purpose:** Lightweight profile/preferences store backed by Redis (with in-process fallback).

#### Actions

| Action | Description |
|--------|-------------|
| `get` | Fetch profile |
| `set` | Replace profile |
| `update` | Merge patch into profile |
| `delete` | Remove profile |

#### Payload Examples

```json
// GET
{
  "action": "get",
  "user_id": "alice"
}

// SET
{
  "action": "set",
  "user_id": "alice",
  "profile": {
    "display_name": "Alice Smith",
    "email": "alice@example.org",
    "theme": "dark",
    "lang": "en"
  }
}

// UPDATE (merge)
{
  "action": "update",
  "user_id": "alice",
  "profile": { "theme": "light" }
}

// DELETE
{
  "action": "delete",
  "user_id": "alice"
}
```

#### Redis Keys

- `profile:{user_id}` → JSON document

---

## Visualization Tools

### `viz.render`

**Module:** `src.mcp.tools.viz.render`

**Purpose:** Render helpers for graphs, tables, and sparklines (Mermaid, Graphviz DOT, Markdown).

#### Functions (Not MCP Actions)

This module provides **utility functions**, not MCP tool actions:

- `render_graph_mermaid(nodes, edges, direction="LR")` → Mermaid flowchart
- `render_graph_dot(nodes, edges)` → Graphviz DOT
- `render_table_markdown(rows, columns=None)` → Markdown table
- `sparkline(values)` → Unicode sparkline

#### Example Usage

```python
from src.mcp.tools.viz.render import render_graph_mermaid, sparkline

mermaid = render_graph_mermaid(
    nodes=[{"id": "User"}, {"id": "Institution"}],
    edges=[{"from": "User", "to": "Institution", "label": "WORKS_AT"}],
    direction="LR"
)

spark = sparkline([1, 3, 2, 5, 4])  # → "▁▅▃█▇"
```

#### Output Formats

- **Mermaid**: `flowchart LR\n  User --> Institution`
- **DOT**: `digraph { ... }`
- **Markdown**: GitHub-style tables
- **Sparkline**: Unicode block characters

---

## Usage Examples

### Agent Initialization

```python
from src.mcp.tools import load

# Load agent.context tool
module, fn = load("agent.context")

# Get full agent context
result = fn({
    "include_tools": True,
    "include_models": True,
    "include_policies": True
}, user={"username": "alice", "role": "analyst"})

print(result["agent_context"]["tools"]["count"])  # 45
print(result["agent_context"]["models"]["names"])  # ["gpt-4", ...]
```

### Graph Operations

```python
# Query graph
module, fn = load("graph.query")
result = fn({
    "action": "run",
    "cypher": "MATCH (n:User) WHERE n.status = $status RETURN n LIMIT 10",
    "params": {"status": "active"}
})

# Bulk upsert nodes
module, fn = load("graph.bulk")
result = fn({
    "action": "nodes",
    "nodes": [
        {"labels": ["User"], "orig_id": "u1", "props": {"name": "Alice"}},
        {"labels": ["User"], "orig_id": "u2", "props": {"name": "Bob"}}
    ]
})
```

### Security & Audit

```python
# Check permissions
module, fn = load("security.permissions")
result = fn({
    "action": "check",
    "principal": "alice@example.org",
    "roles": ["analyst"],
    "action": "invoke",
    "resource": "mcp.tools.graph.query"
})

# Record audit event
module, fn = load("security.audit")
result = fn({
    "action": "access",
    "principal": "alice",
    "resource": "graph.query",
    "action": "invoke",
    "allowed": True
})
```

---

## Best Practices

### Tool Development

1. **Graceful Imports**: Use `contextlib.suppress` for optional dependencies
2. **Consistent Interface**: Always expose `invoke(payload, **kwargs)`
3. **Validation**: Validate payload early, fail fast with clear errors
4. **Audit Trails**: Call `audit_access` for sensitive operations
5. **PII Scrubbing**: Use `scrub_dict` for user data in logs/errors

### Error Handling

```python
try:
    result = tool_fn(payload)
except ValueError as e:
    # Report structured error
    _, error_fn = load("errors.report")
    error_fn({
        "message": str(e),
        "code": "E_INVALID_PAYLOAD",
        "severity": "error",
        "category": "application"
    })
```

### Performance

- Use batch operations (`graph.bulk`) for large datasets
- Set client-side limits (`limit` parameter) to avoid huge responses
- Enable caching (`cache.manage`) for frequently accessed data
- Use `simulate=true` in model tools during development

### Security

- Always validate user input before passing to Cypher
- Use parameterized queries (never string concatenation)
- Enable `read_only` mode for query tools when appropriate
- Check permissions before invoking privileged tools
- Review security checks via `security.check` tool

---

## Appendix

### Tool Naming Convention

Tools follow a hierarchical naming scheme:

```
{category}.{operation}
```

Examples:
- `graph.query` → Graph category, query operation
- `security.audit` → Security category, audit operation
- `system.health` → System category, health operation

### Discovery API

```python
from src.mcp.tools import discover, list_tools

# Get all tool names
names = list_tools()
# ["agent.context", "cache.manage", ...]

# Get full tool specs
specs = discover()
for spec in specs:
    print(f"{spec.name}: {spec.callable_name}")
# graph.query: invoke
# cache.manage: invoke
```

### Module Structure

Each tool package follows this structure:

```
{category}/
├── __init__.py       # Discovery helpers
├── {tool1}.py        # Tool implementation
└── {tool2}.py        # Another tool
```

The `__init__.py` provides:
- `iter_modules()` → Generator of module names
- `list_modules()` → List of module names
- `PACKAGE` → Package name constant

---

## Contributing

When adding a new tool:

1. Create module in appropriate category directory
2. Implement `invoke(payload, **kwargs) -> dict`
3. Add comprehensive docstring with:
   - Purpose
   - Supported actions
   - Payload examples
   - Return shape
   - Notes
4. Use best-effort imports for dependencies
5. Add audit logging for sensitive operations
6. Update this documentation

---

## Changelog

**v0.1.0** (October 24, 2025)
- Initial comprehensive documentation
- 30+ tools across 17 categories
- Complete API reference

---

## License

Copyright © 2025 Cineca Agentic Platform. All rights reserved.

---

**End of MCP Tools Reference Documentation**
