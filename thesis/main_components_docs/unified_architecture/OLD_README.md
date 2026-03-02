# Cineca Agentic Platform

A production-ready, enterprise-grade **Agentic AI Platform** built with FastAPI that enables intelligent LLM-powered agents to interact with graph databases (Memgraph), execute tools via MCP (Model Context Protocol), and orchestrate complex multi-step workflows—all with comprehensive security, observability, and multi-tenancy support.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-3000%2B-brightgreen.svg)](#testing)
[![API Endpoints](https://img.shields.io/badge/endpoints-76-blue.svg)](#api-endpoints)
[![MCP Tools](https://img.shields.io/badge/MCP_tools-34-orange.svg)](#mcp-tools)

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Core Components](#core-components)
  - [API Routers](#api-routers)
  - [MCP Tools System](#mcp-tools-system)
  - [Orchestrator](#orchestrator)
  - [Security & Authentication](#security--authentication)
- [Configuration](#configuration)
- [Database Layer](#database-layer)
- [Testing](#testing)
- [Deployment](#deployment)
- [API Documentation](#api-documentation)
- [API Endpoints](#api-endpoints)
- [MCP Tools](#mcp-tools)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

The **Cineca Agentic Platform** is designed to power intelligent AI agents that can:

- **Query and interact with graph databases** using natural language (Memgraph/Cypher)
- **Execute tools dynamically** through a Model Context Protocol (MCP) system
- **Orchestrate complex multi-step workflows** with planning, reflection, and error recovery
- **Maintain security guardrails** with RBAC, PII scrubbing, and intent filtering
- **Scale to enterprise workloads** with multi-tenancy, caching, and observability

### Use Cases

- **Research Data Exploration**: Query complex research datasets using natural language
- **Automated Workflows**: Build agents that plan and execute multi-step tasks
- **Secure AI Assistants**: Deploy LLM-powered assistants with fine-grained access control
- **Graph Analytics**: Interact with knowledge graphs through conversational interfaces

---

## Key Features

### Agentic AI Capabilities
- **Multi-step Orchestration**: Plan, execute, and reflect on complex workflows
- **Tool Execution**: Dynamic tool discovery and invocation via MCP
- **Intent Classification**: Route queries to appropriate handlers (chat, graph, security)
- **Session Management**: Stateful agent sessions with step tracking

### Enterprise Security
- **OIDC/JWT Authentication**: Auth0 integration with JWKS validation
- **Role-Based Access Control (RBAC)**: Fine-grained permissions per endpoint/tool
- **PII Scrubbing**: Automatic detection and redaction of sensitive data
- **Intent Filtering**: Block malicious or out-of-scope queries
- **Audit Logging**: Comprehensive audit trail for compliance

### Observability
- **Prometheus Metrics**: Request latency, error rates, LLM performance
- **Structured Logging**: JSON logs with correlation IDs and tracing
- **OpenTelemetry Integration**: Distributed tracing support
- **Health Endpoints**: Kubernetes-ready liveness, readiness, and startup probes

### Multi-Tenancy
- **Tenant Isolation**: Data and configuration isolation per tenant
- **Scoped Defaults**: Per-tenant model and provider configurations
- **Quota Management**: Rate limiting per tenant/user

### Database Support
- **PostgreSQL**: Primary data store for jobs, sessions, models, and tenants
- **Memgraph**: Graph database for knowledge graph queries (Cypher)
- **Redis**: Caching, rate limiting, job queues, and SSE event buffers

### LLM Integration
- **Multi-Provider Support**: Ollama, OpenAI, Azure OpenAI, and OpenAI-compatible APIs
- **Model Management**: Register, configure, and manage LLM providers
- **Warmup System**: Pre-load models at startup for fast first requests
- **Fallback Handling**: Graceful degradation when providers are unavailable

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Client Applications                           │
│                    (Web UI, CLI, External Services)                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Application                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   Health    │  │    Auth     │  │   Agents    │  │    Jobs     │     │
│  │  Endpoints  │  │   Router    │  │   Router    │  │   Router    │     │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   Models    │  │   Tools     │  │   Admin     │  │  Tenants    │     │
│  │   Router    │  │   Router    │  │   Router    │  │   Router    │     │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌─────────────────────┐ ┌─────────────────┐ ┌─────────────────────┐
│      Services       │ │   MCP Runtime   │ │    Orchestrator     │
│  ┌───────────────┐  │ │  ┌───────────┐  │ │  ┌───────────────┐  │
│  │ Default Model │  │ │  │   Tool    │  │ │  │   Planning    │  │
│  │   Resolver    │  │ │  │  Registry │  │ │  │   Engine      │  │
│  └───────────────┘  │ │  └───────────┘  │ │  └───────────────┘  │
│  ┌───────────────┐  │ │  ┌───────────┐  │ │  ┌───────────────┐  │
│  │ Model Warmup  │  │ │  │   Tool    │  │ │  │  Reflection   │  │
│  │   Service     │  │ │  │  Policy   │  │ │  │    Loop       │  │
│  └───────────────┘  │ │  └───────────┘  │ │  └───────────────┘  │
│  ┌───────────────┐  │ │  ┌───────────┐  │ │  ┌───────────────┐  │
│  │Intent Classif.│  │ │  │   MCP     │  │ │  │Tool Execution │  │
│  │               │  │ │  │   Tools   │  │ │  │               │  │
│  └───────────────┘  │ │  └───────────┘  │ │  └───────────────┘  │
└─────────────────────┘ └─────────────────┘ └─────────────────────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Data Layer                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │   PostgreSQL    │  │    Memgraph     │  │         Redis           │  │
│  │   ───────────   │  │   ───────────   │  │   ─────────────────     │  │
│  │  • Jobs         │  │  • Knowledge    │  │  • Session Cache        │  │
│  │  • Sessions     │  │    Graph        │  │  • Rate Limiting        │  │
│  │  • Models       │  │  • Cypher       │  │  • Idempotency Keys     │  │
│  │  • Tenants      │  │    Queries      │  │  • SSE Event Buffers    │  │
│  │  • Providers    │  │                 │  │  • Model Resolution     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         LLM Providers                                   │
│       ┌───────────┐    ┌───────────┐    ┌───────────────────────┐       │
│       │  Ollama   │    │  OpenAI   │    │  Azure OpenAI / Other │       │
│       └───────────┘    └───────────┘    └───────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- **Docker & Docker Compose** (recommended)
- **Python 3.10+** (for local development)
- **PostgreSQL 16+**, **Memgraph**, **Redis** (provided via Docker Compose)

### 1. Clone and Setup

```bash
git clone https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform.git
cd Cineca-Agentic-Platform

# Copy environment template
cp .env.example .env

# Edit .env with your configuration (Auth0 credentials, etc.)
```

### 2. Start with Docker Compose

```bash
# Build and start all services
docker compose up -d --build --remove-orphans

# View logs
docker compose logs -f app

# Check health
curl http://localhost:8000/v1/health/live
```

### 3. Access the API

- **API Root**: http://localhost:8000/v1/
- **Swagger UI**: http://localhost:8000/v1/docs
- **Health Check**: http://localhost:8000/v1/health/live

### 4. Fetch Auth0 Tokens (for authenticated endpoints)

```bash
# Fetch fresh tokens
./fetch_auth0_tokens.sh

# Use admin token
export AUTH0_ADMIN_TOKEN=$(cat run/admin-token.txt)
curl -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" http://localhost:8000/v1/user/me
```

---

## Project Structure

```
Cineca-Agentic-Platform/
├── src/                          # Main application source code
│   ├── app.py                    # FastAPI application factory
│   ├── config.py                 # Pydantic settings configuration
│   ├── adapters/                 # External service adapters (LLM, DB)
│   ├── routers/                  # API route handlers
│   │   ├── agent.py              # Agent sessions & steps
│   │   ├── agent_runs.py         # Agent run execution
│   │   ├── tools.py              # Tool discovery & invocation
│   │   ├── jobs.py               # Background job management
│   │   ├── health.py             # Health probes
│   │   ├── auth.py               # Authentication endpoints
│   │   ├── admin.py              # Admin operations
│   │   └── ...
│   ├── mcp/                      # Model Context Protocol implementation
│   │   ├── runtime.py            # MCP tool runtime (RBAC, audit, metrics)
│   │   ├── tool_registry.py      # Central tool registry
│   │   ├── tool_policy.py        # Tool access policies
│   │   └── tools/                # Individual tool implementations
│   │       ├── graph/            # Graph query tools
│   │       ├── data/             # Data manipulation tools
│   │       ├── security/         # Security tools
│   │       └── ...
│   ├── services/                 # Business logic services
│   │   ├── orchestrator.py       # Agent orchestration engine
│   │   ├── default_model_resolver.py  # DMR for model selection
│   │   ├── model_warmup.py       # LLM warmup service
│   │   ├── intent_classifier.py  # Query intent classification
│   │   └── ...
│   ├── security/                 # Security modules
│   │   ├── jwt.py                # JWT validation
│   │   ├── perm.py               # RBAC permissions
│   │   ├── pii_scrubber.py       # PII detection/redaction
│   │   └── ...
│   ├── schemas/                  # Pydantic models
│   └── middleware/               # FastAPI middleware
│
├── db/                           # Database layer
│   ├── postgres_control/         # PostgreSQL repositories & migrations
│   │   ├── repositories/         # Data access objects
│   │   └── migrations/           # Alembic migrations
│   ├── redis_cache/              # Redis caching utilities
│   └── memgraph_domain/          # Memgraph graph database
│
├── tests/                        # Test suite
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   ├── e2e/                      # End-to-end tests
│   ├── security/                 # Security tests
│   ├── agents/                   # Agent-specific tests
│   ├── mcp/                      # MCP tool tests
│   └── ...
│
├── scripts/                      # Utility scripts
│   ├── auth/                     # Authentication scripts
│   ├── database/                 # Database backup/restore
│   ├── deployment/               # Deployment scripts
│   └── ...
│
├── docs/                         # Documentation
├── ui_control_panel/             # Streamlit control panel UI
├── docker-compose.yml            # Docker Compose configuration
├── Dockerfile                    # Multi-stage Docker build
├── Makefile                      # Development commands
└── pyproject.toml                # Python project configuration
```

---

## Core Components

### API Routers

The API is organized into versioned routers under `/v1/`:

| Router | Path | Description |
|--------|------|-------------|
| **Health** | `/v1/health/*` | Liveness, readiness, and startup probes |
| **Auth** | `/v1/auth/*` | Token validation and user info |
| **Agents** | `/v1/agents/*` | Agent sessions and step management |
| **Agent Runs** | `/v1/agent-runs` | Execute agent workflows |
| **Tools** | `/v1/tools/*` | Tool discovery and invocation |
| **Jobs** | `/v1/jobs/*` | Background job management with SSE |
| **Models** | `/v1/models/*` | LLM model instances and providers |
| **Admin** | `/v1/admin/*` | Administrative operations |
| **Tenants** | `/v1/tenants/*` | Multi-tenant management |

### MCP Tools System

The platform implements a **Model Context Protocol (MCP)** inspired tool system:

```
src/mcp/
├── manifest.json          # Tool definitions and schemas
├── runtime.py             # Tool execution runtime
│   ├── ToolContext        # Execution context (principal, tenant, trace)
│   ├── check_permissions  # RBAC enforcement
│   ├── @mcp_tool          # Decorator for tool implementations
│   └── Telemetry          # Prometheus metrics integration
├── tool_registry.py       # Central tool enumeration and validation
├── tool_policy.py         # Access control policies
└── tools/                 # Tool implementations
    ├── graph/             # graph.query, graph.schema, graph.search
    ├── data/              # data.transform, data.validate
    ├── security/          # security.check, security.audit
    ├── cache/             # cache.get, cache.set, cache.invalidate
    ├── user/              # user.profile, user.preferences
    └── system/            # system.health, system.status
```

**Tool Invocation Flow:**
1. Client calls `POST /v1/tools/invocations` with tool name and payload
2. Runtime validates permissions against principal scopes
3. Input payload validated against JSON Schema
4. Tool executed with timeout and cancellation support
5. Result audited and metrics recorded
6. Response returned with standard shape `{ok, action, data, ...}`

### Orchestrator

The **Orchestrator** (`src/services/orchestrator.py`) is the brain of the agentic system:

```python
# Simplified orchestration flow
async def run_agent(goal: str, context: OrchestrationContext):
    # 1. Classify intent (chat, graph query, security check)
    intent = classify_intent(goal)
    
    # 2. Plan steps using LLM
    plan = await planner.create_plan(goal, context)
    
    # 3. Execute steps with tool invocations
    for step in plan.steps:
        result = await execute_step(step, context)
        context.vars.update(result)
    
    # 4. Reflect and synthesize final answer
    answer = await reflector.synthesize(context)
    
    return OrchestrationResult(goal=goal, steps=plan.steps, ...)
```

**Key Features:**
- Multi-LLM coordination (planner, executor, reflector)
- Automatic tool discovery and invocation
- Graph database integration (Memgraph/Cypher)
- Error recovery and retry logic
- Token and step limits for safety

### Security & Authentication

The platform implements defense-in-depth security:

**Authentication:**
```python
# OIDC/JWT validation with Auth0
from src.security.jwt import get_current_principal

@router.get("/protected")
async def protected_endpoint(principal: UserInfo = Depends(get_current_principal)):
    return {"user": principal.sub}
```

**Authorization (RBAC):**
```python
from src.security.perm import require_perms

@router.post("/admin/operation")
@require_perms("admin:all")
async def admin_operation(principal: UserInfo = Depends(get_current_principal)):
    # Only accessible to users with admin:all scope
    ...
```

**Scope Hierarchy:**
- `user:me` - Basic user access
- `tools:basic` - Access to safe tools only
- `tools:all` - Access to all tools
- `admin:all` - Full administrative access

---

## Configuration

Configuration is managed via environment variables and `.env` file:

```bash
# Application
APP_ENV=dev                          # dev, staging, prod
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO

# Database
DB_HOST=postgres
DB_PORT=5432
DB_NAME=cineca_platform
DB_USER=cineca_user
DB_PASSWORD=change_me_now

# Redis
REDIS_URL=redis://redis:6379/0

# Memgraph
MG_HOST=memgraph
MG_PORT=7687

# OIDC Authentication
OIDC_ISSUER=https://your-tenant.auth0.com/
OIDC_AUDIENCE=api://cineca-agentic-platform
OIDC_JWKS_URL=https://your-tenant.auth0.com/.well-known/jwks.json

# LLM Configuration
OLLAMA_BASE_URL=http://ollama:11434/v1
DEFAULT_MODEL_NAME=phi3:mini
LLM_WARMUP_TIMEOUT=300

# Security
RATE_LIMIT_ENABLED=true
RATE_LIMIT_DEFAULT_LIMIT=60
PII_SCRUBBING_ENABLED=true
```

See `src/config.py` for the complete configuration schema.

---

## Database Layer

### PostgreSQL

Primary relational store with repositories pattern:

```
db/postgres_control/
├── database.py              # SQLAlchemy session management
├── models.py                # ORM models
├── repositories/            # Data access layer
│   ├── agents.py            # AgentSessionRepository, AgentStepRepository
│   ├── jobs.py              # JobRepository
│   ├── model_instances.py   # ModelInstanceRepository
│   ├── providers.py         # ProviderRepository
│   └── tenants.py           # TenantRepository
└── migrations/              # Alembic migrations
```

### Redis

Caching, rate limiting, and pub/sub:

```
db/redis_cache/
├── client.py                # Redis client utilities
├── agents.py                # Agent session state caching
├── tools_cache.py           # Tool catalog caching
└── async_client.py          # Async Redis operations
```

### Memgraph

Graph database for knowledge graph queries:

```
db/memgraph_domain/
├── connection.py            # Memgraph connection management
├── queries/                 # Pre-built Cypher queries
└── adapters.py              # Query execution adapters
```

---

## Testing

The project has comprehensive test coverage with **3,000+ test cases** organized by category:

| Metric | Count |
|--------|-------|
| **Total Test Cases** | 3,000+ |
| **Test Files** | 236 |
| **Test Functions** | 2,720 |
| **Test Categories** | 27 |

```bash
# Run all tests
make test

# Run specific test categories
pytest tests/unit/                    # Unit tests
pytest tests/integration/             # Integration tests
pytest tests/security/                # Security tests
pytest tests/agents/                  # Agent tests
pytest tests/mcp/                     # MCP tool tests

# Run with coverage
pytest --cov=src --cov-report=html

# Run security-focused tests
pytest -m security

# Run E2E tests (requires running services)
pytest tests/e2e/
```

**Test Categories:**
- `unit/` - Isolated unit tests with mocks
- `integration/` - Tests with real database connections
- `e2e/` - Full end-to-end API tests
- `security/` - Authentication, authorization, PII scrubbing
- `agents/` - Agent orchestration and sessions
- `mcp/` - MCP tool invocation and policies
- `compliance/` - RFC compliance tests
- `performance/` - Load and performance tests

---

## Deployment

### Docker Compose (Development/Staging)

```bash
# Full stack with all services
docker compose up -d --build

# With GPU support (for local LLM inference)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# With NGINX reverse proxy
docker compose -f docker-compose.yml -f docker-compose.nginx.yml up -d
```

### Production Checklist

1. **Security**
   - [ ] Change all default passwords
   - [ ] Configure OIDC with production Auth0 tenant
   - [ ] Enable HTTPS/TLS termination
   - [ ] Set `APP_ENV=prod`

2. **Database**
   - [ ] Use managed PostgreSQL (AWS RDS, Cloud SQL)
   - [ ] Enable SSL for database connections
   - [ ] Configure connection pooling

3. **Observability**
   - [ ] Enable Prometheus metrics endpoint
   - [ ] Configure OpenTelemetry exporter
   - [ ] Set up log aggregation

4. **Scaling**
   - [ ] Configure Redis cluster for caching
   - [ ] Set appropriate rate limits
   - [ ] Enable horizontal pod autoscaling

---

## API Documentation

Interactive API documentation is available at:

- **Swagger UI**: `http://localhost:8000/v1/docs`
- **OpenAPI JSON**: `http://localhost:8000/v1/openapi.json`

### Key Endpoints

```http
# Health
GET  /v1/health/live       # Liveness probe
GET  /v1/health/ready      # Readiness probe
GET  /v1/health/startup    # Startup probe

# Authentication
GET  /v1/user/me           # Get current user info

# Agents
POST /v1/agents/sessions   # Create agent session
GET  /v1/agents/sessions   # List sessions
POST /v1/agent-runs        # Execute agent run

# Tools
GET  /v1/tools             # Discover available tools
POST /v1/tools/invocations # Invoke a tool

# Jobs
POST /v1/jobs              # Create background job
GET  /v1/jobs              # List jobs
GET  /v1/jobs/{id}/events  # SSE stream for job events

# Models
GET  /v1/models/instances  # List model instances
GET  /v1/models/default    # Get default model
```

---

## API Endpoints

The platform provides **76 API endpoints** across **60 unique paths**, organized into **16 categories**:

| Category | Endpoints | Description |
|----------|-----------|-------------|
| **admin-tenants** | 10 | Multi-tenant management |
| **agents** | 9 | Agent sessions and execution |
| **jobs** | 8 | Background job management |
| **models-instances** | 7 | LLM model instances |
| **models-providers** | 7 | LLM provider management |
| **health** | 6 | Health and readiness probes |
| **internal** | 6 | Internal operations |
| **models-manifests-builtins** | 5 | Built-in model manifests |
| **admin-db** | 4 | Database administration |
| **admin-processes** | 4 | Process management |
| **Batch Operations** | 4 | Bulk operations |
| **tools** | 4 | Tool discovery and invocation |
| **Export/Import** | 3 | Configuration import/export |
| **admin-ops** | 2 | Admin operations |
| **auth** | 1 | Authentication |
| **meta** | 1 | API metadata |

<details>
<summary><strong>Complete Endpoint Reference (Click to expand)</strong></summary>

### Health Endpoints (6)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/health/live` | Liveness probe (canonical) |
| GET | `/v1/health/ready` | Readiness probe (canonical) |
| GET | `/v1/health/startup` | Startup check (canonical, with diagnostics) |
| GET | `/v1/health/components` | All components health (canonical) |
| GET | `/v1/health/components/{name}` | Single component health (canonical) |
| GET | `/v2/health/live` | Liveness probe (v2) |

### Authentication (1)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/auth/me` | Get current user claims from token |

### Agents (9)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/agents/sessions` | Create a new agent session |
| GET | `/v1/agents/sessions` | List agent sessions |
| GET | `/v1/agents/sessions/{session_id}` | Get session details |
| DELETE | `/v1/agents/sessions/{session_id}` | Cancel agent session |
| GET | `/v1/agents/sessions/{session_id}/steps` | List session steps |
| POST | `/v1/agents/sessions/{session_id}/steps` | Add step to session |
| POST | `/v1/agent-runs` | Create an agent run |
| GET | `/v1/agent-runs/{run_id}` | Get agent run by ID |
| GET | `/v1/agent-runs/{run_id}/steps` | Get execution steps for an agent run |

### Tools (4)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/tools` | List available tools (best effort discovery) |
| GET | `/v1/tools/{name}` | Get tool metadata and input schema if available |
| POST | `/v1/tools/{name}/invocations` | Invoke a tool by name (create invocation) |
| GET | `/v1/tools/{name}/invocations/{eid}` | Get tool invocation result |

### Jobs (8)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/jobs` | List caller's jobs (user-scoped) |
| POST | `/v1/jobs` | Create a background job (idempotent) |
| GET | `/v1/jobs/{job_id}` | Get job status (supports conditional caching) |
| DELETE | `/v1/jobs/{job_id}` | Cancel job (202 first, then idempotent 200) |
| GET | `/v1/jobs/{job_id}/events` | Stream job events (SSE with resume, heartbeats, final end) |
| GET | `/v1/admin/jobs` | List all jobs (admin collection) |
| POST | `/v1/admin/jobs` | Create a background job (admin proxy) |
| DELETE | `/v1/admin/jobs/{job_id}` | Cancel job (admin proxy) |

### Models - Instances (7)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/models/instances` | List model instances |
| POST | `/v1/models/instances` | Load/create model instance (Admin Only) |
| GET | `/v1/models/instances/{instance_id}` | Get model instance by ID |
| DELETE | `/v1/models/instances/{instance_id}` | Delete model instance (Admin Only) |
| POST | `/v1/models/instances/{instance_id}/tests` | Test model instance |
| GET | `/v1/models/defaults` | Get default model with precedence resolution |
| PATCH | `/v1/models/defaults` | Set default model with scope support |

### Models - Providers (7)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/admin/models/providers` | List runtime LLM providers |
| POST | `/v1/admin/models/providers/register` | Register a runtime LLM provider |
| GET | `/v1/admin/models/providers/{provider_id}` | Get provider details |
| PATCH | `/v1/admin/models/providers/{provider_id}` | Patch provider details |
| DELETE | `/v1/admin/models/providers/{provider_id}` | Delete/unregister a provider |
| PUT | `/v1/admin/models/providers/default` | Set a provider as default/global (or per-tenant) |
| GET | `/v1/admin/models/providers/main` | Get resolved main LLM provider for a tenant (or global if none) |

### Models - Manifests & Builtins (5)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/admin/models/manifests/builtins` | List built-in manifests |
| POST | `/v1/admin/models/manifests/builtins/staged` | Stage remote manifest |
| POST | `/v1/admin/models/manifests/builtins/activations` | Activate latest staged manifest |
| GET | `/v1/admin/models/manifests/builtins/history` | List activation history |
| POST | `/v1/admin/models/manifests/builtins/rollbacks` | Rollback to previous active manifest |

### Admin - Tenants (10)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/admin/tenants` | List tenants |
| POST | `/v1/admin/tenants` | Create tenant |
| GET | `/v1/admin/tenants/{tenant_id}` | Get tenant by ID |
| PATCH | `/v1/admin/tenants/{tenant_id}` | Update tenant (partial) |
| DELETE | `/v1/admin/tenants/{tenant_id}` | Delete tenant |

### Admin - Database (4)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/admin/db/counts` | Get database counts (Admin) |
| POST | `/v1/admin/db/jobs` | Create database maintenance job (Admin) |
| GET | `/v1/admin/db/jobs/{job_id}` | Get database job status (Admin) |
| DELETE | `/v1/admin/db/jobs/{job_id}` | Cancel database job (Admin) |

### Admin - Processes (4)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/admin/processes` | List active and recent built-in processes |
| GET | `/v1/admin/processes/history/manifests` | Get manifest activation history |
| GET | `/v1/admin/processes/history/processes` | Get process lifecycle event history |
| DELETE | `/v1/admin/processes/{pid}` | Stop a built-in process by PID |

### Admin - Operations (2)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/admin/ops/auto-start-override` | Override auto-start behavior (Admin) |
| GET | `/v1/admin/ops/preview-staged` | Preview staged manifests (Admin) |

### Batch Operations (4)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/batch/operations` | Execute batch operations |
| POST | `/v1/batch/models/bulk-create` | Bulk create models |
| DELETE | `/v1/batch/models/bulk-delete` | Bulk delete models |
| POST | `/v1/batch/tools/bulk-create` | Bulk create tools |

### Export/Import (3)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/export/export` | Export platform configurations |
| POST | `/v1/export/export/tenant/{tenant_id}` | Export single tenant configuration |
| POST | `/v1/export/import` | Import platform configurations |

### Internal (6)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/internal/db/counts` | Get DB node count (internal only) |
| POST | `/v1/internal/db/jobs` | Create DB job (internal only) |
| GET | `/v1/internal/db/jobs/{job_id}` | Get DB job status (internal only) |
| DELETE | `/v1/internal/db/jobs/{job_id}` | Cancel DB job (internal only) |
| POST | `/v1/internal/ops/auto-start-override` | Override auto-start behavior for built-in models |
| GET | `/v1/internal/ops/preview-staged` | Preview staged built-in manifests before deployment |

### Meta (1)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/` | Root V1 |

</details>

---

## MCP Tools

The platform includes **34 MCP (Model Context Protocol) tools** across **17 categories** for agent orchestration:

| Category | Tools | Description |
|----------|-------|-------------|
| **graph** | 8 | Graph database operations (query, search, CRUD, analytics, schema) |
| **security** | 5 | Security checks, auditing, permissions, principal info |
| **system** | 4 | System health, metrics, status, backup |
| **data** | 2 | Data archiving and quality checks |
| **model** | 2 | LLM model management and testing |
| **output** | 2 | Output formatting and summarization |
| **agent** | 1 | Agent context management |
| **cache** | 1 | Cache management |
| **catalog** | 1 | Tool catalog discovery |
| **db** | 1 | Database switching |
| **errors** | 1 | Error reporting |
| **privacy** | 1 | Privacy consent management |
| **ratelimit** | 1 | Rate limiting management |
| **session** | 1 | Session management |
| **tenancy** | 1 | Multi-tenant management |
| **user** | 1 | User profile management |
| **viz** | 1 | Visualization rendering |

<details>
<summary><strong>Complete Tool Reference (Click to expand)</strong></summary>

### Graph Tools (8)
| Tool | Description |
|------|-------------|
| `graph.query` | Execute Cypher queries against Memgraph |
| `graph.secure_query` | Execute secure, validated Cypher queries |
| `graph.search` | Full-text and pattern search in graph |
| `graph.schema` | Retrieve graph schema information |
| `graph.analytics` | Graph analytics (centrality, paths, clustering) |
| `graph.crud` | Create, read, update, delete graph nodes/edges |
| `graph.bulk` | Bulk graph operations |
| `graph.generate_cypher` | Generate Cypher queries from natural language |

### Security Tools (5)
| Tool | Description |
|------|-------------|
| `security.check` | Validate security constraints |
| `security.audit` | Audit logging and compliance |
| `security.permissions` | Check user permissions |
| `security.allowed_operations` | List allowed operations for principal |
| `security.describe_principal` | Get principal/user information |

### System Tools (4)
| Tool | Description |
|------|-------------|
| `system.health` | System health check |
| `system.status` | System status information |
| `system.metrics` | Prometheus metrics retrieval |
| `system.backup` | System backup operations |

### Data Tools (2)
| Tool | Description |
|------|-------------|
| `data.archive` | Archive data operations |
| `data.quality` | Data quality checks |

### Model Tools (2)
| Tool | Description |
|------|-------------|
| `model.manage` | LLM model management |
| `model.test` | Test model instances |

### Output Tools (2)
| Tool | Description |
|------|-------------|
| `output.format` | Format output data |
| `output.summarize` | Summarize text/data |

### Other Tools (11)
| Tool | Description |
|------|-------------|
| `agent.context` | Get/set agent execution context |
| `cache.manage` | Cache operations (get, set, invalidate) |
| `catalog.discover` | Discover available tools |
| `db.switch` | Switch database connections |
| `errors.report` | Report and log errors |
| `privacy.consent` | Manage privacy consent |
| `ratelimit.manage` | Manage rate limiting |
| `session.manage` | Manage agent sessions |
| `tenancy.manage` | Multi-tenant operations |
| `user.profile` | User profile operations |
| `viz.render` | Render visualizations |

</details>

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests (`make test`)
4. Run linting (`make lint`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -e ".[dev,test]"

# Run linting
make lint

# Run tests
make test

# Start development server
uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- **FastAPI** - Modern, fast web framework for building APIs
- **Memgraph** - High-performance graph database
- **Ollama** - Local LLM inference
- **Auth0** - Identity and access management
- **Pydantic** - Data validation using Python type annotations

---

**Author:** Arman Feili  
**Thesis Project:** Sapienza University of Rome, 2025
