# Cineca Agentic Platform — Unified Architecture Diagram

A single, comprehensive view of the platform's architecture, components, and workflows.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    IDENTITY & AUTH                                          │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                        Identity Provider (OIDC / Auth0)                               │  │
│  │                    OAuth login · JWT tokens · JWKS for verification                   │  │
│  └───────────────────────────────────────────────────────────────────────────────────────┘  │
│                                           │                                                 │
│                          ┌────────────────┴────────────────┐                                │
│                          ▼                                 ▼                                │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     CLIENTS & UIs                                           │
│  ┌────────────────────────────────┐        ┌─────────────────────────────────────────────┐  │
│  │      Agent Chat UI             │        │           Control Panel UI                  │  │
│  │      (Next.js / React)         │        │           (Streamlit)                       │  │
│  │  ─────────────────────────     │        │  ─────────────────────────────────────────  │  │
│  │  • End user chat interface     │        │  • Admin/Operator dashboard                 │  │
│  │  • JWT-based authentication    │        │  • Jobs, models, tools management           │  │
│  │  • Agent runs & steps display  │        │  • Graph/NL→Cypher experiments              │  │
│  └────────────────────────────────┘        └─────────────────────────────────────────────┘  │
│                          │                                 │                                │
│                          └────────────┬────────────────────┘                                │
│                                       ▼                                                     │
│                    ┌──────────────────────────────────────────┐                             │
│                    │   Reverse Proxy / API Gateway (NGINX)    │                             │
│                    │   TLS termination · Routing · CORS       │                             │
│                    └──────────────────────────────────────────┘                             │
│                                       │                                                     │
└───────────────────────────────────────┼─────────────────────────────────────────────────────┘
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                            FASTAPI BACKEND APPLICATION                                      │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                              API LAYER (Routers)                                    │    │
│  │  /v1/health  /v1/auth  /v1/agents  /v1/agent-runs  /v1/tools  /v1/jobs             │    │
│  │  /v1/models  /v1/admin  /v1/tenants  /v1/batch  /v1/export  /v1/internal           │    │
│  └─────────────────────────────────────────────────────────────────────────────────────┘    │
│                                          │                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                         SECURITY & CROSS-CUTTING MIDDLEWARE                         │    │
│  │  JWT/OIDC validation · RBAC & Scopes · Rate Limiting (Redis) · Multi-tenancy       │    │
│  │  PII Scrubbing · Output Guard · Audit Logging · Tracing · Correlation IDs          │    │
│  └─────────────────────────────────────────────────────────────────────────────────────┘    │
│                                          │                                                  │
│  ┌──────────────────────────────────┐ ┌──────────────────────────────────────────────┐      │
│  │       SERVICE LAYER              │ │            MCP RUNTIME & TOOLS               │      │
│  │  ────────────────────────────    │ │  ──────────────────────────────────────────  │      │
│  │  • Orchestrator Service          │ │  • Tool Registry (34 tools, 17 categories)  │      │
│  │    - Intent Classifier           │ │  • Tool Policies (RBAC per tool)            │      │
│  │    - Multi-step planner          │ │  • MCP Runtime (ToolContext, audit)         │      │
│  │    - Modes: CHAT/GRAPH/ADMIN/    │ │  • Tool Families:                           │      │
│  │      SECURITY/DANGEROUS          │ │    graph.* cache.* data.* security.*        │      │
│  │  • Session Service               │◀┼─▶   system.* model.* output.* admin.*       │      │
│  │  • Job Service                   │ │      tenancy.* session.* user.* viz.*       │      │
│  │  • Default Model Resolver        │ │      privacy.* ratelimit.* catalog.*        │      │
│  │  • Health / ETL / Archive        │ │                                              │      │
│  │  • Invocation Store              │ │                                              │      │
│  └──────────────────────────────────┘ └──────────────────────────────────────────────┘      │
│                   │                                    │                                    │
│  ┌────────────────┴────────────────────────────────────┴────────────────────────────┐       │
│  │                        ADAPTERS & RESILIENCE FRAMEWORK                           │       │
│  │  ─────────────────────────────────────────────────────────────────────────────   │       │
│  │  • LLM Adapters (OpenAI-style, Ollama, stub/demo)                                │       │
│  │  • Resilience: Circuit Breakers · Retries · Cost Tracking · Provider Fallback   │       │
│  │  • Memgraph Adapter (graph queries, NL→Cypher pipeline)                          │       │
│  │  • Redis Adapter (cache, queues, rate limits, state)                             │       │
│  └──────────────────────────────────────────────────────────────────────────────────┘       │
│                   │                         │                        │                      │
│  ┌────────────────┴──────────┐  ┌───────────┴──────────┐  ┌──────────┴──────────────┐       │
│  │  PostgreSQL Repositories  │  │   Redis Integration  │  │ Memgraph Domain Layer  │       │
│  │  ────────────────────     │  │   ─────────────────  │  │ ──────────────────────  │       │
│  │  Tenants · Providers      │  │  Cache (sessions,    │  │  Domain Graph Schema   │       │
│  │  Models · Agent Runs      │  │    configs)          │  │  (User, Task, File,    │       │
│  │  Sessions · Steps         │  │  Job Queues & Events │  │   Institution nodes)   │       │
│  │  Jobs · Job Events        │  │  Rate-limit counters │  │  NL→Cypher Pipeline:   │       │
│  │  Tools · Manifests        │  │  Session state       │  │   • NL normalization   │       │
│  │  Audit Logs · Idempotency │  │  Cancellation flags  │  │   • Cypher generation  │       │
│  │  SQLAlchemy + Alembic     │  │  Idempotency keys    │  │   • Safety validation  │       │
│  └───────────────────────────┘  └──────────────────────┘  │   • Query execution    │       │
│                                                           │   • Result summary     │       │
│  ┌────────────────────────────────────────────────────┐   └────────────────────────┘       │
│  │            BACKGROUND FRAMEWORK (APScheduler)      │                                     │
│  │  Health checks (Postgres, Redis, Memgraph, LLMs)   │                                     │
│  │  Backups (Memgraph archives) · Cleanup (stale data)│                                     │
│  │  Provider monitoring · Metrics emission            │                                     │
│  └────────────────────────────────────────────────────┘                                     │
│                                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐     │
│  │                        OBSERVABILITY FRAMEWORK                                     │     │
│  │  Prometheus /metrics · OpenTelemetry tracing (OTLP) · Structured logging          │     │
│  │  Health endpoints: /v1/health/live · /ready · /startup · /components              │     │
│  └────────────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                           │                    │                    │
           ┌───────────────┘                    │                    └───────────────┐
           ▼                                    ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                               DATA & INFRASTRUCTURE LAYER                                   │
│  ┌─────────────────────────┐  ┌─────────────────────┐  ┌──────────────────────────────┐     │
│  │       PostgreSQL        │  │        Redis        │  │         Memgraph             │     │
│  │    (Control Plane)      │  │   (Cache & Queues)  │  │      (Graph Database)        │     │
│  │  ─────────────────────  │  │  ─────────────────  │  │  ──────────────────────────  │     │
│  │  • Tenants & configs    │  │  • Entity cache     │  │  • Domain graph (nodes,     │     │
│  │  • Agent runs & steps   │  │  • Job queues       │  │    edges, relationships)    │     │
│  │  • Jobs & job events    │  │  • SSE event buffer │  │  • Cypher query execution   │     │
│  │  • Providers & models   │  │  • Rate-limit data  │  │  • Graph analytics          │     │
│  │  • Manifests & defaults │  │  • Session state    │  │  • ETL import/export        │     │
│  │  • Audit & idempotency  │  │  • Cancel flags     │  │                              │     │
│  └─────────────────────────┘  └─────────────────────┘  └──────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   WORKER PROCESSES                                          │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              Job Processing Worker                                    │  │
│  │  ─────────────────────────────────────────────────────────────────────────────────    │  │
│  │  • Pop job IDs from Redis queue                                                       │  │
│  │  • Load job metadata from PostgreSQL                                                  │  │
│  │  • Execute handlers: ETL, backups, maintenance, long-running tasks                   │  │
│  │  • Check cancellation flags periodically                                              │  │
│  │  • Update job status & emit events → SSE streaming to clients                        │  │
│  │  • Uses same adapters/services as main app                                            │  │
│  └───────────────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   LLM PROVIDERS                                             │
│  ┌────────────────────┐  ┌────────────────────┐  ┌───────────────────────────────────────┐  │
│  │   Ollama (Local)   │  │      OpenAI        │  │  Azure OpenAI / Other Providers      │  │
│  │  ────────────────  │  │  ────────────────  │  │  ─────────────────────────────────   │  │
│  │  Local LLM hosting │  │  Cloud LLM API     │  │  Compatible OpenAI-style APIs        │  │
│  └────────────────────┘  └────────────────────┘  └───────────────────────────────────────┘  │
│                                                                                             │
│                    ▲ Called via Adapters & Resilience Framework ▲                          │
│                      (circuit breakers, cost tracking, fallback)                            │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                              OBSERVABILITY & MONITORING                                     │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌─────────────────────────────────┐  │
│  │      Prometheus       │  │       Grafana         │  │     OTEL Collector / APM       │  │
│  │  ───────────────────  │  │  ───────────────────  │  │  ─────────────────────────────  │  │
│  │  Scrapes /metrics     │  │  Dashboards for       │  │  Receives OTLP traces from     │  │
│  │  from app & workers   │  │  HTTP, agents, jobs,  │  │  app & workers                 │  │
│  │                       │  │  tools, health        │  │  → Jaeger / Tempo / APM        │  │
│  └───────────────────────┘  └───────────────────────┘  └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Run Workflow (Chat / Graph Q&A)

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  1. AUTHENTICATION                                                                       │
│  ───────────────────────────────────────────────────────────────────────────────────     │
│  User → Agent Chat UI → OIDC Provider → JWT (tenant, roles, scopes)                     │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  2. REQUEST → BACKEND                                                                    │
│  ───────────────────────────────────────────────────────────────────────────────────     │
│  UI sends: POST /v1/agent-runs (Bearer JWT, prompt, optional model)                     │
│  → Reverse Proxy → FastAPI Backend                                                       │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  3. SECURITY GATEWAY                                                                     │
│  ───────────────────────────────────────────────────────────────────────────────────     │
│  • Validate JWT (JWKS) → extract tenant, roles, scopes                                  │
│  • RBAC check for endpoint                                                               │
│  • Rate limiting (Redis counters)                                                        │
│  • Audit event logging                                                                   │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  4. INTENT CLASSIFICATION                                                                │
│  ───────────────────────────────────────────────────────────────────────────────────     │
│  Intent Classifier analyzes prompt → determines mode:                                   │
│    • CHAT (conversational)                                                               │
│    • GRAPH (analytics, NL→Cypher)                                                        │
│    • SECURITY / ADMIN (privileged ops)                                                   │
│    • DANGEROUS (destructive ops → refuse/explain)                                        │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  5. ORCHESTRATION & STEP EXECUTION                                                       │
│  ───────────────────────────────────────────────────────────────────────────────────     │
│  Orchestrator builds TODO plan (multi-step run):                                        │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐     │
│  │  FOR EACH STEP:                                                                 │     │
│  │  ─────────────────────────────────────────────────────────────────────────────  │     │
│  │  • Call LLM Provider (via resilience: circuit breakers, fallback, cost)        │     │
│  │  • Invoke MCP Tools (graph.*, data.*, security.*, etc.) with RBAC              │     │
│  │  • If GRAPH mode:                                                               │     │
│  │      1. Normalize NL prompt                                                     │     │
│  │      2. Generate Cypher (LLM or test hints)                                     │     │
│  │      3. Validate safety (read-only, tenant boundaries)                          │     │
│  │      4. Execute on Memgraph                                                     │     │
│  │      5. Summarize results to NL                                                 │     │
│  │  • Persist step (inputs, outputs, metrics) → PostgreSQL                        │     │
│  │  • Use Redis for session state, caching, cancellation checks                   │     │
│  └─────────────────────────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  6. FINALIZATION & RESPONSE                                                              │
│  ───────────────────────────────────────────────────────────────────────────────────     │
│  • Normalize final output (text + optional JSON)                                        │
│  • PII scrubbing & output guard                                                          │
│  • Persist final run & metrics → PostgreSQL                                             │
│  • Emit metrics (Prometheus) & traces (OTEL)                                            │
│  • Return HTTP response → UI polls /agent-runs/{id} for updates                         │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Long-Running Job Workflow

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  1. JOB CREATION                                                                         │
│  ───────────────────────────────────────────────────────────────────────────────────     │
│  Admin (Control Panel UI) → POST /v1/jobs (ETL, backup, maintenance, etc.)              │
│  → Backend validates, creates Job record (status=queued) in PostgreSQL                  │
│  → Enqueues job ID in Redis queue                                                        │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  2. WORKER PROCESSING                                                                    │
│  ───────────────────────────────────────────────────────────────────────────────────     │
│  Worker process:                                                                         │
│    • Pops job ID from Redis                                                              │
│    • Loads job from PostgreSQL → marks status=running                                   │
│    • Executes handler (uses same adapters: Memgraph, LLM, Redis)                        │
│    • Periodically checks cancellation flags (Redis)                                      │
│    • Emits progress events → Redis SSE buffer                                            │
│    • On completion: status=finished/failed → persists result                            │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  3. SSE STREAMING TO UI                                                                  │
│  ───────────────────────────────────────────────────────────────────────────────────     │
│  Control Panel subscribes to GET /v1/jobs/{id}/events (SSE)                             │
│  → Backend streams events from PostgreSQL + Redis buffer                                │
│  → UI displays real-time progress, logs, final status                                   │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Summary Table

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

---

## Key Metrics

| Metric | Value |
|--------|-------|
| **API Endpoints** | 76 across 16 categories |
| **MCP Tools** | 34 tools, 17 categories |
| **Test Cases** | 3,000+ |
| **Test Files** | 236 |

---

**Author:** Arman Feili  
**Thesis Project:** Sapienza University of Rome, 2025
