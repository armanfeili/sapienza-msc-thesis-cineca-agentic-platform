# PostgreSQL Control Module

This module provides the **relational database infrastructure** for the Cineca Agentic Platform, using PostgreSQL as the authoritative data store for tenants, jobs, agents, providers, model instances, tools, and audit logs.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Database Connection](#database-connection)
- [Alembic Migrations](#alembic-migrations)
  - [Migration History](#migration-history)
  - [Running Migrations](#running-migrations)
  - [Creating New Migrations](#creating-new-migrations)
- [ORM Models](#orm-models)
  - [Core Models](#core-models)
  - [Agent Models](#agent-models)
  - [Provider Models](#provider-models)
  - [Job Models](#job-models)
  - [Tool Models](#tool-models)
  - [Audit Models](#audit-models)
- [Repositories](#repositories)
  - [Repository Pattern](#repository-pattern)
  - [Tenants Repository](#tenants-repository)
  - [Jobs Repository](#jobs-repository)
  - [Agents Repository](#agents-repository)
  - [Provider Repository](#provider-repository)
  - [User Default Models Repository](#user-default-models-repository)
- [Schema Reference](#schema-reference)
- [Usage Examples](#usage-examples)
- [FastAPI Integration](#fastapi-integration)
- [Data Seeding](#data-seeding)
- [Caching Strategy](#caching-strategy)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [API Reference](#api-reference)

---

## Overview

The `postgres_control` module serves as the primary persistence layer for the Cineca Agentic Platform, providing:

- **SQLAlchemy ORM Models**: Type-safe Python classes mapped to PostgreSQL tables
- **Alembic Migrations**: Version-controlled database schema evolution (26+ migrations)
- **Repository Pattern**: Clean data access layer with pagination, filtering, and caching
- **Connection Pooling**: Production-ready QueuePool with pre-ping and timeouts
- **Multi-Tenancy**: Full tenant isolation with RBAC support
- **Audit Logging**: Append-only event tables for compliance
- **Redis Caching**: Two-tier architecture with PostgreSQL as source of truth

### Key Features

| Feature | Implementation |
|---------|---------------|
| **Schema Management** | Alembic with 26 versioned migrations |
| **Connection Pooling** | SQLAlchemy QueuePool (configurable size) |
| **Optimistic Locking** | Version columns with auto-increment triggers |
| **Keyset Pagination** | Cursor-based pagination with ETags |
| **Secret Encryption** | Fernet-encrypted API keys in separate table |
| **Audit Trail** | Append-only event tables per domain |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Cineca Agentic Platform                          │
├──────────────────────────────────────────────────────────────────────────┤
│  FastAPI Application (src/)                                              │
│       ↓ Depends(get_db)                                                  │
│  db.postgres_control.repositories                                        │
│       ├── TenantsRepository    → tenants table                           │
│       ├── JobsRepository       → jobs, job_events tables                 │
│       ├── AgentSessionRepo     → agent_sessions, agent_steps, agent_runs │
│       ├── ProviderRepository   → providers, provider_secrets             │
│       └── UserDefaultModelRepo → user_default_models, model_defaults     │
│       ↓                                                                  │
│  db.postgres_control.models (SQLAlchemy ORM)                             │
│       ↓                                                                  │
│  db.postgres_control.database (Engine, SessionLocal)                     │
│       ↓                                                                  │
│  PostgreSQL Database (port 5432)                                         │
│       ├── Connection Pool (QueuePool)                                    │
│       ├── Statement Timeout (30s)                                        │
│       └── SSL Mode (configurable)                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
db/postgres_control/
├── __init__.py              # Package exports
├── database.py              # Engine, session factory, health check
├── alembic.ini              # Alembic configuration
├── init.sql                 # PostgreSQL initialization script
├── seed_tenants.py          # Demo tenant data seeder
├── alembic/                 # Migration framework
│   ├── env.py               # Migration environment configuration
│   ├── script.py.mako       # Migration template
│   └── versions/            # Migration scripts (001-026)
│       ├── 001_initial_tenants_table.py
│       ├── 002_create_tools_tables.py
│       ├── 003_create_jobs_tables.py
│       ├── 004_create_providers_tables.py
│       ├── 005_create_builtins_manifests_tables.py
│       ├── 006_create_model_instances_tables.py
│       ├── 007_user_default_models.py
│       ├── 008_create_agent_tables.py
│       ├── 009_add_last_step_seq_to_agent_sessions.py
│       ├── 010_allow_message_step_type.py
│       ├── 011_create_builtin_process_tables.py
│       ├── 012_create_internal_ops_events.py
│       ├── 013_add_steps_output_to_agent_runs.py
│       ├── 014_rename_session_metadata_to_metadata.py
│       ├── 015_add_todos_warnings_metrics_to_agent_runs.py
│       ├── 016_add_id_to_model_defaults.py
│       ├── 017_add_sequence_to_model_defaults_id.py
│       ├── 018_allow_null_tenant_id_in_model_defaults.py
│       ├── 019_enforce_single_default_per_scope.py
│       ├── 020_add_request_id_to_agent_runs.py
│       ├── 021_add_queued_status_to_agent_runs.py
│       ├── 022_add_idempotency_status_code.py
│       ├── 023_add_model_config_to_agent_runs.py
│       ├── 024_add_llm_error_tracking_to_agent_runs.py
│       ├── 025_add_metadata_to_agent_runs.py
│       └── 026_add_agent_run_indexes.py
├── models/                  # SQLAlchemy ORM models
│   ├── __init__.py          # Model exports
│   ├── tenant.py            # Tenant model
│   ├── job.py               # Job model
│   ├── job_event.py         # Job event model
│   ├── provider.py          # Provider, ProviderSecret, ProviderDefault
│   ├── model_instance.py    # ModelInstance, ModelInstanceEvent, ModelDefault
│   ├── user_default_model.py # UserDefaultModel
│   ├── tool.py              # Tool model
│   ├── tool_invocation.py   # ToolInvocation model
│   ├── tool_audit_event.py  # ToolAuditEvent model
│   ├── agent_session.py     # AgentSession model
│   ├── agent_step.py        # AgentStep model
│   ├── agent_run.py         # AgentRun model
│   ├── manifest.py          # Manifest models
│   ├── builtin_process.py   # BuiltinProcessEvent, ManifestActivationHistory
│   ├── idempotency_key.py   # IdempotencyKey model
│   ├── internal_ops_event.py # InternalOpsEvent model
│   └── audit_log.py         # AuditLog model
└── repositories/            # Data access layer
    ├── __init__.py          # Repository exports
    ├── tenants.py           # TenantsRepository
    ├── jobs.py              # JobsRepository
    ├── agents.py            # AgentSessionRepository, AgentStepRepository, etc.
    ├── provider_repo.py     # ProviderRepository with Redis caching
    ├── model_instance_repo.py # ModelInstanceRepository
    ├── manifest_repo.py     # ManifestRepository
    ├── tools.py             # ToolsRepository
    ├── user_default_models.py # UserDefaultModelRepo
    └── user_default_models_old.py # Legacy repository (deprecated)
```

---

## Installation & Setup

### Prerequisites

- **Python 3.11+**
- **PostgreSQL 14+** with extensions:
  - `uuid-ossp` - UUID generation
  - `pgcrypto` - Cryptographic functions

### Python Dependencies

```bash
pip install sqlalchemy psycopg2-binary alembic pydantic-settings cryptography
```

Or install from the project's requirements:

```bash
pip install -r requirements.txt
```

### Database Creation

```bash
# Create database and user
psql -U postgres << EOF
CREATE DATABASE cineca_platform;
CREATE USER cineca_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE cineca_platform TO cineca_user;
EOF

# Run initialization script
psql -U cineca_user -d cineca_platform -f db/postgres_control/init.sql
```

### Environment Variables

```bash
# Database connection
DB_HOST=localhost
DB_PORT=5432
DB_NAME=cineca_platform
DB_USER=cineca_user
DB_PASS=your_secure_password

# Connection pool settings
DB_POOL_SIZE=5
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600
DB_POOL_PRE_PING=true
DB_ECHO=false

# SSL mode
DB_SSLMODE=prefer  # Options: disable, allow, prefer, require, verify-ca, verify-full

# Application environment
APP_ENV=development  # test uses NullPool instead of QueuePool
```

---

## Configuration

### Database URL

The module constructs the database URL from settings:

```python
# Format: postgresql://user:password@host:port/database
settings.database_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
```

### Connection Pool Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `DB_POOL_SIZE` | 5 | Base connection pool size |
| `DB_POOL_TIMEOUT` | 30 | Wait timeout for connection |
| `DB_POOL_RECYCLE` | 3600 | Connection lifetime (seconds) |
| `DB_POOL_PRE_PING` | true | Test connections before use |
| `DB_ECHO` | false | Log all SQL statements |

### Pool Types

| Environment | Pool Type | Behavior |
|-------------|-----------|----------|
| `APP_ENV=test` | `NullPool` | No pooling, new connection per request |
| `APP_ENV=*` | `QueuePool` | Connection pooling with overflow |

---

## Database Connection

### `database.py`

The database module provides engine creation, session management, and health checking:

```python
"""PostgreSQL database engine and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Declarative base for all ORM models
Base = declarative_base()

# Engine with connection pooling
engine = create_db_engine()

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # Prevent lazy loading issues
)
```

### Session Dependency (FastAPI)

```python
from db.postgres_control.database import get_db
from sqlalchemy.orm import Session

@router.get("/items")
def list_items(db: Session = Depends(get_db)):
    return db.query(Item).all()
```

### Context Manager (Non-FastAPI)

```python
from db.postgres_control.database import get_db_context

with get_db_context() as db:
    items = db.query(Item).all()
    # Session auto-closes after block
```

### Health Check

```python
from db.postgres_control.database import check_db_health

is_healthy, error_msg = check_db_health()
if not is_healthy:
    logger.error(f"Database unhealthy: {error_msg}")
```

### Slow Query Logging

The engine automatically logs queries taking longer than 200ms:

```python
@event.listens_for(engine, "after_cursor_execute")
def log_slow_query(conn, cursor, statement, params, context, executemany):
    if execution_time > 0.2:  # 200ms
        logger.warning(f"Slow query: {statement[:200]}...")
```

---

## Alembic Migrations

### Migration Framework

Alembic manages database schema versions with:

- **Sequential revision IDs** (001, 002, ..., 026)
- **Upgrade/Downgrade functions** for each migration
- **Automatic timestamp tracking** per migration

### Migration History

| Revision | Description | Tables/Changes |
|----------|-------------|----------------|
| 001 | Initial tenants | `tenants` table with constraints |
| 002 | Tools tables | `tools`, `tool_invocations`, `tool_audit_events` |
| 003 | Jobs tables | `jobs`, `job_events` |
| 004 | Providers tables | `providers`, `provider_secrets`, `provider_defaults`, `provider_audit_events` |
| 005 | Builtins manifests | `builtins_manifests`, `builtins_activations`, `builtins_staging_jobs` |
| 006 | Model instances | `model_instances`, `model_instance_events`, `model_defaults` |
| 007 | User default models | `user_default_models` table |
| 008 | Agent tables | `agent_sessions`, `agent_steps`, `agent_runs`, `idempotency_keys` |
| 009 | Session step seq | Add `last_step_seq` to sessions |
| 010 | Message step type | Allow `message` as step type |
| 011 | Builtin processes | `builtin_process_events`, `builtin_manifest_activation_history` |
| 012 | Internal ops events | `internal_ops_events` audit table |
| 013 | Steps output | Add `steps`, `output` to agent_runs |
| 014 | Rename metadata | Column rename in sessions |
| 015 | Todos/warnings/metrics | JSONB columns on agent_runs |
| 016-019 | Model defaults fixes | ID, sequence, null handling, uniqueness |
| 020 | Request ID | Add `request_id` to agent_runs |
| 021 | Queued status | Allow `queued` in agent_runs status |
| 022 | Idempotency status | Add `status_code` to idempotency_keys |
| 023 | Model config | Add model config columns to agent_runs |
| 024 | LLM error tracking | Add error tracking columns |
| 025 | Run metadata | Add `metadata` JSONB to agent_runs |
| 026 | Agent run indexes | Composite indexes for performance |

### Running Migrations

```bash
# Navigate to postgres_control directory
cd db/postgres_control

# Check current revision
alembic current

# Show migration history
alembic history

# Upgrade to latest
alembic upgrade head

# Upgrade to specific revision
alembic upgrade 008

# Downgrade one revision
alembic downgrade -1

# Downgrade to specific revision
alembic downgrade 005
```

### Creating New Migrations

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "add_new_column"

# Create empty migration
alembic revision -m "custom_migration"
```

### Migration Template

New migrations use `script.py.mako`:

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}

def upgrade() -> None:
    """Apply migration."""
    ${upgrades if upgrades else "pass"}

def downgrade() -> None:
    """Revert migration."""
    ${downgrades if downgrades else "pass"}
```

---

## ORM Models

### Core Models

#### Tenant

Multi-tenant organization with metadata:

```python
class Tenant(Base):
    __tablename__ = "tenants"
    
    id: Mapped[str]              # "tenant-abc123"
    name: Mapped[str]            # "ACME Corporation"
    admin_email: Mapped[str]     # "admin@acme.com"
    metadata_: Mapped[dict]      # JSONB: {"region": "us-east-1", "tier": "premium"}
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    version: Mapped[int]         # Optimistic locking
```

### Agent Models

#### AgentSession

Stateful agent conversation:

```python
class AgentSession(Base):
    __tablename__ = "agent_sessions"
    
    session_id: UUID
    user_id: str
    tenant_id: str  # FK to tenants
    status: str     # "active", "completed", "cancelled", "failed"
    
    # Configuration
    manager: str
    temperature: float = 0.2
    max_steps: int = 8
    tools: list[str]  # JSONB
    
    # Tracking
    session_metadata: dict  # JSONB
    last_step_id: UUID
    last_step_seq: int
    etag: str
```

#### AgentStep

Individual step in a session:

```python
class AgentStep(Base):
    __tablename__ = "agent_steps"
    
    step_id: UUID
    session_id: UUID  # FK
    seq: int          # Sequence number
    type: str         # "user", "assistant", "tool", "system", "error"
    message: str
    tool: str
    input: dict       # JSONB
    output: dict      # JSONB
    status: str       # "queued", "running", "completed", "failed", "cancelled"
```

#### AgentRun

Single agent execution:

```python
class AgentRun(Base):
    __tablename__ = "agent_runs"
    
    run_id: UUID
    session_id: UUID  # Optional FK
    user_id: str
    tenant_id: str
    
    # Model config
    model_instance_name: str
    model_id: str
    provider_name: str
    provider_id: str  # FK
    
    # Performance
    latency_ms: int
    trace_id: str
    request_id: str
    
    # Status
    status: str  # "queued", "running", "succeeded", "failed", "cancelled"
    
    # LLM error tracking
    llm_error_type: str     # "timeout", "rate_limit", "context_length", etc.
    llm_error_message: str
    llm_error_occurred_at: datetime
    
    # Execution data (JSONB)
    todos: list
    steps: list
    output: dict
    warnings: list
    metrics: dict
    run_metadata: dict
```

### Provider Models

#### Provider

LLM provider configuration:

```python
class Provider(Base):
    __tablename__ = "providers"
    
    id: str           # "ollama-local"
    name: str         # "Local Ollama"
    type: str         # "openai_compatible"
    base_url: str     # "http://localhost:11434/v1"
    model: str        # Default model
    tenant_id: str    # Null for global
    config_json: dict # Provider-specific config
    has_api_key: bool # Whether secret is set
```

#### ProviderSecret

Encrypted API keys (separate table):

```python
class ProviderSecret(Base):
    __tablename__ = "provider_secrets"
    
    provider_id: str        # FK to providers
    api_key_encrypted: str  # Fernet-encrypted
```

### Job Models

#### Job

Background task:

```python
class Job(Base):
    __tablename__ = "jobs"
    
    id: UUID
    type: str              # "demo", "export.data", "agent.run"
    status: str            # "queued", "running", "finished", "failed", "cancelled"
    owner_sub: str         # User subject
    tenant_id: str         # FK
    
    payload_json: dict     # Input parameters
    result_json: dict      # Output data
    error_json: dict       # Error details
    
    idempotency_key: str   # For duplicate prevention
    priority: int          # Higher = more urgent
    
    # Timestamps
    created_at: datetime
    started_at: datetime
    completed_at: datetime
    
    # Metrics
    queue_latency_ms: int
    exec_latency_ms: int
    etag: str
```

### Tool Models

#### Tool

MCP tool definition:

```python
class Tool(Base):
    __tablename__ = "tools"
    
    id: str               # UUID
    name: str             # "graph.query"
    version: str          # "1.0.0"
    description: str
    input_schema: dict    # JSON Schema
    output_schema: dict   # JSON Schema
    owner_tenant_id: str  # FK
    version_number: int   # Optimistic locking
```

### Audit Models

#### IdempotencyKey

Request replay prevention:

```python
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    
    key: str              # Client-provided key
    owner_user_id: str
    method: str           # HTTP method
    path: str             # Request path
    request_hash: str     # Request body hash
    response_hash: str    # Response body hash
    response_body: str    # Cached response
    status_code: str      # HTTP status code
    created_at: datetime
    replayed_at: datetime
```

---

## Repositories

### Repository Pattern

All repositories follow consistent patterns:

```python
class ExampleRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def create(...) -> Model:
        """Create with idempotency support."""
    
    def get_by_id(id) -> Model | None:
        """Retrieve by primary key."""
    
    def list(..., page_size, page_token) -> (list, next_token, total):
        """Paginated listing with cursor."""
    
    def update(...) -> Model:
        """Update with optimistic locking."""
    
    def delete(id) -> bool:
        """Soft or hard delete."""
```

### Tenants Repository

```python
from db.postgres_control.repositories import TenantsRepository

with get_db_context() as db:
    repo = TenantsRepository(db)
    
    # Create tenant (idempotent)
    tenant, created = repo.create(
        name="ACME Corp",
        admin_email="admin@acme.com",
        metadata={"tier": "premium"}
    )
    
    # List with pagination
    items, next_token, total = repo.list(page_size=20)
    
    # Get by ID
    tenant = repo.get_by_id("tenant-abc123")
    
    # Update metadata
    tenant = repo.update(
        tenant_id="tenant-abc123",
        name="ACME Corporation",
        metadata={"tier": "enterprise"}
    )
    
    # Delete (with dependency check)
    deleted = repo.delete("tenant-abc123")
```

### Jobs Repository

```python
from db.postgres_control.repositories.jobs import JobsRepository

with get_db_context() as db:
    repo = JobsRepository(db)
    
    # Create job
    job = repo.create_job(
        owner_sub="user@example.com",
        tenant_id="tenant-abc",
        type="demo",
        payload_json={"duration_ms": 5000},
        idempotency_key="my-unique-key"
    )
    
    # Get job
    job = repo.get_job(job_id)
    
    # Transition status
    job = repo.transition_status(
        job_id=job.id,
        from_status="queued",
        to_status="running",
        started_at=datetime.now(UTC)
    )
    
    # List with filters
    jobs, total, has_more = repo.list_jobs(
        owner_sub="user@example.com",
        status=["queued", "running"],
        limit=50
    )
    
    # Append event
    event = repo.append_event(
        job_id=job.id,
        event_type="progress",
        event_json={"percent": 50}
    )
```

### Agents Repository

```python
from db.postgres_control.repositories.agents import (
    AgentSessionRepository,
    AgentStepRepository,
    AgentRunRepository,
)

# Create session
session = AgentSessionRepository.create(
    db,
    user_id="auth0|123",
    tenant_id="tenant-abc",
    temperature=0.7,
    max_steps=10,
    tools=["graph.query", "web.search"]
)

# Add step
step = AgentStepRepository.create(
    db,
    session_id=session.session_id,
    type="user",
    message="What is the weather today?"
)

# Create run
run = AgentRunRepository.create(
    db,
    session_id=session.session_id,
    user_id="auth0|123",
    tenant_id="tenant-abc",
    model_instance_name="gpt-4"
)

# Update run status
AgentRunRepository.update_status(
    db,
    run_id=run.run_id,
    status="succeeded",
    output={"answer": "It's sunny!"}
)
```

### Provider Repository

```python
from db.postgres_control.repositories.provider_repo import (
    create_provider,
    get_provider_by_id,
    list_providers,
    update_provider,
    delete_provider,
)

# Create provider (with encrypted API key)
provider = create_provider(
    db,
    id="openai-main",
    name="OpenAI Production",
    type="openai_compatible",
    base_url="https://api.openai.com/v1",
    api_key="sk-xxx...",  # Encrypted before storage
    tenant_id=None,  # Global
    actor="admin@example.com"
)

# Get provider (API key never returned)
provider = get_provider_by_id(db, "openai-main")
# provider["has_api_key"] = True, but no api_key field

# List providers with pagination
providers, next_token, total = list_providers(
    db,
    tenant_id=None,  # Global only
    page_size=20
)

# Update provider
provider = update_provider(
    db,
    provider_id="openai-main",
    base_url="https://api.openai.com/v2",
    actor="admin@example.com"
)

# Delete provider
delete_provider(db, "openai-main", actor="admin@example.com")
```

### User Default Models Repository

```python
from db.postgres_control.repositories.user_default_models import user_default_repo

# Get user's default model
default = user_default_repo.get_user_default(
    user_id="auth0|123",
    tenant_id="acme-corp"
)

if default:
    print(f"Default model: {default['instance_name']}")

# Set user's default
result = user_default_repo.set_user_default(
    user_id="auth0|123",
    instance_id="6491b020-bbe3-47fe-991e-e7c21a15260c",
    tenant_id="acme-corp",
    created_by="auth0|123"
)

# Delete user's default
user_default_repo.delete_user_default(
    user_id="auth0|123",
    tenant_id="acme-corp"
)
```

---

## Schema Reference

### Tables Overview

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `tenants` | Multi-tenant organizations | id, name, admin_email, metadata |
| `tools` | MCP tool definitions | id, name, version, input_schema |
| `tool_invocations` | Tool execution records | eid, tool_name, status, params_json |
| `tool_audit_events` | Tool usage audit | id, tool_id, action, actor |
| `jobs` | Background tasks | id, type, status, owner_sub, payload_json |
| `job_events` | Job lifecycle events | seq_id, job_id, event_type, event_json |
| `providers` | LLM provider config | id, name, type, base_url, tenant_id |
| `provider_secrets` | Encrypted API keys | provider_id, api_key_encrypted |
| `provider_defaults` | Default provider per scope | id, scope, tenant_id, provider_id |
| `provider_audit_events` | Provider change audit | id, action, provider_id, actor |
| `builtins_manifests` | Model manifest registry | id, source_url, content_json, state |
| `builtins_activations` | Manifest activation history | id, manifest_id, activated_at, activated_by |
| `model_instances` | Loaded model instances | id, instance_name, provider_id, model_id |
| `model_instance_events` | Instance lifecycle events | seq_id, instance_id, event_type |
| `model_defaults` | Default model per scope | id, scope, tenant_id, instance_id |
| `user_default_models` | Per-user model preferences | id, user_id, tenant_id, chat_instance_id |
| `agent_sessions` | Stateful agent conversations | session_id, user_id, status, tools |
| `agent_steps` | Session steps | step_id, session_id, seq, type, message |
| `agent_runs` | Agent execution records | run_id, session_id, status, metrics |
| `idempotency_keys` | Request deduplication | key, owner_user_id, response_body |
| `builtin_process_events` | Process lifecycle events | id, process_id, event, artifact |
| `builtin_manifest_activation_history` | Manifest status history | id, manifest_name, status |
| `internal_ops_events` | Internal operations audit | id, kind, sub, data_json |

### Indexes

Key indexes for query performance:

```sql
-- Tenants
ix_tenants_name_lower_unique      -- UNIQUE LOWER(name)
ix_tenants_admin_email_lower      -- LOWER(admin_email)
ix_tenants_created_at_desc        -- created_at DESC

-- Jobs
idx_jobs_idempotency_unique       -- (owner_sub, idempotency_key) WHERE key IS NOT NULL
idx_jobs_owner_created            -- (owner_sub, created_at DESC)
idx_jobs_status_created           -- (status, created_at DESC)
idx_jobs_tenant_created           -- (tenant_id, created_at DESC)

-- Agent Runs
idx_agent_runs_tenant_user_started    -- (tenant_id, user_id, started_at)
idx_agent_runs_tenant_session_started -- (tenant_id, session_id, started_at)
idx_agent_runs_status_started         -- (status, started_at)

-- Providers
ix_provider_tenant_id             -- tenant_id
uq_provider_tenant_name           -- UNIQUE (tenant_id, name)
```

### Check Constraints

```sql
-- Jobs
jobs_status_check: status IN ('queued', 'running', 'finished', 'failed', 'cancelled')

-- Agent Sessions
agent_sessions_status_check: status IN ('active', 'completed', 'cancelled', 'failed')

-- Agent Steps
agent_steps_status_check: status IN ('queued', 'running', 'completed', 'failed', 'cancelled')
agent_steps_type_check: type IN ('user', 'assistant', 'tool', 'system', 'error', 'message')

-- Agent Runs
agent_runs_status_check: status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')

-- Model Defaults
ck_model_defaults_scope: scope IN ('global', 'tenant')
ck_model_defaults_scope_tenant: (scope='global' AND tenant_id IS NULL) OR (scope='tenant' AND tenant_id IS NOT NULL)
```

### Triggers

```sql
-- Auto-update updated_at and version on tenants
CREATE TRIGGER update_tenants_updated_at
BEFORE UPDATE ON tenants
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Auto-update updated_at on jobs
CREATE TRIGGER jobs_updated_at_trigger
BEFORE UPDATE ON jobs
FOR EACH ROW
EXECUTE FUNCTION update_jobs_updated_at();

-- Auto-update updated_at on agent_sessions
CREATE TRIGGER agent_sessions_updated_at_trigger
BEFORE UPDATE ON agent_sessions
FOR EACH ROW
EXECUTE FUNCTION update_agent_sessions_updated_at();
```

---

## Usage Examples

### Complete Job Workflow

```python
from db.postgres_control.database import get_db_context
from db.postgres_control.repositories.jobs import JobsRepository
from datetime import UTC, datetime

with get_db_context() as db:
    repo = JobsRepository(db)
    
    # 1. Create job
    job = repo.create_job(
        owner_sub="user@example.com",
        tenant_id="tenant-abc",
        type="export.data",
        payload_json={"format": "csv", "tables": ["users", "orders"]},
        idempotency_key="export-2025-01-15"
    )
    db.commit()
    print(f"Created job: {job.id}")
    
    # 2. Start job
    job = repo.transition_status(
        job_id=job.id,
        from_status="queued",
        to_status="running",
        started_at=datetime.now(UTC)
    )
    db.commit()
    
    # 3. Complete job
    job = repo.transition_status(
        job_id=job.id,
        from_status="running",
        to_status="finished",
        completed_at=datetime.now(UTC),
        result_json={"file_url": "s3://bucket/export.csv"}
    )
    db.commit()
```

### Agent Session with Steps

```python
from db.postgres_control.repositories.agents import (
    AgentSessionRepository,
    AgentStepRepository,
)

with get_db_context() as db:
    # Create session
    session = AgentSessionRepository.create(
        db,
        user_id="auth0|123",
        tenant_id="acme-corp",
        tools=["graph.query"],
        temperature=0.5
    )
    
    # Add user message
    step1 = AgentStepRepository.create(
        db,
        session_id=session.session_id,
        type="user",
        message="List all users in the database"
    )
    
    # Add assistant response
    step2 = AgentStepRepository.create(
        db,
        session_id=session.session_id,
        type="assistant",
        message="I'll query the database for you.",
        tool="graph.query",
        input={"cypher": "MATCH (u:User) RETURN u.name LIMIT 10"}
    )
    
    db.commit()
```

---

## FastAPI Integration

### Dependency Injection

```python
from fastapi import Depends
from sqlalchemy.orm import Session
from db.postgres_control.database import get_db

@router.get("/tenants")
async def list_tenants(db: Session = Depends(get_db)):
    repo = TenantsRepository(db)
    items, _, _ = repo.list()
    return {"items": [t.to_dict() for t in items]}
```

### Transaction Management

```python
@router.post("/tenants")
async def create_tenant(
    data: CreateTenantRequest,
    db: Session = Depends(get_db)
):
    repo = TenantsRepository(db)
    try:
        tenant, created = repo.create(
            name=data.name,
            admin_email=data.admin_email
        )
        db.commit()
        return {"id": tenant.id, "created": created}
    except Exception:
        db.rollback()
        raise
```

---

## Data Seeding

### Demo Tenants

```bash
# Run the seeder script
python db/postgres_control/seed_tenants.py
```

Script creates demo tenants:

```python
demo_tenants = [
    {
        "name": "Admin Root Tenant",
        "admin_email": "admin@cineca.platform",
        "metadata": {"role": "system", "tier": "admin"}
    },
    {
        "name": "ACME Corporation",
        "admin_email": "admin@acme.com",
        "metadata": {"region": "us-east-1", "tier": "premium"}
    },
    {
        "name": "Beta Test Tenant",
        "admin_email": "beta@example.com",
        "metadata": {"tier": "standard", "pilot_program": True}
    },
    {
        "name": "Research Lab",
        "admin_email": "lab@university.edu",
        "metadata": {"tier": "academic", "department": "AI Research"}
    },
]
```

Output:

```
🌱 Seeding demo tenants into PostgreSQL...
  ✅ Created: Admin Root Tenant (ID: tenant-a1b2c3d4)
  ✅ Created: ACME Corporation (ID: tenant-e5f6g7h8)
  ♻️  Exists:  Beta Test Tenant (ID: tenant-i9j0k1l2)
  ✅ Created: Research Lab (ID: tenant-m3n4o5p6)

📊 Summary:
  • Created: 3
  • Already existed: 1
  • Total: 4

✨ Seeding complete!
```

---

## Caching Strategy

### Two-Tier Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   FastAPI   │ ──► │    Redis    │ ──► │ PostgreSQL  │
│  Application│     │  (Cache)    │     │  (Source)   │
└─────────────┘     └─────────────┘     └─────────────┘
                     TTL: 60-600s        Authoritative
```

### Cache Invalidation

On every write:
1. Write to PostgreSQL first
2. Invalidate related Redis keys
3. Return success

### Redis Key Patterns

```
providers:by_id:{id}        # Single provider (TTL: 5min)
providers:list:{size}:{token} # List page (TTL: 1min)
providers:default:{scope}   # Default provider (TTL: 10min)
providers:health:{id}       # Health status (TTL: 1hr)
```

---

## Security

### API Key Encryption

API keys are encrypted using Fernet symmetric encryption:

```python
from cryptography.fernet import Fernet

# Keys stored in provider_secrets table
# Never returned in API responses
# has_api_key boolean indicator provided instead
```

Configuration:

```bash
PROVIDER_SECRET_KEY=your-32-byte-base64-key
```

### Secret Redaction

The repository automatically redacts sensitive data in API responses:

```python
# Redacted in responses:
- api_key → None
- config.headers.authorization → "***"
- config.auth.token → "***"
```

### SQL Injection Prevention

All queries use parameterized statements via SQLAlchemy ORM:

```python
# Safe - parameterized
db.query(Tenant).filter(Tenant.id == tenant_id).first()

# Never - string formatting
# db.execute(f"SELECT * FROM tenants WHERE id = '{tenant_id}'")
```

---

## Troubleshooting

### Connection Issues

**Error**: `connection refused to localhost:5432`

```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Verify credentials
psql -U cineca_user -h localhost -d cineca_platform -c "SELECT 1"
```

**Error**: `too many connections`

```bash
# Reduce pool size
export DB_POOL_SIZE=3

# Or increase PostgreSQL max_connections
# In postgresql.conf: max_connections = 200
```

### Migration Issues

**Error**: `Target database is not up to date`

```bash
# Check current revision
alembic current

# Show pending migrations
alembic history --indicate-current

# Apply pending migrations
alembic upgrade head
```

**Error**: `relation already exists`

```bash
# Mark migration as complete without running
alembic stamp 008

# Then upgrade from there
alembic upgrade head
```

### Performance Issues

**Slow queries**:

```sql
-- Check slow query log (set log_min_duration_statement)
SET log_min_duration_statement = 200;

-- Analyze query plans
EXPLAIN ANALYZE SELECT * FROM jobs WHERE status = 'queued';

-- Check missing indexes
SELECT * FROM pg_stat_user_tables 
WHERE seq_scan > idx_scan AND n_live_tup > 10000;
```

---

## API Reference

### Database Module

```python
# Engine and session
from db.postgres_control.database import (
    Base,           # SQLAlchemy declarative base
    engine,         # Global engine instance
    SessionLocal,   # Session factory
    get_db,         # FastAPI dependency
    get_db_context, # Context manager
    check_db_health # Health check function
)
```

### Models

```python
from db.postgres_control.models import (
    # Core
    Tenant,
    Base,
    
    # Agents
    AgentSession,
    AgentStep,
    AgentRun,
    
    # Jobs
    Job,
    JobEvent,
    
    # Providers
    Provider,
    ProviderSecret,
    ProviderDefault,
    ProviderAuditEvent,
    
    # Models
    ModelInstance,
    ModelInstanceEvent,
    ModelDefault,
    UserDefaultModel,
    
    # Tools
    Tool,
    ToolInvocation,
    ToolAuditEvent,
    
    # Audit
    IdempotencyKey,
    InternalOpsEvent,
    AuditLog,
    
    # Builtins
    BuiltinProcessEvent,
    BuiltinManifestActivationHistory,
    ManifestStatus,
    ProcessEvent,
)
```

### Repositories

```python
from db.postgres_control.repositories import (
    TenantsRepository,
    ToolsRepository,
    user_default_repo,
)

from db.postgres_control.repositories.jobs import JobsRepository
from db.postgres_control.repositories.agents import (
    AgentSessionRepository,
    AgentStepRepository,
    AgentRunRepository,
    IdempotencyKeyRepository,
)
from db.postgres_control.repositories.provider_repo import (
    create_provider,
    get_provider_by_id,
    list_providers,
    update_provider,
    delete_provider,
)
```

---

## License

This module is part of the Cineca Agentic Platform. See the main project [LICENSE](../../LICENSE) for details.

---

## Contributing

1. Follow existing code patterns
2. Add Alembic migration for schema changes
3. Update tests for new functionality
4. Run migrations in test environment before merging

---

## Changelog

See the main project [CHANGELOG.md](../../CHANGELOG.md) for version history.
