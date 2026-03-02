## A. High-level understanding (1–7)

---

### **1. Detailed High-Level Overview**

1. **Give me a detailed high-level overview of this project:** what it does, who it’s for, and how all major components fit together, based only on the repository content.

**What it does:**

The **Cineca Agentic Platform** is a production-ready, enterprise-grade AI agent orchestration system built on FastAPI. It enables intelligent LLM-powered agents to:

- Execute **multi-step agentic workflows** with planning, tool invocation, and reflection
- Interact with a **graph database (Memgraph)** via natural language queries (NL→Cypher pipeline)
- Invoke **34 MCP (Model Context Protocol) tools** across 17 categories (graph, cache, data, security, admin, etc.)
- Process **asynchronous background jobs** with SSE event streaming
- Support **multiple LLM providers** (OpenAI, Ollama, Azure, custom) with resilience (circuit breakers, fallback, cost tracking)

**Who it's for:**

| Audience | Use Case |
|----------|----------|
| **End Users** | Interact with AI agents via chat UI for Q&A, graph queries, and task execution |
| **Administrators** | Manage tenants, providers, models, jobs, and monitor system health via control panel |
| **Developers** | Extend the platform with new tools, providers, or graph domains; integrate via REST API |
| **Enterprise/Research Orgs** | Multi-tenant deployment with strict security, audit logging, and observability for bioinformatics or HPC workflows (CINECA context) |

**How components fit together:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                                     │
│   Next.js Chat UI (end users)  ←→  Streamlit Control Panel (admins)    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND (src/app.py)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐   │
│  │  Routers    │  │  Security   │  │  Services   │  │  MCP Tools   │   │
│  │  (23 mods)  │  │  (JWT/RBAC) │  │ Orchestrator│  │  (34 tools)  │   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌──────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐
│   PostgreSQL     │  │       Redis         │  │      Memgraph           │
│  (Control Plane) │  │  (Cache/Queues)     │  │   (Graph Database)      │
│  tenants, jobs,  │  │  rate limits, SSE,  │  │  User, Task, File,      │
│  agents, models  │  │  idempotency        │  │  Institution nodes      │
└──────────────────┘  └─────────────────────┘  └─────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         WORKERS & LLM PROVIDERS                         │
│   JobsWorker (background processing)  ←→  Ollama / OpenAI / Azure      │
└─────────────────────────────────────────────────────────────────────────┘
```

The platform follows a **layered architecture** where HTTP requests flow through routers → security middleware → services → adapters (LLM, DB) → persistence, with cross-cutting observability and governance throughout.

---

### **2. Main Architectural Layers & Responsibilities**

2. **Identify the main architectural layers** (API, services, data, security, UIs, workers, etc.) and describe the responsibility of each layer.

| Layer | Location | Responsibility |
|-------|----------|----------------|
| **API Layer** | routers (23 modules) | FastAPI endpoints for agents, jobs, tools, models, tenants, health; request validation, pagination, response formatting |
| **Security Layer** | security | JWT/OIDC validation (jwt.py), RBAC permissions (perm.py), rate limiting, PII scrubbing, output guards, audit logging |
| **Service Layer** | services | Business logic: orchestrator.py (agent runs), intent_classifier.py (routing), default_model_resolver.py (DMR), `jobs_service.py` |
| **MCP Tools Layer** | tools (17 categories) | Tool implementations for graph, cache, data, security, admin, catalog, viz, privacy, etc. with `@mcp_tool` decorators |
| **Data/Persistence Layer** | db | PostgreSQL (`postgres_control/`): ORM models, repositories, Alembic migrations; Redis (`redis_cache/`): caching, queues; Memgraph (`memgraph_domain/`): graph DB |
| **Adapters Layer** | adapters | LLM adapters (OpenAI-style, Ollama, stub), Memgraph adapter, Redis adapter; resilience with circuit breakers |
| **Workers Layer** | workers | Background job processing (jobs_worker.py): queue consumption, job lifecycle, heartbeats, cancellation |
| **Background/Scheduler** | background | APScheduler-based periodic tasks: health checks, backups, cleanups, provider monitoring |
| **Observability** | observability, metrics | Prometheus metrics, OpenTelemetry tracing, structured logging (structlog), health probes |
| **UI Layer** | ui_agent (Next.js), ui_control_panel (Streamlit) | Agent chat interface for users; admin dashboard for operators |
| **Configuration** | config.py, config_modules | Pydantic settings from env vars; compute config, runtime flags |

---

### **3. Primary Use Cases**

3. **Describe the primary use cases** this platform enables for end users, administrators, and developers.

**For End Users:**
- **Conversational AI**: Chat with agents via the Next.js UI for general Q&A, guided workflows
- **Graph Q&A**: Ask natural language questions about graph data (e.g., "How many BLAST tasks were created this month?") — system translates to Cypher, executes, and summarizes
- **Multi-step task execution**: Agents plan TODOs, invoke tools, and complete complex workflows
- **Real-time updates**: SSE streaming for job progress and agent run status

**For Administrators:**
- **Tenant management**: Create/configure tenants with isolated data and rate limits
- **Provider/model management**: Register LLM providers (Ollama, OpenAI), configure model instances, set defaults
- **Job monitoring**: View, cancel, and analyze background jobs via control panel
- **Audit review**: Access audit logs for compliance and debugging
- **Health monitoring**: Check component health (Postgres, Redis, Memgraph, LLMs)

**For Developers:**
- **API integration**: Use REST API (76 endpoints) to build custom clients or integrations
- **Tool extension**: Add new MCP tools by implementing `@mcp_tool`-decorated handlers
- **Provider extension**: Register custom LLM providers via the provider registry
- **Graph schema extension**: Extend Memgraph domain with new node/relationship types

---

### **4. Core Domain Concepts & Entities**

4. **Summarize all core domain concepts and entities** (agents, runs, sessions, steps, jobs, tools, tenants, providers, models, graph nodes/relations).

| Entity | Location | Description |
|--------|----------|-------------|
| **Tenant** | tenant.py | Multi-tenant isolation unit; has config, rate limits, and owns all child entities |
| **Provider** | provider.py | LLM provider registration (name, base_url, api_key, capabilities) |
| **Model Instance** | model_instance.py | Specific model on a provider (e.g., `phi3:mini` on `ollama-local`); can be enabled/loaded |
| **Agent Session** | agent_session.py | Conversation container; groups multiple runs; has status, manager, preferences |
| **Agent Run** | agent_run.py | Single execution of an agent; tracks status (`queued`→`running`→`succeeded`/`failed`), model used, metrics, output |
| **Agent Step** | agent_step.py | Individual step within a session: `message`, `user`, `assistant`, `tool`, `system`, `error` |
| **Job** | job.py | Background task with lifecycle (`queued`→`running`→`finished`/`failed`/`cancelled`), payload, result |
| **Job Event** | job_event.py | Event log for jobs (status transitions, progress); SSE-streamable |
| **Tool** | tool.py | Registered MCP tool with metadata, schema, permissions |
| **Tool Invocation** | tool_invocation.py | Audit record of a tool call (who, what, when, result) |
| **Manifest** | manifest.py | Model manifest/registry entry (built-in models catalog) |
| **Audit Log** | audit_log.py | Append-only audit events for compliance |
| **Graph Nodes** (Memgraph) | memgraph_domain | `User`, `Institution`, `Task` (BLAST, TaxonomySearch, DatabaseCreation), `File`; relationships: `WORKS_AT`, `CREATED`, `OUTPUT`, `PRODUCED_BY` |

**Schemas (API DTOs)** in schemas:
- `CreateSessionRequest`, `SessionResponse`, `CreateStepRequest`, `StepResponse`
- `CreateRunRequest`, `RunResponse`, `OrchestrationStepInput`, `OrchestrationStepOutput`, `TodoItem`, `ExecutionMetrics`
- `JobCreateRequest`, `JobResponse`, `JobListResponse`
- `ToolInfo`, `ToolInvokeRequest`, `ToolInvokeResponse`

---

### **5. Lifecycle of an Agent Run (HTTP Request → Response)**

5. **Explain the typical lifecycle of an “agent run”** from HTTP request to final response, referencing the actual code paths.

**Code path:** `POST /v1/agent-runs` → agent_runs.py → orchestrator.py

**Step-by-step flow:**

```
1. HTTP REQUEST
   └─ POST /v1/agent-runs { prompt, model?, temperature?, max_steps? }
   └─ Headers: Authorization: Bearer <JWT>, X-Tenant-Id, Idempotency-Key

2. SECURITY MIDDLEWARE (src/security/)
   ├─ jwt.py::validate_jwt() → decode JWT, verify JWKS signature, check iss/aud/exp
   ├─ perm.py::require_perms(["user:me"]) → enforce RBAC
   ├─ rate_limit.py → check Redis counters (tenant + user limits)
   └─ audit.py → log request event

3. ROUTER (agent_runs.py::create_agent_run)
   ├─ IdempotencyHandler → check Redis for duplicate Idempotency-Key
   ├─ Create AgentRun record in PostgreSQL (status=queued)
   ├─ Resolve default model via DefaultModelResolver (Redis cache → PostgreSQL → env fallback)
   └─ Spawn BackgroundTask: execute_agent_run_background()

4. IMMEDIATE RESPONSE
   └─ HTTP 202 Accepted { run_id, status: "queued", ... }
   └─ Client polls GET /v1/agent-runs/{run_id} for updates

5. BACKGROUND EXECUTION (execute_agent_run_background)
   ├─ Update run status → "running"
   ├─ Create OrchestrationContext { goal, user_id, session_id, tenant_id, principal }
   └─ Call Orchestrator.run(context)

6. ORCHESTRATOR (orchestrator.py::Orchestrator.run)
   ├─ INTENT CLASSIFICATION (intent_classifier.py::classify_intent)
   │   └─ Determine mode: CHAT | GRAPH | ADMIN | SECURITY | DANGEROUS
   │   └─ Source: catalog match → patterns → conversational → LLM fallback → default
   │
   ├─ MODE ROUTING
   │   ├─ CHAT mode: direct LLM call → response
   │   ├─ GRAPH mode: NL→Cypher pipeline
   │   │   ├─ Normalize NL prompt
   │   │   ├─ Generate Cypher (LLM or test hints via prompt_catalog)
   │   │   ├─ Safety validation (read-only, tenant boundaries)
   │   │   ├─ Execute on Memgraph via MemgraphAdapter
   │   │   └─ Summarize results to NL
   │   ├─ ADMIN/SECURITY: privileged tool invocations with extra RBAC
   │   └─ DANGEROUS: refuse + explanation
   │
   ├─ MULTI-STEP PLANNING (if needed)
   │   ├─ LLM generates TODO list (up to max_steps)
   │   └─ For each step:
   │       ├─ Record Step { id, action, input, started_at }
   │       ├─ Invoke MCP tool or LLM call
   │       ├─ Resilience: circuit breaker, retry, provider fallback
   │       ├─ Record Step output { finished_at, latency_ms, output }
   │       └─ Check cancellation flag in Redis
   │
   └─ FINALIZATION
       ├─ Aggregate outputs, compute metrics
       ├─ PII scrubbing (pii_scrubber.py)
       ├─ Output guard validation (output_guard.py)
       └─ Return OrchestrationResult

7. PERSIST RESULT (agent_runs.py::execute_agent_run_background)
   ├─ Update AgentRun: status=succeeded/failed, output, steps, todos, metrics
   ├─ Emit Prometheus metrics (agent_metrics)
   └─ Log provenance event

8. CLIENT POLLING
   └─ GET /v1/agent-runs/{run_id} returns final RunResponse with output, steps, metrics
```

**Key files referenced:**
- agent_runs.py
- orchestrator.py (8,263 lines)
- intent_classifier.py
- jwt.py, perm.py

---

### **6. Lifecycle of a Background Job (Creation → Completion)**

6. **Explain the typical lifecycle of a background job** from creation to completion, including how workers and queues are used.

**Code path:** `POST /v1/jobs` → jobs.py → jobs_worker.py

**Step-by-step flow:**

```
1. JOB CREATION (API)
   └─ POST /v1/jobs { type: "demo", payload: { duration_ms: 5000 } }
   
2. ROUTER (jobs.py)
   ├─ Validate request via JobCreateRequest schema
   ├─ Check RBAC permissions
   ├─ JobsService.create_job() → Insert Job in PostgreSQL (status=queued)
   ├─ jobs_cache.queue_push_job(job_type, job_id) → Push to Redis queue
   └─ Return JobResponse { id, status: "queued", ... }

3. WORKER POLLING (jobs_worker.py::JobsWorker.start)
   └─ Infinite loop: poll Redis queues for each allowed job type
       └─ jobs_cache.queue_pop_job(job_type) → Atomic pop

4. JOB EXECUTION (_execute_job)
   ├─ Load Job from PostgreSQL
   ├─ Check Redis cancel flag (jobs_cache.check_cancel_flag)
   ├─ Transition status: queued → running
   ├─ Log JobEvent (status transition)
   │
   ├─ Execute job logic (_run_job_with_heartbeat)
   │   ├─ Start heartbeat task (periodic touch of job.updated_at)
   │   ├─ Dispatch to type-specific handler:
   │   │   ├─ demo: sleep simulation
   │   │   ├─ test: test payload processing
   │   │   ├─ long-running: ETL, backup, maintenance
   │   │   └─ agent.run: orchestrator invocation
   │   └─ Check cancel flag periodically during execution
   │
   └─ On completion:
       ├─ Update result in PostgreSQL
       ├─ Transition status: running → finished/failed
       └─ Log JobEvent

5. SSE STREAMING (optional)
   └─ Client subscribes to GET /v1/jobs/{id}/events (SSE)
   └─ Backend streams JobEvents from PostgreSQL + Redis buffer

6. CANCELLATION (if requested)
   ├─ PUT /v1/jobs/{id}/cancel → Set cancel flag in Redis
   ├─ Worker checks flag → marks job as cancelled
   └─ Transition: running → cancelled
```

**Key mechanisms:**
- **Redis queues**: Per-type queues (`demo`, `test`, `long-running`) with atomic pop
- **PostgreSQL persistence**: Job model with status, payload, result, error, timestamps
- **Heartbeat**: Worker updates `updated_at` every 5s to detect stale workers
- **Cancellation**: Redis flag checked before/during execution
- **Graceful shutdown**: SIGTERM/SIGINT handlers stop worker loop

**Key files:**
- jobs_worker.py
- jobs_service.py
- factory.py (storage backend factory)
- jobs_cache.py

---

### **7. Deployment Assumptions & Target Organizations**

7. **Based on the code and docs, what assumptions does this project make** about its deployment environment and target organizations (e.g., multi-tenant, security requirements, infra expectations)?

Based on the codebase, the platform assumes:

**Multi-Tenancy Requirements:**
- **Full tenant isolation** at database level (tenant_id foreign keys, repository filtering)
- **Per-tenant rate limits** configurable via settings
- **Tenant-scoped defaults** for models, tools, and configurations
- Reference: config.py `ADMIN_DEFAULT_TENANT_ID`

**Security Requirements:**
- **Enterprise OIDC/OAuth**: Integration with external identity providers (Auth0, Keycloak) via JWKS
- **JWT-based authentication** with issuer/audience validation
- **RBAC with scopes**: `user:me`, `tools:basic`, `tools:all`, `admin:all`
- **PII scrubbing enabled by default**: `PII_SCRUBBING_ENABLED=True`
- **Output guard enabled**: `OUTPUT_GUARD_ENABLED=True`
- **Audit logging** for compliance (append-only tables)
- Reference: config.py

**Infrastructure Expectations:**
| Component | Expectation | Config |
|-----------|-------------|--------|
| **PostgreSQL** | Always required; control plane database | `DB_HOST`, `DB_PORT`, `DB_NAME` |
| **Redis** | Required for production (caching, queues, rate limits) | `REDIS_URL` |
| **Memgraph** | Required for graph features | `MG_HOST`, `MG_PORT` |
| **LLM Providers** | At least one (Ollama local or OpenAI cloud) | `LLM_PROVIDER`, `OPENAI_API_KEY` |
| **Reverse Proxy** | Expected (NGINX) for TLS termination | `TRUST_PROXY=True` in prod |
| **Container Orchestration** | Docker Compose provided; Kubernetes-ready health probes | docker-compose.yml |
| **Observability Stack** | Prometheus + Grafana expected | `PROMETHEUS_METRICS_ENABLED=True` |

**Target Organizations:**
- **Research institutions / HPC centers** (CINECA is Italy's national supercomputing center)
- **Bioinformatics workflows**: Graph schema includes BLAST tasks, taxonomy searches, database creation
- **Organizations needing**:
  - Strict security and audit trails
  - Multi-tenant SaaS deployment
  - On-premise LLM hosting (Ollama) + cloud fallback
  - Graph-based knowledge management
  - Compliance with data governance policies

**Environment Modes:**
- **`APP_ENV=dev`**: Full docs, debug logging, relaxed security
- **`APP_ENV=prod`**: Security headers, HSTS, secure cookies, restricted docs

**Configuration evidence:**
```python
# From src/config.py
ENABLE_SECURITY_HEADERS: bool = True
ENABLE_HSTS: bool = True
HSTS_MAX_AGE: int = 31536000  # 1 year
SECURE_COOKIES: bool = False  # Set True in production
TRUST_PROXY: bool = False     # Set True behind reverse proxy
DEMO_MODE: bool = False       # Fallback responses when no providers
HAS_GPU: bool = False         # GPU availability flag
```

---

## B. Architecture & design (8–15)

### **8. System Architecture Diagram (Text-Based)**

8. **Draw a mental architecture diagram** (described in text) of the system: show all major services, databases, and interconnections inferred from the code.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                 EXTERNAL CLIENTS                                         │
│  ┌───────────────────────────┐                    ┌───────────────────────────────────┐ │
│  │    Next.js Chat UI        │                    │     Streamlit Control Panel       │ │
│  │    (ui_agent/)            │                    │     (ui_control_panel/)           │ │
│  │    Port: 3000             │                    │     Port: 8501                    │ │
│  │    • End-user chat        │                    │     • Admin dashboards            │ │
│  │    • Agent run execution  │                    │     • Job monitoring              │ │
│  │    • Real-time updates    │                    │     • Graph/NL→Cypher testing     │ │
│  └───────────┬───────────────┘                    └─────────────────┬─────────────────┘ │
│              │                                                      │                   │
│              └──────────────────────┬───────────────────────────────┘                   │
│                                     ▼                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                    NGINX REVERSE PROXY (ops/nginx/)                                 ││
│  │                    TLS Termination · Routing · CORS · Security Headers              ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────┬───────────────────────────────────────────────────┘
                                      │
                          ┌───────────▼───────────┐
                          │  OIDC Provider        │
                          │  (Auth0/Keycloak)     │
                          │  JWKS · JWT tokens    │
                          └───────────────────────┘
                                      │
┌─────────────────────────────────────▼───────────────────────────────────────────────────┐
│                           FASTAPI BACKEND (src/app.py)                                  │
│                                    Port: 8000                                           │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                           API LAYER (src/routers/)                              │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │   │
│  │  │ health   │ │ auth     │ │ agents   │ │ jobs     │ │ tools    │ │ models   │ │   │
│  │  │ (2 vers) │ │ JWT/OIDC │ │ runs     │ │ SSE      │ │ invoke   │ │ instances│ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │   │
│  │  │ tenants  │ │ admin    │ │ batch    │ │ export   │ │ internal │ │ manifests│ │   │
│  │  │          │ │ ops/db   │ │          │ │ import   │ │ ops/db   │ │          │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                               │
│  ┌─────────────────────────────────────▼───────────────────────────────────────────┐   │
│  │                    MIDDLEWARE & CROSS-CUTTING (src/middleware/, src/security/)  │   │
│  │  JWT/JWKS Validation · RBAC · Rate Limiting · PII Scrubbing · Output Guard      │   │
│  │  CORS · Request ID · Vary Headers · Idempotency · Audit Logging                 │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                        │                                               │
│  ┌───────────────────────────────┬─────┴─────┬───────────────────────────────────┐     │
│  │                               │           │                                   │     │
│  ▼                               ▼           ▼                                   ▼     │
│  ┌───────────────────┐  ┌────────────────┐  ┌────────────────────────────────────┐    │
│  │  SERVICE LAYER    │  │  MCP RUNTIME   │  │      ADAPTERS (src/adapters/)      │    │
│  │  (src/services/)  │  │  (src/mcp/)    │  │                                    │    │
│  │                   │  │                │  │  ┌────────────────────────────┐    │    │
│  │  • Orchestrator   │  │  • ToolRegistry│  │  │  LLM Adapter (llm.py)      │    │    │
│  │    (8,263 lines)  │  │  • ToolPolicy  │  │  │  OpenAI-style, Ollama      │    │    │
│  │  • IntentClassify │  │  • Runtime     │  │  │  Circuit breakers, retry   │    │    │
│  │  • DMR (Default   │  │  • 34 Tools:   │  │  └────────────────────────────┘    │    │
│  │    Model Resolver)│  │    graph.*     │  │  ┌────────────────────────────┐    │    │
│  │  • JobsService    │  │    cache.*     │  │  │  Memgraph Adapter          │    │    │
│  │  • SessionService │  │    data.*      │  │  │  (db_memgraph.py)          │    │    │
│  │  • HealthService  │  │    security.*  │  │  │  Cypher queries, health    │    │    │
│  │  • ETL/Archive    │  │    admin.*     │  │  └────────────────────────────┘    │    │
│  │  • ModelWarmup    │  │    catalog.*   │  │  ┌────────────────────────────┐    │    │
│  │  • PromptCatalog  │  │    tenancy.*   │  │  │  MCP Client                │    │    │
│  │  • InvocationStore│  │    session.*   │  │  │  (mcp_client.py)           │    │    │
│  └───────────────────┘  └────────────────┘  │  └────────────────────────────┘    │    │
│           │                     │           └────────────────────────────────────┘    │
│           │                     │                          │                          │
│  ┌────────▼─────────────────────▼──────────────────────────▼───────────────────────┐  │
│  │                    REPOSITORIES (db/postgres_control/repositories/)              │  │
│  │  TenantsRepository · JobsRepository · AgentSessionRepo · AgentRunRepo            │  │
│  │  AgentStepRepo · ProviderRepo · ModelInstanceRepo · ToolsRepo · ManifestRepo     │  │
│  │  IdempotencyRepo · UserDefaultModelsRepo                                         │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                        │                                               │
│  ┌─────────────────────────────────────▼───────────────────────────────────────────┐   │
│  │                         OBSERVABILITY (src/observability/, src/metrics/)        │   │
│  │  Prometheus /metrics · OpenTelemetry Tracing · Structlog JSON Logging           │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                         BACKGROUND (src/background/)                             │   │
│  │  APScheduler: Health checks · Backups · Cleanups · Provider monitoring           │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
└─────────────────────────────────────┬───────────────────────────────────────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
        ▼                             ▼                             ▼
┌───────────────────────┐  ┌──────────────────────┐  ┌──────────────────────────────────┐
│   PostgreSQL          │  │       Redis          │  │          Memgraph                │
│   (Control Plane)     │  │   (Cache/Queues)     │  │      (Graph Database)            │
│   Port: 5432          │  │   Port: 6379         │  │      Port: 7687 (Bolt)           │
│                       │  │                      │  │                                  │
│  TABLES:              │  │  DATA STRUCTURES:    │  │  GRAPH SCHEMA:                   │
│  • tenants            │  │  • STRING: caching   │  │  Nodes:                          │
│  • providers          │  │  • HASH: job docs    │  │  • User (id, name, email, role)  │
│  • model_instances    │  │  • ZSET: indexes     │  │  • Institution (id, name, type)  │
│  • agent_sessions     │  │  • LIST: job queues  │  │  • BlastTask (id, params, status)│
│  • agent_runs         │  │  • COUNTER: rate lim │  │  • TaxonomySearch (id, query)    │
│  • agent_steps        │  │                      │  │  • DatabaseCreation (id, name)   │
│  • jobs               │  │  NAMESPACES:         │  │  • File (id, path, size, type)   │
│  • job_events         │  │  • cache:*           │  │                                  │
│  • tools              │  │  • job:*             │  │  Relationships:                  │
│  • tool_invocations   │  │  • rate:*            │  │  • WORKS_AT (User→Institution)   │
│  • manifests          │  │  • session:*         │  │  • CREATED (User→Task)           │
│  • audit_logs         │  │  • idem:*            │  │  • OUTPUT (Task→File)            │
│  • idempotency_keys   │  │  • queue:*           │  │  • PRODUCED_BY (File→Task)       │
│  • user_default_models│  │  • cancel:*          │  │  • INPUT_FILE (Task→File)        │
│                       │  │                      │  │                                  │
│  26+ Alembic          │  │  TTL-based auto      │  │  NL→Cypher pipeline              │
│  migrations           │  │  expiry              │  │  via Orchestrator                │
└───────────────────────┘  └──────────────────────┘  └──────────────────────────────────┘
        │                             │                             │
        └─────────────────────────────┼─────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              WORKER PROCESS (src/workers/)                              │
│                              jobs_worker.py                                             │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│  1. Poll Redis queues (job types: demo, test, long-running, agent.run)                 │
│  2. Pop job ID atomically (BRPOP/LPOP)                                                 │
│  3. Load job metadata from PostgreSQL                                                  │
│  4. Transition: queued → running                                                       │
│  5. Execute handler (ETL, backups, agent runs, maintenance)                            │
│  6. Heartbeat loop (touch updated_at every 5s)                                         │
│  7. Check cancellation flags in Redis                                                  │
│  8. Transition: running → finished/failed/cancelled                                    │
│  9. Emit JobEvents for SSE streaming                                                   │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              LLM PROVIDERS (External)                                   │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────────────────────┐   │
│  │   Ollama (Local)  │  │   OpenAI (Cloud)  │  │   Azure OpenAI / Other Providers  │   │
│  │   Port: 11434     │  │   api.openai.com  │  │   Compatible OpenAI-style APIs    │   │
│  │   phi3:mini, etc. │  │   gpt-4o, etc.    │  │                                   │   │
│  └───────────────────┘  └───────────────────┘  └───────────────────────────────────┘   │
│                                                                                         │
│                 ▲ Called via LLM Adapter with resilience framework ▲                   │
│                   (circuit breakers, cost tracking, provider fallback)                  │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           MONITORING & OBSERVABILITY                                    │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────────────────────┐   │
│  │   Prometheus      │  │     Grafana       │  │    OTEL Collector (Optional)      │   │
│  │   Scrapes /metrics│  │   Dashboards for  │  │    Receives OTLP traces           │   │
│  │   from app:8000   │  │   HTTP, agents,   │  │    → Jaeger / Tempo / APM         │   │
│  │                   │  │   jobs, tools     │  │                                   │   │
│  └───────────────────┘  └───────────────────┘  └───────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

**Key Interconnections:**
1. **UIs → Backend**: REST API calls with JWT authentication
2. **Backend → PostgreSQL**: SQLAlchemy ORM via repositories (control plane)
3. **Backend → Redis**: Caching, queues, rate limits, idempotency via `db.redis_cache`
4. **Backend → Memgraph**: Cypher queries via gqlalchemy adapter (graph domain)
5. **Backend → LLM Providers**: HTTP/REST via `src.adapters.llm` with resilience
6. **Workers → All DBs**: Same adapters as backend for job execution
7. **Prometheus → Backend**: Scrapes `/metrics` endpoint

---

### **9. API Layer Structure**

9. **Explain how the API layer is structured** (routers, dependencies, schemas) and how it interacts with the service layer and repositories.

**Structure Overview:**

The API layer is organized in `src/routers/` with 23 router modules, each handling a specific domain:

| Router Module | Endpoints | Primary Purpose |
|--------------|-----------|-----------------|
| `health.py`, `health_v2.py` | `/v1/health/*`, `/v2/health/*` | Kubernetes probes (liveness, readiness, startup, components) |
| `auth.py` | `/v1/auth/*` | JWT validation, user info, token introspection |
| `agent.py` | `/v1/agents/*` | Session management, step creation |
| `agent_runs.py` | `/v1/agent-runs/*` | Agent run execution (orchestrator invocation) |
| `tools.py` | `/v1/tools/*` | Tool discovery, invocation |
| `jobs.py` | `/v1/jobs/*` | Background job CRUD, SSE streaming |
| `models.py`, `model_instances.py` | `/v1/models/*` | LLM model management |
| `model_management.py`, `model_processes.py` | `/v1/models/*` | Model loading, unloading |
| `manifests.py` | `/v1/manifests/*` | Built-in model catalog |
| `tenants.py`, `tenants_admin.py` | `/v1/tenants/*` | Multi-tenant management |
| `admin.py`, `admin_db.py`, `admin_jobs.py`, `admin_ops.py` | `/v1/admin/*` | Admin operations |
| `batch.py` | `/v1/batch/*` | Batch operations |
| `export_import.py` | `/v1/export/*`, `/v1/import/*` | Data export/import |
| `internal_db.py`, `internal_ops.py` | `/v1/internal/*` | Internal debugging endpoints |

**Dependency Injection Pattern:**

```python
# Typical router endpoint structure (from agent_runs.py)
@router.post("/agent-runs")
async def create_agent_run(
    request: Request,
    body: CreateRunRequest,                              # Schema validation (Pydantic)
    background_tasks: BackgroundTasks,                   # FastAPI background tasks
    db: DBSession = Depends(get_db),                     # PostgreSQL session
    user: UserInfo = Depends(get_current_user),          # JWT-validated user
    _: Any = Depends(require_perms(["user:me"])),        # RBAC enforcement
):
    # 1. Rate limiting
    handler = RateLimitHandler(user_id=user.sub, tenant_id=user.tenant_id)
    await handler.check("runs:create")
    
    # 2. Idempotency check
    idempotency_handler = IdempotencyHandler(request, db)
    cached = await idempotency_handler.check()
    if cached:
        return cached
    
    # 3. Repository operations
    run = AgentRunRepository.create(db, user_id=user.sub, ...)
    
    # 4. Background task (service layer)
    background_tasks.add_task(execute_agent_run_background, run_id=run.run_id, ...)
    
    # 5. Return schema-validated response
    return RunResponse(...)
```

**Schema Layer (`src/schemas/`):**

All Pydantic request/response models are centralized:
- `agents.py`: `CreateSessionRequest`, `SessionResponse`, `CreateRunRequest`, `RunResponse`, `TodoItem`, `ExecutionMetrics`
- `jobs.py`: `JobCreateRequest`, `JobResponse`, `JobListResponse`
- `tools.py`: `ToolInfo`, `ToolInvokeRequest`, `ToolInvokeResponse`
- `models.py`: `ModelInstanceResponse`, `ModelLoadRequest`
- `tenants.py`: `TenantCreateRequest`, `TenantResponse`
- `auth.py`: `UserInfo`, `TokenIntrospection`

**Interaction Flow:**

```
HTTP Request
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  ROUTER (src/routers/*.py)                                  │
│  • Validates request via Pydantic schemas                   │
│  • Resolves dependencies (get_db, get_current_user, etc.)   │
│  • Applies middleware (rate limit, idempotency)             │
└─────────────────────────────────────────────────────────────┘
    │
    ├─► REPOSITORY (db/postgres_control/repositories/*.py)
    │   • Direct DB operations (CRUD, pagination)
    │   • Returns ORM models
    │
    └─► SERVICE (src/services/*.py)
        • Business logic (orchestrator, intent classification)
        • Calls adapters (LLM, Memgraph, Redis)
        • Returns domain results
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  RESPONSE                                                   │
│  • Converted to Pydantic schema                             │
│  • JSON serialized with proper HTTP status                  │
└─────────────────────────────────────────────────────────────┘
```

---

### **10. Repository Pattern for PostgreSQL**

10. **Describe the repository pattern used for PostgreSQL access:** which repositories exist, how they are organized, and how they enforce multi-tenancy.

**Repository Location:** `db/postgres_control/repositories/`

**Available Repositories:**

| Repository | File | Models Managed | Key Methods |
|-----------|------|----------------|-------------|
| `TenantsRepository` | `tenants.py` | `Tenant` | `create()`, `get()`, `list()`, `update()`, `delete()` |
| `JobsRepository` | `jobs.py` | `Job`, `JobEvent` | `create_job()`, `get_job()`, `list_jobs()`, `transition_status()`, `append_event()` |
| `AgentSessionRepository` | `agents.py` | `AgentSession` | `create()`, `get_by_id()`, `list_by_user()`, `update_status()` |
| `AgentRunRepository` | `agents.py` | `AgentRun` | `create()`, `get_by_id()`, `update_status()`, `list_recent()` |
| `AgentStepRepository` | `agents.py` | `AgentStep` | `create()`, `get_by_session_and_seq()`, `list_by_session()` |
| `IdempotencyRepository` | `agents.py` | `IdempotencyKey` | `get_or_create()`, `mark_replayed()` |
| `ProviderRepository` | `provider_repo.py` | `Provider`, `ProviderSecret` | `create()`, `get()`, `list()`, `update()`, `delete()` |
| `ModelInstanceRepository` | `model_instance_repo.py` | `ModelInstance` | `create()`, `get()`, `list()`, `set_default()` |
| `ToolsRepository` | `tools.py` | `Tool`, `ToolInvocation`, `ToolAuditEvent` | `create()`, `get()`, `list()`, `log_invocation()` |
| `ManifestRepository` | `manifest_repo.py` | `Manifest` | `create()`, `get()`, `list()` |
| `UserDefaultModelsRepository` | `user_default_models.py` | `UserDefaultModel` | `get_default()`, `set_default()` |

**Core Patterns Implemented:**

1. **Session Management:**
```python
class TenantsRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, name: str, config: dict) -> Tenant:
        tenant = Tenant(id=self.generate_tenant_id(), name=name, config=config)
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant
```

2. **Cursor-Based Pagination:**
```python
def list(self, page_size: int = 100, page_token: str | None = None) -> tuple[list[Tenant], str | None, int]:
    # Decode cursor (format: "created_at|id")
    # Apply WHERE clause for keyset pagination
    query = self.db.query(Tenant).order_by(Tenant.created_at.desc(), Tenant.id.asc())
    if page_token:
        created_at, cursor_id = decode_cursor(page_token)
        query = query.filter(or_(
            Tenant.created_at < created_at,
            and_(Tenant.created_at == created_at, Tenant.id > cursor_id)
        ))
    items = query.limit(page_size + 1).all()
    # Return (items, next_token, total)
```

3. **ETag Computation:**
```python
@staticmethod
def compute_etag(tenant: Tenant) -> str:
    data = f"{tenant.id}:{tenant.updated_at.isoformat()}:{tenant.version}"
    return f'"{hashlib.sha256(data.encode()).hexdigest()[:16]}"'
```

4. **Redis Caching Integration:**
```python
def get_cached(self, tenant_id: str) -> Tenant | None:
    cache_key = f"tenant:{tenant_id}"
    cached = cache_get_json(cache_key)
    if cached:
        return Tenant(**cached)
    tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant:
        cache_set_json(cache_key, tenant.to_dict(), ttl=3600)
    return tenant
```

**Multi-Tenancy Enforcement:**

1. **Foreign Key Constraints:** All tenant-scoped models have `tenant_id` FK:
```python
# From agent_run.py
tenant_id = Column(String(255), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
```

2. **Repository-Level Filtering:**
```python
# AgentRunRepository
def list_by_tenant(self, tenant_id: str, page_size: int = 100) -> list[AgentRun]:
    return self.db.query(AgentRun).filter(
        AgentRun.tenant_id == tenant_id
    ).order_by(AgentRun.started_at.desc()).limit(page_size).all()
```

3. **Ownership Validation:**
```python
def get_by_id_and_owner(self, run_id: UUID, user_id: str, tenant_id: str) -> AgentRun | None:
    return self.db.query(AgentRun).filter(
        AgentRun.run_id == run_id,
        AgentRun.user_id == user_id,
        AgentRun.tenant_id == tenant_id
    ).first()
```

4. **Cascade Deletes:**
```python
# Deleting a tenant cascades to all child resources
session.query(Tenant).filter(Tenant.id == tenant_id).delete()
# All agent_sessions, agent_runs, jobs, etc. are deleted via ON DELETE CASCADE
```

---

### **11. Redis Usage Across the System**

11. **Explain how Redis is used across the system** (caching, queues, rate limiting, session state, idempotency, etc.) and point to the relevant modules.

**Redis Module Location:** `db/redis_cache/`

**Usage Categories:**

| Category | Module | Key Pattern | TTL | Purpose |
|----------|--------|-------------|-----|---------|
| **Caching** | `client.py` | `cache:*` | Configurable | Entity caching, config caching |
| **Job Queues** | `jobs_cache.py` | `queue:{job_type}` | None | FIFO job dispatch |
| **Job Storage** | `job_store.py` | `job:{id}` | `JOB_TTL_DAYS` | Job documents (HASH) |
| **Rate Limiting** | `rate_limit.py` | `rate:user:{id}:{action}`, `rate:tenant:{id}:{action}` | Window size | Sliding window counters (ZSET) |
| **Session State** | `agents.py` | `session:{id}`, `step_seq:{session_id}` | Session TTL | Session cache, step sequencing |
| **Idempotency** | `client.py` | `idem:{key}` | 24h default | Request deduplication |
| **Cancel Flags** | `jobs_cache.py` | `cancel:{job_id}` | Job TTL | Job cancellation signals |
| **SSE Events** | `job_store.py` | `events:{job_id}` | Job TTL | Ring buffer for SSE streaming |
| **Tool Results** | `tools_cache.py` | `tool:{name}:{hash}` | Tool-specific | Tool invocation caching |
| **ETag Cache** | `agents.py` | `etag:session:{id}` | Short | HTTP conditional requests |
| **Distributed Locks** | `agents.py` | `lock:{resource}` | Lock TTL | Step allocation, session locks |

**Key Implementation Details:**

1. **Synchronous Client (`client.py`):**
```python
def get_redis() -> redis.Redis:
    """Return process-wide Redis client."""
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client

def cache_set_json(key: str, value: Any, ex: int | None = None) -> bool:
    """Set JSON value with optional TTL."""
    return cache_set(key, _json_dumps(value), ex=ex)
```

2. **Async Client (`async_client.py`):**
```python
async def get_async_redis() -> redis.asyncio.Redis:
    """Return async Redis client for rate limiting, SSE, etc."""
    global _async_client
    if _async_client is None:
        _async_client = await redis.asyncio.Redis.from_url(settings.REDIS_URL)
    return _async_client
```

3. **Rate Limiting (`rate_limit.py`):**
```python
async def check_rate_limit(key: str, limit: int, window: int) -> tuple[bool, int, int]:
    """Sliding window algorithm using ZSET."""
    now = time.time()
    window_start = now - window
    
    r = await get_async_redis()
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)  # Remove expired
    pipe.zadd(key, {str(now): now})              # Add current
    pipe.zcard(key)                               # Count in window
    pipe.expire(key, window)                      # Set TTL
    results = await pipe.execute()
    
    current_count = results[2]
    if current_count > limit:
        return False, 0, int(window_start + window - now) + 1
    return True, limit - current_count, 0
```

4. **Job Queues (`jobs_cache.py`):**
```python
def queue_push_job(job_type: str, job_id: str) -> None:
    """Push job to type-specific queue."""
    r = get_redis()
    r.lpush(f"queue:{job_type}", job_id)

def queue_pop_job(job_type: str, timeout: int = 0) -> str | None:
    """Atomically pop job from queue."""
    r = get_redis()
    result = r.brpop(f"queue:{job_type}", timeout=timeout)
    return result[1] if result else None
```

5. **Idempotency (`client.py`):**
```python
def idem_get(key: str) -> tuple[str, float | None] | None:
    """Get idempotency entry (response, expiry)."""
    r = get_redis()
    data = r.hgetall(f"idem:{key}")
    if data:
        return data.get("response"), float(data.get("ttl", 0))
    return None

def idem_set(key: str, response: str, ttl: int = 86400) -> bool:
    """Set idempotency entry with TTL."""
    r = get_redis()
    r.hset(f"idem:{key}", mapping={"response": response, "ttl": str(time.time() + ttl)})
    r.expire(f"idem:{key}", ttl)
    return True
```

6. **Graceful Degradation:**
```python
# Local fallback when Redis unavailable
_LOCAL_RATE_DATA: dict[str, list[float]] = defaultdict(list)

async def _check_rate_limit_local(key: str, limit: int, window: int) -> tuple[bool, int, int]:
    """In-memory fallback for rate limiting."""
    # ... uses _LOCAL_RATE_DATA instead of Redis
```

---

### **12. Memgraph Role in Architecture**

12. **Explain the role of Memgraph in the architecture**: which modules interact with it, and for what types of operations.

**Memgraph Purpose:**

Memgraph serves as the **graph domain database** for bioinformatics workflows, storing relationships between users, institutions, computational tasks (BLAST, taxonomy searches, database creation), and file artifacts.

**Modules Interacting with Memgraph:**

| Module | Location | Purpose |
|--------|----------|---------|
| **Memgraph Adapter** | `src/adapters/db_memgraph.py` | Connection factory, health checks, query execution |
| **Graph MCP Tools** | `src/mcp/tools/graph/` | Tool implementations for graph operations |
| **Orchestrator** | `src/services/orchestrator.py` | NL→Cypher pipeline for GRAPH mode |
| **Prompt Catalog** | `src/services/prompt_catalog.py` | Pre-matched prompts for test mode |
| **Intent Classifier** | `src/services/intent_classifier.py` | Detects GRAPH intent |
| **Memgraph Domain** | `db/memgraph_domain/` | Schema, population scripts, config |

**Operations Supported:**

1. **Schema Introspection (`graph.schema`):**
```python
# Get labels, relationship types, property keys
CALL db.labels() YIELD label RETURN label;
CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType;
```

2. **Ad-hoc Queries (`graph.query`):**
```python
# From src/mcp/tools/graph/query.py
@mcp_tool(name="graph.query", scope="tools:read")
async def graph_query(ctx: ToolContext, payload: GraphQueryPayload) -> dict:
    cypher = payload.cypher
    if payload.read_only and _looks_write(cypher):
        raise ValueError("Query contains write operations but read_only=True")
    
    db = get_client()
    rows = list(db.execute_and_fetch(cypher, payload.params))
    return {"ok": True, "rows": rows, "rowcount": len(rows)}
```

3. **CRUD Operations (`graph.crud`):**
```python
# Create, read, update, delete nodes and relationships
MATCH (u:User {id: $user_id}) SET u.name = $name RETURN u;
```

4. **Search (`graph.search`):**
```python
# Full-text or pattern-based search
MATCH (n) WHERE n.name CONTAINS $query RETURN n LIMIT 100;
```

5. **Analytics (`graph.analytics`):**
```python
# Aggregations, path finding, centrality
MATCH (u:User)-[:CREATED]->(t:BlastTask) RETURN u.name, count(t) AS task_count;
```

6. **Bulk Operations (`graph.bulk`):**
```python
# Batch imports/exports for ETL
UNWIND $nodes AS node CREATE (n:User) SET n = node;
```

7. **Secure Query (`graph.secure_query`):**
```python
# With tenant boundary enforcement
MATCH (u:User {tenant_id: $tenant_id})-[r]->(t) RETURN u, r, t;
```

**NL→Cypher Pipeline (GRAPH Mode):**

```
User Prompt: "How many BLAST tasks were created this month?"
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  INTENT CLASSIFICATION                                      │
│  classify_intent() → mode=GRAPH, confidence=0.95            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  CYPHER GENERATION (Orchestrator)                           │
│  1. Check prompt_catalog for test hints                     │
│  2. If no match, call LLM to generate Cypher                │
│  3. Output: MATCH (t:BlastTask) WHERE t.created_at >=       │
│             datetime('2025-12-01') RETURN count(t)          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  SAFETY VALIDATION (graph/secure_query.py)                  │
│  • Check for write patterns (CREATE, DELETE, etc.)          │
│  • Verify tenant boundaries                                 │
│  • Validate against allowlist                               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  EXECUTION (MemgraphAdapter)                                │
│  db.execute_and_fetch(cypher, params)                       │
│  Result: [{"count(t)": 42}]                                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  SUMMARIZATION (LLM or fallback)                            │
│  "42 BLAST tasks were created this month."                  │
└─────────────────────────────────────────────────────────────┘
```

---

### **13. Configuration System**

13. **Describe the configuration system:** how settings are loaded (env, config modules) and how compute/runtime configuration is derived.

**Configuration Architecture:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CONFIGURATION SOURCES                           │
├─────────────────────────────────────────────────────────────────────────┤
│  1. .env file (loaded by python-dotenv)                                 │
│  2. Environment variables (override .env)                               │
│  3. Default values in Pydantic models                                   │
│  4. Computed properties (runtime derivation)                            │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    MAIN SETTINGS (src/config.py)                        │
│                    class Settings(BaseSettings)                         │
├─────────────────────────────────────────────────────────────────────────┤
│  # App                                                                  │
│  APP_ENV: str = "dev"          # dev, stage, prod                       │
│  APP_HOST: str = "0.0.0.0"                                              │
│  APP_PORT: int = 8000                                                   │
│  LOG_LEVEL: str = "INFO"                                                │
│                                                                         │
│  # PostgreSQL                                                           │
│  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_SSLMODE           │
│  DB_POOL_SIZE=10, DB_POOL_TIMEOUT=30, DB_POOL_RECYCLE=3600             │
│                                                                         │
│  # Redis                                                                │
│  REDIS_URL: str = "redis://redis:6379/0"                               │
│                                                                         │
│  # Memgraph                                                             │
│  MG_HOST, MG_PORT, MG_USER, MG_PASSWORD, MG_TLS                        │
│                                                                         │
│  # Security                                                             │
│  JWT_SECRET, JWT_ALGORITHM, OIDC_ISSUER, OIDC_AUDIENCE, OIDC_JWKS_URL  │
│  PII_SCRUBBING_ENABLED=True, OUTPUT_GUARD_ENABLED=True                 │
│  RATE_LIMIT_ENABLED=True, RATE_LIMIT_DEFAULT_LIMIT=60                  │
│                                                                         │
│  # LLM                                                                  │
│  LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY, OLLAMA_BASE_URL              │
│  DEFAULT_MODEL_NAME="phi3:mini", LLM_MAX_TOKENS=2048, LLM_MAX_STEPS=10 │
│                                                                         │
│  # Memgraph Response                                                    │
│  MEMGRAPH_RESPONSE_MODE: str = "llm-best-effort"                       │
│  MEMGRAPH_BUILDER_LLM_TIMEOUT_MS: int = 180000                         │
│                                                                         │
│  # Observability                                                        │
│  PROMETHEUS_METRICS_ENABLED=True, OTEL_SERVICE_NAME, OTEL_*            │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│             COMPUTE CONFIG (src/config_modules/compute.py)              │
│             class ComputeConfig(BaseSettings)                           │
├─────────────────────────────────────────────────────────────────────────┤
│  device: DeviceType = "cpu"      # cpu, cuda, mps, auto                 │
│  max_concurrent_llm_calls: int   # 1 for CPU, 4 for GPU                 │
│  step_timeout_seconds: int       # 1200 for CPU, 30 for GPU             │
│  run_timeout_seconds: int        # 1800 for CPU, 120 for GPU            │
│  test_mode: bool = False         # Reduced timeouts for testing         │
│  memgraph_nl_test_mode: bool     # Special mode for NL tests            │
│                                                                         │
│  @property                                                              │
│  def recommended_step_timeout(self) -> int:                             │
│      if self.memgraph_nl_test_mode: return reduced_timeout              │
│      if self.device == "cpu": return 1200                               │
│      if self.device == "cuda": return 30                                │
│      if self.device == "mps": return 60                                 │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  USAGE IN CODE                                          │
├─────────────────────────────────────────────────────────────────────────┤
│  from src.config import settings                                        │
│  from src.config_modules.compute import get_compute_config              │
│                                                                         │
│  # Direct access                                                        │
│  db_url = f"postgresql://{settings.DB_USER}:..."                       │
│                                                                         │
│  # Computed config                                                      │
│  compute = get_compute_config()                                         │
│  timeout = compute.recommended_step_timeout                             │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key Configuration Patterns:**

1. **Pydantic Settings with Validation:**
```python
class Settings(BaseSettings):
    MEMGRAPH_RESPONSE_MODE: str = Field(default="llm-best-effort")
    
    @field_validator("MEMGRAPH_RESPONSE_MODE", mode="before")
    @classmethod
    def validate_memgraph_response_mode(cls, v: Any) -> str:
        valid_modes = {"fallback-only", "llm-best-effort", "llm-required"}
        if v not in valid_modes:
            return "llm-best-effort"  # Default on invalid
        return v
```

2. **Device-Aware Defaults:**
```python
# From compute.py
@property
def recommended_step_timeout(self) -> int:
    if self.device == "cpu":
        return 1200   # 20 minutes for slow CPU inference
    elif self.device == "cuda":
        return 30     # 30 seconds for fast GPU
    elif self.device == "mps":
        return 60     # 1 minute for Apple Silicon
```

3. **Environment-Specific Behavior:**
```python
# From logging_setup.py
def _wants_json() -> bool:
    env = os.getenv("APP_ENV", "dev").strip().lower()
    return env in {"prod", "production"}  # JSON logs in production
```

---

### **14. Cross-Cutting Concerns**

14. **Identify and explain all cross-cutting concerns** (logging, metrics, tracing, auth, rate limiting, PII scrubbing, error handling) and where they are implemented.

| Concern | Location | Implementation |
|---------|----------|----------------|
| **Logging** | `src/logging_setup.py` | Structlog with JSON (prod) or console (dev) output; request ID correlation |
| **Metrics** | `src/observability/metrics.py`, `src/metrics/` | Prometheus counters/histograms for HTTP, jobs, tools, LLM calls, rate limits |
| **Tracing** | `src/observability/` | OpenTelemetry with OTLP exporter; trace/span IDs in logs |
| **Authentication** | `src/security/jwt.py` | OIDC/JWT validation via JWKS; `validate_jwt()`, `get_current_principal()` |
| **Authorization** | `src/security/perm.py` | RBAC with scopes; `require_perms()`, `has_perms()`, `enforce_perms()` |
| **Rate Limiting** | `db/redis_cache/rate_limit.py`, `src/middleware/rate_limit.py` | Sliding window via Redis ZSET; per-user + per-tenant quotas |
| **PII Scrubbing** | `src/security/pii_scrubber.py` | Regex detection of SSN, email, phone, CC; modes: mask, hash, remove, off |
| **Output Guard** | `src/security/output_guard.py` | Response sanitization; detects sensitive patterns |
| **Intent Filter** | `src/security/intent_filter.py` | Blocks dangerous operations (schema drops, bulk deletes) |
| **Audit Logging** | `src/security/audit.py` | Append-only audit events to PostgreSQL |
| **Error Handling** | `src/errors/`, `src/app.py` | RFC 7807 Problem Details; `HTTPException` handlers |
| **Idempotency** | `src/middleware/idempotency.py`, `db/redis_cache/client.py` | Request deduplication via `Idempotency-Key` header |
| **Request Context** | `src/app.py`, `src/middleware/` | Context vars for request_id, trace_id, tenant_id |
| **CORS** | `src/app.py` | FastAPI CORS middleware with configurable origins |
| **Security Headers** | `src/middleware/` | HSTS, CSP, X-Content-Type-Options, X-Frame-Options |

**Implementation Details:**

1. **Structured Logging:**
```python
# src/logging_setup.py
def setup_logging(level: str = "INFO") -> None:
    pre_chain = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    if use_json:
        renderer = structlog.processors.JSONRenderer(sort_keys=True)
    else:
        renderer = structlog.dev.ConsoleRenderer()
```

2. **Prometheus Metrics:**
```python
# src/observability/metrics.py
class _MetricStore:
    def __init__(self, registry: CollectorRegistry):
        self.http_requests_total = Counter(
            "http_requests_total", "Total HTTP requests",
            ["method", "path", "status"], registry=registry
        )
        self.http_request_duration_seconds = Histogram(
            "http_request_duration_seconds", "HTTP request duration",
            ["method", "path", "status"], registry=registry
        )
```

3. **PII Scrubbing:**
```python
# src/security/pii_scrubber.py
def scrub_text(text: str, mode: str | None = None) -> str:
    """Detect and redact PII patterns."""
    mode = _mode(mode)
    if mode == "off":
        return text
    
    for pattern, category in _PII_PATTERNS:
        for match in pattern.finditer(text):
            if mode == "mask":
                text = text[:match.start()] + _mask(match.group(), category) + text[match.end():]
            elif mode == "hash":
                text = text[:match.start()] + f"sha256:{_hash(match.group())[:16]}" + text[match.end():]
    return text
```

4. **Rate Limit Middleware:**
```python
# src/middleware/rate_limit.py
class RateLimitHandler:
    async def check(self, action: str) -> None:
        limit, window = get_rate_limit_config(action)
        key = make_rate_limit_key(action, self.user_id, self.resource_id)
        
        allowed, remaining, retry_after = await check_rate_limit(key, limit, window)
        
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={"code": "E_RATE_LIMIT", "retry_after": retry_after},
                headers={"Retry-After": str(retry_after)}
            )
```

5. **Error Handling (RFC 7807):**
```python
# src/app.py
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "type": "about:blank",
            "title": "Validation Error",
            "status": 422,
            "detail": str(exc),
            "instance": str(request.url.path),
            "errors": exc.errors()
        }
    )
```

---

### **15. Architectural Strengths & Weaknesses**

15. **Highlight the main architectural strengths and weaknesses** of the design as implemented (e.g., modularity, coupling, clarity, extensibility).

**Strengths:**

| Strength | Evidence | Benefit |
|----------|----------|---------|
| **Strong Modularity** | Separate directories for routers, services, adapters, repositories, MCP tools | Easy to navigate; clear separation of concerns |
| **Comprehensive Repository Pattern** | All DB access via `db/postgres_control/repositories/` | Testable, cacheable, consistent data access |
| **Graceful Degradation** | Redis fallbacks in `rate_limit.py`, optional imports throughout | System remains functional when dependencies fail |
| **Configuration Flexibility** | Pydantic settings with env overrides, device-aware compute config | Easy deployment customization per environment |
| **Security-First Design** | JWT/OIDC, RBAC, PII scrubbing, output guards, audit logging | Enterprise-ready security posture |
| **Multi-Tenancy Built-In** | Tenant FK on all models, repository-level filtering | True data isolation from the ground up |
| **Extensive Observability** | Prometheus metrics, structured logging, OpenTelemetry, health probes | Production-ready monitoring |
| **Tool Extensibility** | `@mcp_tool` decorator pattern, dynamic discovery | Easy to add new tools |
| **LLM Resilience** | Circuit breakers, cost tracking, provider fallback | Handles provider failures gracefully |
| **Comprehensive Documentation** | README files in every major directory | Self-documenting codebase |

**Weaknesses:**

| Weakness | Evidence | Impact |
|----------|----------|--------|
| **Orchestrator Complexity** | `orchestrator.py` is 8,263 lines | Hard to understand, test, and maintain; high cognitive load |
| **Tight LLM Coupling** | Orchestrator directly handles NL→Cypher, response building | Difficult to swap or mock LLM behavior |
| **Optional Import Pattern** | `try/except` imports scattered throughout | Runtime errors possible; harder to trace dependencies |
| **Mixed Sync/Async** | Some adapters sync, some async; thread offloading in orchestrator | Potential for subtle concurrency bugs |
| **Test Mode Complexity** | `MEMGRAPH_NL_TEST_MODE`, prompt catalog hints | Testing requires special configuration knowledge |
| **Schema Duplication** | Pydantic schemas (API) vs SQLAlchemy models (DB) | Manual sync required; potential drift |
| **Hardcoded Patterns** | Write detection regex in `graph/query.py`, PII patterns | Limited customization without code changes |
| **Limited Async Worker** | `jobs_worker.py` uses sync PostgreSQL | Potential bottleneck under high job load |
| **No Event Sourcing** | State stored as snapshots, not events | Limited audit trail for state changes |
| **Monolithic Deployment** | Single FastAPI app + single worker type | Scaling requires running full app instances |

**Recommendations for Improvement:**

1. **Refactor Orchestrator**: Extract NL→Cypher, response building, step execution into separate service classes
2. **Async-First**: Convert all adapters to async to avoid thread pool exhaustion
3. **Dependency Injection**: Use FastAPI's DI more consistently instead of optional imports
4. **Schema Generation**: Auto-generate Pydantic schemas from SQLAlchemy models (e.g., `sqlmodel`)
5. **Feature Flags**: Replace test mode booleans with proper feature flag system
6. **Event-Driven Architecture**: Add event bus for loose coupling between services

---

## C. Security, multi-tenancy & governance (16–22)

---

### **16. Full Authentication Flow (OIDC/JWT/JWKS)**

16. **Explain the full authentication flow** (OIDC/JWT, JWKS, issuer/audience checks) and where in the code this is enforced.

**Location:** [src/security/jwt.py](src/security/jwt.py)

**Authentication Flow:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OIDC/JWT AUTHENTICATION FLOW                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. CLIENT REQUEST                                                          │
│     └─ Authorization: Bearer <JWT>                                          │
│                                                                             │
│  2. BEARER EXTRACTION (jwt.py::bearer_required)                             │
│     ├─ HTTPBearer security scheme extracts token                            │
│     └─ Raises HTTP 401 if missing or malformed                              │
│                                                                             │
│  3. JWT HEADER PARSING                                                      │
│     ├─ jose.jwt.get_unverified_header(token)                                │
│     └─ Extract `kid` (key ID) and `alg` (algorithm)                         │
│                                                                             │
│  4. JWKS FETCH & CACHE (jwt.py::_get_key_for_kid)                           │
│     ├─ Check in-memory cache: _JWKS_CACHE[kid]                              │
│     │   └─ Cache hit: return cached key if not expired                      │
│     ├─ Cache miss: fetch from settings.OIDC_JWKS_URL                        │
│     │   ├─ HTTP GET to JWKS endpoint (httpx async)                          │
│     │   ├─ Respect Cache-Control: max-age header                            │
│     │   └─ Support file:// URLs for testing                                 │
│     └─ Cache all keys by kid with TTL (default 900s)                        │
│                                                                             │
│  5. SIGNATURE VERIFICATION                                                  │
│     ├─ jwk.construct(key_dict) → public key                                 │
│     ├─ Manual verify: message.encode() + decoded_sig                        │
│     └─ Raises 401 if signature invalid                                      │
│                                                                             │
│  6. CLAIMS VALIDATION (jwt.py::validate_jwt)                                │
│     ├─ Time checks:                                                         │
│     │   ├─ exp (expiration) must be > now                                   │
│     │   ├─ nbf (not before) must be <= now                                  │
│     │   └─ iat (issued at) must be <= now + 60s clock skew                  │
│     ├─ Issuer check: claims["iss"] == settings.OIDC_ISSUER                  │
│     ├─ Audience check: settings.OIDC_AUDIENCE in claims["aud"]              │
│     └─ Optional TTL enforcement for internal endpoints                      │
│                                                                             │
│  7. PRINCIPAL CREATION (jwt.py::get_current_principal)                      │
│     ├─ Extract sub (subject) as user identity                               │
│     ├─ Extract scopes from: scope, scopes, roles, permissions               │
│     └─ Return Principal(sub, scopes, raw_claims)                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Code Paths:**

```python
# From jwt.py - Bearer extraction
async def bearer_required(credentials: HTTPAuthorizationCredentials = Security(_http_bearer)) -> str:
    if not credentials or str(credentials.scheme).lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return credentials.credentials

# From jwt.py - JWT validation
async def validate_jwt(token: str, *, enforce_short_ttl: bool = False) -> dict[str, Any]:
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")
    key_dict = await _get_key_for_kid(kid)
    public_key = jwk.construct(key_dict)
    
    # Verify signature
    message, encoded_sig = token.rsplit(".", 1)
    if not public_key.verify(message.encode(), base64url_decode(encoded_sig.encode())):
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    
    # Validate claims (iss, aud, exp, nbf, iat)
    claims = jwt.get_unverified_claims(token)
    # ... validation logic ...
    return claims
```

**Configuration (from config.py):**

| Setting | Purpose |
|---------|---------|
| `OIDC_JWKS_URL` | URL to fetch JSON Web Key Set (e.g., `https://auth0.example/.well-known/jwks.json`) |
| `OIDC_ISSUER` | Expected `iss` claim in tokens |
| `OIDC_AUDIENCE` | Expected `aud` claim (API identifier) |
| `OIDC_TIMEOUT_S` | HTTP timeout for JWKS fetch (default: 5s) |
| `INTERNAL_TOKEN_MAX_TTL_SECONDS` | Max TTL for internal endpoint tokens (default: 3600s) |

**JWKS Caching Strategy:**
- In-memory cache keyed by `kid`
- TTL from `Cache-Control: max-age` header (clamped 600s–900s)
- On-miss refresh: fetches entire JWKS and caches all keys
- Support for local file:// URLs in test environments

---

### **17. Authorization Model (RBAC and Scopes)**

17. **Describe the authorization model (RBAC and scopes)**: how roles, scopes, and policies are defined, and how endpoints and tools enforce them.

**Location:** [src/security/perm.py](src/security/perm.py), [src/security/authorization.py](src/security/authorization.py)

**Permission Model:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            RBAC AUTHORIZATION MODEL                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  TOKEN CLAIMS                     INTERNAL PERMISSIONS                      │
│  ─────────────                    ────────────────────                      │
│  roles: ["admin"]        ──►      admin:all (super permission)              │
│  permissions: [...]      ──►      Pass-through (Auth0 style)                │
│  scope: "read write"     ──►      Split to ["read", "write"]                │
│  scopes: ["tools:basic"] ──►      Direct permissions                        │
│                                                                             │
│  PERMISSION HIERARCHY                                                       │
│  ────────────────────                                                       │
│  admin:all  ──► grants ALL permissions (super user)                         │
│  tools:all  ──► grants all tool invocations                                 │
│  tools:basic ──► grants basic tool invocations                              │
│  user:me    ──► grants user-level operations                                │
│                                                                             │
│  ROLE → SCOPE EXPANSION (authorization.py)                                  │
│  ────────────────────────────────────────────                               │
│  "user"  → ["read", "agent.run", "tools.invoke", "models.complete",         │
│             "system.health"]                                                │
│  "admin" → ["*"]  (wildcard = full access)                                  │
│                                                                             │
│  SCOPE MATCHING MODES                                                       │
│  ───────────────────                                                        │
│  mode="any" → at least one required scope must be satisfied                 │
│  mode="all" → all required scopes must be satisfied                         │
│                                                                             │
│  WILDCARD SUPPORT                                                           │
│  ────────────────                                                           │
│  "*"        → matches everything                                            │
│  "tools.*"  → matches "tools.invoke", "tools.admin", etc.                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Permission Extraction (perm.py::current_permissions):**

```python
def current_permissions(user) -> set[str]:
    perms: set[str] = set()
    raw = getattr(user, "raw", {}) or {}
    
    # 1) Explicit permissions claim (Auth0-style)
    _ingest(raw.get("permissions"))
    
    # 2) scope (space-delimited) or scopes (array)
    _ingest(raw.get("scope"))
    _ingest(raw.get("scopes"))
    
    # 3) Roles → implicit mapping
    roles = raw.get("roles")
    if any(str(r).lower() == "admin" for r in roles):
        perms.add("admin:all")
    
    # Normalize Auth0-style names
    # tools:invoke:basic → tools:basic
    # tools:invoke:all → tools:all
    return normalize(perms)
```

**Enforcement in Endpoints:**

```python
# Dependency-based enforcement (most common pattern)
@router.get("/admin/stats", dependencies=[Depends(require_perms(["admin:all"]))])
async def get_admin_stats():
    ...

# Inline enforcement
@router.post("/tools/{tool_id}/invoke")
async def invoke_tool(user: Principal = Depends(get_current_principal)):
    enforce_perms(user, any_of=["tools:basic", "tools:all"])
    ...
```

**Scope Check Algorithm (authorization.py::check_scopes):**

```python
def check_scopes(user_scopes_or_roles, required, *, mode="any") -> bool:
    req = _as_list(required)
    eff = _expand_roles_to_scopes(user_scopes_or_roles)  # Role expansion
    
    if "*" in eff:
        return True  # Wildcard = full access
    
    if mode == "any":
        return any(_scope_satisfies(c, r) for r in req for c in eff)
    else:  # mode == "all"
        return all(any(_scope_satisfies(c, r) for c in eff) for r in req)
```

**Policy Loading (authorization.py):**

- Built-in defaults in `_DEFAULT_ROLE_SCOPES`
- Optional YAML policy files merged at startup:
  - `src/agent_policies/roles.yaml`
  - `src/mcp/policies.yaml`
- Uses PyYAML for policy file parsing (optional dependency)

---

### **18. Multi-Tenancy Implementation**

18. **Explain how multi-tenancy is implemented** at the database and service level: how tenant IDs flow through the system and how tenant isolation is ensured.

**Location:** [src/security/tenants.py](src/security/tenants.py), [db/postgres_control/models/](db/postgres_control/models/)

**Multi-Tenancy Architecture:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MULTI-TENANCY IMPLEMENTATION                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. TENANT ID SOURCES (Priority Order)                                      │
│     ├─ HTTP Header: X-Tenant-Id                                             │
│     ├─ Query Parameter: ?tenant=xxx or ?tid=xxx                             │
│     ├─ JWT Claims: tid, tenant, tenant_id, org                              │
│     └─ Default Tenant: settings.TENANCY_DEFAULT                             │
│                                                                             │
│  2. TENANT VALIDATION                                                       │
│     ├─ Regex: ^[A-Za-z][A-Za-z0-9._-]{0,63}$                                │
│     ├─ Allowlist check: settings.TENANCY_ALLOWED                            │
│     └─ Raises 400 (invalid) or 403 (not allowed)                            │
│                                                                             │
│  3. CONTEXT PROPAGATION                                                     │
│     ├─ contextvars.ContextVar("current_tenant")                             │
│     ├─ Set at request start via middleware/dependency                       │
│     └─ Accessible anywhere: get_current_tenant()                            │
│                                                                             │
│  4. DATABASE ISOLATION                                                      │
│     ├─ Every tenant-scoped table has tenant_id FK                           │
│     ├─ ON DELETE CASCADE from tenants table                                 │
│     └─ Composite indexes include tenant_id                                  │
│                                                                             │
│  5. QUERY FILTERING                                                         │
│     ├─ Repository methods filter by tenant_id                               │
│     └─ All list/get operations scope to current tenant                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Database Schema (tenant isolation via FK):**

```python
# From agent_run.py - tenant_id as FK with cascade delete
class AgentRun(Base):
    __tablename__ = "agent_runs"
    
    tenant_id = Column(
        String(255), 
        ForeignKey("tenants.id", ondelete="CASCADE"),  # Cascade on tenant deletion
        nullable=False, 
        index=True
    )
    
    __table_args__ = (
        # Composite indexes for tenant-scoped queries
        Index("idx_agent_runs_tenant_user_started", "tenant_id", "user_id", "started_at"),
        Index("idx_agent_runs_tenant_session_started", "tenant_id", "session_id", "started_at"),
    )
```

**Tenant Selection Flow (tenants.py):**

```python
def select_tenant(request, user, *, fallback_to_default=True, set_context=True) -> TenantContext:
    tenant_id, source = None, "none"
    
    # 1) Header (X-Tenant-Id)
    if request:
        tenant_id = request.headers.get(_header_name())
        source = "header"
    
    # 2) Query param (?tenant=xxx)
    if not tenant_id and request:
        tenant_id = request.query_params.get("tenant")
        source = "query"
    
    # 3) User/JWT claims
    if not tenant_id and user:
        tenant_id = _extract_from_user(user)  # tid, tenant, tenant_id, org
        source = "user"
    
    # 4) Default fallback
    if not tenant_id and fallback_to_default:
        tenant_id = settings.TENANCY_DEFAULT
        source = "default"
    
    # Validate and set context
    _validate(tenant_id)  # Regex check
    allowed = _is_allowed(tenant_id)  # Allowlist check
    set_current_tenant(tenant_id)  # Store in ContextVar
    
    return TenantContext(id=tenant_id, source=source, allowed=allowed)
```

**Key Namespacing for Cache Isolation:**

```python
def tenantize_key(key: str, tenant_id: str | None = None) -> str:
    """Prefix cache keys with tenant to avoid collisions."""
    t = tenant_id or get_current_tenant() or "global"
    return f"t:{t}:{key}"  # e.g., "t:acme:rate:count"
```

**Configuration:**

| Setting | Default | Purpose |
|---------|---------|---------|
| `TENANCY_ENABLED` | `False` | Enable tenant enforcement |
| `TENANCY_DEFAULT` | `None` | Default tenant if none provided |
| `TENANT_HEADER` | `X-Tenant-Id` | Header name for tenant ID |
| `TENANCY_ALLOWED` | `""` | Allowlist (comma-separated or `*`) |

---

### **19. Rate-Limiting Mechanisms**

19. **Describe all rate-limiting mechanisms** in the project: how they work, where they are enforced, and what is configurable.

**Location:** [src/security/rate_limit.py](src/security/rate_limit.py), [src/middleware/rate_limit.py](src/middleware/rate_limit.py), [db/redis_cache/rate_limit.py](db/redis_cache/rate_limit.py)

**Rate Limiting Architecture:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RATE LIMITING MECHANISMS                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STRATEGY: Fixed-Window Counter                                             │
│  ────────────────────────────────                                           │
│  • Window: configurable (default 60 seconds)                                │
│  • Counter: increments per request                                          │
│  • Reset: at window boundary                                                │
│                                                                             │
│  BACKENDS                                                                   │
│  ────────                                                                   │
│  ┌─────────────────────┐        ┌─────────────────────────────────┐        │
│  │  Redis (Primary)    │        │  In-Memory (Fallback)           │        │
│  │  ─────────────────  │        │  ──────────────────────         │        │
│  │  • INCR + EXPIRE    │        │  • Per-process dict             │        │
│  │  • Distributed      │        │  • Thread-safe lock             │        │
│  │  • Persistent       │        │  • Non-distributed              │        │
│  └─────────────────────┘        └─────────────────────────────────┘        │
│           │                               │                                 │
│           └───────── Automatic failover ──┘                                 │
│                                                                             │
│  SCOPES                                                                     │
│  ──────                                                                     │
│  1. Per-User Rate Limit                                                     │
│     Key: rl:{tenant}:{user_sub}:{path}                                      │
│     Purpose: Prevent individual user abuse                                  │
│                                                                             │
│  2. Per-Tenant Quota                                                        │
│     Key: quota:{tenant}:{action}                                            │
│     Purpose: Enforce organization-level limits                              │
│                                                                             │
│  ENFORCEMENT POINTS                                                         │
│  ─────────────────                                                          │
│  • RateLimitHandler (middleware) → per-endpoint                             │
│  • rate_limiter() dependency → decorative enforcement                       │
│  • Explicit rate_limit_check() calls → custom logic                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Core API (rate_limit.py):**

```python
@dataclass(frozen=True)
class RateLimitResult:
    key: str
    limit: int
    window: int
    count: int
    remaining: int
    reset_seconds: int
    allowed: bool
    backend: str  # "redis" | "memory" | "disabled"

def rate_limit_check(key: str, *, limit=None, window=None, cost=1, user=None) -> RateLimitResult:
    """Consume `cost` from current window and return result."""
    if not _enabled():
        return RateLimitResult(allowed=True, backend="disabled", ...)
    
    backend = get_backend()  # Auto-selects redis or memory
    if backend == "redis":
        return _redis_check(key, limit, window, cost=cost)
    else:
        return _mem_check(key, limit, window, cost=cost)
```

**Middleware Handler (middleware/rate_limit.py):**

```python
class RateLimitHandler:
    def __init__(self, user_id: str, tenant_id: str | None = None):
        self.user_id = user_id
        self.tenant_id = tenant_id
    
    async def check(self, action: str) -> None:
        # 1. Per-user rate limit
        key = make_rate_limit_key(action, self.user_id)
        allowed, remaining, retry_after = await check_rate_limit(key, limit, window)
        if not allowed:
            raise HTTPException(429, detail={"code": "E_RATE_LIMIT", ...})
        
        # 2. Per-tenant quota (if tenant_id provided)
        if self.tenant_id:
            tenant_allowed, _, _ = await check_tenant_quota(action, self.tenant_id)
            if not tenant_allowed:
                raise HTTPException(429, detail={"code": "E_TENANT_QUOTA", ...})
```

**FastAPI Dependency (rate_limit.py):**

```python
def rate_limiter(*, limit=None, window=None, key=None, key_func=None, cost=1):
    """Build a FastAPI dependency for rate limiting."""
    async def _dep(request: Request, user=Depends(get_current_user)):
        k = key or key_func(request, user) or _default_key_func(request, user)
        res = rate_limit_check(k, limit=limit, window=window, cost=cost)
        if not res.allowed:
            raise HTTPException(429, headers={
                "Retry-After": str(res.reset_seconds),
                "X-RateLimit-Limit": str(res.limit),
                "X-RateLimit-Remaining": str(res.remaining),
            })
    return _dep

# Usage in endpoints
@router.get("/expensive", dependencies=[Depends(rate_limiter(limit=10, window=60))])
```

**Configuration:**

| Setting | Default | Purpose |
|---------|---------|---------|
| `RATE_LIMIT_ENABLED` | `True` | Enable/disable rate limiting |
| `RATE_LIMIT_BACKEND` | `"redis"` | Backend: `redis` or `memory` |
| `RATE_LIMIT_DEFAULT_LIMIT` | `60` | Requests per window |
| `RATE_LIMIT_DEFAULT_WINDOW` | `60` | Window length in seconds |

**HTTP 429 Response Headers:**

```
Retry-After: 45
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 45
X-RateLimit-Scope: user | tenant
```

---

### **20. PII Scrubbing and Output Guarding**

20. **Identify how PII scrubbing and output guarding work**, including where sensitive data is detected and masked and how responses are sanitized.

**Location:** [src/security/pii_scrubber.py](src/security/pii_scrubber.py), [src/security/output_guard.py](src/security/output_guard.py)

**PII Scrubbing System:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             PII SCRUBBING SYSTEM                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  DETECTION PATTERNS (Regex-based)                                           │
│  ─────────────────────────────────                                          │
│  • EMAIL: [A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}                    │
│  • PHONE: Country code + area code + local number (10-15 digits)            │
│  • IPv4: \d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3} (validated octets)             │
│  • SSN (US): \d{3}-\d{2}-\d{4}                                              │
│  • IBAN: [A-Z]{2}\d{2}[A-Z0-9]{11,30}                                       │
│  • Credit Card: 13-19 digits + Luhn validation                              │
│                                                                             │
│  SENSITIVE KEYS (Key-based detection)                                       │
│  ─────────────────────────────────────                                      │
│  password, secret, api_key, token, access_token, refresh_token,             │
│  authorization, ssn, iban, credit_card, email, phone, passport,             │
│  address, dob, birthdate, tax_id, national_id                               │
│                                                                             │
│  REDACTION MODES (PII_SCRUBBER_MODE)                                        │
│  ─────────────────────────────────────                                      │
│  • mask   → "[REDACTED]" or partial mask (credit card: 4***1234)            │
│  • hash   → "sha256:<hex>" (stable, reversible with key)                    │
│  • remove → Empty string or None                                            │
│  • off    → No-op (pass through)                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**PII Scrubber API:**

```python
# Text scrubbing
def scrub_text(text: str, mode: str | None = None) -> str:
    """Redact PII in a text string."""
    hits = _scan(text)  # Find all PII matches
    for hit in reversed(hits):  # Apply back-to-front to preserve offsets
        repl = _replacement(hit, mode)
        text = text[:hit.start] + repl + text[hit.end:]
    return text

# Recursive object scrubbing
def scrub(obj: Any, mode: str | None = None) -> Any:
    """Recursively scrub dicts/lists/tuples/strings."""
    if isinstance(obj, str):
        return scrub_text(obj, mode)
    if isinstance(obj, dict):
        return scrub_dict(obj, mode)  # Also checks sensitive keys
    if isinstance(obj, list):
        return [scrub(x, mode) for x in obj]
    return obj

# Detection without scrubbing
def contains_pii(text: str) -> bool:
    return bool(find_pii(text))
```

**Output Guard System (Cypher Safety):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           OUTPUT GUARD (CYPHER)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CYPHER ANALYSIS (analyze_cypher)                                           │
│  ─────────────────────────────────                                          │
│  • has_return: RETURN clause present                                        │
│  • has_limit: LIMIT clause present                                          │
│  • writes: CREATE/MERGE/SET/DELETE/REMOVE/LOAD CSV detected                 │
│  • destructive: DROP GRAPH/TRUNCATE detected                                │
│  • unbounded: Variable-length traversal -[*]-> without bounds               │
│  • risky_call: CALL with write/create/delete/update                         │
│  • risk_score: 0-100 composite score                                        │
│                                                                             │
│  GUARD MODES (OUTPUT_GUARD_MODE)                                            │
│  ────────────────────────────────                                           │
│  • enforce → Block dangerous queries, auto-limit RETURN                     │
│  • monitor → Log but allow (annotate only)                                  │
│  • off     → No-op                                                          │
│                                                                             │
│  AUTO-REMEDIATION                                                           │
│  ────────────────                                                           │
│  • ensure_cypher_limit(query, limit=100)                                    │
│    Appends "LIMIT N" if RETURN exists without LIMIT                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Output Guard API:**

```python
def guard_cypher(query: str, *, mode=None, allow_writes=None, raise_on_block=True) -> OutputGuardResult:
    analysis = analyze_cypher(query)
    
    # Block destructive queries in enforce mode
    if analysis.destructive and mode == "enforce":
        raise HTTPException(400, detail={"message": "Query blocked", "reasons": analysis.reasons})
    
    # Auto-append LIMIT if missing
    if analysis.has_return and not analysis.has_limit:
        sanitized = ensure_cypher_limit(query, limit=100)
    
    return OutputGuardResult(allowed=True, sanitized_query=sanitized, risk_score=analysis.risk_score)
```

**Integration Points:**

1. **Orchestrator Response Sanitization** (orchestrator.py):
   - Scrubs agent output before returning to client
   - Applied after all LLM processing

2. **Cypher Query Validation** (graph tools):
   - Guards all NL→Cypher generated queries
   - Blocks destructive operations
   - Auto-limits unbounded queries

3. **Audit Log Redaction** (audit.py):
   - Scrubs sensitive meta before logging
   - Content hashes instead of raw values

---

### **21. Auditing Approach**

21. **Describe the auditing approach**: which events are logged, where audit data is stored, and how it could be used for compliance.

**Location:** [src/security/audit.py](src/security/audit.py), [db/postgres_control/models/audit_log.py](db/postgres_control/models/audit_log.py)

**Audit System Architecture:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AUDITING ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  AUDIT EVENT CATEGORIES                                                     │
│  ──────────────────────                                                     │
│  • auth      → Login success/failure, token validation                      │
│  • access    → Resource access allow/deny decisions                         │
│  • policy    → RBAC/scope checks, tenant selection, output guard            │
│  • ratelimit → Rate limit checks and denials                                │
│  • model     → LLM completions with token usage                             │
│  • data      → Data operations (read/write/delete/export)                   │
│                                                                             │
│  AUDIT EVENT STRUCTURE (AuditEvent)                                         │
│  ──────────────────────────────────                                         │
│  • event_id: UUID                                                           │
│  • ts: ISO 8601 timestamp                                                   │
│  • category: auth | access | policy | ratelimit | model | data              │
│  • action: login | check | allow | deny | complete | ...                    │
│  • outcome: success | failure | allow | deny | info                         │
│  • severity: info | warning | critical                                      │
│  • principal: User identifier (sub)                                         │
│  • tenant_id: Tenant context                                                │
│  • resource: Affected resource                                              │
│  • trace_id: Distributed tracing correlation                                │
│  • meta: Redacted metadata (sensitive keys scrubbed)                        │
│  • input_hash: SHA-256 of input content                                     │
│  • output_hash: SHA-256 of output content                                   │
│                                                                             │
│  STORAGE DESTINATIONS                                                       │
│  ────────────────────                                                       │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐    │
│  │  Structured Logs   │  │  Prometheus        │  │  Provenance Chain  │    │
│  │  (structlog)       │  │  Metrics           │  │  (append-only)     │    │
│  │  ────────────────  │  │  ──────────────    │  │  ────────────────  │    │
│  │  • JSON formatted  │  │  • Counter:        │  │  • record_         │    │
│  │  • Rotated logs    │  │    audit_events_   │  │    provenance()    │    │
│  │  • ELK/Loki ready  │  │    total           │  │  • Tamper-evident  │    │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘    │
│                                                                             │
│  POSTGRESQL AUDIT TABLE                                                     │
│  ──────────────────────                                                     │
│  • audit_logs table (AuditLog model)                                        │
│  • Indexed by: timestamp, action, resource_type, user_id, tenant_id         │
│  • JSONB details column for extensible metadata                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Audit Convenience Functions:**

```python
# Authentication events
def audit_auth_success(*, username: str, scopes: list, tenant_id: str) -> AuditEvent:
    return audit_event(category="auth", action="login", outcome="success", ...)

def audit_auth_failure(*, username: str, reason: str, tenant_id: str) -> AuditEvent:
    return audit_event(category="auth", action="login", outcome="failure", ...)

# Access control events
def audit_access(*, principal: str, resource: str, method: str, allowed: bool) -> AuditEvent:
    return audit_event(category="access", action="allow"|"deny", ...)

# Policy decisions (RBAC, tenancy, output guard)
def audit_policy_decision(*, policy: str, subject: str, action: str, resource: str, allowed: bool) -> AuditEvent:
    return audit_event(category="policy", ...)

# Rate limiting events
def audit_rate_limit(*, principal: str, key: str, allowed: bool, limit: int, count: int) -> AuditEvent:
    return audit_event(category="ratelimit", ...)

# Model usage (LLM calls)
def audit_model_usage(*, principal: str, model: str, prompt_tokens: int, completion_tokens: int) -> AuditEvent:
    return audit_event(category="model", action="complete", ...)

# Data access events
def audit_data_access(*, principal: str, operation: str, resource: str, record_count: int) -> AuditEvent:
    return audit_event(category="data", action=operation, ...)
```

**PostgreSQL Audit Log Model:**

```python
class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)  # create, update, delete
    resource_type = Column(String, nullable=False, index=True)  # model, user, tenant
    resource_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    tenant_id = Column(String, nullable=True, index=True)
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    details = Column(JSONB, nullable=True)  # Extensible metadata
```

**Compliance Use Cases:**

| Use Case | Audit Data Used |
|----------|-----------------|
| **Access Reviews** | `access` events with principal, resource, outcome |
| **Failed Login Detection** | `auth` events with outcome="failure" |
| **Rate Limit Abuse** | `ratelimit` events with allowed=False |
| **LLM Cost Tracking** | `model` events with token usage |
| **Data Exfiltration Detection** | `data` events with operation="export" |
| **Tenant Activity Reports** | All events filtered by tenant_id |
| **Security Incident Investigation** | Events correlated by trace_id |

---

### **22. Security Strengths and Weaknesses**

22. **From a security perspective, list the main strengths and potential weaknesses** you see in the current implementation, based purely on the code.

**Security Strengths:**

| Strength | Evidence | Impact |
|----------|----------|--------|
| **Defense in Depth** | Multiple security layers (JWT → RBAC → Rate Limit → PII Scrub → Output Guard) | Comprehensive protection |
| **OIDC/JWKS Integration** | Industry-standard token validation with JWKS caching | Enterprise-ready auth |
| **Automatic JWKS Refresh** | On-miss cache refresh with TTL from Cache-Control | Handles key rotation |
| **Multi-Tenant Isolation** | FK constraints, composite indexes, tenant-scoped queries | Strong data separation |
| **PII Detection Diversity** | Multiple pattern types (email, phone, SSN, CC, IBAN, IPv4) | Broad coverage |
| **Luhn Validation** | Credit card numbers verified before flagging | Reduced false positives |
| **Cypher Output Guard** | Blocks destructive operations, auto-limits queries | Prevents graph abuse |
| **Sensitive Key Scrubbing** | Redacts by key name regardless of value pattern | Catches non-regex PII |
| **Audit Trail** | Comprehensive event logging with Prometheus + provenance | Compliance ready |
| **Rate Limit Fallback** | Redis → in-memory automatic failover | High availability |
| **Content Hashing** | Audit stores hashes, not raw content | Privacy-preserving logs |
| **Role Expansion** | YAML-based policy loading with merge semantics | Flexible RBAC |
| **Wildcard Scopes** | `*` and `tools.*` patterns for flexible permissions | Enterprise scalability |

**Potential Weaknesses:**

| Weakness | Location | Risk | Recommendation |
|----------|----------|------|----------------|
| **Regex-Based PII Detection** | `pii_scrubber.py` | False negatives for novel patterns | Add ML-based detection or expand patterns |
| **Fixed-Window Rate Limiting** | `rate_limit.py` | Burst at window boundaries | Consider sliding window or token bucket |
| **In-Memory Fallback Non-Distributed** | `rate_limit.py` | Inconsistent limits across replicas | Alert on Redis failover |
| **No Token Revocation** | `jwt.py` | Compromised tokens valid until expiry | Implement token blocklist in Redis |
| **JWKS URL Required at Startup** | `jwt.py` | Single point of failure | Add retry/circuit breaker for JWKS fetch |
| **Allowlist Empty = Allow Any** | `tenants.py` | Misconfiguration risk | Require explicit allowlist in production |
| **PII Scrubber Mode "off" Option** | `pii_scrubber.py` | Can be disabled | Remove "off" mode in production configs |
| **Output Guard Monitor Mode** | `output_guard.py` | Dangerous queries logged but allowed | Default to "enforce" in production |
| **No Input Validation Rate Limiting** | N/A | Large payloads could DoS | Add request body size limits |
| **Sensitive Keys Hardcoded** | `pii_scrubber.py` | Limited customization | Externalize to config |
| **Audit Log Growth** | `audit_log.py` | Unbounded table growth | Add retention/archival policy |
| **No Encryption at Rest** | DB models | Data exposure if DB compromised | Enable TDE or column encryption |
| **Clock Skew Tolerance** | `jwt.py` | 60s skew may be too permissive | Reduce to 30s |

**Security Configuration Checklist (Production):**

```python
# Recommended production settings
APP_ENV=prod
ENABLE_SECURITY_HEADERS=True
ENABLE_HSTS=True
HSTS_MAX_AGE=31536000
SECURE_COOKIES=True
TRUST_PROXY=True  # Behind reverse proxy

# Rate limiting
RATE_LIMIT_ENABLED=True
RATE_LIMIT_BACKEND=redis

# PII and output guards
PII_SCRUBBING_ENABLED=True
PII_SCRUBBER_MODE=mask  # Never "off"
OUTPUT_GUARD_ENABLED=True
OUTPUT_GUARD_MODE=enforce  # Never "monitor" in prod
OUTPUT_GUARD_ALLOW_WRITES=False
OUTPUT_GUARD_BLOCK_DROP_GRAPH=True

# Tenancy
TENANCY_ENABLED=True
TENANCY_ALLOWED=tenant1,tenant2  # Explicit allowlist, not "*"
```

---

## D. LLM providers, resilience & cost (23–28)

### 23. Explain how LLM providers are modeled and configured (providers, model instances, defaults, priorities) in the codebase.

**Answer:**

The Cineca Agentic Platform implements a sophisticated **PostgreSQL-backed LLM provider registry** with a multi-layered configuration system. The design follows a clear hierarchy: **Providers → Model Instances → Defaults**.

---

#### **1. Provider Registry (`db/postgres_control/models/provider.py`)**

The `Provider` model represents a backend LLM service endpoint:

```python
class Provider(Base):
    """Provider registry table (authoritative source)."""
    __tablename__ = "providers"
    
    id: Mapped[str]                    # Unique provider identifier
    name: Mapped[str]                  # Human-friendly name (e.g., "openai-production")
    type: Mapped[str]                  # Provider type ("openai_compatible", "custom")
    base_url: Mapped[str | None]       # HTTP base URL (e.g., "https://api.openai.com/v1")
    model: Mapped[str | None]          # Default model identifier
    tenant_id: Mapped[str | None]      # Tenant scope (null = global)
    config_json: Mapped[dict | None]   # Provider-specific configuration (extra='allow')
    has_api_key: Mapped[bool]          # Whether api_key is configured (computed field)
```

**Key Design Decisions:**
- **Multi-tenant scoping**: Providers can be global (`tenant_id=NULL`) or tenant-specific
- **Secrets separation**: API keys are stored in a separate `ProviderSecret` table with encryption
- **Flexible config**: `config_json` supports arbitrary provider-specific keys (OpenAI-specific parameters, custom headers, etc.)
- **Type-based routing**: The `type` field determines which adapter/client to use

**Secret Storage (`ProviderSecret`):**
```python
class ProviderSecret(Base):
    """Provider secrets table (encrypted storage, never returned in API)."""
    provider_id: Mapped[str]           # FK to providers.id
    api_key_encrypted: Mapped[str | None]  # Encrypted API key (NEVER exposed in API)
```

---

#### **2. Model Instance Registry (`db/postgres_control/models/model_instance.py`)**

Model instances represent specific model configurations bound to a provider:

```python
class ModelInstance(Base):
    """Model instance registry (PostgreSQL authoritative)."""
    __tablename__ = "model_instances"
    
    id: Mapped[UUID]                   # Unique instance ID
    instance_name: Mapped[str]         # Human-readable name (e.g., "gpt-4-turbo-prod")
    provider_id: Mapped[str]           # FK to providers.id (CASCADE delete)
    model_id: Mapped[str]              # Model identifier (e.g., "gpt-4", "claude-3")
    enabled: Mapped[bool]              # Administratively enabled (default: true)
    loaded: Mapped[bool]               # Loaded in runtime (default: false)
    context_window: Mapped[int | None] # Maximum context window size
    modalities: Mapped[dict | None]    # Supported modalities (chat, completion, embedding)
    parameters: Mapped[dict | None]    # Model parameters (temperature, max_tokens)
```

**Key Characteristics:**
- **Provider binding**: Each instance belongs to exactly one provider (foreign key with CASCADE delete)
- **Runtime state tracking**: `enabled` vs `loaded` allows distinguishing between admin-disabled and not-yet-loaded states
- **Modalities support**: Tracks what capabilities each model has (chat, completion, embedding, vision, etc.)
- **Parameter templates**: Store default parameters like temperature, max_tokens per instance
- **Event logging**: `ModelInstanceEvent` provides append-only audit trail for load/unload/test/update events

---

#### **3. Default Model Resolution (`db/postgres_control/models/model_instance.py` + `src/services/default_model_resolver.py`)**

The `ModelDefault` table designates which instance is the default for a given scope:

```python
class ModelDefault(Base):
    """Default model instance per scope (global or tenant)."""
    __tablename__ = "model_defaults"
    
    scope: Mapped[str]                 # "global" or "tenant"
    tenant_id: Mapped[str | None]      # Tenant ID (null for global scope)
    instance_id: Mapped[UUID]          # FK to model_instances.id
    
    # Constraints:
    # - scope IN ('global', 'tenant')
    # - (scope = 'global' AND tenant_id IS NULL) OR (scope = 'tenant' AND tenant_id IS NOT NULL)
```

**Default Model Resolver (DMR) Service:**

The `DefaultModelResolver` singleton (`src/services/default_model_resolver.py`) implements a **3-tier resolution strategy**:

```python
class DefaultModelResolver:
    """
    Resolves the default model for API requests, orchestrator, health checks, etc.
    
    Resolution order:
    1. Redis cache (if hit) — 15 min TTL
    2. PostgreSQL (authoritative)
    3. Environment variable (emergency fallback)
    """
    
    async def get_default_model(self, tenant_id: str | None = None, scope: str = "global"):
        # 1. Try Redis cache (fast path)
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result  # source="redis", cached=True
        
        # 2. Query PostgreSQL (authoritative)
        db_result = await self._get_from_db(scope, tenant_id)
        if db_result:
            await self._set_cache(cache_key, db_result)  # Warm cache
            return db_result  # source="db", cached=False
        
        # 3. Environment variable fallback
        if self.allow_env_fallback:
            env_model = os.getenv("LLM_DEFAULT_MODEL")
            if env_model:
                return {"model_id": env_model, "source": "env"}
        
        return None
```

**Configuration:**
```python
DEFAULT_MODEL_CACHE_TTL_SECONDS = 900  # 15 minutes
DEFAULT_MODEL_ALLOW_ENV_FALLBACK = True
```

---

#### **4. Priority and Selection Logic**

**In the Resilience Framework (`src/resilience/llm_fallback.py`):**

Providers are assigned priorities through `ProviderConfig`:

```python
@dataclass
class ProviderConfig:
    name: str
    priority: int = 1              # Lower = higher priority (primary)
    enabled: bool = True
    max_cost_per_hour: float = 10.0  # USD per hour limit
    max_tokens_per_request: int = 4096
    timeout_seconds: float = 30.0
    failure_threshold: int = 5     # Circuit breaker opens after 5 failures
    recovery_timeout: float = 60.0 # Seconds before half-open
    success_threshold: int = 2     # Successes needed to close circuit
```

**Example Priority Configuration:**
```python
configs = [
    ProviderConfig(name="openai-gpt4", priority=1),      # Primary
    ProviderConfig(name="anthropic-claude", priority=2), # Secondary fallback
    ProviderConfig(name="azure-openai", priority=3),     # Tertiary fallback
]
```

**In the Orchestrator (`src/services/orchestrator.py`):**

The orchestrator selects the main LLM through a registry-based approach:

1. Query registered Ollama models (excluding reserved names like `planner`, `workerA`, `workerB`)
2. Use the first registered model as `main_llm_name`
3. Set `default_model` from the selected client's model attribute
4. Support for `LLM_TOOL_PREFERENCES`, `LLM_AGENT_ROLES`, and `LLM_TOOL_ACL` mappings

---

#### **5. Provider Audit Trail**

All provider changes are logged to `ProviderAuditEvent`:

```python
class ProviderAuditEvent(Base):
    """Append-only audit log for provider changes."""
    __tablename__ = "provider_audit_events"
    
    event_type: Mapped[str]        # create, update, delete, secret_update
    provider_id: Mapped[str]       # Affected provider
    actor_sub: Mapped[str | None]  # User who made the change
    trace_id: Mapped[str | None]   # Request correlation ID
    event_json: Mapped[dict | None] # Change details (excluding secrets)
```

---

### 24. Describe the resilience framework for LLM calls: provider pool, circuit breakers, cost tracking, and fallback behavior.

**Answer:**

The platform implements a **comprehensive resilience framework** in `src/resilience/llm_fallback.py` that provides enterprise-grade fault tolerance for LLM calls. The framework consists of four interconnected components: **Provider Pool**, **Circuit Breakers**, **Cost Tracking**, and **Fallback Orchestration**.

---

#### **1. Provider Pool Architecture**

The `LLMFallbackOrchestrator` manages a pool of LLM providers:

```python
class LLMFallbackOrchestrator:
    """Orchestrates LLM calls with fallback, circuit breaker, and cost tracking."""
    
    def __init__(self, providers: dict[str, LLMProvider], configs: list[ProviderConfig]):
        self.providers = providers
        # Sort configs by priority (lower = higher priority)
        self.configs = {c.name: c for c in sorted(configs, key=lambda x: x.priority)}
        
        # Per-provider components
        self.circuit_breakers = {name: CircuitBreaker(...) for name in self.configs}
        self.cost_trackers = {name: CostTracker(...) for name in self.configs}
        self.health_status: dict[str, float | None] = {}
```

**Provider Protocol:**
```python
class LLMProvider(Protocol):
    """Protocol for LLM providers."""
    
    async def call(self, prompt: str, max_tokens: int, temperature: float, **kwargs) -> dict[str, Any]:
        """Returns: {"content": str, "input_tokens": int, "output_tokens": int, "model": str}"""
        ...
    
    async def health_check(self) -> bool:
        """Check if provider is healthy."""
        ...
```

---

#### **2. Circuit Breaker Pattern**

Each provider has its own circuit breaker implementing the **three-state pattern**:

```python
class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation, requests flow through
    OPEN = "open"          # Provider failed, requests blocked
    HALF_OPEN = "half_open" # Testing recovery, limited requests allowed

class CircuitBreaker:
    def __init__(
        self,
        provider_name: str,
        failure_threshold: int = 5,    # Open after 5 consecutive failures
        recovery_timeout: float = 60.0, # Seconds before testing recovery
        success_threshold: int = 2,     # Successes to close from half-open
    ):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.opened_at: float | None = None
```

**State Transitions:**

```
CLOSED ──(5 failures)──> OPEN ──(60s timeout)──> HALF_OPEN ──(2 successes)──> CLOSED
                           ↑                        │
                           └───(any failure)────────┘
```

**Key Methods:**

```python
def can_attempt(self) -> bool:
    """Check if we can attempt a call."""
    if self.state == CircuitState.CLOSED:
        return True
    if self.state == CircuitState.OPEN:
        if time.time() - self.opened_at >= self.recovery_timeout:
            self._half_open()  # Transition to half-open after timeout
            return True
        return False  # Still open, block request
    return True  # Half-open allows one test request

def record_success(self) -> None:
    """Record successful call."""
    self.failure_count = 0
    if self.state == CircuitState.HALF_OPEN:
        self.success_count += 1
        if self.success_count >= self.success_threshold:
            self._close()  # Recovery confirmed

def record_failure(self) -> None:
    """Record failed call."""
    if self.state == CircuitState.HALF_OPEN:
        self._open()  # Immediate return to open on failure
        return
    self.failure_count += 1
    if self.failure_count >= self.failure_threshold:
        self._open()
```

---

#### **3. Cost Tracking and Budget Enforcement**

The `CostTracker` class implements **sliding-window cost accounting**:

```python
@dataclass
class CostTracker:
    """Track provider costs and enforce caps."""
    
    max_cost_per_hour: float
    window_size_seconds: int = 3600  # 1 hour sliding window
    
    # Provider-specific pricing (per 1K tokens)
    PROVIDER_COSTS = {
        "openai-gpt4": {"input": 0.03, "output": 0.06},
        "openai-gpt35": {"input": 0.001, "output": 0.002},
        "anthropic-claude": {"input": 0.008, "output": 0.024},
        "azure-openai": {"input": 0.03, "output": 0.06},
        "stub": {"input": 0.0, "output": 0.0},  # Test stub is free
    }
    
    costs: list[dict[str, Any]] = field(default_factory=list)
```

**Usage Recording:**

```python
def record_usage(self, provider: str, input_tokens: int, output_tokens: int) -> float:
    """Record token usage and return cost."""
    pricing = self.PROVIDER_COSTS.get(provider, {"input": 0.01, "output": 0.02})
    cost = (input_tokens / 1000.0 * pricing["input"]) + 
           (output_tokens / 1000.0 * pricing["output"])
    
    self.costs.append({
        "timestamp": time.time(),
        "provider": provider,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
    })
    self._cleanup_old_costs()  # Remove entries outside window
    return cost
```

**Budget Enforcement:**

```python
def can_afford(self, estimated_tokens: int, provider: str) -> bool:
    """Check if request is within cost cap."""
    current_cost = self.get_current_cost()
    
    # Estimate cost (assume 50/50 input/output split)
    pricing = self.PROVIDER_COSTS.get(provider, {"input": 0.01, "output": 0.02})
    estimated_cost = (estimated_tokens / 2000.0 * pricing["input"] + 
                      estimated_tokens / 2000.0 * pricing["output"])
    
    return (current_cost + estimated_cost) <= self.max_cost_per_hour
```

**Statistics:**

```python
def get_stats(self) -> dict[str, Any]:
    return {
        "current_cost": total_cost,
        "max_cost_per_hour": self.max_cost_per_hour,
        "remaining_budget": max(0, self.max_cost_per_hour - total_cost),
        "utilization_pct": min(100, (total_cost / self.max_cost_per_hour) * 100),
        "total_input_tokens": ...,
        "total_output_tokens": ...,
        "request_count": len(self.costs),
    }
```

---

#### **4. Fallback Orchestration**

The `LLMFallbackOrchestrator.call()` method implements **priority-based fallback**:

```python
async def call(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.7, **kwargs) -> dict[str, Any]:
    """Call LLM with automatic fallback."""
    self.stats["total_calls"] += 1
    errors = []
    attempted_providers = []
    
    # Try providers in priority order
    for provider_name, config in self.configs.items():
        if not config.enabled:
            continue
        
        attempted_providers.append(provider_name)
        
        # Gate 1: Circuit breaker check
        circuit = self.circuit_breakers[provider_name]
        if not circuit.can_attempt():
            self.stats["circuit_breaker_blocks"] += 1
            errors.append(f"{provider_name}: Circuit breaker {circuit.state.value}")
            continue
        
        # Gate 2: Cost cap check
        cost_tracker = self.cost_trackers[provider_name]
        if not cost_tracker.can_afford(max_tokens, provider_name):
            self.stats["cost_limited_calls"] += 1
            errors.append(f"{provider_name}: Cost cap exceeded")
            continue
        
        # Gate 3: Token limit check
        if max_tokens > config.max_tokens_per_request:
            errors.append(f"{provider_name}: Exceeds token limit")
            continue
        
        # Attempt the call
        try:
            result = await asyncio.wait_for(
                provider.call(prompt, max_tokens, temperature, **kwargs),
                timeout=config.timeout_seconds,
            )
            
            # Record success
            circuit.record_success()
            cost_tracker.record_usage(provider_name, result["input_tokens"], result["output_tokens"])
            self.stats["successful_calls"] += 1
            
            fallback_used = attempted_providers.index(provider_name) > 0
            if fallback_used:
                self.stats["fallback_calls"] += 1
            
            return {
                **result,
                "provider": provider_name,
                "fallback_used": fallback_used,
            }
        
        except TimeoutError:
            circuit.record_failure()
            errors.append(f"{provider_name}: Timeout")
            continue
        
        except Exception as e:
            circuit.record_failure()
            errors.append(f"{provider_name}: {e!s}")
            continue
    
    # All providers failed
    self.stats["failed_calls"] += 1
    raise Exception(f"All LLM providers failed. Attempted: {attempted_providers}. Errors: {errors}")
```

---

#### **5. Health Probing**

The orchestrator supports proactive health checks:

```python
async def health_probe(self, provider_name: str) -> bool:
    """Probe provider health."""
    try:
        healthy = await asyncio.wait_for(provider.health_check(), timeout=5.0)
        if healthy:
            self.health_status[provider_name] = time.time()
        return healthy
    except Exception:
        return False

async def health_probe_all(self) -> dict[str, bool]:
    """Probe all providers concurrently."""
    tasks = {name: self.health_probe(name) for name in self.configs}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    return {name: result if isinstance(result, bool) else False 
            for name, result in zip(tasks.keys(), results)}
```

---

#### **6. Observability and Status Reporting**

```python
def get_status(self) -> dict[str, Any]:
    """Get orchestrator status."""
    return {
        "stats": self.stats.copy(),
        "circuit_breakers": {name: cb.get_state_dict() for name, cb in self.circuit_breakers.items()},
        "cost_trackers": {name: ct.get_stats() for name, ct in self.cost_trackers.items()},
        "health_status": self.health_status.copy(),
        "provider_order": [
            {"name": name, "priority": config.priority, "enabled": config.enabled}
            for name, config in self.configs.items()
        ],
    }
```

---

### 25. Walk through a typical LLM call end-to-end, showing how the orchestrator picks a provider, calls it, handles errors, and falls back if needed.

**Answer:**

This walkthrough traces an LLM call from API request through to response, showing all decision points and fallback paths.

---

#### **Scenario Setup**

**Configuration:**
- Primary: `openai-gpt4` (priority=1, max_cost_per_hour=$10)
- Secondary: `anthropic-claude` (priority=2, max_cost_per_hour=$5)
- Tertiary: `azure-openai` (priority=3, max_cost_per_hour=$8)

**Initial State:**
- All circuit breakers: CLOSED
- All cost trackers: $0.00 / $X.00

---

#### **Step 1: API Request Received**

```
POST /v1/agents/{agent_id}/runs
{
  "input": "Explain quantum computing",
  "model": null  // Use default
}
```

The request flows through:
1. **Authentication middleware**: Validates JWT, extracts tenant_id and user_sub
2. **Authorization check**: Verifies `agents:run` scope
3. **Agent router** (`src/routers/agents.py`): Routes to orchestrator

---

#### **Step 2: Orchestrator Initialization**

The orchestrator resolves the default model via DMR:

```python
# In orchestrator.py
async def _resolve_model(self, tenant_id: str | None):
    dmr = get_dmr()
    result = await dmr.get_default_model(tenant_id=tenant_id)
    
    # Resolution chain:
    # 1. Redis cache check (key: "models:default:tenant:{tenant_id}")
    #    → MISS (first request)
    # 2. PostgreSQL query (model_defaults JOIN model_instances JOIN providers)
    #    → HIT: instance_id=uuid-123, model_id="gpt-4", provider_id="openai-prod"
    # 3. Cache warmup (set with 15 min TTL)
    
    return result  # {"model_id": "gpt-4", "source": "db", "cached": False}
```

---

#### **Step 3: LLM Call Initiated**

The orchestrator calls `call_model()`:

```python
# In orchestrator.py
async def call_model(self, prompt: str, **kwargs) -> str:
    self.llm_call_count += 1  # Increment counter
    
    # Build LLM request
    client = self.llm_clients[self.main_llm_name]
    return await client.complete(prompt=prompt, **kwargs)
```

For resilience mode, the `LLMFallbackOrchestrator.call()` is invoked:

```python
result = await orchestrator.call(
    prompt="Explain quantum computing",
    max_tokens=1000,
    temperature=0.7,
)
```

---

#### **Step 4: Provider Selection (Priority Order)**

```python
# In llm_fallback.py
self.stats["total_calls"] += 1
errors = []
attempted_providers = []

for provider_name, config in self.configs.items():  # Sorted by priority
    # Provider order: openai-gpt4 (1), anthropic-claude (2), azure-openai (3)
```

---

#### **Step 5: First Attempt — openai-gpt4**

**Gate 1: Enabled Check**
```python
if not config.enabled:
    continue  # Skip disabled providers
# openai-gpt4.enabled = True → PASS
```

**Gate 2: Circuit Breaker Check**
```python
circuit = self.circuit_breakers["openai-gpt4"]
if not circuit.can_attempt():
    self.stats["circuit_breaker_blocks"] += 1
    errors.append("openai-gpt4: Circuit breaker open")
    continue
# State = CLOSED → PASS
```

**Gate 3: Cost Cap Check**
```python
cost_tracker = self.cost_trackers["openai-gpt4"]
if not cost_tracker.can_afford(max_tokens=1000, provider="openai-gpt4"):
    self.stats["cost_limited_calls"] += 1
    errors.append("openai-gpt4: Cost cap exceeded")
    continue
# current_cost=$0.00, estimated=$0.045 (1000 tokens), cap=$10 → PASS
```

**Gate 4: Token Limit Check**
```python
if max_tokens > config.max_tokens_per_request:
    errors.append("openai-gpt4: Exceeds limit 8192")
    continue
# 1000 <= 8192 → PASS
```

**Gate 5: Provider Exists**
```python
provider = self.providers.get("openai-gpt4")
if not provider:
    errors.append("openai-gpt4: Provider not found")
    continue
# Provider exists → PASS
```

---

#### **Step 6: Make the Call (with Timeout)**

```python
try:
    result = await asyncio.wait_for(
        provider.call(
            prompt="Explain quantum computing",
            max_tokens=1000,
            temperature=0.7,
        ),
        timeout=config.timeout_seconds,  # 30s
    )
```

---

#### **Step 7a: Success Path**

If the call succeeds:

```python
# Response from OpenAI
result = {
    "content": "Quantum computing is a type of computation that harnesses...",
    "input_tokens": 8,
    "output_tokens": 250,
    "model": "gpt-4-turbo",
}

# Record success
circuit.record_success()
# → failure_count reset to 0, state remains CLOSED

cost_tracker.record_usage("openai-gpt4", input_tokens=8, output_tokens=250)
# → Cost: (8/1000 * $0.03) + (250/1000 * $0.06) = $0.00024 + $0.015 = $0.01524
# → costs list updated with timestamp

self.stats["successful_calls"] += 1

# Check if fallback was used
fallback_used = attempted_providers.index("openai-gpt4") > 0
# → False (index 0, primary provider)

return {
    "content": "Quantum computing is a type of computation...",
    "input_tokens": 8,
    "output_tokens": 250,
    "model": "gpt-4-turbo",
    "provider": "openai-gpt4",
    "fallback_used": False,
}
```

---

#### **Step 7b: Failure Path — Timeout**

If OpenAI times out:

```python
except TimeoutError:
    circuit.record_failure()
    # → failure_count: 0 → 1 (threshold = 5, not yet open)
    
    errors.append("openai-gpt4: Timeout after 30s")
    logger.warning("LLM call timeout for openai-gpt4")
    continue  # Try next provider
```

---

#### **Step 7c: Failure Path — API Error**

If OpenAI returns an error:

```python
except Exception as e:  # e.g., RateLimitError
    circuit.record_failure()
    # → failure_count: 1 → 2
    
    errors.append("openai-gpt4: Rate limit exceeded")
    logger.warning("LLM call failed for openai-gpt4: Rate limit exceeded")
    continue  # Try next provider
```

---

#### **Step 8: Fallback to anthropic-claude**

After openai-gpt4 fails, the loop continues to the next provider:

```python
# Next iteration: anthropic-claude
attempted_providers = ["openai-gpt4", "anthropic-claude"]

# Same gate checks...
# All pass, make the call:

result = await asyncio.wait_for(
    provider.call(prompt, max_tokens, temperature),
    timeout=30.0,
)

# Success!
circuit.record_success()  # anthropic-claude circuit
cost_tracker.record_usage("anthropic-claude", input_tokens=8, output_tokens=240)
# → Cost: (8/1000 * $0.008) + (240/1000 * $0.024) = $0.00006 + $0.00576 = $0.00582

self.stats["successful_calls"] += 1
fallback_used = True  # index 1 > 0

self.stats["fallback_calls"] += 1

return {
    "content": "Quantum computing leverages quantum mechanical phenomena...",
    "input_tokens": 8,
    "output_tokens": 240,
    "model": "claude-3-opus",
    "provider": "anthropic-claude",
    "fallback_used": True,
}
```

---

#### **Step 9: All Providers Fail**

If all three providers fail:

```python
# After trying all providers:
self.stats["failed_calls"] += 1
error_msg = (
    "All LLM providers failed. "
    "Attempted: ['openai-gpt4', 'anthropic-claude', 'azure-openai']. "
    "Errors: ['openai-gpt4: Timeout', 'anthropic-claude: 503 Service Unavailable', 'azure-openai: Cost cap exceeded']"
)
logger.error(error_msg)
raise Exception(error_msg)
```

---

#### **Step 10: Response to Client**

The result flows back through:
1. **Orchestrator**: Records step metrics, updates run state
2. **Agent router**: Formats response
3. **SSE stream**: Sends event to client

```json
{
  "type": "agent_message",
  "content": "Quantum computing leverages quantum mechanical phenomena...",
  "metadata": {
    "provider": "anthropic-claude",
    "fallback_used": true,
    "input_tokens": 8,
    "output_tokens": 240,
    "model": "claude-3-opus"
  }
}
```

---

#### **State After Call**

| Provider | Circuit State | Failure Count | Cost (1h window) |
|----------|---------------|---------------|------------------|
| openai-gpt4 | CLOSED | 1 | $0.00 |
| anthropic-claude | CLOSED | 0 | $0.00582 |
| azure-openai | CLOSED | 0 | $0.00 |

| Statistic | Value |
|-----------|-------|
| total_calls | 1 |
| successful_calls | 1 |
| failed_calls | 0 |
| fallback_calls | 1 |
| cost_limited_calls | 0 |
| circuit_breaker_blocks | 0 |

---

### 26. Identify how token usage and costs are tracked and how budgets are enforced for different providers.

**Answer:**

The platform implements **comprehensive token and cost tracking** with real-time budget enforcement through multiple layers.

---

#### **1. Token Tracking at LLM Adapter Level**

The LLM adapter (`src/adapters/llm.py`) captures token usage from provider responses:

```python
class LLMClient:
    async def complete(self, *, prompt: str, **kwargs) -> str:
        response = await self._http.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=self.timeout,
        )
        data = response.json()
        
        # Extract usage from OpenAI-compatible response
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        
        return {
            "content": data["choices"][0]["message"]["content"],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": data.get("model"),
        }
```

---

#### **2. Cost Calculation Formula**

The `CostTracker` applies **provider-specific pricing** per 1,000 tokens:

```python
PROVIDER_COSTS = {
    "openai-gpt4":    {"input": 0.03,  "output": 0.06},   # $0.03/1K in, $0.06/1K out
    "openai-gpt35":   {"input": 0.001, "output": 0.002},  # $0.001/1K in, $0.002/1K out
    "anthropic-claude": {"input": 0.008, "output": 0.024}, # $0.008/1K in, $0.024/1K out
    "azure-openai":   {"input": 0.03,  "output": 0.06},   # Same as OpenAI
    "stub":           {"input": 0.0,   "output": 0.0},    # Free (testing)
}

def record_usage(self, provider: str, input_tokens: int, output_tokens: int) -> float:
    pricing = self.PROVIDER_COSTS.get(provider, {"input": 0.01, "output": 0.02})
    
    cost = (input_tokens / 1000.0 * pricing["input"]) + 
           (output_tokens / 1000.0 * pricing["output"])
    
    self.costs.append({
        "timestamp": time.time(),
        "provider": provider,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
    })
    
    return cost
```

**Example Calculation:**
```
Provider: openai-gpt4
Input tokens: 500
Output tokens: 1000

Cost = (500/1000 × $0.03) + (1000/1000 × $0.06)
     = $0.015 + $0.06
     = $0.075
```

---

#### **3. Sliding Window Budget Tracking**

Costs are tracked within a **1-hour sliding window**:

```python
window_size_seconds: int = 3600  # 1 hour

def _cleanup_old_costs(self) -> None:
    """Remove cost entries outside window."""
    cutoff = time.time() - self.window_size_seconds
    self.costs = [c for c in self.costs if c["timestamp"] >= cutoff]

def get_current_cost(self) -> float:
    """Get total cost in current window."""
    self._cleanup_old_costs()
    return sum(c["cost"] for c in self.costs)
```

This ensures:
- Old costs "expire" after 1 hour
- Budget is always calculated on a rolling basis
- No persistent storage required for cost tracking

---

#### **4. Pre-Call Budget Enforcement**

Before each LLM call, the orchestrator checks if the request is affordable:

```python
def can_afford(self, estimated_tokens: int, provider: str) -> bool:
    """Check if request is within cost cap."""
    current_cost = self.get_current_cost()
    
    # Conservative estimate: assume 50/50 input/output split
    pricing = self.PROVIDER_COSTS.get(provider, {"input": 0.01, "output": 0.02})
    estimated_cost = (
        estimated_tokens / 2000.0 * pricing["input"] + 
        estimated_tokens / 2000.0 * pricing["output"]
    )
    
    return (current_cost + estimated_cost) <= self.max_cost_per_hour
```

**Usage in Orchestrator:**
```python
# In LLMFallbackOrchestrator.call()
cost_tracker = self.cost_trackers[provider_name]
if not cost_tracker.can_afford(max_tokens, provider_name):
    self.stats["cost_limited_calls"] += 1
    errors.append(f"{provider_name}: Cost cap exceeded")
    continue  # Try next provider
```

---

#### **5. Per-Provider Budget Configuration**

Each provider has an independent budget configured via `ProviderConfig`:

```python
configs = [
    ProviderConfig(
        name="openai-gpt4",
        priority=1,
        max_cost_per_hour=10.0,  # $10/hour limit
    ),
    ProviderConfig(
        name="anthropic-claude",
        priority=2,
        max_cost_per_hour=5.0,   # $5/hour limit
    ),
    ProviderConfig(
        name="azure-openai",
        priority=3,
        max_cost_per_hour=8.0,   # $8/hour limit
    ),
]
```

---

#### **6. Budget Status Reporting**

The `get_stats()` method provides real-time budget visibility:

```python
def get_stats(self) -> dict[str, Any]:
    self._cleanup_old_costs()
    total_cost = sum(c["cost"] for c in self.costs)
    
    return {
        "current_cost": total_cost,
        "max_cost_per_hour": self.max_cost_per_hour,
        "remaining_budget": max(0, self.max_cost_per_hour - total_cost),
        "utilization_pct": min(100, (total_cost / self.max_cost_per_hour) * 100),
        "total_input_tokens": sum(c["input_tokens"] for c in self.costs),
        "total_output_tokens": sum(c["output_tokens"] for c in self.costs),
        "request_count": len(self.costs),
    }
```

**Example Output:**
```json
{
    "current_cost": 4.52,
    "max_cost_per_hour": 10.0,
    "remaining_budget": 5.48,
    "utilization_pct": 45.2,
    "total_input_tokens": 45000,
    "total_output_tokens": 52000,
    "request_count": 127
}
```

---

#### **7. Fallback on Budget Exhaustion**

When a provider's budget is exhausted, requests automatically fall back:

```
openai-gpt4 (priority=1): $10.00/$10.00 → BLOCKED (cost cap)
  ↓ fallback
anthropic-claude (priority=2): $2.30/$5.00 → AVAILABLE
  ↓ success
Request served by anthropic-claude
```

This ensures:
- **No service interruption**: Requests continue via fallback
- **Cost control**: Each provider respects its budget
- **Observability**: `cost_limited_calls` counter tracks blocking events

---

#### **8. Metrics and Observability**

Token usage and costs are exposed via Prometheus metrics:

```python
# From src/observability/metrics.py
llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens used",
    ["provider", "direction"],  # direction: input/output
)

llm_cost_usd = Counter(
    "llm_cost_usd",
    "Total LLM cost in USD",
    ["provider"],
)
```

And in logging:

```python
logger.info(
    f"LLM call succeeded via {provider_name} "
    f"(fallback={fallback_used}, tokens={result.get('input_tokens', 0)}+{result.get('output_tokens', 0)})"
)
```

---

#### **9. Limitations and Future Improvements**

| Current Limitation | Potential Enhancement |
|-------------------|----------------------|
| In-memory cost tracking (lost on restart) | Persist to Redis with TTL |
| Hardcoded provider pricing | Admin API to update pricing |
| No tenant-level budgets | Per-tenant cost caps |
| Estimated pre-check (50/50 split) | Use historical token ratios |
| No alerting on budget thresholds | Prometheus alerting rules |

---

### 27. Compare the LLM resilience design in this project with what you typically see in common LLM frameworks (e.g., single-provider + simple retries).

**Answer:**

This comparison analyzes the Cineca Agentic Platform's resilience approach against common LLM framework patterns.

---

#### **1. Typical LLM Framework Approaches**

**LangChain:**
```python
# Simple retry decorator
from langchain.llms import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def call_llm(prompt):
    llm = OpenAI(model="gpt-4")
    return llm(prompt)
```

**LlamaIndex:**
```python
from llama_index.llms import OpenAI
# Single provider, built-in retry logic
llm = OpenAI(model="gpt-4", max_retries=3)
```

**OpenAI SDK:**
```python
from openai import OpenAI
client = OpenAI(max_retries=2)  # Simple retry on transient errors
```

---

#### **2. Feature Comparison Matrix**

| Feature | Typical Frameworks | Cineca Agentic Platform |
|---------|-------------------|------------------------|
| **Provider Model** | Single provider | Multi-provider pool |
| **Retry Strategy** | Simple exponential backoff | Circuit breaker + priority fallback |
| **Failover** | None / manual | Automatic priority-based |
| **Cost Tracking** | None / external | Built-in per-provider |
| **Budget Enforcement** | None | Per-provider hourly caps |
| **Health Probing** | None | Async health checks |
| **Circuit Breaker** | Rare | Per-provider with 3 states |
| **Observability** | Basic logging | Prometheus + structured logging |
| **Configuration** | Code-level | Database + runtime config |

---

#### **3. Detailed Comparison**

##### **3.1 Provider Management**

| Aspect | Typical | Cineca |
|--------|---------|--------|
| Registration | Hardcoded in config | PostgreSQL registry |
| Multi-tenancy | None | Tenant-scoped providers |
| Secrets | Env vars or config | Encrypted DB storage |
| Dynamic updates | Restart required | Runtime via API |

**Typical:**
```python
# LangChain - hardcoded
llm = ChatOpenAI(model="gpt-4", api_key=os.getenv("OPENAI_API_KEY"))
```

**Cineca:**
```python
# Database-driven
Provider(name="openai-prod", type="openai_compatible", tenant_id="tenant-123")
ProviderSecret(provider_id="openai-prod", api_key_encrypted="...")
```

##### **3.2 Failure Handling**

| Aspect | Typical | Cineca |
|--------|---------|--------|
| Pattern | Retry decorator | Circuit breaker |
| Scope | Per-request | Per-provider state |
| Memory | None (stateless) | Failure history |
| Recovery | Immediate retry | Timed recovery window |

**Typical (tenacity):**
```python
@retry(stop=stop_after_attempt(3))
def call():
    # Retries same provider 3 times
    # No memory of past failures
    return llm.call(prompt)
```

**Cineca (circuit breaker):**
```python
# After 5 failures → circuit opens
# After 60s → circuit half-opens (test request)
# After 2 successes → circuit closes
if not circuit.can_attempt():
    continue  # Skip this provider
```

##### **3.3 Fallback Strategy**

| Aspect | Typical | Cineca |
|--------|---------|--------|
| Fallback model | Manual if-else | Automatic priority order |
| Configuration | Code changes | ProviderConfig.priority |
| Triggering | Exception catching | Any gate failure |

**Typical:**
```python
try:
    return openai_llm(prompt)
except Exception:
    return anthropic_llm(prompt)  # Manual fallback
```

**Cineca:**
```python
# Automatic iteration through priority-ordered providers
for provider_name, config in self.configs.items():  # Sorted by priority
    if not circuit.can_attempt(): continue
    if not cost_tracker.can_afford(): continue
    # ... try provider
```

##### **3.4 Cost Management**

| Aspect | Typical | Cineca |
|--------|---------|--------|
| Tracking | External (billing dashboard) | Built-in per-request |
| Enforcement | None | Pre-call budget check |
| Granularity | Account-level | Per-provider hourly |
| Alerting | External | Metrics + fallback |

**Typical:**
```python
# No cost awareness
response = llm.call(prompt)  # May exceed budget
```

**Cineca:**
```python
# Pre-flight cost check
if not cost_tracker.can_afford(estimated_tokens, provider):
    continue  # Skip to cheaper provider
```

---

#### **4. Architectural Differences**

##### **4.1 State Management**

```
Typical Framework:
┌────────────────────┐
│     Stateless      │
│   Request → LLM    │
│   (no memory)      │
└────────────────────┘

Cineca Platform:
┌────────────────────────────────────────────────────┐
│                   Stateful Pool                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ Provider 1  │  │ Provider 2  │  │ Provider 3  │ │
│  │ ─────────── │  │ ─────────── │  │ ─────────── │ │
│  │ Circuit: ✓  │  │ Circuit: ✗  │  │ Circuit: ✓  │ │
│  │ Cost: $2.30 │  │ Cost: $4.80 │  │ Cost: $1.20 │ │
│  │ Health: ✓   │  │ Health: ?   │  │ Health: ✓   │ │
│  └─────────────┘  └─────────────┘  └─────────────┘ │
└────────────────────────────────────────────────────┘
```

##### **4.2 Decision Flow**

```
Typical Framework:
Request → Retry(3) → Success/Fail

Cineca Platform:
Request → Enabled? → Circuit OK? → Budget OK? → Token OK? → Call
            │            │             │            │          │
            ↓            ↓             ↓            ↓          ↓
         Skip      Try Next      Try Next    Try Next   Record
```

---

#### **5. Quantitative Comparison**

| Metric | Typical | Cineca |
|--------|---------|--------|
| Max retries | 3 (same provider) | N providers × 1 attempt each |
| Failure memory | 0 | 5 failures before open |
| Recovery delay | 0 (immediate) | 60s before half-open |
| Cost visibility | None | Real-time per-provider |
| Fallback latency | Exception handling time | Minimal (pre-filtered) |

---

#### **6. When Each Approach is Better**

| Scenario | Better Choice | Reason |
|----------|---------------|--------|
| Prototyping | Typical | Simpler setup |
| Single provider | Typical | No pool needed |
| Production scale | Cineca | Reliability + cost control |
| Multi-region | Cineca | Provider diversity |
| Cost-sensitive | Cineca | Budget enforcement |
| Transient errors | Either | Both handle retries |
| Sustained outage | Cineca | Circuit breaker prevents cascading |

---

#### **7. Summary**

| Dimension | Typical Frameworks | Cineca Platform |
|-----------|-------------------|-----------------|
| **Complexity** | Low | Medium-High |
| **Reliability** | Basic | Enterprise-grade |
| **Cost Control** | None | Comprehensive |
| **Flexibility** | Limited | High |
| **Observability** | Basic | Rich metrics |
| **Operations** | Simple | More setup required |

The Cineca approach is **significantly more sophisticated** than typical framework patterns, implementing patterns seen in production systems at companies like Netflix (Hystrix-style circuit breakers) and financial institutions (per-provider cost caps).

---

### 28. List the main advantages and disadvantages of this multi-provider resilience strategy, including complexity and operational trade-offs.

**Answer:**

This analysis evaluates the multi-provider resilience strategy from both theoretical and practical perspectives.

---

#### **Advantages**

##### **1. High Availability and Fault Tolerance**

| Benefit | Description | Impact |
|---------|-------------|--------|
| **No single point of failure** | If OpenAI goes down, Anthropic takes over | 99.9%+ uptime possible |
| **Graceful degradation** | System continues with reduced capacity | Zero user-facing errors |
| **Provider diversity** | Different failure modes don't correlate | Resilient to vendor issues |

```
Example: OpenAI rate-limited
  openai-gpt4 → Rate limit → Skip
  anthropic-claude → Available → Success ✓
Result: User never sees error
```

##### **2. Cost Optimization**

| Benefit | Description | Savings Potential |
|---------|-------------|-------------------|
| **Per-provider budgets** | Prevent runaway costs | 20-50% cost reduction |
| **Automatic tiering** | Fall to cheaper providers when budget hit | Variable |
| **Usage visibility** | Real-time cost tracking per provider | Better forecasting |

```
Scenario: Primary expensive, secondary cheaper
  openai-gpt4 ($10/hr cap reached) → anthropic-claude ($0.008/1K in)
Result: Requests continue at lower cost
```

##### **3. Operational Intelligence**

| Benefit | Description | Value |
|---------|-------------|-------|
| **Circuit breaker memory** | Learns from failures | Faster recovery |
| **Health probing** | Proactive issue detection | Reduced MTTR |
| **Rich observability** | Per-provider metrics | Data-driven decisions |

```python
status = orchestrator.get_status()
# Returns: circuit states, cost stats, health status, provider order
```

##### **4. Flexibility and Extensibility**

| Benefit | Description | Example |
|---------|-------------|---------|
| **Runtime configuration** | No restarts for changes | Add provider via API |
| **Priority adjustment** | Reorder without code | Promote secondary |
| **Multi-tenant isolation** | Different configs per tenant | Custom provider pools |

##### **5. Testing and Validation**

| Benefit | Description | Implementation |
|---------|-------------|----------------|
| **Deterministic stubs** | Predictable test behavior | `DeterministicStubProvider` |
| **Failure injection** | Test fallback paths | `provider.fail_next = 1` |
| **State inspection** | Verify circuit behavior | `circuit.get_state_dict()` |

---

#### **Disadvantages**

##### **1. Increased Complexity**

| Challenge | Description | Mitigation |
|-----------|-------------|------------|
| **More moving parts** | 3 providers × (circuit + cost + health) = 9 components | Good documentation |
| **State management** | In-memory state lost on restart | Persist to Redis (future) |
| **Configuration burden** | More settings to tune | Sensible defaults |

```
Component count comparison:
  Typical:  1 LLM client
  Cineca:   N providers + N circuit breakers + N cost trackers + orchestrator
```

##### **2. Operational Overhead**

| Challenge | Description | Impact |
|-----------|-------------|--------|
| **Multi-provider contracts** | Maintain N API agreements | Business complexity |
| **Credential management** | N API keys to rotate | Security burden |
| **Billing reconciliation** | Track costs across providers | Accounting complexity |
| **Model parity issues** | Different models ≠ identical outputs | Quality variance |

##### **3. Latency Considerations**

| Challenge | Description | Measurement |
|-----------|-------------|-------------|
| **Pre-flight checks** | Circuit + cost + token checks | ~1-5ms per provider |
| **Fallback delay** | Failed request + next attempt | Full timeout before fallback |
| **Health probes** | Periodic background overhead | Configurable frequency |

```
Worst case latency:
  openai: 30s timeout → fail
  anthropic: 30s timeout → fail
  azure: 30s timeout → fail
Total: 90s before final error
```

##### **4. Consistency Challenges**

| Challenge | Description | Example |
|-----------|-------------|---------|
| **Output variance** | Different providers produce different responses | GPT-4 vs Claude tone |
| **Feature parity** | Not all models support same features | Vision, function calling |
| **Token limits** | Different context windows | 8K vs 100K |

##### **5. Cost Tracking Limitations**

| Limitation | Description | Future Fix |
|------------|-------------|------------|
| **In-memory only** | Lost on restart | Redis persistence |
| **Hardcoded pricing** | Manual updates needed | Admin API |
| **Estimate-based pre-check** | 50/50 split assumption | Historical ratios |
| **No tenant budgets** | Platform-wide caps only | Per-tenant tracking |

---

#### **Trade-off Analysis Matrix**

| Dimension | Simple Retry | Multi-Provider Resilience |
|-----------|--------------|--------------------------|
| **Setup time** | Minutes | Hours |
| **Configuration** | 1 API key | N API keys + priorities + caps |
| **MTTR** | Full outage until provider recovers | Seconds (fallback) |
| **Cost control** | None | Per-provider caps |
| **Team knowledge** | Basic | Must understand circuit breakers |
| **Debugging** | Straightforward | Need to trace multi-provider flow |
| **Testing** | Simple mocks | Stub providers + state verification |

---

#### **When This Strategy Excels**

| Scenario | Why It Works |
|----------|--------------|
| **Mission-critical applications** | Cannot afford downtime |
| **Cost-sensitive deployments** | Need budget enforcement |
| **Multi-tenant platforms** | Isolation and customization |
| **Regulated industries** | Audit trail and compliance |
| **High-scale systems** | Handle rate limits gracefully |

---

#### **When to Use Simpler Approaches**

| Scenario | Why Simpler Is Better |
|----------|----------------------|
| **Prototypes/MVPs** | Velocity over resilience |
| **Single-provider commitment** | No fallback needed |
| **Low traffic** | Rate limits unlikely |
| **Tight budgets** | One provider is cheaper |
| **Small teams** | Less operational overhead |

---

#### **Recommendations for Improvement**

| Area | Current State | Recommendation |
|------|---------------|----------------|
| **State persistence** | In-memory | Redis-backed circuit state |
| **Pricing updates** | Hardcoded | Admin API for pricing table |
| **Tenant budgets** | Global only | Per-tenant cost caps |
| **Alerting** | Metrics only | Prometheus alerting rules |
| **Fallback latency** | Full timeout | Fast-fail with health pre-check |
| **Output consistency** | None | Response normalization layer |

---

#### **Summary Scorecard**

| Criterion | Score (1-5) | Notes |
|-----------|-------------|-------|
| **Reliability** | ⭐⭐⭐⭐⭐ | Excellent fault tolerance |
| **Cost control** | ⭐⭐⭐⭐ | Good, needs persistence |
| **Simplicity** | ⭐⭐ | Complex but well-structured |
| **Observability** | ⭐⭐⭐⭐ | Rich metrics and logging |
| **Extensibility** | ⭐⭐⭐⭐⭐ | Easy to add providers |
| **Operational burden** | ⭐⭐⭐ | Moderate overhead |

**Overall Assessment**: The multi-provider resilience strategy is a **production-grade design** that trades simplicity for reliability and cost control. It is well-suited for enterprise deployments where uptime and budget management are critical, but may be overkill for simpler use cases.

---

## E. Graph (Memgraph) + NL→Cypher (29–35)

---

### 29. Describe the graph data model (nodes, relationships, properties) as implemented for Memgraph, and explain the main use cases it supports.

The Memgraph graph data model in this platform is designed for **bioinformatics workflows** at CINECA, modeling users, organizations, computational tasks, and file artifacts.

#### Node Types (14 Labels)

| Label | Description | Key Properties |
|-------|-------------|----------------|
| **User** | Platform user | `user_id`, `firstName`, `lastName`, `user_name`, `email` |
| **Institution** | Organization/company | `name` |
| **SearchbyTaxon** | Taxonomy search task | `task_id`, `status`, `taxon`, `tool`, `output_fasta` |
| **Bold** | BOLD barcode search task | `task_id`, `status`, `taxon`, `tool`, `output_fasta` |
| **Command** | Generic command task | `task_id`, `status`, `start`, `tags` |
| **Blast** | BLAST sequence search | `task_id`, `blasttype`, `blast_version`, `dbname`, `output_csv` |
| **BlastSeq** | BLAST sequence task | `task_id`, `blasttype`, `blast_version`, `dbname` |
| **CreateDb** | Database creation task | `task_id`, `dbtype`, `dbname` |
| **File** | Generic file artifact | `file_id`, `user_filename`, `size`, `extension`, `bucket_name` |
| **Fasta** | FASTA sequence file | `file_id`, `user_filename`, `size`, `extension` |
| **BlastDb** | BLAST database file | `file_id`, `dbname`, `size` |
| **BlastedSeq** | BLAST result file | `file_id`, `user_filename`, `size` |
| **Xml** | XML output file | `file_id`, `user_filename`, `size` |
| **PhyloTree** | Phylogenetic tree file | `file_id`, `format`, `size` |

#### Relationship Types (4 Core Relationships)

| Type | Pattern | Description |
|------|---------|-------------|
| **WORKS_AT** | `(User)-[:WORKS_AT]->(Institution)` | User employment at organization |
| **RUNS** | `(User)-[:RUNS]->(Task)` | User executes computational task |
| **INPUT** | `(File)-[:INPUT]->(Task)` | File is input to task |
| **OUTPUT** | `(Task)-[:OUTPUT]->(File)` | Task produces output file |

#### Schema Diagram
```
                    ┌─────────────┐
                    │ Institution │
                    └──────▲──────┘
                           │ WORKS_AT
                    ┌──────┴──────┐
                    │    User     │
                    └──────┬──────┘
                           │ RUNS
           ┌───────────────┼────────────────┐
           ▼               ▼                ▼
    ┌─────────────┐ ┌─────────────┐  ┌─────────────┐
    │SearchbyTaxon│ │   Blast     │  │  CreateDb   │
    │    Bold     │ │  BlastSeq   │  │   Command   │
    └──────┬──────┘ └──────┬──────┘  └──────┬──────┘
           │               │                │
    INPUT──┤──OUTPUT INPUT─┤──OUTPUT INPUT──┤──OUTPUT
           ▼               ▼                ▼
    ┌─────────────┐ ┌─────────────┐  ┌─────────────┐
    │   Fasta     │ │ BlastedSeq  │  │  BlastDb    │
    │    File     │ │    File     │  │    File     │
    └─────────────┘ └─────────────┘  └─────────────┘
```

#### Main Use Cases Supported

1. **Data Lineage & Provenance**: Track which user ran which task, what files were inputs, and what outputs were produced—essential for reproducibility in bioinformatics.

2. **Institutional Analytics**: Query patterns like "How many BLAST jobs did CINECA users run?" or "Which institutions collaborate on tasks using shared databases?"

3. **Task Workflow Visualization**: Understand multi-step computational pipelines (e.g., Fasta → Blast → BlastedSeq → downstream analysis).

4. **Data Quality Checks**: Find orphaned nodes (files with no associated task), incomplete tasks, or missing properties.

5. **Natural Language Graph Q&A**: Allow non-technical users to ask questions like "Show 10 random Blast nodes with their outputs" without knowing Cypher.

**Code References**:
- Schema definition: [db/memgraph_domain/README_memgraph_domain.md](db/memgraph_domain/README_memgraph_domain.md#graph-schema)
- Data population: [db/memgraph_domain/populate.py](db/memgraph_domain/populate.py)
- Original dataset: [db/memgraph_domain/original-dataset/](db/memgraph_domain/original-dataset/)

---

### 30. Explain the full NL→Cypher pipeline: from natural language question to generated Cypher to safety checks to execution and summarization.

The NL→Cypher pipeline is a 6-stage process implemented primarily in `graph.secure_query` tool and the orchestrator:

#### Pipeline Stages

```
┌─────────────────────────────────────────────────────────────────────────┐
│  1. INTENT CLASSIFICATION                                               │
│  ─────────────────────────────────────────────────────────────────────  │
│  src/services/intent_classifier.py:classify_intent()                    │
│  • Analyze prompt to determine mode: CHAT, GRAPH, SECURITY, ADMIN,      │
│    DANGEROUS                                                            │
│  • Check prompt catalog for pre-classified matches                      │
│  • Return: mode, confidence score, matched_catalog_id                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  2. CATALOG MATCHING & HINT EXTRACTION                                  │
│  ─────────────────────────────────────────────────────────────────────  │
│  src/services/prompt_catalog.py:match_prompt_by_text()                  │
│  src/memgraph/test_mode.py:get_prompt_hints()                           │
│  • Match normalized prompt text against catalog                         │
│  • Extract hints: limit_hint, random, todo_mode, expected_cypher        │
│  • Apply category-based policies (read_only, admin_write, dangerous)    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  3. CYPHER GENERATION (LLM-powered)                                     │
│  ─────────────────────────────────────────────────────────────────────  │
│  src/mcp/tools/graph/secure_query.py:_generate_cypher_from_nl()         │
│  • Fetch schema context from Memgraph (labels, relationship types)      │
│  • Build system prompt with schema + safety rules                       │
│  • Call LLM with temperature=0.0 for deterministic output               │
│  • Extract clean Cypher (strip markdown formatting)                     │
│  System prompt rules:                                                   │
│    - ONLY generate READ-ONLY queries (MATCH, RETURN, WHERE, WITH)       │
│    - DO NOT use CREATE, MERGE, DELETE, SET, REMOVE, DROP                │
│    - Always parameterize literal values                                 │
│    - Use LIMIT to cap results (default: 100)                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  4. SAFETY VALIDATION                                                   │
│  ─────────────────────────────────────────────────────────────────────  │
│  src/mcp/tools/graph/secure_query.py:_validate_cypher()                 │
│  src/security/graph_access_policy.py:validate_for_principal()           │
│  • Regex-based detection of write operations                            │
│  • Forbidden clause detection (DROP DATABASE, AUTH, KILL, etc.)         │
│  • CALL procedure allowlist enforcement                                 │
│  • Principal permission checks (RBAC)                                   │
│  • Return: {read_only, safe, allowed, checks{write_ops, forbidden}}     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                          ┌─────────┴─────────┐
                          ▼                   ▼
                    [SAFE QUERY]        [BLOCKED QUERY]
                          │                   │
                          │           Return denial reason
                          │           + suggested EXPLAIN rewrite
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  5. QUERY EXECUTION                                                     │
│  ─────────────────────────────────────────────────────────────────────  │
│  src/adapters/db_memgraph.py:query()                                    │
│  • Execute validated Cypher against Memgraph                            │
│  • Apply timeout protection (default: 5000ms)                           │
│  • Apply row limit (default: 1000 rows)                                 │
│  • Collect Prometheus metrics (latency, success/failure)                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  6. RESULT FORMATTING & SUMMARIZATION                                   │
│  ─────────────────────────────────────────────────────────────────────  │
│  src/mcp/tools/graph/secure_query.py:_format_results()                  │
│  src/services/orchestrator.py:_format_memgraph_count_text()             │
│  • Format results: rows, markdown, csv, or json                         │
│  • Generate natural language summary of count queries                   │
│  • Return structured response with cypher, rows, validation info        │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Key Actions in `graph.secure_query` Tool

| Action | Description |
|--------|-------------|
| **ask** | End-to-end: generate → validate → execute → format |
| **generate** | Generate Cypher from NL (without execution) |
| **validate** | Validate Cypher for safety (without execution) |
| **execute** | Execute pre-validated Cypher |

#### Example Flow

```python
# Input
payload = {
    "action": "ask",
    "prompt": "How many Blast nodes are there?",
    "principal": "user@example.org",
    "tenant": "default"
}

# Stage 3: Generated Cypher
cypher = "MATCH (n:Blast) RETURN count(n) AS count"

# Stage 4: Validation
validation = {
    "read_only": True,
    "safe": True,
    "allowed": True,
    "checks": {"write_operations": False, "forbidden_clauses": []}
}

# Stage 5-6: Execution & Response
result = {
    "ok": True,
    "cypher": "MATCH (n:Blast) RETURN count(n) AS count",
    "rows": [{"count": 186}],
    "rowcount": 1,
    "validation": {...}
}
```

**Code References**:
- Main pipeline: [src/mcp/tools/graph/secure_query.py](src/mcp/tools/graph/secure_query.py)
- Orchestrator graph mode: [src/services/orchestrator.py#L2677-2800](src/services/orchestrator.py#L2677)
- Intent classifier: [src/services/intent_classifier.py](src/services/intent_classifier.py)

---

### 31. Describe the "test mode" for NL→Cypher: how prompts are mapped to expected Cypher, and how this is wired into the code for deterministic tests.

The **Memgraph NL Test Mode** is a critical feature that enables deterministic, LLM-independent testing of the NL→Cypher pipeline.

#### Test Mode Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    MEMGRAPH NL TEST MODE                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Environment Variable: LLM_MEMGRAPH_NL_TEST_MODE=true                   │
│  Prompts File: LLM_MEMGRAPH_NL_PROMPTS_PATH (optional)                  │
│  Default: tests/integration/resources/memgraph_nl_prompts.json          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  memgraph_nl_prompts.json (Prompt Catalog)                              │
│  ─────────────────────────────────────────────────────────────────────  │
│  [                                                                      │
│    {                                                                    │
│      "id": "p01",                                                       │
│      "text": "How many :Blast nodes are there?",                        │
│      "category": "read_only",                                           │
│      "allowed_for_user": true,                                          │
│      "allowed_for_admin": true,                                         │
│      "expected_pattern": "MATCH (b:Blast)",                             │
│      "expected_cypher_contains": ["count"],                             │
│      "smoke": true,                                                     │
│      "todo_mode": "optional",                                           │
│      "limit_hint": null,                                                │
│      "random": false                                                    │
│    },                                                                   │
│    ...                                                                  │
│  ]                                                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Catalog Entry Schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique prompt identifier (e.g., "p01", "p03") |
| `text` | string | Natural language prompt text |
| `category` | string | `read_only`, `admin_write`, `dangerous`, `security`, `data_quality` |
| `allowed_for_user` | bool | Whether regular users can execute this |
| `allowed_for_admin` | bool | Whether admins can execute this |
| `expected_pattern` | string | Regex/substring that should appear in generated Cypher |
| `expected_cypher_contains` | list | Required substrings in generated Cypher |
| `smoke` | bool | Whether this is a smoke test (quick validation) |
| `todo_mode` | string | `none`, `optional`, `required` - controls TODO list behavior |
| `limit_hint` | int | Suggested LIMIT value for the query |
| `random` | bool | Whether to add ORDER BY rand() |

#### Code Wiring

**1. Test Mode Detection** ([src/memgraph/test_mode.py](src/memgraph/test_mode.py)):
```python
_TEST_MODE_ENV = "LLM_MEMGRAPH_NL_TEST_MODE"

def _is_enabled() -> bool:
    value = os.getenv(_TEST_MODE_ENV)
    if value is None:
        return True  # Default enabled for integration tests
    return value.strip().lower() in {"1", "true", "yes", "on"}

def get_prompt_hints(prompt: str) -> Optional[Dict[str, Any]]:
    if not _is_enabled():
        return None
    index = _load_prompt_index(prompt_path)
    normalized = _normalize(prompt)
    return index.get(normalized)
```

**2. Prompt Catalog Loading** ([src/services/prompt_catalog.py](src/services/prompt_catalog.py)):
```python
@lru_cache(maxsize=1)
def load_prompt_catalog() -> dict[str, Any]:
    # Index by ID, normalized text, and category
    catalog["by_id"][prompt_id] = prompt
    catalog["by_text_normalized"][normalized] = prompt
    catalog["by_category"][category].append(prompt)

def match_prompt_by_text(text: str, threshold: float = 0.85):
    # Exact match first, then fuzzy matching
    exact_match = catalog["by_text_normalized"].get(normalized)
    if exact_match:
        return exact_match
    return _fuzzy_match(normalized, catalog["all"], threshold)
```

**3. Orchestrator Integration** ([src/services/orchestrator.py](src/services/orchestrator.py)):
```python
# In _classify_intent()
if match_prompt_by_text is not None:
    catalog_match = match_prompt_by_text(goal)
    if catalog_match:
        ctx.vars["matched_catalog_entry"] = catalog_match
        ctx.vars["memgraph_prompt_id"] = catalog_match.get("id")
        
        if get_execution_hints is not None:
            hints = get_execution_hints(catalog_match)
            ctx.vars["memgraph_prompt_limit"] = hints.get("limit_hint")
            ctx.vars["memgraph_prompt_random"] = hints.get("random", False)

# In _enrich_context_with_catalog()
if catalog_entry.get("expected_cypher_contains"):
    ctx.vars["expected_cypher_contains"] = catalog_entry["expected_cypher_contains"]
```

**4. Router Integration** ([src/routers/agent_runs.py](src/routers/agent_runs.py)):
```python
# Extract prompt hints for validation
prompt_hints = get_prompt_hints(prompt)
expected_cypher_contains = prompt_hints.get("expected_cypher_contains", [])

# Validate generated Cypher against expected patterns
test_metadata = {
    "expected_cypher_contains": prompt_hints.get("expected_cypher_contains", []),
    "category": prompt_hints.get("category"),
}
```

#### Benefits of Test Mode

1. **Deterministic Testing**: Tests don't depend on LLM output variability
2. **RBAC Testing**: Pre-defined `allowed_for_user`/`allowed_for_admin` flags
3. **Category-based Policies**: Automatic policy application based on category
4. **Smoke Tests**: Quick validation with `smoke: true` prompts
5. **Execution Hints**: Control query behavior (limits, randomness, TODO mode)

**Code References**:
- Test mode module: [src/memgraph/test_mode.py](src/memgraph/test_mode.py)
- Prompt catalog: [src/services/prompt_catalog.py](src/services/prompt_catalog.py)
- Prompts file: [tests/integration/resources/memgraph_nl_prompts.json](tests/integration/resources/memgraph_nl_prompts.json)

---

### 32. Detail the safety checks applied to Cypher queries (e.g., preventing destructive operations, enforcing tenant boundaries) and where they live in the code.

The platform implements **multi-layer security validation** for Cypher queries:

#### Layer 1: Pattern-Based Detection

**Location**: [src/security/graph_access_policy.py](src/security/graph_access_policy.py)

```python
# Write operations - modify data
WRITE_PATTERNS = re.compile(
    r"\b(CREATE|MERGE|SET|REMOVE)\b", re.IGNORECASE
)

# Delete operations - separate for finer control
DELETE_PATTERNS = re.compile(
    r"\b(DELETE|DETACH\s+DELETE)\b", re.IGNORECASE
)

# Schema/Admin operations - modify database structure
ADMIN_PATTERNS = re.compile(
    r"\b(CREATE\s+INDEX|DROP\s+INDEX|CREATE\s+CONSTRAINT|DROP\s+CONSTRAINT|"
    r"REINDEX|ALTER|CREATE\s+TRIGGER|DROP\s+TRIGGER)\b", re.IGNORECASE
)

# Dangerous operations - always blocked
DANGEROUS_PATTERNS = re.compile(
    r"\b(DROP\s+DATABASE|DROP\s+GRAPH|AUTH|TERMINATE|KILL|SHUTDOWN|"
    r"TRUNCATE|LOAD\s+CSV|COPY\s+FROM|COPY\s+TO)\b", re.IGNORECASE
)

# Heavy operations (potential performance impact)
HEAVY_PATTERNS = re.compile(
    r"(-\[\*\]->|-\[\*\d+\.\.\]->)|"  # Unbounded variable-length paths
    r"\bMATCH\s*\([^)]+\)\s*,\s*\(",  # Cartesian products
    re.IGNORECASE
)
```

#### Layer 2: CALL Procedure Allowlist

**Location**: [src/mcp/tools/graph/secure_query.py](src/mcp/tools/graph/secure_query.py)

```python
# Safe read-only CALL procedures
_CALL_READ_ONLY_PROCS = {
    "db.labels", "db.relationshipTypes", "db.propertyKeys",
    "db.indexes", "db.constraints", "db.info", "db.stats",
    "show_labels", "show_relationship_types", "show_property_keys",
}

# Blocked CALL procedures (write semantics)
_WRITE_PAT = re.compile(
    r"CALL\s+("
    r"db\.create|db\.alter|db\.drop|db\.execute|db\.set|db\.delete|"
    r"db\.add|db\.remove|db\.update|db\.insert|db\.merge|"
    r"apoc\.create|apoc\.merge|apoc\.set|apoc\.refactor"
    r")", re.IGNORECASE
)
```

#### Layer 3: Validation Result Structure

**Location**: [src/security/graph_access_policy.py](src/security/graph_access_policy.py)

```python
@dataclass
class CypherValidation:
    is_safe: bool           # Can query be executed?
    is_read_only: bool      # No write operations?
    has_writes: bool        # CREATE/MERGE/SET/REMOVE detected?
    has_deletes: bool       # DELETE/DETACH DELETE detected?
    requires_admin: bool    # Schema/admin operations?
    is_dangerous: bool      # Explicitly dangerous?
    is_heavy: bool          # Potentially expensive?
    blocked_clauses: list[str]
    suggested_rewrite: str | None  # e.g., "EXPLAIN ..."
    denial_reason: str | None
```

#### Layer 4: Principal-Based RBAC

**Location**: [src/security/graph_access_policy.py](src/security/graph_access_policy.py)

```python
class GraphAccessPolicy:
    def validate_for_principal(self, cypher, principal, tenant_id):
        validation = self.validate_cypher(cypher)
        
        is_admin = self._is_admin(principal)
        has_write_perm = self._has_write_permission(principal)
        
        # Adjust safety based on permissions
        if validation.is_dangerous:
            if self.strict_mode:
                validation.is_safe = False
            else:
                validation.is_safe = is_admin
        
        if validation.requires_admin and not is_admin:
            validation.is_safe = False
            validation.denial_reason = "Admin privileges required"
```

#### Layer 5: Permission Checks in secure_query Tool

**Location**: [src/mcp/tools/graph/secure_query.py](src/mcp/tools/graph/secure_query.py)

```python
def _check_permissions(principal, tenant, action) -> dict:
    scopes = _extract_scopes(principal)
    perms = current_permissions(principal)
    role = infer_role_from_principal(principal)
    
    allowed = False
    if not tenant:
        allowed = False
    elif isinstance(principal, dict) and principal.get("rbac_enforced") is False:
        allowed = True  # RBAC bypass for testing
    elif "admin:all" in perms or role == "admin":
        allowed = True
    elif any(tok in perms for tok in ("tools:all", "tools:basic")):
        allowed = True
    
    return {"allowed": allowed, "role": role, "permissions": sorted(perms)}
```

#### Layer 6: Tenant Scoping

**Location**: [src/mcp/tools/graph/secure_query.py](src/mcp/tools/graph/secure_query.py)

```python
def _validate_cypher(cypher: str, tenant: str) -> dict:
    # Tenant scoping check (heuristic)
    tenant_scoped = True  # Assume queries will be scoped at execution time
    
    return {
        "read_only": not has_writes,
        "safe": is_safe,
        "checks": {
            "write_operations": has_writes,
            "forbidden_clauses": forbidden_clauses,
            "tenant_scoped": tenant_scoped,
        }
    }
```

#### Safety Check Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CYPHER SAFETY VALIDATION                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Input: "MATCH (n:User) RETURN n"                                       │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Pattern Detection                                               │    │
│  │ • WRITE_PATTERNS → false                                        │    │
│  │ • DELETE_PATTERNS → false                                       │    │
│  │ • ADMIN_PATTERNS → false                                        │    │
│  │ • DANGEROUS_PATTERNS → false                                    │    │
│  │ • HEAVY_PATTERNS → false                                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                           │                                             │
│                           ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ CALL Procedure Check                                            │    │
│  │ • In _CALL_READ_ONLY_PROCS? → N/A (no CALL)                     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                           │                                             │
│                           ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Principal RBAC Check                                            │    │
│  │ • Role: "user"                                                  │    │
│  │ • Permissions: ["tools:basic"]                                  │    │
│  │ • is_read_only=true → ALLOWED                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                           │                                             │
│                           ▼                                             │
│  Result: {is_safe: true, is_read_only: true, allowed: true}             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Input: "DROP DATABASE mydb"                                            │
│                                                                         │
│  • DANGEROUS_PATTERNS → true ("DROP DATABASE")                          │
│  • Result: {is_safe: false, is_dangerous: true}                         │
│  • denial_reason: "Query contains dangerous operations"                 │
│  • suggested_rewrite: "EXPLAIN DROP DATABASE mydb"                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Code References**:
- Graph access policy: [src/security/graph_access_policy.py](src/security/graph_access_policy.py)
- Secure query validation: [src/mcp/tools/graph/secure_query.py#L200-250](src/mcp/tools/graph/secure_query.py#L200)
- Query tool validation: [src/mcp/tools/graph/query.py#L70-90](src/mcp/tools/graph/query.py#L70)

---

### 33. From the code, identify the main advantages of the graph integration compared to a typical RAG-only approach.

Based on the codebase analysis, the graph integration provides several significant advantages over traditional RAG approaches:

#### 1. **Structured Relational Queries**

| Aspect | Graph Integration | RAG-Only |
|--------|------------------|----------|
| **Query Type** | Cypher with explicit relationships | Vector similarity search |
| **Precision** | Exact pattern matching on graph structure | Approximate nearest neighbor |
| **Reasoning** | Multi-hop traversals (`User→RUNS→Blast→OUTPUT→File`) | Single-hop semantic retrieval |

**Code Evidence** ([db/memgraph_domain/sample_queries.txt](db/memgraph_domain/sample_queries.txt)):
```cypher
-- Multi-hop query impossible with RAG
MATCH (u:User)-[:RUNS]->(t:Blast)-[:OUTPUT]->(f:BlastedSeq)
WHERE t.blasttype = 'blastn'
RETURN u.user_name, t.task_id, f.user_filename
```

#### 2. **Schema-Aware Query Generation**

**Code Evidence** ([src/mcp/tools/graph/secure_query.py#L320-340](src/mcp/tools/graph/secure_query.py)):
```python
# NL→Cypher generation includes schema context
labels_result = db.query("CALL show_labels() YIELD label RETURN collect(label) AS labels")
rel_types_result = db.query("CALL show_relationship_types() YIELD type RETURN collect(type) AS types")

system_prompt = f"""...
Available node labels: {', '.join(labels)}
Available relationship types: {', '.join(rel_types)}
"""
```

This schema awareness prevents hallucinated entity names and ensures valid Cypher.

#### 3. **Aggregation & Analytics**

**Code Evidence** ([tests/integration/resources/memgraph_nl_prompts.json](tests/integration/resources/memgraph_nl_prompts.json)):
```json
{
  "text": "Count :Blast nodes grouped by presence of `blast_version`",
  "expected_cypher_contains": ["blast_version", "count"]
},
{
  "text": "Return the top 10 :BlastedSeq with the most inbound :OUTPUT from :Blast",
  "expected_cypher_contains": ["count", "ORDER BY", "LIMIT"]
}
```

Graph databases excel at aggregations that RAG cannot perform (counts, rankings, groupings).

#### 4. **Data Lineage & Provenance**

The graph schema explicitly captures computational provenance:
- `(User)-[:RUNS]->(Task)` - Who ran what
- `(File)-[:INPUT]->(Task)` - What inputs were used  
- `(Task)-[:OUTPUT]->(File)` - What outputs were produced

**Code Evidence** ([db/memgraph_domain/README_memgraph_domain.md](db/memgraph_domain/README_memgraph_domain.md)):
```
User ──[:WORKS_AT]──► Institution
User ──[:RUNS]──────► <Task>
<Task>─[:INPUT]─────► {Fasta | File | BlastDb}
<Task>─[:OUTPUT]────► {File | BlastedSeq | Fasta | Xml | BlastDb}
```

#### 5. **Data Quality Checks**

**Code Evidence** ([tests/integration/resources/memgraph_nl_prompts.json](tests/integration/resources/memgraph_nl_prompts.json)):
```json
{
  "text": "Show 10 :Blast with no outgoing :OUTPUT edges (possible data issue)",
  "category": "read_only",
  "expected_cypher_contains": ["WHERE NOT", "LIMIT"]
}
```

Graph queries can find structural anomalies (orphaned nodes, missing relationships) that RAG cannot detect.

#### 6. **Deterministic, Auditable Execution**

| Feature | Graph Integration | RAG-Only |
|---------|------------------|----------|
| **Generated Query** | Visible Cypher statement | Hidden embedding lookup |
| **Reproducibility** | Same Cypher → same results | Embedding drift over time |
| **Auditability** | Full query logged | Black-box retrieval |
| **Safety Validation** | Regex + RBAC on Cypher | None |

**Code Evidence** ([src/mcp/tools/graph/secure_query.py#L500-520](src/mcp/tools/graph/secure_query.py)):
```python
# Result includes both generated Cypher and validation
return {
    "ok": True,
    "prompt": prompt,
    "cypher": cypher,  # Fully auditable
    "validation": validation,  # Security checks documented
    "rows": formatted_rows,
}
```

#### 7. **RBAC-Controlled Access**

Different operations require different permissions:
- `read_only` queries: `tools:basic` scope
- `admin_write` queries: `admin` role required
- `dangerous` queries: Always blocked or EXPLAIN-only

**Code Evidence** ([src/services/prompt_catalog.py#L309-335](src/services/prompt_catalog.py)):
```python
policies = {
    "read_only": {"requires_admin": False, "allow_execution": True},
    "admin_write": {"requires_admin": True, "allow_execution": True},
    "dangerous": {"requires_admin": True, "allow_execution": False, "suggest_explain": True},
}
```

#### Summary Comparison

| Capability | Graph (Memgraph) | RAG |
|------------|-----------------|-----|
| Multi-hop relationships | ✅ Native | ❌ Requires chunking hacks |
| Exact counts/aggregations | ✅ Cypher | ❌ Approximations only |
| Schema validation | ✅ At generation time | ❌ No schema awareness |
| Data lineage | ✅ First-class relationships | ❌ Flat document chunks |
| Audit trail | ✅ Full Cypher logged | ❌ Opaque embeddings |
| Security validation | ✅ Pattern + RBAC | ❌ None |
| Performance on complex queries | ✅ Index-backed | ❌ O(n) similarity search |

---

### 34. Identify possible risks or weaknesses of the NL→Cypher approach (e.g., complexity, maintainability, test burden, potential escape routes).

#### 1. **Injection Risks Despite Validation**

**Risk**: Regex-based safety checks can be bypassed with creative payloads.

**Code Evidence** ([src/mcp/tools/graph/secure_query.py#L187-195](src/mcp/tools/graph/secure_query.py)):
```python
# Pattern-based detection is heuristic, not formal parsing
_WRITE_PAT = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|...)\b",
    re.IGNORECASE
)
```

**Potential Bypass**: Unicode lookalikes, comment injection, or novel Memgraph-specific syntax not covered by patterns.

**Mitigation in Code**: The platform uses multiple layers (pattern + allowlist + RBAC), but formal Cypher parsing would be safer.

#### 2. **LLM Hallucination of Invalid Cypher**

**Risk**: LLM may generate syntactically valid but semantically incorrect queries.

**Code Evidence** ([src/mcp/tools/graph/secure_query.py#L300-320](src/mcp/tools/graph/secure_query.py)):
```python
# LLM generates Cypher based on schema hints only
system_prompt = f"""...
Available node labels: {', '.join(labels)}
...
Generate ONLY the Cypher query, nothing else.
"""
```

**Examples of Hallucination**:
- Referencing non-existent labels (e.g., `MATCH (n:Users)` instead of `(n:User)`)
- Inventing relationship types (e.g., `[:CREATES]` instead of `[:OUTPUT]`)
- Incorrect property names

**Mitigation**: Schema context helps, but there's no compile-time validation.

#### 3. **Maintenance Burden of Prompt Catalog**

**Risk**: The catalog requires manual updates for new prompt patterns.

**Code Evidence** ([tests/integration/resources/memgraph_nl_prompts.json](tests/integration/resources/memgraph_nl_prompts.json)):
```json
// 35+ prompts, each requiring:
{
  "id": "p28",
  "text": "Set default value `blast_version='N/A'` for :Blast where missing.",
  "category": "admin_write",
  "expected_pattern": "SET",
  "expected_cypher_contains": ["SET", "blast_version"]
}
```

Every new query type needs manual catalog entry, including expected patterns.

#### 4. **Fuzzy Matching Brittleness**

**Risk**: Prompt matching relies on text normalization and Jaccard similarity.

**Code Evidence** ([src/services/prompt_catalog.py#L200-230](src/services/prompt_catalog.py)):
```python
def _similarity_score(s1: str, s2: str) -> float:
    words1 = set(s1.split())
    words2 = set(s2.split())
    return len(words1 & words2) / len(words1 | words2)  # Jaccard
```

**Problem**: Minor rephrasing can break matching:
- "How many Blast nodes?" ✓
- "What's the count of Blast nodes?" ✗ (may not match)

#### 5. **Test Mode Dependency**

**Risk**: Production behavior differs from test mode.

**Code Evidence** ([src/memgraph/test_mode.py#L19-22](src/memgraph/test_mode.py)):
```python
def _is_enabled() -> bool:
    value = os.getenv(_TEST_MODE_ENV)
    if value is None:
        return True  # Default enabled!
```

Test mode is **enabled by default**, meaning production needs explicit `LLM_MEMGRAPH_NL_TEST_MODE=false`.

#### 6. **Limited Error Recovery**

**Risk**: Failed Cypher generation has limited fallback options.

**Code Evidence** ([src/services/orchestrator.py#L2760-2770](src/services/orchestrator.py)):
```python
except Exception as e:
    log.warning("orchestrator.graph_mode.generate_failed", error=str(e))
    self._tool_errors += 1
    
if not cypher:
    # Fallback to existing pipeline (less optimized)
    return await self._fallback_to_standard_pipeline(goal, ctx, result)
```

Fallback exists but may produce suboptimal results.

#### 7. **Timeout and Performance Risks**

**Risk**: Complex NL→Cypher can generate expensive queries.

**Code Evidence** ([src/mcp/tools/graph/secure_query.py#L505-510](src/mcp/tools/graph/secure_query.py)):
```python
# Default timeout is 5 seconds
timeout_ms = int(payload.get("timeout_ms") or 5000)
max_rows = int(payload.get("max_rows") or 1000)
```

**Problem**: Heavy operations pattern detection may miss novel expensive patterns.

#### 8. **No Formal Cypher Parser**

**Risk**: All validation is regex-based, not AST-based.

**Consequence**: 
- Can't detect semantic issues (e.g., cartesian products in complex queries)
- Novel Cypher syntax may bypass patterns
- No compile-time validation

#### Risk Summary Table

| Risk | Severity | Mitigation in Code | Residual Risk |
|------|----------|-------------------|---------------|
| Injection bypass | High | Multi-layer patterns | Medium - no formal parser |
| LLM hallucination | Medium | Schema context | Medium - no compile-time check |
| Catalog maintenance | Medium | Fuzzy matching | High - manual updates needed |
| Fuzzy match brittleness | Medium | Threshold tuning | Medium - rephrasing breaks |
| Test mode confusion | Low | Explicit env var | Low |
| Error recovery | Medium | Fallback pipeline | Low |
| Performance | Medium | Timeout + row limit | Medium |
| No formal parser | High | Regex patterns | High |

---

### 35. Compare this graph integration with what is typically seen in SOTA agentic or RAG frameworks, and summarize where this project is stronger or weaker.

#### Comparison Matrix

| Feature | This Project (Cineca) | LangChain GraphCypherQAChain | LlamaIndex KnowledgeGraphIndex | Neo4j + LangGraph |
|---------|----------------------|------------------------------|--------------------------------|-------------------|
| **NL→Cypher Generation** | LLM with schema context | LLM with schema | LLM with schema | LLM with schema |
| **Safety Validation** | ✅ Multi-layer (regex + RBAC + allowlist) | ⚠️ Basic prompt injection check | ❌ None | ⚠️ Basic |
| **Test Mode (Deterministic)** | ✅ Full prompt catalog + hints | ❌ No | ❌ No | ❌ No |
| **Intent Classification** | ✅ 5 modes (CHAT/GRAPH/ADMIN/SECURITY/DANGEROUS) | ⚠️ Binary (graph/not) | ❌ Always graph | ⚠️ Agent routing |
| **RBAC Integration** | ✅ Per-query, per-tool permissions | ❌ No | ❌ No | ⚠️ Limited |
| **Audit Trail** | ✅ Full query + principal + tenant logging | ⚠️ Basic logging | ⚠️ Basic logging | ⚠️ Varies |
| **Multi-tenancy** | ✅ Native tenant_id scoping | ❌ No | ❌ No | ⚠️ Custom impl |
| **Suggested Rewrites** | ✅ EXPLAIN suggestions for blocked queries | ❌ No | ❌ No | ❌ No |
| **Fallback Handling** | ✅ Graceful degradation to chat mode | ⚠️ Error propagation | ⚠️ Error propagation | ⚠️ Varies |
| **Prometheus Metrics** | ✅ Full (latency, errors, counts) | ❌ No | ❌ No | ⚠️ Custom |
| **Schema Discovery** | ✅ Runtime schema fetch | ✅ Yes | ✅ Yes | ✅ Yes |

#### Where This Project is **Stronger**

##### 1. Security Architecture
```
This Project:
┌──────────────────────────────────────────────────────────────────────────┐
│ 6 Security Layers                                                        │
│ • Pattern detection (regex)                                              │
│ • CALL procedure allowlist                                               │
│ • Principal RBAC                                                         │
│ • Tenant scoping                                                         │
│ • Suggested rewrites                                                     │
│ • Audit logging                                                          │
└──────────────────────────────────────────────────────────────────────────┘

LangChain GraphCypherQAChain:
┌──────────────────────────────────────────────────────────────────────────┐
│ 1 Security Layer                                                         │
│ • Prompt-level injection warning only                                    │
└──────────────────────────────────────────────────────────────────────────┘
```

##### 2. Deterministic Testing Infrastructure

**Code Evidence**: Full prompt catalog with 35+ entries, each with:
- Expected Cypher patterns
- Category-based policies
- RBAC expectations
- Smoke test flags

No SOTA framework provides equivalent test mode infrastructure.

##### 3. Intent-Based Routing

The 5-mode classification (CHAT/GRAPH/ADMIN/SECURITY/DANGEROUS) with confidence scores is more sophisticated than binary routing in most frameworks.

##### 4. Production Observability

Full Prometheus metrics integration:
```python
DB_QUERIES = Counter("db_memgraph_queries_total", ...)
DB_LATENCY = Histogram("db_memgraph_query_latency_seconds", ...)
```

#### Where This Project is **Weaker**

##### 1. No Formal Cypher Parser

**Industry Standard**: Neo4j's Cypher parser provides AST-level validation.

**This Project**: Regex-only, which can miss edge cases.

```python
# Current approach (regex)
_WRITE_PAT = re.compile(r"\b(CREATE|MERGE|DELETE|...)\b")

# Better approach (not implemented)
from neo4j_cypher_parser import parse
ast = parse(cypher)
if has_write_clause(ast):
    block()
```

##### 2. Limited Graph Algorithms

**LlamaIndex**: Built-in graph algorithms (PageRank, community detection).

**This Project**: Raw Cypher only—no native algorithm support.

##### 3. No Vector Hybrid Search

**Neo4j + LangChain**: Supports hybrid vector + graph queries.

**This Project**: Pure graph, no vector embedding integration.

```python
# Industry pattern (not in this project)
MATCH (n:Document)
WHERE n.embedding <-> $query_embedding < 0.5
RETURN n
```

##### 4. Limited Multi-Graph Support

**LlamaIndex**: Can query across multiple knowledge graphs.

**This Project**: Single Memgraph instance assumption.

##### 5. No Query Caching

**Production frameworks**: Often include query result caching.

**This Project**: Each query hits Memgraph directly.

#### Summary: Competitive Position

| Area | Position | Notes |
|------|----------|-------|
| **Security** | 🥇 Industry-leading | Multi-layer validation + RBAC |
| **Testing** | 🥇 Industry-leading | Full deterministic test mode |
| **Observability** | 🥇 Production-ready | Prometheus + audit logging |
| **Intent Classification** | 🥈 Strong | 5-mode classification |
| **Query Generation** | 🥈 Competitive | Schema-aware LLM |
| **Formal Parsing** | 🥉 Weak | Regex-only |
| **Hybrid Search** | 🥉 Missing | No vector integration |
| **Graph Algorithms** | 🥉 Missing | No built-in algos |

#### Conclusion

This project excels in **enterprise security and testability** but lags in **advanced graph features** (algorithms, hybrid search). It's well-suited for production deployments where **security and compliance** are paramount, but would benefit from:
1. Formal Cypher parser integration
2. Vector embedding hybrid search
3. Query result caching
4. Built-in graph algorithm support

The security-first design makes it more production-ready than most SOTA frameworks, which prioritize features over safety.

#### Appendix: Full comparison document (comparison.md)

# Cineca Agentic Platform — Comparison with MCP, GitHub MCP Server, mcp-neo4j, LangChain GraphCypherQAChain, LlamaIndex KnowledgeGraphIndex, and Neo4j + LangGraph

> **Purpose**: An honest, straightforward comparison to help you decide when to use the **Cineca Agentic Platform** vs. composing other standards/libraries/servers.
>
> **Sources used**:
> - This repository’s [README.md](README.md)
> - MCP documentation (intro + server/tools specification)
> - GitHub MCP Server repository documentation
> - neo4j-contrib/mcp-neo4j repository documentation (cypher/memory/cloud-aura-api/data-modeling servers)
> - LangChain GraphCypherQAChain (Python + JS docs)
> - LlamaIndex KnowledgeGraphIndex (examples + API reference)
> - LangGraph overview documentation
>
> **Important framing**: Several items in this comparison are not “competing platforms”:
> - **MCP** is a protocol/spec.
> - **GitHub MCP Server** and **mcp-neo4j** are MCP servers (tool providers).
> - **LangChain GraphCypherQAChain**, **LlamaIndex KnowledgeGraphIndex**, and **LangGraph** are libraries/frameworks.
> - **Neo4j + LangGraph** is an integration pattern (a way to build a system).

---

## Quick takeaway

- Choose **Cineca Agentic Platform** if you want a **production-oriented backend platform** with: multi-tenancy, RBAC, audit trails, rate limiting, job workers + SSE streaming, observability, and a curated “tool runtime” and graph pipeline.
- Choose **MCP servers** (GitHub MCP Server / mcp-neo4j) if you mainly need **standard MCP tool access** from an MCP-capable client (e.g., Claude Desktop / IDE integrations) and don’t want to run a whole application platform.
- Choose **LangChain/LlamaIndex** if you’re building a **Python app** and you want to assemble components quickly, accepting that you must design security/ops/governance yourself.
- Choose **LangGraph** if your primary problem is **stateful orchestration** (durable execution, interruptions/human oversight, long-running graphs) and you want a low-level orchestration runtime.

---

## What each thing “is” (scope and intent)

| Item | Category | Primary goal | What it is *not* |
|---|---|---|---|
| Cineca Agentic Platform | Full-stack backend platform | Run and govern agent workflows (API + jobs + tools + graph + security + observability + UIs) | Not a drop-in MCP server for arbitrary MCP clients (unless you add an MCP transport surface) |
| MCP (spec/docs) | Protocol specification | Standardize how an AI client talks to tool servers (discovery + invocation) | Not an implementation, not a workflow engine |
| GitHub MCP Server | MCP server implementation | Expose GitHub operations as MCP tools | Not a multi-tenant agent platform, not a general workflow runtime |
| neo4j-contrib/mcp-neo4j | MCP server suite | Expose Neo4j Cypher, memory, Aura mgmt, and data modeling as MCP tools | Not a full agent platform, not an orchestration framework |
| LangChain GraphCypherQAChain | Library component | NL→Cypher→execute→answer loop for Neo4j | Not a platform; governance/tenancy/ops are on you |
| LlamaIndex KnowledgeGraphIndex | Library index | Build/query a knowledge graph index from documents (triplets) | Not a DB-backed graph analytics platform by itself |
| Neo4j + LangGraph | Architecture pattern | Use Neo4j for graph storage + LangGraph for orchestration | Not a single product; you assemble and operate it |

---

## High-level feature matrix

Legend: ✅ built-in / explicit feature; ⚪ possible but you implement it; ❌ not in scope.

| Capability area | Cineca | MCP spec | GitHub MCP Server | mcp-neo4j | LangChain GraphCypherQAChain | LlamaIndex KG Index | Neo4j + LangGraph |
|---|---:|---:|---:|---:|---:|---:|---:|
| Production backend API (HTTP, versioning, error envelope) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ⚪ |
| Multi-tenancy as first-class concept | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ⚪ |
| RBAC/scopes enforced centrally | ✅ | ⚪ (recommended) | ⚪ (toolset scoping / modes) | ⚪ (server config patterns) | ❌ | ❌ | ⚪ |
| Audit logging (runs/steps/tools) | ✅ | ⚪ (recommended) | ⚪ | ⚪ | ❌ | ❌ | ⚪ |
| Rate limiting | ✅ | ⚪ (recommended) | ⚪ (platform limits / modes) | ⚪ (server hardening exists; rate limits typically external) | ❌ | ❌ | ⚪ |
| Background jobs + worker processes | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ⚪ |
| Streaming progress to UI (SSE) | ✅ | ⚪ (transport exists; not required) | ⚪ (varies by client/transport) | ✅ (SSE/HTTP transports) | ❌ | ❌ | ⚪ |
| Built-in UIs | ✅ (Next.js + Streamlit) | ❌ | ❌ | ❌ | ❌ | ❌ | ⚪ |
| Graph DB integration | ✅ (Memgraph) | ❌ | ❌ | ✅ (Neo4j) | ✅ (Neo4j) | ⚪ (graph store / extracted triplets) | ✅ (Neo4j) |
| “NL→Cypher” pipeline | ✅ (explicit pipeline + safety validation) | ❌ | ❌ | ✅ (Cypher tools, schema tools) | ✅ (chain) | ❌ (triplet KG approach) | ⚪ (you build it) |
| MCP tool protocol compatibility | ⚪ (MCP-style tools; not necessarily MCP JSON-RPC server) | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Observability (metrics/tracing/health) | ✅ | ❌ | ⚪ | ⚪ | ⚪ (via LangSmith / your tracing) | ⚪ | ⚪ |

---

## Comparison details (differences, advantages, disadvantages)

### 1) Cineca Agentic Platform vs. MCP (spec/docs)

**Core difference**
- MCP defines **how a client and a tool server talk** (tool discovery + tool calling, schemas, results, error conventions, and security considerations).
- Cineca is a **complete application platform** that includes an internal tool runtime, orchestration, persistence, security middleware, and UIs.

**Advantages of Cineca (relative to “just MCP”)**
- Provides the things MCP intentionally does not: API surface, orchestration, job processing, tenancy, RBAC, audit trails, observability, UI(s).
- Centralizes governance (authn/authz, rate limits, logging) around tool execution and agent runs.

**Disadvantages / gaps (relative to MCP)**
- If you need out-of-the-box compatibility with the MCP JSON-RPC server surface (`tools/list`, `tools/call`, etc.), Cineca’s “MCP-style” tool router is not the same thing as an MCP server unless you explicitly implement MCP transport/protocol.
- MCP’s output model supports multiple content block types and structured content; Cineca has its own tool invocation request/response contracts.

**When MCP wins**
- You want a minimal standards-based “tool server” to plug into many MCP clients.

**When Cineca wins**
- You want a platform that runs the entire workflow end-to-end (auth, orchestration, persistence, safety, ops).

---

### 2) Cineca Agentic Platform vs. GitHub MCP Server

**Core difference**
- GitHub MCP Server is a **tool provider**: it exposes GitHub operations (issues, PRs, repos, etc.) over MCP.
- Cineca is a **platform** that can host many tool families (including GitHub-like tools if implemented) and run multi-step agent workflows.

**Advantages of Cineca**
- Platform features: multi-tenancy, centralized RBAC, job system + SSE, observability stack, UIs.
- Not tied to a single external system.

**Advantages of GitHub MCP Server**
- Standard MCP compatibility: designed to be used by MCP clients directly.
- Domain depth: purpose-built toolsets around GitHub.
- Operational safety modes are emphasized (e.g., read-only / lockdown patterns).

**Disadvantages of Cineca (relative to GitHub MCP Server)**
- Cineca does not inherently provide GitHub’s domain-specific toolset; you must implement/maintain those tools.
- If you specifically need MCP client compatibility for GitHub automation, GitHub MCP Server is closer to the goal.

**Disadvantages of GitHub MCP Server (relative to Cineca)**
- Not a general orchestration platform: it won’t give you multi-tenant workflow persistence, jobs, or UI.

---

### 3) Cineca Agentic Platform vs. neo4j-contrib/mcp-neo4j (cypher/memory/cloud-aura-api/data-modeling)

**Core difference**
- mcp-neo4j is a set of **Neo4j-focused MCP servers** with well-defined tools (Cypher read/write/schema, graph memory tools, Aura management tools, data modeling tools), designed to connect to MCP clients.
- Cineca implements a **graph domain and NL→Cypher pipeline** against **Memgraph**, embedded within a larger governance/ops platform.

**Advantages of Cineca**
- “Platform” layer: tenancy, RBAC across the whole system, audit logging for runs/steps/tools, rate limiting, worker jobs, SSE streaming, health/metrics/tracing, UIs.
- Opinionated workflow model: persisted agent runs/steps; orchestration service; structured error handling.

**Advantages of mcp-neo4j**
- Neo4j-native focus and ecosystem fit (Neo4j Aura, Neo4j schema tooling, Neo4j memory conventions).
- True MCP server surfaces (stdio/SSE/HTTP), meaning MCP clients can connect without a custom adapter.
- Separate servers for distinct responsibilities (Cypher vs memory vs Aura vs modeling), which can be operationally cleaner if you only need one slice.

**Disadvantages / trade-offs**
- Cineca uses **Memgraph**, not Neo4j. If Neo4j-specific features (Aura, APOC, enterprise features, specific query behaviors) matter, mcp-neo4j aligns better.
- mcp-neo4j does not provide Cineca’s broader platform components (multi-tenancy control plane, job system, UIs) out of the box.

---

### 4) Cineca Agentic Platform vs. LangChain GraphCypherQAChain

**Core difference**
- GraphCypherQAChain is a **library chain** that generates Cypher from natural language and executes it against Neo4j, returning an answer.
- Cineca is a **service-backed platform** with a graph pipeline, tool registry, persistence, and cross-cutting security/observability.

**Advantages of Cineca**
- Central governance: authn/authz, rate limiting, auditability, persisted runs/steps, and a job system.
- A broader tool ecosystem beyond graph Q&A.
- Production “platform” defaults (health probes, metrics, tracing, structured logs).

**Advantages of GraphCypherQAChain**
- Very fast to integrate into an existing Python/LangChain app.
- Strong alignment with Neo4j; built around schema-aware generation.

**Important security note (GraphCypherQAChain)**
- The LangChain docs explicitly warn that generating and executing Cypher can be dangerous and recommend narrowly scoped database credentials; examples show an explicit flag (`allow_dangerous_requests=True`) to acknowledge this risk.

**Disadvantages of Cineca (relative to GraphCypherQAChain)**
- If you only need a small in-process component, Cineca can feel heavier than a single chain.

**Disadvantages of GraphCypherQAChain (relative to Cineca)**
- No built-in multi-tenancy, RBAC, auditing, rate limiting, job processing, or ops stack.

---

### 5) Cineca Agentic Platform vs. LlamaIndex KnowledgeGraphIndex

**Core difference**
- KnowledgeGraphIndex focuses on **extracting and querying triplets** (subject–predicate–object) from documents as an index.
- Cineca focuses on **runtime agent workflows** and graph query pipelines (Memgraph + NL→Cypher), within a platform.

**Advantages of Cineca**
- Better fit when you need operational workflows: multi-step orchestration, tool execution, governance, and a managed API.
- Suited for “graph as a database” use cases (CRUD/analytics/queries) rather than only building an extracted KG index.

**Advantages of KnowledgeGraphIndex**
- Great for document-centric knowledge graph extraction and retrieval.
- Can be easier to prototype locally; integrates with LlamaIndex query engines.
- Supports manual triplet insertion APIs and optional embeddings.

**Disadvantages / trade-offs**
- Cineca is not primarily an “offline KG indexing” library; it’s an online platform.
- KnowledgeGraphIndex does not provide the full platform runtime characteristics (auth/RBAC/jobs/ops) without additional engineering.

---

### 6) Cineca Agentic Platform vs. Neo4j + LangGraph

**Core difference**
- Neo4j + LangGraph is a **build-it-yourself architecture**: Neo4j for graph storage/query, LangGraph for stateful orchestration.
- Cineca is a **pre-integrated platform** with a specific stack (Memgraph + FastAPI + Postgres + Redis + workers) and built-in governance and UIs.

**What LangGraph brings (as documented)**
- A low-level orchestration framework/runtime for long-running stateful workflows/agents.
- Emphasis on durable execution (resume after failure), human-in-the-loop interruptions, memory, and debugging/visibility via LangSmith.

**Advantages of Cineca**
- You get a coherent, end-to-end system (API + persistence + governance + ops) without assembling many moving parts.

**Advantages of Neo4j + LangGraph**
- You pick best-of-breed components for your needs (Neo4j features + LangGraph orchestration model).
- You can implement true MCP servers alongside it if MCP interoperability is a hard requirement.

**Trade-offs**
- Neo4j + LangGraph requires you to design and maintain: auth/RBAC/tenancy boundaries, auditing, rate limiting, deployment topology, observability, and UI.
- Cineca’s orchestration model may be “less LangGraph-native” (e.g., LangGraph-specific interruption semantics and tooling), while Cineca is stronger in “platform operations” out of the box.

---

## Decision guide (practical recommendations)

| If you need… | Prefer |
|---|---|
| An end-to-end multi-tenant agent backend (API + governance + ops) | Cineca Agentic Platform |
| MCP compatibility for tool access from many clients | GitHub MCP Server / mcp-neo4j / other MCP servers |
| Neo4j-specific tool suite via MCP (Cypher/memory/Aura/modeling) | mcp-neo4j |
| A simple in-app NL→Cypher Q&A feature against Neo4j | LangChain GraphCypherQAChain |
| Document-centric KG extraction + retrieval | LlamaIndex KnowledgeGraphIndex |
| Long-running stateful orchestrations with durable execution + human-in-loop | LangGraph (often with your own persistence/ops) |

---

## Notes on “MCP compliance” terminology

This repository’s backend exposes a REST-style Tools API described as a “generic MCP-style dispatcher” (discovery + invocation) and the README describes tools executed “via MCP (Model Context Protocol)”. MCP the standard is JSON-RPC-based and defines `tools/list` and `tools/call` semantics.

If strict MCP interoperability is a requirement (i.e., plugging into MCP clients without a custom adapter), treat Cineca’s current tool surface as **MCP-inspired** rather than a drop-in MCP server unless you have implemented an MCP transport/protocol layer.


---
## F. Agents, tools, jobs & background framework (36–41)

---

### 36. Internal Structure of an "Agent Run"

36. **Explain the internal structure of an “agent run”**: how runs, sessions, steps, TODOs, tool calls, and metrics are represented and persisted.

An agent run represents a single execution/invocation of an agent. The platform uses a hierarchical model: **Sessions → Runs → Steps**, with TODOs, tool calls, and metrics tracked throughout.

#### 36.1 Data Model Hierarchy

```
AgentSession (stateful container)
    └── AgentRun (single execution)
            ├── Steps (orchestration actions)
            ├── TODOs (task list)
            ├── Tool Calls (MCP invocations)
            └── Metrics (performance data)
```

#### 36.2 AgentSession (PostgreSQL Model)

Sessions are stateful containers for agent interactions. Defined in [db/postgres_control/models/agent_session.py](db/postgres_control/models/agent_session.py):

```python
class AgentSession(Base):
    __tablename__ = "agent_sessions"

    session_id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    # Session state: active → completed/cancelled/failed
    status = Column(String(50), nullable=False, default="active", server_default="active")
    
    # Agent configuration
    manager = Column(String(255), nullable=True)  # Planner LLM name
    preferred_workers = Column(JSONB, nullable=True)  # List of worker names
    llm_preferences = Column(JSONB, nullable=True)  # Dict of tool/action → LLM name
    agent_role = Column(String(255), nullable=True)  # e.g., 'researcher', 'coder'
    tools = Column(JSONB, nullable=True)  # Allowed tool names
    temperature = Column(Float, nullable=False, default=0.2)
    max_steps = Column(Integer, nullable=False, default=8)
    
    # Metadata and tracking
    session_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_step_id = Column(PGUUID(as_uuid=True), ForeignKey("agent_steps.step_id"))
    etag = Column(String(64))  # For HTTP caching
    
    # Relationships
    steps = relationship("AgentStep", back_populates="session", cascade="all, delete-orphan")
    runs = relationship("AgentRun", back_populates="session", cascade="all, delete-orphan")
```

**Key features:**
- Status state machine: `active → completed/cancelled/failed`
- Configurable agent behavior (manager, workers, tools, temperature)
- ETag support for HTTP caching
- Cascade delete to clean up steps and runs

#### 36.3 AgentRun (PostgreSQL Model)

Runs represent single executions. Defined in [db/postgres_control/models/agent_run.py](db/postgres_control/models/agent_run.py):

```python
class AgentRun(Base):
    __tablename__ = "agent_runs"

    run_id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    session_id = Column(PGUUID(as_uuid=True), ForeignKey("agent_sessions.session_id"), nullable=True)
    user_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), ForeignKey("tenants.id"), nullable=False)

    # Model configuration (DB-driven)
    model_instance_name = Column(String(255), nullable=True)  # e.g., phi3-mini
    model_id = Column(String(255), nullable=True)  # Provider-specific ID (e.g., phi3:mini)
    provider_name = Column(String(255), nullable=True)  # e.g., ollama-local
    provider_id = Column(String(255), ForeignKey("providers.id"), nullable=True)
    config_source = Column(String(50), nullable=True)  # db_default, env_fallback, etc.

    # Run status: queued → running → succeeded/failed/cancelled
    status = Column(String(50), nullable=False, default="queued")
    
    # LLM error tracking
    llm_error_type = Column(String(100), nullable=True)  # timeout, context_length, rate_limit, etc.
    llm_error_message = Column(Text, nullable=True)
    llm_error_occurred_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    latency_ms = Column(Integer, nullable=True)

    # Execution data (JSONB for flexibility)
    todos = Column(JSONB, nullable=True, server_default="[]")
    steps = Column(JSONB, nullable=True, server_default="[]")
    output = Column(JSONB, nullable=True)
    warnings = Column(JSONB, nullable=True, server_default="[]")
    metrics = Column(JSONB, nullable=True)  # LLM calls, tool calls, timing
    run_metadata = Column("metadata", JSONB, nullable=False, server_default="{}")

    # Tracing
    trace_id = Column(String(255), nullable=True, index=True)
    request_id = Column(String(255), nullable=True, index=True)
```

**Status state machine:**
```
queued → running → succeeded
                 → failed
                 → cancelled
```

#### 36.4 AgentStep (PostgreSQL Model)

Steps are individual actions within a session. Defined in [db/postgres_control/models/agent_step.py](db/postgres_control/models/agent_step.py):

```python
class AgentStep(Base):
    __tablename__ = "agent_steps"

    step_id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    session_id = Column(PGUUID(as_uuid=True), ForeignKey("agent_sessions.session_id"), nullable=False)
    
    # Monotonic sequence number per session (allocated via Redis INCR)
    seq = Column(Integer, nullable=False)
    
    # Step type: message, user, assistant, tool, system, error
    type = Column(String(50), nullable=False)
    message = Column(Text, nullable=True)
    tool = Column(String(255), nullable=True)  # Tool name if type='tool'

    # Structured input/output
    input = Column(JSONB, nullable=True)
    output = Column(JSONB, nullable=True)
    
    # Status: queued → running → completed/failed/cancelled
    status = Column(String(50), nullable=False, default="queued")
    error = Column(JSONB, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
```

**Step types:**
| Type | Description |
|------|-------------|
| `message` | User message |
| `user` | User action |
| `assistant` | LLM response |
| `tool` | Tool invocation |
| `system` | System message |
| `error` | Error occurred |

#### 36.5 TODOs (Pydantic Schema)

TODOs represent planned tasks in the agent's execution. Defined in [src/schemas/agents.py](src/schemas/agents.py):

```python
class TodoItem(BaseModel):
    task: str  # Description of the task
    status: Literal["pending", "in_progress", "completed", "failed"] | None = None
    expect_evidence: bool = True  # Whether TODO should produce evidence
    evidence: list[str] = []  # Step IDs or summaries supporting completion
    meta: dict[str, Any] | None = {}  # Tool hints, modes, prompt IDs
    requires_llm_planning: bool = True  # If false, execute directly
    nested_steps: list[str] = []  # Nested step descriptions from LLM
    fallback_mode: bool = False  # Execute without tools (fallback mode)
```

TODOs are stored in the `todos` JSONB column of `agent_runs` and enable:
- Multi-step planning by the orchestrator
- Progress tracking with evidence
- Fallback mode for degraded operation

#### 36.6 Metrics (Pydantic Schema)

Execution metrics track performance. Defined in [src/schemas/agents.py](src/schemas/agents.py):

```python
class LLMCallMetrics(BaseModel):
    model: str
    latency_ms: int
    success: bool
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    purpose: str | None = None  # e.g., 'todo_list_creation'
    error: str | None = None

class ToolCallMetrics(BaseModel):
    name: str
    latency_ms: int
    success: bool

class ExecutionMetrics(BaseModel):
    overall_ms: int
    llm: list[LLMCallMetrics] = []
    tools: list[ToolCallMetrics] = []
    
    # Counters
    total_llm_calls: int | None = None
    llm_attempted_calls: int | None = None
    llm_successful_calls: int | None = None
    tool_calls: int | None = None
    tool_errors: int | None = None
    
    # Timing breakdown
    first_llm_call_ms: int | None = None
    planning_ms: int | None = None
    execution_ms: int | None = None
    
    # Configuration
    configured_run_timeout_seconds: int | None = None
    configured_step_timeout_seconds: int | None = None
    timeout_stage: str | None = None
    timeout_reason: str | None = None
```

#### 36.7 Orchestrator Data Structures

The orchestrator uses internal dataclasses for execution. Defined in [src/services/orchestrator.py](src/services/orchestrator.py):

```python
@dataclass(slots=True)
class Step:
    """A single orchestration step produced by a planner."""
    id: str
    action: str
    input: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None
    latency_ms: int | None = None

@dataclass(slots=True)
class OrchestrationContext:
    """Mutable 'blackboard' context passed between steps."""
    goal: str
    user_id: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None
    run_id: str | None = None
    principal: dict[str, Any] | None = None  # For RBAC
    force_full_agentic: bool = False
    vars: dict[str, Any] = field(default_factory=dict)

@dataclass
class OrchestrationResult:
    goal: str
    manager: str | None = None
    steps: list[Step] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    todos: list[dict[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    # Timing
    started_at: str = field(default_factory=lambda: utc_now().isoformat())
    finished_at: str | None = None
    overall_ms: int | None = None
    
    # Metrics
    llm_metrics: list[dict[str, Any]] = field(default_factory=list)
    tool_metrics: list[dict[str, Any]] = field(default_factory=list)
    total_llm_calls: int = 0
    llm_attempted_calls: int = 0
    llm_successful_calls: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    
    # Degraded/fallback flags
    degraded: bool = False  # LLM fallback used
    used_fallback: bool = False  # Deterministic fallback instead of LLM
```

#### 36.8 Persistence Flow

```
1. Request arrives at POST /v1/agent-runs
   ↓
2. Router creates AgentRun in PostgreSQL (status=queued)
   ↓
3. Orchestrator.run() executes:
   - Intent classification
   - TODO list creation
   - Step-by-step execution (LLM calls + tool invocations)
   - Metrics accumulation
   ↓
4. Router updates AgentRun:
   - status → succeeded/failed
   - todos, steps, output, metrics → JSONB columns
   - finished_at, latency_ms
   ↓
5. Response returned to client
```

---

### 37. MCP Tool Ecosystem

37. **Describe the MCP tool ecosystem**: which tool families exist (graph, cache, data, security, admin, utils), how they are defined, and how they are invoked.

The platform implements a Model Context Protocol (MCP) tool system with 34 tools across 17 categories.

#### 37.1 Tool Categories (Families)

| Family | Tools | Purpose |
|--------|-------|---------|
| `agent.*` | `agent.context` | Context assembly, metadata collection |
| `cache.*` | `cache.manage` | Redis-backed caching with TTL and namespacing |
| `catalog.*` | `catalog.discover` | Tool discovery and metadata |
| `data.*` | `data.archive`, `data.quality` | Data archival, quality checks |
| `db.*` | `db.switch` | Database connection management |
| `errors.*` | `errors.report` | Structured error reporting |
| `graph.*` | `graph.analytics`, `graph.bulk`, `graph.crud`, `graph.generate_cypher`, `graph.query`, `graph.schema`, `graph.search`, `graph.secure_query` | Memgraph operations |
| `model.*` | `model.manage` | LLM model configuration |
| `output.*` | `output.guard` | Output filtering and guards |
| `privacy.*` | `privacy.scrub` | PII scrubbing |
| `ratelimit.*` | `ratelimit.check` | Rate limiting |
| `security.*` | `security.allowed_operations`, `security.audit`, `security.check`, `security.describe_principal`, `security.permissions` | Security operations |
| `session.*` | `session.manage` | Session management |
| `system.*` | `system.health` | Health checks |
| `tenancy.*` | `tenancy.resolve` | Multi-tenant resolution |
| `user.*` | `user.preferences` | User preferences |
| `viz.*` | `viz.render` | Visualization |

#### 37.2 Tool Directory Structure

```
src/mcp/tools/
├── __init__.py          # Discovery and loading utilities
├── README_mcp_tools.md  # Documentation
├── agent/               # Context assembly tools
├── cache/               # Redis caching tools
├── catalog/             # Tool discovery
├── data/                # Data management
├── db/                  # Database switching
├── errors/              # Error reporting
├── graph/               # Memgraph operations
│   ├── analytics.py
│   ├── bulk.py
│   ├── crud.py
│   ├── generate_cypher.py
│   ├── query.py
│   ├── schema.py
│   ├── search.py
│   └── secure_query.py
├── model/               # LLM management
├── output/              # Output guards
├── privacy/             # PII scrubbing
├── ratelimit/           # Rate limiting
├── security/            # Security operations
├── session/             # Session management
├── system/              # System health
├── tenancy/             # Multi-tenancy
├── user/                # User preferences
└── viz/                 # Visualization
```

#### 37.3 Tool Definition Pattern

Tools are defined using a decorator-based pattern. From [src/mcp/runtime.py](src/mcp/runtime.py):

```python
@mcp_tool(
    name="graph.query",
    scopes=["graph:read"],
    timeout_ms=30000,
    rate_limit=60,
)
async def invoke(payload: dict, ctx: ToolContext, **kwargs) -> dict:
    """Execute read-only Cypher queries."""
    action = payload.get("action", "run")
    
    if action == "run":
        return _act_run(db, payload)
    elif action == "explain":
        return _act_explain(db, payload)
    else:
        raise ValueError(f"Unknown action: {action}")
```

**Decorator provides:**
- Name registration
- Scope-based RBAC
- Timeout enforcement
- Rate limiting hooks
- Telemetry (Prometheus metrics)

#### 37.4 MCP Runtime Features

The runtime in [src/mcp/runtime.py](src/mcp/runtime.py) provides:

```python
class ToolContext(BaseModel):
    """Execution context for a tool invocation."""
    tool: str
    action: str
    principal: Any | None = None  # For RBAC
    tenant: str | None = None
    trace_id: str | None = None
    timeout_ms: int | None = None
    start_time: float = 0.0

    def elapsed_ms(self) -> float:
        """Return elapsed time in milliseconds."""
        return (time.time() - self.start_time) * 1000

    def check_timeout(self) -> None:
        """Raise TimeoutError_ if timeout exceeded."""
        if self.timeout_ms and self.elapsed_ms() > self.timeout_ms:
            raise TimeoutError_(f"Operation timed out after {self.timeout_ms}ms")

# Standard error types
class ToolError(Exception): ...
class ValidationError_(ToolError): ...
class PermissionError_(ToolError): ...
class TimeoutError_(ToolError): ...
class RateLimitError_(ToolError): ...
```

**Metrics (Prometheus):**
```python
TOOL_INVOCATIONS = Counter(
    "mcp_tool_invocations_total",
    "Total MCP tool invocations",
    ["tool", "action", "status"],
)
TOOL_LATENCY = Histogram(
    "mcp_tool_latency_seconds",
    "MCP tool invocation latency",
    ["tool", "action"],
)
```

#### 37.5 Tool Discovery and Loading

From [src/mcp/tools/__init__.py](src/mcp/tools/__init__.py):

```python
PACKAGE_ROOT = "src.mcp.tools"
ENTRYPOINT_CANDIDATES = ("invoke", "run", "handle")

def module_name_for_tool(tool_name: str) -> str:
    """Translate MCP tool name to Python module path.
    
    Example: "graph.query" → "src.mcp.tools.graph.query"
    """
    return f"{PACKAGE_ROOT}.{tool_name.strip().strip('.')}"

def import_module_for_tool(tool_name: str) -> ModuleType:
    """Import and return the Python module that implements the tool."""
    return importlib.import_module(module_name_for_tool(tool_name))

def find_callable_in_module(mod: ModuleType) -> tuple[str | None, Callable | None]:
    """Best-effort resolution of callable within a tool module.
    
    Preference order: invoke → run → handle
    """
    for attr in ("invoke", "run", "handle"):
        if hasattr(mod, attr):
            fn = getattr(mod, attr)
            if callable(fn):
                return attr, fn
    return None, None

def load(tool_name: str) -> tuple[ModuleType, Callable | None]:
    """Import a tool module and return (module, callable_or_none)."""
    mod = import_module_for_tool(tool_name)
    _, fn = find_callable_in_module(mod)
    return mod, fn
```

#### 37.6 Tool Invocation via API

Tools are invoked through [src/routers/tools.py](src/routers/tools.py):

```python
@router.post("/invocations", response_model=ToolInvokeResponse)
async def invoke_tool(
    request: Request,
    body: ToolInvokeRequest,
    user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Invoke a tool by dotted name (e.g., "graph.query")."""
    
    # Load tool module
    mod, fn = load(body.name)
    if not fn:
        raise HTTPException(404, f"Tool '{body.name}' not found")
    
    # Create context
    ctx = ToolContext(
        tool=body.name,
        action=body.payload.get("action", "default"),
        principal=user,
        tenant=request.headers.get("X-Tenant-Id"),
        timeout_ms=body.timeout_ms,
    )
    
    # Execute with metrics
    start = time.time()
    try:
        result = await fn(body.payload, ctx=ctx)
        TOOL_INVOKE.labels(name=body.name, success="true").inc()
        return ToolInvokeResponse(ok=True, result=result)
    except Exception as e:
        TOOL_INVOKE.labels(name=body.name, success="false").inc()
        raise
    finally:
        TOOL_LATENCY.observe(time.time() - start)
```

#### 37.7 Example: graph.query Tool

From [src/mcp/tools/graph/query.py](src/mcp/tools/graph/query.py):

```python
"""
MCP Tool: graph.query

Supported actions:
- run: Execute Cypher query
- explain: Get execution plan
- profile: Get profiled execution
"""

from src.mcp.runtime import ToolContext, mcp_tool

# Write detection pattern
_WRITE_PAT = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP)\b",
    re.IGNORECASE | re.DOTALL,
)

def _looks_write(cypher: str) -> bool:
    """Detect write operations in Cypher query."""
    return bool(_WRITE_PAT.search(cypher))

def _act_run(db: MemgraphAdapter, payload: dict) -> dict:
    cypher = payload.get("cypher")
    if not cypher:
        raise ValueError("graph.query/run requires 'cypher'")
    
    params = payload.get("params") or {}
    read_only = bool(payload.get("read_only", False))
    limit = payload.get("limit")
    
    # Safety check
    if read_only and _looks_write(cypher):
        raise ValueError("Write operations not allowed in read_only mode")
    
    # Execute
    rows = db.execute(cypher, params)
    rows, truncated = _slice_rows(rows, limit)
    
    return {
        "ok": True,
        "action": "run",
        "columns": _columns(rows),
        "rows": rows,
        "rowcount": len(rows),
        "truncated": truncated,
        "read_only": read_only,
    }
```

---

### 38. Jobs Framework

38. **Explain how the jobs framework works** (job model, job store, event store, idempotency, status transitions, SSE events) using code references.

The jobs framework provides asynchronous task execution with PostgreSQL persistence and Redis queuing.

#### 38.1 Job Model

From [src/jobs/models.py](src/jobs/models.py):

```python
class JobStatus(str, Enum):
    """Job lifecycle states."""
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.FINISHED, JobStatus.FAILED, JobStatus.CANCELLED)

class JobDocument(BaseModel):
    """Core job entity - storage-agnostic domain model."""
    id: str
    owner: str  # From JWT sub claim
    tenant_id: str
    type: str  # e.g., 'demo', 'training'
    status: JobStatus = JobStatus.QUEUED
    payload: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None
    error: str | None = None

    def to_hash_dict(self) -> dict[str, str]:
        """Convert to flat string dict for Redis HASH storage."""
        return {
            "id": self.id,
            "owner": self.owner,
            "tenant_id": self.tenant_id,
            "type": self.type,
            "status": self.status.value,
            "payload": json.dumps(self.payload),
            "result": json.dumps(self.result) if self.result else "",
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
            "error": self.error or "",
        }
```

PostgreSQL model from [db/postgres_control/models/job.py](db/postgres_control/models/job.py):

```python
class Job(Base):
    __tablename__ = "jobs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    type = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="queued")
    owner_sub = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), ForeignKey("tenants.id"), nullable=True)

    # Job data
    payload_json = Column(JSONB, nullable=False, default=dict)
    result_json = Column(JSONB)
    error_json = Column(JSONB)

    # Idempotency and priority
    idempotency_key = Column(String(255), index=True)
    priority = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Performance metrics
    queue_latency_ms = Column(Integer)
    exec_latency_ms = Column(Integer)

    # Relationships
    events = relationship("JobEvent", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'finished', 'failed', 'cancelled')"),
        Index("idx_jobs_idempotency_unique", "owner_sub", "idempotency_key", unique=True,
              postgresql_where="idempotency_key IS NOT NULL"),
    )
```

#### 38.2 Job Store Interface

From [src/jobs/interfaces.py](src/jobs/interfaces.py):

```python
class JobStore(ABC):
    """Abstract interface for job document storage."""

    @abstractmethod
    async def create(self, job: JobDocument, ttl_seconds: int) -> None:
        """Persist a new job with automatic expiry."""

    @abstractmethod
    async def get(self, job_id: str) -> JobDocument | None:
        """Retrieve job by ID."""

    @abstractmethod
    async def update_status(
        self, job_id: str, status: JobStatus,
        result: dict | None = None, error: str | None = None,
        ttl_seconds: int | None = None
    ) -> bool:
        """Atomically update job status and optional result/error."""

    @abstractmethod
    async def list_by_owner(
        self, owner: str, status: JobStatus | None = None,
        offset: int = 0, limit: int = 25
    ) -> tuple[list[JobDocument], int]:
        """List jobs for owner, newest first."""

    @abstractmethod
    async def delete(self, job_id: str) -> bool:
        """Delete job and associated indices."""

class IdempotencyStore(ABC):
    """Abstract interface for idempotency key management."""

    @abstractmethod
    async def get_job_id(self, key: str) -> str | None:
        """Check if idempotency key exists and return associated job_id."""

    @abstractmethod
    async def store(self, key: str, job_id: str, ttl_seconds: int) -> None:
        """Store idempotency key pointing to job_id with expiry."""

class EventStore(ABC):
    """Abstract interface for SSE event management."""

    @abstractmethod
    async def append(self, job_id: str, event: SSEEvent, ring_size: int) -> None:
        """Append event to job's ring buffer."""

    @abstractmethod
    async def get_next_event_id(self, job_id: str) -> int:
        """Get next monotonic event ID for this job."""

    @abstractmethod
    async def replay_from(self, job_id: str, last_event_id: int) -> list[SSEEvent]:
        """Retrieve events with event_id > last_event_id."""
```

#### 38.3 Store Factory

From [src/jobs/factory.py](src/jobs/factory.py):

```python
def get_stores() -> tuple[JobStore, IdempotencyStore, EventStore]:
    """Factory function for job storage backends."""
    backend = settings.JOB_STORE_BACKEND.lower()

    if backend == "memory":
        logger.info("Using in-memory job storage (no TTL)")
        return (
            MemoryJobStore(),
            MemoryIdempotencyStore(),
            MemoryEventStore(ring_size=settings.SSE_RING_SIZE),
        )
    elif backend == "redis":
        logger.info(f"Using Redis job storage (TTL={settings.JOB_TTL_DAYS} days)")
        return (
            RedisJobStore(),
            RedisIdempotencyStore(),
            RedisEventStore(ring_size=settings.SSE_RING_SIZE),
        )
    else:
        raise ValueError(f"Invalid JOB_STORE_BACKEND: {backend}")
```

#### 38.4 Event Model (SSE)

From [src/jobs/models.py](src/jobs/models.py):

```python
class SSEEvent(BaseModel):
    """Server-Sent Event for job status updates."""
    event_id: int  # Monotonic sequence number
    event_type: str  # 'status', 'end', 'error'
    data: dict[str, Any]  # Payload (job_id, status, etc.)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_sse_format(self) -> str:
        """Format as SSE wire protocol."""
        return "\n".join([
            f"id: {self.event_id}",
            f"event: {self.event_type}",
            f"data: {json.dumps(self.data)}",
            "",  # SSE requires blank line
        ])
```

PostgreSQL event model from [db/postgres_control/models/job_event.py](db/postgres_control/models/job_event.py):

```python
class JobEvent(Base):
    """Records state changes in a job's lifecycle."""
    __tablename__ = "job_events"

    seq_id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_id = Column(PGUUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    event_type = Column(String(100), nullable=False)  # status, log, progress, heartbeat, end
    event_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_sse_event(self) -> str:
        """Format as SSE message."""
        return "\n".join([
            f"id: {self.seq_id}",
            f"event: {self.event_type}",
            f"data: {self.event_json}",
            "",
        ])
```

#### 38.5 Status Transitions

```
queued → running → finished
                 → failed
                 → cancelled

queued → cancelled (before execution)
```

From [src/services/jobs_service.py](src/services/jobs_service.py):

```python
def transition_status(
    self, job_id: UUID, from_status: str, to_status: str
) -> Job | None:
    """Atomically transition job status with validation."""
    return self.repo.transition_status(
        job_id=job_id,
        from_status=from_status,
        to_status=to_status,
        completed_at=datetime.utcnow() if to_status in ("finished", "failed", "cancelled") else None,
    )
```

#### 38.6 Idempotency Support

From [src/services/jobs_service.py](src/services/jobs_service.py):

```python
def create_job(
    self, owner_sub: str, tenant_id: str, job_type: str,
    payload: dict, idempotency_key: str | None = None, priority: int = 0
) -> tuple[Job, bool]:
    """Create a new job with idempotency support."""
    
    # Check Redis idempotency cache first (fast path)
    if idempotency_key:
        cached_job_id = jobs_cache.get_idempotency_mapping(owner_sub, idempotency_key)
        if cached_job_id:
            job = self.repo.get_job(UUID(cached_job_id))
            if job:
                return job, False  # Idempotent replay

    # Check PostgreSQL idempotency (authoritative)
    if idempotency_key:
        existing_job = self.repo.find_by_idempotency(owner_sub, idempotency_key)
        if existing_job:
            # Cache in Redis for future fast lookups
            jobs_cache.set_idempotency_mapping(owner_sub, idempotency_key, existing_job.id, ttl_hours=24)
            return existing_job, False

    # Create new job
    job = self.repo.create_job(...)
    
    # Push to Redis queue
    jobs_cache.queue_push_job(job_type, job.id, priority)
    
    # Cache in Redis
    jobs_cache.set_job_state(job.id, job.status, owner_sub, ttl_seconds=7200)
    
    if idempotency_key:
        jobs_cache.set_idempotency_mapping(owner_sub, idempotency_key, job.id, ttl_hours=24)

    return job, True  # New job created
```

---

### 39. Worker Architecture

39. **Describe the worker architecture**: how workers dequeue jobs, interact with Postgres/Redis, handle cancellations, and manage heartbeats/shutdown.

Workers process jobs from Redis queues and persist results to PostgreSQL.

#### 39.1 Worker Class

From [src/workers/jobs_worker.py](src/workers/jobs_worker.py):

```python
class JobsWorker:
    """Background worker for processing jobs with PostgreSQL persistence."""

    def __init__(
        self,
        poll_interval: float = 1.0,
        heartbeat_interval: float = 5.0,
        max_iterations: int | None = None,
    ):
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval
        self.max_iterations = max_iterations
        self.running = False
        self.current_job_id: str | None = None

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False
```

#### 39.2 Main Worker Loop

```python
async def start(self):
    """Main worker loop."""
    logger.info("Jobs worker starting...")
    self.running = True
    iteration = 0

    while self.running:
        # Check max iterations (for testing)
        if self.max_iterations and iteration >= self.max_iterations:
            break

        iteration += 1

        try:
            processed = await self._process_next_job()
            if not processed:
                # No jobs available, sleep before next poll
                await asyncio.sleep(self.poll_interval)
        except Exception as e:
            logger.error(f"Error in worker loop: {e}")
            await asyncio.sleep(self.poll_interval)

    logger.info("Jobs worker stopped")
```

#### 39.3 Job Dequeuing

```python
async def _process_next_job(self) -> bool:
    """Process one job from the queue."""
    # Get allowed job types
    allowed_types = [t.strip() for t in settings.ALLOWED_JOB_TYPES.split(",")]

    # Try to pop from each queue (round-robin)
    for job_type in allowed_types:
        job_id = await asyncio.to_thread(jobs_cache.queue_pop_job, job_type, timeout=0)

        if job_id:
            logger.info(f"Popped job {job_id} from queue '{job_type}'")
            self.current_job_id = job_id

            try:
                db = next(get_db())
                try:
                    await self._execute_job(job_id, db)
                finally:
                    self.current_job_id = None
            except Exception as e:
                logger.error(f"Failed to execute job {job_id}: {e}")

            return True

    return False  # All queues empty
```

#### 39.4 Job Execution with Lifecycle Management

```python
async def _execute_job(self, job_id: str, db: Session):
    """Execute a single job with full lifecycle management."""
    job_uuid = UUID(job_id)
    jobs_service = JobsService(db)

    try:
        # Load job from PostgreSQL
        job = jobs_service.repo.get_job(job_uuid)
        if not job:
            logger.error(f"Job {job_id} not found in database")
            return

        # Check if already cancelled
        if await asyncio.to_thread(jobs_cache.check_cancel_flag, job_id):
            await self._mark_cancelled(job_uuid, jobs_service)
            return

        # Transition to RUNNING
        job = jobs_service.transition_status(job_uuid, from_status="queued", to_status="running")
        if not job:
            logger.error(f"Failed to transition job {job_id} to running")
            return

        # Log event
        jobs_service.append_event(
            job_uuid,
            event_type="status",
            event_data={"to": "running", "from": "queued", "timestamp": datetime.utcnow().isoformat()},
        )

        # Execute with heartbeat monitoring
        result = await self._run_job_with_heartbeat(job_id, job.type, job.payload_json or {}, jobs_service)

        # Check if cancelled during execution
        if await asyncio.to_thread(jobs_cache.check_cancel_flag, job_id):
            await self._mark_cancelled(job_uuid, jobs_service)
            return

        # Transition to FINISHED
        job = jobs_service.repo.update_job_result(job_uuid, result)
        job = jobs_service.transition_status(job_uuid, from_status="running", to_status="finished")

        jobs_service.append_event(job_uuid, event_type="status",
            event_data={"to": "finished", "from": "running", "timestamp": datetime.utcnow().isoformat()})

    except Exception as e:
        # Transition to FAILED
        job = jobs_service.repo.update_job_error(job_uuid, str(e))
        job = jobs_service.transition_status(job_uuid, from_status="running", to_status="failed")
        jobs_service.append_event(job_uuid, event_type="status",
            event_data={"to": "failed", "error": str(e), "timestamp": datetime.utcnow().isoformat()})
```

#### 39.5 Heartbeat Mechanism

```python
async def _run_job_with_heartbeat(
    self, job_id: str, job_type: str, payload: dict, jobs_service: JobsService
) -> dict:
    """Execute job with periodic heartbeat updates."""
    job_uuid = UUID(job_id)

    # Start heartbeat task
    heartbeat_task = asyncio.create_task(self._heartbeat_loop(job_uuid, jobs_service))

    try:
        result = await self._execute_job_type(job_id, job_type, payload)
        return result
    finally:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task

async def _heartbeat_loop(self, job_uuid: UUID, jobs_service: JobsService):
    """Periodically update job timestamp to indicate worker is alive."""
    while True:
        await asyncio.sleep(self.heartbeat_interval)
        try:
            jobs_service.repo.touch_job(job_uuid)
            logger.debug(f"Heartbeat for job {job_uuid}")
        except Exception as e:
            logger.warning(f"Heartbeat failed for job {job_uuid}: {e}")
```

#### 39.6 Cancellation Handling

```python
async def _execute_demo_job(self, job_id: str, payload: dict) -> dict:
    """Demo job with cancellation checks."""
    duration_ms = payload.get("duration_ms", 1000)
    duration_sec = duration_ms / 1000.0

    # Simulate work with cancellation checks
    sleep_chunks = int(duration_sec / 0.5) + 1  # Check every 0.5s

    for _ in range(sleep_chunks):
        # Check cancellation flag in Redis
        if await asyncio.to_thread(jobs_cache.check_cancel_flag, job_id):
            raise asyncio.CancelledError("Job cancelled")
        await asyncio.sleep(min(0.5, duration_sec))

    return {"status": "completed", "duration_ms": duration_ms}

async def _mark_cancelled(self, job_uuid: UUID, jobs_service: JobsService):
    """Mark job as cancelled."""
    # Try from queued first
    job = jobs_service.transition_status(job_uuid, from_status="queued", to_status="cancelled")
    if not job:
        # Try from running
        job = jobs_service.transition_status(job_uuid, from_status="running", to_status="cancelled")

    if job:
        jobs_service.append_event(job_uuid, event_type="status",
            event_data={"to": "cancelled", "timestamp": datetime.utcnow().isoformat()})
```

#### 39.7 Worker Entry Point

```python
async def main():
    """Main entry point for worker process."""
    poll_interval = float(settings.JOB_WORKER_POLL_INTERVAL)
    heartbeat_interval = float(settings.JOB_WORKER_HEARTBEAT_INTERVAL)

    if not settings.USE_POSTGRES_JOBS:
        logger.error("Worker requires USE_POSTGRES_JOBS=true")
        sys.exit(1)

    worker = JobsWorker(poll_interval=poll_interval, heartbeat_interval=heartbeat_interval)

    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")

if __name__ == "__main__":
    asyncio.run(main())
```

---

### 40. Background/Scheduler Framework

40. **Explain the background/scheduler framework**: what periodic tasks exist (health checks, backups, cleanups) and how they are configured.

The platform uses APScheduler for periodic background tasks.

#### 40.1 Configuration

From [src/background.py](src/background.py):

```python
@dataclass
class BackgroundConfig:
    enabled: bool = getattr(settings, "BACKGROUND_ENABLED", True)

    # Health probe interval (seconds)
    health_enabled: bool = getattr(settings, "BACKGROUND_HEALTH_ENABLED", True)
    health_interval_seconds: int = getattr(settings, "BACKGROUND_HEALTH_INTERVAL_SECONDS", 30)

    # Backups via cron (crontab format, UTC)
    backup_enabled: bool = getattr(settings, "BACKGROUND_BACKUPS_ENABLED", False)
    backup_cron: str = getattr(settings, "BACKGROUND_BACKUPS_CRON", "30 2 * * *")  # 02:30 UTC daily

    # Cleanup via cron
    cleanup_enabled: bool = getattr(settings, "BACKGROUND_CLEANUP_ENABLED", False)
    cleanup_cron: str = getattr(settings, "BACKGROUND_CLEANUP_CRON", "15 3 * * 0")  # 03:15 UTC Sundays

    # Redis cleanup (hourly)
    redis_cleanup_enabled: bool = getattr(settings, "BACKGROUND_REDIS_CLEANUP_ENABLED", True)
    redis_cleanup_interval_seconds: int = getattr(settings, "BACKGROUND_REDIS_CLEANUP_INTERVAL", 3600)
    redis_cleanup_batch_size: int = getattr(settings, "BACKGROUND_REDIS_CLEANUP_BATCH_SIZE", 500)
```

#### 40.2 Background Manager

```python
class BackgroundManager:
    """Coordinates background jobs with metrics and logging."""

    def __init__(
        self,
        health: HealthService | None = None,
        archive: ArchiveService | None = None,
        metrics: ServiceMetrics | None = None,
        config: BackgroundConfig | None = None,
    ):
        self.config = config or BackgroundConfig()
        self.scheduler: AsyncIOScheduler | None = None
        self.health = health or HealthService()
        self.archive = archive or ArchiveService()
        self.metrics = metrics or ServiceMetrics()
        self._started = False

    async def start(self) -> None:
        """Start the scheduler and register jobs."""
        if not self.config.enabled:
            log.info("background.disabled")
            return

        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._register_jobs()
        self.scheduler.start()
        self._started = True

    async def stop(self) -> None:
        """Stop scheduler and wait for running jobs."""
        if self._started and self.scheduler:
            self.scheduler.shutdown(wait=True)
            self._started = False
```

#### 40.3 Job Registration

```python
def _register_jobs(self) -> None:
    assert self.scheduler is not None

    # Health checks (interval-based)
    if self.config.health_enabled:
        self.scheduler.add_job(
            self._wrap_job(self._job_health, "health"),
            IntervalTrigger(seconds=self.config.health_interval_seconds),
            id="background.health",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

    # Backups (cron-based)
    if self.config.backup_enabled:
        self.scheduler.add_job(
            self._wrap_job(self._job_backup, "backup"),
            CronTrigger.from_crontab(self.config.backup_cron),
            id="background.backup",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

    # Cleanup (cron-based)
    if self.config.cleanup_enabled:
        self.scheduler.add_job(
            self._wrap_job(self._job_cleanup, "cleanup"),
            CronTrigger.from_crontab(self.config.cleanup_cron),
            id="background.cleanup",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

    # Redis index cleanup (interval-based)
    if self.config.redis_cleanup_enabled and settings.JOB_STORE_BACKEND == "redis":
        self.scheduler.add_job(
            self._wrap_job(self._job_redis_cleanup, "redis_cleanup"),
            IntervalTrigger(seconds=self.config.redis_cleanup_interval_seconds),
            id="background.redis_cleanup",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
```

#### 40.4 Periodic Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `health` | Every 30s | Check Postgres, Redis, Memgraph, LLMs |
| `backup` | 02:30 UTC daily | Memgraph snapshot/backup |
| `cleanup` | 03:15 UTC Sundays | Retention cleanup, prune stale data |
| `redis_cleanup` | Hourly | Clean orphaned ZSET members from indexes |

```python
async def _job_health(self) -> None:
    """Periodic health check sweep."""
    res = await self.health.check()
    if not res.ok:
        log.warning("background.health.unhealthy", error=res.error)
    else:
        log.info("background.health.ok")

async def _job_backup(self) -> None:
    """Create a snapshot/backup via ArchiveService."""
    for candidate in ("backup", "run_backup", "create_backup"):
        if hasattr(self.archive, candidate):
            fn = getattr(self.archive, candidate)
            maybe_awaitable = fn()
            if asyncio.iscoroutine(maybe_awaitable):
                await maybe_awaitable
            break

async def _job_cleanup(self) -> None:
    """Run retention/cleanup via ArchiveService."""
    for candidate in ("cleanup", "run_cleanup", "prune"):
        if hasattr(self.archive, candidate):
            fn = getattr(self.archive, candidate)
            maybe_awaitable = fn()
            if asyncio.iscoroutine(maybe_awaitable):
                await maybe_awaitable
            break

async def _job_redis_cleanup(self) -> None:
    """Clean orphaned ZSET members from Redis job store indexes."""
    store = RedisJobStore()
    redis = await get_async_redis()
    total_removed = 0

    # Clean global index
    removed = await store.cleanup_orphaned_index_members("jobs:all", batch_size=500)
    total_removed += removed

    # Clean status indexes
    for status in ["queued", "running", "finished", "failed", "cancelled"]:
        removed = await store.cleanup_orphaned_index_members(f"jobs:status:{status}")
        total_removed += removed

    # Clean owner indexes
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor=cursor, match="jobs:owner:*", count=100)
        for key in keys:
            removed = await store.cleanup_orphaned_index_members(key)
            total_removed += removed
        if cursor == 0:
            break

    log.info("background.redis_cleanup.completed", total_orphans_removed=total_removed)
```

#### 40.5 Job Wrapper with Metrics

```python
def _wrap_job(self, func: Callable[[], Awaitable[Any]], job_name: str) -> Callable[[], Awaitable[None]]:
    async def runner() -> None:
        start = time.perf_counter()
        status = "ok"
        try:
            await func()
        except Exception as e:
            status = "error"
            log.warning("background.job.error", job=job_name, err=str(e))
        finally:
            dur = time.perf_counter() - start
            # Record metrics
            if hasattr(self.metrics, "record_bg_job"):
                self.metrics.record_bg_job(job_name, status=status, duration_seconds=dur)
            log.debug("background.job.done", job=job_name, status=status, duration=f"{dur:.3f}s")
    return runner
```

#### 40.6 FastAPI Lifespan Integration

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Attach BackgroundManager to app.state.bg."""
    manager = build_default_manager()
    app.state.bg = manager
    await manager.start()
    try:
        yield
    finally:
        await manager.stop()
```

---

### 41. Operational Strengths and Weaknesses

41. **From an operational viewpoint, list the main strengths and weaknesses of the way agents, jobs, and background tasks are designed.**

#### 41.1 Strengths

| Area | Strength | Evidence |
|------|----------|----------|
| **Persistence** | Dual-store architecture (PostgreSQL + Redis) | Jobs persist in PostgreSQL (authoritative), Redis for queuing/caching. Survives Redis restarts. |
| **Idempotency** | Full idempotency support | Two-tier check (Redis cache → PostgreSQL authoritative) prevents duplicate job creation |
| **Observability** | Comprehensive metrics | Prometheus counters for jobs, tools, LLM calls; structured logging; trace IDs throughout |
| **Graceful Shutdown** | Signal handling | Workers handle SIGTERM/SIGINT, complete current job before shutdown |
| **Cancellation** | Redis-based cancel flags | Jobs check cancellation periodically during execution |
| **Heartbeats** | Worker liveness detection | Periodic timestamp updates allow detecting stale workers |
| **State Machines** | Clear status transitions | Validated transitions (queued→running→finished/failed/cancelled) with check constraints |
| **SSE Streaming** | Real-time updates | Ring buffer with Last-Event-ID support for resume |
| **Tool Ecosystem** | Comprehensive MCP tools | 34 tools across 17 categories with consistent patterns |
| **RBAC** | Scope-based access control | Tools enforce scopes, RBAC checked at invocation |
| **Multi-tenancy** | Tenant isolation | All models include tenant_id, queries are tenant-scoped |
| **Background Tasks** | APScheduler integration | Configurable intervals and cron schedules for maintenance |

#### 41.2 Weaknesses / Areas for Improvement

| Area | Weakness | Mitigation/Suggestion |
|------|----------|----------------------|
| **Single Worker** | No distributed job locking | Current design assumes single worker per job type; multi-worker would need distributed locks (Redis SETNX) |
| **Job Retry** | No automatic retry on failure | Jobs fail permanently; could add retry count and exponential backoff |
| **Job Priority** | Basic priority support | Priority is stored but not fully utilized in queue popping logic |
| **Timeout Granularity** | Run-level timeouts only | Step-level timeouts exist but complex failure modes when LLM is slow |
| **Memory Backend Limitations** | No TTL, single-process | Memory backend doesn't auto-expire; only suitable for dev/test |
| **Redis Dependencies** | Many Redis call patterns | Tight coupling to Redis for queues, caching, rate limits; Redis outage impacts availability |
| **Background Task Errors** | Silent failures | Errors are logged but no alerting integration built-in |
| **Event Ring Size** | Fixed buffer | Ring buffer size is configurable but can drop old events if consumer is slow |
| **Tool Registration** | Module-based discovery | Tools must follow naming convention; no dynamic registration at runtime |
| **Orchestrator Complexity** | 8000+ line file | [orchestrator.py](src/services/orchestrator.py) is very large; could benefit from refactoring into smaller modules |
| **Database Migrations** | 26 migrations | Large migration history; could consolidate for new deployments |
| **Cold Start** | Model loading time | First LLM call can be slow if Ollama needs to load model; warmup not automatic |

#### 41.3 Summary Table

| Component | Strengths | Weaknesses |
|-----------|-----------|------------|
| **Agent Runs** | Rich metrics, TODO support, JSONB flexibility | Complex schema, potential for inconsistent state |
| **MCP Tools** | Consistent patterns, RBAC, metrics | Module-based discovery only, no hot reload |
| **Jobs Framework** | Dual-store, idempotency, SSE | Single worker assumption, no retry |
| **Workers** | Heartbeats, graceful shutdown | No distributed locking |
| **Background Tasks** | Configurable, metrics | Silent failures, no alerting |

#### 41.4 Recommendations

1. **Add distributed locking** for multi-worker deployments (Redis SETNX or Redlock)
2. **Implement job retry** with configurable retry count and backoff
3. **Add alerting integration** for background task failures (PagerDuty, Slack, etc.)
4. **Refactor orchestrator.py** into smaller, focused modules
5. **Add model warmup** on startup for frequently-used models
6. **Implement circuit breaker** for Redis operations to handle outages gracefully
7. **Add job dead-letter queue** for permanently failed jobs requiring manual intervention

---

## G. Observability, testing & maintainability (42–46)

---

### 42. Observability Stack

42. **Describe the observability stack**: which metrics are exposed, what tracing instrumentation exists, and how logging is structured.

The platform implements comprehensive observability through three pillars: **metrics**, **tracing**, and **structured logging**.

#### 42.1 Metrics (Prometheus)

Metrics are exposed via the `/metrics` endpoint using the `prometheus_client` library. The setup is in [src/observability/metrics.py](src/observability/metrics.py) (569 lines).

**Setup Function:**
```python
def setup_metrics(app: FastAPI) -> None:
    """
    Initialize Prometheus metrics for the provided FastAPI app.
    - Creates/attaches app.state.prometheus_registry
    - Registers default collectors (Process/Platform/GC)
    - Creates/attaches app.state.metrics (_MetricStore)
    - Mounts /metrics endpoint
    """
```

**Metrics Categories:**

| Category | Metric Name | Type | Labels | Purpose |
|----------|-------------|------|--------|---------|
| **HTTP** | `http_requests_total` | Counter | method, path, status | Total HTTP requests |
| **HTTP** | `http_request_duration_seconds` | Histogram | method, path, status | Request latency distribution |
| **Background Jobs** | `background_jobs_total` | Counter | job, status | Job execution count |
| **Background Jobs** | `background_job_duration_seconds` | Histogram | job, status | Job duration distribution |
| **Tools** | `tools_invocations_total` | Counter | tool_name, status, tenant_id | Tool invocation count |
| **Tools** | `tools_invocation_duration_seconds` | Histogram | tool_name, status | Tool latency |
| **Tools** | `tools_queue_depth` | Gauge | tool_name | Pending invocations |
| **Tools** | `tools_cache_operations_total` | Counter | operation, result | Redis cache ops (hit/miss/error) |
| **Tools** | `tools_idempotency_conflicts_total` | Counter | tool_name | 409 idempotency conflicts |
| **Intent** | `intent_classification_total` | Counter | mode, source, adjusted | Intent classifications |
| **Intent** | `intent_classification_duration_seconds` | Histogram | mode, source | Classification latency |
| **Intent** | `intent_classification_confidence` | Histogram | mode, source | Confidence score distribution |
| **Intent** | `intent_pattern_matches_total` | Counter | pattern_group | Pattern match counts |
| **Intent** | `intent_llm_fallback_total` | Counter | success | LLM fallback usage |
| **Intent** | `intent_rbac_adjustments_total` | Counter | original_mode, adjusted_mode, role | RBAC adjustments |
| **Service** | `service_info` | Gauge | version | Static version info (always 1) |

**Agent-Specific Metrics** (from [src/metrics/agent_metrics.py](src/metrics/agent_metrics.py)):

| Metric Name | Type | Labels | Purpose |
|-------------|------|--------|---------|
| `agent_run_duration_seconds` | Histogram | status, tenant_id | Agent run duration |
| `agent_run_failures_total` | Counter | failure_type, tenant_id | Run failures by type |
| `agent_run_success_total` | Counter | tenant_id | Successful runs |
| `agent_run_queued_total` | Gauge | tenant_id | Queued runs |
| `agent_run_running_total` | Gauge | tenant_id | Active runs |
| `agent_todos_count` | Histogram | tenant_id | TODOs per run |
| `agent_todo_duration_seconds` | Histogram | status, tenant_id | TODO execution time |
| `agent_step_duration_seconds` | Histogram | action, status, tenant_id | Step execution time |
| `agent_llm_calls_total` | Counter | model, status, tenant_id | LLM call count |
| `agent_llm_duration_seconds` | Histogram | model, tenant_id | LLM call latency |
| `agent_llm_tokens_total` | Counter | model, token_type, tenant_id | Token consumption |

**Rate Limiting Metrics** (from [src/observability/rate_limit_metrics.py](src/observability/rate_limit_metrics.py)):

| Metric Name | Type | Labels | Purpose |
|-------------|------|--------|---------|
| `rate_limit_requests_total` | Counter | action, scope, result | Rate limit checks |
| `rate_limit_exceeded_total` | Counter | action, scope | Rate limit violations |
| `tenant_quota_exceeded_total` | Counter | action, tenant_id | Tenant quota violations |
| `rate_limit_usage_ratio` | Histogram | action, scope | Usage as ratio (0.0-1.0) |

**Model/Provider Metrics** (from [src/metrics/prometheus.py](src/metrics/prometheus.py)):

| Metric Name | Type | Labels | Purpose |
|-------------|------|--------|---------|
| `default_model_name` | Gauge | scope, tenant_id, model_name | Current default model |
| `model_warmup_seconds` | Histogram | model_name, provider, status | Model warmup duration |
| `provider_health_status` | Gauge | provider, model_name | Provider health (1/0) |
| `dmr_cache_hits_total` | Counter | scope, tenant_id | DMR cache hits |
| `dmr_cache_misses_total` | Counter | scope, tenant_id | DMR cache misses |

**Multiprocess Mode:**
```python
# Supports Prometheus multiprocess mode for Gunicorn workers
if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
    multiprocess.MultiProcessCollector(registry)
```

#### 42.2 Tracing (OpenTelemetry)

Distributed tracing is implemented in [src/observability/tracing.py](src/observability/tracing.py) (283 lines).

**Key Features:**
- Idempotent initialization (safe to call multiple times)
- OTLP exporter over gRPC (4317) or HTTP/protobuf (4318)
- Environment/resource attributes (service name, version, environment)
- FastAPI, Requests, and Logging instrumentation
- Graceful no-op if OTEL is disabled or dependencies missing

**Configuration:**
```python
# Environment variables for tracing
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false")
OTEL_EXPORTER_OTLP_PROTOCOL = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
OTEL_CONSOLE_EXPORTER = os.getenv("OTEL_CONSOLE_EXPORTER", "false")
OTEL_SAMPLER_RATIO = float(os.getenv("OTEL_SAMPLER_RATIO", "1.0"))
```

**Resource Attributes:**
```python
def _build_resource() -> Resource:
    return Resource.create({
        "service.name": settings.APP_NAME,  # "cineca-agentic-platform"
        "service.version": __version__,
        "service.instance.id": socket.gethostname(),
        "deployment.environment": settings.APP_ENV,
        "host.name": socket.gethostname(),
    })
```

**Sampling Strategy:**
```python
def _select_sampler() -> ParentBased:
    if env in {"prod", "production"}:
        # Sample 20% of traces in production
        return ParentBased(TraceIdRatioBased(0.2))
    # Sample all traces in non-prod
    return ParentBased(AlwaysOnSampler())
```

**Instrumentations:**
```python
# FastAPI automatic span creation
FastAPIInstrumentor().instrument_app(app, tracer_provider=provider)

# Outbound HTTP calls (requests library)
RequestsInstrumentor().instrument()

# Log correlation
LoggingInstrumentor().instrument(set_logging_format=True)
```

**Usage in Code:**
```python
from src.observability.tracing import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("operation_name") as span:
    span.set_attribute("key", "value")
    # ... operation
```

#### 42.3 Structured Logging (Structlog)

Logging is configured in [src/logging_setup.py](src/logging_setup.py) (165 lines).

**Setup Function:**
```python
def setup_logging(level: str | int = "INFO") -> None:
    """
    Initialize structlog + stdlib logging with a single StreamHandler.
    - Uses JSON in production, pretty console in development
    - Filters noisy access logs for /metrics, /health endpoints
    """
```

**Format Selection:**
```python
def _wants_json() -> bool:
    """JSON in production, console renderer in development."""
    fmt = os.getenv("LOG_FORMAT", "").strip().lower()
    if fmt in {"json", "console"}:
        return fmt == "json"
    env = os.getenv("APP_ENV", "dev").strip().lower()
    return env in {"prod", "production"}
```

**Processor Chain:**
```python
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
    wrapper_class=structlog.stdlib.BoundLogger,
)
```

**Access Log Filtering:**
```python
# Filter high-frequency noise paths
noise_paths = ["/metrics", "/health", "get /v1/agent-runs/", "options /v1/"]
access_filter = AccessPathFilter(*noise_paths)
logging.getLogger("uvicorn.access").addFilter(access_filter)
```

#### 42.4 Observability Middleware

The [src/observability/middleware.py](src/observability/middleware.py) (190 lines) ties everything together:

```python
class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Responsibilities:
    - Generate/propagate X-Request-ID and expose on responses
    - Time every request and expose X-Process-Time header
    - Record Prometheus metrics via record_request()
    - Attach trace_id as X-Trace-Id (if OpenTelemetry active)
    - Bind context into structlog for correlated logs
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        
        # Bind logging context
        bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=_get_route_template(request),
            client_ip=request.client.host if request.client else None,
        )
        
        if trace_id := _current_trace_id():
            bind_contextvars(trace_id=trace_id)
        
        response = await call_next(request)
        
        # Record metrics
        duration = time.perf_counter() - started
        record_request(request.method, route_template, status_code, duration, app=request.app)
        
        # Add headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration:.4f}s"
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        
        return response
```

---

### 43. Health Checks Implementation

43. **Explain how health checks are implemented** (liveness, readiness, startup, component health) and how they relate to infrastructure readiness.


Health checks follow Kubernetes probe patterns with four endpoints. Implementation is in [src/routers/health.py](src/routers/health.py) (707 lines) and [src/health/components.py](src/health/components.py) (639 lines).

#### 43.1 Health Endpoints

| Endpoint | Type | Purpose | Returns |
|----------|------|---------|---------|
| `GET /health/live` | Liveness | Process alive check | Plain text `ok` |
| `GET /health/ready` | Readiness | Dependencies ready check | JSON with status |
| `GET /health/startup` | Startup | Initial boot diagnostics | JSON with startup info |
| `GET /health/components` | Components | All component health | JSON with all checks |
| `GET /health/components/{name}` | Single | Individual component | JSON with check result |

#### 43.2 Liveness Probe

```python
@router.get("/live", response_class=PlainTextResponse)
async def health_live() -> Response:
    """
    Liveness probe: returns simple 'ok' text for low-cost probes.
    - No external I/O
    - Always returns HTTP 200 with plain text "ok"
    - <1ms response time
    """
    return PlainTextResponse(content="ok", status_code=200, headers={"Cache-Control": "no-store"})
```

**Use case:** Container orchestrators (Kubernetes) use this to detect crashes. If it fails, container is restarted.

#### 43.3 Readiness Probe

```python
@router.get("/ready")
async def ready() -> Response:
    """
    Readiness probe: checks external dependencies and reports aggregate status.
    
    Returns:
    - 200 when status is "ok" or "degraded" (with policy)
    - 503 when status is "error" (critical dependencies failed)
    """
    checks = await get_all_checks()
    status_str, http_code = evaluate_readiness(checks)
    
    body = build_response_body(
        checks=checks,
        status=status_str,
        service_name="cineca-agentic-platform",
        version=settings.APP_VERSION,
    )
    
    # Admin can disable readiness
    if not _is_ready:
        body["status"] = "not ready"
        body["reason"] = "admin-disabled"
        return JSONResponse(status_code=503, content=body)
    
    return JSONResponse(status_code=http_code, content=body)
```

**Use case:** Load balancers use this to determine if instance should receive traffic.

#### 43.4 Component Probes

Each component has a dedicated probe function in [src/health/components.py](src/health/components.py):

```python
class ComponentStatus(str, Enum):
    OK = "ok"          # Healthy and functional
    DEGRADED = "degraded"  # Functional with warnings
    ERROR = "error"     # Not functional
    UNKNOWN = "unknown"  # Not configured/unreachable

@dataclass
class ComponentCheck:
    ok: bool
    status: ComponentStatus
    latency_ms: int | None = None
    details: dict[str, Any] = field(default_factory=dict)
```

**Component Probe Functions:**

| Component | Probe | Behavior |
|-----------|-------|----------|
| `app` | `probe_app()` | Always OK (process running) |
| `postgres` | `probe_postgres()` | `SELECT 1` with retry/backoff |
| `redis` | `probe_redis()` | `PING` + queue depth check |
| `memgraph` | `probe_memgraph()` | `RETURN 1` query (informational only) |
| `providers` | `probe_providers()` | Provider registry + health status |
| `workers` | `probe_workers()` | Queue depths, backlog threshold |

**PostgreSQL Probe with Retry:**
```python
async def probe_postgres() -> ComponentCheck:
    timeout_ms = config.postgres_timeout_ms
    max_attempts = config.postgres_retries
    backoff_ms = config.postgres_retry_backoff_ms
    
    for attempt in range(1, max_attempts + 1):
        try:
            is_healthy, error_msg = await asyncio.wait_for(
                asyncio.to_thread(check_db_health),
                timeout=timeout_ms / 1000.0
            )
            if is_healthy:
                return ComponentCheck(ok=True, status=ComponentStatus.OK, ...)
        except asyncio.TimeoutError:
            if attempt < max_attempts:
                await asyncio.sleep(backoff_ms / 1000.0)
    
    return ComponentCheck(ok=False, status=ComponentStatus.ERROR, ...)
```

**Redis Probe with Degradation:**
```python
async def probe_redis() -> ComponentCheck:
    global _redis_consecutive_failures
    
    try:
        client = await get_async_redis()
        pong = await asyncio.wait_for(client.ping(), timeout=2.0)
        
        # Get queue depths
        queues = {}
        for job_type in allowed_types:
            queues[job_type] = await client.llen(f"jobs:queue:{job_type}")
        
        _redis_consecutive_failures = 0
        return ComponentCheck(ok=True, status=ComponentStatus.OK, details={"queues": queues})
    
    except (asyncio.TimeoutError, Exception) as e:
        _redis_consecutive_failures += 1
        # First failure = degraded, subsequent = error
        status = ComponentStatus.DEGRADED if _redis_consecutive_failures == 1 else ComponentStatus.ERROR
        return ComponentCheck(ok=status != ComponentStatus.ERROR, status=status, ...)
```

#### 43.5 Readiness Evaluation Policy

```python
def evaluate_readiness(checks: dict[str, ComponentCheck]) -> tuple[str, int]:
    """
    Evaluate overall readiness based on component checks.
    
    Policy:
    - All OK → "ok", 200
    - Any DEGRADED but no ERROR → "degraded", 200
    - Any ERROR in critical components (postgres, redis) → "error", 503
    - Memgraph ERROR → "degraded", 200 (informational only)
    """
```

#### 43.6 Infrastructure Integration

```yaml
# Kubernetes probe configuration
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /health/startup
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 30
```

---

### 44. Testing Strategy

44. **Summarize the testing strategy**: unit, integration, e2e, security, performance; highlight how Postgres/Redis/Memgraph are handled in tests.

The platform has a comprehensive test suite with **272 test files** and **~64,500 lines** of test code, organized in [tests/](tests/) directory.

#### 44.1 Test Categories (Markers)

| Marker | Purpose | Speed | Dependencies |
|--------|---------|-------|--------------|
| `@pytest.mark.unit` | Pure Python logic | <1s each | None |
| `@pytest.mark.integration` | Adapter/service tests | Variable | Fakes or real services |
| `@pytest.mark.e2e` | HTTP API tests | Variable | App or live server |
| `@pytest.mark.performance` | Latency budgets | Skipped by default | None |
| `@pytest.mark.security` | AuthN/Z, rate limits | Variable | None |

**Running tests:**
```bash
pytest -q                        # Full suite
pytest -m "unit"                 # Only unit tests
pytest -m "integration"          # Only integration tests
pytest -m "e2e"                  # Only E2E tests
pytest -m "security"             # Security tests
pytest -m "performance" --runslow  # Performance tests
```

#### 44.2 Test Directory Structure

```
tests/
├── conftest.py              # Global fixtures & markers (1014 lines)
├── fixtures/
│   ├── fake_memgraph.py     # In-memory Memgraph adapter
│   ├── sample_data.py       # Synthetic graph data
│   └── oidc.py              # Token minting for tests
├── unit/                    # Pure logic tests
├── integration/             # Adapter/service tests
├── e2e/                     # HTTP endpoint tests
├── security/                # Auth/rate limit tests
├── performance/             # Latency tests
├── agents/                  # Agent orchestration tests
├── jobs/                    # Job processing tests
├── mcp/                     # MCP tool tests
├── health/                  # Health probe tests
├── db/                      # Database tests
├── api/                     # API contract tests
├── routers/                 # Router-specific tests
└── ...
```

#### 44.3 Database Handling in Tests

**PostgreSQL:**
```python
# From tests/conftest.py
@pytest.fixture
def db_session():
    """Create isolated database session for test."""
    from db.postgres_control.database import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
```

**Redis:**
```python
@pytest.fixture
def redis_fake():
    """In-memory Redis stub when REDIS_URL not reachable."""
    if _can_reach_redis():
        # Use real Redis with unique prefix
        return RealRedisWithNamespace(prefix=f"test:{uuid.uuid4().hex}")
    return FakeRedis()
```

**Memgraph:**
```python
# From tests/fixtures/fake_memgraph.py
class FakeMemgraphAdapter:
    """Deterministic in-memory Memgraph double."""
    
    def __init__(self):
        self._nodes = {}
        self._edges = []
    
    def execute(self, query: str, params: dict = None):
        """Parse Cypher-like queries and return mock results."""
        if "RETURN 1" in query:
            return [{"ok": 1}]
        # ... pattern matching for common queries
```

**Switching to Real Services:**
```bash
# Use real Memgraph
export MG_HOST=localhost MG_PORT=7687
pytest -m "integration" --run-real-memgraph

# Use real Redis
export REDIS_URL=redis://localhost:6379/0
pytest -m "integration"
```

#### 44.4 Fixture Highlights

```python
# Session-scoped event loop
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# FastAPI test client
@pytest.fixture
def app_client():
    from src.app import create_app
    app = create_app()
    return TestClient(app)

# Temporary backup directory
@pytest.fixture
def tmp_backups_dir(tmp_path):
    return tmp_path / "backups"

# Auth0 token fetching (integration tests)
@pytest.fixture(scope="session", autouse=True)
def fetch_auth0_tokens():
    """Fetch fresh Auth0 tokens before test session."""
    # Runs fetch_auth0_tokens.sh for real Auth0 tokens
    ...

# JWKS cache cleanup
@pytest.fixture(autouse=True)
def clear_jwks_cache():
    """Clear JWKS cache to ensure test isolation."""
    from src.security.jwt import _JWKS_CACHE
    _JWKS_CACHE.clear()
    yield
    _JWKS_CACHE.clear()
```

#### 44.5 Test Examples

**Unit Test (PII Scrubbing):**
```python
@pytest.mark.unit
def test_scrub_basic_email():
    text = "Email me at jane.doe@example.com"
    cleaned, findings = scrub(text)
    assert "example.com" not in cleaned
    assert any(f["type"] == "EMAIL" for f in findings)
```

**Integration Test (Archive Round Trip):**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_archive_round_trip(tmp_backups_dir, memgraph_fake):
    svc = ArchiveService(etl=memgraph_fake.etl, base_dir=tmp_backups_dir)
    snap = await svc.snapshot_graph()
    assert snap.ok and snap.data["file"].endswith(".json.gz")
    res = await svc.restore_graph(snap.data["file"])
    assert res.ok
```

**Security Test (Authorization):**
```python
@pytest.mark.security
def test_admin_endpoint_requires_admin_role(app_client, user_token):
    response = app_client.get(
        "/v1/admin/stats",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 403
```

#### 44.6 Coverage and CI

```bash
# Local coverage
coverage run -m pytest -q
coverage html
open htmlcov/index.html

# CI coverage
pytest --maxfail=1 --disable-warnings -q \
    --cov=src --cov-report=term-missing:skip-covered

# Parallel execution
pytest -n auto  # requires pytest-xdist
```

---

### 45. Maintainability and Extensibility

45. **Evaluate maintainability and extensibility**: how easy is it (from the code) to add a new tool, LLM provider, graph domain, or endpoint?

#### 45.1 Adding a New MCP Tool

**Difficulty:** ⭐⭐ Easy

**Steps:**
1. Create module at `src/mcp/tools/<category>/<tool_name>.py`
2. Implement `invoke(payload: dict, ctx: ToolContext) -> dict` function
3. Register tool metadata in module docstring
4. Tool is auto-discovered via naming convention

**Example:**
```python
# src/mcp/tools/custom/my_tool.py
"""
MCP Tool: custom.my_tool

Actions:
- do_something: Performs custom operation
"""

from src.mcp.runtime import ToolContext, mcp_tool

@mcp_tool(
    name="custom.my_tool",
    scopes=["custom:read"],
    timeout_ms=30000,
)
async def invoke(payload: dict, ctx: ToolContext, **kwargs) -> dict:
    action = payload.get("action", "do_something")
    
    if action == "do_something":
        return {"ok": True, "result": "done"}
    
    raise ValueError(f"Unknown action: {action}")
```

**Discovery mechanism:**
```python
# src/mcp/tools/__init__.py
def module_name_for_tool(tool_name: str) -> str:
    """Translate "custom.my_tool" → "src.mcp.tools.custom.my_tool" """
    return f"src.mcp.tools.{tool_name}"

def load(tool_name: str) -> tuple[ModuleType, Callable | None]:
    mod = importlib.import_module(module_name_for_tool(tool_name))
    _, fn = find_callable_in_module(mod)  # looks for invoke, run, handle
    return mod, fn
```

#### 45.2 Adding a New LLM Provider

**Difficulty:** ⭐⭐⭐ Moderate

**Steps:**
1. Add provider configuration to database or settings
2. Implement adapter methods in `src/adapters/llm.py`
3. Register in provider registry
4. Add health probe if needed

**Current adapter pattern:**
```python
# src/adapters/llm.py
_PROVIDER: str = (settings.LLM_PROVIDER or "demo").lower()

def complete(prompt: str, model: str | None, temperature: float, max_tokens: int, **kwargs) -> dict:
    if _PROVIDER == "openai":
        return _openai_complete(prompt, model, temperature, max_tokens, **kwargs)
    elif _PROVIDER == "ollama":
        return _ollama_complete(prompt, model, temperature, max_tokens, **kwargs)
    else:
        return _demo_complete(prompt, model, **kwargs)
```

**To add a new provider (e.g., Anthropic):**
```python
# 1. Add provider detection
_PROVIDER: str = (settings.LLM_PROVIDER or "demo").lower()

# 2. Implement completion function
def _anthropic_complete(prompt: str, model: str, temperature: float, max_tokens: int, **kwargs) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}]
    )
    return {"ok": True, "content": response.content[0].text, ...}

# 3. Register in complete()
def complete(...) -> dict:
    ...
    elif _PROVIDER == "anthropic":
        return _anthropic_complete(prompt, model, temperature, max_tokens, **kwargs)
```

#### 45.3 Adding a New Graph Domain

**Difficulty:** ⭐⭐⭐ Moderate

**Steps:**
1. Define node/edge types in `db/memgraph_domain/`
2. Add schema definitions
3. Create ETL loaders
4. Update NL→Cypher templates in prompt catalog

**Current domain model:**
```
db/memgraph_domain/
├── models/           # Node/edge definitions
├── schema.py         # Graph schema metadata
├── etl/              # ETL loaders
└── queries/          # Common query templates
```

#### 45.4 Adding a New API Endpoint

**Difficulty:** ⭐ Very Easy

**Steps:**
1. Create or extend router in `src/routers/`
2. Define Pydantic schemas in `src/schemas/`
3. Implement business logic in `src/services/`
4. Mount router in `src/app.py`

**Example:**
```python
# src/routers/custom.py
from fastapi import APIRouter, Depends
from src.schemas.custom import CustomRequest, CustomResponse
from src.services.custom import CustomService

router = APIRouter(prefix="/v1/custom", tags=["custom"])

@router.post("/", response_model=CustomResponse)
async def create_custom(
    request: CustomRequest,
    user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = CustomService(db)
    return service.create(request, user)

# src/app.py
from src.routers import custom
app.include_router(custom.router)
```

#### 45.5 Extensibility Summary

| Extension Type | Difficulty | Files to Modify | Auto-Discovery |
|----------------|------------|-----------------|----------------|
| MCP Tool | ⭐⭐ | 1 file | Yes (naming convention) |
| LLM Provider | ⭐⭐⭐ | 1-2 files | No (manual registration) |
| Graph Domain | ⭐⭐⭐ | 3-5 files | No |
| API Endpoint | ⭐ | 2-3 files | No (explicit mount) |
| Background Task | ⭐⭐ | 1 file | No (scheduler registration) |
| Health Probe | ⭐⭐ | 1 file | Yes (component registry) |

---

### 46. Technical Debt and Design Smells

46. **Identify any technical debt or design smells** visible in the current code: where complexity is high, abstractions leaky, or documentation lacking.

#### 46.1 Large Files (God Classes/Modules)

| File | Lines | Issue | Recommendation |
|------|-------|-------|----------------|
| `orchestrator.py` | 8,262 | Monolithic orchestration logic | Split into planner, executor, metrics modules |
| `model_instances.py` | 2,110 | Router does too much | Extract service layer |
| `model_management.py` | 2,097 | Complex router | Extract validation, CRUD helpers |
| `jobs.py` | 2,004 | Large router | Extract job lifecycle helpers |
| `app.py` | 1,930 | App factory too large | Split middleware, router mounting |
| `config.py` | 661 | Flat settings class | Group by domain (db, auth, llm, etc.) |

**Total source code:** ~77,000 lines across 272+ Python files.

#### 46.2 Incomplete TODO Comments

```python
# src/mcp/runtime.py:359
# TODO: Integrate with src.mcp.tools.ratelimit.manage

# src/mcp/tools/graph/secure_query.py:424
return {"cypher": cypher, "params": {}}  # TODO: Extract parameters if needed

# src/routers/admin_db.py:94
# TODO: Parse actual job data

# src/routers/admin_db.py:323
# TODO: Implement actual Memgraph query

# src/routers/admin_ops.py:270
# TODO: Implement actual manifest reading logic
```

These indicate unfinished features that may cause unexpected behavior.

#### 46.3 Tight Coupling to Redis

Redis is used for multiple purposes, creating implicit dependencies:

```python
# Different Redis usages scattered across codebase
- Job queues (jobs:queue:*)
- Idempotency cache (jobs:idempotency:*)
- Rate limiting (ratelimit:*)
- Session state (sessions:*)
- DMR cache (dmr:*)
- Cancel flags (jobs:cancel:*)
```

**Issue:** Redis outage affects all features simultaneously.

**Recommendation:** Introduce abstraction layer or circuit breakers per usage.

#### 46.4 Inconsistent Error Handling

```python
# Some places use custom exceptions
raise ToolError("Operation failed")

# Others use generic HTTPException
raise HTTPException(status_code=500, detail="Operation failed")

# Some use Result pattern
return Result(ok=False, error="Operation failed")

# Others return dicts
return {"ok": False, "error": "Operation failed"}
```

**Recommendation:** Standardize on Result pattern or custom exception hierarchy.

#### 46.5 Missing Type Annotations

```python
# Some functions lack type hints
def process_result(data):  # Missing: data: dict, -> dict
    ...

# JSONB columns lose type safety
todos = Column(JSONB, nullable=True)  # Runtime type is Any
```

**Recommendation:** Enable `mypy --strict` and add comprehensive type annotations.

#### 46.6 Circular Import Risks

```python
# src/config.py imports from src.security
# src/security imports from src.config
# Some modules use lazy imports to avoid cycles

with suppress(Exception):
    from src.logging_setup import get_logger
if "logger" not in globals():
    import logging
    logger = logging.getLogger(__name__)
```

**Recommendation:** Define clear import boundaries, consider dependency injection.

#### 46.7 Test-Production Parity

```python
# Production uses real Redis
from db.redis_cache.client import RedisCache

# Tests may use fake
class FakeRedis:
    def __init__(self):
        self._data = {}
```

**Issue:** Behavior differences between fake and real implementations.

**Recommendation:** Use testcontainers for integration tests, or verify fake behavior matches real.

#### 46.8 Documentation Gaps

| Area | Status | Issue |
|------|--------|-------|
| API Endpoints | ✅ Good | OpenAPI docs comprehensive |
| MCP Tools | ⚠️ Partial | Some tools lack usage examples |
| Configuration | ⚠️ Partial | Not all env vars documented |
| Architecture | ✅ Good | README has detailed diagrams |
| Deployment | ⚠️ Partial | Production hardening not documented |
| Contribution | ❌ Missing | No CONTRIBUTING.md |

#### 46.9 Hardcoded Values

```python
# Magic numbers in code
_OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
timeout=2.0  # 2000ms hardcoded
buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)  # Histogram buckets
```

**Recommendation:** Move to configuration with sensible defaults.

#### 46.10 Technical Debt Summary Table

| Category | Severity | Count | Effort to Fix |
|----------|----------|-------|---------------|
| Large modules | Medium | 6 files | High |
| Incomplete TODOs | Low | 5 items | Medium |
| Redis coupling | Medium | System-wide | High |
| Error handling | Medium | Scattered | Medium |
| Type annotations | Low | ~30% missing | Medium |
| Circular imports | Low | 2-3 cases | Low |
| Test parity | Medium | Redis/Memgraph | Medium |
| Documentation | Low | Partial | Low |
| Hardcoded values | Low | ~20 instances | Low |

#### 46.11 Recommendations Priority

1. **High Priority:**
   - Refactor `orchestrator.py` into smaller modules
   - Add circuit breakers for Redis operations
   - Standardize error handling patterns

2. **Medium Priority:**
   - Complete type annotations (enable mypy strict)
   - Document all configuration options
   - Implement TODO comments or remove them

3. **Low Priority:**
   - Extract hardcoded values to configuration
   - Add CONTRIBUTING.md
   - Improve test-production parity with testcontainers


---

## H. UIs, UX & developer experience (47–50)

---

### **47. Describe the Agent Chat UI architecture (Next.js) and how it interacts with the backend (API endpoints, polling patterns, model selection).**

The Agent Chat UI is a modern, production-grade Next.js 14 application designed as a Copilot-style conversational interface for interacting with AI agents. Its architecture follows React best practices with TypeScript for type safety.

#### **Technology Stack**

| Component | Technology | Version |
|-----------|-----------|---------|
| **Framework** | Next.js (App Router) | 14.2.15 |
| **UI Library** | React | 18.3.1 |
| **State Management** | Zustand | 4.5.5 |
| **UI Components** | Radix UI | Latest |
| **Styling** | Tailwind CSS | 3.4.14 |
| **Icons** | Lucide React | Latest |
| **Type Safety** | TypeScript | 5.x |

Reference: [ui_agent/package.json](ui_agent/package.json)

#### **Component Architecture**

The UI follows a component-based architecture with clear separation of concerns:

```
ui_agent/src/
├── app/
│   ├── page.tsx          # Main chat page with layout
│   ├── layout.tsx        # Root layout with providers
│   ├── globals.css       # Global styles (Tailwind)
│   └── api/              # API routes (auth token proxy)
├── components/
│   ├── chat-area.tsx     # Message display + step rendering
│   ├── chat-input.tsx    # Prompt input + model selector
│   ├── role-toggle.tsx   # Admin/User role switch
│   └── ui/               # Radix UI primitives (Button, Select, etc.)
├── stores/
│   ├── auth-store.ts     # Authentication state (Zustand + persist)
│   └── chat-store.ts     # Chat messages and runs (Zustand)
└── lib/
    ├── api.ts            # Backend API client
    └── utils.ts          # Utility functions
```

Reference: [ui_agent/src/app/page.tsx](ui_agent/src/app/page.tsx)

#### **Main Page Layout**

The main page ([ui_agent/src/app/page.tsx](ui_agent/src/app/page.tsx)) uses a flex-based layout with three key areas:

```tsx
<div className="flex flex-col h-screen">
  {/* Sticky Header - Role Selection */}
  <header className="sticky top-0 z-10 border-b bg-white/80 backdrop-blur-sm">
    <RoleToggle />  {/* Admin/User toggle buttons */}
  </header>
  
  {/* Scrollable Chat Area */}
  <main className="flex-1 overflow-hidden">
    <ChatArea className="flex-1 overflow-y-auto" />
    
    {/* Sticky Input Bar */}
    <ChatInput className="sticky bottom-0" />
  </main>
</div>
```

#### **State Management with Zustand**

The application uses Zustand for lightweight, performant state management with two main stores:

**1. Auth Store** ([ui_agent/src/stores/auth-store.ts](ui_agent/src/stores/auth-store.ts)):
- Manages `role` selection (Admin/User)
- Handles token generation via Next.js API route (`/api/auth/tokens`)
- SSR-safe with hydration detection
- Persists role selection in localStorage (tokens are NOT persisted for security)

```typescript
interface AuthState {
  role: 'admin' | 'user' | null;
  adminToken: string | null;
  userToken: string | null;
  hasHydrated: boolean;
  tokensFetched: boolean;
  tokenError: string | null;
  
  signIn: (role: 'admin' | 'user') => Promise<void>;
  signOut: () => void;
  getActiveToken: () => string | null;
  generateToken: (role) => Promise<string | null>;
}
```

**2. Chat Store** ([ui_agent/src/stores/chat-store.ts](ui_agent/src/stores/chat-store.ts)):
- Manages chat messages (user prompts + agent responses)
- Tracks agent runs with steps, status, and metrics
- Handles auto-scroll behavior

```typescript
interface ChatState {
  messages: ChatMessage[];
  selectedModel: string;
  availableModels: Array<{ id: string; name: string }>;
  currentRunId: string | null;
  isSubmitting: boolean;
  isPolling: boolean;
  
  addUserMessage: (content: string) => string;
  addAgentResponse: (messageId: string, run: AgentRun) => void;
  updateAgentRun: (messageId: string, run: AgentRun) => void;
}
```

#### **Backend API Interaction**

The API client ([ui_agent/src/lib/api.ts](ui_agent/src/lib/api.ts)) provides typed functions for all backend communication:

| Endpoint | Function | Purpose |
|----------|----------|---------|
| `POST /v1/agent-runs` | `createAgentRun()` | Create new agent run |
| `GET /v1/agent-runs/{id}` | `getAgentRun()` | Poll run status |
| `GET /v1/agent-runs/{id}/steps` | `getAgentRunSteps()` | Get execution steps |
| `GET /v1/models/instances` | `listModels()` | List available models |
| `GET /v1/models/defaults` | `getDefaultModel()` | Get default model config |
| `GET /v1/auth/me` | `getAuthMe()` | Validate token |

#### **Polling Pattern**

The chat UI implements a **time-based polling pattern** for agent run completion ([ui_agent/src/lib/api.ts#L190-220](ui_agent/src/lib/api.ts)):

```typescript
export async function pollRunUntilComplete(
  runId: string,
  token: string | null,
  onUpdate: (run: AgentRun) => void,
  intervalMs: number = 2000,    // 2 second intervals
  maxAttempts: number = 300     // 10 minutes max
): Promise<AgentRun> {
  let attempts = 0;
  
  while (attempts < maxAttempts) {
    const run = await getAgentRun(runId, token);
    onUpdate(run);  // Update UI with latest state
    
    // Terminal states
    if (['succeeded', 'failed', 'cancelled'].includes(run.status)) {
      return run;
    }
    
    await new Promise(resolve => setTimeout(resolve, intervalMs));
    attempts++;
  }
  
  throw new Error(`Polling timed out after ${maxAttempts} attempts`);
}
```

**Key characteristics:**
- **Interval**: 2 seconds between polls
- **Timeout**: 10 minutes maximum (300 attempts)
- **Real-time updates**: `onUpdate` callback updates the UI on each poll
- **Status tracking**: Continues until `succeeded`, `failed`, or `cancelled`

#### **Model Selection Flow**

The chat input component ([ui_agent/src/components/chat-input.tsx](ui_agent/src/components/chat-input.tsx)) handles model selection:

1. **On role change**: Fetches available models from `/v1/models/instances`
2. **Default resolution**: Queries `/v1/models/defaults` for backend-configured default
3. **Fallback logic**: If backend default exists, use it; otherwise use first available model
4. **User override**: Dropdown allows selecting any loaded/enabled model

```typescript
// Load models on role change
useEffect(() => {
  const loadModels = async () => {
    // 1. Get backend default model
    const defaultModel = await getDefaultModel(token);
    
    // 2. List all available instances
    const response = await listModels(token);
    const models = response.items
      .filter(m => m.enabled && m.loaded)
      .map(m => ({ id: m.id, name: m.instance_name }));
    
    // 3. Set default (backend preference → first available)
    if (defaultModel?.chat?.instance_id) {
      setSelectedModel(defaultModel.chat.instance_id);
    } else {
      setSelectedModel(models[0].id);
    }
  };
  loadModels();
}, [role, isReady]);
```

#### **Chat Message Display**

The chat area ([ui_agent/src/components/chat-area.tsx](ui_agent/src/components/chat-area.tsx)) renders messages with rich step visualization:

- **User messages**: Simple text bubbles
- **Agent responses**: Full run timeline with:
  - Status indicators (loading spinner, success checkmark, error X)
  - Step-by-step execution display
  - Tool calls with inputs/outputs
  - Cypher query syntax highlighting
  - Collapsible JSON outputs
  - Execution metrics (latency, tokens)

```typescript
// Step merging logic for combined display
function mergeStepsAndOutputs(
  steps: OrchestrationStep[],
  outputs: OrchestrationStep[]
): OrchestrationStep[] {
  // Combines step actions with their corresponding outputs
  // for a unified timeline view
}
```

---

### **48. Describe the Control Panel UI architecture (Streamlit) and how it uses the API to provide dashboards, jobs view, tool exploration, and graph/NL→Cypher testing.**

The Control Panel UI is a comprehensive Streamlit-based administration and operations interface providing full API coverage with role-aware access control.

#### **Technology Stack**

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | Streamlit | Rapid Python web apps |
| **Authentication** | Auth0 | OAuth2/OIDC |
| **HTTP Client** | httpx | Async-capable requests |
| **Data Display** | Pandas | Tabular data |
| **Visualization** | Plotly (via Streamlit) | Charts/graphs |

Reference: [ui_control_panel/app.py](ui_control_panel/app.py)

#### **Application Structure**

```
ui_control_panel/
├── app.py              # Main Streamlit entry point
├── api.py              # API client with auth handling
├── state.py            # Session state management
├── components.py       # Reusable UI components
└── views/
    ├── auth.py         # Authentication tab
    ├── dashboard.py    # Health monitoring
    ├── agents.py       # Agent runs & sessions
    ├── tools.py        # Tool discovery & invocation
    ├── models.py       # Model management
    ├── jobs.py         # Job management
    ├── tenants.py      # Multi-tenancy CRUD
    ├── admin.py        # Admin operations
    ├── cypher.py       # NL→Cypher workflow
    └── explore.py      # API explorer
```

Reference: [ui_control_panel/README.md](ui_control_panel/README.md)

#### **Main Application Flow**

The main app ([ui_control_panel/app.py](ui_control_panel/app.py)) follows this initialization sequence:

```python
# 1. Page configuration
st.set_page_config(
    page_title="Cineca Agentic Platform",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Custom CSS for responsive design
inject_custom_css()  # Breakpoints at 1024px, 768px, 480px

# 3. State initialization
init_state()  # Session state with auth tokens, settings

# 4. Auto token renewal
check_and_renew_tokens()  # Refresh before expiry

# 5. API health check
run_self_test()  # Verify backend connectivity

# 6. Tab-based navigation
tabs = st.tabs([
    "🔐 Auth", "📊 Dashboard", "🤖 Agents", "🔧 Tools",
    "🧠 Models", "📋 Jobs", "🏢 Tenants", "⚙️ Admin",
    "🔍 Cypher", "🌐 Explore"
])
```

#### **Authentication System**

The Control Panel supports **four identity types** with Auth0 integration:

| Identity Type | Auth Method | Use Case |
|--------------|-------------|----------|
| **Admin** | Password Realm | Full platform administration |
| **User** | Password Realm | Normal user operations |
| **Machine** | Client Credentials | Service-to-service |
| **Custom** | Manual token | Testing/debugging |

**Scope-Based Access Control** ([ui_control_panel/README.md#L94-110](ui_control_panel/README.md)):

| Tab/Feature | Required Scopes |
|-------------|----------------|
| Dashboard | None (public health endpoints) |
| Agents | `user:me` |
| Tools (Safe) | `tools:invoke:basic` |
| Tools (All) | `tools:invoke:all` |
| Models (Create) | `admin:all` |
| Tenants | `admin:all` |
| Admin | `admin:all` |

#### **API Client Architecture**

The API client ([ui_control_panel/api.py](ui_control_panel/api.py)) provides robust backend communication:

**Key Features:**
1. **Endpoint Normalization**: All paths normalized to `/v1/*` prefix
2. **Token Masking**: Tokens masked in logs (first 8 + last 8 chars)
3. **Header Building**: Authorization + X-Tenant-ID injection
4. **Response Handling**: JSON parsing with 401/4xx/5xx handling

```python
def normalize_endpoint(endpoint: str) -> str:
    """Ensure all endpoints start with /v1/"""
    if not endpoint.startswith('/'):
        endpoint = '/' + endpoint
    if not endpoint.startswith('/v1'):
        endpoint = '/v1' + endpoint
    return endpoint

def get_headers() -> dict:
    """Build request headers with auth and tenant context"""
    headers = {"Content-Type": "application/json"}
    token = get_active_token()
    if token:
        headers["Authorization"] = f"Bearer {token.value}"
    tenant_id = get_state().tenant_id
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    return headers
```

#### **Dashboard Tab - Health Monitoring**

The dashboard ([ui_control_panel/views/dashboard.py](ui_control_panel/views/dashboard.py)) provides real-time system health:

**Health Endpoints Monitored:**

| Endpoint | Purpose | Display |
|----------|---------|---------|
| `/v1/health/live` | Liveness probe | ✅/❌ status card |
| `/v1/health/ready` | Readiness probe | ✅/❌ status card |
| `/v1/health/startup` | Startup probe | ✅/❌ status card |
| `/v1/health/components` | Component health | Grid of cards |

**Auto-Refresh Implementation:**
```python
# Non-blocking auto-refresh using session state
if auto_refresh:
    if "last_health_refresh" not in st.session_state:
        st.session_state.last_health_refresh = time.time()
    
    elapsed = time.time() - st.session_state.last_health_refresh
    if elapsed >= 30:  # 30-second interval
        st.session_state.last_health_refresh = time.time()
        st.rerun()
```

#### **Agents Tab - Copilot-Style Runs**

The agents view ([ui_control_panel/views/agents.py](ui_control_panel/views/agents.py)) provides a full agent execution interface:

**Features:**
- **Run Creator**: Form with prompt, model selection, temperature, max steps
- **Session Management**: Create/list/cancel sessions
- **Real-Time Monitoring**: Progress bar with step-by-step timeline
- **Result Display**: Final answer + execution metrics

**Run Creation Flow:**
```python
run_data = {
    "prompt": prompt,
    "max_steps": max_steps,
    "temperature": temperature,
}

if selected_instance_id != default_instance_id:
    run_data["manager"] = selected_instance_id

success, data, error = create_agent_run(run_data)

if success:
    run_id = data.get("run_id")
    _monitor_agent_run(run_id, run_data)  # Start polling
```

**Polling with Jitter:**
```python
# Jittered polling to prevent thundering herd
timeout_seconds = 120
base_poll_interval = 0.5  # Start with 500ms

for poll_count in range(max_polls):
    success, data, error = get_agent_run(run_id)
    status = data.get("status")
    
    if status in ["completed", "failed", "cancelled"]:
        break
    
    sleep_with_jitter(base_poll_interval)  # Randomized delay
```

#### **Tools Tab - Discovery & Invocation**

The tools view ([ui_control_panel/views/tools.py](ui_control_panel/views/tools.py)) provides:

**Sub-Tabs:**
1. **Discover Tools**: List all tools with capability filtering
2. **Invoke Tool**: Schema-driven form generation for tool execution
3. **Test All Tools**: Batch testing of tool availability

**Capability-Based Filtering:**
```python
# Filter tools by capabilities
restricted_caps = {"writes_db", "model_management", "admin"}

if any(cap in restricted_caps for cap in tool.capabilities):
    required_scopes = ["tools:invoke:all", "admin:all"]
else:
    required_scopes = ["tools:invoke:basic", "tools:invoke:all"]
```

#### **Cypher Tab - NL→Cypher Workflow**

The Cypher view ([ui_control_panel/views/cypher.py](ui_control_panel/views/cypher.py)) provides natural language to Cypher conversion:

**Workflow:**
1. **Query Builder**: Natural language input with example questions
2. **Schema Explorer**: Graph schema visualization
3. **Query History**: Previous queries with results

**Execution Flow:**
```python
def _execute_nl_to_cypher(natural_language: str):
    # Step 1: Invoke NL→Cypher tool
    success, data, error = invoke_tool(
        "memgraph.nl_to_cypher",
        {"natural_language": natural_language}
    )
    
    # Step 2: Get execution ID
    eid = data.get("execution_id")
    
    # Step 3: Poll for results
    result_data = _poll_for_cypher_result(eid)
    
    # Step 4: Display generated Cypher + results
    _display_cypher_execution_result(natural_language, result_data)
```

#### **Jobs Tab - Async Job Management**

The jobs view ([ui_control_panel/views/jobs.py](ui_control_panel/views/jobs.py)) handles asynchronous operations:

**Features:**
- **User Jobs**: Personal job creation and monitoring
- **Admin Jobs**: Full job administration (requires `admin:all`)
- **Event Streaming**: Real-time job progress updates
- **Filtering**: By status (pending/running/completed/failed/cancelled), job type

```python
def render_jobs_tab():
    token = get_active_token()
    has_admin = token and "admin:all" in token.scopes
    
    if has_admin:
        sub_tabs = st.tabs(["📋 My Jobs", "⚙️ Admin Jobs"])
        with sub_tabs[0]:
            _render_user_jobs()
        with sub_tabs[1]:
            _render_admin_jobs()
    else:
        _render_user_jobs()
```

#### **Explore Tab - API Explorer**

The explore view ([ui_control_panel/views/explore.py](ui_control_panel/views/explore.py)) provides:

- **Root Endpoint**: API version and metadata
- **OpenAPI Spec**: View/download API specification
- **Raw Request Inspector**: Execute arbitrary API requests (with SSRF protection)

```python
# SSRF protection - only /v1/* paths allowed
def is_safe_path(path: str) -> bool:
    return path.startswith("/v1/")
```

---

### **49. From a UX and developer-experience standpoint, list the key advantages and limitations of having both a Next.js chat UI and a Streamlit control panel.**

#### **Advantages**

| Category | Advantage | Details |
|----------|-----------|---------|
| **Persona Targeting** | **Optimal UX per user type** | Chat UI for end-users (conversational), Control Panel for admins/operators (data-driven) |
| **Technology Fit** | **Right tool for the job** | Next.js excels at real-time interactive experiences; Streamlit excels at rapid admin tool development |
| **Development Velocity** | **Faster iteration on admin features** | Streamlit's Python-native approach allows quick feature additions without frontend expertise |
| **Separation of Concerns** | **Independent deployment** | UIs can be versioned, deployed, and scaled independently |
| **Skill Utilization** | **Leverages team strengths** | Backend Python developers can contribute to Control Panel; frontend specialists focus on Chat UI |
| **Maintenance** | **Focused codebases** | Each UI has a single purpose, reducing complexity |
| **Testing** | **Easier to test in isolation** | Each UI can be tested independently with mocked backends |

**Specific UX Advantages:**

**Next.js Chat UI:**
- Fast initial page load (SSR/SSG)
- Smooth real-time updates without page refreshes
- Modern component library (Radix UI) for accessibility
- Type-safe with TypeScript
- Auto-scroll behavior for chat experience
- Keyboard shortcuts (Enter to send)

**Streamlit Control Panel:**
- Zero JavaScript knowledge required for Python developers
- Automatic reactive updates on state changes
- Built-in data display components (tables, charts)
- Easy form handling and validation
- Tab-based navigation for complex workflows
- JSON drawer components for debugging

#### **Limitations**

| Category | Limitation | Impact |
|----------|------------|--------|
| **Cognitive Load** | **Two UIs to learn** | Users who need both may face learning curve |
| **Consistency** | **Different look and feel** | No unified design system across UIs |
| **Maintenance** | **Duplicate API wrappers** | API client logic in both TypeScript and Python |
| **Deployment** | **Multiple containers/processes** | Increased operational complexity |
| **Feature Parity** | **Risk of drift** | New API features may appear in one UI before the other |
| **Testing** | **E2E testing complexity** | Full user journeys may span both UIs |
| **Documentation** | **Two sets of docs** | Users need guidance on which UI to use when |

**Specific Technical Limitations:**

**Next.js Chat UI:**
- Requires Node.js runtime
- More complex build pipeline (webpack/turbopack)
- SSR hydration complexity
- Token management across server/client

**Streamlit Control Panel:**
- Single-threaded Python (scaling limitations)
- Page refresh on every interaction (perceived latency)
- Limited customization compared to full React
- No offline support
- Session state not persisted across refreshes

#### **Developer Experience Analysis**

| Aspect | Next.js Chat UI | Streamlit Control Panel |
|--------|-----------------|------------------------|
| **Setup Time** | 10-15 min (npm install) | 2-5 min (pip install) |
| **Hot Reload** | Fast (Next.js) | Good (Streamlit) |
| **Type Safety** | Excellent (TypeScript) | Limited (Python hints) |
| **Component Reuse** | High (Radix + custom) | Medium (built-in only) |
| **State Debugging** | DevTools + Zustand | Print statements + UI |
| **API Mocking** | MSW, custom handlers | Python mocks |
| **Learning Curve** | Steeper (React/TS) | Gentle (Python only) |

#### **Recommendations**

1. **Consider a shared design token system** (colors, spacing) for visual consistency
2. **Implement an API SDK** that both UIs consume to reduce duplication
3. **Document user journeys** clearly indicating when to use each UI
4. **Align feature releases** to prevent capability gaps

---

### **50. Considering all the above code-level analysis, provide a consolidated list of the project's main advantages and disadvantages, and compare them explicitly with current state-of-the-art agentic / orchestration systems (e.g., LangChain, LlamaIndex, Semantic Kernel, OpenAI Assistants, AutoGen, crewAI), highlighting where this project is ahead, on par, or behind.**

#### **Project Advantages (Consolidated)**

| # | Advantage | Code Evidence |
|---|-----------|---------------|
| 1 | **Production-Grade Architecture** | Docker-compose orchestration, health probes, graceful shutdown, proper logging |
| 2 | **Enterprise Multi-Tenancy** | `X-Tenant-ID` header propagation, tenant-scoped data isolation, scope-based auth |
| 3 | **Comprehensive Observability** | Prometheus metrics, Grafana dashboards, structured logging, trace ID propagation |
| 4 | **Robust Security** | Auth0 OAuth2/OIDC, scope-based permissions, SSRF protection, token masking |
| 5 | **Flexible Model Management** | Hot-swappable models, model defaults hierarchy (user→tenant→global), provider abstraction |
| 6 | **Graph-Powered Knowledge** | Memgraph integration, NL→Cypher, schema-aware queries, relationship modeling |
| 7 | **Async Job Infrastructure** | PostgreSQL-backed queue, event streaming, idempotency keys, job lifecycle management |
| 8 | **Extensible Tool System** | Capability-based access, schema-driven invocation, audit logging |
| 9 | **Dual-UI Strategy** | Optimized for different personas (chat vs. admin) |
| 10 | **Modern Python Stack** | FastAPI, Pydantic v2, async/await, proper typing |
| 11 | **MCP Integration** | Model Context Protocol support for tool sharing |
| 12 | **Comprehensive Testing** | 85%+ coverage, pytest fixtures, E2E with Playwright |

#### **Project Disadvantages (Consolidated)**

| # | Disadvantage | Impact |
|---|-------------|--------|
| 1 | **Incomplete Orchestrator** | Core `orchestrator.run()` returns demo output; real reasoning loop not fully implemented |
| 2 | **Limited Streaming** | No SSE/WebSocket for real-time step output (polling only) |
| 3 | **Single Memgraph Dependency** | Graph queries tied to Memgraph; no graph DB abstraction |
| 4 | **No Built-in RAG Pipeline** | Document ingestion, chunking, embedding not implemented |
| 5 | **Limited Agent Types** | ReAct pattern only; no plan-and-execute, tree-of-thought variants |
| 6 | **No Multi-Agent Collaboration** | No native support for agent-to-agent communication |
| 7 | **Missing Conversation Memory** | Session steps stored but no semantic/summary memory |
| 8 | **Dual UI Maintenance** | Two codebases with API wrapper duplication |
| 9 | **Complex Deployment** | 8+ containers (app, postgres, redis, memgraph, prometheus, grafana, nginx, ui) |
| 10 | **Documentation Gaps** | Architecture decisions not always documented (ADRs partial) |

---

#### **Comparison with State-of-the-Art Systems**

##### **1. LangChain**

| Feature | LangChain | This Project | Assessment |
|---------|-----------|--------------|------------|
| **Agent Types** | ReAct, Plan-and-Execute, Self-Ask, BabyAGI, AutoGPT | ReAct only | 🔴 **Behind** |
| **Tool Ecosystem** | 100+ integrations | ~15 built-in tools | 🔴 **Behind** |
| **Memory Systems** | Buffer, Summary, Knowledge Graph, Entity | Session steps only | 🔴 **Behind** |
| **Streaming** | Full callback + async streaming | Polling only | 🔴 **Behind** |
| **RAG Pipeline** | Document loaders, splitters, retrievers | Not implemented | 🔴 **Behind** |
| **Multi-Tenancy** | Not built-in (requires custom) | Native X-Tenant-ID | 🟢 **Ahead** |
| **Production Deployment** | Requires LangServe/custom | Docker-compose ready | 🟢 **Ahead** |
| **Observability** | LangSmith (paid) | Open Prometheus/Grafana | 🟢 **Ahead** |
| **Enterprise Security** | Basic | OAuth2 + RBAC + scopes | 🟢 **Ahead** |
| **Graph Integration** | Community packages | Native Memgraph + NL→Cypher | 🟢 **Ahead** |

**Summary**: LangChain leads in agent variety and ecosystem; this project leads in production infrastructure and enterprise features.

---

##### **2. LlamaIndex**

| Feature | LlamaIndex | This Project | Assessment |
|---------|-----------|--------------|------------|
| **Data Ingestion** | 160+ loaders | Not implemented | 🔴 **Behind** |
| **Index Types** | Vector, List, Tree, Keyword | Graph-based only | 🔴 **Behind** |
| **Query Engines** | Sophisticated routing | Simple NL→Cypher | 🔴 **Behind** |
| **Agent Protocol** | Supports many LLMs | Multi-provider (Ollama, OpenAI, HF) | 🟡 **On Par** |
| **Response Synthesis** | Tree-summarize, refine | Direct LLM output | 🔴 **Behind** |
| **Multi-Tenancy** | Not built-in | Native | 🟢 **Ahead** |
| **Observability** | Integration-based | Native Prometheus | 🟢 **Ahead** |
| **Enterprise Auth** | Not built-in | OAuth2 + RBAC | 🟢 **Ahead** |

**Summary**: LlamaIndex excels at data indexing and retrieval; this project leads in deployment and security.

---

##### **3. Semantic Kernel (Microsoft)**

| Feature | Semantic Kernel | This Project | Assessment |
|---------|----------------|--------------|------------|
| **Language Support** | C#, Python, Java | Python only | 🔴 **Behind** |
| **Plugin System** | Strongly typed skills | Capability-based tools | 🟡 **On Par** |
| **Planner** | Stepwise, Sequential, Action | ReAct only | 🔴 **Behind** |
| **Memory** | Semantic memory + embeddings | Session-based | 🔴 **Behind** |
| **Azure Integration** | Native | Not built-in | 🔴 **Behind** |
| **Multi-Tenancy** | Azure AD | Native X-Tenant-ID | 🟡 **On Par** |
| **Open Source Stack** | Partially (Azure deps) | Fully open (no cloud lock-in) | 🟢 **Ahead** |
| **Graph Database** | Not built-in | Native Memgraph | 🟢 **Ahead** |

**Summary**: Semantic Kernel has better enterprise Microsoft integration; this project is more open and graph-native.

---

##### **4. OpenAI Assistants API**

| Feature | OpenAI Assistants | This Project | Assessment |
|---------|------------------|--------------|------------|
| **Setup Complexity** | SaaS (instant) | Self-hosted (complex) | 🔴 **Behind** |
| **Tool Calling** | Native function calling | Custom orchestrator | 🟡 **On Par** |
| **File Search** | Built-in vector search | Not implemented | 🔴 **Behind** |
| **Code Interpreter** | Sandboxed execution | Not implemented | 🔴 **Behind** |
| **Streaming** | Native SSE | Polling only | 🔴 **Behind** |
| **Model Choice** | OpenAI only | Multi-provider | 🟢 **Ahead** |
| **Data Sovereignty** | US-based (OpenAI) | Self-hosted (any region) | 🟢 **Ahead** |
| **Cost Control** | Usage-based | Fixed infrastructure | 🟢 **Ahead** |
| **Customization** | Limited | Full code access | 🟢 **Ahead** |
| **Multi-Tenancy** | Organization-level | Fine-grained tenants | 🟢 **Ahead** |

**Summary**: OpenAI Assistants is easier to start; this project offers more control, privacy, and customization.

---

##### **5. AutoGen (Microsoft)**

| Feature | AutoGen | This Project | Assessment |
|---------|---------|--------------|------------|
| **Multi-Agent** | Native agent conversations | Single-agent orchestrator | 🔴 **Behind** |
| **Agent Roles** | Configurable personas | User-defined roles | 🟡 **On Par** |
| **Code Execution** | Docker-based sandbox | Not implemented | 🔴 **Behind** |
| **Human-in-Loop** | Built-in approval flows | Not implemented | 🔴 **Behind** |
| **Production Ready** | Research-oriented | Production architecture | 🟢 **Ahead** |
| **Enterprise Auth** | Not built-in | OAuth2 + RBAC | 🟢 **Ahead** |
| **Observability** | Logging only | Full metrics stack | 🟢 **Ahead** |
| **Persistence** | In-memory | PostgreSQL + Redis | 🟢 **Ahead** |

**Summary**: AutoGen leads in multi-agent scenarios; this project leads in production-readiness and persistence.

---

##### **6. crewAI**

| Feature | crewAI | This Project | Assessment |
|---------|--------|--------------|------------|
| **Multi-Agent Teams** | Native crews + roles | Single-agent | 🔴 **Behind** |
| **Agent Delegation** | Built-in task handoff | Not implemented | 🔴 **Behind** |
| **Process Types** | Sequential, hierarchical | Step-by-step only | 🔴 **Behind** |
| **Tool Sharing** | Native between agents | MCP-based (single agent) | 🔴 **Behind** |
| **Production Features** | Minimal | Comprehensive | 🟢 **Ahead** |
| **Enterprise Security** | Not built-in | OAuth2 + RBAC + scopes | 🟢 **Ahead** |
| **Persistence** | File-based | PostgreSQL + Redis + Memgraph | 🟢 **Ahead** |
| **Observability** | Basic logging | Prometheus + Grafana | 🟢 **Ahead** |

**Summary**: crewAI excels at multi-agent workflows; this project leads in enterprise infrastructure.

---

#### **Consolidated Comparison Matrix**

| Capability | LangChain | LlamaIndex | Semantic Kernel | OpenAI Assistants | AutoGen | crewAI | **This Project** |
|------------|-----------|------------|-----------------|-------------------|---------|--------|-----------------|
| Multi-Agent | 🟡 | 🔴 | 🔴 | 🔴 | 🟢 | 🟢 | 🔴 |
| RAG Pipeline | 🟢 | 🟢 | 🟡 | 🟢 | 🔴 | 🔴 | 🔴 |
| Memory Systems | 🟢 | 🟢 | 🟢 | 🟢 | 🟡 | 🟡 | 🔴 |
| Streaming | 🟢 | 🟢 | 🟢 | 🟢 | 🟡 | 🟡 | 🔴 |
| Multi-Tenancy | 🔴 | 🔴 | 🟡 | 🟡 | 🔴 | 🔴 | 🟢 |
| Enterprise Auth | 🔴 | 🔴 | 🟢 | 🟡 | 🔴 | 🔴 | 🟢 |
| Observability | 🟡 | 🟡 | 🟡 | 🔴 | 🔴 | 🔴 | 🟢 |
| Graph Integration | 🔴 | 🟡 | 🔴 | 🔴 | 🔴 | 🔴 | 🟢 |
| Self-Hosted | 🟢 | 🟢 | 🟡 | 🔴 | 🟢 | 🟢 | 🟢 |
| Production Ready | 🟡 | 🟡 | 🟢 | 🟢 | 🔴 | 🔴 | 🟢 |

**Legend**: 🟢 Strong | 🟡 Partial | 🔴 Weak/Missing

---

#### **Strategic Positioning Summary**

**This project is AHEAD in:**
- Enterprise-grade multi-tenancy and security
- Self-hosted observability with open tools
- Graph database integration with NL→Cypher
- Production deployment architecture
- Model provider flexibility

**This project is ON PAR in:**
- Tool/plugin extensibility
- Basic agent orchestration patterns
- API-first design

**This project is BEHIND in:**
- Multi-agent collaboration
- RAG and document processing
- Advanced memory systems
- Real-time streaming
- Agent type variety (ReAct only)

**Recommended Roadmap Priorities:**
1. Implement SSE/WebSocket streaming for real-time step output
2. Add conversation memory (summary + semantic)
3. Build document ingestion and vector search (RAG)
4. Extend agent types (plan-and-execute, tree-of-thought)
5. Consider multi-agent capability for complex workflows