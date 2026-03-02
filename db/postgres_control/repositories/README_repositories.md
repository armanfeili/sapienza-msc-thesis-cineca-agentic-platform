# PostgreSQL Control Repositories Documentation

## Overview

This directory contains repository classes that provide data access layer operations for the PostgreSQL control database. These repositories encapsulate database operations, caching, pagination, and business logic for each domain entity.

The repositories follow consistent patterns:
- **SQLAlchemy ORM**: All repositories use SQLAlchemy for type-safe database operations
- **Session Management**: Each method manages its own database session lifecycle
- **Caching**: Redis integration for performance optimization
- **Pagination**: Cursor-based pagination for large result sets
- **ETags**: HTTP caching support with computed ETags
- **Audit Trails**: Comprehensive audit logging for mutations
- **Idempotency**: Support for idempotent operations where applicable

## Repository Architecture

### Core Patterns

#### Session Management
```python
def some_method(self, ...):
    db: Session = next(get_db())
    try:
        # Database operations
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

#### Cursor Pagination
```python
def list_with_pagination(self, page_size=20, page_token=None):
    # Decode cursor (created_at|id format)
    # Apply WHERE clause for keyset pagination
    # Return (items, next_token)
```

#### ETag Computation
```python
@staticmethod
def compute_etag(entity) -> str:
    data = f"{entity.id}:{entity.updated_at.isoformat()}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]
```

#### Redis Caching
```python
# Try cache first
cached = cache_get_json(cache_key)
if cached:
    return cached

# Compute result
result = ...

# Cache result
cache_set_json(cache_key, result, ttl=TTL)
return result
```

## Repository Classes

### Agents Repository (`agents.py`)

Repository for agent sessions, steps, runs, and idempotency operations.

#### AgentSessionRepository

**Methods:**
- `create()`: Create new agent session with configuration
- `get_by_id()`: Retrieve session by UUID
- `get_by_id_and_owner()`: Get session with ownership validation
- `list_by_user()`: List user's sessions with cursor pagination
- `list_all()`: Admin view of all sessions
- `update_status()`: Update session status
- `update_last_step()`: Update last step reference
- `delete()`: Delete session (cascades to steps/runs)

**Features:**
- ETag computation for HTTP caching
- Cursor-based pagination (created_at DESC, session_id DESC)
- Ownership filtering for security

#### AgentStepRepository

**Methods:**
- `create()`: Create new step with structured data
- `get_by_id()`: Get step by UUID
- `get_by_session_and_seq()`: Get step by session + sequence
- `list_by_session()`: List steps for session (seq ASC)
- `update_status()`: Update step status and results

**Features:**
- Sequential step tracking within sessions
- JSONB storage for input/output data
- Status transitions (queued → running → completed/failed)

#### AgentRunRepository

**Methods:**
- `create()`: Create new run with model configuration
- `get_by_id()`: Get run by UUID
- `get_by_id_and_owner()`: Get run with ownership check
- `update_status()`: Update run status, metrics, and results
- `list_recent()`: List recent runs with filtering

**Features:**
- Model instance tracking (legacy + new fields)
- LLM error tracking (type, message, timestamp)
- Performance metrics (latency, LLM calls, tool calls)
- JSONB storage for todos, steps, output, warnings, metrics

#### IdempotencyRepository

**Methods:**
- `get_or_create()`: Get existing or create new idempotency key
- `mark_replayed()`: Mark key as replayed

**Features:**
- Request deduplication for POST operations
- Hash-based request fingerprinting
- Response caching for replay

### Jobs Repository (`jobs.py`)

Repository for asynchronous job management and event tracking.

#### JobsRepository

**Methods:**
- `create_job()`: Create new job in queued status
- `get_job()`: Retrieve job by ID
- `get_job_for_owner()`: Get job with ownership validation
- `find_by_idempotency()`: Find job by owner + idempotency key
- `list_jobs()`: List jobs with filtering and pagination
- `transition_status()`: Atomic status transition with events
- `append_event()`: Add event to job audit trail
- `get_events()`: Retrieve job events
- `update_job_result()` / `update_job_error()`: Update job results
- `touch_job()`: Update last modified timestamp
- `delete_job()`: Delete job and events

**Features:**
- Idempotency support for job creation
- Status transition validation (from_status check)
- Automatic latency computation (queue + execution time)
- Event-driven audit trail
- ETag computation for caching
- Priority-based job ordering

#### Job States
- `queued` → `running` → `finished`/`failed`/`cancelled`
- Terminal states: `finished`, `failed`, `cancelled`

### Manifest Repository (`manifest_repo.py`)

Repository for built-in model manifests with authoritative PostgreSQL storage and Redis caching.

#### Core Functions

**Stage Operations:**
- `stage_manifest()`: Stage new manifest with SHA256 content hashing
- Content-based idempotency (SHA256 uniqueness)
- State transition: staged

**Activation Operations:**
- `activate_latest_staged()`: Activate most recent staged manifest
- `rollback_to_previous()`: Rollback to previous active manifest
- Atomic state transitions with Redis locking
- Audit event logging

**Query Operations:**
- `list_builtins()`: List all manifests (active/staged/archived)
- `list_history()`: List activation history with pagination
- `get_active()`: Get currently active manifest

**Features:**
- **PostgreSQL Authoritative**: All writes go to Postgres first
- **Redis Caching**: Short TTL for performance
- **Content Hashing**: SHA256 for idempotency
- **State Machine**: staged → active → archived
- **Audit Trail**: Complete operation history
- **Activation Locks**: Prevent concurrent activations
- **Prometheus Metrics**: Staging, activation, rollback counters

#### State Transitions
```
staged → active (activate)
active → archived (new manifest activated)
active → archived (rollback to previous)
```

### Model Instance Repository (`model_instance_repo.py`)

Repository for model instance management with provider integration.

#### Core Functions

**CRUD Operations:**
- `list_instances()`: List instances with filtering and pagination
- `create_instance()`: Create new instance with validation
- `get_instance()`: Get instance by ID or name
- `delete_instance()`: Delete instance with audit events

**Default Management:**
- `get_default()`: Get default instance with precedence resolution
- `set_default()`: Set default instance for scope
- `record_test_event()`: Log instance testing events

**Features:**
- **Multi-tenancy**: tenant_id scoping (null = global)
- **Provider Integration**: FK to providers table
- **Event Logging**: Lifecycle events (load/unload/test)
- **Validation**: Instance existence and enablement checks
- **ETag Caching**: HTTP cache validation

#### Default Resolution Precedence
1. Tenant-scoped default (tenant_id specified)
2. Global default (tenant_id = null)
3. None (no default configured)

### Provider Repository (`provider_repo.py`)

Repository for LLM provider management with encryption and audit trails.

#### Core Functions

**CRUD Operations:**
- `create_provider()`: Create provider with encrypted secrets
- `list_providers()`: List providers (redacted)
- `get_provider()`: Get provider by ID (redacted by default)
- `patch_provider()`: Update provider with config merging
- `delete_provider()`: Delete provider with cascade cleanup

**Default Management:**
- `set_provider_default()`: Set default provider for scope
- `get_provider_default()`: Get default with fallback resolution

**Health Management:**
- `set_provider_health()`: Cache health snapshot
- `get_provider_health()`: Get cached health data

**Features:**
- **Secret Encryption**: Fernet encryption for API keys
- **Redaction Policy**: Never expose secrets in API responses
- **Config Merging**: Deep merge for provider configuration
- **Audit Events**: Complete mutation audit trail
- **Multi-tenancy**: Global + tenant-scoped providers
- **ETag Caching**: HTTP conditional requests

#### Redaction Rules
- `api_key` → removed
- `config.headers.authorization` → `***`
- `config.auth.token` → `***`

### Tenants Repository (`tenants.py`)

Repository for tenant organization management.

#### TenantsRepository

**Methods:**
- `create()`: Create tenant with idempotency
- `get_by_id()` / `get_by_name()`: Retrieve tenants
- `list()`: List tenants with keyset pagination
- `update_partial()`: Partial updates with JSONB merging
- `delete()`: Delete tenant with dependency checks

**Features:**
- **Idempotency**: Name-based conflict detection
- **JSONB Metadata**: Flexible tenant attributes
- **Case-Insensitive Names**: Unique constraint on LOWER(name)
- **Dependency Checks**: Prevent deletion with blockers
- **ETag Computation**: Stable cache validation

#### Tenant ID Generation
Format: `tenant-{8-char-uuid-hex}` (e.g., `tenant-a1b2c3d4`)

### Tools Repository (`tools.py`)

Repository for tool definitions and invocations with audit trails.

#### ToolsRepository

**Tool Management:**
- `create_tool()`: Create tool with schema validation
- `get_tool_by_id()` / `get_tool_by_name_version()`: Retrieve tools
- `list_tools()`: List tools with pagination
- `update_tool()`: Update tool fields
- `delete_tool()`: Delete tool

**Invocation Management:**
- `create_invocation()`: Create invocation with idempotency
- `get_invocation_by_eid()` / `get_invocation_by_idempotency_key()`: Retrieve invocations
- `list_invocations()`: List invocations with filtering
- `update_invocation_status()`: Update status with audit events

**Audit Events:**
- `append_audit_event()`: Add audit event
- `get_audit_events()`: Retrieve audit trail

**Features:**
- **Schema Validation**: JSON schemas for input/output
- **Idempotency**: Request deduplication
- **Audit Trail**: Complete invocation history
- **Status Tracking**: pending → running → finished/failed/cancelled
- **ETag Computation**: Cache validation

### User Default Models Repository (`user_default_models.py`)

Repository for per-user default model preferences.

#### UserDefaultModelRepo

**Methods:**
- `get_user_default()`: Get user's default preference
- `set_user_default()`: Set/update user's default
- `delete_user_default()`: Remove user's default
- `cascade_clear_defaults()`: Clear defaults for deleted instance
- `list_user_defaults()`: List user's defaults

**Features:**
- **Tenant Scoping**: user_id + tenant_id combinations
- **Instance Validation**: Ensure referenced instances exist and are enabled
- **ETag Caching**: HTTP cache support
- **Cascade Cleanup**: Automatic cleanup on instance deletion

#### Resolution Precedence
1. User + tenant specific
2. User global (tenant_id = null)
3. Tenant default (from model_instances)
4. Global default (from model_instances)

### Legacy Repository (`user_default_models_old.py`)

Raw SQL implementation of user default models repository (deprecated).

**Note:** This file contains a raw SQL/psycopg2 implementation that has been replaced by the SQLAlchemy version above. It is kept for reference but should not be used in new code.

## Database Schema Dependencies

### Required Tables
- `agent_sessions`, `agent_steps`, `agent_runs`
- `idempotency_keys`
- `jobs`, `job_events`
- `builtins_manifests`, `builtins_activations`, `builtins_staging_jobs`, `builtins_manifest_audit`
- `model_instances`, `model_instance_events`, `model_defaults`
- `providers`, `provider_secrets`, `provider_defaults`, `provider_audit_events`
- `tenants`
- `tools`, `tool_invocations`, `tool_audit_events`
- `user_default_models`

### Foreign Key Relationships
- Agent runs → sessions (CASCADE)
- Agent steps → sessions (CASCADE)
- Job events → jobs (CASCADE)
- Model instances → providers (CASCADE)
- Provider secrets → providers (CASCADE)
- Tool invocations → tenants (no CASCADE)
- User defaults → model instances (CASCADE)

## Redis Cache Keys

### Pattern: `repositories:{entity}:{operation}:{params}`
- `providers:by_id:{id}`
- `providers:list:{page_size}:{page_token}`
- `providers:default:{scope}:{tenant_id}`
- `manifests:builtins:active`
- `manifests:builtins:list`
- `manifests:builtins:history`
- `models:instances:lock:{instance_id}`

## Error Handling

### Common Exceptions
- `ValueError`: Invalid input parameters
- `IntegrityError`: Database constraint violations
- `sqlalchemy.exc.NoResultFound`: Entity not found

### Idempotency Handling
- Race condition detection with retry logic
- Conflict resolution for concurrent operations
- Audit logging for all mutations

## Performance Considerations

### Indexing Strategy
- Primary keys: Automatic unique indexes
- Foreign keys: Automatic performance indexes
- Composite indexes: For common query patterns
- Partial indexes: For sparse constraints
- Functional indexes: For case-insensitive searches

### Caching Strategy
- **Redis TTL**: Short-lived caches (5-60 minutes)
- **ETags**: HTTP conditional request support
- **Invalidation**: Cache clearing on mutations
- **Fallback**: Graceful degradation when Redis unavailable

### Pagination
- **Cursor-based**: Efficient for large datasets
- **Keyset pagination**: Avoid OFFSET performance issues
- **Stable ordering**: Consistent results across requests

## Security Considerations

### Data Protection
- **Secret Encryption**: API keys encrypted at rest
- **Redaction**: Never expose secrets in responses
- **Ownership Checks**: User/tenant isolation
- **Audit Trails**: Complete mutation logging

### Access Control
- **Repository-level**: Ownership validation in queries
- **Tenant Isolation**: tenant_id filtering
- **Admin Operations**: Separate admin methods

## Testing

### Unit Tests
- Mock database sessions for isolated testing
- Test idempotency and error conditions
- Validate ETag computation and caching

### Integration Tests
- Full database operations with test fixtures
- Redis cache validation
- Concurrent operation testing

## Migration Notes

When modifying repositories:
1. Update corresponding database migrations
2. Consider backward compatibility
3. Update dependent services
4. Test with realistic data volumes
5. Update this documentation

## Related Documentation

- [Models Documentation](../models/README_models.md)
- [Database Schema](../../docs/database/schema.md)
- [API Documentation](../../api/README_api.md)
- [Security Model](../../docs/security/model.md)
- [Caching Strategy](../../docs/caching/redis.md)

---

*This documentation was generated on December 9, 2025. Last updated when repositories were modified.*