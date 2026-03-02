# Cineca Agentic Platform

A production-ready, multi-tenant **agentic AI platform** built on FastAPI, PostgreSQL, Redis, Memgraph, and multiple LLM providers.  
It orchestrates LLM calls, graph queries, and MCP tools with strong security, observability, and UI layers for both end users and administrators.

---

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [High-Level Architecture](#high-level-architecture)
4. [Core Backend](#core-backend)
   - [API Layer](#api-layer)
   - [Domain Schemas](#domain-schemas)
   - [Error Handling](#error-handling)
   - [Configuration & Compute Settings](#configuration--compute-settings)
5. [Data & Persistence Layer](#data--persistence-layer)
   - [PostgreSQL Control Plane](#postgresql-control-plane)
   - [Redis Cache & Queues](#redis-cache--queues)
   - [Memgraph Graph Domain](#memgraph-graph-domain)
6. [Services & Orchestrator](#services--orchestrator)
   - [Service Layer](#service-layer)
   - [Intent Classification](#intent-classification)
   - [Agent Orchestration Engine](#agent-orchestration-engine)
   - [LLM Resilience & Cost Control](#llm-resilience--cost-control)
7. [MCP Tools & Tooling Ecosystem](#mcp-tools--tooling-ecosystem)
8. [Jobs, Workers & Background Tasks](#jobs-workers--background-tasks)
   - [Asynchronous Jobs](#asynchronous-jobs)
   - [Worker Processes](#worker-processes)
   - [Background Framework](#background-framework)
9. [Security & Governance](#security--governance)
   - [Authentication & Identity](#authentication--identity)
   - [Authorization & Roles](#authorization--roles)
   - [Rate Limiting, PII & Output Guards](#rate-limiting-pii--output-guards)
   - [Audit & Compliance](#audit--compliance)
10. [Observability & Health](#observability--health)
    - [Metrics](#metrics)
    - [Tracing](#tracing)
    - [Health Probes](#health-probes)
11. [Utilities & Cross-Cutting Helpers](#utilities--cross-cutting-helpers)
12. [User Interfaces](#user-interfaces)
    - [Agent Chat UI](#agent-chat-ui)
    - [Control Panel UI](#control-panel-ui)
13. [Configuration & Environment](#configuration--environment)
14. [Running the Platform](#running-the-platform)
    - [Docker Compose](#docker-compose)
    - [Local Development](#local-development)
15. [Operational Scripts & Tooling](#operational-scripts--tooling)
16. [Testing Strategy](#testing-strategy)
    - [Memgraph NL Test Mode](#memgraph-nl-test-mode)
17. [Typical End-to-End Flows](#typical-end-to-end-flows)
18. [Production Notes & Best Practices](#production-notes--best-practices)

---

## Overview

The platform provides a complete stack to **design, execute, and observe agentic AI workflows**:

- A **FastAPI** backend that exposes the Agents API, Jobs API, Models/Providers API, MCP tools API, Tenants API, and Health endpoints.
- A **service layer** that orchestrates LLM providers, tools, and databases through an extensible agent engine.
- A **PostgreSQL control plane** storing tenants, agents, runs, steps, jobs, tools, model definitions, and audit logs.
- A **Redis data plane** for caching, job queues, rate limiting, idempotency, and session state.
- A **Memgraph graph database** with a domain model and secure NL→Cypher capabilities for graph Q&A.
- A **resilience framework** with provider fallback, circuit breakers, and cost tracking.
- A **security framework** with OIDC/JWT, RBAC, PII scrubbing, rate limiting, and output guards.
- A **background framework** for scheduled health checks, backups, and cleanups.
- Two **user interfaces**:
  - A **Next.js chat UI** for end users.
  - A **Streamlit control panel** for admins and operators.
- A comprehensive **observability** setup (Prometheus metrics, tracing, structured logging) and a **test suite** covering unit, integration, e2e, security, and performance tests.

The design goal is to be **production-ready**: opinionated about safety, observability and resilience, but flexible enough to integrate with diverse LLM providers and graph workloads.

---

## Key Features

- **Agentic orchestration**: multi-step runs with TODO lists, tools, and graph queries.
- **Multi-provider LLM support**: OpenAI-style APIs, Ollama, demo/stub providers and custom providers.
- **Memgraph integration**: graph schema, ETL, analytics, CRUD, and natural language graph queries.
- **MCP tools**: rich tool catalog for graph, cache, data, security, admin, and utilities.
- **Asynchronous jobs**: persistent job lifecycle, SSE event streaming, and background workers.
- **Security first**: OIDC/JWT, RBAC, scopes, rate limits, PII scrubbing, and auditable dangerous-ops handling.
- **Observability**: metrics for HTTP, jobs, tools, agents, rate limits, and provider health; plus tracing and structured logging.
- **UIs**: modern chat UI for users and a control panel for operators and maintainers.

---

## High-Level Architecture

Conceptually, the platform is organized in three layers plus cross-cutting concerns:

1. **Core Backend**
   - FastAPI application (Agents, Jobs, Tools, Models/Providers, Tenants, Auth, Health).
   - Service layer (orchestrator, session, default model resolution, ETL, archive, health).
   - MCP tools and adapters (LLMs, Memgraph, Redis).
   - Resilience and background frameworks.

2. **Data & Infrastructure**
   - PostgreSQL as **control plane**.
   - Redis as **cache, queue and coordination** layer.
   - Memgraph as **graph data store**.
   - Worker processes for asynchronous jobs.

3. **Presentation**
   - **Agent chat UI** (Next.js).
   - **Control Panel UI** (Streamlit).

**Cross-cutting modules** implement:

- Configuration and compute settings.
- Security and authorization policies.
- Observability (metrics, logs, traces).
- Utilities (pagination, idempotency, provider resolution, JSON, ETag, deprecation).

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
  - Introspection endpoints (OpenAPI export, etc.).

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

- **Domain Schema**
  - Nodes such as users, institutions, computational tasks, and files.
  - Relationships encoding lineage and association (e.g., tasks producing/consuming files, user membership in institutions).
- **Population & ETL**
  - Scripts to load both a reference “original dataset” and synthetic data.
  - Export/import via JSONL and CSV for reproducible states.
- **Graph Operations**
  - Analytics (counts, degree, centrality).
  - CRUD for nodes and relationships.
  - Schema discovery and search.
- **Natural Language Graph Querying**
  - Secure NL→Cypher pipeline:
    - The user asks a natural language question.
    - An LLM-assisted component drafts Cypher.
    - A safety layer validates the Cypher.
    - The query is executed on Memgraph.
    - Results are turned back into a natural language answer.

Graph operations are exposed both through the agent orchestration engine and through dedicated tooling and UI components.

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
   - NL→Cypher translation.
   - Cypher safety validation.
   - Execution and result summarization.
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

---

## Jobs, Workers & Background Tasks

### Asynchronous Jobs

Long-running tasks are executed through the **job system**:

- **Job Lifecycle**
  - `queued → running → finished / failed / cancelled`
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
  - **Cypher/Graph** – interface for graph queries, including NL→Cypher experiments.
- **UX Features**
  - Paginated and sortable tables.
  - JSON drawers and log panes with search/filter capabilities.
  - Visual timelines for job and agent step events.
  - Token/role badges and scope verifiers.

This UI is the main operational console for the platform.

---

## Configuration & Environment

Configuration is primarily driven by environment variables and layered settings:

- **Database**
  - Connection URLs for Postgres.
  - Pool sizes, timeouts, and pre-ping options.
- **Redis**
  - Host, port, database index.
  - SSL and password if needed.
- **Memgraph**
  - Host, port, and credentials if configured.
- **LLM Providers**
  - Provider names, base URLs, API keys.
  - Timeouts, maximum tokens, and budgets.
  - Fallback priorities and resilience settings.
- **Security**
  - OIDC issuer and audience.
  - JWKS URL.
  - Encryption secrets for API keys.
- **Jobs & Workers**
  - Allowed job types.
  - Poll intervals and batch sizes.
  - TTLs for jobs and events.
- **Rate Limits**
  - Requests per window per scope.
  - Window duration.
- **Observability**
  - Metrics endpoint and ports.
  - OTLP exporter config.

A dedicated compute configuration layer translates raw env vars into derived settings (e.g., concurrency) for the orchestrator and workers.

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
   docker compose up -d
````

4. Access:

   * Backend API via the configured host/port.
   * Chat UI and control panel via their respective ports.

The base configuration is suitable for development; additional hardening is recommended for production (TLS, secured credentials, restricted networks).

### Local Development

For local backend development without containers:

1. Create and activate a Python virtual environment.
2. Install Python dependencies.
3. Run Postgres, Redis, and Memgraph locally or via Docker.
4. Apply database migrations.
5. Start the FastAPI app (e.g., via `uvicorn`).
6. Optionally start a local worker to process jobs.

Environment variables for local development can be managed via `.env` and the settings system.

---

## Operational Scripts & Tooling

The repository includes scripts to support operations:

* **ETL Loader**

  * Generate synthetic Memgraph data and load graph datasets.
* **OpenAPI Export**

  * Export the OpenAPI specification to JSON/YAML for documentation or client code generation.
* **Backup Script**

  * Back up graph (and optionally Redis) data into a tarball bundle with:

    * Data archives (e.g. `memgraph.tar.gz`).
    * `manifest.json` with metadata.
    * `checksums.sha256` for integrity verification.
* **Auth Automation**

  * Shell scripts to fetch identity provider tokens for admin/user/machine roles and populate environment files.
* **Makefile Targets** (conceptually)

  * Install dependencies.
  * Run tests and linters.
  * Build and run Docker images.
  * Seed databases.
  * Export API definitions.

These tools streamline common workflows for both development and operations.

---

## Testing Strategy

The platform includes a comprehensive test suite:

* **Unit Tests**

  * Cover pure functions and small components:

    * Intent classifier, PII scrubber, archive logic.
    * Auth helpers, validators, utilities.
* **Integration Tests**

  * Exercise interactions across components:

    * API routes and FastAPI app.
    * Postgres repositories and migrations.
    * Redis caches and rate limiting.
    * Memgraph operations and ETL.
    * Multi-tenant behavior.
* **End-to-End Tests**

  * Hit the HTTP API and validate full flows:

    * Health endpoints.
    * Basic agent runs.
    * Tool invocations and error paths.
* **Security Tests**

  * Focus on:

    * Authentication/authorization.
    * Dangerous operation handling.
    * PII masking and output guards.
    * Rate limiting correctness.
* **Performance Tests**

  * Measure latency and resource usage under load.
  * May be opt-in (e.g., via special flags in test runner).

Common test fixtures manage environments for Postgres, Redis, and Memgraph, including in-memory/fake versions where appropriate.

### Memgraph NL Test Mode

For deterministic testing of natural language graph queries, the platform supports a **Memgraph NL test mode**:

* A JSON file maps **normalized prompts** to metadata including expected Cypher.
* Environment variables control:

  * Enabling/disabling NL test mode.
  * Path to the test prompts file.
* When test mode is enabled:

  * The NL→Cypher component reads expected Cypher from the test hints file.
  * Tests become deterministic and independent of LLM output variability.

This significantly improves test reliability for graph-related features.

---

## Typical End-to-End Flows

### Chat / Agent Run

1. User opens the chat UI and authenticates.
2. UI obtains access token and discovers available models.
3. User sends a prompt; UI creates a new agent run via the API.
4. Backend:

   * Validates token, extracts tenant/roles.
   * Classifies intent and selects mode.
   * Orchestrator executes multi-step run with LLM calls and tools.
   * Steps, metrics, and final output are persisted.
5. UI polls the run until completion and renders:

   * Conversation.
   * Orchestration steps.
   * Execution metrics.

### Graph Q&A

1. User asks a graph-related question (e.g., “Which institutions collaborated on tasks using sample X?”).
2. Intent classifier routes to graph mode.
3. Orchestrator:

   * Generates Cypher from NL (or uses hints in test mode).
   * Validates Cypher for safety.
   * Executes query on Memgraph.
   * Summarizes results in natural language.
4. Response is returned to the user with optional visibility into the underlying query and data.

### Long-Running Job

1. Admin uses the control panel to trigger a long-running operation (e.g., large ETL import).
2. Backend:

   * Creates a job record in Postgres.
   * Enqueues job ID in Redis.
3. Worker picks up the job, executes it, and streams events/logs.
4. Control panel UI polls job status and events in real time, showing progress and final outcome.

### Provider Onboarding

1. Admin registers a new LLM provider with credentials and configuration.
2. Backend stores provider and model metadata in Postgres.
3. Default model resolution is updated and cached in Redis.
4. Orchestrator and adapters now can route LLM calls through the new provider, respecting resilience policies.

---

## Production Notes & Best Practices

* **Security**

  * Use a hardened reverse proxy with TLS termination.
  * Configure strict CORS and cookie settings.
  * Store secrets securely (e.g., using an external secret manager).
* **Multi-Tenancy**

  * Ensure tenant boundaries are enforced at the repository and service levels.
  * Configure per-tenant models, limits, and roles as needed.
* **Scaling**

  * Scale the backend app and worker processes horizontally.
  * Scale stateful services (Postgres, Redis, Memgraph) according to load patterns.
* **Observability**

  * Integrate metrics and traces with your monitoring stack.
  * Set up alerts for critical metrics (error rates, queue depth, resource usage).
* **Evolution**

  * Use migrations to evolve the schema; avoid manual DB changes.
  * Use deprecation utilities to phase out endpoints and features safely.

---