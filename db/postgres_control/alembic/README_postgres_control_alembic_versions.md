# Alembic Database Migrations

> **Module:** `db/postgres_control/alembic`  
> **Database:** PostgreSQL  
> **Migration Tool:** Alembic (SQLAlchemy)  
> **Current Revision:** 026  
> **Purpose:** Schema evolution and version control for the Cineca Agentic Platform PostgreSQL database

## Table of Contents

1. [Overview](#overview)
2. [Directory Structure](#directory-structure)
3. [Configuration](#configuration)
4. [Migration Summary](#migration-summary)
5. [Detailed Migration Reference](#detailed-migration-reference)
   - [001: Initial Tenants Table](#001-initial-tenants-table)
   - [002: Tools Tables](#002-tools-tables)
   - [003: Jobs Tables](#003-jobs-tables)
   - [004: Providers Tables](#004-providers-tables)
   - [005: Builtins Manifests Tables](#005-builtins-manifests-tables)
   - [006: Model Instances Tables](#006-model-instances-tables)
   - [007: User Default Models](#007-user-default-models)
   - [008: Agent Tables](#008-agent-tables)
   - [009: Add Last Step Seq](#009-add-last-step-seq)
   - [010: Allow Message Step Type](#010-allow-message-step-type)
   - [011: Builtin Process Tables](#011-builtin-process-tables)
   - [012: Internal Ops Events](#012-internal-ops-events)
   - [013: Add Steps Output to Agent Runs](#013-add-steps-output-to-agent-runs)
   - [014: Rename Session Metadata](#014-rename-session-metadata)
   - [015: Add Todos/Warnings/Metrics](#015-add-todoswarningsmetrics)
   - [016: Add ID to Model Defaults](#016-add-id-to-model-defaults)
   - [017: Add Sequence to Model Defaults ID](#017-add-sequence-to-model-defaults-id)
   - [018: Allow NULL Tenant ID](#018-allow-null-tenant-id)
   - [019: Enforce Single Default Per Scope](#019-enforce-single-default-per-scope)
   - [020: Add Request ID to Agent Runs](#020-add-request-id-to-agent-runs)
   - [021: Add Queued Status to Agent Runs](#021-add-queued-status-to-agent-runs)
   - [022: Add Idempotency Status Code](#022-add-idempotency-status-code)
   - [023: Add Model Config to Agent Runs](#023-add-model-config-to-agent-runs)
   - [024: Add LLM Error Tracking](#024-add-llm-error-tracking)
   - [025: Add Metadata to Agent Runs](#025-add-metadata-to-agent-runs)
   - [026: Add Agent Run Indexes](#026-add-agent-run-indexes)
6. [Schema Overview](#schema-overview)
7. [Table Reference](#table-reference)
8. [Triggers & Functions](#triggers--functions)
9. [Running Migrations](#running-migrations)
10. [Rollback Procedures](#rollback-procedures)
11. [Best Practices](#best-practices)
12. [Troubleshooting](#troubleshooting)

---

## Overview

This directory contains Alembic database migrations for the Cineca Agentic Platform. Alembic is a database migration tool for SQLAlchemy that provides:

- **Version Control**: Track schema changes over time
- **Reversibility**: Every migration has upgrade and downgrade functions
- **Dependency Chain**: Migrations run in order based on revision IDs
- **Auto-generation**: Can auto-detect model changes (though manual migrations preferred)

### Key Features

- **26 migrations** covering all platform tables
- **Trigger functions** for automatic timestamp updates
- **Check constraints** for data integrity
- **Foreign key relationships** with cascade rules
- **GIN/JSONB indexes** for efficient JSON queries
- **Partial indexes** for sparse data patterns

---

## Directory Structure

```
db/postgres_control/alembic/
├── README.md                    # This documentation
├── env.py                       # Alembic environment configuration (84 lines)
├── script.py.mako               # Template for new migrations (30 lines)
└── versions/                    # Migration files directory
    ├── 001_initial_tenants_table.py          # Initial tenants schema
    ├── 002_create_tools_tables.py            # Tools and invocations
    ├── 003_create_jobs_tables.py             # Jobs and events
    ├── 004_create_providers_tables.py        # Provider registry
    ├── 005_create_builtins_manifests_tables.py  # Model manifests
    ├── 006_create_model_instances_tables.py  # Model instances
    ├── 007_user_default_models.py            # User defaults
    ├── 008_create_agent_tables.py            # Agent sessions/steps/runs
    ├── 009_add_last_step_seq_to_agent_sessions.py
    ├── 010_allow_message_step_type.py
    ├── 011_create_builtin_process_tables.py
    ├── 012_create_internal_ops_events.py
    ├── 013_add_steps_output_to_agent_runs.py
    ├── 014_rename_session_metadata_to_metadata.py
    ├── 015_add_todos_warnings_metrics_to_agent_runs.py
    ├── 016_add_id_to_model_defaults.py
    ├── 017_add_sequence_to_model_defaults_id.py
    ├── 018_allow_null_tenant_id_in_model_defaults.py
    ├── 019_enforce_single_default_per_scope.py
    ├── 020_add_request_id_to_agent_runs.py
    ├── 021_add_queued_status_to_agent_runs.py
    ├── 022_add_idempotency_status_code.py
    ├── 023_add_model_config_to_agent_runs.py
    ├── 024_add_llm_error_tracking_to_agent_runs.py
    ├── 025_add_metadata_to_agent_runs.py
    └── 026_add_agent_run_indexes.py
```

---

## Configuration

### Environment File (`env.py`)

The `env.py` file configures Alembic for both offline and online migrations:

```python
# Key configuration
from db.postgres_control.database import Base
from db.postgres_control.models.tenant import Tenant
from src.config import settings

# Target metadata for autogenerate
target_metadata = Base.metadata

# Database URL from settings
config.set_main_option("sqlalchemy.url", settings.database_url)
```

#### Offline Mode

Generates SQL scripts without database connection:

```python
def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
```

#### Online Mode

Runs migrations against live database:

```python
def run_migrations_online() -> None:
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No pooling for migrations
    )
```

### Migration Template (`script.py.mako`)

Template for generating new migrations:

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}

def upgrade() -> None:
    ${upgrades if upgrades else "pass"}

def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

---

## Migration Summary

### Migration Chain

```
001 → 002 → 003 → 004 → 005 → 006 → 007 → 008 → 009 → 010 →
011 → 012 → 013 → 014 → 015 → 016 → 017 → 018 → 019 → 020 →
021 → 022 → 023 → 024 → 025 → 026 (HEAD)
```

### Quick Reference Table

| Rev | Name | Tables Created | Key Changes |
|-----|------|----------------|-------------|
| 001 | initial_tenants_table | `tenants` | Base tenant table with triggers |
| 002 | create_tools_tables | `tools`, `tool_invocations`, `tool_audit_events` | Tool registry |
| 003 | create_jobs_tables | `jobs`, `job_events` | Async job management |
| 004 | create_providers_tables | `providers`, `provider_secrets`, `provider_defaults`, `provider_audit_events` | LLM provider registry |
| 005 | create_builtins_manifests_tables | `builtins_manifests`, `builtins_activations`, `builtins_staging_jobs`, `builtins_manifest_audit` | Model manifest management |
| 006 | create_model_instances_tables | `model_instances`, `model_instance_events`, `model_defaults` | Runtime model instances |
| 007 | user_default_models | `user_default_models` | Per-user model preferences |
| 008 | create_agent_tables | `agent_sessions`, `agent_steps`, `agent_runs`, `idempotency_keys` | Core agent tables |
| 009 | add_last_step_seq | - | Add `last_step_seq` column |
| 010 | allow_message_step_type | - | Add 'message' to step types |
| 011 | create_builtin_process_tables | `builtin_manifest_activation_history`, `builtin_process_events` | Process tracking |
| 012 | create_internal_ops_events | `internal_ops_events` | Internal operations audit |
| 013 | add_steps_output | - | Add `steps`, `output` to agent_runs |
| 014 | rename_session_metadata | - | Rename column |
| 015 | add_todos_warnings_metrics | - | Add JSONB columns, change output to JSONB |
| 016 | add_id_to_model_defaults | - | Add surrogate key |
| 017 | add_sequence_to_id | - | Add sequence for ID |
| 018 | allow_null_tenant_id | - | Allow NULL tenant_id |
| 019 | enforce_single_default | - | Unique constraint enforcement |
| 020 | add_request_id | - | Add request_id column |
| 021 | add_queued_status | - | Add 'queued' status |
| 022 | add_idempotency_status_code | - | Add status_code column |
| 023 | add_model_config | - | Add model config columns |
| 024 | add_llm_error_tracking | - | Add LLM error columns |
| 025 | add_metadata | - | Add metadata JSONB |
| 026 | add_agent_run_indexes | - | Add composite indexes |

---

## Detailed Migration Reference

### 001: Initial Tenants Table

**File:** `001_initial_tenants_table.py`  
**Date:** 2025-10-11  
**Tables Created:** `tenants`

#### Schema

```sql
CREATE TABLE tenants (
    id TEXT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    admin_email VARCHAR(320) NOT NULL,
    metadata JSONB DEFAULT '{}' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    version BIGINT DEFAULT 0 NOT NULL,
    CONSTRAINT ck_tenants_name_length CHECK (char_length(name) BETWEEN 1 AND 255)
);
```

#### Indexes

```sql
CREATE UNIQUE INDEX ix_tenants_name_lower_unique ON tenants (LOWER(name));
CREATE INDEX ix_tenants_admin_email_lower ON tenants (LOWER(admin_email));
CREATE INDEX ix_tenants_created_at_desc ON tenants (created_at DESC);
```

#### Trigger Function

```sql
CREATE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_tenants_updated_at
BEFORE UPDATE ON tenants
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

---

### 002: Tools Tables

**File:** `002_create_tools_tables.py`  
**Date:** 2025-12-11  
**Tables Created:** `tools`, `tool_invocations`, `tool_audit_events`

#### tools Table

```sql
CREATE TABLE tools (
    id TEXT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    description TEXT,
    input_schema JSONB NOT NULL,
    output_schema JSONB,
    owner_tenant_id TEXT NOT NULL REFERENCES tenants(id),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    version_number BIGINT DEFAULT 0 NOT NULL,
    CONSTRAINT ck_tools_name_length CHECK (char_length(name) BETWEEN 1 AND 255),
    CONSTRAINT ck_tools_version_length CHECK (char_length(version) BETWEEN 1 AND 50)
);
```

#### tool_invocations Table

```sql
CREATE TABLE tool_invocations (
    eid TEXT PRIMARY KEY,
    tool_name VARCHAR(255) NOT NULL,
    tool_version VARCHAR(50) NOT NULL,
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    status VARCHAR(50) NOT NULL,
    params_json JSONB NOT NULL,
    result_json JSONB,
    error_json JSONB,
    started_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at TIMESTAMPTZ,
    idempotency_key VARCHAR(255),
    requested_by VARCHAR(255),
    request_headers JSONB,
    latency_ms INTEGER,
    CONSTRAINT ck_tool_invocations_status CHECK (
        status IN ('pending', 'running', 'finished', 'failed', 'cancelled')
    )
);
```

#### tool_audit_events Table

```sql
CREATE TABLE tool_audit_events (
    id BIGSERIAL PRIMARY KEY,
    eid TEXT NOT NULL REFERENCES tool_invocations(eid) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

---

### 003: Jobs Tables

**File:** `003_create_jobs_tables.py`  
**Date:** 2025-10-12  
**Tables Created:** `jobs`, `job_events`

#### jobs Table

```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    owner_sub VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    payload_json JSONB DEFAULT '{}' NOT NULL,
    result_json JSONB,
    error_json JSONB,
    idempotency_key VARCHAR(255),
    priority INTEGER DEFAULT 0 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    queue_latency_ms INTEGER,
    exec_latency_ms INTEGER,
    etag VARCHAR(64),
    CONSTRAINT jobs_status_check CHECK (
        status IN ('queued', 'running', 'finished', 'failed', 'cancelled')
    )
);
```

#### job_events Table

```sql
CREATE TABLE job_events (
    seq_id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    event_json JSONB DEFAULT '{}' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
```

#### Indexes

```sql
CREATE UNIQUE INDEX idx_jobs_idempotency_unique ON jobs (owner_sub, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX idx_jobs_owner_created ON jobs (owner_sub, created_at DESC);
CREATE INDEX idx_jobs_status_created ON jobs (status, created_at DESC);
CREATE INDEX idx_jobs_tenant_created ON jobs (tenant_id, created_at DESC);
CREATE INDEX idx_jobs_updated ON jobs (updated_at DESC);
```

---

### 004: Providers Tables

**File:** `004_create_providers_tables.py`  
**Date:** 2025-10-12  
**Tables Created:** `providers`, `provider_secrets`, `provider_defaults`, `provider_audit_events`

#### providers Table

```sql
CREATE TABLE providers (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    base_url VARCHAR(512),
    model VARCHAR(255),
    tenant_id VARCHAR(255),
    config_json JSONB,
    has_api_key BOOLEAN DEFAULT false NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_provider_tenant_name UNIQUE (tenant_id, name)
);
```

#### provider_secrets Table

```sql
CREATE TABLE provider_secrets (
    provider_id VARCHAR(255) PRIMARY KEY REFERENCES providers(id) ON DELETE CASCADE,
    api_key_encrypted TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
```

#### provider_defaults Table

```sql
CREATE TABLE provider_defaults (
    scope VARCHAR(50) NOT NULL,
    tenant_id VARCHAR(255) DEFAULT 'global' NOT NULL,
    provider_id VARCHAR(255) NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    PRIMARY KEY (scope, tenant_id),
    CONSTRAINT uq_provider_default_scope_tenant UNIQUE (scope, tenant_id)
);
```

#### provider_audit_events Table

```sql
CREATE TABLE provider_audit_events (
    id SERIAL PRIMARY KEY,
    provider_id VARCHAR(255),
    actor VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    tenant_id VARCHAR(255),
    payload JSONB,
    trace_id VARCHAR(255),
    event_id VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
```

---

### 005: Builtins Manifests Tables

**File:** `005_create_builtins_manifests_tables.py`  
**Date:** 2025-10-12  
**Tables Created:** `builtins_manifests`, `builtins_activations`, `builtins_staging_jobs`, `builtins_manifest_audit`

#### builtins_manifests Table

```sql
CREATE TABLE builtins_manifests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url TEXT NOT NULL,
    content_json JSONB NOT NULL,
    sha256 VARCHAR(64) NOT NULL UNIQUE,
    version VARCHAR(255),
    state VARCHAR(20) NOT NULL,  -- 'staged', 'active', 'archived'
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    activated_at TIMESTAMPTZ,
    created_by_sub VARCHAR(255) NOT NULL,
    etag VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT ck_manifest_state CHECK (state IN ('staged', 'active', 'archived'))
);
```

#### builtins_activations Table

```sql
CREATE TABLE builtins_activations (
    id BIGSERIAL PRIMARY KEY,
    manifest_id UUID NOT NULL REFERENCES builtins_manifests(id) ON DELETE CASCADE,
    activated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    activated_by_sub VARCHAR(255) NOT NULL,
    reason TEXT,
    previous_manifest_id UUID REFERENCES builtins_manifests(id) ON DELETE SET NULL,
    trace_id VARCHAR(255),
    event_id VARCHAR(255)
);
```

---

### 006: Model Instances Tables

**File:** `006_create_model_instances_tables.py`  
**Date:** 2025-10-13  
**Tables Created:** `model_instances`, `model_instance_events`, `model_defaults`

#### model_instances Table

```sql
CREATE TABLE model_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255),
    instance_name VARCHAR(255) NOT NULL,
    provider_id VARCHAR(255) NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    model_id VARCHAR(255) NOT NULL,
    model_uri TEXT,
    enabled BOOLEAN DEFAULT true NOT NULL,
    loaded BOOLEAN DEFAULT false NOT NULL,
    is_default BOOLEAN DEFAULT false NOT NULL,
    context_window INTEGER,
    modalities JSONB,
    description TEXT,
    parameters JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    etag VARCHAR(64) NOT NULL,
    CONSTRAINT uq_model_instances_tenant_name UNIQUE (tenant_id, instance_name)
);
```

#### model_defaults Table

```sql
CREATE TABLE model_defaults (
    scope VARCHAR(20) NOT NULL,  -- 'global', 'tenant', 'user'
    tenant_id VARCHAR(255),
    instance_id UUID NOT NULL REFERENCES model_instances(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    etag VARCHAR(64) NOT NULL,
    CONSTRAINT ck_model_defaults_scope CHECK (scope IN ('global', 'tenant', 'user')),
    CONSTRAINT ck_model_defaults_scope_tenant CHECK (
        (scope = 'global' AND tenant_id IS NULL) OR
        (scope = 'tenant' AND tenant_id IS NOT NULL) OR
        (scope = 'user')
    )
);
```

---

### 007: User Default Models

**File:** `007_user_default_models.py`  
**Date:** 2025-10-17  
**Tables Created:** `user_default_models`

```sql
CREATE TABLE user_default_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255),
    chat_instance_id UUID NOT NULL REFERENCES model_instances(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_by VARCHAR(255),
    etag VARCHAR(64),
    CONSTRAINT uq_user_tenant_default UNIQUE (user_id, tenant_id)
);
```

---

### 008: Agent Tables

**File:** `008_create_agent_tables.py`  
**Date:** 2025-10-17  
**Tables Created:** `agent_sessions`, `agent_steps`, `agent_runs`, `idempotency_keys`

#### agent_sessions Table

```sql
CREATE TABLE agent_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'active' NOT NULL,
    manager VARCHAR(255),
    preferred_workers JSONB,
    llm_preferences JSONB,
    agent_role VARCHAR(255),
    tools JSONB,
    temperature FLOAT DEFAULT 0.2 NOT NULL,
    max_steps INTEGER DEFAULT 8 NOT NULL,
    metadata JSONB DEFAULT '{}' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    last_step_id UUID,
    last_step_seq INTEGER,
    etag VARCHAR(64),
    CONSTRAINT agent_sessions_status_check CHECK (
        status IN ('active', 'completed', 'cancelled', 'failed')
    )
);
```

#### agent_steps Table

```sql
CREATE TABLE agent_steps (
    step_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    type VARCHAR(50) NOT NULL,
    message TEXT,
    tool VARCHAR(255),
    input JSONB,
    output JSONB,
    status VARCHAR(50) DEFAULT 'queued' NOT NULL,
    error JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    completed_at TIMESTAMPTZ,
    CONSTRAINT agent_steps_status_check CHECK (
        status IN ('queued', 'running', 'completed', 'failed', 'cancelled')
    ),
    CONSTRAINT agent_steps_type_check CHECK (
        type IN ('message', 'user', 'assistant', 'tool', 'system', 'error')
    ),
    CONSTRAINT uq_agent_steps_session_seq UNIQUE (session_id, seq)
);
```

#### agent_runs Table

```sql
CREATE TABLE agent_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    model VARCHAR(255),
    manager VARCHAR(255),
    latency_ms INTEGER,
    trace_id VARCHAR(255),
    event_id VARCHAR(255),
    request_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'queued' NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    finished_at TIMESTAMPTZ,
    steps JSONB DEFAULT '[]',
    output JSONB,
    todos JSONB DEFAULT '[]',
    warnings JSONB DEFAULT '[]',
    metrics JSONB,
    metadata JSONB DEFAULT '{}' NOT NULL,
    -- Model configuration (migration 023)
    model_instance_name VARCHAR(255),
    model_id VARCHAR(255),
    provider_name VARCHAR(255),
    provider_id VARCHAR(255) REFERENCES providers(id) ON DELETE SET NULL,
    config_source VARCHAR(50),
    -- LLM error tracking (migration 024)
    llm_error_type VARCHAR(100),
    llm_error_message TEXT,
    llm_error_occurred_at TIMESTAMPTZ,
    CONSTRAINT agent_runs_status_check CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')
    )
);
```

#### idempotency_keys Table

```sql
CREATE TABLE idempotency_keys (
    key VARCHAR(255) PRIMARY KEY,
    owner_user_id VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    path VARCHAR(500) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    response_hash VARCHAR(64) NOT NULL,
    response_body TEXT,
    status_code VARCHAR(3) DEFAULT '200' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    replayed_at TIMESTAMPTZ
);
```

---

### 009: Add Last Step Seq

**File:** `009_add_last_step_seq_to_agent_sessions.py`

```sql
ALTER TABLE agent_sessions ADD COLUMN last_step_seq INTEGER;
```

---

### 010: Allow Message Step Type

**File:** `010_allow_message_step_type.py`

Modifies check constraint to allow 'message' type:

```sql
ALTER TABLE agent_steps DROP CONSTRAINT agent_steps_type_check;
ALTER TABLE agent_steps ADD CONSTRAINT agent_steps_type_check 
    CHECK (type IN ('message', 'user', 'assistant', 'tool', 'system', 'error'));
```

---

### 011: Builtin Process Tables

**File:** `011_create_builtin_process_tables.py`

Creates PostgreSQL ENUMs and process tracking tables:

```sql
CREATE TYPE manifeststatus AS ENUM ('staged', 'active', 'rolled_back', 'failed');
CREATE TYPE processevent AS ENUM ('start', 'heartbeat', 'stop', 'exit', 'signal');

CREATE TABLE builtin_manifest_activation_history (
    id UUID PRIMARY KEY,
    manifest_name VARCHAR(255) NOT NULL,
    version VARCHAR(100) NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL,
    activated_by TEXT,
    status manifeststatus NOT NULL,
    notes TEXT
);

CREATE TABLE builtin_process_events (
    id UUID PRIMARY KEY,
    process_id VARCHAR(255) NOT NULL,
    artifact VARCHAR(255) NOT NULL,
    pid INTEGER,
    port INTEGER,
    event processevent NOT NULL,
    reason TEXT,
    exit_code INTEGER,
    ts TIMESTAMPTZ NOT NULL,
    tenant_id VARCHAR(255),
    manifest_version VARCHAR(100),
    host VARCHAR(255)
);
```

---

### 012: Internal Ops Events

**File:** `012_create_internal_ops_events.py`

```sql
CREATE TABLE internal_ops_events (
    id BIGSERIAL PRIMARY KEY,
    kind VARCHAR(100) NOT NULL,
    sub VARCHAR(255) NOT NULL,
    enabled BOOLEAN,
    note TEXT,
    data_json JSONB,
    ts TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_internal_ops_events_kind_ts ON internal_ops_events (kind, ts);
CREATE INDEX idx_internal_ops_events_sub_ts ON internal_ops_events (sub, ts);
```

---

### 013: Add Steps Output to Agent Runs

**File:** `013_add_steps_output_to_agent_runs.py`

```sql
ALTER TABLE agent_runs ADD COLUMN steps JSONB DEFAULT '[]';
ALTER TABLE agent_runs ADD COLUMN output TEXT;
```

---

### 014: Rename Session Metadata

**File:** `014_rename_session_metadata_to_metadata.py`

```sql
ALTER TABLE agent_sessions RENAME COLUMN session_metadata TO metadata;
```

---

### 015: Add Todos/Warnings/Metrics

**File:** `015_add_todos_warnings_metrics_to_agent_runs.py`

```sql
ALTER TABLE agent_runs ADD COLUMN todos JSONB DEFAULT '[]';
ALTER TABLE agent_runs ADD COLUMN warnings JSONB DEFAULT '[]';
ALTER TABLE agent_runs ADD COLUMN metrics JSONB;

-- Convert output from TEXT to JSONB
ALTER TABLE agent_runs ALTER COLUMN output TYPE JSONB USING 
    CASE WHEN output IS NULL OR output = '' THEN NULL ELSE to_jsonb(output) END;
```

---

### 016: Add ID to Model Defaults

**File:** `016_add_id_to_model_defaults.py`

```sql
ALTER TABLE model_defaults DROP CONSTRAINT pk_model_defaults;
ALTER TABLE model_defaults ADD COLUMN id INTEGER NOT NULL;
ALTER TABLE model_defaults ADD CONSTRAINT pk_model_defaults PRIMARY KEY (id);
ALTER TABLE model_defaults ADD CONSTRAINT uq_model_defaults_scope_tenant 
    UNIQUE (scope, tenant_id);
```

---

### 017: Add Sequence to Model Defaults ID

**File:** `017_add_sequence_to_model_defaults_id.py`

```sql
CREATE SEQUENCE model_defaults_id_seq;
ALTER TABLE model_defaults ALTER COLUMN id SET DEFAULT nextval('model_defaults_id_seq');
ALTER SEQUENCE model_defaults_id_seq OWNED BY model_defaults.id;
```

---

### 018: Allow NULL Tenant ID

**File:** `018_allow_null_tenant_id_in_model_defaults.py`

```sql
ALTER TABLE model_defaults ALTER COLUMN tenant_id DROP NOT NULL;
```

---

### 019: Enforce Single Default Per Scope

**File:** `019_enforce_single_default_per_scope.py`

This is a complex migration that:

1. Adds 'user' to allowed scope values
2. Sanitizes duplicate default data (keeps most recent)
3. Creates partial unique indexes for constraint enforcement

```sql
-- Unique index for tenant-scoped defaults
CREATE UNIQUE INDEX uq_model_defaults_scope_tenant_not_null
    ON model_defaults (scope, tenant_id)
    WHERE tenant_id IS NOT NULL;

-- Unique index for global defaults (NULL tenant_id)
CREATE UNIQUE INDEX uq_model_defaults_scope_null_tenant
    ON model_defaults (scope)
    WHERE tenant_id IS NULL;
```

---

### 020: Add Request ID to Agent Runs

**File:** `020_add_request_id_to_agent_runs.py`

```sql
ALTER TABLE agent_runs ADD COLUMN request_id VARCHAR(255);
CREATE INDEX idx_agent_runs_request_id ON agent_runs (request_id);
```

---

### 021: Add Queued Status to Agent Runs

**File:** `021_add_queued_status_to_agent_runs.py`

Updates status constraint and default:

```sql
ALTER TABLE agent_runs DROP CONSTRAINT agent_runs_status_check;
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check 
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled'));
ALTER TABLE agent_runs ALTER COLUMN status SET DEFAULT 'queued';
```

---

### 022: Add Idempotency Status Code

**File:** `022_add_idempotency_status_code.py`

```sql
ALTER TABLE idempotency_keys ADD COLUMN status_code VARCHAR(3) NOT NULL DEFAULT '200';
```

---

### 023: Add Model Config to Agent Runs

**File:** `023_add_model_config_to_agent_runs.py`

Adds model configuration tracking:

```sql
ALTER TABLE agent_runs ADD COLUMN model_instance_name VARCHAR(255);
ALTER TABLE agent_runs ADD COLUMN model_id VARCHAR(255);
ALTER TABLE agent_runs ADD COLUMN provider_name VARCHAR(255);
ALTER TABLE agent_runs ADD COLUMN provider_id VARCHAR(255);
ALTER TABLE agent_runs ADD COLUMN config_source VARCHAR(50);

ALTER TABLE agent_runs ADD CONSTRAINT fk_agent_runs_provider_id 
    FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE SET NULL;

CREATE INDEX idx_agent_runs_provider_id ON agent_runs (provider_id);
CREATE INDEX idx_agent_runs_config_source ON agent_runs (config_source);
```

---

### 024: Add LLM Error Tracking

**File:** `024_add_llm_error_tracking_to_agent_runs.py`

Adds LLM error tracking columns:

```sql
ALTER TABLE agent_runs ADD COLUMN llm_error_type VARCHAR(100);
ALTER TABLE agent_runs ADD COLUMN llm_error_message TEXT;
ALTER TABLE agent_runs ADD COLUMN llm_error_occurred_at TIMESTAMPTZ;

CREATE INDEX idx_agent_runs_llm_error_type ON agent_runs (llm_error_type);
```

**Error Types:**
- `timeout`
- `context_length`
- `rate_limit`
- `connection`
- `validation`
- `unknown`

---

### 025: Add Metadata to Agent Runs

**File:** `025_add_metadata_to_agent_runs.py`

```sql
ALTER TABLE agent_runs ADD COLUMN metadata JSONB DEFAULT '{}' NOT NULL;
```

---

### 026: Add Agent Run Indexes

**File:** `026_add_agent_run_indexes.py`

Adds composite indexes for efficient listing queries:

```sql
CREATE INDEX idx_agent_runs_tenant_user_started 
    ON agent_runs (tenant_id, user_id, started_at);
CREATE INDEX idx_agent_runs_tenant_session_started 
    ON agent_runs (tenant_id, session_id, started_at);
CREATE INDEX idx_agent_runs_status_started 
    ON agent_runs (status, started_at);
```

---

## Schema Overview

### Entity Relationship Summary

```
tenants
├── tools (owner_tenant_id → tenants.id)
├── tool_invocations (tenant_id → tenants.id)
├── jobs (tenant_id → tenants.id)
├── agent_sessions (tenant_id → tenants.id)
└── agent_runs (tenant_id → tenants.id)

providers
├── provider_secrets (provider_id → providers.id)
├── provider_defaults (provider_id → providers.id)
├── model_instances (provider_id → providers.id)
└── agent_runs (provider_id → providers.id)

model_instances
├── model_instance_events (instance_id → model_instances.id)
├── model_defaults (instance_id → model_instances.id)
└── user_default_models (chat_instance_id → model_instances.id)

agent_sessions
├── agent_steps (session_id → agent_sessions.session_id)
├── agent_runs (session_id → agent_sessions.session_id)
└── last_step_id → agent_steps.step_id

builtins_manifests
├── builtins_activations (manifest_id → builtins_manifests.id)
└── builtins_manifest_audit (manifest_id → builtins_manifests.id)
```

---

## Table Reference

### Tables by Domain

#### Multi-tenancy
- `tenants` - Tenant organizations

#### Tools System
- `tools` - Tool definitions
- `tool_invocations` - Tool execution records
- `tool_audit_events` - Tool audit trail

#### Jobs System
- `jobs` - Async job records
- `job_events` - Job event stream

#### Provider Management
- `providers` - LLM provider registry
- `provider_secrets` - Encrypted API keys
- `provider_defaults` - Default provider settings
- `provider_audit_events` - Provider audit trail

#### Model Management
- `builtins_manifests` - Model manifest definitions
- `builtins_activations` - Manifest activation history
- `builtins_staging_jobs` - Staging idempotency
- `builtins_manifest_audit` - Manifest audit trail
- `model_instances` - Runtime model instances
- `model_instance_events` - Instance event log
- `model_defaults` - Global/tenant defaults
- `user_default_models` - Per-user defaults

#### Agent System
- `agent_sessions` - Conversation sessions
- `agent_steps` - Individual steps
- `agent_runs` - Execution runs
- `idempotency_keys` - Request idempotency

#### Process Tracking
- `builtin_manifest_activation_history` - Activation history
- `builtin_process_events` - Process lifecycle events

#### Audit & Operations
- `internal_ops_events` - Internal operations audit

---

## Triggers & Functions

### update_updated_at_column()

Used by: `tenants`, `tools`

```sql
CREATE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### update_jobs_updated_at()

Used by: `jobs`

```sql
CREATE FUNCTION update_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### update_agent_sessions_updated_at()

Used by: `agent_sessions`

```sql
CREATE FUNCTION update_agent_sessions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

## Running Migrations

### Basic Commands

```bash
# Show current revision
alembic current

# Show migration history
alembic history --verbose

# Upgrade to latest
alembic upgrade head

# Upgrade one step
alembic upgrade +1

# Upgrade to specific revision
alembic upgrade 008

# Downgrade one step
alembic downgrade -1

# Downgrade to specific revision
alembic downgrade 005

# Generate new migration (autogenerate)
alembic revision --autogenerate -m "description"

# Generate empty migration
alembic revision -m "description"

# Show SQL without executing
alembic upgrade head --sql
```

### Environment Setup

```bash
# Set database URL
export DATABASE_URL="postgresql://user:pass@localhost/dbname"

# Or in .env file
DATABASE_URL=postgresql://user:pass@localhost/dbname
```

### Production Deployment

```bash
# Generate SQL migration script
alembic upgrade head --sql > migration.sql

# Review and apply
psql -f migration.sql

# Or apply directly (with backup first)
pg_dump -Fc dbname > backup.dump
alembic upgrade head
```

---

## Rollback Procedures

### Safe Rollback Steps

1. **Backup first**:
   ```bash
   pg_dump -Fc database_name > backup_$(date +%Y%m%d_%H%M%S).dump
   ```

2. **Check current revision**:
   ```bash
   alembic current
   ```

3. **Downgrade**:
   ```bash
   alembic downgrade -1
   ```

4. **Verify**:
   ```bash
   alembic current
   \dt  # List tables in psql
   ```

### Emergency Rollback

```bash
# Restore from backup
pg_restore -c -d database_name backup.dump
```

---

## Best Practices

### Migration Development

1. **Always provide downgrade**: Every `upgrade()` should have a matching `downgrade()`
2. **Test both directions**: Run upgrade, then downgrade, then upgrade again
3. **Use transactions**: Alembic wraps migrations in transactions by default
4. **Handle data carefully**: Use `op.execute()` for data migrations
5. **Document changes**: Use docstrings to explain the purpose

### Naming Conventions

```
{3-digit-number}_{description}.py

Examples:
001_initial_tenants_table.py
015_add_todos_warnings_metrics_to_agent_runs.py
```

### Check Constraints

```python
# Add check constraint
op.create_check_constraint(
    'constraint_name',
    'table_name',
    "column IN ('value1', 'value2')"
)

# Drop check constraint
op.drop_constraint('constraint_name', 'table_name', type_='check')
```

### Partial Indexes

```python
# Create partial index
op.create_index(
    'index_name',
    'table_name',
    ['column'],
    unique=True,
    postgresql_where=sa.text('column IS NOT NULL')
)
```

---

## Troubleshooting

### Common Issues

#### "Target database is not up to date"

```bash
# Check current revision
alembic current

# Show pending migrations
alembic history --indicate-current

# Apply pending
alembic upgrade head
```

#### "Relation already exists"

Use `IF NOT EXISTS` in raw SQL:

```python
op.execute("CREATE TABLE IF NOT EXISTS ...")
op.execute("CREATE INDEX IF NOT EXISTS ...")
```

#### "Column does not exist" during downgrade

Check column additions in previous migrations:

```python
def downgrade():
    # Only drop if exists
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [c['name'] for c in inspector.get_columns('table_name')]
    if 'column_name' in columns:
        op.drop_column('table_name', 'column_name')
```

#### Foreign key constraint violations

Drop/recreate in correct order:

```python
# Downgrade: drop child table first
op.drop_table('child_table')
op.drop_table('parent_table')

# Upgrade: create parent first
op.create_table('parent_table', ...)
op.create_table('child_table', ...)
```

---

## Related Documentation

- **PostgreSQL Control**: `db/postgres_control/README.md`
- **Redis Cache**: `db/redis_cache/README.md`
- **Memgraph Domain**: `db/memgraph_domain/README.md`
- **SQLAlchemy Models**: `db/postgres_control/models/`

---

## License

This module is part of the Cineca Agentic Platform and follows the project's licensing terms.
