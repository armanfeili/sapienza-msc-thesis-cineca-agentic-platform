# Cineca Agentic Platform

A production-grade, agentic AI platform for multi-tenant, secure, observable, and orchestrated LLM workflows.

---

## 1. Overview

The **Cineca Agentic Platform** is an enterprise-ready system that exposes:

* A **FastAPI backend** with a rich, versioned REST API
* A **graph-aware orchestration engine** that combines LLMs, MCP tools, and Memgraph
* A **background jobs subsystem** backed by Redis and PostgreSQL
* Two **user interfaces**:

  * A modern **Next.js chat UI** for agent interactions
  * A **Streamlit control panel** for admin/ops
* A complete **Docker-based deployment stack** with Prometheus/Grafana, Ollama, and supporting services

It is designed to support **multi-tenant**, **RBAC-secured**, and **observable** LLM workflows, where agents can plan, call tools, query graphs, and run long-running jobs with full auditability.

---

## 2. High-Level Architecture

At the highest level, the platform looks like this:

```text
          ┌─────────────────────────────┐
          │   Next.js Chat UI           │  (ui_agent)
          └─────────────┬───────────────┘
                        │ HTTP (REST/WebSockets)
          ┌─────────────▼───────────────┐
          │       FastAPI Backend       │
          │   - Orchestrator Service    │
          │   - Session Service         │
          │   - Jobs Service            │
          │   - MCP Tools (Graph, etc.) │
          └───────────┬─────┬───────────┘
                      │     │
     ┌────────────────┘     └─────────────────┐
     │                                        │
┌────▼───────┐                        ┌───────▼────────┐
│ PostgreSQL │                        │   Memgraph     │
│  (RDBMS)   │                        │ (Graph DB)     │
└────▲───────┘                        └───────▲────────┘
     │   ▲                                     │
     │   │                                     │
┌────▼───┴────────┐                   ┌────────┴───────┐
│  Redis          │                   │  Ollama / LLMs │
│ (Cache, Queues) │                   │ + other LLMs   │
└────▲───────┬────┘                   └────────▲───────┘
     │       │                                  │
     │       │                                  │
     │ ┌─────▼──────────────────┐               │
     │ │  Jobs Worker(s)        │               │
     │ │  (async job executor)  │               │
     │ └────────────────────────┘               │
     │
     │ HTTP / API
┌────▼─────────────────────┐
│ Streamlit Control Panel  │ (ui_control_panel)
└──────────────────────────┘
```

Key characteristics:

* **Core backend**: FastAPI app with modular services (`src/services/*`) and lazy-loaded adapters (`src/adapters/*`).
* **Data stores**:

  * PostgreSQL for relational persistence and job tracking
  * Memgraph for graph-based bioinformatics and knowledge graphs 
  * Redis for caching, rate limiting, sessions, and job queues 
* **LLM layer**: Multi-provider adapter for OpenAI/Ollama and demo LLMs. 
* **Tooling and graph**: MCP tools for graph CRUD, queries, and natural language → Cypher. 
* **Observability stack**: Prometheus + Grafana + OpenTelemetry integrated in Docker.

---

## 3. API Layer

The `docs/general/README_api.md` describes the public REST API, defined via **OpenAPI 3.1.0** specifications. 

### 3.1 Scope of the API

The API provides endpoints for:

* **Health & Monitoring**
* **Authentication & Users**
* **Tools & MCP integration**
* **Jobs & Background processing**
* **AI Models & Instances**
* **Model Providers & Manifests**
* **Agent Sessions & Runs**
* **Tenant Management**
* **Process Management**
* **Batch Operations, Export/Import**
* **Internal/Admin Operations**

The main files:

* `openapi.json`: canonical, full v1 specification
* `openapi_v1.json`: stable v1 subset
* `openapi_v2.json`: experimental v2 surface (currently mainly health) 

### 3.2 Authentication

The API uses **JWT Bearer tokens**:

```yaml
securitySchemes:
  HTTPBearer:
    type: http
    scheme: bearer
    bearerFormat: JWT
```

Tokens are issued by **Auth0** and are role- and scope-based:

* Admin tokens: full access (admin + tools:invoke:all + user:me)
* User tokens: limited tool and user scopes
* Machine tokens: client credential flows for automation

Tokens are consumed both by:

* The **backend FastAPI** for RBAC and multi-tenant isolation
* The **UIs** (Next.js + Streamlit) to call the backend with proper privileges

### 3.3 API Categories

Each category in the OpenAPI spec maps to a functional area:

* `/health/*`: liveness/readiness for Kubernetes/Docker
* `/v1/user/*`: user info, tokens, and introspection
* `/v1/tools/*`: MCP tool discovery and invocation
* `/v1/jobs/*`: submit, query, and manage jobs (with SSE streaming support)
* `/v1/models/*`: providers, instances, manifests, defaults
* `/v1/agents/*`: sessions and runs management
* `/v1/tenants/*`: full multi-tenant lifecycle
* `/v1/admin/*`: administrative and internal operations

These are implemented in FastAPI routers that delegate to **services** (section 5).

---

## 4. Deployment & Infrastructure (Docker Stack)

`README_Cineca-Agentic-Platform_docker.md` describes a full **Docker Compose** stack that supports development, testing, and production. 

### 4.1 Core Containers

* **`app`**: FastAPI application (Python 3.11 slim)

  * Exposes port `8000`
  * Health endpoints integrated with DB checks
  * Depends on PostgreSQL, Memgraph, Redis, and Ollama
* **`postgres`**: PostgreSQL 16-alpine

  * Persistent volume
  * `pg_isready` health checks
* **`memgraph`**: Memgraph Platform (graph DB)

  * Bolt (7687) + Web UI (3000)
* **`redis`**: Redis 7-alpine

  * Used for rate limiting, cache, sessions, and job queues
* **`ollama`**: Ollama models

  * Local LLM inference with GPU support
* **`worker`**: background job worker (same image as `app`)

  * Runs the jobs worker loop (see section 7)
* **`db-populate`**: one-off Memgraph population job
* **Monitoring**:

  * `prometheus` for metrics scraping
  * `grafana` for dashboards
* **UI services**:

  * `ui_control_panel` (Streamlit)
  * Optionally `ui_agent` (Next.js) as a separate container

The **startup order** is infrastructure → AI services → app → workers → UI → monitoring. 

### 4.2 Dockerfile & Entry Point

The main image is built via a **multi-stage Dockerfile**:

* App stage: install dependencies, copy `src/`, `db/`, and `docker-entrypoint.sh`, run under a non-root `app` user.
* Test runner stage: separate image for running pytest with a local Redis. 

`docker-entrypoint.sh`:

* Runs Alembic migrations (`db/postgres_control`) and initializes default Ollama models.
* Then executes the main command (usually `uvicorn src.app:app`). 

### 4.3 Environments & Profiles

* `docker-compose.yml`: base stack
* `docker-compose.override.dev.yml`: development conveniences
* `docker-compose.nginx.yml`: production with reverse proxy and SSL
* `docker-compose.gpu.yml`: GPU-enabled deployments

Volumes are provisioned for PostgreSQL, Memgraph, Redis, Ollama, Prometheus, and Grafana to ensure persistence. 

---

## 5. Service Layer (`src/services`)

The **services framework** is the core business layer of the platform. It provides orchestrated, async-first operations with lazy loading and strong typing.

### 5.1 Service Infrastructure

Shared types:

* `ServiceResult[T]`: typed result with success/failure
* `ServiceStatus`: health status with timestamps
* `ServiceError`: base class for service-level errors
* `ServiceBase`: base class with logging, health checks, and settings

Services are retrieved via a **lazy-loading factory**:

```python
from src.services import get_orchestrator, get_session_service

orchestrator = get_orchestrator()
session_svc = get_session_service()
```

Internally, a `ServiceContainer` maps service types to instances, allowing simple, typed access and test-friendly replacement. 

### 5.2 Orchestrator Service

The orchestrator is the **central coordination engine** for agent runs, combining LLM planning, tool calls, and graph operations. It is documented in both `README_services.md` and `README_src_services_orchestrator.md`.

Key features:

* **Multi-LLM support**: multiple named LLM clients with automatic failover
* **MCP tool integration**: async/sync execution of tools with access control
* **Graph integration**: Memgraph queries via dedicated tools/adapters
* **Redis-backed caching**: optional caching of run outputs and sub-results
* **Intent classification**: delegating to `src.services.intent_classifier` for routing
* **Planning system**: TODO-list based planning and step-by-step execution
* **Metrics & audit**: extensive metrics (LLM calls, tool calls, latencies) and audit logging
* **Timeout management**: device-aware timeouts, step budgets, and global run budgets

Core data types:

* `OrchestrationContext`: holds goal, user/session/tenant IDs, run ID, principal, and variables
* `Step`: each orchestration step contains ID, action, input, meta, timestamps, and latency
* `OrchestrationResult`: includes steps, outputs, todos, errors, warnings, metrics, and counters 

### 5.3 Session Service

The session service manages conversational **chat sessions**:

* Stores message history (user/assistant/system/tool) with timestamps and metadata
* Supports Redis-based persistence with TTLs and in-memory fallback
* Exposes CRUD operations used by the API and UI to maintain conversational context

### 5.4 Other Services

Additional services documented in `README_src_services.md`:

* **Archive Service**: snapshot/restore of graph data and filesystem archives
* **Default Model Resolver**: resolves the default LLM model, caching results in Redis and persisting authoritative state in PostgreSQL
* **ETL Service**: CSV/JSON graph imports and snapshot exports for Memgraph 

These services integrate with adapters (`db.memgraph_domain`, `db.postgres_control`, `db.redis_cache`, and `src.adapters.llm`) and are observable, secure, and testable. 

---

## 6. Adapters & Utilities

### 6.1 Adapters (`src/adapters`)

The **Adapters framework** centralizes access to external dependencies via **lazy-loading**:

* **Memgraph adapter**: connection pooling, health checks, and helpers for Cypher queries
* **Redis adapter**: key-value operations, JSON serialization, TTL management
* **LLM adapter**: abstraction over OpenAI/Ollama/custom providers
* **MCP client adapter**: tool discovery, schema-driven invocation, and standardised results 

Key design traits:

* Uses `__getattr__` (PEP 562) for lazy imports
* Avoids import-time side effects and speeds up cold starts
* Presents a minimal, ergonomic API for query/execute operations

### 6.2 Utilities (`src/utils`)

The utilities package includes cross-cutting concerns such as:

* **Pagination** (`pagination.py`): page tokens, ETag generation, response caching
* **Idempotency** (`idempotency.py`): decorator-based idempotent operations, fast to integrate with FastAPI endpoints
* **Provider resolution** (`provider_resolver.py`): standardizes base URLs, timeouts, and upstream model IDs (with Ollama-specific handling)
* **Run output normalization** (`run_output.py`): converts arbitrary outputs into schemas suitable for Pydantic and JSON
* **Principal utilities** (`principal.py`): user/tenant extraction
* **JSON helpers** (`jsonable.py`): safe dumps/loads with fallbacks
* **ETag support** (`etag.py`): HTTP ETag generation/validation
* **Deprecation helpers** (`deprecation.py`)
* **Test helpers** (`test_helpers.py`) for async tests and mocking 

These utilities are heavily reused across services and API endpoints to guarantee consistent behaviour (pagination, caching, idempotency, safe JSON, etc.).

---

## 7. Background Jobs & Workers

The **Workers framework** (`src/workers`) powers asynchronous job execution. 

### 7.1 Architecture

* Jobs are queued in **Redis** and persisted in **PostgreSQL**.
* Workers run as separate processes (or containers) and follow this lifecycle:

```text
Redis Queue → Dequeue → Load job from PostgreSQL → Execute → Save result → Update status
```

### 7.2 Job Lifecycle

Statuses:

* `queued` → job is pending
* `running` → worker claimed and is executing
* `finished` → successful completion
* `failed` → error occurred
* `cancelled` → cancelled via Redis flags

Workers feature:

* **Multi-queue support** (different job types)
* **Cancellation** via Redis flags checked during execution
* **Heartbeat monitoring** to update liveness in the DB
* **Graceful shutdown** via signal handling
* **Event logging** for complete job history (events table) 

### 7.3 Job Types

Examples (extensible):

* `demo`: simulates work through sleep and returns timings
* `test`: echoes input payload immediately
* `long-running`: multi-step processes with progress simulation

Jobs are submitted through the API and orchestrated services; the **Streamlit control panel** exposes a UI for monitoring and managing them.

---

## 8. Graph Domain & Tools

### 8.1 Memgraph Domain (`db/memgraph_domain`)

This module is the **graph data layer**, tailored for bioinformatics-like workloads:

* Graph client factory using `gqlalchemy`
* Pydantic-based configuration via env variables
* Synthetic data generator (`populate.py`)
* Original dataset loader from JSON/CSV
* Docker integration for population (`db-populate` service)
* Sample queries in Cypher (`sample_queries.txt`)

The schema models entities like:

* Users
* Institutions
* Tasks (BLAST searches, taxonomy, database creation)
* Files and related artefacts

It also exposes convenience functions such as:

* `get_memgraph()`, `populate(...)`, `build_graph()`, `persist_graph(...)`, and `create_from_original_and_populate(...)` for programmatic integration. 

### 8.2 Graph MCP Tools (`src/mcp/tools/graph`)

The **graph tools** provide MCP-compatible operations over Memgraph, including: 

* **Search**: find nodes/relationships, filter by labels/properties
* **Bulk ingest**: large-scale node/relationship imports with batching
* **Secure query**: natural-language to graph querying with access control and output formatting
* **Schema discovery**: labels, relationship types, counts, and other schema metadata

These tools emit rich metrics (`graph_tool_invocations_total`, `graph_tool_duration_seconds`, etc.) and structured logs for observability.

---

## 9. Security & Authentication

Security is layered across:

1. **Auth0-based authentication** and JWT tokens used by API and UIs.
2. **Role-based access control** (Admin/User/Machine) with scopes:

   * `user:me`, `tools:invoke:*`, `admin:*`, etc.
3. **Tenant isolation**: tenant IDs are embedded in principals and passed across services; Memgraph, PostgreSQL, and Redis usage respect tenant separation. 
4. **Audit logging**: orchestrator and services log all sensitive operations.
5. **UI controls**:

   * `ui_agent`: role-aware, token-based chat UI
   * `ui_control_panel`: token badges, scope-based feature visibility, and access checks

Scripts like `fetch_auth0_tokens.sh` manage token acquisition, validation, and safe storage for development and CI. 

---

## 10. Observability & Health

Observability is a first-class concern:

* Metrics via **Prometheus** and **OpenTelemetry**:

  * Orchestrator metrics (`orchestrator_runs_total`, LLM calls, tool calls)
  * Service-specific metrics (session operations, cache hits, etc.) 
* Dashboards via **Grafana** (auto-provisioned dashboards and data sources). 
* Structured logging using **structlog**, correlation IDs, and rich context.
* Health checks:

  * `/health` endpoints in the FastAPI app
  * Memgraph, PostgreSQL, Redis, and Ollama health probes in Docker
  * Orchestrator-specific health via tools (`system.health`)

The **Streamlit control panel** includes health cards and dashboards (health_cards, dashboard view) to surface these metrics visually. 

---

## 11. User Interfaces

### 11.1 `ui_agent` (Next.js Chat Frontend)

The `ui_agent` app is a **Next.js 14 / TypeScript** UI that provides the main **chat interface**: 

* Role-based authentication toggle (Admin/User) integrated with Auth0
* Real-time chat with agents, including:

  * Run status (queued/running/succeeded/failed/cancelled)
  * Orchestration steps rendered as collapsible sections
  * Metrics (latencies, token usage, tool calls)
  * TODO tracking, outputs, and error surfaces
* Model selection UI: fetches models from backend and updates selected model
* Zustand-based state management:

  * `auth-store.ts`: manages tokens and roles (SSR-safe, localStorage-backed)
  * `chat-store.ts`: messages, runs, loading states, auto-scroll
* `lib/api.ts`: typed client for backend API (create runs, list models, get run details)
* Built with Tailwind CSS + Radix UI (via shadcn/ui) for a modern UX

This is the UI end-users would use to “talk to” the agentic system.

### 11.2 `ui_control_panel` (Streamlit Admin Panel)

The **Streamlit-based control panel** is an administrative cockpit. It provides: 

* **Auth & Tokens**: manage tokens, view scopes, auto-renew, see token badges
* **Agent Runs**: list, filter, and inspect runs and sessions
* **Jobs**: monitor job queues, statuses, and histories
* **Models**: explore model providers, instances, manifests, and defaults
* **Tenants**: manage multi-tenant environments
* **Tools**: discover and invoke MCP tools via schema-driven forms
* **Explore & Cypher**: API explorer and natural-language-to-Cypher view
* **Health & Dashboard**: system-level monitoring views

Internally it consists of:

* `app.py`: main app and navigation
* `api.py`: robust HTTP client with token management, retries, caching
* `state.py`: typed Streamlit session state
* A set of components (`health_cards`, `tool_card`, `tenant_selector`, `log_pane`, `json_drawer`, etc.)
* Views (`auth.py`, `agents.py`, `jobs.py`, `models.py`, `tools.py`, `tenants.py`, `admin.py`, `dashboard.py`, etc.) 

---

## 12. Development, Tooling & Automation

### 12.1 Scripts & Makefile

`README_Cineca-Agentic-Platform_scripts.md` documents:

* **Auth scripts**:

  * `fetch_auth0_tokens.sh`: fetch admin/user/machine tokens, validate them, write them into `.env`, etc. 
* **Makefile targets**:

  * Environment setup (`env`, `install`, `pre-commit-install`)
  * Running dev server (`dev`, `ready`)
  * Docker orchestration (`up`, `up-gpu`, `up-cpu`, `up-observability`)
  * LLM smoke tests (`llm-smoke-test`, `runtime-smoke`)
  * OpenAPI export (`openapi`, `openapi-docker`)
  * CI helpers (`ci`, `test-ci`)

This provides a **complete developer workflow**: from env bootstrap to automated testing, security checks, and deployment.

### 12.2 Testing Infrastructure

Testing is multi-layered:

* **Unit & integration tests**: pytest-based, with async support and shared fixtures; memgraph, Redis, and services are all tested using dedicated helpers.
* **Graph-specific tests**: `test-memgraph` and `test-memgraph-nl` pipelines for NL→Cypher, including automated restarts and token refresh. 
* **End-to-end UI tests**: Playwright configuration for the Streamlit UI:

  * Cross-browser testing
  * CI-optimised, JUnit + HTML reports, trace/screenshot/video on failure
  * Local development mode auto-starts Docker services 

---

## 13. Project Documentation Files (What Each README Covers)

The 37 README files in the `docs/general` (and related) folder act as **module-level documentation**. Conceptually:

* **Core platform & background**

  * `README_background.md`: narrative and design goals of the platform
* **APIs and external interfaces**

  * `README_api.md`: OpenAPI specifications and API categories/v1/v2 
  * `README_mcp_tools.md`: overview of MCP tools (graph, jobs, etc.)
* **Runtime & infra**

  * `README_docker.md`: full Docker stack, services, networking, volumes, GPU support 
  * `README_health.md`: health endpoints and their semantics
  * `README_observability.md`: metrics, tracing, logging
  * `README_resilience.md`: circuit breakers, retries, backoff, idempotency
* **Security**

  * `README_security.md`: threat model, RBAC, audit logging, tenant isolation
  * `README_src_security.md`: security-specific code in `src/security`
* **Data & storage**

  * `README_postgres_control.md` / `README_postgres_control_alembic_versions.md`: PostgreSQL schema & migrations
  * `README_memgraph_domain.md`: Memgraph domain, schema, population, queries 
  * `README_redis_cache.md`: Redis usage patterns and data structures
  * `README_migrations.md`: DB migration strategies
* **Business logic layer**

  * `README_services.md`: high-level services framework 
  * `README_src_services.md`: detailed service implementations in `src/services` 
  * `README_src_services_orchestrator.md`: orchestrator architecture and APIs 
  * `README_services_intent_classifier.md`: intent classification service
* **Adapters & utilities**

  * `README_adapters.md`: adapters framework for external systems 
  * `README_utils.md` / `README_src_utils.md`: utilities (pagination, idempotency, JSON, etc.) 
* **Graph & tools**

  * `README_graph.md`: graph tools (search, bulk ingest, secure query, schema) 
* **Jobs & workers**

  * `README_jobs.md`: job domain, models, APIs
  * `README_workers.md` / `README_src_workers.md`: worker implementation and configuration 
* **UIs**

  * `README_ui_agent.md`: Next.js chat UI documentation 
  * `README_ui_control_panel.md`: Streamlit admin/control panel documentation 
* **Testing**

  * `README_tests.md`: tests architecture
  * `README_test_memgraph.md`: Memgraph-specific tests
* **Config, schemas, and repositories**

  * `README_config_modules.md`: settings modules and env configuration
  * `README_schemas.md`: Pydantic schemas for API and services
  * `README_models.md`: ORM/domain models
  * `README_repositories.md`: repository pattern for DB access
* **Other**

  * `README_errors.md`: error taxonomy and handling
  * `README_health.md`: health model and endpoints
  * `README_scripts.md` / `README_auth_automation_requirements_scripts.md`: scripts, Makefile, auth automation

Together, these READMEs form a **complete documentation surface** for the platform, aligned with the code structure.

---

## 14. Putting It All Together

In operation, a typical flow looks like:

1. A user opens the **Next.js chat UI** (`ui_agent`), chooses a role, and authenticates.
2. The UI obtains a JWT from Auth0, stores it, and sends a chat message + selected model to the backend via the **REST API**.
3. The FastAPI backend:

   * Creates an **agent session/run** entry in PostgreSQL.
   * Passes an `OrchestrationContext` with user/tenant info into the **orchestrator service**.
4. The orchestrator:

   * Uses the **intent classifier** to decide whether to call tools, graph, jobs, etc.
   * Interacts with **LLMs** via adapter, possibly planning a TODO list.
   * Invokes **MCP tools**, including **graph** tools (Memgraph) or job submission tools.
   * Stores intermediate steps, metrics, and outputs, potentially caching results in Redis.
5. If long-running work is needed, the orchestrator or tools submit a job into the **jobs service** which enqueues into Redis and persists in PostgreSQL.
6. A **worker** process picks up jobs, executes them, updates statuses, logs events, and handles cancellations. 
7. The UI polls the run status or subscribes to updates, rendering:

   * Steps, metrics, and outputs
   * TODOs and their statuses
   * Any errors or warnings 
8. Operators use the **Streamlit control panel** to:

   * Inspect runs, jobs, models, tenants, tools, and metrics
   * Trigger admin actions, ETL, or health checks
   * Monitor overall platform health and performance

All of this runs on a **Dockerised, observable, secure** stack with clear layering:

* Frontend UIs
* API & services
* Adapters & utilities
* Data stores (PostgreSQL, Memgraph, Redis)
* LLM + tools infrastructure
* Jobs & workers
* Monitoring, metrics, and admin tooling
