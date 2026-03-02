# PostgreSQL Control Models Documentation

## Overview

This directory contains SQLAlchemy ORM models for the PostgreSQL control database in the Cineca Agentic Platform. These models define the schema for various entities including agents, jobs, tools, tenants, providers, and audit trails.

The models are organized into separate files, each containing one or more related classes. All models inherit from a common `Base` class and use PostgreSQL-specific features like JSONB, UUID, and advanced indexing.

## Model Architecture

- **Base Class**: All models inherit from `db.postgres_control.database.Base`
- **Database**: PostgreSQL with extensions (UUID, JSONB)
- **Naming Convention**: Snake_case table names, PascalCase class names
- **Relationships**: Foreign keys with CASCADE deletes where appropriate
- **Indexing**: Comprehensive indexes for performance
- **Constraints**: Check constraints for data integrity
- **ETags**: HTTP caching support with computed ETags

## Models Summary

| Model | Table | Purpose |
|-------|-------|---------|
| `AgentRun` | `agent_runs` | Agent execution instances |
| `AgentSession` | `agent_sessions` | Stateful agent interactions |
| `AgentStep` | `agent_steps` | Sequential steps in sessions |
| `AuditLog` | `audit_logs` | Administrative action audit trail |
| `BuiltinManifestActivationHistory` | `builtin_manifest_activation_history` | Manifest activation timeline |
| `BuiltinProcessEvent` | `builtin_process_events` | Process lifecycle events |
| `IdempotencyKey` | `idempotency_keys` | Request deduplication |
| `InternalOpsEvent` | `internal_ops_events` | Operator action tracking |
| `Job` | `jobs` | Asynchronous task management |
| `JobEvent` | `job_events` | Job state change events |
| `BuiltinsManifest` | `builtins_manifests` | Manifest content and state |
| `BuiltinsActivation` | `builtins_activations` | Manifest activation history |
| `BuiltinsStagingJob` | `builtins_staging_jobs` | Staging operation tracking |
| `BuiltinsManifestAudit` | `builtins_manifest_audit` | Manifest audit trail |
| `ModelInstance` | `model_instances` | Model instance registry |
| `ModelInstanceEvent` | `model_instance_events` | Instance lifecycle events |
| `ModelDefault` | `model_defaults` | Default model selections |
| `Provider` | `providers` | LLM provider registry |
| `ProviderSecret` | `provider_secrets` | Encrypted provider secrets |
| `ProviderDefault` | `provider_defaults` | Default provider selections |
| `ProviderAuditEvent` | `provider_audit_events` | Provider audit trail |
| `Tenant` | `tenants` | Organization/customer tenants |
| `Tool` | `tools` | Tool definitions with schemas |
| `ToolInvocation` | `tool_invocations` | Tool execution instances |
| `ToolAuditEvent` | `tool_audit_events` | Tool invocation audit trail |
| `UserDefaultModel` | `user_default_models` | User model preferences |

## Detailed Model Documentation

### AgentRun (`agent_runs`)

Represents a single execution/invocation of an agent. Runs can be one-shot or bound to a session, tracking model usage, performance metrics, and execution status.

#### Key Fields
- `run_id`: UUID primary key
- `session_id`: Optional FK to `agent_sessions`
- `user_id`: User identifier (indexed)
- `tenant_id`: Tenant scope (indexed, CASCADE delete)
- `model` / `manager`: Legacy model fields (deprecated)
- `model_instance_name`: Human-readable instance name
- `model_id`: Provider-specific model ID
- `provider_name`: Provider name
- `provider_id`: FK to `providers`
- `config_source`: Source of model config
- `latency_ms`: Performance metric
- `trace_id`, `request_id`, `event_id`: Tracing identifiers
- `status`: Execution status (queued/running/succeeded/failed/cancelled)
- `llm_error_type`: Error classification
- `llm_error_message`: Detailed error message
- `llm_error_occurred_at`: Error timestamp
- `started_at`, `finished_at`: Execution timestamps
- `todos`, `steps`, `output`, `warnings`, `metrics`: JSONB execution data
- `run_metadata`: Arbitrary metadata

#### Relationships
- `session`: Many-to-one with `AgentSession`

#### Constraints & Indexes
- Status check constraint
- Composite indexes for user/started_at, session/started_at, tenant/user/started_at
- Status/started_at index

#### Methods
- `to_dict()`: Convert to dictionary with computed degraded/used_fallback flags

### AgentSession (`agent_sessions`)

Represents a stateful agent interaction progressing through active → completed/cancelled/failed states.

#### Key Fields
- `session_id`: UUID primary key
- `user_id`: User identifier (indexed)
- `tenant_id`: Tenant scope (indexed, CASCADE delete)
- `status`: Session status (active/completed/cancelled/failed)
- `manager`: Agent manager
- `preferred_workers`: List of worker names (JSONB)
- `llm_preferences`: LLM preferences (JSONB)
- `agent_role`: Agent role
- `tools`: Allowed tool names (JSONB)
- `temperature`: Generation temperature (default 0.2)
- `max_steps`: Maximum steps (default 8)
- `session_metadata`: Arbitrary metadata
- `created_at`, `updated_at`: Timestamps
- `last_step_id`: FK to last `agent_steps`
- `last_step_seq`: Last step sequence number
- `etag`: Computed ETag for caching

#### Relationships
- `steps`: One-to-many with `AgentStep` (CASCADE delete)
- `runs`: One-to-many with `AgentRun` (CASCADE delete)

#### Constraints & Indexes
- Status check constraint
- Composite indexes for user/created_at, tenant/created_at, status

#### Methods
- `compute_etag()`: MD5 hash of session_id/status/updated_at
- `update_etag()`: Update ETag field
- `to_dict()`: Convert to dictionary

### AgentStep (`agent_steps`)

Represents a single step in an agent session. Steps are sequentially numbered and track user messages, agent responses, tool calls, and system events.

#### Key Fields
- `step_id`: UUID primary key
- `session_id`: FK to `agent_sessions` (CASCADE delete, indexed)
- `seq`: Monotonic sequence number
- `type`: Step type (message/user/assistant/tool/system/error)
- `message`: Text content
- `tool`: Tool name
- `input`, `output`: Structured data (JSONB)
- `status`: Step status (queued/running/completed/failed/cancelled)
- `error`: Error details (JSONB)
- `created_at`, `completed_at`: Timestamps

#### Relationships
- `session`: Many-to-one with `AgentSession`

#### Constraints & Indexes
- Unique constraint on (session_id, seq)
- Check constraints for status and type
- Composite indexes for session/seq, session/created_at

#### Methods
- `to_dict()`: Convert to dictionary

### AuditLog (`audit_logs`)

Audit log entry for tracking administrative actions on critical resources for compliance and security auditing.

#### Key Fields
- `id`: String primary key
- `timestamp`: Event timestamp (indexed)
- `action`: Action type (create/update/delete, indexed)
- `resource_type`: Resource type (model/user/tenant, indexed)
- `resource_id`: Resource identifier (indexed)
- `user_id`: Actor user ID (indexed)
- `tenant_id`: Tenant context (indexed)
- `success`: Boolean success flag
- `error_message`: Error details
- `details`: Additional metadata (JSON)

#### Methods
- `__repr__()`: String representation

### BuiltinManifestActivationHistory (`builtin_manifest_activation_history`)

Persistent timeline of built-in manifest activation operations. Each row represents a stage/activate/rollback/failure event for a specific manifest version.

#### Key Fields
- `id`: UUID primary key
- `manifest_name`: Manifest name (indexed)
- `version`: Manifest version
- `activated_at`: Activation timestamp (indexed)
- `activated_by`: Actor identifier
- `status`: Activation status (staged/active/rolled_back/failed)
- `notes`: Optional context/reason

#### Constraints & Indexes
- Composite indexes for name/activated_at, status

#### Methods
- `__repr__()`: String representation

### BuiltinProcessEvent (`builtin_process_events`)

Audit trail of built-in process lifecycle events. Captures start/heartbeat/stop/exit/signal events for processes.

#### Key Fields
- `id`: UUID primary key
- `process_id`: Stable process identifier (indexed)
- `artifact`: Artifact name (e.g., llama3-8b, indexed)
- `pid`: OS process ID (indexed)
- `port`: Listening port
- `event`: Event type (start/heartbeat/stop/exit/signal, indexed)
- `reason`: Event reason (e.g., admin_stop, oom_killed)
- `exit_code`: Exit code for EXIT events
- `ts`: Event timestamp (indexed)
- `tenant_id`: Multi-tenancy support (indexed)
- `manifest_version`: Manifest version at start
- `host`: Hostname for distributed deployments

#### Constraints & Indexes
- Various indexes for ts, artifact/ts, pid/ts, process_id, tenant_id

#### Methods
- `__repr__()`: String representation

### IdempotencyKey (`idempotency_keys`)

Stores request fingerprints to enable idempotent POST operations. Replay detection returns cached response hash.

#### Key Fields
- `key`: String primary key
- `owner_user_id`: Owner user ID (indexed)
- `method`: HTTP method
- `path`: Request path
- `request_hash`: Request hash
- `response_hash`: Response hash
- `response_body`: Cached response body
- `status_code`: HTTP status code
- `created_at`, `replayed_at`: Timestamps

#### Constraints & Indexes
- Composite index for owner/created_at

#### Methods
- `to_dict()`: Convert to dictionary

### InternalOpsEvent (`internal_ops_events`)

Records operator actions on internal endpoints. Tracks actions like auto-start override changes and staged manifest previews.

#### Key Fields
- `id`: BigInteger primary key (auto-increment)
- `kind`: Event kind (e.g., auto_start_override, indexed)
- `sub`: Actor subject (indexed)
- `enabled`: Boolean value for overrides
- `note`: Optional note/reason
- `data_json`: Additional structured data (JSONB)
- `ts`: Event timestamp (indexed)

#### Constraints & Indexes
- Composite indexes for kind/ts, sub/ts

#### Methods
- `to_dict()`: Convert to dictionary
- `__repr__()`: String representation

### Job (`jobs`)

Represents an asynchronous task in the system. Jobs progress through queued → running → finished/failed/cancelled states.

#### Key Fields
- `id`: UUID primary key
- `type`: Job type (indexed)
- `status`: Job status (queued/running/finished/failed/cancelled)
- `owner_sub`: Owner subject (indexed)
- `tenant_id`: Tenant scope (indexed, CASCADE delete)
- `payload_json`: Job payload (JSONB)
- `result_json`: Job result (JSONB)
- `error_json`: Error details (JSONB)
- `idempotency_key`: Idempotency key (unique sparse index)
- `priority`: Job priority (default 0)
- `created_at`, `updated_at`, `started_at`, `completed_at`: Timestamps
- `queue_latency_ms`, `exec_latency_ms`: Performance metrics
- `etag`: Computed ETag for caching

#### Relationships
- `events`: One-to-many with `JobEvent` (CASCADE delete)

#### Constraints & Indexes
- Status check constraint
- Unique sparse index on (owner_sub, idempotency_key)
- Various composite indexes for owner/created_at, status/created_at, tenant/created_at, updated_at

#### Methods
- `compute_etag()`: MD5 hash of id/status/updated_at
- `update_etag()`: Update ETag field
- `to_dict()`: Convert to dictionary (with payload/result inclusion options)
- `is_terminal()`: Check if job is in terminal state

### JobEvent (`job_events`)

Records state changes and significant events in a job's lifecycle. Event types include status changes, logs, progress updates, heartbeats, and completion.

#### Key Fields
- `seq_id`: BigInteger primary key (auto-increment)
- `job_id`: FK to `jobs` (CASCADE delete, indexed)
- `event_type`: Event type
- `event_json`: Event payload (JSONB)
- `created_at`: Event timestamp

#### Relationships
- `job`: Many-to-one with `Job`

#### Constraints & Indexes
- Composite indexes for job/seq, created_at

#### Methods
- `to_dict()`: Convert to dictionary
- `to_sse_event()`: Format as Server-Sent Event

### BuiltinsManifest (`builtins_manifests`)

Builtins manifests table (authoritative source). Stores manifest content, versioning, and state tracking. State transitions: staged → active → archived.

#### Key Fields
- `id`: UUID primary key
- `source_url`: URL from which manifest was fetched
- `content_json`: Full manifest content (JSON)
- `sha256`: Content hash (unique, content-based idempotency)
- `version`: Optional version tag
- `state`: Manifest state (staged/active/archived)
- `created_at`, `activated_at`, `updated_at`: Timestamps
- `created_by_sub`: Creator subject
- `etag`: ETag for HTTP caching

#### Constraints & Indexes
- State check constraint
- Unique constraint on sha256
- Various indexes for state, created_at

#### Methods
- `__repr__()`: String representation

### BuiltinsActivation (`builtins_activations`)

Builtins activations table (activation history). Records every manifest activation/rollback event with timestamps and actors.

#### Key Fields
- `id`: BigInteger primary key (auto-increment)
- `manifest_id`: FK to `builtins_manifests` (CASCADE delete)
- `activated_at`: Activation timestamp
- `activated_by_sub`: Actor subject
- `reason`: Optional activation reason
- `previous_manifest_id`: Previous active manifest (for rollback)
- `trace_id`, `event_id`: Tracing identifiers

#### Constraints & Indexes
- Indexes for manifest_id, activated_at, activated_by_sub

#### Methods
- `__repr__()`: String representation

### BuiltinsStagingJob (`builtins_staging_jobs`)

Builtins staging jobs table (idempotency tracking). Records staging operations for idempotent replay.

#### Key Fields
- `id`: UUID primary key
- `idempotency_key`: Idempotency key
- `source_url`: Source URL
- `sha256`: Content hash
- `created_at`: Job creation timestamp
- `created_by_sub`: Creator subject
- `status`: Job status (ok/error)
- `error_json`: Error details (JSON)

#### Constraints & Indexes
- Status check constraint
- Unique constraint on (created_by_sub, idempotency_key)
- Indexes for created_at, sha256

#### Methods
- `__repr__()`: String representation

### BuiltinsManifestAudit (`builtins_manifest_audit`)

Builtins manifest audit table (append-only audit trail). Records all manifest operations for compliance.

#### Key Fields
- `id`: BigInteger primary key (auto-increment)
- `manifest_id`: FK to `builtins_manifests` (SET NULL)
- `action`: Action performed (stage/activate/rollback/delete)
- `details_json`: Event details (JSON)
- `created_at`: Event timestamp
- `actor_sub`: Actor subject
- `trace_id`, `event_id`: Tracing identifiers

#### Constraints & Indexes
- Various indexes for manifest_id, action, actor_sub, created_at

#### Methods
- `__repr__()`: String representation

### ModelInstance (`model_instances`)

Model instance registry (PostgreSQL authoritative). Stores all model instance metadata including tenant scope and configuration.

#### Key Fields
- `id`: UUID primary key
- `tenant_id`: Tenant scope (nullable for global)
- `instance_name`: Human-readable name
- `provider_id`: FK to `providers` (CASCADE delete)
- `model_id`: Model identifier
- `model_uri`: Optional model URI/path
- `enabled`: Administrative enable flag
- `loaded`: Runtime loaded flag
- `is_default`: Default flag (deprecated)
- `context_window`: Maximum context window
- `modalities`: Supported modalities (JSONB)
- `description`: Instance description
- `parameters`: Model parameters (JSONB)
- `created_at`, `updated_at`: Timestamps
- `etag`: ETag for HTTP caching

#### Relationships
- `events`: One-to-many with `ModelInstanceEvent` (CASCADE delete)

#### Constraints & Indexes
- Unique constraint on (tenant_id, instance_name)
- Various indexes for tenant/created_at, provider/loaded/created_at, enabled

### ModelInstanceEvent (`model_instance_events`)

Model instance event log (append-only). Records lifecycle events for model instances.

#### Key Fields
- `seq_id`: BigInteger primary key (auto-increment)
- `instance_id`: FK to `model_instances` (CASCADE delete)
- `event_type`: Event type (load/unload/test/update/delete)
- `event_json`: Event payload/context (JSONB)
- `created_at`: Event timestamp
- `actor_sub`: Actor subject
- `trace_id`: Correlation ID

#### Relationships
- `instance`: Many-to-one with `ModelInstance`

#### Constraints & Indexes
- Indexes for instance/created_at, type/created_at, actor/created_at

### ModelDefault (`model_defaults`)

Default model instance per scope (global or tenant). Stores default model selections with tenant scoping.

#### Key Fields
- `id`: Integer primary key (auto-increment)
- `scope`: Scope type (global/tenant)
- `tenant_id`: Tenant ID (null for global)
- `instance_id`: FK to `model_instances` (CASCADE delete)
- `created_at`, `updated_at`: Timestamps
- `etag`: ETag for HTTP caching

#### Constraints & Indexes
- Check constraints for scope/tenant_id relationship
- Index on instance_id

### Provider (`providers`)

Provider registry table (authoritative source). Stores all provider metadata including type, base_url, model, and tenant scope.

#### Key Fields
- `id`: String primary key
- `name`: Human-friendly name
- `type`: Provider type (openai_compatible/custom)
- `base_url`: HTTP base URL
- `model`: Default model identifier
- `tenant_id`: Tenant scope (nullable for global)
- `config_json`: Provider-specific configuration (JSON)
- `has_api_key`: Computed API key presence flag
- `created_at`, `updated_at`: Timestamps

#### Constraints & Indexes
- Unique constraint on (tenant_id, name)
- Indexes for tenant_id, type, created_at

#### Methods
- `__repr__()`: String representation

### ProviderSecret (`provider_secrets`)

Provider secrets table (encrypted storage). Stores sensitive credentials separately from main provider record.

#### Key Fields
- `provider_id`: String primary key (FK to providers)
- `api_key_encrypted`: Encrypted API key
- `created_at`, `updated_at`: Timestamps

#### Constraints & Indexes
- Index on created_at

#### Methods
- `__repr__()`: String representation

### ProviderDefault (`provider_defaults`)

Provider defaults table (global and tenant-scoped). Stores default provider selections per scope and tenant.

#### Key Fields
- `scope`: String primary key (scope type)
- `tenant_id`: String primary key (tenant ID, 'global' for global default)
- `provider_id`: Provider identifier
- `created_at`, `updated_at`: Timestamps

#### Constraints & Indexes
- Unique constraint on (scope, tenant_id)
- Indexes for tenant_id, provider_id

#### Methods
- `__repr__()`: String representation

### ProviderAuditEvent (`provider_audit_events`)

Provider audit events table (append-only audit trail). Records all changes to providers, secrets, and defaults for compliance.

#### Key Fields
- `id`: Integer primary key (auto-increment)
- `provider_id`: Affected provider (nullable)
- `actor`: Actor principal
- `action`: Action performed
- `tenant_id`: Tenant context
- `payload`: Event details (JSON)
- `trace_id`, `event_id`: Tracing identifiers
- `created_at`: Event timestamp

#### Constraints & Indexes
- Various indexes for provider_id, actor, action, created_at, tenant_id

#### Methods
- `__repr__()`: String representation

### Tenant (`tenants`)

Tenant ORM model. Represents an organization/customer tenant with isolation and metadata.

#### Key Fields
- `id`: Text primary key (unique tenant identifier)
- `name`: Display name
- `admin_email`: Primary admin contact email
- `metadata_`: Arbitrary tenant metadata (JSONB)
- `created_at`, `updated_at`: Timestamps
- `version`: Optimistic locking version

#### Constraints & Indexes
- Unique index on LOWER(name)
- Index on LOWER(admin_email)
- Index on created_at DESC
- Check constraint for name length

#### Methods
- `__repr__()`: String representation
- `to_dict()`: Convert to dictionary

### Tool (`tools`)

Tool ORM model. Represents a versioned tool definition with JSON schemas for inputs/outputs.

#### Key Fields
- `id`: Text primary key (UUID)
- `name`: Tool name
- `version`: Tool version (semver)
- `description`: Tool description
- `input_schema`: JSON schema for inputs (JSONB)
- `output_schema`: JSON schema for outputs (JSONB)
- `owner_tenant_id`: FK to tenants (CASCADE delete)
- `created_at`, `updated_at`: Timestamps
- `version_number`: Optimistic locking version

#### Constraints & Indexes
- Unique index on (name, version)
- Index on owner_tenant_id
- Check constraints for name/version length

#### Methods
- `__repr__()`: String representation
- `to_dict()`: Convert to dictionary

### ToolInvocation (`tool_invocations`)

ToolInvocation ORM model. Represents a tool execution with idempotency, status tracking, and audit trail.

#### Key Fields
- `eid`: Text primary key (execution ID)
- `tool_name`: Tool name
- `tool_version`: Tool version
- `tenant_id`: FK to tenants
- `status`: Invocation status (pending/running/finished/failed/cancelled)
- `params_json`: Input parameters (JSONB)
- `result_json`: Output result (JSONB)
- `error_json`: Error details (JSONB)
- `started_at`, `completed_at`: Timestamps
- `idempotency_key`: Idempotency key (unique sparse)
- `requested_by`: Requester identifier
- `request_headers`: Request headers (JSONB)
- `latency_ms`: Execution latency

#### Constraints & Indexes
- Index on status
- Unique sparse index on idempotency_key
- Composite index for tenant/started_at DESC
- Index on tool_name
- Status check constraint

#### Methods
- `__repr__()`: String representation
- `to_dict()`: Convert to dictionary

### ToolAuditEvent (`tool_audit_events`)

ToolAuditEvent ORM model. Represents an audit event for a tool invocation (status change, result stored).

#### Key Fields
- `id`: BigInteger primary key (auto-increment)
- `eid`: FK to tool_invocations (CASCADE delete)
- `event_type`: Event type
- `payload_json`: Event data (JSONB)
- `created_at`: Event timestamp

#### Constraints & Indexes
- Index on eid
- Composite index on (eid, created_at)

#### Methods
- `__repr__()`: String representation
- `to_dict()`: Convert to dictionary

### UserDefaultModel (`user_default_models`)

User-scoped default model preferences with tenant scoping.

#### Key Fields
- `id`: UUID primary key
- `user_id`: User identifier
- `tenant_id`: Tenant scope
- `chat_instance_id`: FK to model_instances (CASCADE delete)
- `created_at`, `updated_at`: Timestamps
- `created_by`: Creator identifier
- `etag`: ETag for caching

#### Relationships
- `instance`: Many-to-one with ModelInstance

#### Constraints & Indexes
- Unique index on (user_id, tenant_id)
- Indexes for user_id, tenant_id, chat_instance_id

## Database Schema Features

### Data Types
- **UUID**: For primary keys and references
- **JSONB**: For flexible structured data
- **Text**: For variable-length strings
- **Timestamps**: With timezone awareness

### Indexing Strategy
- **Primary Keys**: Automatic unique indexes
- **Foreign Keys**: Automatic indexes for performance
- **Composite Indexes**: For common query patterns
- **Partial Indexes**: For sparse unique constraints
- **Functional Indexes**: For case-insensitive searches

### Constraints
- **Check Constraints**: For enumerated values and data validation
- **Unique Constraints**: For business logic uniqueness
- **Foreign Key Constraints**: With appropriate CASCADE/SET NULL behavior

### Performance Considerations
- **ETags**: For HTTP conditional requests and caching
- **Optimistic Locking**: Version fields for concurrent updates
- **Idempotency**: Keys for duplicate request prevention
- **Audit Trails**: Append-only tables for compliance

### Multi-Tenancy
- **Tenant Isolation**: tenant_id columns with appropriate indexing
- **Global vs Tenant Scope**: Nullable tenant_id for global resources
- **Cascading Deletes**: Clean up tenant-scoped data on tenant deletion

### Audit and Compliance
- **Append-Only Tables**: Immutable audit trails
- **Actor Tracking**: user_id/sub fields for attribution
- **Timestamp Precision**: Microsecond timestamps
- **Correlation IDs**: trace_id/event_id for distributed tracing

## Usage Examples

### Creating a New Agent Run
```python
from db.postgres_control.models import AgentRun

run = AgentRun(
    user_id="user123",
    tenant_id="tenant456",
    model_instance_name="gpt-4",
    model_id="gpt-4",
    provider_name="openai",
    status="queued"
)
```

### Querying with Relationships
```python
from db.postgres_control.models import AgentSession

session = session.query(AgentSession).filter_by(session_id=session_uuid).first()
runs = session.runs  # Access related runs
steps = session.steps  # Access related steps
```

### Using ETags for Caching
```python
job = session.query(Job).filter_by(id=job_uuid).first()
job.update_etag()
etag = job.etag  # Use in HTTP responses
```

## Migration Notes

When modifying these models:
1. Update the corresponding Alembic migration files
2. Consider backward compatibility for existing data
3. Update any dependent code that uses these models
4. Test migrations on staging environments first
5. Update this documentation

## Related Documentation

- [Database Schema Overview](../README.md)
- [API Documentation](../../api/README_api.md)
- [Migration Guide](../../docs/database/migrations.md)
- [Security Model](../../docs/security/model.md)

---

*This documentation was generated on December 9, 2025. Last updated when models were modified.*