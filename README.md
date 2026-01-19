# Cineca Agentic Platform

A production-ready, enterprise-grade **Agentic AI Platform** built with FastAPI that enables intelligent LLM-powered agents to interact with graph databases (Memgraph), execute tools via MCP (Model Context Protocol), and orchestrate complex multi-step workflows—all with comprehensive security, observability, and multi-tenancy support.

**[Live Demo](https://armanfeili.github.io/sapienza-msc-thesis-cineca-agentic-platform/)** — See the Agent Chat UI in action

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-3000%2B-brightgreen.svg)](#testing-strategy)
[![API Endpoints](https://img.shields.io/badge/endpoints-76-blue.svg)](#api-endpoints)
[![MCP Tools](https://img.shields.io/badge/MCP_tools-34-orange.svg)](#mcp-tools--tooling-ecosystem)
[![Demo](https://img.shields.io/badge/demo-live-brightgreen.svg)](https://armanfeili.github.io/sapienza-msc-thesis-cineca-agentic-platform/)

---

## Start Here (Project Map)

| What | Path | Notes |
|------|------|-------|
| **App entry point** | `src/app.py` | FastAPI application factory |
| **Orchestrator** | `src/services/orchestrator.py` | Agent run execution engine |
| **Routers (API)** | `src/routers/` | HTTP endpoints by domain |
| **Security** | `src/security/` | JWT, RBAC, PII, rate limits |
| **MCP Tools** | `src/mcp/tools/` | Tool implementations |
| **Postgres repos** | `db/postgres_control/repositories/` | Data access layer |
| **Migrations** | `db/migrations/` | Alembic schema migrations |
| **Redis layer** | `db/redis_cache/` | Cache, queues, rate limits |
| **Memgraph domain** | `db/memgraph_domain/` | Graph schema + NL->Cypher |
| **Worker entry** | `src/workers/` | Background job processing |
| **Agent Chat UI** | `ui_agent/` | Next.js frontend |
| **Control Panel UI** | `ui_control_panel/` | Streamlit admin UI |
| **Config** | `src/config.py` | Pydantic settings |
| **Tests** | `tests/` | Unit, integration, e2e, security |

---

## Quickstart

### Prerequisites
- Docker + Docker Compose v2
- Bash (for helper scripts)
- Node.js 20 (only if running the Next.js UI locally outside Docker)

### Start the full stack (Docker Compose)
```bash
docker compose up -d --build --remove-orphans
```

### Fetch Auth0/OIDC tokens into `.env` (local convenience)

```bash
# Fetch and save tokens to .env
./fetch_auth0_tokens.sh --save-to-env
```

### Run the Agent Chat UI locally (Next.js)

Portable version (recommended):

```bash
source ~/.nvm/nvm.sh
nvm use 20
cd ui_agent
npx next dev -p 3002
```

### Verify the platform is healthy

1. Discover exposed ports:

   ```bash
   docker compose ps
   ```
2. Call health endpoints using your backend base URL:

   * `<BACKEND_BASE_URL>/v1/health/live`
   * `<BACKEND_BASE_URL>/v1/health/ready`
   * `<BACKEND_BASE_URL>/v1/health/components`

### Smoke Tests (copy/paste)

Replace `<BACKEND_BASE_URL>` with your actual backend URL (e.g., `http://localhost:8000`).

**1. Health readiness:**
```bash
curl -s <BACKEND_BASE_URL>/v1/health/ready | jq
```

**2. Auth introspection (requires token):**
```bash
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  <BACKEND_BASE_URL>/v1/auth/me | jq
```

**3. Create an agent run + poll:**
```bash
# Create run
RUN_ID=$(curl -s -X POST <BACKEND_BASE_URL>/v1/agent-runs \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, world!"}' | jq -r '.id')

# Poll until completed
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  <BACKEND_BASE_URL>/v1/agent-runs/$RUN_ID | jq '.status'
```

**4. Create a job + stream events:**
```bash
# Create job
JOB_ID=$(curl -s -X POST <BACKEND_BASE_URL>/v1/jobs \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "demo", "payload": {}}' | jq -r '.id')

# Stream SSE events
curl -N -H "Authorization: Bearer $ACCESS_TOKEN" \
  <BACKEND_BASE_URL>/v1/jobs/$JOB_ID/events
```

### Read this first

- [High-Level Architecture](#high-level-architecture)
- [Security & Governance](#security--governance)
- [API Endpoints](#api-endpoints)

---

## Table of Contents

1. [Start Here (Project Map)](#start-here-project-map)
2. [Quickstart](#quickstart)
3. [Overview](#overview)
4. [Glossary](#glossary)
5. [Key Features](#key-features)
6. [High-Level Architecture](#high-level-architecture)
7. [Project Structure](#project-structure)
8. [Core Backend](#core-backend)
   - [API Layer](#api-layer)
   - [Domain Schemas](#domain-schemas)
   - [Error Handling](#error-handling)
   - [Configuration & Compute Settings](#configuration--compute-settings)
9. [Data & Persistence Layer](#data--persistence-layer)
   - [PostgreSQL Control Plane](#postgresql-control-plane)
   - [Redis Cache & Queues](#redis-cache--queues)
   - [Memgraph Graph Domain](#memgraph-graph-domain)
10. [Services & Orchestrator](#services--orchestrator)
    - [Service Layer](#service-layer)
    - [Intent Classification](#intent-classification)
    - [Agent Orchestration Engine](#agent-orchestration-engine)
    - [LLM Resilience & Cost Control](#llm-resilience--cost-control)
11. [MCP Tools & Tooling Ecosystem](#mcp-tools--tooling-ecosystem)
    - [MCP Runtime Internals](#mcp-runtime-internals)
    - [Tool Inventory](#tool-inventory)
12. [Jobs, Workers & Background Tasks](#jobs-workers--background-tasks)
    - [Asynchronous Jobs](#asynchronous-jobs)
    - [Worker Processes](#worker-processes)
    - [Background Framework](#background-framework)
14. [Security & Governance](#security--governance)
    - [Authentication & Identity](#authentication--identity)
    - [Authorization & Roles](#authorization--roles)
    - [Rate Limiting, PII & Output Guards](#rate-limiting-pii--output-guards)
    - [Audit & Compliance](#audit--compliance)
15. [Observability & Health](#observability--health)
    - [Metrics](#metrics)
    - [Tracing](#tracing)
    - [Health Probes](#health-probes)
16. [Utilities & Cross-Cutting Helpers](#utilities--cross-cutting-helpers)
17. [User Interfaces](#user-interfaces)
    - [Agent Chat UI](#agent-chat-ui)
    - [Control Panel UI](#control-panel-ui)
18. [Configuration & Environment](#configuration--environment)
19. [Running the Platform](#running-the-platform)
    - [Docker Compose](#docker-compose)
    - [Ports & URLs](#ports--urls-how-to-discover-them)
    - [Local Development](#local-development)
    - [Deployment Variants](#deployment-variants)
20. [Troubleshooting](#troubleshooting)
21. [Operational Scripts & Tooling](#operational-scripts--tooling)
22. [Testing Strategy](#testing-strategy)
    - [Test Metrics](#test-metrics)
    - [Memgraph NL Test Mode](#memgraph-nl-test-mode)
23. [Typical End-to-End Flows](#typical-end-to-end-flows)
24. [Production Notes & Best Practices](#production-notes--best-practices)
25. [API Endpoints](#api-endpoints)
26. [Contributing](#contributing)
27. [License](#license)
28. [Acknowledgments](#acknowledgments)

---

## Overview

The platform provides a complete stack to **design, execute, and observe agentic AI workflows**:

- A **FastAPI** backend that exposes the Agents API, Jobs API, Models/Providers API, MCP tools API, Tenants API, and Health endpoints.
- A **service layer** that orchestrates LLM providers, tools, and databases through an extensible agent engine.
- A **PostgreSQL control plane** storing tenants, agents, runs, steps, jobs, tools, model definitions, and audit logs.
- A **Redis data plane** for caching, job queues, rate limiting, idempotency, and session state.
- A **Memgraph graph database** with a domain model and secure NL->Cypher capabilities for graph Q&A.
- A **resilience framework** with provider fallback, circuit breakers, and cost tracking.
- A **security framework** with OIDC/JWT, RBAC, PII scrubbing, rate limiting, and output guards.
- A **background framework** for scheduled health checks, backups, and cleanups.
- Two **user interfaces**:
  - A **Next.js chat UI** for end users.
  - A **Streamlit control panel** for admins and operators.
- A comprehensive **observability** setup (Prometheus metrics, tracing, structured logging) and a **test suite** covering unit, integration, e2e, security, and performance tests.

The design goal is to be **production-ready**: opinionated about safety, observability and resilience, but flexible enough to integrate with diverse LLM providers and graph workloads.

For a complete list of all platform components, see the [Component Summary](#component-summary) table.

---

## Glossary

- **Tenant**: The isolation boundary for data access, configuration, defaults, and authorization decisions.
- **Principal**: The authenticated caller derived from a JWT (subject + tenant + roles + scopes).
- **Agent Run**: A single execution request that produces a final output and a trace of intermediate steps.
- **Session**: The conversational context/state used across steps (may span multiple runs depending on API usage).
- **Step**: One unit of work inside an agent run (LLM call, tool invocation, graph query, etc.) with persisted inputs/outputs/metrics.
- **Tool (MCP Tool)**: A registered capability callable by agents (and via APIs) with JSON-schema validated inputs and audited outputs.
- **Tool Invocation**: A single execution of a tool, recorded for auditability, observability, and debugging.
- **Provider**: A runtime LLM provider configuration (OpenAI-style, Ollama, Azure OpenAI, etc.).
- **Model Instance**: A resolved model configuration that can be selected/used for inference (often tied to a provider).
- **Control Plane (PostgreSQL)**: The authoritative store for tenants, runs, steps, jobs, tools, manifests, defaults, audit logs, etc.
- **Data Plane (Redis)**: The low-latency layer for caching, queues, rate-limits, idempotency, cancellation flags, and ephemeral state.

### State Machines (Canonical Statuses)

These are the canonical status values used throughout the platform:

**Agent Run:**
`pending` -> `running` -> `succeeded` | `failed` | `cancelled`

**Job:**
`queued` -> `running` -> `finished` | `failed` | `cancelled`

**Circuit Breaker (per provider):**
`CLOSED` -> `OPEN` -> `HALF_OPEN` -> `CLOSED`

---

## Key Features

- **Agentic orchestration**: Multi-step agent runs with TODO lists, tools, and graph queries. See [Agent Orchestration Engine](#agent-orchestration-engine).
- **Multi-provider LLM support**: OpenAI-style APIs, Ollama, demo/stub providers. See [LLM Resilience & Cost Control](#llm-resilience--cost-control).
- **Memgraph integration**: Graph schema, ETL, analytics, CRUD, and NL->Cypher pipeline. See [Memgraph Graph Domain](#memgraph-graph-domain).
- **MCP tools**: 34 tools in 17 categories. See [Tool Inventory](#tool-inventory).
- **Asynchronous jobs**: Persistent job lifecycle with SSE streaming. See [Jobs, Workers & Background Tasks](#jobs-workers--background-tasks).
- **Security first**: OIDC/JWT, RBAC, scopes, rate limits, PII scrubbing. See [Security & Governance](#security--governance).
- **Observability**: Prometheus metrics, OpenTelemetry tracing, structured logging. See [Observability & Health](#observability--health).
- **UIs**: Next.js chat UI for users; Streamlit control panel for operators. See [User Interfaces](#user-interfaces).

For detailed component breakdown, see the [Component Summary](#component-summary) table.

---

## High-Level Architecture

The platform is organized in three layers plus cross-cutting concerns. For a comprehensive breakdown of all components, see the [Component Summary](#component-summary) table.

1. **Core Backend** – FastAPI application, service layer, MCP tools, adapters, resilience and background frameworks.
2. **Data & Infrastructure** – PostgreSQL (control plane), Redis (cache/queues), Memgraph (graph), worker processes.
3. **Presentation** – Agent Chat UI (Next.js), Control Panel UI (Streamlit).

**Cross-cutting modules**: Configuration, security, observability, and utilities.

### Diagram conventions (read before the diagrams)

- The ASCII diagrams are conceptual and may abbreviate route families (e.g., `/v1/health`) to represent the broader set of health endpoints documented later.
- Some diagram arrows describe behavior at a high level; the authoritative contracts remain the endpoint tables and schema definitions in `src/schemas/`.
- **Do not edit the diagram blocks**: they are intentionally kept stable as a reference artifact.

### Architecture Diagram

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                                    IDENTITY & AUTH                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                        Identity Provider (OIDC / Auth0)                             │  │
│  │                    OAuth login · JWT tokens · JWKS for verification                 │  │
│  └─────────────────────────────────────────────────────────────────────────────────────┘  │
│                                           │                                               │
│                          ┌────────────────┴────────────────┐                              │
│                          ▼                                 ▼                              │
└───────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                                     CLIENTS & UIs                                         │
│  ┌────────────────────────────────┐        ┌───────────────────────────────────────────┐  │
│  │      Agent Chat UI             │        │           Control Panel UI                │  │
│  │      (Next.js / React)         │        │           (Streamlit)                     │  │
│  │  ─────────────────────────     │        │  ───────────────────────────────────────  │  │
│  │  - End user chat interface     │        │  - Admin/Operator dashboard               │  │
│  │  - JWT-based authentication    │        │  - Jobs, models, tools management         │  │
│  │  - Agent runs & steps display  │        │  - Graph/NL->Cypher experiments           │  │
│  └────────────────────────────────┘        └───────────────────────────────────────────┘  │
│                          │                                 │                              │
│                          └────────────┬────────────────────┘                              │
│                                       ▼                                                   │
│                    ┌──────────────────────────────────────────┐                           │
│                    │   Reverse Proxy / API Gateway (NGINX)    │                           │
│                    │   TLS termination · Routing · CORS       │                           │
│                    └──────────────────────────────────────────┘                           │
│                                       │                                                   │
└───────────────────────────────────────┼───────────────────────────────────────────────────┘
                                        ▼
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                            FASTAPI BACKEND APPLICATION                                    │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                                           │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐    │
│  │                              API LAYER (Routers)                                  │    │
│  │  /v1/health  /v1/auth  /v1/agents  /v1/agent-runs  /v1/tools  /v1/jobs            │    │
│  │  /v1/models  /v1/admin  /v1/tenants  /v1/batch  /v1/export  /v1/internal          │    │
│  └───────────────────────────────────────────────────────────────────────────────────┘    │
│                                          │                                                │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐    │
│  │                         SECURITY & CROSS-CUTTING MIDDLEWARE                       │    │
│  │  JWT/OIDC validation · RBAC & Scopes · Rate Limiting (Redis) · Multi-tenancy      │    │
│  │  PII Scrubbing · Output Guard · Audit Logging · Tracing · Correlation IDs         │    │
│  └───────────────────────────────────────────────────────────────────────────────────┘    │
│                                          │                                                │
│  ┌──────────────────────────────────┐ ┌────────────────────────────────────────────┐      │
│  │       SERVICE LAYER              │ │            MCP RUNTIME & TOOLS             │      │
│  │  ────────────────────────────    │ │  ───────────────────────────────────────── │      │
│  │  - Orchestrator Service          │ │  - Tool Registry (34 tools, 17 categories) │      │
│  │    - Intent Classifier           │ │  - Tool Policies (RBAC per tool)           │      │
│  │    - Multi-step planner          │ │  - MCP Runtime (ToolContext, audit)        │      │
│  │    - Modes: CHAT/GRAPH/ADMIN/    │ │  - Tool Families:                          │      │
│  │      SECURITY/DANGEROUS          │ │    graph.* cache.* data.* security.*       │      │
│  │  - Session Service               │◀┼─▶   system.* model.* output.* admin.*      │      │
│  │  - Job Service                   │ │      tenancy.* session.* user.* viz.*      │      │
│  │  - Default Model Resolver        │ │      privacy.* ratelimit.* catalog.*       │      │
│  │  - Health / ETL / Archive        │ │                                            │      │
│  │  - Invocation Store              │ │                                            │      │
│  └──────────────────────────────────┘ └────────────────────────────────────────────┘      │
│                   │                                    │                                  │
│  ┌────────────────┴────────────────────────────────────┴───────────────────────────┐      │
│  │                        ADAPTERS & RESILIENCE FRAMEWORK                          │      │
│  │  ─────────────────────────────────────────────────────────────────────────────  │      │
│  │  - LLM Adapters (OpenAI-style, Ollama, stub/demo)                               │      │
│  │  - Resilience: Circuit Breakers · Retries · Cost Tracking · Provider Fallback   │      │
│  │  - Memgraph Adapter (graph queries, NL->Cypher pipeline)                        │      │
│  │  - Redis Adapter (cache, queues, rate limits, state)                            │      │
│  └─────────────────────────────────────────────────────────────────────────────────┘      │
│                   │                         │                        │                    │
│  ┌────────────────┴──────────┐  ┌───────────┴──────────┐  ┌──────────┴─────────────┐      │
│  │  PostgreSQL Repositories  │  │   Redis Integration  │  │ Memgraph Domain Layer  │      │
│  │  ────────────────────     │  │   ─────────────────  │  │ ────────────────────── │      │
│  │  Tenants · Providers      │  │  Cache (sessions,    │  │  Domain Graph Schema   │      │
│  │  Models · Agent Runs      │  │    configs)          │  │  (User, Task, File,    │      │
│  │  Sessions · Steps         │  │  Job Queues & Events │  │   Institution nodes)   │      │
│  │  Jobs · Job Events        │  │  Rate-limit counters │  │  NL->Cypher Pipeline:  │      │
│  │  Tools · Manifests        │  │  Session state       │  │   - NL normalization   │      │
│  │  Audit Logs · Idempotency │  │  Cancellation flags  │  │   - Cypher generation  │      │
│  │  SQLAlchemy + Alembic     │  │  Idempotency keys    │  │   - Safety validation  │      │
│  └───────────────────────────┘  └──────────────────────┘  │   - Query execution    │      │
│                                                           │   - Result summary     │      │
│  ┌────────────────────────────────────────────────────┐   └────────────────────────┘      │
│  │            BACKGROUND FRAMEWORK (APScheduler)      │                                   │
│  │  Health checks (Postgres, Redis, Memgraph, LLMs)   │                                   │
│  │  Backups (Memgraph archives) · Cleanup (stale data)│                                   │
│  │  Provider monitoring · Metrics emission            │                                   │
│  └────────────────────────────────────────────────────┘                                   │
│                                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐     │
│  │                        OBSERVABILITY FRAMEWORK                                   │     │
│  │  Prometheus /metrics · OpenTelemetry tracing (OTLP) · Structured logging         │     │
│  │  Health endpoints: /v1/health/live · /ready · /startup · /components             │     │
│  └──────────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                           │
└───────────────────────────────────────────────────────────────────────────────────────────┘
                           │                    │                    │
           ┌───────────────┘                    │                    └─────────────┐
           ▼                                    ▼                                  ▼
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                               DATA & INFRASTRUCTURE LAYER                                 │
│  ┌─────────────────────────┐  ┌─────────────────────┐  ┌────────────────────────────┐     │
│  │       PostgreSQL        │  │        Redis        │  │         Memgraph           │     │
│  │    (Control Plane)      │  │   (Cache & Queues)  │  │      (Graph Database)      │     │
│  │  ─────────────────────  │  │  ─────────────────  │  │  ───────────────────────── │     │
│  │  - Tenants & configs    │  │  - Entity cache     │  │  - Domain graph (nodes,    │     │
│  │  - Agent runs & steps   │  │  - Job queues       │  │    edges, relationships)   │     │
│  │  - Jobs & job events    │  │  - SSE event buffer │  │  - Cypher query execution  │     │
│  │  - Providers & models   │  │  - Rate-limit data  │  │  - Graph analytics         │     │
│  │  - Manifests & defaults │  │  - Session state    │  │  - ETL import/export       │     │
│  │  - Audit & idempotency  │  │  - Cancel flags     │  │                            │     │
│  └─────────────────────────┘  └─────────────────────┘  └────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                                   WORKER PROCESSES                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              Job Processing Worker                                  │  │
│  │  ───────────────────────────────────────────────────────────────────────────────    │  │
│  │  - Pop job IDs from Redis queue                                                     │  │
│  │  - Load job metadata from PostgreSQL                                                │  │
│  │  - Execute handlers: ETL, backups, maintenance, long-running tasks                  │  │
│  │  - Check cancellation flags periodically                                            │  │
│  │  - Update job status & emit events -> SSE streaming to clients                      │  │
│  │  - Uses same adapters/services as main app                                          │  │
│  └─────────────────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                                   LLM PROVIDERS                                           │
│  ┌────────────────────┐  ┌────────────────────┐  ┌─────────────────────────────────────┐  │
│  │   Ollama (Local)   │  │      OpenAI        │  │  Azure OpenAI / Other Providers     │  │
│  │  ────────────────  │  │  ────────────────  │  │  ─────────────────────────────────  │  │
│  │  Local LLM hosting │  │  Cloud LLM API     │  │  Compatible OpenAI-style APIs       │  │
│  └────────────────────┘  └────────────────────┘  └─────────────────────────────────────┘  │
│                                                                                           │
│                    ▲ Called via Adapters & Resilience Framework ▲                         │
│                      (circuit breakers, cost tracking, fallback)                          │
└───────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                              OBSERVABILITY & MONITORING                                   │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────────────┐  │
│  │      Prometheus       │  │       Grafana         │  │     OTEL Collector / APM      │  │
│  │  ───────────────────  │  │  ───────────────────  │  │  ──────────────────────────── │  │
│  │  Scrapes /metrics     │  │  Dashboards for       │  │  Receives OTLP traces from    │  │
│  │  from app & workers   │  │  HTTP, agents, jobs,  │  │  app & workers                │  │
│  │                       │  │  tools, health        │  │  -> Jaeger / Tempo / APM      │  │
│  └───────────────────────┘  └───────────────────────┘  └───────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

## Agent Run Workflow (Chat / Graph Q&A)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  1. AUTHENTICATION                                                                     │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  User -> Agent Chat UI -> OIDC Provider -> JWT (tenant, roles, scopes)                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  2. REQUEST -> BACKEND                                                                 │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  UI sends: POST /v1/agent-runs (Bearer JWT, prompt, optional model)                    │
│  -> Reverse Proxy -> FastAPI Backend                                                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  3. SECURITY GATEWAY                                                                   │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  - Validate JWT (JWKS) -> extract tenant, roles, scopes                                │
│  - RBAC check for endpoint                                                             │
│  - Rate limiting (Redis counters)                                                      │
│  - Audit event logging                                                                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  4. INTENT CLASSIFICATION                                                              │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  Intent Classifier analyzes prompt -> determines mode:                                 │
│    - CHAT (conversational)                                                             │
│    - GRAPH (analytics, NL->Cypher)                                                     │
│    - SECURITY / ADMIN (privileged ops)                                                 │
│    - DANGEROUS (destructive ops -> refuse/explain)                                     │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  5. ORCHESTRATION & STEP EXECUTION                                                     │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  Orchestrator builds TODO plan (multi-step run):                                       │
│                                                                                        │
│  ┌───────────────────────────────────────────────────────────────────────────────┐     │
│  │  FOR EACH STEP:                                                               │     │
│  │  ───────────────────────────────────────────────────────────────────────────. │     │
│  │  - Call LLM Provider (via resilience: circuit breakers, fallback, cost)       │     │
│  │  - Invoke MCP Tools (graph.*, data.*, security.*, etc.) with RBAC             │     │
│  │  - If GRAPH mode:                                                             │     │
│  │      1. Normalize NL prompt                                                   │     │
│  │      2. Generate Cypher (LLM or test hints)                                   │     │
│  │      3. Validate safety (read-only, tenant boundaries)                        │     │
│  │      4. Execute on Memgraph                                                   │     │
│  │      5. Summarize results to NL                                               │     │
│  │  - Persist step (inputs, outputs, metrics) -> PostgreSQL                      │     │
│  │  - Use Redis for session state, caching, cancellation checks                  │     │
│  └───────────────────────────────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  6. FINALIZATION & RESPONSE                                                            │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  - Normalize final output (text + optional JSON)                                       │
│  - PII scrubbing & output guard                                                        │
│  - Persist final run & metrics -> PostgreSQL                                           │
│  - Emit metrics (Prometheus) & traces (OTEL)                                           │
│  - Return HTTP response -> UI polls /agent-runs/{id} for updates                       │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

## Long-Running Job Workflow

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  1. JOB CREATION                                                                       │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  Admin (Control Panel UI) -> POST /v1/jobs (ETL, backup, maintenance, etc.)            │
│  -> Backend validates, creates Job record (status=queued) in PostgreSQL                │
│  -> Enqueues job ID in Redis queue                                                     │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  2. WORKER PROCESSING                                                                  │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  Worker process:                                                                       │
│    - Pops job ID from Redis                                                            │
│    - Loads job from PostgreSQL -> marks status=running                                 │
│    - Executes handler (uses same adapters: Memgraph, LLM, Redis)                       │
│    - Periodically checks cancellation flags (Redis)                                    │
│    - Emits progress events -> Redis SSE buffer                                         │
│    - On completion: status=finished/failed -> persists result                          │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  3. SSE STREAMING TO UI                                                                │
│  ─────────────────────────────────────────────────────────────────────────────────     │
│  Control Panel subscribes to GET /v1/jobs/{id}/events (SSE)                            │
│  -> Backend streams events from PostgreSQL + Redis buffer                              │
│  -> UI displays real-time progress, logs, final status                                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

## Component Summary

| Layer | Components | Responsibilities |
|-------|------------|------------------|
| **Identity** | Auth0 / OIDC Provider | OAuth login, JWT tokens, JWKS |
| **Clients** | Agent Chat UI (Next.js), Control Panel UI (Streamlit) | User/Admin interfaces |
| **Edge** | Reverse Proxy (NGINX) | TLS, routing, CORS |
| **Backend** | FastAPI Application | API, services, orchestration, security |
| **Services** | Orchestrator, Session, Job, Health, ETL, Archive | Business logic & workflows |
| **MCP Tools** | 34 tools in 17 categories | graph, cache, data, security, system, etc. |
| **Adapters** | LLM, Memgraph, Redis adapters | External service integration |
| **Resilience** | Circuit breakers, retries, fallback, cost tracking | LLM reliability |
| **Data** | PostgreSQL (control), Redis (cache/queues), Memgraph (graph) | Persistence & state |
| **Workers** | Job processing worker | Async long-running tasks |
| **LLM** | Ollama, OpenAI, Azure OpenAI | Language model inference |
| **Observability** | Prometheus, Grafana, OTEL Collector | Metrics, traces, dashboards |

## Key Metrics

| Metric | Value |
|--------|-------|
| **API Endpoints** | 76 across 16 categories |
| **MCP Tools** | 34 tools, 17 categories |
| **Test Cases** | 3,000+ |
| **Test Files** | 236 |

---

## Project Structure

```
Cineca-Agentic-Platform/
├── src/                              # Main application source code
│   ├── app.py                        # FastAPI application factory
│   ├── config.py                     # Pydantic settings configuration
│   ├── logging_setup.py              # Structured logging configuration
│   ├── audit_logger.py               # Audit logging utilities
│   ├── provenance.py                 # Data provenance tracking
│   ├── background.py                 # Background task scheduler
│   ├── adapters/                     # External service adapters (LLM, DB)
│   ├── agent_policies/               # Agent behavior policies
│   ├── background/                   # Background task implementations
│   ├── config_modules/               # Modular configuration
│   ├── errors/                       # Error definitions and handlers
│   ├── health/                       # Health check implementations
│   ├── i18n/                         # Internationalization
│   ├── jobs/                         # Job definitions and handlers
│   ├── mcp/                          # Model Context Protocol implementation
│   │   ├── runtime.py                # MCP tool runtime (RBAC, audit, metrics)
│   │   ├── tool_registry.py          # Central tool registry
│   │   ├── tool_policy.py            # Tool access policies
│   │   ├── schemas.py                # MCP-specific schemas
│   │   ├── manifest.json             # Tool definitions
│   │   ├── policies.yaml             # Tool policies configuration
│   │   └── tools/                    # Tool implementations (19 categories)
│   │       ├── agent/                # Agent context tools
│   │       ├── cache/                # Cache management tools
│   │       ├── catalog/              # Tool catalog discovery
│   │       ├── data/                 # Data manipulation tools
│   │       ├── db/                   # Database tools
│   │       ├── errors/               # Error reporting tools
│   │       ├── graph/                # Graph query tools
│   │       ├── model/                # Model management tools
│   │       ├── output/               # Output formatting tools
│   │       ├── privacy/              # Privacy consent tools
│   │       ├── ratelimit/            # Rate limiting tools
│   │       ├── security/             # Security audit tools
│   │       ├── session/              # Session management tools
│   │       ├── system/               # System health tools
│   │       ├── tenancy/              # Multi-tenant tools
│   │       ├── user/                 # User profile tools
│   │       └── viz/                  # Visualization tools
│   ├── memgraph/                     # Memgraph integration utilities
│   ├── metrics/                      # Prometheus metrics definitions
│   ├── middleware/                   # FastAPI middleware
│   ├── models/                       # SQLAlchemy ORM models
│   ├── observability/                # Tracing and observability
│   ├── repositories/                 # Data access repositories
│   ├── resilience/                   # Circuit breakers, retries, fallback
│   ├── routers/                      # API route handlers
│   │   ├── admin.py                  # Admin operations
│   │   ├── admin_db.py               # Admin database operations
│   │   ├── admin_jobs.py             # Admin job management
│   │   ├── admin_ops.py              # Admin operational endpoints
│   │   ├── agent.py                  # Agent sessions & steps
│   │   ├── agent_runs.py             # Agent run execution
│   │   ├── auth.py                   # Authentication endpoints
│   │   ├── batch.py                  # Batch operations
│   │   ├── export_import.py          # Data export/import
│   │   ├── health.py                 # Health probes (v1)
│   │   ├── health_v2.py              # Health probes (v2)
│   │   ├── internal_db.py            # Internal database endpoints
│   │   ├── internal_ops.py           # Internal operations
│   │   ├── jobs.py                   # Background job management
│   │   ├── manifests.py              # Manifest management
│   │   ├── model_instances.py        # Model instance management
│   │   ├── model_management.py       # Model configuration
│   │   ├── model_processes.py        # Model processes
│   │   ├── models.py                 # Model endpoints
│   │   ├── tenants.py                # Tenant management
│   │   ├── tenants_admin.py          # Tenant admin operations
│   │   └── tools.py                  # Tool discovery & invocation
│   ├── schemas/                      # Pydantic request/response models
│   ├── scripts/                      # Application scripts
│   ├── security/                     # Security modules
│   │   ├── admin.py                  # Admin security
│   │   ├── audit.py                  # Security audit logging
│   │   ├── auth.py                   # Authentication logic
│   │   ├── authorization.py          # Authorization checks
│   │   ├── graph_access_policy.py    # Graph access policies
│   │   ├── intent_filter.py          # Intent filtering
│   │   ├── internal.py               # Internal security
│   │   ├── jwt.py                    # JWT validation
│   │   ├── model_perms.py            # Model permissions
│   │   ├── output_guard.py           # Output safety guard
│   │   ├── perm.py                   # RBAC permissions
│   │   ├── pii_scrubber.py           # PII detection/redaction
│   │   ├── policies_loader.py        # Policy loading
│   │   ├── rate_limit.py             # Rate limiting
│   │   ├── secrets.py                # Secrets management
│   │   ├── tenants.py                # Tenant security
│   │   └── validators.py             # Input validators
│   ├── services/                     # Business logic services
│   │   ├── archive.py                # Archive service
│   │   ├── default_model_resolver.py # DMR for model selection
│   │   ├── etl.py                    # ETL operations
│   │   ├── health.py                 # Health service
│   │   ├── intent_classifier.py      # Query intent classification
│   │   ├── invocation_store.py       # Tool invocation storage
│   │   ├── job_store.py              # Job storage
│   │   ├── jobs_service.py           # Jobs business logic
│   │   ├── model_warmup.py           # LLM warmup service
│   │   ├── orchestrator.py           # Agent orchestration engine
│   │   ├── process_service.py        # Process management
│   │   ├── prompt_catalog.py         # Prompt templates
│   │   ├── service_metrics.py        # Service-level metrics
│   │   ├── session.py                # Session management
│   │   ├── session_fallback.py       # Session fallback logic
│   │   ├── status.py                 # Status service
│   │   └── tenants.py                # Tenant service
│   ├── utils/                        # Shared utilities
│   └── workers/                      # Background job workers
│
├── db/                               # Database layer
│   ├── populate.py                   # Database population script
│   ├── postgres_control/             # PostgreSQL control plane
│   │   ├── database.py               # Database connection
│   │   ├── init.sql                  # Initial schema
│   │   ├── seed_tenants.py           # Tenant seeding
│   │   ├── alembic/                  # Alembic migrations
│   │   ├── alembic.ini               # Alembic configuration
│   │   ├── models/                   # SQLAlchemy models
│   │   └── repositories/             # Data access objects
│   ├── redis/                        # Redis utilities
│   ├── redis_cache/                  # Redis caching layer
│   ├── memgraph_domain/              # Memgraph graph database
│   │   ├── config.py                 # Memgraph configuration
│   │   ├── memgraph_client.py        # Memgraph client
│   │   ├── populate.py               # Graph population
│   │   ├── create_original_db.py     # Original dataset loader
│   │   ├── original-dataset/         # Reference graph data
│   │   └── populated/                # Populated graph exports
│   └── migrations/                   # Additional migrations
│
├── tests/                            # Test suite (3,000+ test cases)
│   ├── conftest.py                   # Shared fixtures
│   ├── agents/                       # Agent-specific tests
│   ├── api/                          # API endpoint tests
│   ├── caching/                      # Cache tests
│   ├── compliance/                   # Compliance tests
│   ├── db/                           # Database tests
│   ├── e2e/                          # End-to-end tests
│   ├── fixtures/                     # Test fixtures
│   ├── health/                       # Health check tests
│   ├── integration/                  # Integration tests
│   ├── internal_db/                  # Internal DB tests
│   ├── jobs/                         # Job tests
│   ├── mcp/                          # MCP tool tests
│   ├── middleware/                   # Middleware tests
│   ├── observability/                # Observability tests
│   ├── performance/                  # Performance tests
│   ├── resilience/                   # Resilience tests
│   ├── routers/                      # Router tests
│   ├── scripts/                      # Script tests
│   ├── security/                     # Security tests
│   ├── smoke/                        # Smoke tests
│   ├── sse/                          # SSE tests
│   ├── ui_control_panel/             # UI tests
│   ├── unit/                         # Unit tests
│   └── utils/                        # Utility tests
│
├── scripts/                          # Utility scripts
│   ├── api-polish/                   # API refinement scripts
│   ├── auth/                         # Authentication scripts
│   ├── database/                     # Database backup/restore
│   ├── debug/                        # Debugging utilities
│   ├── deployment/                   # Deployment scripts
│   ├── manifest/                     # Manifest management
│   ├── ollama/                       # Ollama LLM scripts
│   ├── openapi/                      # OpenAPI generation
│   ├── security/                     # Security scripts
│   ├── testing/                      # Test utilities
│   └── verification/                 # Verification scripts
│
├── docs/                             # Documentation
│   ├── adr/                          # Architecture Decision Records
│   ├── agents/                       # Agent documentation
│   ├── api/                          # API documentation
│   ├── architecture/                 # Architecture docs
│   ├── compliance/                   # Compliance docs
│   ├── database/                     # Database docs
│   ├── diagrams/                     # Architecture diagrams
│   ├── features/                     # Feature documentation
│   ├── guides/                       # User guides
│   ├── mcp/                          # MCP documentation
│   ├── observability/                # Observability docs
│   ├── operations/                   # Operations guides
│   ├── orchestrator/                 # Orchestrator docs
│   ├── production/                   # Production guides
│   ├── quickstarts/                  # Quickstart guides
│   ├── reference/                    # Reference documentation
│   ├── schema/                       # Schema documentation
│   ├── security/                     # Security documentation
│   ├── testing/                      # Testing documentation
│   └── ui/                           # UI documentation
│
├── api/                              # OpenAPI specifications
│   ├── openapi.json                  # Main OpenAPI spec
│   ├── openapi_v1.json               # v1 API spec
│   ├── openapi_v2.json               # v2 API spec
│   └── openapi_with_batch_export.json
│
├── examples/                         # Usage examples
│   ├── cli/                          # CLI examples
│   ├── data/                         # Sample data
│   └── tools/                        # Tool examples
│
├── monitoring/                       # Monitoring configuration
│   └── grafana/                      # Grafana dashboards
│
├── ops/                              # Operations configuration
│   ├── backup/                       # Backup scripts
│   ├── grafana/                      # Grafana setup
│   ├── nginx/                        # NGINX configuration
│   └── prometheus/                   # Prometheus configuration
│
├── ui_agent/                         # Next.js agent chat UI
├── ui_control_panel/                 # Streamlit control panel UI
│
├── docker-compose.yml                # Main Docker Compose
├── docker-compose.gpu.yml            # GPU support variant
├── docker-compose.nginx.yml          # NGINX variant
├── docker-compose.override.yml       # Local overrides
├── docker-compose.override.dev.yml   # Development overrides
├── Dockerfile                        # Multi-stage Docker build
├── docker-entrypoint.sh              # Container entrypoint
├── Makefile                          # Development commands
├── pyproject.toml                    # Python project configuration
├── requirements.txt                  # Python dependencies
├── conftest.py                       # Root test configuration
├── fetch_auth0_tokens.sh             # Auth0 token fetching script
├── .env.example                      # Environment template
└── README.md                         # This file
```

---

## Core Backend

### API Layer

The backend is implemented with **FastAPI**, exposing a versioned HTTP API. Major domains:

- **Agents**
  - Create and manage *agent runs*.
  - Manage *sessions* and *steps* for each agent run.
  - Report execution metrics and TODO items.
- **Jobs**
  - Submit long-running jobs.
  - Poll job status.
  - Stream job events via Server-Sent Events (SSE).
- **Models & Providers**
  - Register and manage model providers.
  - List models, configure defaults, and test connectivity.
- **MCP Tools**
  - Discover tools and schemas.
  - Invoke tools with structured requests/responses.
- **Tenants**
  - Manage tenants and tenant-bound configuration.
- **Health & Meta**
  - Liveness, readiness, startup probes.
  - Component-level health.
  - Introspection endpoints (OpenAPI export, etc).

The API adheres to consistent patterns:

- **JSON schemas** are defined centrally in the schemas package.
- **Idempotency** for safe retry of selected endpoints.
- **Pagination** using token-based cursors.
- **ETags** to support conditional GETs.
- **Rate limiting** integrated into request handling.
- **Standardized errors** via Problem Details (see below).

### Domain Schemas

The **schemas** package defines all request and response models using Pydantic:

- **Agents & Runs**
  - Requests to create runs, resume sessions, and list runs.
  - Response models for runs, steps, TODO items, and execution metrics.
- **Jobs**
  - Job creation requests and job status responses.
  - Event payloads for streamed logs and status transitions.
- **Models & Providers**
  - Provider registration payloads.
  - Model definitions, health checks, configuration overrides.
- **Tools**
  - Tool metadata, invocation requests, and results.
- **Tenants, Auth, Admin**
  - Tenant definitions.
  - Auth responses.
  - Admin operations payloads.

These schemas are the **single source of truth** for the API, ensuring consistency between code and documentation.

### Error Handling

The backend uses an **RFC 7807 Problem Details** pattern for error responses:

- A **ProblemDetail** structure with:
  - `type`, `title`, `status`, `detail`, `instance`.
  - A `code` field referencing an internal error code enumeration.
  - Optional structured fields for additional context.
- Helper functions make it easy to:
  - Create error responses consistently.
  - Raise standardized HTTP exceptions for common scenarios (e.g., “session not found”, “invalid cursor”, “duplicate session”, conflicts, bad requests).

All service and API layers are encouraged to use these helpers, resulting in predictable and debuggable error contracts.

### Configuration & Compute Settings

Configuration is centralized in a **settings** module with environment-driven configuration. A specialized **compute configuration** layer derives runtime parameters for:

- Concurrency levels.
- Timeouts for LLM calls and tool invocations.
- CPU vs GPU vs MPS usage for local LLMs (e.g. Ollama).
- Test mode overrides (e.g., shorter timeouts, stubbed providers).

This derived configuration is consumed by:

- Orchestrator and service layer.
- LLM adapters and resilience framework.
- Workers and background tasks.

It allows the platform to adapt to different runtime environments (laptop, CI, production cluster) without modifying code.

---

## Data & Persistence Layer

### PostgreSQL Control Plane

PostgreSQL is the **authoritative source of truth** for control-plane entities:

- **Tenants**
- **Providers and Model Instances**
- **Agent Runs, Sessions, and Steps**
- **Jobs and Job Events**
- **MCP tools and tool invocations**
- **Built-in manifests and processes**
- **User default models**
- **Idempotency keys**
- **Audit logs and internal operations**

The database layer consists of:

- **ORM Models** (SQLAlchemy):
  - UUID primary keys, JSONB fields, and rich indexes.
  - ETag support for caching and concurrency.
- **Migrations**:
  - An Alembic migration chain that evolves the schema over time.
  - Additional carefully-crafted SQL migrations for:
    - Converting text to JSONB outputs.
    - Adding warning/metrics fields with indexes.
    - Creating internal operations audit tables.
- **Repositories**:
  - Encapsulate data access logic for each domain:
    - Agents, Sessions, Steps, Jobs, Tenants, Providers, Models, Tools, Manifests, Defaults, Audit.
  - Implement cursor-based pagination and ETag calculation.
  - Integrate Redis caching where beneficial.

The repositories are the main entry point used by services, ensuring consistent behavior and isolation from raw SQL.

### Redis Cache & Queues

Redis is used as a high-performance **cache and coordination layer**:

- **Cache**
  - JSON-encoded objects (runs, model configs, provider metadata).
  - Short-lived caches for hot paths.
- **Jobs**
  - Job queues per job type.
  - An event buffer for job progress that powers SSE streaming.
- **Agent State**
  - Session storage and step sequence management.
  - Cancellation flags and ephemeral state.
  - Idempotency keys for APIs.
- **Rate Limiting**
  - Sliding windows per user/tenant and per scope.
  - Efficient Lua scripts for atomic increments and checks.
- **Maintenance**
  - Pruning expired keys and managing housekeeping tasks.

When Redis is unavailable, many components are designed to degrade gracefully where possible.


### Memgraph Graph Domain

Memgraph provides a **graph data store** used for rich relationships and graph analytics:

- **Domain Schema**: Nodes such as users, institutions, computational tasks, and files. Relationships encode lineage and association (e.g., tasks producing/consuming files, user membership in institutions).
- **Population & ETL**: Scripts to load reference "original dataset" and synthetic data. Export/import via JSONL and CSV for reproducible states.
- **Graph Operations**: Analytics (counts, degree, centrality), CRUD for nodes and relationships, schema discovery and search.

#### NL->Cypher Pipeline (Canonical Reference)

This is the authoritative description of the natural language to Cypher translation pipeline used throughout the platform:

1. **NL Normalization** – The user asks a natural language question; the system normalizes it.
2. **Cypher Generation** – An LLM-assisted component drafts a Cypher query (or uses test hints in test mode).
3. **Safety Validation** – A safety layer validates the Cypher (read-only enforcement, tenant boundaries, forbidden patterns).
4. **Query Execution** – The validated query is executed on Memgraph.
5. **Result Summarization** – Results are transformed back into a natural language answer.

This pipeline is invoked when the orchestrator operates in **Graph Mode** (see [Agent Orchestration Engine](#agent-orchestration-engine)) and is also used by graph tools and the Control Panel UI's Cypher/Graph tab.

---

## Services & Orchestrator

### Service Layer

The service layer implements **business logic** on top of adapters and repositories. It follows a consistent pattern:

- Base classes for services with:
  - Typed results (`ServiceResult`).
  - Status enumeration (`ServiceStatus`).
  - Consistent error handling and logging.
- Example services:
  - **Orchestrator Service**
  - **Session Service** (managing chat sessions and message history).
  - **Default Model Resolver** (tenant-aware default LLM selection).
  - **Archive Service** (snapshot and archive graph or system state).
  - **ETL Service** (import/export graph data).
  - **Health Service** (aggregated status from Redis, Memgraph, Postgres, providers).
  - **Invocation Store** (cache for tool invocation results).
  - **Job Service** (job lifecycle).

Services are orchestrated by the API layer and by workers.

### Intent Classification

Before executing an agent run, the platform categorizes the user prompt with a **lightweight intent classifier**:

- Primary modes:
  - `CHAT` – normal conversational use.
  - `GRAPH` – graph analytics and data retrieval operations.
  - `SECURITY` – security context queries.
  - `ADMIN` – administrative tasks.
  - `DANGEROUS` – potentially destructive or sensitive operations.
- Pipeline:
  1. Match against known tool catalog patterns.
  2. Detect obviously dangerous expressions (e.g., “drop all”, “delete everything”).
  3. Identify admin/security/graph use cases.
  4. Fall back to chat.
- Output:
  - Mode, confidence score, and an explanation for the classification.

This classifier feeds directly into the orchestrator and is intertwined with security (e.g., requiring admin roles for certain intents).

### Agent Orchestration Engine

The **orchestrator** is the central engine that executes agent runs:

1. **Mode Selection**
   - Uses intent classification to pick an execution route (chat, graph, security, admin, dangerous).
2. **Planning**
   - Builds a TODO list of steps to answer the user’s request.
   - Steps may involve LLM calls, tool invocations, graph operations, or intermediate reasoning.
3. **Execution**
   - For each step:
     - Calls the appropriate LLM provider (via adapters and resilience layer).
     - Invokes MCP tools with structured requests.
     - Executes Memgraph queries if in graph mode.
     - Records inputs, outputs, timing, and errors to PostgreSQL.
4. **Graph Mode**
   - Uses the [NL->Cypher Pipeline](#nlcypher-pipeline-canonical-reference) for natural language graph queries.
5. **Dangerous Mode**
   - For clearly destructive operations, the engine may:
     - Refuse to execute and return a safe explanation.
     - Suggest alternative “EXPLAIN-only” operations.
6. **Output**
   - The final answer is normalized into a consistent format:
     - Text, structured JSON, or combined forms.
   - Detailed **steps and metrics** can be inspected via API and UIs.

This engine is responsible for coordinating all moving pieces (LLMs, tools, graph, DB) while obeying security and resource policies.

### LLM Resilience & Cost Control

LLM calls are handled through a **resilience framework**:

- **Provider Pool**
  - Multiple providers can be configured for a given capability.
  - Each with priority, timeouts, and budget.
- **Circuit Breakers**
  - States: `CLOSED`, `OPEN`, `HALF_OPEN`.
  - Per-provider error thresholds and recovery rules.
- **Cost Tracker**
  - Tracks token usage and cost over time.
  - Enforces per-provider budgets.
- **Fallback Behavior**
  - Attempt the primary provider first.
  - On failure or budget exhaustion, fallback to the next provider.
  - Provide metadata about which provider actually served the request.

A deterministic stub provider is available in tests to ensure reproducible behavior.

### Registry-Based Model Management

- **Providers are registered in the control plane (PostgreSQL)** – Each provider entry includes a name, base URL, credentials, and configuration.
- **Model instances reference providers** – They are the selectable runtime units used by agents and APIs.
- **Local LLMs (e.g., Ollama) are onboarded** by registering a provider with a `base_url` pointing to the local server and creating model instances that reference local model IDs.
- **Usage is tracked** (tokens, latency) for observability and debugging. Monetary cost tracking is optional and may be zero for local/self-hosted providers.

---

## MCP Tools & Tooling Ecosystem

The platform implements a rich ecosystem of **Model Context Protocol (MCP) tools**, accessible to agents and directly via APIs:

- **Catalog & Discovery**
  - List all tools and their schemas.
  - Describe inputs and outputs.
- **Common Tool Families**
  - `graph.*` – graph analytics, CRUD, secure querying.
  - `cache.*` – cache management and invalidation.
  - `data.*` – archival, integrity checks, duplicates, schema validation.
  - `db.*` – database connection inspection and switching.
  - `security.*` – security checks and configuration queries.
  - `admin.*` – administrative operations (subject to RBAC).
  - `utils.*` – generic utilities.
- **Security Model**
  - Tools are scoped with permissions and roles.
  - All invocations go through an audit trail.
  - Tools operate within tenant boundaries.

The orchestrator uses these tools as building blocks during agent runs.

### MCP Runtime Internals

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
1. Client calls `POST /v1/tools/{name}/invocations` with the request payload
2. Runtime validates permissions against principal scopes
3. Input payload validated against JSON Schema
4. Tool executed with timeout and cancellation support
5. Result audited and metrics recorded
6. Response returned with standard shape `{ok, action, data, ...}`

### Tool Inventory

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

## Jobs, Workers & Background Tasks

### Asynchronous Jobs

Long-running tasks are executed through the **job system**:

- **Job Lifecycle**
  - `queued -> running -> finished / failed / cancelled`
- **Job Model**
  - Payload representing the task.
  - Result and error structures.
  - Timestamps and owner/tenant fields.
- **Storage & Coordination**
  - Persistent metadata and events in PostgreSQL.
  - Job queues and event buffers in Redis.
- **Idempotency**
  - Idempotency keys to avoid duplicate job submissions.
- **Events & Streaming**
  - Event log of job progress (status changes, intermediate logs).
  - SSE endpoints to stream events to clients.

Jobs are used for heavy operations such as large ETL loads, exports, or expensive computations.

### Worker Processes

Dedicated **worker processes** pull jobs from Redis and execute them:

- **Design Principles**
  - Queue-based processing for high throughput.
  - PostgreSQL-backed persistence for reliability.
  - Graceful shutdown and signal handling.
  - Heartbeat updates for worker health monitoring.
  - Cancellation support via Redis cancellation flags.
- **Flow**
  1. Pop a job ID from a Redis queue.
  2. Load the job from PostgreSQL.
  3. Mark as `running`.
  4. Execute the associated job handler.
  5. Check for cancellation flags periodically.
  6. Mark as `finished`, `failed`, or `cancelled`.
  7. Append events to the job events log.

Different job types can be configured (demo, test, long-running, etc.), and the worker adheres to type whitelists and configuration options.

### Background Framework

In addition to ad-hoc jobs, the platform runs **scheduled background tasks**:

- **Health Monitoring**
  - Periodic connectivity checks for Postgres, Redis, Memgraph, LLM providers.
- **Provider Health**
  - Specialized checks for provider availability and latency.
- **Backups**
  - Regular compressed backups of Memgraph and optionally Redis.
  - Retention policies and checksum validation.
- **Cleanup**
  - Age-based pruning of temporary files, old job events, and stale caches.
- **Metrics**
  - Emit Prometheus metrics for background task outcomes and timings.

This is typically implemented with APScheduler integrated into the application lifecycle.

---

## Security & Governance

### Authentication & Identity

The platform integrates with **OIDC/JWT** identity providers (e.g., Auth0):

- **JWT Validation**
  - Uses JWKS to verify signatures.
  - Validates issuer, audience, expiry.
- **Token Parsing**
  - Extracts subject, tenant, roles, and scopes.
- **Password Hashing**
  - For local or fallback user databases (e.g., bcrypt).

Automation scripts can fetch access tokens for different roles and use them for local testing and tooling.

### Authorization & Roles

Authorization is enforced via **RBAC and scopes**:

- **Roles**
  - Example roles: `admin`, `user`, and possibly more fine-grained roles.
- **Policies**
  - Policies describe which tools and models each role can use.
  - They can also encode:
    - Required scopes.
    - Default models per role.
    - Rate limit settings.
- **Integration**
  - FastAPI dependencies enforce required scopes and roles.
  - Orchestrator and tools check permissions at runtime.
  - Tenant context is enforced for all data access.

This ensures that powerful capabilities (e.g., admin tools, dangerous graph operations) are only available to authorized principals.

### Rate Limiting, PII & Output Guards

- **Rate Limiting**
  - Implemented as sliding windows in Redis.
  - Configurable per route, per scope, per tenant.
- **PII Scrubbing**
  - Sensitive data (emails, IDs, etc.) is masked in logs and structured outputs.
  - Works on nested structures and free text.
- **Output Guard**
  - A post-processing layer for LLM outputs and tool results.
  - Enforces safety policies (e.g., no secrets, filtered content).

These mechanisms collectively provide defense-in-depth for safety and privacy.

### Audit & Compliance

The platform records security-relevant actions in **audit logs**:

- **Security Audit**
  - Login attempts, token validations, permission decisions.
  - Dangerous or admin-level actions.
- **Internal Operations**
  - Administrative data changes (e.g., manual DB operations) with dedicated tables.
- **Tool Auditing**
  - All MCP tool invocations and their results, including metadata.

Audit data can be surfaced via the control panel and used to support compliance requirements.

---

## Observability & Health

### Metrics

Metrics are exposed in a **Prometheus-friendly** format:

- **HTTP**
  - Requests per path/method.
  - Latency histograms.
  - Error counts.
- **Agents**
  - Runs per tenant and per model.
  - Step counts and durations.
  - LLM tokens, latencies, and error rates.
  - Tool invocation counts and failures.
- **Jobs**
  - Jobs created, running, completed, failed, cancelled.
  - Queue depth and processing latencies.
- **Tools**
  - Invocation counts and latencies by tool.
  - Queue metrics and cache hit/miss rates.
- **Rate Limits**
  - Requests checked, violations, quota utilization.
- **Background Tasks**
  - Task runs and outcomes.

### Tracing

The platform integrates with **OpenTelemetry**:

- Automatic instrumentation for:
  - FastAPI routes.
  - HTTP client calls.
  - Database interactions (Postgres).
- Traces can be exported via OTLP to a collector and wired to tools such as Jaeger or Tempo.
- Resource attributes capture environment, service name, and version.

### Health Probes

Multiple health probes are exposed via HTTP endpoints:

- **Liveness**
  - Confirms that the process is alive.
- **Readiness**
  - Verifies that core dependencies (Postgres, Redis, Memgraph, providers) are available.
- **Startup**
  - Indicates that initial bootstrapping and background schedulers are ready.
- **Component Health**
  - Per-component status (OK/degraded/unavailable) with timing and error messages.

These endpoints are suitable for Kubernetes probes and for use in external monitoring (e.g., the control panel dashboard).

---

## Utilities & Cross-Cutting Helpers

The utilities framework provides shared helpers used across the project:

- **Pagination**
  - Stateless token-based pagination with `page_token` and `page_size`.
  - ETag support for caching paginated endpoints.
- **Idempotency**
  - Decorators and helpers to implement idempotent operations.
  - Backed by Redis or in-memory stores.
- **Provider Resolution**
  - Helper to interpret provider configuration:
    - Base URLs.
    - Timeouts.
    - Upstream model IDs (e.g., Ollama).
- **JSON Utilities**
  - Canonical JSON serialization for complex Python types (datetime, UUID, Decimal, Enum, paths).
  - Error-tolerant decoding and normalization.
- **ETag Handling**
  - Helpers to compute strong/weak ETags from payloads.
  - Pattern for conditional GET/PUT operations.
- **Deprecation**
  - Facilities to mark endpoints and features as deprecated with removal versions and headers.
- **Run Output Normalization**
  - Ensures agent outputs are normalized (e.g., always a dict or a `{"text": ...}` structure).
- **Test Helpers**
  - Async helpers and mocks for tests.
  - Utility functions for shaping LLM and tool responses.

These utilities underpin consistent behavior throughout the codebase.

---

## User Interfaces

### Agent Chat UI

The **agent chat UI** is a modern web application built with Next.js:

- **Technologies**
  - Next.js App Router, React, TypeScript.
  - Tailwind CSS, shadcn/ui, Radix UI.
  - Zustand for state management.
- **Features**
  - Role-based behavior (user/admin) controlled by access tokens.
  - Side-by-side visualization of:
    - User and agent messages.
    - Agent runs and their statuses.
    - Orchestration steps with detailed JSON.
    - Execution metrics (latency, tokens, tool calls).
  - Dynamic model selection based on available backend models.
  - Responsive layout optimized for interactive chat.

The UI interacts with the Agents API to create and monitor runs, automatically polling until completion.

### Control Panel UI

The **control panel UI** is a Streamlit application for operators and administrators:

- **Core Components**
  - Persistent session state with typed fields for tokens, tenants, and preferences.
  - API client with retries, backoff, and token management.
- **Views & Tabs**
  - **Dashboard** – system-wide KPIs, health status, and trends.
  - **Agents** – search and inspect runs, sessions, steps, and metrics.
  - **Jobs** – list and manage jobs, monitor status, and view event logs.
  - **Models & Providers** – manage providers, models, and defaults.
  - **Tools** – discover and invoke tools; inspect schemas and responses.
  - **Tenants** – create and manage tenants.
  - **Admin** – higher-level operations and configuration.
  - **Cypher/Graph** – interface for graph queries, including NL->Cypher experiments.
- **UX Features**
  - Paginated and sortable tables.
  - JSON drawers and log panes with search/filter capabilities.
  - Visual timelines for job and agent step events.
  - Token/role badges and scope verifiers.

This UI is the main operational console for the platform.

---

## Configuration & Environment

> **Template:** See [.env.example](.env.example) for the full annotated template with all available options.

---

## Running the Platform

### Docker Compose

The simplest way to run the full stack is via **Docker Compose**:

- Services typically include:
  - Backend app (FastAPI).
  - Worker process.
  - PostgreSQL.
  - Memgraph.
  - Redis.
  - Local LLM (e.g. Ollama) for demo mode.
  - Prometheus and Grafana.
  - Control panel UI (Streamlit).
  - Reverse proxy (e.g., Nginx).

Steps (conceptual):

1. Ensure Docker and Docker Compose are installed.
2. Configure environment variables (e.g., `.env` file).
3. Launch the stack:
   ```bash
   docker compose up -d --build --remove-orphans
   ```
4. Access:
   - Backend API via the configured host/port.
   - Chat UI and control panel via their respective ports.

The base configuration is suitable for development; additional hardening is recommended for production (TLS, secured credentials, restricted networks).

### Ports & URLs (how to discover them)

This repository supports multiple deployment variants and port mappings. To avoid guessing, discover the active mappings from Docker:

```bash
docker compose ps
```

#### Default Port Mappings (docker-compose.yml)

| Service | Container Port | Default Host Port | URL Pattern |
|---------|----------------|-------------------|-------------|
| **FastAPI Backend** | 8000 | 8000 | `http://localhost:8000` |
| **Agent Chat UI** | 3000 | 3002 | `http://localhost:3002` |
| **Control Panel UI** | 8501 | 8501 | `http://localhost:8501` |
| **PostgreSQL** | 5432 | 5432 | `postgresql://localhost:5432` |
| **Redis** | 6379 | 6379 | `redis://localhost:6379` |
| **Memgraph** | 7687 | 7687 | `bolt://localhost:7687` |
| **Memgraph Lab** | 3000 | 3001 | `http://localhost:3001` |
| **Prometheus** | 9090 | 9090 | `http://localhost:9090` |
| **Grafana** | 3000 | 3003 | `http://localhost:3003` |
| **Ollama** | 11434 | 11434 | `http://localhost:11434` |

> **Note:** Actual ports may differ based on `docker-compose.override.yml` or variant files.

Use the printed host ports to form:

* `<BACKEND_BASE_URL>` (FastAPI)
* `<CHAT_UI_URL>` (Next.js Agent UI, if exposed via Docker or run locally)
* `<CONTROL_PANEL_URL>` (Streamlit, if exposed via Docker)

Common backend endpoints (append to `<BACKEND_BASE_URL>`):

* `/v1/health/live`
* `/v1/health/ready`
* `/v1/health/components`
* `/v1/tools`
* `/v1/jobs`
* `/v1/agent-runs`

### Local Development

For local backend development without containers:

#### 1. Environment setup
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -e ".[dev,test]"
```

#### 2. Start infrastructure (Docker)
```bash
# Run only Postgres, Redis, Memgraph (not the app)
docker compose up -d postgres redis memgraph
```

#### 3. Apply database migrations
```bash
# Run Alembic migrations
alembic upgrade head

# Or via make if available
make migrate
```

#### 4. Start the FastAPI backend
```bash
uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

#### 5. Start the worker (for background jobs)
```bash
# In a separate terminal
python -m src.workers.job_worker

# Or via make if available
make worker
```

#### 6. Run tests
```bash
pytest -q

# Or via make
make test
```

Environment variables for local development can be managed via `.env` and the settings system.

### Deployment Variants

```bash
# Full stack with all services
docker compose up -d --build

# With GPU support (for local LLM inference)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# With NGINX reverse proxy
docker compose -f docker-compose.yml -f docker-compose.nginx.yml up -d
```

---

## Troubleshooting

### 401/403 errors (Auth / scopes / roles)
- Re-fetch tokens and ensure they are written into the expected `.env` used by your runtime:
  ```bash
  ./fetch_auth0_tokens.sh --save-to-env
  ```
- Confirm the JWT contains the expected tenant/roles/scopes for the endpoint/tool you are calling.

### Backend dependencies not ready (Postgres/Redis/Memgraph)
- Check container status and port mappings:
  ```bash
  docker compose ps
  docker compose logs -f
  ```
- Use component health to identify the failing dependency:
  * `<BACKEND_BASE_URL>/v1/health/components`

### UI can't reach the backend
- Verify the UI runtime is configured with the correct backend base URL.
- If running the UI locally, ensure CORS/routing is consistent with your chosen backend URL and exposed port.

---

## Operational Scripts & Tooling

The repository includes scripts to support operations:

- **ETL Loader**
  - Generate synthetic Memgraph data and load graph datasets.
- **OpenAPI Export**
  - Export the OpenAPI specification to JSON/YAML for documentation or client code generation.
- **Backup Script**
  - Back up graph (and optionally Redis) data into a tarball bundle with:
    - Data archives (e.g. `memgraph.tar.gz`).
    - `manifest.json` with metadata.
    - `checksums.sha256` for integrity verification.
- **Auth Automation**
  - Shell scripts to fetch identity provider tokens for admin/user/machine roles and populate environment files.
- **Makefile Targets** (conceptually)
  - Install dependencies.
  - Run tests and linters.
  - Build and run Docker images.
  - Seed databases.
  - Export API definitions.

These tools streamline common workflows for both development and operations.

---

## Testing Strategy

The platform includes a comprehensive test suite:

- **Unit Tests**
  - Cover pure functions and small components:
    - Intent classifier, PII scrubber, archive logic.
    - Auth helpers, validators, utilities.
- **Integration Tests**
  - Exercise interactions across components:
    - API routes and FastAPI app.
    - Postgres repositories and migrations.
    - Redis caches and rate limiting.
    - Memgraph operations and ETL.
    - Multi-tenant behavior.
- **End-to-End Tests**
  - Hit the HTTP API and validate full flows:
    - Health endpoints.
    - Basic agent runs.
    - Tool invocations and error paths.
- **Security Tests**
  - Focus on:
    - Authentication/authorization.
    - Dangerous operation handling.
    - PII masking and output guards.
    - Rate limiting correctness.
- **Performance Tests**
  - Measure latency and resource usage under load.
  - May be opt-in (e.g., via special flags in test runner).

Common test fixtures manage environments for Postgres, Redis, and Memgraph, including in-memory/fake versions where appropriate.

### Test Metrics

The project has comprehensive test coverage with **3,000+ test cases** organized by category:

| Metric | Count |
|--------|-------|
| **Total Test Cases** | 3,000+ |
| **Test Files** | 236 |
| **Test Functions** | 2,720 |
| **Test Categories** | 27 |

### Memgraph NL Test Mode

For deterministic testing of natural language graph queries, the platform supports a **Memgraph NL test mode**:

- A JSON file maps **normalized prompts** to metadata including expected Cypher.
- Environment variables control:
  - Enabling/disabling NL test mode.
  - Path to the test prompts file.
- When test mode is enabled:
  - The NL->Cypher component reads expected Cypher from the test hints file.
  - Tests become deterministic and independent of LLM output variability.

This significantly improves test reliability for graph-related features.

---

## Typical End-to-End Flows

### Chat / Agent Run

1. User opens the chat UI and authenticates.
2. UI obtains access token and discovers available models.
3. User sends a prompt; UI creates a new agent run via the API.
4. Backend:
   - Validates token, extracts tenant/roles.
   - Classifies intent and selects mode.
   - Orchestrator executes multi-step run with LLM calls and tools.
   - Steps, metrics, and final output are persisted.
5. UI polls the run until completion and renders:
   - Conversation.
   - Orchestration steps.
   - Execution metrics.

### Graph Q&A

1. User asks a graph-related question (e.g., “Which institutions collaborated on tasks using sample X?”).
2. Intent classifier routes to graph mode.
3. Orchestrator:
   - Generates Cypher from NL (or uses hints in test mode).
   - Validates Cypher for safety.
   - Executes query on Memgraph.
   - Summarizes results in natural language.
4. Response is returned to the user with optional visibility into the underlying query and data.

### Long-Running Job

1. Admin triggers a long-running operation via the control panel.
2. Backend creates a job record and enqueues it; worker processes the job with SSE streaming.
3. Control panel displays real-time progress and final outcome.

For detailed job lifecycle, worker processing, and SSE streaming, see [Jobs, Workers & Background Tasks](#jobs-workers--background-tasks) and the [Long-Running Job Workflow](#long-running-job-workflow) diagram.

### Provider Onboarding

1. Admin registers a new LLM provider with credentials and configuration.
2. Backend stores provider and model metadata in Postgres.
3. Default model resolution is updated and cached in Redis.
4. Orchestrator and adapters now can route LLM calls through the new provider, respecting resilience policies.

---

## Production Notes & Best Practices

- **Security**
  - Use a hardened reverse proxy with TLS termination.
  - Configure strict CORS and cookie settings.
  - Store secrets securely (e.g., using an external secret manager).
- **Multi-Tenancy**
  - Ensure tenant boundaries are enforced at the repository and service levels.
  - Configure per-tenant models, limits, and roles as needed.
- **Scaling**
  - Scale the backend app and worker processes horizontally.
  - Scale stateful services (Postgres, Redis, Memgraph) according to load patterns.
- **Observability**
  - Integrate metrics and traces with your monitoring stack.
  - Set up alerts for critical metrics (error rates, queue depth, resource usage).
- **Evolution**
  - Use migrations to evolve the schema; avoid manual DB changes.
  - Use deprecation utilities to phase out endpoints and features safely.

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

## API Endpoints

The platform provides **76 API endpoints** across **60 unique paths**, organized into **16 categories**:

| Category | Endpoints | Description |
|----------|-----------|-------------|
| **admin-tenants** | 5 | Multi-tenant management |
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

### Admin - Tenants (5)
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

# Base runtime dependencies (pinned)
pip install -r requirements.txt
# Install project in editable mode with dev+test extras
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
