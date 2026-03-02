# Cineca Agentic Platform - Complete Project Documentation

**Version**: 0.1.0  
**Date**: November 1, 2025  
**Author**: Arman Feili  
**Institution**: Sapienza University of Rome  
**Project Type**: Master's Thesis (ILP Thesis 2025)

---

## Table of Contents

1. [Executive Overview](#executive-overview)
2. [Project Background & Motivation](#project-background--motivation)
3. [Architecture & Design](#architecture--design)
4. [Core Components](#core-components)
5. [Technology Stack](#technology-stack)
6. [Key Features](#key-features)
7. [API Surface](#api-surface)
8. [Security & Compliance](#security--compliance)
9. [Data Management](#data-management)
10. [Observability & Monitoring](#observability--monitoring)
11. [Deployment & Operations](#deployment--operations)
12. [Development Workflow](#development-workflow)
13. [Testing Strategy](#testing-strategy)
14. [Production Readiness](#production-readiness)
15. [Future Enhancements](#future-enhancements)
16. [References & Resources](#references--resources)

---

## Executive Overview

The **Cineca Agentic Platform** is an advanced, production-ready platform for intelligent agent orchestration with natural language processing capabilities. Built as a thesis project at Sapienza University of Rome, it demonstrates enterprise-grade architecture patterns for building scalable, secure, and observable AI-powered systems.

### What It Does

The platform enables users to:
- **Query graph databases using natural language** - Converts NL → Cypher queries with security guardrails
- **Orchestrate AI agents** - Manage multi-turn conversations with context preservation
- **Execute distributed jobs** - Background task processing with progress tracking
- **Manage multiple LLM providers** - Flexible integration with OpenAI, Ollama, and custom endpoints
- **Enforce fine-grained access control** - Multi-tenant RBAC with audit logging
- **Monitor system health in real-time** - Prometheus metrics + Grafana dashboards

### Key Metrics

| Metric | Value |
|--------|-------|
| **Total Test Coverage** | 931 passing tests (100% green) |
| **API Endpoints** | 50+ REST endpoints across 12 routers |
| **MCP Tools** | 32 standardized tools with RBAC |
| **Lines of Code** | ~25,000+ Python (excluding tests) |
| **Databases** | PostgreSQL (persistence), Redis (cache), Memgraph (graph) |
| **Container Services** | 12 containerized services |
| **Documentation Files** | 330+ markdown documents |

### Technology Highlights

- **FastAPI** (async REST API with OpenAPI 3.1)
- **PostgreSQL 16** (ACID persistence with Alembic migrations)
- **Redis 7** (caching, rate limiting, job queues)
- **Memgraph** (graph database with Cypher query language)
- **Ollama** (local LLM inference)
- **Prometheus + Grafana** (observability stack)
- **Docker Compose** (development & deployment orchestration)
- **GitHub Actions** (CI/CD pipeline)

---

## Project Background & Motivation

### Academic Context

This project was developed as part of a Master's thesis at **Sapienza University of Rome** under the ILP (Intelligent Learning and Perception) program. The research explores:

1. **Agentic AI Architectures** - Design patterns for building autonomous AI systems
2. **Graph-Based Knowledge Representation** - Using graph databases for complex relationship modeling
3. **Security in AI Systems** - Implementing guardrails, audit trails, and access controls
4. **Production-Grade AI Systems** - Bridging the gap between research prototypes and deployable systems

### Problem Statement

Traditional database interfaces require:
- **Technical expertise** - Users must learn query languages (SQL, Cypher)
- **Schema knowledge** - Understanding complex data models
- **Security awareness** - Avoiding injection attacks and unauthorized access

**The platform solves these problems by:**
- Enabling natural language queries with automatic translation to Cypher
- Providing intelligent schema exploration and validation
- Enforcing security policies automatically (read-only checks, tenant isolation, rate limiting)

### Use Cases

1. **Enterprise Knowledge Graphs** - Explore organizational data using conversational interfaces
2. **Research Data Analysis** - Query scientific datasets without learning Cypher
3. **Multi-Tenant SaaS** - Provide secure, isolated environments for multiple organizations
4. **AI Agent Development** - Framework for building context-aware conversational agents

---

## Architecture & Design

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT APPLICATIONS                            │
│                    (Web UI, CLI, REST Clients, SDKs)                    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI REST API LAYER                          │
│  ┌──────────────┬──────────────┬──────────────┬──────────────────────┐ │
│  │  Auth/AuthZ  │  Rate Limit  │  Validation  │  Request Logging     │ │
│  │  Middleware  │  Middleware  │  Middleware  │  & Tracing           │ │
│  └──────────────┴──────────────┴──────────────┴──────────────────────┘ │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     ROUTERS (21 modules)                          │  │
│  │  Agents│Health│Tools│Jobs│Models│Tenants│Admin│Internal          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          SERVICE LAYER                                   │
│  ┌─────────────┬─────────────┬─────────────┬──────────────────────┐   │
│  │  Agent      │  Tool       │  Job        │  Model Management    │   │
│  │  Orchestr.  │  Execution  │  Scheduler  │  & LLM Adapter      │   │
│  └─────────────┴─────────────┴─────────────┴──────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     MCP TOOLS REGISTRY (32 tools)                       │
│  ┌─────────────┬─────────────┬─────────────┬──────────────────────┐   │
│  │  Graph      │  System     │  Security   │  Data Management     │   │
│  │  Operations │  Health     │  Audit      │  & Analytics        │   │
│  └─────────────┴─────────────┴─────────────┴──────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
         ┌─────────────┬──────────────┬──────────────┐
         │ PostgreSQL  │    Redis     │  Memgraph    │
         │  (ACID DB)  │   (Cache)    │  (Graph DB)  │
         └─────────────┴──────────────┴──────────────┘
                    │            │            │
                    └────────────┼────────────┘
                                 ▼
                    ┌──────────────────────────┐
                    │   Observability Stack    │
                    │  Prometheus + Grafana    │
                    └──────────────────────────┘
```

### Design Principles

1. **Separation of Concerns** - Clean layering (routers → services → repositories → databases)
2. **Security by Default** - All endpoints protected; explicit allowlists for operations
3. **Observability First** - Structured logging, distributed tracing, metrics on all operations
4. **Idempotency** - Safe retries with deduplication keys
5. **Multi-Tenancy** - Tenant isolation at database and application layers
6. **API-First** - OpenAPI 3.1 schema drives documentation and client generation
7. **Testability** - Dependency injection, mocking, fixtures for all components

### Component Communication Patterns

**Synchronous (REST)**
- Client → API → Service → Database
- Used for: CRUD operations, queries, admin tasks

**Asynchronous (Jobs)**
- Client → API → Redis Queue → Worker → PostgreSQL
- Used for: Long-running operations, batch processing, scheduled tasks

**Event-Driven (SSE)**
- Worker → PostgreSQL (events) → API → Client (streaming)
- Used for: Real-time job progress, status updates

---

## Core Components

### 1. FastAPI Application (`src/app.py`)

The main application entry point that:
- Configures middleware (CORS, auth, rate limiting, logging)
- Registers routers for different API domains
- Sets up dependency injection
- Initializes database connections
- Exposes OpenAPI schema at `/v1/openapi.json`

**Key Middleware Stack:**
```python
1. RequestIDMiddleware      # X-Request-ID propagation
2. CORSMiddleware           # Cross-origin resource sharing
3. AuthenticationMiddleware # JWT/OIDC validation
4. RateLimitMiddleware      # Request throttling
5. LoggingMiddleware        # Structured logging
6. ExceptionHandlerMiddleware # RFC-7807 errors
```

### 2. Routers (21 modules in `src/routers/`)

| Router | Path | Purpose |
|--------|------|---------|
| `health.py` | `/v1/health/*` | Liveness, readiness, startup checks |
| `auth.py` | `/v1/auth/*` | Token exchange, user info |
| `agent.py` | `/v1/agents/*` | Agent sessions and runs |
| `agent_runs.py` | `/v1/agent-runs` | One-shot agent execution |
| `tools.py` | `/v1/tools/*` | Tool discovery and invocation |
| `jobs.py` | `/v1/jobs/*` | Job lifecycle, SSE events |
| `models.py` | `/v1/models/*` | Model catalog and inference |
| `model_instances.py` | `/v1/models/instances/*` | Model instance management |
| `tenants.py` | `/v1/tenants/*` | Tenant CRUD (user-accessible) |
| `tenants_admin.py` | `/v1/admin/tenants/*` | Admin tenant operations |
| `admin.py` | `/v1/admin/*` | Admin surface (providers, processes) |
| `internal_db.py` | `/v1/internal/db/*` | Database population & utilities |

### 3. Service Layer (`src/services/`)

Business logic components that orchestrate operations:

- **`agent_service.py`** - Agent lifecycle, session management, conversation history
- **`orchestrator_service.py`** - Tool selection, LLM routing, retry logic
- **`tool_service.py`** - Tool discovery, validation, execution
- **`job_service.py`** - Job creation, status tracking, cancellation
- **`model_service.py`** - Model discovery, instance management, health checks
- **`tenant_service.py`** - Multi-tenancy enforcement, quota management

### 4. MCP Tools Registry (`src/mcp/tools/`)

**32 standardized tools** organized by domain:

#### Graph Operations (8 tools)
- `graph.query@1` - Execute ad-hoc Cypher queries
- `graph.secure_query@1` - NL→Cypher with guardrails (read-only enforcement)
- `graph.generate_cypher@1` - Generate Cypher from natural language
- `graph.schema@1` - Introspect graph schema (labels, relationships)
- `graph.search@1` - Semantic search over graph nodes
- `graph.crud@1` - Create, update, delete nodes/relationships
- `graph.bulk@1` - Bulk operations with batch processing
- `graph.analytics@1` - Graph algorithms (PageRank, centrality, clustering)

#### System Tools (4 tools)
- `system.health@1` - Health checks (liveness, readiness, details)
- `system.status@1` - System info (version, uptime, resources)
- `system.metrics@1` - Prometheus metrics export
- `system.backup@1` - Database backup and restore

#### Security Tools (3 tools)
- `security.audit@1` - Audit log queries
- `security.permissions@1` - RBAC policy management
- `security.check@1` - Permission validation

#### Data Management (3 tools)
- `data.archive@1` - Archive, restore, purge operations
- `data.quality@1` - Data quality checks
- `db.switch@1` - Database switching (dev/staging/prod)

#### Other Domains (14 tools)
- Agent context, cache management, catalog discovery
- Error reporting, model management, output formatting
- Privacy consent, rate limit management, session management
- Tenancy management, user profiles, visualization rendering

**Tool Standardization:**
- All tools follow `<domain>.<action>@<version>` naming
- Declare capabilities (`reads_db`, `writes_db`, `nl_to_cypher`, etc.)
- Specify required scopes (`tools:basic`, `tools:all`, `admin:all`)
- Include input schemas with action enums
- Support audit logging and tracing

### 5. Database Layers

#### PostgreSQL (`db/postgres_control/`)
**Production-grade persistence with:**
- **Alembic migrations** - Version-controlled schema changes
- **Repository pattern** - Clean data access abstraction
- **Connection pooling** - QueuePool (size=10, overflow=20)
- **JSONB support** - Flexible metadata storage

**Key Tables:**
- `tenants` - Multi-tenant isolation
- `jobs` - Background job state
- `job_events` - Job lifecycle events
- `tool_invocations` - Tool execution history
- `model_instances` - LLM instance registry
- `user_default_models` - Per-user model preferences

#### Redis (`db/redis_cache/`)
**High-performance caching with:**
- **Rate limiting** - Token bucket algorithm
- **Job queues** - Multiple priority queues (demo, test, long-running)
- **Result caching** - Tool invocation results (TTL: 1 hour)
- **Idempotency keys** - Request deduplication (TTL: 24 hours)

**Key Patterns:**
```
tools:queue:{name}              # Pending invocations
tools:result:{eid}              # Cached results
tools:idem:{key}                # Idempotency mappings
jobs:queue:{type}               # Job queues
ratelimit:{user}:{endpoint}     # Rate limit counters
```

#### Memgraph (`db/memgraph_domain/`)
**Graph database operations:**
- **Cypher query execution** - Via Bolt protocol
- **Sample dataset** - Academic/research graph structure
- **Schema introspection** - Dynamic schema discovery
- **Full-text search** - Node property indexing

### 6. Background Worker (`src/workers/jobs_worker.py`)

Dedicated service for asynchronous job processing:
- **Queue polling** - Retrieves jobs from Redis queues (configurable interval)
- **Job execution** - Runs job handlers with timeout protection
- **Heartbeat updates** - Periodic status updates to PostgreSQL
- **Graceful shutdown** - Handles SIGTERM/SIGINT for clean termination
- **Error handling** - Captures failures, updates job status, logs errors

**Supported Job Types:**
- `demo` - Sleep simulation for testing
- `test` - Instant echo for validation
- `long-running` - Multi-step processing

---

## Technology Stack

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.11+ | Primary language |
| **FastAPI** | 0.115+ | Async REST framework |
| **Pydantic** | 2.x | Data validation & settings |
| **SQLAlchemy** | 2.0 | ORM for PostgreSQL |
| **Alembic** | 1.13+ | Database migrations |
| **Redis-py** | 5.x | Redis client |
| **Neo4j Driver** | 5.x | Memgraph Bolt connection |

### Databases

| Database | Version | Purpose |
|----------|---------|---------|
| **PostgreSQL** | 16-alpine | Primary persistence |
| **Redis** | 7-alpine | Cache, queues, rate limiting |
| **Memgraph** | Latest | Graph database |

### Observability

| Tool | Purpose |
|------|---------|
| **Prometheus** | Metrics collection & storage |
| **Grafana** | Dashboards & visualization |
| **Structured Logging** | JSON logs with correlation IDs |
| **OpenTelemetry** | Distributed tracing (optional) |

### LLM Integration

| Provider | Purpose |
|----------|---------|
| **Ollama** | Local LLM inference |
| **OpenAI API** | Cloud LLM (GPT-4, etc.) |
| **Custom Endpoints** | Pluggable LLM backends |

### Development Tools

| Tool | Purpose |
|------|---------|
| **Ruff** | Linting & formatting |
| **Black** | Code formatting |
| **Mypy** | Type checking |
| **Pytest** | Testing framework |
| **Bandit** | Security linting |
| **pip-audit** | Dependency vulnerability scanning |

### Deployment

| Tool | Purpose |
|------|---------|
| **Docker** | Containerization |
| **Docker Compose** | Multi-container orchestration |
| **GitHub Actions** | CI/CD pipelines |
| **Kubernetes** (future) | Production orchestration |

---

## Key Features

### 1. Natural Language to Cypher Translation

**Problem:** Users need to query graph databases without learning Cypher.

**Solution:** `graph.secure_query` tool with 4 actions:

```python
# Action: ask (end-to-end NL → results)
{
  "action": "ask",
  "question": "Find all researchers working on AI in Italy",
  "principal": "user-123",
  "tenant": "tenant-abc"
}

# Behind the scenes:
# 1. Schema context retrieval (node labels, relationship types)
# 2. LLM generates Cypher: MATCH (r:Researcher)-[:WORKS_ON]->(t:Topic {name: "AI"})
# 3. Security validation (read-only check, forbidden clause detection)
# 4. Permission check (tenant isolation, RBAC scopes)
# 5. Safe execution (timeout: 5s, row limit: 1000)
# 6. Result formatting (rows, JSON, CSV, Markdown)
```

**Security Guardrails:**
- Read-only enforcement (detects CREATE, SET, DELETE, MERGE)
- Forbidden clause blocking (CALL db.drop*, db.execute*)
- Tenant scoping (injects WHERE tenant_id = ?)
- Rate limiting (10 requests/min recommended)
- Timeout protection (prevents runaway queries)

### 2. Agent Orchestration

**Sessions:** Long-lived conversations with context preservation.

```python
# Create session
POST /v1/agents/sessions
{
  "agent_id": "research-assistant",
  "system_prompt": "You are a helpful research assistant.",
  "config": {"temperature": 0.7, "max_tokens": 2000}
}
# Response: {"session_id": "sess-abc123", "status": "active"}

# Send messages
POST /v1/agents/sessions/sess-abc123/steps
{
  "user_message": "What is the capital of France?",
  "tool_choice": "auto"
}
# Response: {"assistant_message": "Paris", "tool_calls": []}

# Get history
GET /v1/agents/sessions/sess-abc123
# Response: {"history": [...], "token_count": 245}
```

**One-Shot Runs:** Stateless agent execution.

```python
POST /v1/agent-runs
{
  "prompt": "Summarize the top 5 AI researchers in our database",
  "tools": ["graph.search", "output.summarize"],
  "max_steps": 10
}
```

### 3. Multi-LLM Provider Management

**Provider Registry:**
```python
# Register provider
POST /v1/admin/models/providers/register
{
  "name": "openai-production",
  "provider_type": "openai",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "default_model": "gpt-4-turbo"
}

# Set as default
POST /v1/admin/models/providers/{id}:setDefault

# List providers
GET /v1/admin/models/providers
# Response: {
#   "items": [...],
#   "total": 3,
#   "next_page_token": "page_2"
# }
```

**Model Defaults with Precedence:**
```
User Default → Tenant Default → Global Default → 404
```

### 4. Background Jobs with Progress Tracking

**Create Job:**
```python
POST /v1/jobs
{
  "type": "demo",
  "payload": {"duration_ms": 5000},
  "idempotency_key": "job-20251101-abc"
}
# Response: {
#   "id": "job-uuid",
#   "status": "queued",
#   "queue_latency_ms": null
# }
```

**Stream Progress (SSE):**
```bash
curl -N http://localhost:8000/v1/jobs/{id}/events \
  -H "Accept: text/event-stream"

# Output:
# event: status_change
# data: {"status": "running", "timestamp": "2025-11-01T10:00:00Z"}
#
# event: progress
# data: {"percent": 50, "message": "Processing..."}
#
# event: status_change
# data: {"status": "finished", "result": {...}}
```

**Job Lifecycle:**
```
queued → running → finished/failed/cancelled
```

### 5. Multi-Tenant Access Control

**Tenant Isolation:**
- Database-level: Tenant ID in all tables (PostgreSQL)
- Application-level: JWT claims validation (`tenant_id` in token)
- Query-level: Automatic WHERE tenant_id = ? injection

**RBAC Scopes:**
```yaml
# src/agent_policies/policies.yaml
roles:
  user:
    scopes:
      - tools:basic  # Read-only operations
  operator:
    scopes:
      - tools:basic
      - tools:all    # Write operations
  admin:
    scopes:
      - admin:all    # Security & tenancy administration
```

**Scope Enforcement:**
```python
# Router decorator
@router.post("/tools/{name}/invocations")
@requires_scopes("tools:basic")
async def invoke_tool(...):
    # Only users with tools:basic scope can access
    pass
```

### 6. Idempotency & Caching

**Idempotency Keys:**
```python
POST /v1/jobs
Headers:
  Idempotency-Key: job-20251101-abc

# First request: 201 Created
# Second request (same key): 200 OK + Idempotency-Replayed: true
# Conflict (same key, different params): 409 Conflict
```

**ETag Caching:**
```python
GET /v1/tenants/{id}
Response Headers:
  ETag: "abc123"

# Subsequent request:
GET /v1/tenants/{id}
Headers:
  If-None-Match: "abc123"

# Response: 304 Not Modified (no body)
```

### 7. Rate Limiting

**Configuration:**
```python
# Production mode
RATE_LIMIT_MODE=prod
- Sessions: 10/min
- Steps: 100/min
- Runs: 20/min
- List: 100/min

# Test mode (for CI)
RATE_LIMIT_MODE=test
- All: 10000/min
```

**Response Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1698768000
```

### 8. Comprehensive Observability

**Metrics (Prometheus):**
```
# HTTP metrics
http_requests_total{method, endpoint, status}
http_request_duration_seconds{method, endpoint}

# Job metrics
job_operations_total{operation, status}
job_queue_depth{queue_name}
job_duration_seconds{type}

# Tool metrics
tools_invocations_total{tool_name, status}
tools_cache_hit_rate{tool_name}

# Rate limit metrics
ratelimit_requests_total{endpoint, action}
```

**Grafana Dashboards:**
- Health overview (CPU, memory, request rate)
- Job processing (queue depth, latency, throughput)
- Tool usage (invocations, cache hits, errors)
- Database connections (pool size, active queries)

**Structured Logging:**
```json
{
  "timestamp": "2025-11-01T10:00:00Z",
  "level": "INFO",
  "message": "tool.invocation.success",
  "tool_name": "graph.search",
  "duration_ms": 42,
  "principal": "user-123",
  "tenant": "tenant-abc",
  "trace_id": "trace-xyz",
  "request_id": "req-123"
}
```

---

## API Surface

### OpenAPI 3.1 Specification

**Spec Location:** `/v1/openapi.json`  
**Interactive Docs:** `/docs` (Swagger UI) - configurable via `ENABLE_DOCS`

### API Versioning

- **Current Version:** `v1`
- **Path Prefix:** `/v1/`
- **Deprecation Policy:** 90-day notice for breaking changes

### Endpoint Summary (50+ endpoints)

#### Health & Metadata
```
GET  /v1/                    # Service info
GET  /v1/health/live         # Liveness probe
GET  /v1/health/ready        # Readiness probe
GET  /v1/health/startup      # Detailed startup checks
GET  /metrics                # Prometheus metrics
```

#### Authentication
```
POST /v1/auth/token          # Token exchange
GET  /v1/auth/me             # Current user info
```

#### Agents
```
POST   /v1/agents/sessions             # Create session
GET    /v1/agents/sessions/{id}        # Get session
POST   /v1/agents/sessions/{id}/steps  # Send message
DELETE /v1/agents/sessions/{id}        # Close session
POST   /v1/agent-runs                  # One-shot run
```

#### Tools
```
GET  /v1/tools                         # List tools
GET  /v1/tools/{name}                  # Tool details
POST /v1/tools/{name}/invocations      # Invoke tool
GET  /v1/tools/{name}/invocations/{id} # Get invocation result
```

#### Jobs
```
POST   /v1/jobs           # Create job
GET    /v1/jobs/{id}      # Get job status
DELETE /v1/jobs/{id}      # Cancel job
GET    /v1/jobs/{id}/events # Stream events (SSE)
```

#### Models (User-Accessible)
```
GET  /v1/models                      # List models
POST /v1/models/completions          # Text completion
POST /v1/models/chat/completions     # Chat completion
POST /v1/models/embeddings           # Generate embeddings
GET  /v1/models/instances            # List instances
GET  /v1/models/instances/{id}       # Instance details
POST /v1/models/instances/{id}/tests # Test instance
GET  /v1/models/defaults             # Get default model
PATCH /v1/models/defaults            # Set default (user scope)
```

#### Admin - Providers
```
GET    /v1/admin/models/providers          # List providers
POST   /v1/admin/models/providers/register # Register provider
GET    /v1/admin/models/providers/main     # Get main provider
GET    /v1/admin/models/providers/{id}     # Provider details
PATCH  /v1/admin/models/providers/{id}     # Update provider
DELETE /v1/admin/models/providers/{id}     # Remove provider
POST   /v1/admin/models/providers/{id}:setDefault # Set default
```

#### Admin - Tenants
```
GET    /v1/admin/tenants      # List tenants
POST   /v1/admin/tenants      # Create tenant
GET    /v1/admin/tenants/{id} # Tenant details
PATCH  /v1/admin/tenants/{id} # Update tenant
DELETE /v1/admin/tenants/{id} # Delete tenant
```

#### Admin - Processes & Manifests
```
GET    /v1/admin/processes                      # List processes
DELETE /v1/admin/processes/{pid}                # Stop process
GET    /v1/admin/models/manifests/builtins      # List manifests
POST   /v1/admin/models/manifests/builtins:stage    # Stage manifest
POST   /v1/admin/models/manifests/builtins:activate # Activate manifest
POST   /v1/admin/models/manifests/builtins:rollback # Rollback manifest
```

#### Internal - Database Utilities
```
POST   /v1/internal/db/jobs       # Create DB job
GET    /v1/internal/db/jobs/{id}  # DB job status
DELETE /v1/internal/db/jobs/{id}  # Cancel DB job
GET    /v1/internal/db/counts     # Node/edge counts
```

### Response Formats

**Success (200 OK):**
```json
{
  "data": {...},
  "metadata": {
    "timestamp": "2025-11-01T10:00:00Z",
    "request_id": "req-123"
  }
}
```

**Error (RFC 7807 Problem+JSON):**
```json
{
  "type": "https://api.example.com/errors/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Tenant with ID tenant-123 not found",
  "instance": "/v1/tenants/tenant-123",
  "correlation_id": "req-123",
  "timestamp": "2025-11-01T10:00:00Z"
}
```

### Authentication

**JWT Bearer Token:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/agents/sessions
```

**OIDC Configuration:**
```bash
export OIDC_ISSUER="https://auth.example.com"
export OIDC_AUDIENCE="cineca-api"
export OIDC_JWKS_URL="https://auth.example.com/.well-known/jwks.json"
```

---

## Security & Compliance

### Security Architecture

#### 1. Authentication Layer
- **OIDC/OAuth2** - Resource server mode with JWKS validation
- **JWT Validation** - Signature verification, expiry checks, audience validation
- **Token Claims** - `sub` (user ID), `tenant_id`, `roles`, `scopes`

#### 2. Authorization Layer
- **RBAC** - Role-based access control with 3 roles (user, operator, admin)
- **Scope Enforcement** - Declarative scope requirements on endpoints
- **Tenant Isolation** - Automatic tenant ID injection in queries

#### 3. Guardrails

**Input Validation:**
- Pydantic schemas for all request bodies
- Type checking, range validation, format validation
- Custom validators for domain-specific rules

**Intent Filtering:**
```python
# src/security/intent_filter.py
# Blocks malicious prompts:
# - Prompt injection attempts
# - System prompt overrides
# - Jailbreak patterns
```

**Output Guards:**
```python
# src/security/output_guard.py
# Validates LLM-generated Cypher:
# - Write operation detection
# - Forbidden clause blocking
# - Schema conformance checking
```

**PII Scrubbing:**
```python
# src/security/pii_scrubber.py
# Redacts sensitive data in logs:
# - Email addresses → [EMAIL]
# - Phone numbers → [PHONE]
# - Credit cards → [CC]
```

#### 4. Rate Limiting

**Implementation:**
- Token bucket algorithm with Redis backend
- Per-endpoint, per-user limits
- Exponential backoff hints in headers

**Configuration:**
```python
# Production limits
RATE_LIMIT_MODE=prod
- POST /v1/agents/sessions: 10/min
- POST /v1/agents/sessions/{id}/steps: 100/min
- POST /v1/tools/{name}/invocations: 60/min
```

#### 5. Audit Logging

**Audit Trail:**
```sql
CREATE TABLE audit_events (
  id SERIAL PRIMARY KEY,
  timestamp TIMESTAMP DEFAULT NOW(),
  event_type VARCHAR(100),
  principal VARCHAR(255),
  tenant_id VARCHAR(255),
  resource_type VARCHAR(100),
  resource_id VARCHAR(255),
  action VARCHAR(50),
  result VARCHAR(50),
  metadata JSONB
);
```

**Logged Events:**
- Authentication success/failure
- Authorization denials
- Resource creation/modification/deletion
- Tool invocations
- Admin operations (provider registration, tenant creation)

### Compliance Features

#### GDPR Readiness
- **Data Subject Access Requests (DSAR)** - Query audit logs by principal
- **Right to Erasure** - Cascade deletes with soft deletion
- **Privacy by Design** - PII scrubbing, minimal data retention
- **Consent Management** - `privacy.consent` tool for opt-in/opt-out tracking

#### Security Best Practices
- **Secret Management** - Never commit secrets; use environment variables
- **TLS Encryption** - HTTPS termination at reverse proxy
- **Dependency Scanning** - `pip-audit` in CI pipeline
- **Security Linting** - Bandit for Python security issues
- **Container Scanning** - Trivy for Docker image vulnerabilities

---

## Data Management

### PostgreSQL Schema

#### Tenants
```sql
CREATE TABLE tenants (
  id VARCHAR(255) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  admin_email VARCHAR(320) NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  version INTEGER NOT NULL DEFAULT 1,
  CONSTRAINT uq_tenants_name_ci UNIQUE (LOWER(name))
);
```

#### Jobs
```sql
CREATE TABLE jobs (
  id UUID PRIMARY KEY,
  type VARCHAR(100) NOT NULL,
  status VARCHAR(50) DEFAULT 'queued',
  payload_json JSONB,
  result_json JSONB,
  error_json JSONB,
  priority INTEGER DEFAULT 5,
  queue_latency_ms INTEGER,
  exec_latency_ms INTEGER,
  created_at TIMESTAMP DEFAULT NOW(),
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  heartbeat_at TIMESTAMP,
  cancelled BOOLEAN DEFAULT FALSE,
  idempotency_key VARCHAR(255) UNIQUE
);

CREATE TABLE job_events (
  job_id UUID NOT NULL REFERENCES jobs(id),
  seq_id SERIAL,
  event_type VARCHAR(100) NOT NULL,
  event_json JSONB,
  created_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (job_id, seq_id)
);
```

#### Tool Invocations
```sql
CREATE TABLE tool_invocations (
  id SERIAL PRIMARY KEY,
  eid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  tool_name VARCHAR(255) NOT NULL,
  tool_version VARCHAR(50) NOT NULL DEFAULT '1',
  tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(id),
  params_json JSONB,
  result_json JSONB,
  error_json JSONB,
  status VARCHAR(50) DEFAULT 'pending',
  latency_ms INTEGER,
  requested_by VARCHAR(255),
  idempotency_key VARCHAR(255),
  request_headers JSONB,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(idempotency_key, tool_name)
);
```

### Redis Data Structures

**Job Queues (List):**
```redis
LPUSH jobs:queue:demo '{"id": "job-123", "type": "demo", "payload": {...}}'
BRPOP jobs:queue:demo 0  # Blocking pop for worker
```

**Rate Limiting (String with TTL):**
```redis
SET ratelimit:user-123:/v1/agents/sessions 10 EX 60
INCR ratelimit:user-123:/v1/agents/sessions
```

**Idempotency (Hash with TTL):**
```redis
HSET idempotency:key-abc status "200" body "{...}" headers "{...}"
EXPIRE idempotency:key-abc 86400  # 24 hours
```

**Tool Results (String with TTL):**
```redis
SET tools:result:event-123 '{"ok": true, "result": {...}}' EX 3600
```

### Memgraph Graph Model

**Node Labels:**
- `Researcher` - Academic researchers
- `Publication` - Research papers
- `Institution` - Universities, labs
- `Topic` - Research topics/areas
- `Project` - Research projects

**Relationship Types:**
- `WORKS_AT` - Researcher → Institution
- `AUTHORED` - Researcher → Publication
- `CITED_BY` - Publication → Publication
- `WORKS_ON` - Researcher → Topic
- `FUNDED_BY` - Project → Institution

**Sample Cypher:**
```cypher
// Find top 5 researchers by publication count
MATCH (r:Researcher)-[:AUTHORED]->(p:Publication)
RETURN r.name, COUNT(p) AS pub_count
ORDER BY pub_count DESC
LIMIT 5;

// Find collaboration network
MATCH (r1:Researcher)-[:AUTHORED]->(p:Publication)<-[:AUTHORED]-(r2:Researcher)
WHERE r1 <> r2
RETURN r1.name, r2.name, COUNT(p) AS collaborations;
```

### Database Migrations

**Alembic Workflow:**
```bash
# Generate migration
alembic revision --autogenerate -m "Add user_default_models table"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1

# View history
alembic history --verbose
```

**Migration Files:** `db/postgres_control/alembic/versions/`

---

## Observability & Monitoring

### Prometheus Metrics

**HTTP Metrics:**
```
http_requests_total{method, endpoint, status, tenant_id}
http_request_duration_seconds{method, endpoint}
http_requests_in_flight{method, endpoint}
```

**Job Metrics:**
```
job_operations_total{operation, status, type}
job_queue_depth{queue_name}
job_queue_latency_seconds{type}
job_execution_duration_seconds{type}
job_active_count{type}
```

**Tool Metrics:**
```
tools_invocations_total{tool_name, status}
tools_invocation_duration_seconds{tool_name}
tools_cache_operations_total{operation, result}
tools_queue_depth{tool_name}
tools_idempotency_conflicts_total{tool_name}
```

**Database Metrics:**
```
db_connections_active{database}
db_connections_idle{database}
db_query_duration_seconds{query_type}
db_transaction_duration_seconds{operation}
```

**Rate Limit Metrics:**
```
ratelimit_requests_total{endpoint, action}
ratelimit_limit_exceeded_total{endpoint, tenant_id}
```

### Grafana Dashboards

**Health Overview Dashboard:**
- Request rate (req/s) by endpoint
- Error rate (%) by status code
- P50/P95/P99 latency by endpoint
- CPU & memory usage
- Database connection pool utilization

**Job Processing Dashboard:**
- Queue depth by queue type
- Queue latency (time to start)
- Execution duration (time to complete)
- Success/failure rate
- Active job count

**Tool Usage Dashboard:**
- Invocations per tool
- Cache hit rate
- Average duration
- Error rate by tool
- Idempotency conflicts

**Database Dashboard (Memgraph):**
- Node count by label
- Relationship count by type
- Query duration histogram
- Active connections

### Structured Logging

**Log Format (JSON):**
```json
{
  "timestamp": "2025-11-01T10:00:00.123Z",
  "level": "INFO",
  "logger": "src.routers.tools",
  "message": "tool.invocation.success",
  "tool_name": "graph.search",
  "duration_ms": 42,
  "principal": "user-123",
  "tenant_id": "tenant-abc",
  "trace_id": "trace-xyz-789",
  "request_id": "req-abc-123",
  "extra": {
    "params": {"query": "..."},
    "result_count": 15
  }
}
```

**Log Levels:**
- `DEBUG` - Detailed diagnostic info (disabled in production)
- `INFO` - Normal operation events (tool invocations, auth success)
- `WARNING` - Recoverable issues (rate limit exceeded, cache miss)
- `ERROR` - Errors requiring attention (DB connection failures, tool errors)
- `CRITICAL` - System-level failures (startup failures, disk full)

### Distributed Tracing (OpenTelemetry)

**Configuration:**
```bash
export OTEL_SERVICE_NAME="cineca-agentic-platform"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://jaeger:4318"
export OTEL_TRACES_SAMPLER="parentbased_always_on"
```

**Trace Context Propagation:**
- `traceparent` header (W3C standard)
- `X-Request-ID` header (correlation ID)
- `X-Trace-ID` header (distributed trace ID)

---

## Deployment & Operations

### Docker Compose Deployment

**Quick Start:**
```bash
# Clone repository
git clone https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform.git
cd Cineca-Agentic-Platform

# Configure environment
cp .env.example .env
# Edit .env: Set JWT_SECRET, DB_PASSWORD, etc.

# Start all services
docker compose up -d

# Verify health
curl http://localhost:8000/v1/health/ready

# View logs
docker compose logs -f app

# Stop services
docker compose down
```

**Service Architecture (12 containers):**
```
app                  # FastAPI application
worker               # Background job processor
postgres             # Primary persistence
redis                # Cache & queues
memgraph             # Graph database
ollama               # Local LLM inference
prometheus           # Metrics storage
grafana              # Visualization
ui                   # Streamlit interface
llm-mock-planner     # Mock LLM (testing)
llm-mock-workerA     # Mock LLM (testing)
llm-mock-workerB     # Mock LLM (testing)
```

**Port Mapping:**
```
8000   → app         (FastAPI API)
8501   → ui          (Streamlit UI)
5432   → postgres    (PostgreSQL)
6379   → redis       (Redis)
7687   → memgraph    (Bolt protocol)
3000   → memgraph    (Memgraph Lab UI)
9090   → prometheus  (Metrics)
3001   → grafana     (Dashboards)
11434  → ollama      (LLM API)
```

### Environment Configuration

**Required Variables:**
```bash
# Application
APP_ENV=production
LOG_LEVEL=INFO
ENABLE_DOCS=false

# Databases
DB_HOST=postgres
DB_PORT=5432
DB_NAME=cineca_platform
DB_USER=cineca_user
DB_PASSWORD=CHANGE_ME_IN_PRODUCTION

REDIS_URL=redis://redis:6379/0

MG_HOST=memgraph
MG_PORT=7687

# Authentication
OIDC_ISSUER=https://auth.example.com
OIDC_AUDIENCE=cineca-api
OIDC_JWKS_URL=https://auth.example.com/.well-known/jwks.json

# Security
JWT_SECRET=REPLACE_WITH_STRONG_SECRET
RATE_LIMIT_MODE=prod
RATE_LIMIT_BACKEND=redis

# Features
ENABLE_ADMIN_ROUTES=1
USE_POSTGRES_JOBS=true
INTERNAL_DB_UTILS_ENABLED=true
```

**Complete Reference:** See `docs/environment-variables.md` (40+ variables)

### Health Checks

**Liveness (Container Running?):**
```bash
curl http://localhost:8000/v1/health/live
# Response: {"ok": true}
```

**Readiness (Ready for Traffic?):**
```bash
curl http://localhost:8000/v1/health/ready
# Response: {
#   "ok": true,
#   "checks": {
#     "postgres": "ok",
#     "redis": "ok",
#     "memgraph": "ok"
#   }
# }
```

**Startup (Detailed Diagnostics):**
```bash
curl http://localhost:8000/v1/health/startup
# Response: {
#   "ok": true,
#   "migrations_applied": true,
#   "dependencies": {
#     "postgres": {"status": "connected", "latency_ms": 2},
#     "redis": {"status": "connected", "latency_ms": 1},
#     "memgraph": {"status": "connected", "latency_ms": 5}
#   },
#   "configuration": {
#     "rate_limit_mode": "prod",
#     "job_store_backend": "postgres"
#   }
# }
```

### Operator Runbook

**See:** `docs/OPERATOR_RUNBOOK.md` for detailed procedures:

- **Deployment Checklist** - Pre-deployment validation steps
- **Configuration Guide** - Required and optional settings
- **Monitoring Setup** - Grafana dashboard configuration
- **Troubleshooting** - Common issues and resolutions
- **Backup & Restore** - Database backup procedures
- **Secret Rotation** - JWT, DB password rotation
- **Scaling Guide** - Horizontal and vertical scaling
- **Incident Response** - Emergency procedures

### Production Checklist

**Run automated validation:**
```bash
./scripts/production_checklist.sh
```

**Manual Verification:**
- [ ] All environment variables set
- [ ] JWT_SECRET is strong (32+ characters)
- [ ] Database passwords rotated
- [ ] OIDC issuer configured
- [ ] Rate limiting enabled (RATE_LIMIT_MODE=prod)
- [ ] Admin routes protected (ENABLE_ADMIN_ROUTES=1)
- [ ] Docs disabled in prod (ENABLE_DOCS=false)
- [ ] Backup schedule configured
- [ ] Monitoring alerts configured
- [ ] Incident response plan documented

---

## Development Workflow

### Local Development Setup

```bash
# 1. Clone repository
git clone https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform.git
cd Cineca-Agentic-Platform

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Configure environment
cp .env.example .env
# Edit .env for local settings

# 5. Start dependencies (docker-compose)
docker compose up -d postgres redis memgraph ollama

# 6. Run migrations
alembic upgrade head

# 7. Start development server
uvicorn src.app:app --reload --host 0.0.0.0 --port 8000

# 8. Open in browser
open http://localhost:8000/docs
```

### Code Quality Tools

**Linting & Formatting:**
```bash
# Format code
black src/ tests/
ruff format src/ tests/

# Lint code
ruff check src/ tests/

# Type checking
mypy src/
```

**Security Scanning:**
```bash
# Python security linter
bandit -r src/

# Dependency vulnerability scan
pip-audit
```

**Pre-Commit Hooks:**
```bash
# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

### Code Organization

```
src/
├── app.py                  # FastAPI application
├── config.py               # Configuration (Pydantic Settings)
├── logging_setup.py        # Structured logging
│
├── routers/                # API endpoints (21 modules)
│   ├── health.py
│   ├── auth.py
│   ├── agent.py
│   ├── tools.py
│   └── ...
│
├── services/               # Business logic (14 modules)
│   ├── agent_service.py
│   ├── orchestrator_service.py
│   ├── tool_service.py
│   └── ...
│
├── repositories/           # Data access layer
│   └── tenants_repository.py
│
├── schemas/                # Pydantic models (request/response)
│   ├── agents.py
│   ├── tools.py
│   ├── jobs.py
│   └── ...
│
├── security/               # Security components (17 modules)
│   ├── auth.py             # Authentication
│   ├── authorization.py    # Authorization
│   ├── intent_filter.py    # Prompt injection detection
│   ├── output_guard.py     # Cypher validation
│   ├── pii_scrubber.py     # PII redaction
│   ├── rate_limit.py       # Rate limiting
│   └── audit.py            # Audit logging
│
├── mcp/                    # MCP tools & registry
│   ├── manifest.json       # Tool manifest (32 tools)
│   ├── policies.yaml       # RBAC policies
│   ├── core/               # Core MCP logic
│   └── tools/              # Tool implementations (17 categories)
│
├── adapters/               # External service adapters
│   ├── llm_adapter.py      # LLM providers
│   └── memgraph_adapter.py # Graph database
│
├── middleware/             # FastAPI middleware
│   ├── request_id.py
│   ├── logging.py
│   └── ...
│
├── observability/          # Metrics & tracing
│   ├── metrics.py
│   └── tracing.py
│
├── background/             # Background tasks
│   └── jobs.py
│
└── workers/                # Worker services
    └── jobs_worker.py
```

### Git Workflow

**Branching Strategy:**
```
main                    # Production-ready code
├── chore/*             # Maintenance tasks
├── feature/*           # New features
├── fix/*               # Bug fixes
└── docs/*              # Documentation updates
```

**Commit Convention:**
```
type(scope): description

Types: feat, fix, docs, chore, refactor, test, style
Scopes: api, tools, security, db, ci, etc.

Example:
feat(tools): add graph.secure_query with NL→Cypher translation
fix(auth): correct JWT expiry validation
docs(api): update OpenAPI examples for /v1/agents/sessions
```

---

## Testing Strategy

### Test Suite Overview

**Total Tests:** 931 passing (100% green)  
**Coverage:** 60%+ overall (80% for core modules)  
**Duration:** ~2 minutes (full suite)

### Test Categories

#### 1. Unit Tests (`tests/unit/`)
**Coverage:** Individual functions, classes, utilities

```python
# Example: Test PII scrubber
def test_pii_scrubber_redacts_email():
    text = "Contact user@example.com for details"
    result = scrub_pii(text)
    assert "[EMAIL]" in result
    assert "user@example.com" not in result
```

**Total:** ~400 tests

#### 2. Integration Tests (`tests/integration/`)
**Coverage:** API endpoints, database operations, service interactions

```python
# Example: Test tenant creation
async def test_create_tenant(client, auth_headers):
    response = await client.post(
        "/v1/admin/tenants",
        json={"name": "Test Corp", "admin_email": "admin@test.com"},
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Corp"
```

**Total:** ~400 tests

#### 3. End-to-End Tests (`tests/e2e/`)
**Coverage:** Full workflows, multi-step scenarios

```python
# Example: Agent session workflow
async def test_agent_session_workflow(client, auth_headers):
    # Create session
    create_resp = await client.post(
        "/v1/agents/sessions",
        json={"agent_id": "assistant"},
        headers=auth_headers
    )
    session_id = create_resp.json()["session_id"]
    
    # Send message
    step_resp = await client.post(
        f"/v1/agents/sessions/{session_id}/steps",
        json={"user_message": "Hello"},
        headers=auth_headers
    )
    assert step_resp.status_code == 200
    
    # Get history
    history_resp = await client.get(
        f"/v1/agents/sessions/{session_id}",
        headers=auth_headers
    )
    assert len(history_resp.json()["history"]) == 2
```

**Total:** ~100 tests

#### 4. Security Tests (`tests/security/`)
**Coverage:** Authentication, authorization, input validation, injection attacks

```python
# Example: Test RBAC enforcement
async def test_admin_endpoint_requires_admin_scope(client, user_token):
    # User token without admin scope
    response = await client.get(
        "/v1/admin/tenants",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 403
```

**Total:** ~30 tests

### Test Infrastructure

**Fixtures (`tests/conftest.py`):**
- `client` - Async HTTP client (httpx)
- `db_session` - Database session with rollback
- `redis_client` - Redis client with cleanup
- `auth_headers` - Valid JWT token
- `admin_headers` - Admin JWT token
- `user_headers` - User JWT token

**Mocks:**
- `mock_llm` - Deterministic LLM responses
- `mock_memgraph` - In-memory graph database
- `mock_oidc` - OIDC provider stub

### Running Tests

**Full Suite:**
```bash
pytest
```

**Specific Category:**
```bash
pytest tests/unit/           # Unit tests only
pytest tests/integration/    # Integration tests only
pytest tests/e2e/            # E2E tests only
```

**With Coverage:**
```bash
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

**Parallel Execution:**
```bash
pytest -n auto  # Use all CPU cores
```

**Watch Mode:**
```bash
ptw -- tests/  # Re-run on file changes
```

### CI/CD Pipeline (GitHub Actions)

**Workflow:** `.github/workflows/test.yml`

**Steps:**
1. Checkout code
2. Set up Python 3.11
3. Install dependencies
4. Start services (PostgreSQL, Redis, Memgraph)
5. Run migrations
6. Run linters (ruff, black, mypy)
7. Run security scanners (bandit, pip-audit)
8. Run test suite
9. Upload coverage report
10. Build Docker image
11. Push to registry (on main branch)

**Status Badge:**
```
[![Tests](https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform/workflows/Tests/badge.svg)](https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform/actions)
```

---

## Production Readiness

### Current Status

**Production Readiness Score:** 8/10

**Completed:**
- ✅ Comprehensive test suite (931 tests passing)
- ✅ Database migrations with rollback support
- ✅ Multi-database architecture (PostgreSQL, Redis, Memgraph)
- ✅ Background job processing with worker service
- ✅ Rate limiting with production configuration
- ✅ Idempotency for safe retries
- ✅ ETag caching for performance
- ✅ RBAC with fine-grained scopes
- ✅ Audit logging
- ✅ Structured logging with correlation IDs
- ✅ Prometheus metrics + Grafana dashboards
- ✅ OpenAPI 3.1 specification
- ✅ Docker Compose deployment
- ✅ Health checks (liveness, readiness, startup)
- ✅ Security guardrails (intent filter, output guard, PII scrubbing)
- ✅ Operator runbook

**In Progress:**
- 🟡 Kubernetes deployment manifests
- 🟡 Load testing & performance benchmarks
- 🟡 Security audit (penetration testing)
- 🟡 Disaster recovery procedures

### Known Limitations

1. **Scalability:**
   - Single-instance worker (horizontal scaling requires queue partitioning)
   - In-memory session storage (should migrate to Redis for multi-instance deployments)

2. **Observability:**
   - OpenTelemetry tracing not fully implemented (optional)
   - Log aggregation not configured (requires ELK/Loki)

3. **Security:**
   - HTTPS termination at reverse proxy (not built-in)
   - Secrets management via environment variables (should use vault)

4. **Operations:**
   - No automated backups configured
   - No blue-green deployment strategy
   - No canary release process

### Roadmap to 1.0

**Phase 1: Stability (Weeks 1-2)**
- [ ] Load testing (target: 1000 req/s sustained)
- [ ] Memory profiling & optimization
- [ ] Connection pool tuning
- [ ] Cache hit rate optimization

**Phase 2: Observability (Weeks 3-4)**
- [ ] Complete OpenTelemetry integration
- [ ] Log aggregation setup (Loki or ELK)
- [ ] Custom Grafana alerts
- [ ] SLO/SLI definitions

**Phase 3: Operations (Weeks 5-6)**
- [ ] Kubernetes Helm charts
- [ ] Automated backup/restore scripts
- [ ] Blue-green deployment guide
- [ ] Disaster recovery runbook

**Phase 4: Security (Weeks 7-8)**
- [ ] External security audit
- [ ] Penetration testing
- [ ] Secrets management integration (Vault)
- [ ] TLS/mTLS configuration

---

## Future Enhancements

### Short-Term (3-6 months)

1. **Graph Embeddings**
   - Vector embeddings for semantic search
   - Integration with embedding models (text-embedding-ada-002)
   - Similarity queries on graph nodes

2. **Advanced Agent Capabilities**
   - Multi-agent collaboration
   - Agent planning & reasoning
   - Tool chaining & composition

3. **Enhanced Multi-Tenancy**
   - Tenant quotas & usage tracking
   - Per-tenant rate limits
   - Tenant-specific model preferences

4. **Web Admin Console**
   - Tool management UI
   - Agent session viewer
   - Metrics dashboard
   - User/tenant administration

### Medium-Term (6-12 months)

1. **Kubernetes Deployment**
   - Helm charts
   - Auto-scaling policies
   - Service mesh integration (Istio)

2. **Real-Time Event Streaming**
   - Kafka integration for event bus
   - Change data capture (CDC) from databases
   - Real-time analytics pipelines

3. **Advanced Security**
   - Fine-grained permissions (resource-level ACLs)
   - Audit log analytics & anomaly detection
   - Automated threat response

4. **Performance Optimizations**
   - Query result caching with TTL
   - Database query optimization
   - CDN integration for static assets

### Long-Term (12+ months)

1. **Multi-Region Deployment**
   - Global database replication
   - Region-aware routing
   - Data residency compliance

2. **Advanced Analytics**
   - Graph neural networks
   - Predictive analytics
   - Anomaly detection

3. **Extensibility**
   - Plugin architecture for custom tools
   - Custom LLM provider adapters
   - Marketplace for community tools

4. **Enterprise Features**
   - Single Sign-On (SSO) integration
   - Advanced billing & metering
   - Compliance certifications (SOC2, ISO 27001)

---

## References & Resources

### Documentation

- **README.md** - Project overview & quick start
- **docs/OPERATOR_RUNBOOK.md** - Production deployment guide
- **docs/architecture.md** - System architecture details
- **docs/API_DOCUMENTATION_COMPLETE.md** - API reference
- **docs/MCP_TOOLS_REFERENCE.md** - MCP tools catalog
- **docs/SECURITY.md** - Security policy & procedures
- **docs/TESTING_GUIDE.md** - Testing best practices

### External Documentation

- **FastAPI** - https://fastapi.tiangolo.com
- **PostgreSQL** - https://www.postgresql.org/docs/
- **Redis** - https://redis.io/docs/
- **Memgraph** - https://memgraph.com/docs/
- **Prometheus** - https://prometheus.io/docs/
- **Grafana** - https://grafana.com/docs/

### Research Papers

(Add relevant academic papers related to the thesis)

### GitHub Repository

https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform

---

## Appendix

### A. Configuration Reference

See `docs/environment-variables.md` for complete list (40+ variables).

### B. API Endpoint Reference

See `api/openapi.json` for OpenAPI 3.1 specification.

### C. Database Schema

See `db/postgres_control/models/` for SQLAlchemy models.

### D. Metrics Reference

See `docs/observability/metrics-reference.md` for Prometheus metrics.

### E. Glossary

- **MCP** - Model Control Protocol (tool standardization framework)
- **RBAC** - Role-Based Access Control
- **SSE** - Server-Sent Events
- **OIDC** - OpenID Connect
- **JWT** - JSON Web Token
- **ACID** - Atomicity, Consistency, Isolation, Durability
- **TTL** - Time To Live
- **ETag** - Entity Tag (HTTP caching)
- **JWKS** - JSON Web Key Set
- **NL** - Natural Language
- **LLM** - Large Language Model
- **PII** - Personally Identifiable Information

---

**Document Version:** 1.0  
**Last Updated:** November 1, 2025  
**Maintained By:** Arman Feili  
**Contact:** arman.feili@students.uniroma1.it

---

*This document is part of the ILP Thesis 2025 project at Sapienza University of Rome.*

