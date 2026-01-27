```txt
CINECA AGENTIC PLATFORM — ARCHITECTURE (Text Rewrite)

================================================================================
1) IDENTITY & AUTHENTICATION LAYER: CLIENTS & USER INTERFACES
================================================================================

1.1 Identity Provider (OIDC / Auth0)
- OAuth 2.0 login flow
- JWT tokens:
  - tenant_id, sub, roles[], scopes[], exp, iat
- JWKS endpoint for token verification
- Token refresh & revocation
- Principal object:
  - sub, tenant_id
  - roles: [admin, operator, user, viewer]
  - scopes: [read, write, graph:read, graph:write, tools:invoke, admin:all, ...]

1.2 Agent Chat UI (Next.js / React) — WORKFLOW A (Agent Run)
- End-user chat interface
- JWT-based authentication
- SSE streaming support
- Agent runs & steps visualization
- Real-time polling for updates
API call
- POST /v1/agent-runs
  - Bearer JWT, prompt, model, temperature
  - Returns: {run_id, status: "queued"}

1.3 Control Panel UI (Streamlit) — WORKFLOW B (Long-Running Jobs)
- Admin/Operator dashboard
- Jobs / models / tools management
- Graph + NL→Cypher experiments
- SSE streaming for job events
- ETL / backup / maintenance triggers
API call
- POST /v1/jobs
  - Bearer JWT, type, payload
  - Job Types: demo, test, long-running, agent.run
  - Returns: {id, status, created_at}

1.4 Reverse Proxy / API Gateway (NGINX)
- TLS termination (HTTPS)
- Routing to backend services
- CORS handling
- Load balancing

================================================================================
2) SECURITY MIDDLEWARE STACK (Request/Response Pipeline)
================================================================================

1. CORS Handler
- Allowed origins, methods, headers configuration
- Preflight OPTIONS request handling
- Credentials and expose headers support

2. Trace Context (OpenTelemetry)
- Injects/extracts W3C trace-context headers (traceparent, tracestate)
- Creates root span if missing; propagates existing trace
- Adds trace_id, span_id, parent_id to request context

3. Auth JWT (OIDC/JWT validation + principal extraction)
- Validates Bearer token via JWKS endpoint (RS256/RS384/RS512)
- Extracts claims: sub, tenant_id, roles[], scopes[], exp, iat
- RBAC + scope enforcement for endpoints
- Builds Principal object for downstream authorization
- Rejects expired/invalid/malformed tokens → 401 Unauthorized

RBAC Permission Matrix (7 roles with hierarchical scopes)
- admin:
  - agent-runs = CRUD
  - jobs      = CRUD
  - tools     = CRUD
  - tenants   = CRUD
  - graph(write) = ✓
  - Full system access (*)
  - Cross-tenant operations, all admin functions
- operator:
  - agent-runs = CRU
  - jobs      = CRUD
  - tools     = R
  - tenants   = R
  - graph(write) = ✗
- user:
  - agent-runs = CR
  - jobs      = CRD
  - tools     = R
  - tenants   = ✗
  - graph(write) = ✗
- viewer:
  - agent-runs = R
  - jobs      = R
  - tools     = R
  - tenants   = ✗
  - graph(write) = ✗

4. Rate Limit (Redis-backed, multi-dimension)
- Per-user:    ratelimit:user:{sub}
- Per-tenant:  ratelimit:tenant:{tenant_id}
- Per-endpoint:ratelimit:endpoint:{method}:{path}
- Sliding window; exceeded → 429 Too Many Requests
- Returns headers:
  - X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset

5. Tenant Resolver (Multi-tenancy isolation)
- Resolves tenant config from Redis cache or PostgreSQL
- Injects tenant_id filter into all database queries
- Enforces data isolation between tenants
- Loads tenant-specific settings (model defaults, feature flags)

6. Input Guard (Request validation + sanitization)
- Pydantic schema validation for all request bodies
- Injection prevention (SQL, Cypher, command injection patterns)
- Content-type validation and size limits
- Malicious payload detection

7. Output Guard (Response sanitization + compliance)
- PII scrubbing (email redaction, phone masking, SSN removal)
- Content filtering for sensitive data patterns
- Response size validation and truncation
- Audit logging of responses with correlation IDs

8. Error Handler (Centralized exception handling)
- Normalizes exception → consistent error response format
- Attaches correlation/trace IDs
- Maps domain errors to correct HTTP status codes
- Ensures errors are logged (structured) and traceable

================================================================================
3) API LAYER (Routers)
================================================================================

Primary endpoints
- /v1/health    - Health probes (live, ready, startup, components)
- /v1/auth      - Token introspection, identity verification
- /v1/agents    - Agent definitions and configurations
- /v1/agent-runs- Agent run lifecycle (create, poll, cancel)
- /v1/tools     - MCP tool registry and invocation
- /v1/jobs      - Async job lifecycle (create, stream, cancel)
- /v1/models    - Model and provider management
- /v1/admin     - Administrative operations
- /v1/tenants   - Multi-tenant configuration
- /v1/sessions  - Session management
- /v1/graph     - Graph query endpoints
- /v1/batch     - Batch operations
- /v1/export    - Data export utilities
- /v1/internal  - Internal diagnostics

================================================================================
4) ENDPOINT GROUPS FOR THE TWO EXECUTION WORKFLOWS
================================================================================

WORKFLOW A — Agent Run Endpoints
- POST /v1/agent-runs (use_jobs=false → BackgroundTasks)
- POST /v1/agent-runs?use_jobs=true (→ Jobs Worker)
- GET  /v1/agent-runs/{id} (ETag support for caching)
- GET  /v1/agent-runs/{id}/steps

WORKFLOW B — Long-Running Job Endpoints
- POST   /v1/jobs → HTTP 202 + Location header
- GET    /v1/jobs/{id}
- GET    /v1/jobs/{id}/events (SSE streaming)
- DELETE /v1/jobs/{id} (cancellation via Redis Lua script)

================================================================================
5) JOB CREATION & ENQUEUE (Async Execution Entry Point)
================================================================================

Job creation flow
- Validate job request (Pydantic schema)
- Validate payload against JSON Schema for the job type
- Check idempotency key (Redis + PostgreSQL)
- Create Job record (status=queued) → PostgreSQL
- LPUSH job_id → Redis queue: jobs:queue:{type}
- HSET job state → Redis: jobs:state:{id}
- Cache idempotency mapping → Redis
- Return HTTP 202 + JobResponse {id, status, created_at} + Location header
- Job Types: demo, test, long-running, agent.run

Redis queue (Job IDs) → Workers via BRPOP

================================================================================
6) WORKERS (Async Processing)
================================================================================

6.1 Job Processing Worker — processing loop (per job)
1) Pop job ID: BRPOP jobs:queue:{type} (blocking wait)
2) Load job metadata from PostgreSQL
3) Check pre-execution cancellation flag (Redis)
4) Update status: queued → running
5) Append status event to job_events table
6) Start async heartbeat task
7) Execute handler (uses same adapters: Memgraph, LLM, Redis):
   - demo jobs: simple demonstration
   - test jobs: testing purposes
   - long-running jobs: extended analysis
   - agent.run jobs: async agent execution (orchestrator integration)
     • Load/Create AgentRun record → PostgreSQL
     • AgentRun status: queued → running
     • Emit SSE: agent_run_started
     • Initialize Orchestrator.from_env()
     • Emit SSE: orchestrator_init
     • Execute orchestrator.run() with timeout
     • LLM calls, MCP tools, graph queries
     • Persist steps per-step → PostgreSQL
     • Session state → Redis
     • Check cancellation between steps
     • Emit progress events per orchestration step
     • Apply PII scrubbing + output guard
     • Emit agent-specific Prometheus metrics
     • Update AgentRun status → succeeded | failed
8) Periodically check cancellation flags (Redis: jobs:cancel:{id})
9) Emit progress events → RPUSH jobs:events:{id} → SSE to Control Panel
10) On completion: status = finished | failed | cancelled
11) Persist result → PostgreSQL
12) Append terminal event to job_events

Job status state machine
- queued → running → finished | failed | cancelled

Resources (as specified)
- 2 CPU, 4GB RAM
- Shared codebase: uses same adapters/services as main app

6.2 SSE Streaming to Control Panel
- Control Panel subscribes: GET /v1/jobs/{id}/events (Server-Sent Events)
- Backend streams events from PostgreSQL + Redis buffer
- UI displays: real-time progress, logs, final status

================================================================================
7) SERVICE LAYER
================================================================================

7.1 Orchestrator Service — 1 run per prompt, 4 phases

PHASE 1) Intent Classification
- Analyze prompt via LLM
- Check params.category → match prompt catalog → classify_intent()
- Categories:
  - CHAT      - conversational responses
  - GRAPH     - analytics, NL→Cypher queries
  - SECURITY  - security/permissions questions
  - ADMIN     - administrative write operations
  - DANGEROUS - destructive ops → refuse + offer EXPLAIN
  - EXPLAIN   - explain-only query analysis

PHASE 2) TODO Planning (multi-step run)
- LLM-based planning
- Input: goal + context + schema
- Output: TODO array
- Planning modes:
  - full     (LLM per TODO)
  - optional (try direct first)
  - none     (deterministic)

PHASE 3) Step Execution (FOR EACH TODO)
1) Call LLM provider (planner, reflector, responder)
2) Invoke MCP tools with RBAC check (34 tools available)
3) If GRAPH mode: NL→Cypher pipeline
4) Persist step → PostgreSQL (via adapter)
5) Use Redis for session/cache/cancel (via adapter)
- Step record format:
  {id, action, input, output, latency_ms, started_at, finished_at}

PHASE 4) Finalization & Response Generation
- build_response() → orchestration result
- Response mode selection: fallback-only | llm-best-effort
- Canonical output structure: {goal, steps[], outputs[], todos[], metrics}
- Normalize output: text + optional JSON payload
- Safety/compliance: PII scrubbing + output guard checks
- Persist final state + metrics → PostgreSQL
- Observability: emit Prometheus metrics + OpenTelemetry traces

7.2 Additional Services
- Session Service (state management)
- Job Service (job lifecycle)
- Default Model Resolver
- Health / ETL / Archive Services
- Invocation Store (audit trail)

================================================================================
8) PHASE 3 (Expanded): Step Execution Building Blocks
================================================================================

Step 1) LLM Providers
- Ollama (Local)
  - Local LLM hosting
  - Self-hosted models: phi3:mini, Mistral, LLaMA, Qwen, Gemma
- OpenAI
  - Cloud LLM API
  - GPT-4, GPT-3.5, etc.
- Azure OpenAI / Other Providers
  - Compatible OpenAI-style APIs
  - Enterprise deployments

Step 2) MCP Runtime & Tools (34 tools, 12 categories as shown)
- Tool registry (PostgreSQL-backed manifests)
- Tool policies (RBAC per tool, required_scopes)
- MCP runtime (ToolContext, audit logging)
- Invocation pipeline:
  Request → schema validation → RBAC check → execute → audit log

Tool categories (examples)
- GRAPH     - query, secure_query, generate_cypher, schema, explain
- SECURITY  - describe_principal, allowed_operations, validate
- SYSTEM    - health, metrics, config, status
- CACHE     - get, set, delete, invalidate
- CATALOG   - discover, describe, search
- MODEL     - list, info, warmup, switch
- AGENT     - context, history, state
- ANALYTICS - query, aggregate, visualize
- ADMIN     - create_index, drop_index, constraint
- ETL       - import, export, transform
- CRUD      - create_node, update_node, delete_node
- EXPORT    - csv, json, cypher

Tool manifest (from PostgreSQL)
- {name, description, input_schema, required_scopes,
   rate_limit: {requests: 100, window: 60}}

Step 3) NL→Cypher Pipeline (GRAPH mode) — 6 stages
1) Normalize NL prompt (input sanitization, entity extraction, context enrichment)
2) Catalog lookup (check if query matches known patterns in prompt catalog)
3) Generate Cypher (LLM-based generation with schema context, or test hints in test mode)
4) Validate safety (6-layer validation: syntax, read-only, tenant isolation, depth limits, timeout guards, result caps)
5) Execute on Memgraph (run validated Cypher with tenant filtering and timeout enforcement)
6) Summarize results (LLM summarization or direct count bypass for efficiency)

================================================================================
9) DATA & INFRASTRUCTURE LAYER
================================================================================

9.1 PostgreSQL
Tables
- tenants         - multi-tenant configurations
- agent_runs      - agent run records with status
- steps           - per-step execution records
- sessions        - user session state
- jobs            - async job records
- job_events      - job progress events
- tool_manifests  - MCP tool definitions
- model_defaults  - default model configurations
- audit_logs      - all action audit trail

Migrations
- SQLAlchemy + Alembic migrations
Used by
- App (Background Tasks) + Workers

9.2 Redis (Cache & Queues)

CACHE
- session:{id}        - session data
- tenant:config:{id}  - tenant configurations
- model:defaults:{id} - model defaults

QUEUES
- jobs:queue:{type}   - job queue (LPUSH/BRPOP)
- jobs:events:{id}    - SSE event buffer (ring)
- jobs:state:{id}     - job state (HASH)

RATE LIMITING
- ratelimit:user:{id}     - per-user limits
- ratelimit:tenant:{id}   - per-tenant limits
- ratelimit:endpoint:{...}- per-endpoint limits

CONTROL
- idempotency:{key}  - idempotency mapping
- circuit:{provider} - circuit breaker state

Used by
- App (Background Tasks) + Workers

9.3 Memgraph (Graph Database)
Nodes (Bioinformatics Domain - 14 node types)
- (:User        {user_id, firstName, lastName, user_name, email})
- (:Institution {id, name, country, type})
- (:Task        {task_id, status, start, tags}) — e.g., Blast, CreateDb, SearchbyTaxon, Bold, Command
- (:File        {file_id, user_filename, size, extension, bucket_name}) — e.g., Fasta, BlastDb, Xml, BlastedSeq
- (:Dataset     {id, name, description, version})
- (:Sample      {id, name, organism, tissue})
- (:Experiment  {id, name, protocol, date})
- (:Publication {id, doi, title, journal, year})
- (:Gene        {id, symbol, name, chromosome})
- (:Protein     {id, name, sequence, function})
- (:Pathway     {id, name, description})
- (:Tool        {id, name, version, type})
- (:Workflow    {id, name, steps, inputs})
- (:Result      {id, type, metrics, timestamp})

Relationships (4 relationship types)
- (User)-[:WORKS_AT {since, role, department}]->(Institution)
- (User)-[:RUNS]->(Task)
- (File)-[:INPUT]->(Task)
- (Task)-[:OUTPUT]->(File)

Used by
- NL→Cypher pipeline, graph.* tools, analytics, ETL jobs

================================================================================
10) PHASE 4 COMPLETION (Workflow-specific)
================================================================================

WORKFLOW A — PHASE 4) Agent Run Completion
- State machine: queued → running → succeeded | failed
- Record provenance event for completed run
- Build API payload:
  AgentRunResponse {id, status, outputs[], steps[], todos[], metrics}
- Return HTTP response to client
- UI polling: GET /agent-runs/{id} (ETag support)

WORKFLOW B — PHASE 4) Long-Running Job Completion
- State machine: queued → running → finished | failed | cancelled
- Persist job status → PostgreSQL
- Append progress/state events → job_events table
- Progress event format: {stage, message, percent}
- Stream updates via SSE to Control Panel (heartbeat keep-alive)
- Emit + persist terminal status: finished | failed | cancelled

================================================================================
11) ADAPTERS & RESILIENCE FRAMEWORK
================================================================================

1) LLM ADAPTERS
- Ollama Adapter: local LLM providers
- OpenAI-Style API Adapter: compatible REST interface
- Azure OpenAI Adapter: Azure-hosted OpenAI endpoints
- Stub/Demo Adapter: testing and demos

2) RESILIENCE MECHANISMS
- Circuit Breaker (per provider)
  CLOSED (normal) → OPEN (reject requests) → HALF_OPEN (allow single probe) → CLOSED
- Automatic Retries: exponential backoff (provider-aware)
- Cost Tracking: per provider + per model
- Provider Fallback: ordered fallback chain on failure/timeouts

3) DATABASE ADAPTERS
- Redis Adapter
  - cache
  - queues
  - rate limits
- PostgreSQL Adapter
  - repositories
  - transactions
- Memgraph Adapter
  - graph queries
  - NL→Cypher

================================================================================
12) BACKGROUND FRAMEWORK (Scheduled Operations)
================================================================================

APScheduler — Scheduled Tasks
- Health check (every 30s):
  - Postgres ping, Redis ping, Memgraph ping, LLM warmup/availability
- Cleanup (hourly):
  - stale/old sessions, expired/stale cache, expired jobs, old job records, orphan runs
- Backup (daily):
  - PostgreSQL dump, Redis RDB snapshot, Memgraph archives, audit logs export
- Provider monitoring:
  - provider health + metrics emission

================================================================================
13) OBSERVABILITY & MONITORING
================================================================================

Instrumentation & Endpoints
- Prometheus /metrics endpoint (app + workers)
- OpenTelemetry tracing (OTLP export from app + workers)
- Structured logging (JSON format)
- Health endpoints:
  - /v1/health/live
  - /v1/health/ready
  - /v1/health/startup
  - /v1/health/components

Tracing (OTel Collector + APM Backend)
- Receives OTLP traces from: app + workers
- Exports to: Jaeger / Tempo / APM backend
- Trace spans include:
  - agent run execution (end-to-end)
  - step-by-step processing
  - tool invocations
  - database queries
  - job lifecycle (enqueue → execute → complete/fail/cancel)

Grafana (Dashboards)
- HTTP request metrics
- Agent run statistics (runs/steps)
- Job processing + queue metrics
- Tool invocation stats
- LLM provider health + circuit breaker states
- System/component health status

Prometheus (Metrics Collection)
- Scrapes /metrics from: app + workers
- Metrics collected:
  - HTTP latency + throughput
  - agent run / step execution metrics
  - tool invocation metrics
  - LLM token usage + cost
  - LLM provider health + circuit breaker states
  - job processing metrics
  - job queue depths
  - system health status
