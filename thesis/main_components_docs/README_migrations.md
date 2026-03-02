# Database Migrations

> **Module:** `db/migrations`  
> **Database:** PostgreSQL  
> **Purpose:** Schema evolution and database population utilities for the Cineca Agentic Platform

## Table of Contents

1. [Overview](#overview)
2. [Migration Files](#migration-files)
3. [Migration Details](#migration-details)
   - [005: Add Warnings to Agent Runs](#005-add-warnings-to-agent-runs)
   - [006: Add Step Timestamps](#006-add-step-timestamps)
   - [007: Change Output to JSONB](#007-change-output-to-jsonb)
   - [008: Add Metrics to Agent Runs](#008-add-metrics-to-agent-runs)
   - [Internal Ops Audit Table](#internal-ops-audit-table)
4. [Database Population Utility](#database-population-utility)
5. [Schema Overview](#schema-overview)
6. [Index Strategy](#index-strategy)
7. [Data Types & Conventions](#data-types--conventions)
8. [Running Migrations](#running-migrations)
9. [Rollback Procedures](#rollback-procedures)
10. [Query Examples](#query-examples)
11. [Performance Considerations](#performance-considerations)
12. [Related Documentation](#related-documentation)

---

## Overview

This directory contains PostgreSQL database migrations for the Cineca Agentic Platform. The migrations follow a numbered sequence to ensure proper ordering and track schema evolution over time.

### Migration Naming Convention

```
{sequence_number}_{description}.sql
```

- **Sequence Numbers**: 3-digit prefixed (e.g., `005`, `006`)
- **Description**: Snake_case describing the change
- **Special Files**: Non-numbered files for standalone features (e.g., `internal_ops_audit_table.sql`)

### Current Migration Sequence

| Number | File | Description | Date |
|--------|------|-------------|------|
| 005 | `005_add_warnings_to_agent_runs.sql` | Add warnings JSONB column | 2025-11-09 |
| 006 | `006_add_step_timestamps.sql` | Add step timing columns | - |
| 007 | `007_change_output_to_jsonb.sql` | Convert output TEXT to JSONB | - |
| 008 | `008_add_metrics_to_agent_runs.sql` | Add metrics JSONB column | 2025-11-09 |
| - | `internal_ops_audit_table.sql` | Create audit trail table | - |

---

## Migration Files

### Directory Structure

```
db/migrations/
├── README.md                           # This documentation
├── 005_add_warnings_to_agent_runs.sql  # 16 lines
├── 006_add_step_timestamps.sql         # 20 lines
├── 007_change_output_to_jsonb.sql      # 23 lines
├── 008_add_metrics_to_agent_runs.sql   # 13 lines
└── internal_ops_audit_table.sql        # 115 lines
```

### Related Files

```
db/
├── populate.py      # Database population utilities (240 lines)
├── migrations/      # This directory
├── postgres_control/# PostgreSQL control plane
├── memgraph_domain/ # Memgraph domain layer
├── redis_cache/     # Redis caching layer
└── redis/           # Redis utilities
```

---

## Migration Details

### 005: Add Warnings to Agent Runs

**File:** `005_add_warnings_to_agent_runs.sql`  
**Date:** 2025-11-09  
**Purpose:** Store non-fatal warnings during agent execution

#### Schema Change

```sql
ALTER TABLE agent_runs 
ADD COLUMN IF NOT EXISTS warnings JSONB DEFAULT '[]'::jsonb;
```

#### Column Details

| Column | Type | Default | Nullable | Description |
|--------|------|---------|----------|-------------|
| `warnings` | JSONB | `'[]'::jsonb` | Yes | Non-fatal warnings during execution |

#### Index Created

```sql
CREATE INDEX IF NOT EXISTS idx_agent_runs_has_warnings 
ON agent_runs ((jsonb_array_length(warnings) > 0))
WHERE jsonb_array_length(warnings) > 0;
```

This is a **partial expression index** that:
- Only indexes runs that have at least one warning
- Enables efficient filtering of runs with warnings
- Uses minimal storage by excluding empty warning arrays

#### Use Cases

- Model fallback notifications (e.g., RAM constraints caused model downgrade)
- Resource constraint warnings
- Deprecation notices
- Rate limit approached warnings
- Timeout recovery notices

#### Example Warning Structure

```json
[
    {
        "code": "MODEL_DOWNGRADE",
        "message": "Switched from gpt-4o to gpt-4o-mini due to RAM constraints",
        "timestamp": "2025-11-09T14:30:00Z",
        "severity": "warning",
        "context": {
            "original_model": "gpt-4o",
            "fallback_model": "gpt-4o-mini",
            "reason": "insufficient_ram"
        }
    }
]
```

---

### 006: Add Step Timestamps

**File:** `006_add_step_timestamps.sql`  
**Purpose:** Enable per-step latency tracking and performance analysis

#### Schema Change

```sql
ALTER TABLE agent_steps 
ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;
```

#### Column Details

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `started_at` | TIMESTAMPTZ | Yes | ISO timestamp when step execution started |
| `finished_at` | TIMESTAMPTZ | Yes | ISO timestamp when step execution finished |

#### Indexes Created

```sql
-- General timestamp queries
CREATE INDEX IF NOT EXISTS idx_agent_steps_timestamps 
ON agent_steps(started_at, finished_at);

-- Duration/latency calculations
CREATE INDEX IF NOT EXISTS idx_agent_steps_duration
ON agent_steps(finished_at, started_at) 
WHERE started_at IS NOT NULL AND finished_at IS NOT NULL;
```

#### Use Cases

- Per-step latency tracking
- Step duration analysis
- Performance bottleneck identification
- SLA compliance monitoring
- Timeline visualization

#### Duration Calculation

```sql
-- Calculate step duration in milliseconds
SELECT 
    id,
    EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000 AS duration_ms
FROM agent_steps
WHERE started_at IS NOT NULL 
  AND finished_at IS NOT NULL;
```

---

### 007: Change Output to JSONB

**File:** `007_change_output_to_jsonb.sql`  
**Purpose:** Enable structured output access without client-side JSON parsing

#### Migration Strategy

This migration performs a **data migration** before the schema change:

1. **Wrap non-JSON text** in a JSON object with a `"text"` field
2. **Convert column type** from TEXT to JSONB
3. **Add GIN index** for efficient JSONB queries

#### Step 1: Data Migration

```sql
UPDATE agent_runs
SET output = jsonb_build_object('text', output)::text
WHERE output IS NOT NULL 
  AND output != ''
  AND output !~ '^\s*[\{\[]';  -- Not starting with { or [
```

This ensures:
- Existing JSON outputs are preserved as-is
- Plain text outputs are wrapped: `"Hello"` → `{"text": "Hello"}`
- Empty/null outputs remain unchanged

#### Step 2: Column Type Change

```sql
ALTER TABLE agent_runs 
ALTER COLUMN output TYPE JSONB 
USING CASE 
    WHEN output IS NULL OR output = '' THEN NULL
    ELSE output::jsonb
END;
```

#### Step 3: Add GIN Index

```sql
CREATE INDEX IF NOT EXISTS idx_agent_runs_output_gin 
ON agent_runs USING gin(output);
```

#### Benefits

- **Direct API access**: Output returned as JSON, not string
- **Query flexibility**: Use JSONB operators (`@>`, `?`, `->`)
- **Index efficiency**: GIN index supports containment queries
- **Type safety**: PostgreSQL validates JSON structure

#### Output Query Examples

```sql
-- Get specific field from output
SELECT output->>'result' AS result FROM agent_runs;

-- Filter by output content
SELECT * FROM agent_runs WHERE output @> '{"success": true}';

-- Check if output has key
SELECT * FROM agent_runs WHERE output ? 'error';
```

---

### 008: Add Metrics to Agent Runs

**File:** `008_add_metrics_to_agent_runs.sql`  
**Date:** 2025-11-09  
**Purpose:** Store execution metrics for performance analysis

#### Schema Change

```sql
ALTER TABLE agent_runs 
ADD COLUMN IF NOT EXISTS metrics JSONB;
```

#### Column Details

| Column | Type | Default | Nullable | Description |
|--------|------|---------|----------|-------------|
| `metrics` | JSONB | NULL | Yes | Execution metrics (latency, LLM calls, tool calls) |

#### Index Created

```sql
CREATE INDEX IF NOT EXISTS idx_agent_runs_metrics_gin 
ON agent_runs USING gin(metrics);
```

#### Example Metrics Structure

```json
{
    "overall_ms": 2450,
    "llm_calls": [
        {
            "model": "gpt-4o",
            "input_tokens": 1250,
            "output_tokens": 350,
            "latency_ms": 1200,
            "cached": false
        },
        {
            "model": "gpt-4o",
            "input_tokens": 1600,
            "output_tokens": 200,
            "latency_ms": 800,
            "cached": false
        }
    ],
    "tool_calls": [
        {
            "tool": "web_search",
            "latency_ms": 350,
            "success": true
        }
    ],
    "total_tokens": 3400,
    "estimated_cost_usd": 0.0425
}
```

#### Metrics Query Examples

```sql
-- Get average run duration
SELECT AVG((metrics->>'overall_ms')::numeric) AS avg_duration_ms
FROM agent_runs
WHERE metrics IS NOT NULL;

-- Get runs with high token usage
SELECT id, metrics->>'total_tokens' AS tokens
FROM agent_runs
WHERE (metrics->>'total_tokens')::int > 10000;

-- Aggregate LLM usage by model
SELECT 
    llm_call->>'model' AS model,
    COUNT(*) AS call_count,
    SUM((llm_call->>'input_tokens')::int) AS total_input_tokens
FROM agent_runs,
     jsonb_array_elements(metrics->'llm_calls') AS llm_call
WHERE metrics IS NOT NULL
GROUP BY llm_call->>'model';
```

---

### Internal Ops Audit Table

**File:** `internal_ops_audit_table.sql`  
**Purpose:** Permanent audit trail for all internal endpoint operations

This is a **standalone migration** that creates a comprehensive audit table for tracking internal operations.

#### Table Schema

```sql
CREATE TABLE IF NOT EXISTS internal_ops_events (
    -- Primary key
    id BIGSERIAL PRIMARY KEY,
    
    -- Event identification
    correlation_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    
    -- Actor information
    actor_sub VARCHAR(255) NOT NULL,
    actor_type VARCHAR(50),
    
    -- Request details
    endpoint VARCHAR(255) NOT NULL,
    http_method VARCHAR(10) NOT NULL,
    request_params JSONB,
    request_body JSONB,
    
    -- Response details
    http_status INTEGER NOT NULL,
    response_body JSONB,
    
    -- Operation metadata
    operation_result VARCHAR(50) NOT NULL,
    duration_ms INTEGER,
    
    -- Idempotency tracking
    idempotency_key VARCHAR(255),
    is_idempotency_replay BOOLEAN DEFAULT FALSE,
    
    -- Cache tracking
    cache_status VARCHAR(20),
    
    -- Error details
    error_type VARCHAR(100),
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    
    -- Metadata
    metadata JSONB
);
```

#### Column Reference

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `id` | BIGSERIAL | PK | Auto-incrementing ID |
| `correlation_id` | VARCHAR(255) | Yes | Request ID for distributed tracing |
| `event_type` | VARCHAR(100) | Yes | Type of operation (e.g., 'auto_start_override') |
| `actor_sub` | VARCHAR(255) | Yes | Subject claim from JWT token |
| `actor_type` | VARCHAR(50) | No | Actor type: 'service', 'm2m', 'system' |
| `endpoint` | VARCHAR(255) | Yes | Full endpoint path |
| `http_method` | VARCHAR(10) | Yes | HTTP method: GET, POST, etc. |
| `request_params` | JSONB | No | Query parameters |
| `request_body` | JSONB | No | Request payload |
| `http_status` | INTEGER | Yes | HTTP response status code |
| `response_body` | JSONB | No | Response payload (redacted if sensitive) |
| `operation_result` | VARCHAR(50) | Yes | Result: 'success', 'error', 'cache_hit', etc. |
| `duration_ms` | INTEGER | No | Request duration in milliseconds |
| `idempotency_key` | VARCHAR(255) | No | Idempotency key from header |
| `is_idempotency_replay` | BOOLEAN | No | True if served from cache |
| `cache_status` | VARCHAR(20) | No | Cache status: 'hit', 'miss', 'refresh' |
| `error_type` | VARCHAR(100) | No | Error classification |
| `error_message` | TEXT | No | Full error message |
| `created_at` | TIMESTAMPTZ | Yes | Event timestamp |
| `metadata` | JSONB | No | Additional context, feature flags |

#### Indexes

```sql
-- Correlation ID lookup
CREATE INDEX idx_internal_ops_events_correlation_id 
    ON internal_ops_events(correlation_id);

-- Actor-based queries
CREATE INDEX idx_internal_ops_events_actor_sub 
    ON internal_ops_events(actor_sub);

-- Event type filtering
CREATE INDEX idx_internal_ops_events_event_type 
    ON internal_ops_events(event_type);

-- Time-based queries (descending for recent-first)
CREATE INDEX idx_internal_ops_events_created_at 
    ON internal_ops_events(created_at DESC);

-- Idempotency key lookup (partial index)
CREATE INDEX idx_internal_ops_events_idempotency_key 
    ON internal_ops_events(idempotency_key) 
    WHERE idempotency_key IS NOT NULL;

-- Result-based filtering
CREATE INDEX idx_internal_ops_events_result 
    ON internal_ops_events(operation_result);

-- Composite index for actor audit trails
CREATE INDEX idx_internal_ops_events_actor_time 
    ON internal_ops_events(actor_sub, created_at DESC);
```

#### Event Types

| Event Type | Description |
|------------|-------------|
| `auto_start_override` | Auto-start behavior override |
| `preview_staged` | Preview environment staging |
| `db_counts` | Database count queries |
| `config_update` | Configuration changes |
| `feature_toggle` | Feature flag changes |
| `cache_invalidation` | Cache invalidation requests |

#### Operation Results

| Result | Description |
|--------|-------------|
| `success` | Operation completed successfully |
| `error` | Operation failed with error |
| `cache_hit` | Response served from cache |
| `feature_unavailable` | Feature is disabled/unavailable |

---

## Database Population Utility

The `db/populate.py` module provides utilities for creating and populating test data.

### Module Overview

**File:** `db/populate.py`  
**Lines:** ~240  
**Purpose:** Database population utilities for test data generation

### Public API

#### `create_from_original_and_populate()`

Main entry point for database setup and population.

```python
def create_from_original_and_populate(
    wipe: bool = False,
    users: int | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict:
    """
    Create database schema from original definitions and optionally populate.

    Args:
        wipe: If True, wipe existing database before creating
        users: If provided, populate with N users after creation
        progress_callback: Optional callback(progress: 0-100, message: str)

    Returns:
        dict with creation results (nodes_created, edges_created, etc.)

    Raises:
        RuntimeError: If database operations fail
    """
```

**Progress Stages:**

| Progress % | Stage |
|------------|-------|
| 0-10% | Wipe database (if requested) |
| 10-40% | Create schema |
| 40-85% | Build graph (users, tools, sessions) |
| 85-95% | Persist to database |
| 95-100% | Complete |

#### `build_graph()`

Generates synthetic graph data in-memory.

```python
def build_graph(
    num_users: int = 100,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict:
    """
    Build synthetic graph data structure (in-memory).

    Args:
        num_users: Number of users to generate
        progress_callback: Optional callback(progress: 0-100, message: str)

    Returns:
        dict with graph structure:
        - users: List of user dicts
        - tools: List of tool dicts
        - sessions: List of session dicts
        - edges: List of relationship edges
    """
```

**Generated Data:**

| Entity | Count Formula | Attributes |
|--------|---------------|------------|
| Users | `num_users` | id, email, name, created_at |
| Tools | `max(10, num_users // 5)` | id, name, description, created_at |
| Sessions | `min(num_users * 2, 500)` | id, user_id, tool_id, created_at |
| Edges | 2 per session | CREATED_SESSION, USES_TOOL |

#### `persist_graph()`

Persists graph data to Memgraph database.

```python
def persist_graph(
    graph: dict,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict:
    """
    Persist graph data to Memgraph database.

    Args:
        graph: Graph structure from build_graph()
        progress_callback: Optional callback(progress: 0-100, message: str)

    Returns:
        dict with persistence results:
        - nodes_created: Total nodes created
        - edges_created: Total edges created
        - users: Number of users
        - tools: Number of tools
        - sessions: Number of sessions
    """
```

#### `check_utilities_available()`

Checks if database utilities are available.

```python
def check_utilities_available() -> tuple[bool, str | None]:
    """
    Check if all required DB utilities are available.

    Returns:
        (available: bool, error_message: Optional[str])
    """
```

### Usage Examples

```python
from db.populate import (
    create_from_original_and_populate,
    build_graph,
    persist_graph,
    check_utilities_available,
)

# Check prerequisites
available, error = check_utilities_available()
if not available:
    print(f"Error: {error}")
    exit(1)

# Full setup with progress tracking
def on_progress(progress: float, message: str):
    print(f"[{progress:.0f}%] {message}")

result = create_from_original_and_populate(
    wipe=True,
    users=1000,
    progress_callback=on_progress,
)

print(f"Created {result['nodes_created']} nodes")
print(f"Created {result['edges_created']} edges")

# Or build and persist separately
graph = build_graph(num_users=500)
print(f"Built {len(graph['users'])} users, {len(graph['tools'])} tools")

persist_result = persist_graph(graph)
print(f"Persisted {persist_result['nodes_created']} nodes")
```

### Progress Callback Format

```python
def progress_callback(progress: float, message: str) -> None:
    """
    Progress callback function.
    
    Args:
        progress: Float between 0-100 for progress, or -1 for error
        message: Human-readable status message
    """
```

**Progress Values:**

| Value | Meaning |
|-------|---------|
| 0-100 | Percentage complete |
| -1 | Error occurred (message contains error details) |

---

## Schema Overview

### Tables Modified by Migrations

#### `agent_runs`

Primary table for storing agent execution runs.

| Column | Type | Added By | Description |
|--------|------|----------|-------------|
| `id` | UUID | Base | Primary key |
| `output` | JSONB | 007 | Structured output (converted from TEXT) |
| `warnings` | JSONB | 005 | Non-fatal warnings array |
| `metrics` | JSONB | 008 | Execution metrics |
| ... | ... | Base | Other columns |

#### `agent_steps`

Table for individual steps within agent runs.

| Column | Type | Added By | Description |
|--------|------|----------|-------------|
| `id` | UUID | Base | Primary key |
| `started_at` | TIMESTAMPTZ | 006 | Step start timestamp |
| `finished_at` | TIMESTAMPTZ | 006 | Step completion timestamp |
| ... | ... | Base | Other columns |

#### `internal_ops_events`

Audit trail table for internal operations.

| Column | Type | Added By | Description |
|--------|------|----------|-------------|
| `id` | BIGSERIAL | audit table | Primary key |
| 30+ columns | Various | audit table | See [Internal Ops Audit Table](#internal-ops-audit-table) |

---

## Index Strategy

### Index Types Used

| Type | Description | Use Case |
|------|-------------|----------|
| B-tree | Default index type | Equality and range queries |
| GIN | Generalized Inverted Index | JSONB containment queries |
| Partial | Indexes subset of rows | Filtering specific conditions |
| Expression | Indexes computed values | Derived value queries |
| Composite | Multi-column indexes | Combined query patterns |

### Indexes by Table

#### `agent_runs` Indexes

```sql
-- Partial expression index for runs with warnings
idx_agent_runs_has_warnings ON ((jsonb_array_length(warnings) > 0))
    WHERE jsonb_array_length(warnings) > 0

-- GIN index for output JSONB queries
idx_agent_runs_output_gin USING gin(output)

-- GIN index for metrics JSONB queries
idx_agent_runs_metrics_gin USING gin(metrics)
```

#### `agent_steps` Indexes

```sql
-- Composite timestamp index
idx_agent_steps_timestamps ON (started_at, finished_at)

-- Partial composite for duration queries
idx_agent_steps_duration ON (finished_at, started_at) 
    WHERE started_at IS NOT NULL AND finished_at IS NOT NULL
```

#### `internal_ops_events` Indexes

```sql
-- Single column indexes
idx_internal_ops_events_correlation_id ON (correlation_id)
idx_internal_ops_events_actor_sub ON (actor_sub)
idx_internal_ops_events_event_type ON (event_type)
idx_internal_ops_events_result ON (operation_result)

-- Descending time index for recent-first queries
idx_internal_ops_events_created_at ON (created_at DESC)

-- Partial index for idempotency lookups
idx_internal_ops_events_idempotency_key ON (idempotency_key) 
    WHERE idempotency_key IS NOT NULL

-- Composite index for actor audit trails
idx_internal_ops_events_actor_time ON (actor_sub, created_at DESC)
```

---

## Data Types & Conventions

### JSONB vs JSON

All JSON columns use **JSONB** (binary JSON):

- **Storage**: Parsed and stored in binary format
- **Indexing**: Supports GIN indexes for fast containment queries
- **Performance**: Faster for read operations
- **Trade-off**: Slightly slower writes, slightly more storage

### Timestamp Conventions

- **Type**: `TIMESTAMP WITH TIME ZONE` (TIMESTAMPTZ)
- **Default**: `NOW()` for creation timestamps
- **Format**: ISO 8601 (`YYYY-MM-DDTHH:MM:SS.mmmZ`)
- **Timezone**: Stored in UTC

### Naming Conventions

| Entity | Convention | Example |
|--------|------------|---------|
| Tables | snake_case | `agent_runs` |
| Columns | snake_case | `created_at` |
| Indexes | `idx_{table}_{columns}` | `idx_agent_runs_output_gin` |
| Constraints | `{table}_{column}_{type}` | `agent_runs_id_pkey` |

---

## Running Migrations

### Manual Execution

```bash
# Connect to PostgreSQL
psql -h localhost -U postgres -d cineca_platform

# Run migration
\i db/migrations/005_add_warnings_to_agent_runs.sql

# Verify
\d agent_runs
```

### Using psql Script

```bash
# Run all migrations in order
for file in db/migrations/0*.sql; do
    echo "Running $file..."
    psql -h localhost -U postgres -d cineca_platform -f "$file"
done

# Run standalone migrations
psql -h localhost -U postgres -d cineca_platform \
    -f db/migrations/internal_ops_audit_table.sql
```

### Migration Order

Migrations must be run in sequence order:

```
005_add_warnings_to_agent_runs.sql    (first)
006_add_step_timestamps.sql
007_change_output_to_jsonb.sql
008_add_metrics_to_agent_runs.sql     (last numbered)
internal_ops_audit_table.sql          (standalone, any time)
```

### Idempotent Operations

All migrations use `IF NOT EXISTS` / `IF EXISTS` patterns:

```sql
-- Columns
ADD COLUMN IF NOT EXISTS warnings JSONB

-- Indexes
CREATE INDEX IF NOT EXISTS idx_name ON table(column)

-- Tables
CREATE TABLE IF NOT EXISTS internal_ops_events (...)
```

This allows migrations to be re-run safely without errors.

---

## Rollback Procedures

### 005: Remove Warnings Column

```sql
-- Drop index first
DROP INDEX IF EXISTS idx_agent_runs_has_warnings;

-- Drop column
ALTER TABLE agent_runs DROP COLUMN IF EXISTS warnings;
```

### 006: Remove Step Timestamps

```sql
-- Drop indexes
DROP INDEX IF EXISTS idx_agent_steps_timestamps;
DROP INDEX IF EXISTS idx_agent_steps_duration;

-- Drop columns
ALTER TABLE agent_steps 
DROP COLUMN IF EXISTS started_at,
DROP COLUMN IF EXISTS finished_at;
```

### 007: Revert Output to TEXT

⚠️ **Warning**: This rollback may lose data if JSON outputs don't fit TEXT format.

```sql
-- Drop GIN index
DROP INDEX IF EXISTS idx_agent_runs_output_gin;

-- Convert back to TEXT
ALTER TABLE agent_runs 
ALTER COLUMN output TYPE TEXT 
USING output::text;
```

### 008: Remove Metrics Column

```sql
-- Drop GIN index
DROP INDEX IF EXISTS idx_agent_runs_metrics_gin;

-- Drop column
ALTER TABLE agent_runs DROP COLUMN IF EXISTS metrics;
```

### Internal Ops Audit Table

```sql
-- Drop all indexes (optional, CASCADE handles this)
-- DROP INDEX IF EXISTS idx_internal_ops_events_*;

-- Drop table
DROP TABLE IF EXISTS internal_ops_events CASCADE;
```

---

## Query Examples

### Agent Runs Queries

```sql
-- Find runs with warnings
SELECT id, warnings
FROM agent_runs
WHERE jsonb_array_length(warnings) > 0;

-- Get runs with specific warning code
SELECT id, warnings
FROM agent_runs
WHERE warnings @> '[{"code": "MODEL_DOWNGRADE"}]';

-- Get average run duration from metrics
SELECT 
    DATE_TRUNC('hour', created_at) AS hour,
    AVG((metrics->>'overall_ms')::numeric) AS avg_duration_ms,
    COUNT(*) AS run_count
FROM agent_runs
WHERE metrics IS NOT NULL
GROUP BY hour
ORDER BY hour DESC
LIMIT 24;

-- Get output with specific structure
SELECT id, output->>'result' AS result
FROM agent_runs
WHERE output ? 'result';
```

### Agent Steps Queries

```sql
-- Calculate step durations
SELECT 
    id,
    run_id,
    EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000 AS duration_ms
FROM agent_steps
WHERE started_at IS NOT NULL 
  AND finished_at IS NOT NULL
ORDER BY duration_ms DESC
LIMIT 10;

-- Find slow steps (> 5 seconds)
SELECT id, run_id, started_at, finished_at
FROM agent_steps
WHERE finished_at - started_at > INTERVAL '5 seconds';

-- Steps per hour distribution
SELECT 
    DATE_TRUNC('hour', started_at) AS hour,
    COUNT(*) AS step_count
FROM agent_steps
WHERE started_at IS NOT NULL
GROUP BY hour
ORDER BY hour DESC;
```

### Audit Trail Queries

```sql
-- Recent operations by actor
SELECT event_type, operation_result, created_at, duration_ms
FROM internal_ops_events
WHERE actor_sub = 'service@clients'
ORDER BY created_at DESC
LIMIT 20;

-- Failed operations in last hour
SELECT correlation_id, event_type, error_type, error_message, created_at
FROM internal_ops_events
WHERE operation_result = 'error'
  AND created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;

-- Idempotency cache hit rate
SELECT 
    COUNT(*) FILTER (WHERE is_idempotency_replay = true) AS cache_hits,
    COUNT(*) FILTER (WHERE idempotency_key IS NOT NULL) AS total_with_idem_key,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_idempotency_replay = true) / 
          NULLIF(COUNT(*) FILTER (WHERE idempotency_key IS NOT NULL), 0), 2) AS hit_rate_percent
FROM internal_ops_events
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Operation performance metrics
SELECT 
    event_type,
    COUNT(*) AS total_requests,
    AVG(duration_ms) AS avg_duration_ms,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_ms) AS p50_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
    MAX(duration_ms) AS max_duration_ms
FROM internal_ops_events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY event_type
ORDER BY total_requests DESC;

-- Feature availability status over time
SELECT 
    DATE_TRUNC('hour', created_at) AS hour,
    COUNT(*) FILTER (WHERE operation_result = 'feature_unavailable') AS unavailable_count,
    COUNT(*) AS total_requests
FROM internal_ops_events
WHERE event_type = 'db_counts'
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY hour
ORDER BY hour DESC;
```

---

## Performance Considerations

### JSONB Indexing

GIN indexes on JSONB columns enable fast containment queries but:
- **Insert overhead**: ~10-20% slower writes
- **Storage**: GIN indexes can be 2-3x the column size
- **Maintenance**: VACUUM/REINDEX periodically for fragmented indexes

### Partial Index Benefits

The `idx_agent_runs_has_warnings` partial index:
- Only includes rows with non-empty warnings
- Estimated 90%+ space savings vs full index
- Faster inserts for runs without warnings

### Query Optimization Tips

```sql
-- Use @> for JSONB containment (uses GIN index)
SELECT * FROM agent_runs WHERE output @> '{"success": true}';

-- Avoid ->> in WHERE clause (doesn't use index)
-- BAD:  WHERE output->>'status' = 'success'
-- GOOD: WHERE output @> '{"status": "success"}'

-- Use partial index conditions
SELECT * FROM agent_runs 
WHERE jsonb_array_length(warnings) > 0;  -- Uses partial index
```

### Connection to populate.py

The `persist_graph()` function in `populate.py` uses batch operations:
- Simulates batch INSERT performance
- Progress callbacks for long-running operations
- Suitable for populating test environments

---

## Related Documentation

- **PostgreSQL Control**: `db/postgres_control/README.md`
- **Redis Cache**: `db/redis_cache/README.md`
- **Memgraph Domain**: `db/memgraph_domain/README.md`
- **Job Models**: `src/jobs/models.py`
- **Agent Runs Service**: `src/services/agent_runs.py`

---

## Changelog

### 2025-11-09

- Added migration 005: warnings column to agent_runs
- Added migration 008: metrics column to agent_runs

### Previous

- Added migration 006: step timestamps
- Added migration 007: output TEXT to JSONB conversion
- Created internal_ops_audit_table for audit trail

---

## License

This module is part of the Cineca Agentic Platform and follows the project's licensing terms.
