# Cineca Agentic Platform - Complete Architecture Reference

> **Version**: 1.0.0  
> **Last Updated**: December 2025  
> **Platform**: AI-Powered Multi-Tenant Agentic System

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Platform Overview](#platform-overview)
3. [High-Level Architecture](#high-level-architecture)
4. [Core Infrastructure](#core-infrastructure)
   - [Database Layer](#database-layer)
   - [Caching Layer](#caching-layer)
   - [Configuration System](#configuration-system)
5. [Application Layer](#application-layer)
   - [API Framework](#api-framework)
   - [Authentication & Security](#authentication--security)
   - [Services Layer](#services-layer)
6. [AI/ML Components](#aiml-components)
   - [LLM Integration](#llm-integration)
   - [Agent Orchestration](#agent-orchestration)
   - [MCP Tools Framework](#mcp-tools-framework)
7. [Background Processing](#background-processing)
   - [Jobs Framework](#jobs-framework)
   - [Workers System](#workers-system)
   - [Background Manager](#background-manager)
8. [Observability Stack](#observability-stack)
9. [User Interfaces](#user-interfaces)
10. [Deployment & Operations](#deployment--operations)
11. [Testing Framework](#testing-framework)
12. [Component Interconnections](#component-interconnections)
13. [Quick Reference](#quick-reference)

---

## Executive Summary

The **Cineca Agentic Platform** is a comprehensive, enterprise-grade AI platform designed for managing LLM providers, orchestrating intelligent agents, executing MCP-compatible tools, and processing background jobs in a multi-tenant environment. Built on FastAPI with PostgreSQL, Memgraph, and Redis as core data stores, it provides a complete ecosystem for AI-powered workflows.

### Key Capabilities

| Capability | Description |
|------------|-------------|
| **Multi-LLM Orchestration** | Support for OpenAI, Ollama, Azure, and custom LLM providers with automatic failover |
| **Agent Sessions** | Stateful multi-step agent interactions with planning and execution phases |
| **MCP Tool Framework** | Model Context Protocol tools for graph operations, caching, and system management |
| **Graph Database** | Memgraph integration for knowledge graphs and complex relationship queries |
| **Multi-Tenancy** | Full tenant isolation with RBAC and per-tenant configurations |
| **Real-time Updates** | SSE streaming for job progress and agent execution status |
| **Enterprise Security** | JWT/OIDC authentication, rate limiting, PII scrubbing, and audit logging |

---

## Platform Overview

### Technology Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Interfaces                                 │
│  ┌─────────────────────────┐  ┌─────────────────────────────────────────┐   │
│  │   UI Agent (Next.js)    │  │    Control Panel (Streamlit)           │   │
│  │   - Chat Interface      │  │    - Admin Dashboard                   │   │
│  │   - Agent Visualization │  │    - Model Management                  │   │
│  └─────────────────────────┘  └─────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                              FastAPI Backend                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Routers: Health | Auth | Tools | Jobs | Agents | Models | Tenants  │   │
│  │  Middleware: CORS | Rate Limiting | Observability | Error Handling  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                              Services Layer                                  │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌──────────────┐  │
│  │  Orchestrator  │ │ Intent Classif │ │ Session Service│ │ Job Service  │  │
│  │  - Planning    │ │ - Pattern Match│ │ - State Mgmt   │ │ - Lifecycle  │  │
│  │  - Execution   │ │ - LLM Fallback │ │ - History      │ │ - Events     │  │
│  └────────────────┘ └────────────────┘ └────────────────┘ └──────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│                              Adapters Layer                                  │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌──────────────┐  │
│  │   LLM Adapter  │ │   MCP Client   │ │ Memgraph Adapt │ │ Redis Adapter│  │
│  │  - Multi-prov  │ │  - Tool Disco  │ │  - Cypher Ops  │ │ - Caching    │  │
│  │  - Failover    │ │  - Invocation  │ │  - CRUD        │ │ - Queues     │  │
│  └────────────────┘ └────────────────┘ └────────────────┘ └──────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│                              Data Layer                                      │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌──────────────┐  │
│  │   PostgreSQL   │ │    Memgraph    │ │     Redis      │ │    Ollama    │  │
│  │  - Tenants     │ │  - Knowledge   │ │  - Cache       │ │  - Local LLM │  │
│  │  - Jobs        │ │  - Graph       │ │  - Queues      │ │  - Models    │  │
│  │  - Agents      │ │  - Relations   │ │  - Rate Limits │ │  - Inference │  │
│  └────────────────┘ └────────────────┘ └────────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## High-Level Architecture

### Request Flow

```
User Request
     │
     ▼
┌─────────────────┐
│  FastAPI Router │◄── Authentication (JWT/OIDC)
└────────┬────────┘    Rate Limiting
         │             Observability Middleware
         ▼
┌─────────────────┐
│ Intent Classifier│◄── Pattern Matching
└────────┬────────┘    LLM Fallback
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────────┐
│ Chat  │ │  Graph/   │
│ Mode  │ │ Admin/etc │
└───┬───┘ └─────┬─────┘
    │           │
    ▼           ▼
┌─────────────────────┐
│    Orchestrator     │◄── LLM Planning
│  (Multi-step agent) │    Tool Execution
└──────────┬──────────┘    Metrics Collection
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌─────────┐
│ LLM API │ │MCP Tools│◄── Graph Queries
└────┬────┘ └────┬────┘    Cache Ops
     │           │         Security Tools
     ▼           ▼
┌─────────────────────┐
│   Response Builder  │◄── Output Normalization
└──────────┬──────────┘    Metrics Aggregation
           │
           ▼
     API Response
```

---

## Core Infrastructure

### Database Layer

The platform uses three database systems, each optimized for specific use cases:

#### PostgreSQL (Relational Control Plane)

**Purpose**: Authoritative data store for tenants, jobs, agents, providers, and audit logs.

**Key Features**:
- **26 Alembic Migrations**: Version-controlled schema evolution
- **Connection Pooling**: QueuePool with configurable size
- **Optimistic Locking**: Version columns with auto-increment triggers
- **Multi-Tenancy**: Full tenant isolation with RBAC support

**Core Tables**:
| Table | Purpose |
|-------|---------|
| `tenants` | Organization/customer tenant definitions |
| `jobs`, `job_events` | Asynchronous job management with event logging |
| `agent_sessions`, `agent_steps`, `agent_runs` | Agent execution tracking |
| `providers`, `provider_secrets` | LLM provider registry with encrypted credentials |
| `model_instances`, `model_defaults` | Model configuration and defaults |
| `tools`, `tool_invocations` | Tool definitions and execution audit |
| `audit_logs` | Administrative action audit trail |

**Configuration**:
```bash
DB_HOST=postgres
DB_PORT=5432
DB_NAME=cineca_platform
DB_USER=cineca_user
DB_SSLMODE=disable
DB_POOL_SIZE=10
```

#### Memgraph (Graph Database)

**Purpose**: Knowledge graph storage for bioinformatics workflows and complex relationship queries.

**Key Features**:
- **Cypher Query Language**: Full Cypher support for graph operations
- **gqlalchemy Integration**: Python ORM for graph operations
- **Schema Support**: Nodes (User, Institution, Task, File) and Relationships

**Graph Schema**:
```cypher
(User)-[:WORKS_AT]->(Institution)
(User)-[:RUNS]->(Task)
(Task)<-[:INPUT]-(File)
(Task)-[:OUTPUT]->(File)
```

**Configuration**:
```bash
MG_HOST=memgraph
MG_PORT=7687
MG_USER=
MG_PASSWORD=
```

#### Redis (Cache & Queues)

**Purpose**: High-performance caching, job queues, rate limiting, and distributed coordination.

**Key Features**:
- **Multi-Purpose Storage**: Caching, queues, rate limits, session state
- **TTL Management**: Automatic expiration for cached data
- **Lua Scripts**: Atomic operations for complex workflows
- **Graceful Degradation**: In-memory fallback when unavailable

**Key Namespaces**:
| Prefix | Purpose |
|--------|---------|
| `cache:` | General key-value cache |
| `jobs:` | Job documents and state |
| `rate:` | Rate limiting counters |
| `session:` | Agent session state |
| `idem:` | Idempotency keys |

**Configuration**:
```bash
REDIS_URL=redis://redis:6379/0
```

### Caching Layer

The Redis cache module provides comprehensive caching infrastructure:

**Core Components**:
- **Synchronous Client**: `cache_get()`, `cache_set()`, `cache_delete()`
- **Asynchronous Client**: Connection pooling with health checks
- **Agent Helpers**: Session caching, step sequencing, distributed locks
- **Job Store**: TTL-based job document management
- **Rate Limiting**: Sliding window algorithm with quotas

**Cache Operations**:
```python
from db.redis_cache import cache_get_json, cache_set_json

# JSON caching with TTL
cache_set_json("user:123", {"name": "Alice"}, ex=3600)
user = cache_get_json("user:123")
```

### Configuration System

The platform uses a layered configuration approach:

**Base Configuration** (`src/config.py`):
- Pydantic Settings with environment variable support
- `.env` file loading with validation
- Type-safe configuration access

**Config Modules** (`src/config_modules/`):
- **ComputeConfig**: Device-aware LLM execution settings
- Automatic timeout and concurrency tuning
- Test mode configurations

**Agent Policies** (`src/agent_policies/`):
- **Retry Policies** (`retry.yaml`): Exponential backoff, circuit breakers
- **Role Policies** (`roles.yaml`): RBAC with tool access control

---

## Application Layer

### API Framework

The REST API is built on FastAPI with OpenAPI 3.1.0 specifications.

**API Versions**:
- **v1 (Stable)**: Full production API with RBAC and multi-tenancy
- **v2 (Preview)**: Experimental endpoints

**Core Endpoints**:

| Category | Endpoints | Description |
|----------|-----------|-------------|
| **Health** | `/v1/health/live`, `/v1/health/ready`, `/v1/health/startup` | Container orchestration probes |
| **Auth** | `/v1/auth/me` | Current user claims |
| **Tools** | `/v1/tools`, `/v1/tools/{name}/invocations` | MCP tool discovery and invocation |
| **Jobs** | `/v1/jobs`, `/v1/jobs/{id}/stream` | Async job management with SSE |
| **Agents** | `/v1/agents/sessions`, `/v1/agents/runs` | Agent session and run management |
| **Models** | `/v1/models/instances`, `/v1/models/providers` | LLM model management |
| **Tenants** | `/v1/tenants` | Multi-tenant administration |

**Authentication**:
```bash
# JWT Bearer Token
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     https://api.example.com/v1/endpoint
```

**Permission Scopes**:
| Scope | Description |
|-------|-------------|
| `user:me` | Basic user access |
| `tools:basic` | Basic tool invocation |
| `tools:all` | Full tool access |
| `admin:all` | Administrative access |

### Authentication & Security

The security framework provides comprehensive protection:

**Authentication**:
- **JWT/OIDC**: Auth0 integration with JWKS caching
- **Token Validation**: Signature verification, expiration checks
- **Principal Extraction**: User identity and permissions from claims

**Authorization**:
- **RBAC**: Role-based access control with scope mapping
- **Permission Checking**: Granular permission enforcement
- **Tenant Isolation**: Multi-tenant data separation

**Security Controls**:
- **Rate Limiting**: Sliding window with Redis/memory backends
- **Input Validation**: Pydantic-based request validation
- **Output Guards**: Cypher query protection, PII scrubbing
- **Audit Logging**: Comprehensive security event tracking

**Error Handling**:
```json
{
  "type": "https://httpstatuses.com/404",
  "title": "Session Not Found",
  "status": 404,
  "detail": "Agent session 'session-123' does not exist.",
  "extensions": {
    "error_code": "session_not_found"
  }
}
```

### Services Layer

Core business logic is implemented in the services layer:

**Orchestrator** (`src/services/orchestrator.py`):
- Central coordination engine for agent runs
- Multi-LLM support with automatic failover
- Tool integration with MCP protocol
- Intent-based routing (Chat, Graph, Admin, Security, Dangerous)

**Session Service** (`src/services/session.py`):
- Chat session management with message history
- Redis-backed or in-memory storage
- TTL support with automatic expiration

**Intent Classifier** (`src/services/intent_classifier.py`):
- Heuristic-based intent classification
- Pattern matching with regex
- LLM fallback for ambiguous cases
- Safety-first processing (dangerous patterns checked first)

**Default Model Resolver**:
- Centralized default LLM resolution
- Redis caching with PostgreSQL fallback
- Tenant-aware model selection

---

## AI/ML Components

### LLM Integration

The platform supports multiple LLM providers with resilient orchestration:

**Supported Providers**:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Azure OpenAI
- Ollama (Local models)
- Custom providers

**Resilience Features**:
- **Circuit Breaker**: Automatic blocking of failing providers
- **Automatic Failover**: Priority-based provider fallback
- **Cost Tracking**: Per-provider budget enforcement
- **Health Monitoring**: Continuous availability checks

**Configuration**:
```bash
LLM_PROVIDER=local-llamacpp
OLLAMA_BASE_URL=http://ollama:11434/v1
DEFAULT_MODEL_NAME=phi3:mini
```

### Agent Orchestration

Agents execute complex multi-step workflows:

**Agent Run Flow**:
1. **Intent Classification**: Determine operational mode
2. **TODO Creation**: LLM-driven task planning
3. **Step Execution**: Tool invocations and LLM calls
4. **Result Aggregation**: Metrics collection and response building

**Execution Modes**:
| Mode | Description | Confidence Threshold |
|------|-------------|---------------------|
| Chat | General conversation | 0.60 |
| Graph | Memgraph database queries | 0.80 |
| Security | Permission queries | 0.75 |
| Admin | Administrative operations | 0.70 |
| Dangerous | Heavy/destructive ops (blocked) | 0.70 |

**Session Management**:
```python
# Create session
POST /v1/agents/sessions
{
  "prompt": "Show me all Blast nodes",
  "temperature": 0.2,
  "max_steps": 8
}

# Get run status
GET /v1/agents/runs/{run_id}
```

### MCP Tools Framework

The Model Context Protocol tools provide graph operations, caching, and system management:

**Tool Categories**:

| Category | Tools | Description |
|----------|-------|-------------|
| **Graph** | `graph.query`, `graph.crud`, `graph.analytics` | Memgraph operations |
| **Cache** | `cache.manage` | Redis caching operations |
| **Catalog** | `catalog.discover` | Tool discovery |
| **Security** | `security.describe_principal` | Permission queries |
| **Data** | `data.archive`, `data.quality` | Data management |

**Tool Invocation**:
```json
POST /v1/tools/graph.query/invocations
{
  "action": "execute",
  "cypher": "MATCH (n:Blast) RETURN n LIMIT 10",
  "principal": {"user_id": "user-123"},
  "tenant": "tenant-1"
}
```

**Response Format**:
```json
{
  "ok": true,
  "action": "execute",
  "data": [...],
  "elapsed_ms": 45
}
```

---

## Background Processing

### Jobs Framework

Asynchronous job management with multiple storage backends:

**Job Lifecycle**:
```
queued → running → finished/failed/cancelled
```

**Storage Backends**:
- **Memory**: Development/testing (no persistence)
- **Redis**: Production (TTL, multi-instance)

**Job Types**:
- `demo`: Configurable sleep duration
- `test`: Instant completion
- `long-running`: Multi-step with progress

**SSE Streaming**:
```bash
GET /v1/jobs/{id}/stream
# Returns: Server-Sent Events with status updates
```

### Workers System

PostgreSQL-backed background workers process jobs from Redis queues:

**Worker Features**:
- Multi-tenant job processing
- Atomic queue operations
- Heartbeat monitoring
- Graceful shutdown handling
- Cancellation support

**Configuration**:
```bash
USE_POSTGRES_JOBS=true
JOB_WORKER_POLL_INTERVAL=1.0
JOB_WORKER_HEARTBEAT_INTERVAL=5.0
ALLOWED_JOB_TYPES=demo,test,long-running
```

### Background Manager

APScheduler-based task scheduling:

**Scheduled Tasks**:
- **Health Monitoring**: Periodic connectivity checks
- **Provider Health**: LLM provider availability monitoring
- **Backups**: Automated archive creation
- **Cleanup**: Age-based pruning of temporary files

**Configuration**:
```python
BackgroundConfig(
    enabled=True,
    health_enabled=True,
    health_interval_seconds=30,
    backup_enabled=False,
    backup_cron="30 2 * * *"
)
```

---

## Observability Stack

### Metrics (Prometheus)

Comprehensive metrics collection:

**HTTP Metrics**:
- `http_requests_total`: Request counters
- `http_request_duration_seconds`: Latency histograms

**Agent Metrics**:
- `agent_runs_total`: Execution counters
- `agent_run_duration_seconds`: Run latency
- `llm_calls_total`: LLM API calls
- `llm_tokens_total`: Token consumption

**Rate Limit Metrics**:
- `rate_limit_exceeded_total`: Violation tracking
- `tenant_quota_exceeded_total`: Quota breaches

### Tracing (OpenTelemetry)

Distributed tracing with OTLP export:

**Configuration**:
```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SAMPLER_RATIO=0.2
```

### Logging

Structured logging with correlation:

**Features**:
- Correlation IDs (X-Request-ID)
- Trace context propagation
- Request timing headers
- Error context binding

---

## User Interfaces

### UI Agent (Next.js)

Modern chat interface for agent interactions:

**Technology Stack**:
- Next.js 14 with App Router
- TypeScript with strict configuration
- Tailwind CSS + Radix UI
- Zustand state management

**Key Features**:
- Role-based authentication (Admin/User)
- Real-time chat with status updates
- Agent run visualization with metrics
- Model selection from backend
- Collapsible orchestration steps

### UI Control Panel (Streamlit)

Administrative dashboard for platform management:

**Key Features**:
- Tab-based navigation
- Authentication with Auth0
- Agent run management
- Job monitoring
- Model provider management
- Tenant administration
- Tool invocation interface
- System health monitoring

---

## Deployment & Operations

### Docker Compose

Multi-service orchestration:

**Core Services**:
- `app`: FastAPI application
- `postgres`: PostgreSQL database
- `memgraph`: Graph database
- `redis`: Cache and queues
- `ollama`: Local LLM serving
- `worker`: Background job processor
- `prometheus`: Metrics collection
- `grafana`: Dashboard visualization

**Deployment Profiles**:
```bash
# Standard deployment
docker compose up -d

# CPU-optimized
docker compose -f docker-compose.yml -f docker-compose.override.dev.yml up -d

# GPU-enabled
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

### Makefile Targets

Comprehensive development workflow automation:

**Core Targets**:
```bash
make dev              # Run FastAPI with auto-reload
make up               # Start all services
make test             # Run test suite
make lint             # Code quality checks
make db-migrate       # Run Alembic migrations
make openapi          # Export OpenAPI spec
```

### Scripts

Operational utilities:

**ETL Loader** (`scripts/etl_load.py`):
- Synthetic data generation
- JSONL file loading
- Batch processing with MERGE

**OpenAPI Export** (`scripts/export_openapi.py`):
- JSON and YAML export
- Schema customization

**Auth0 Token Fetcher** (`fetch_auth0_tokens.sh`):
- Multi-token support (Admin/User/Machine)
- Environment integration

---

## Testing Framework

### Test Categories

| Category | Purpose | Markers |
|----------|---------|---------|
| **Unit** | Component isolation | `@pytest.mark.unit` |
| **Integration** | Component interactions | `@pytest.mark.integration` |
| **E2E** | Full HTTP flows | `@pytest.mark.e2e` |
| **Security** | Security controls | `@pytest.mark.security` |
| **Performance** | Latency budgets | `@pytest.mark.performance` |

### Test Infrastructure

**Fixtures**:
- `app_client`: Synchronous TestClient
- `async_client`: Async HTTPX client
- `db_session`: Database session with transactions
- `fake_redis`: In-memory Redis stub
- `llm_stub`: Deterministic LLM responses

**Running Tests**:
```bash
# Full suite
pytest -q

# Specific categories
pytest -m "unit" -q
pytest -m "integration" -q
pytest -m "security" -q
```

---

## Component Interconnections

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Request Processing                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  HTTP Request ─────► FastAPI Router                                         │
│       │                    │                                                 │
│       │              ┌─────┴─────┐                                          │
│       │              ▼           ▼                                          │
│       │         JWT Validation   Rate Limiting                              │
│       │              │           │                                          │
│       │              ▼           ▼                                          │
│       │         ┌────────────────────┐                                      │
│       │         │  Intent Classifier │                                      │
│       │         └─────────┬──────────┘                                      │
│       │                   │                                                  │
│       │    ┌──────────────┼──────────────┐                                  │
│       │    ▼              ▼              ▼                                  │
│       │  Chat           Graph          Admin                                │
│       │  Mode           Mode           Mode                                 │
│       │    │              │              │                                  │
│       │    └──────────────┼──────────────┘                                  │
│       │                   ▼                                                  │
│       │         ┌─────────────────┐                                         │
│       │         │   Orchestrator  │                                         │
│       │         └────────┬────────┘                                         │
│       │                  │                                                   │
│       │    ┌─────────────┼─────────────┐                                    │
│       │    ▼             ▼             ▼                                    │
│       │  LLM          MCP Tools      Session                                │
│       │  Adapter      Framework      Service                                │
│       │    │             │             │                                    │
│       │    ▼             ▼             ▼                                    │
│       │  Ollama/       Memgraph/     Redis                                  │
│       │  OpenAI        PostgreSQL                                           │
│       │                                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Dependencies

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Dependency Graph                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  API Routers ────────────► Services Layer                                   │
│       │                         │                                            │
│       ├── Auth Middleware       ├── Orchestrator                            │
│       ├── Rate Limit Middleware │   ├── LLM Clients                         │
│       └── Observability         │   ├── MCP Client                          │
│                                 │   ├── Intent Classifier                   │
│                                 │   └── Session Service                     │
│                                 │                                            │
│  Services ───────────────► Adapters Layer                                   │
│       │                         │                                            │
│       ├── Orchestrator          ├── Memgraph Adapter                        │
│       ├── Session Service       ├── LLM Adapter                             │
│       ├── Job Service           ├── MCP Client                              │
│       └── Health Service        └── Redis Cache                             │
│                                                                              │
│  Adapters ───────────────► Data Layer                                       │
│       │                         │                                            │
│       ├── Memgraph Adapter ────► Memgraph DB                                │
│       ├── PostgreSQL Repos ────► PostgreSQL DB                              │
│       ├── Redis Cache ─────────► Redis Server                               │
│       └── LLM Adapter ─────────► Ollama/OpenAI                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `postgres` | PostgreSQL host |
| `MG_HOST` | `memgraph` | Memgraph host |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `LLM_PROVIDER` | `local-llamacpp` | Default LLM provider |
| `OLLAMA_BASE_URL` | `http://ollama:11434/v1` | Ollama API URL |
| `OIDC_ISSUER` | - | Auth0 issuer URL |
| `RATE_LIMIT_MODE` | `prod` | Rate limiting mode |

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `src/` | Application source code |
| `src/adapters/` | External service adapters |
| `src/routers/` | FastAPI route handlers |
| `src/services/` | Business logic layer |
| `src/security/` | Security controls |
| `src/mcp/` | MCP tools framework |
| `db/` | Database modules |
| `db/postgres_control/` | PostgreSQL ORM and migrations |
| `db/memgraph_domain/` | Memgraph graph operations |
| `db/redis_cache/` | Redis caching layer |
| `tests/` | Test suite |
| `ui_agent/` | Next.js chat interface |
| `ui_control_panel/` | Streamlit admin panel |

### Common Commands

```bash
# Development
make dev                    # Start development server
make test                   # Run tests
make lint                   # Code quality

# Docker
docker compose up -d        # Start services
docker compose logs -f app  # View logs
docker compose down         # Stop services

# Database
make db-migrate             # Run migrations
make db-seed                # Seed demo data
make populate               # Populate Memgraph

# Monitoring
curl http://localhost:8000/v1/health/ready
curl http://localhost:8000/metrics
```

---

## Related Documentation

| Document | Location |
|----------|----------|
| API Reference | `api/README_api.md` |
| Security Guide | `docs/security/` |
| Deployment Guide | `docs/deployment/` |
| Architecture Decisions | `docs/adr/` |
| Testing Guide | `tests/README.md` |

---

*This document provides a complete reference for the Cineca Agentic Platform architecture. For detailed component documentation, refer to the individual README files in each module directory.*
