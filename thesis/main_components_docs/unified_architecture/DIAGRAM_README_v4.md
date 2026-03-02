                  CINECA AGENTIC PLATFORM – UNIFIED ARCHITECTURE
                  ==============================================

 Identity & Clients
 ------------------
   +----------------------+      OAuth/OIDC      +-----------------------+
   | Agent Chat UI        |<-------------------->| Identity Provider      |
   | (Next.js)            |                      | (e.g., Auth0 / OIDC)   |
   +----------------------+                      +-----------------------+
   +----------------------+
   | Control Panel UI     |
   | (Streamlit)          |
   +----------------------+
   +----------------------+
   | Other API Clients    |
   +----------------------+
              |
              | HTTPS + JWT (tenant, roles, scopes)
              v

 Edge
 ----
   +-------------------------------+
   | Reverse Proxy / API Gateway   |
   | (e.g. NGINX / Ingress)        |
   +-----------------------+-------+
                           |
                           v

 Core Backend (FastAPI App)
 --------------------------
   +-------------------------------------------------------------------------+
   |                        FASTAPI BACKEND APPLICATION                      |
   |-------------------------------------------------------------------------|
   |  API LAYER                                                              |
   |   - Agents & Agent Runs API                                             |
   |   - Jobs API                                                            |
   |   - Tools (MCP) API                                                     |
   |   - Models & Providers API                                              |
   |   - Tenants & Admin API                                                 |
   |   - Auth & Health / Meta                                                |
   |                                                                         |
   |  SECURITY & GOVERNANCE                                                  |
   |   - JWT / OIDC validation (JWKS)                                        |
   |   - RBAC (roles, scopes, tenant context)                                |
   |   - Rate limiting (Redis-backed)                                        |
   |   - PII scrubber & Output Guard                                         |
   |   - Audit logs (tools, admin, dangerous ops)                            |
   |                                                                         |
   |  SERVICE & ORCHESTRATION LAYER                                          |
   |   - Orchestrator (multi-step agent runs, modes: CHAT / GRAPH / ADMIN /  |
   |                  SECURITY / DANGEROUS)                                  |
   |   - Intent Classifier                                                   |
   |   - Session Service & Job Service                                       |
   |   - Default Model / Provider Resolver                                   |
   |   - ETL / Archive / Health services                                     |
   |                                                                         |
   |  MCP RUNTIME & TOOLS                                                    |
   |   - Tool registry & tool policies                                       |
   |   - MCP runtime (ToolContext, RBAC, audit, telemetry)                   |
   |   - Tool families: graph.*, cache.*, data.*, db.*, security.*, admin.*, |
   |     output.*, privacy.*, session.*, tenancy.*, user.*, ratelimit.*, ... |
   |                                                                         |
   |  ADAPTERS & RESILIENCE                                                  |
   |   - LLM adapters (OpenAI-style, Ollama, stub/demo)                      |
   |   - Memgraph adapter (graph domain + NL→Cypher pipeline)                |
   |   - Redis adapter (cache, queues, rate limits, state)                   |
   |   - HTTP / external service clients                                     |
   |   - Resilience framework (provider pool, circuit breakers, cost/budgets)|
   |                                                                         |
   |  OBSERVABILITY & HEALTH                                                 |
   |   - Prometheus metrics endpoint                                         |
   |   - OpenTelemetry tracing (OTLP exporter)                               |
   |   - Structured logging                                                  |
   |   - Health endpoints (live / ready / startup / components)              |
   +----------------------+-----------------------------+--------------------+
                          |                             |
                          | DB / cache / graph          | metrics & traces
                          v                             v

 Data & State Layer
 ------------------
   +------------------------------+   +---------------------------+   +----------------------+
   | PostgreSQL (Control Plane)   |   | Redis (Cache & Queues)   |   | Memgraph (Graph DB)  |
   |------------------------------|   |---------------------------|   |----------------------|
   | - Tenants & providers        |   | - Cache (runs, configs)   |   | - Domain graph       |
   | - Models & manifests         |   | - Job queues & SSE buffer |   |   (nodes, edges)     |
   | - Agent runs, sessions,steps |   | - Rate-limit counters     |   | - Cypher queries     |
   | - Jobs & job events          |   | - Idempotency keys        |   | - NL→Cypher in       |
   | - Tools & tool invocations   |   | - Cancellation flags      |   |   GRAPH mode         |
   | - Defaults, audit, ops       |   +---------------------------+   +----------------------+
   +------------------------------+

 Workers & Background
 --------------------
           ^                               ^
           | Postgres & Redis              | Redis queues
           |                               |
   +-------+-------------------------------+-----------------------------+
   |                        Worker Processes                            |
   |  - Consume job queues from Redis                                   |
   |  - Execute long-running tasks (ETL, backups, maintenance, demos)   |
   |  - Update jobs & job events in PostgreSQL                          |
   |  - Emit progress events for SSE to clients                         |
   +--------------------------------------------------------------------+
           ^
           |
   +-------+------------------------------------------------------------+
   |            Background Scheduler / Built-in Processes               |
   |  - Periodic health checks (Postgres, Redis, Memgraph, LLMs)        |
   |  - Backups & cleanup (jobs, keys, temp data)                       |
   |  - Model / provider warmup                                         |
   +--------------------------------------------------------------------+

 External Ecosystem
 ------------------
   +------------------------+      +------------------------+      +------------------------+
   | LLM Providers          |      | Prometheus            |      | OTEL Collector / APM   |
   |------------------------|      |------------------------|      |------------------------|
   | - OpenAI / Azure       |<-----| scrape /metrics from  |<-----| receive traces from    |
   | - Ollama (local)       |      | FastAPI app + workers |      | app + workers (OTLP)   |
   | - Other OpenAI-style   |      +------------------------+      +------------------------+
   +-----------^------------+
               |
               | HTTP calls via LLM adapters & resilience framework
               v
         +-----+--------------------------+
         |        FASTAPI BACKEND         |
         +--------------------------------+


---


                 CINECA AGENTIC PLATFORM – UNIFIED WORKFLOW
                 ==========================================

[0] LOGIN & TOKEN
-----------------
  +-----------+             +--------------------+
  |  End User |             |  Admin / Operator  |
  +-----+-----+             +---------+----------+
        |                              |
        | Open UI (Next.js / Streamlit)|
        v                              v
  +--------------------+       +--------------------+
  | Agent Chat UI      |       | Control Panel UI   |
  | (Next.js)          |       | (Streamlit)        |
  +---------+----------+       +---------+----------+
            |                            |
            | OIDC login (redirect, code flow)
            v
      +----------------------------+
      |  Identity Provider (OIDC) |
      +-------------+-------------+
                    |
                    | ID token + access token (JWT)
                    v
      +----------------------------+
      |  UI holds JWT (tenant,    |
      |  roles, scopes, expires)  |
      +-------------+-------------+


[1] REQUEST INTO BACKEND
------------------------
User / Admin performs an action:
  - Send chat prompt
  - Inspect runs
  - Trigger ETL / backup job
  - Manage models / tools / tenants

UI → Backend:

  +--------------------+
  |   Web UI / Client  |
  +---------+----------+
            |
            | HTTPS request with:
            |   - Path / method (e.g. POST /v1/agent-runs)
            |   - Authorization: Bearer <JWT>
            |   - Tenant header (optional)
            v
  +-----------------------------+
  | Reverse Proxy / Ingress     |
  +-------------+---------------+
                |
                v
  +-----------------------------+
  | FastAPI API Router          |
  | (/v1/agents, /v1/jobs, ...) |
  +-------------+---------------+


[2] SECURITY GATEWAY (FOR EVERY REQUEST)
----------------------------------------
  +-----------------------------+
  | Security Gateway            |
  |-----------------------------|
  | 1. Authentication           |
  |    - Decode JWT, verify via |
  |      JWKS (issuer, aud, exp)|
  |                             |
  | 2. Principal / Tenant       |
  |    - Extract subject, roles |
  |    - Determine tenant       |
  |                             |
  | 3. Authorization (RBAC)     |
  |    - Check required scopes  |
  |      for endpoint           |
  |                             |
  | 4. Rate Limiting (Redis)    |
  |    - Increment counters     |
  |    - If over limit → 429    |
  |                             |
  | 5. Audit Event              |
  |    - Who, what, when, where |
  +-------------+---------------+
                |
     If fail → 401/403/429 + ProblemDetail
                |
                v
       (Security OK) → Endpoint logic


[3] ENDPOINT LOGIC → SERVICE LAYER
----------------------------------
  +-----------------------------+
  | Endpoint (example:         |
  | POST /v1/agent-runs)       |
  +-------------+---------------+
                |
                v
  +-----------------------------+
  | Service Layer               |
  |-----------------------------|
  | - Agents / Agent Runs       |
  | - Jobs                      |
  | - Tools (MCP)               |
  | - Models & Providers        |
  | - Admin / Tenants           |
  +-------------+---------------+
                |
                +------------------------------------------------------+
                |                                                      |
                v                                                      v
     [Agent Run Workflow]                                 [Job Workflow]
     (chat, graph, reasoning)                             (long-running ops)


[4A] AGENT RUN WORKFLOW (CHAT / GRAPH / SECURITY / ADMIN)
----------------------------------------------------------
  +-----------------------------+
  | Orchestrator Service        |
  +-------------+---------------+
                |
                | 1. Create AgentRun + Session in Postgres
                | 2. Store request metadata (user, tenant, model)
                v
        +------------------------+
        | Intent Classifier      |
        +-----------+------------+
                    |
                    | Analyze prompt → mode:
                    |   - CHAT
                    |   - GRAPH
                    |   - SECURITY / ADMIN
                    |   - DANGEROUS
                    v
        +------------------------+
        | Orchestrator Engine    |
        +-----------+------------+
                    |
                    | 3. Build TODO plan (steps):
                    |    - LLM reasoning steps
                    |    - MCP tool calls (graph, data, security, ...)
                    |    - Optional job creation for long tasks
                    v

        +-----------------------------------------------------------+
        | 4. Step Execution Loop                                    |
        |-----------------------------------------------------------|
        | For each step:                                            |
        |                                                           |
        |  a) Choose LLM provider via Resilience Framework          |
        |     - Check circuit breakers (OPEN/HALF_OPEN/CLOSED)      |
        |     - Check token / cost budgets                          |
        |     - Pick provider/model (OpenAI, Ollama, stub, ...)     |
        |                                                           |
        |  b) Call LLM Adapter                                      |
        |     - Build request payload                               |
        |     - Invoke provider HTTP API                            |
        |     - On success: track tokens, cost, latency             |
        |     - On error: update breaker, try next provider         |
        |                                                           |
        |  c) Optionally call MCP Tools                             |
        |     - Check RBAC policies                                 |
        |     - graph.* → Memgraph (analytics, NL→Cypher)           |
        |     - cache.* → Redis                                     |
        |     - data.*, security.*, admin.*, system.*, ...          |
        |     - Log tool invocation in Postgres (audit)             |
        |                                                           |
        |  d) If mode = GRAPH:                                      |
        |     - Normalize NL prompt                                 |
        |     - Generate Cypher (LLM or test hints)                 |
        |     - Safety checks (no destructive ops, tenant guards)   |
        |     - Execute Cypher on Memgraph                          |
        |     - Post-process results, summarize to NL / JSON        |
        |                                                           |
        |  e) Persist step                                          |
        |     - Insert AgentStep in Postgres                        |
        |     - Update AgentRun status, metrics                     |
        |     - Use Redis for session state, cancellation flags     |
        +-----------------------------------------------------------+

                    |
                    | All steps done OR cancelled
                    v

  +-----------------------------+
  | Finalization & Response     |
  |-----------------------------|
  | - Normalize final output    |
  |   (text + optional JSON)    |
  | - Run output guard + PII    |
  |   scrubber                  |
  | - Persist final AgentRun    |
  |   & metrics in Postgres     |
  | - Emit metrics/traces       |
  +-------------+---------------+
                |
                v
        +------------------------+
        | HTTP Response          |
        +-----------+------------+
                    |
                    v
        +------------------------+
        | Agent Chat UI          |
        |------------------------|
        | - Poll /v1/agent-runs  |
        |   and /steps (or SSE)  |
        | - Render messages,     |
        |   steps, metrics       |
        +-----------+------------+
                    |
                    v
              End User sees
              final answer


[4B] LONG-RUNNING JOB WORKFLOW (ETL, BACKUPS, BULK OPS)
--------------------------------------------------------
  +-----------------------------+
  | Jobs / Admin Endpoint       |
  | (e.g., POST /v1/jobs)       |
  +-------------+---------------+
                |
                v
  +-----------------------------+
  | Job Service                 |
  |-----------------------------|
  | 1. Create Job record in     |
  |    Postgres (status=queued) |
  | 2. Push job ID into Redis   |
  |    queue by job_type        |
  +-------------+---------------+
                |
                v
          +-----------+
          | Redis     |
          | Queue     |
          +-----+-----+
                |
                | Worker polls
                v
       +--------------------------+
       | Worker Process           |
       |--------------------------|
       | 3. Pop job ID from Redis |
       | 4. Load job from         |
       |    Postgres → running    |
       | 5. Emit "started" event  |
       |                          |
       | 6. Execute handler:      |
       |    - ETL / Memgraph ops  |
       |    - LLM / tools         |
       |    - Backups / cleanup   |
       |    - Check cancel flag   |
       |                          |
       | 7. On success:           |
       |    - Save result         |
       |    - status=finished     |
       |    - emit "progress"/    |
       |      "done" events       |
       |                          |
       |    On failure:           |
       |    - Save error info     |
       |    - status=failed       |
       |    - emit "failed" event |
       +-------------+------------+
                     |
                     v
     +-------------------------------+
     | Postgres + Redis Event Buffer |
     +-------------------------------+
                     |
                     | UI polls /jobs/{id} & /events OR SSE
                     v
     +-------------------------------+
     | Control Panel UI (Streamlit) |
     |-------------------------------|
     | - Show progress, logs,       |
     |   final status, result       |
     +-------------------------------+


[5] OBSERVABILITY & HEALTH (CROSS-CUTTING)
------------------------------------------
At each step above:
  - FastAPI app & workers expose metrics (/metrics) → Prometheus
  - Traces emitted via OpenTelemetry → OTEL collector / APM
  - Health framework updates component status (DB, Redis, Memgraph, LLMs)
  - Logs include tenant, run_id, job_id, correlation IDs


[6] DATA STORES INVOLVED (SUMMARY)
----------------------------------
  - PostgreSQL: control plane (tenants, providers, models, agent runs, steps,
    jobs, job events, tools, manifests, audit logs, idempotency).
  - Redis: cache, job queues, rate limits, SSE buffers, cancellation flags.
  - Memgraph: domain graph + Cypher (especially in GRAPH mode).
  - LLM Providers: external or local models called via resilience framework.


---

## 1) Architecture Diagram (.txt)

```text
                          +------------------------------------+
                          |              CLIENTS               |
                          |------------------------------------|
                          | - Agent Chat UI (Next.js)          |
                          | - Control Panel UI (Streamlit)     |
                          +-----------------+------------------+
                                            |
                                            v
                          +-----------------+------------------+
                          |               API GATEWAY          |
                          |             (FastAPI App)          |
                          |------------------------------------|
                          | - Agents API                       |
                          | - Jobs API                         |
                          | - Models & Providers API           |
                          | - Tools (MCP) API                  |
                          | - Tenants & Admin API              |
                          | - Health & Meta API                |
                          +-----------------+------------------+
                                            |
                       +--------------------+---------------------+
                       |                                          |
                       v                                          v
        +--------------+----------------+          +--------------+----------------+
        |           SERVICE LAYER        |          |        SECURITY LAYER         |
        |--------------------------------|          |--------------------------------|
        | - Orchestrator Service         |          | - Auth (OIDC/JWT)             |
        | - Session Service              |          | - RBAC & Permissions          |
        | - Default Model Resolver       |          | - Roles & Policies            |
        | - ETL / Archive Services       |          | - PII Scrubber                |
        | - Health Service               |          | - Output Guard                |
        | - Invocation Store, Job Service|          | - Rate Limiting               |
        +--------------+-----------------+          | - Tenants & Admin Controls    |
                       |                            +--------------+----------------+
                       |                                           |
                       v                                           v
        +--------------+-----------------+           +-------------+----------------+
        |              ADAPTERS          |           |         MCP TOOLS            |
        |--------------------------------|           |--------------------------------|
        | - LLM Provider Adapters        |           | - Graph tools (analytics,     |
        |   (OpenAI-style, Ollama, etc.) |           |   CRUD, secure NL→Cypher)    |
        | - Memgraph Adapter             |           | - Cache tools                 |
        | - Redis Client (sync/async)    |           | - Data tools (archival, ETL) |
        | - HTTP Clients / External APIs |           | - DB tools                    |
        +--------------+-----------------+           | - Security / Admin tools     |
                       |                             | - Utility tools              |
                       |                             +-------------+----------------+
                       |                                           |
                       v                                           v
+----------------------+---------------------+    +----------------+--------------------+
|     POSTGRESQL CONTROL PLANE               |    |            REDIS LAYER              |
|--------------------------------------------|    |-------------------------------------|
| - Tenants                                  |    | - Cache for hot entities            |
| - Providers & Model Instances              |    | - Job queues & SSE event buffers    |
| - Agents, Sessions, Runs, Steps            |    | - Agent session state               |
| - Jobs & Job Events                        |    | - Idempotency keys                 |
| - Tools & Tool Invocations                 |    | - Rate-limit counters              |
| - Built-in Manifests & Processes           |    | - Cancellation flags               |
| - User Default Models                      |    +-----------------+-------------------+
| - Audit Logs & Internal Ops                |
+----------------------+---------------------+
                       |
                       |
                       v
         +-------------+----------------------+
         |          MEMGRAPH GRAPH DB         |
         |------------------------------------|
         | - Domain graph schema              |
         | - Nodes: users, institutions,      |
         |   tasks, files, etc.              |
         | - Edges for lineage & relations   |
         | - Analytics & graph queries       |
         +-------------+----------------------+

                                     |
                                     v
                  +------------------+-------------------+
                  |      EXTERNAL LLM PROVIDERS         |
                  |-------------------------------------|
                  | - Cloud APIs (OpenAI-style)         |
                  | - Local LLMs (e.g. Ollama)          |
                  | - Stub / Demo providers (testing)   |
                  +------------------+-------------------+

                                     |
                                     v
                        +------------+-------------+
                        |   RESILIENCE FRAMEWORK  |
                        |-------------------------|
                        | - Provider pool &       |
                        |   fallback priorities   |
                        | - Circuit breakers      |
                        | - Cost tracking         |
                        +------------+------------+

                                     |
                                     v
                        +------------+------------+
                        | BACKGROUND / SCHEDULER |
                        |------------------------|
                        | - Health checks        |
                        | - Backups (Memgraph,   |
                        |   Redis)               |
                        | - Cleanup tasks        |
                        +------------+-----------+

                                     |
                                     v
                        +------------+------------+
                        |   WORKER PROCESSES     |
                        |------------------------|
                        | - Dequeue jobs from    |
                        |   Redis queues         |
                        | - Load/save from/to    |
                        |   Postgres             |
                        | - Execute long tasks   |
                        | - Emit job events      |
                        +------------+-----------+

                                     |
                                     v
                        +------------+------------+
                        |   OBSERVABILITY STACK  |
                        |------------------------|
                        | - Metrics (Prometheus) |
                        | - Traces (OTel/OTLP)   |
                        | - Logs (structured)    |
                        +------------------------+
```

---

## 2) Workflow Diagram (.txt)

Below is a text-based diagram of the **main agent workflow** (chat request → orchestration → tools/DBs → response) plus where jobs/workers fit.

### 2.1 Agent Run / Chat Workflow

```text
 [User] 
   |
   v
 [Agent Chat UI (Next.js)]
   |
   | 1. User selects role/model and sends a prompt
   v
 [API Gateway (FastAPI)]
   |
   | 2. HTTP request: POST /agents/runs (with token, tenant, prompt)
   v
 [Security Layer]
   |
   | 3. Validate JWT (OIDC/JWKS)
   | 4. Extract user, roles, scopes, tenant
   | 5. Check authorization & rate limits
   v
 [Service Layer – Orchestrator Service]
   |
   | 6. Call Intent Classifier
   v
 [Intent Classifier]
   |
   | 7. Classify request as: CHAT | GRAPH | SECURITY | ADMIN | DANGEROUS
   v
 [Orchestrator Engine]
   |
   | 8. Select orchestration mode based on intent
   | 9. Build TODO list (steps) for answering the request
   |
   +-------------------------------------------------------------+
   | For each step:                                              |
   |                                                             |
   |  9.1 Select LLM provider via Resilience Framework           |
   |      - Check budgets, circuit breaker state, priorities     |
   |                                                             |
   |  9.2 Invoke LLM adapter                                    |
   |      - Possibly call external LLM (OpenAI-style, Ollama)    |
   |      - Or stub provider in tests                            |
   |                                                             |
   |  9.3 Optionally invoke MCP tools                            |
   |      - Graph tools (analytics, NL→Cypher, queries)          |
   |      - Cache/data/admin/security tools                      |
   |      - Tool invocations audited and checked by security     |
   |                                                             |
   |  9.4 If GRAPH mode:                                         |
   |      a) Generate Cypher from NL                             |
   |      b) Validate Cypher (safe patterns, tenant boundaries)  |
   |      c) Execute on Memgraph via adapter                     |
   |      d) Summarize results to NL                             |
   |                                                             |
   |  9.5 Persist step data                                      |
   |      - Store AgentStep in Postgres                          |
   |      - Update AgentRun status & metrics                     |
   |                                                             |
   +-------------------------------------------------------------+
   |
   | 10. Normalize final output (text/JSON) and compile metrics
   v
 [Repositories + Postgres]
   |
   | 11. Persist AgentRun, AgentSteps, metrics into control plane
   v
 [API Gateway]
   |
   | 12. HTTP response: run details, status, output, metrics
   v
 [Agent Chat UI]
   |
   | 13. UI stores run ID, starts polling:
   |       GET /agents/runs/{id}
   |       GET /agents/runs/{id}/steps
   |
   | 14. UI updates chat messages, shows orchestration steps,
   |     metrics, run status in real time
   v
 [User sees final answer + internal steps/metrics]
```

### 2.2 Long-Running Job Workflow (Background Jobs + Workers)

```text
 [Admin / Operator]
   |
   v
 [Control Panel UI (Streamlit)]
   |
   | 1. Admin triggers a long operation (e.g., ETL load, big export)
   v
 [API Gateway (FastAPI)]
   |
   | 2. HTTP request: POST /jobs (with token, job payload)
   v
 [Security Layer]
   |
   | 3. Validate JWT, check tenant & admin permissions
   v
 [Job Service (Service Layer)]
   |
   | 4. Create Job record in Postgres with status = "queued"
   | 5. Push job ID into Redis queue (by job_type)
   v
 [Redis Queue]
   |
   | 6. Job ID stored in e.g. "job_queue:long_running"
   v
 [Worker Process]
   |
   | 7. Worker polls Redis, pops job ID
   | 8. Loads job from Postgres, marks status = "running"
   | 9. Emits job events (e.g., "started") → PostgreSQL + Redis event buffer
   |
   | 10. Executes job handler:
   |      - May call ETL Service, Adapters (Memgraph, Redis, LLM), etc.
   |      - Periodically check cancellation flags in Redis
   |
   | 11. On success:
   |      - Save result into Job record
   |      - Mark status = "finished"
   |      - Emit events ("progress", "done")
   |
   |    On failure:
   |      - Store error info
   |      - Mark status = "failed"
   |      - Emit failure event
   v
 [Postgres + Redis Event Buffer]
   |
   | 12. Job status + event stream persisted
   v
 [Control Panel UI]
   |
   | 13. UI polls /jobs/{id} and /jobs/{id}/events
   |     or subscribes to SSE endpoint
   |
   | 14. Shows real-time progress, logs, final status and result
   v
 [Admin / Operator observes and manages jobs]
```


## 3) Memgraph + NL→Cypher Flow (.txt)

```text
                      +---------------------------------+
                      |        USER / CLIENT UI         |
                      | (Chat UI or Control Panel NL UI)|
                      +-----------------+---------------+
                                        |
                                        | 1. User asks a graph-related question
                                        v
                              +---------+---------+
                              |     FASTAPI       |
                              |   Agents / Graph  |
                              +---------+---------+
                                        |
                                        | 2. Create AgentRun or call graph endpoint
                                        v
                           +------------+------------+
                           |      SECURITY LAYER     |
                           | (AuthZ, scopes, tenant) |
                           +------------+------------+
                                        |
                                        | 3. Check token, roles, tenant, limits
                                        v
                          +-------------+-------------+
                          |   ORCHESTRATOR SERVICE    |
                          +-------------+-------------+
                                        |
                                        | 4. Call Intent Classifier
                                        v
                         +--------------+--------------+
                         |     INTENT CLASSIFIER       |
                         +--------------+--------------+
                                        |
                                        | 5. Classify as GRAPH or similar
                                        v
                          +-------------+-------------+
                          |   ORCHESTRATOR (GRAPH MODE)|
                          +-------------+-------------+
                                        |
                                        | 6. Build NL→Cypher step
                                        v
          +-----------------------------+------------------------------+
          |       NL → CYPHER GENERATION COMPONENT                     |
          |------------------------------------------------------------|
          |                                                            |
          | 6.1 Normalize NL prompt                                    |
          |                                                            |
          | 6.2 Check if "Memgraph NL test mode" is enabled:           |
          |                                                            |
          |  +----------------------+           +-------------------+  |
          |  |  Test Mode Enabled? |           |  Test Mode Off    |  |
          |  +----------------------+           +-------------------+  |
          |             | YES                              | NO       |
          |             v                                  v          |
          |   [Load expected Cypher]               [Invoke LLM via   |
          |   from NL→Cypher hints JSON            LLM adapter /     |
          |   (prompt_hints.json)]                 provider pool]    |
          |     - Use normalized prompt as key     - Use resilience  |
          |     - Retrieve expected_cypher         - Generate Cypher |
          |                                                            |
          +-----------------------------+------------------------------+
                                        |
                                        | 7. Candidate CYPHER string
                                        v
                     +------------------+------------------+
                     |   CYPHER SAFETY & POLICY CHECKS    |
                     |------------------------------------|
                     | - Validate query shape             |
                     | - Enforce tenant boundaries        |
                     | - Block destructive operations     |
                     |   (e.g. DELETE all, DROP schema)  |
                     | - Optional row / time limits       |
                     +------------------+------------------+
                                        |
                                        | 8. If unsafe → error / refused
                                        |    If safe   → proceed
                                        v
                      +-----------------+-----------------+
                      |   MEMGRAPH ADAPTER & DRIVER       |
                      |-----------------------------------|
                      | - Open connection                 |
                      | - Execute Cypher query           |
                      | - Stream/collect results         |
                      +-----------------+-----------------+
                                        |
                                        | 9. Result rows / graph data
                                        v
                      +-----------------+-----------------+
                      |  GRAPH RESULT POST-PROCESSING    |
                      |-----------------------------------|
                      | - Limit rows, prune fields       |
                      | - Optionally compute aggregations|
                      | - Format as structured JSON      |
                      +-----------------+-----------------+
                                        |
                                        | 10. Summarize back to NL answer
                                        v
                          +-------------+-------------+
                          |   ORCHESTRATOR SERVICE    |
                          +-------------+-------------+
                                        |
                                        | 11. Persist:
                                        |     - AgentStep (Cypher, result summary)
                                        |     - Metrics (latency, rows, etc.)
                                        v
                      +-----------------+-----------------+
                      |   POSTGRESQL CONTROL PLANE       |
                      |  (AgentRun, Steps, Metrics)      |
                      +-----------------+-----------------+
                                        |
                                        | 12. Return enriched response:
                                        |     - Answer in NL
                                        |     - Optional Cypher + partial data
                                        v
                         +--------------+--------------+
                         |     API RESPONSE            |
                         +--------------+--------------+
                                        |
                                        | 13. UI renders:
                                        |     - Answer message
                                        |     - Orchestration step(s)
                                        |     - Optional “Show Cypher / Data”
                                        v
                              +---------+----------+
                              |    USER / CLIENT   |
                              +--------------------+
```

---

## 4) LLM Resilience & Provider Selection Flow (.txt)

This diagram shows **how the orchestrator selects and falls back across LLM providers** with circuit breakers and cost tracking.

```text
                         +---------------------------+
                         |     ORCHESTRATOR STEP     |
                         |   "Need an LLM response"  |
                         +-------------+-------------+
                                       |
                                       | 1. Request: model_name, context, budget
                                       v
                     +-----------------+-----------------+
                     |   LLM RESILIENCE ORCHESTRATOR    |
                     |----------------------------------|
                     | - Provider pool (config)         |
                     | - Circuit breakers               |
                     | - Cost tracker                   |
                     | - Retry / fallback rules         |
                     +-----------------+-----------------+
                                       |
                                       | 2. Resolve candidate providers
                                       |    (priority order, matching model)
                                       v
              +------------------------+-------------------------+
              |        PROVIDER POOL CONFIGURATION              |
              |-------------------------------------------------|
              | For each provider:                              |
              |   - Name (e.g., openai, ollama, stub)          |
              |   - Supported models                            |
              |   - Priority (1 = highest)                      |
              |   - Timeouts, max tokens                        |
              |   - Budget (per-day, per-run, etc.)             |
              |   - Circuit breaker config                      |
              +------------------------+-------------------------+
                                       |
                                       | 3. Iterate providers in priority order
                                       v
                +-----------------------------------------------------+
                | For each provider candidate:                        |
                |-----------------------------------------------------|
                | 3.1 Check circuit breaker:                          |
                |     - If OPEN  -> skip provider                     |
                |     - If HALF_OPEN -> allow limited trial           |
                |     - If CLOSED -> normal                            |
                |                                                     |
                | 3.2 Check cost tracker:                             |
                |     - If budget exceeded -> skip provider           |
                |                                                     |
                | 3.3 If both ok:                                     |
                |     a) Call provider adapter:                        |
                |        - Build request payload                      |
                |        - Apply timeouts & config                   |
                |        - Send to external LLM API or local service  |
                |     b) On success:                                  |
                |        - Update token usage & cost                  |
                |        - Update circuit breaker success counters    |
                |        - Return response to Orchestrator           |
                |                                                     |
                |     c) On failure (timeout, HTTP error, etc.):     |
                |        - Update circuit breaker error counters      |
                |        - Log error & metrics                        |
                |        - Try next provider in pool                  |
                +-----------------------------------------------------+
                                       |
                                       | 4. If SOME provider succeeds:
                                       v
                      +----------------+----------------+
                      | RETURN SUCCESSFUL LLM RESULT    |
                      |---------------------------------|
                      | - Chosen provider               |
                      | - Output text / JSON            |
                      | - Token usage, cost estimate    |
                      | - Fallback_used flag            |
                      +----------------+----------------+
                                       |
                                       v
                         +-------------+-------------+
                         |  ORCHESTRATOR STEP        |
                         +-------------+-------------+
                                       |
                                       | 5. Use LLM result to:
                                       |    - Plan next TODO step
                                       |    - Build Cypher/tool requests
                                       |    - Produce final answer
                                       v
                           [Rest of agent orchestration]

                                       |
                                       | 6. If ALL providers failed:
                                       v
                      +----------------+----------------+
                      | LLM FALLBACK FAILURE           |
                      |--------------------------------|
                      | - Compose structured error     |
                      | - ProblemDetail for API        |
                      | - Optionally suggest retry or  |
                      |   different model              |
                      +----------------+----------------+
                                       |
                                       v
                              [Error bubbled up]
```

---

## 5) (Bonus) Security & Request Lifecycle Diagram (.txt)

Given how central security is to your system, a third “important” diagram that is often useful in docs is a **request lifecycle with security hooks**—showing where auth, RBAC, rate limiting, and audit happen around *any* API call (agent, jobs, tools, admin, etc.).

```text
                  +-----------------------------+
                  |        CLIENT REQUEST       |
                  | (Chat UI / Control Panel)   |
                  +--------------+--------------+
                                 |
                                 | 1. HTTP request with:
                                 |    - Path, method
                                 |    - Authorization: Bearer <JWT>
                                 |    - Tenant header (optional)
                                 v
                      +----------+-----------+
                      |      API ROUTER     |
                      |    (FastAPI path)   |
                      +----------+-----------+
                                 |
                                 | 2. Pre-route dependencies
                                 v
                 +---------------+----------------+
                 |           SECURITY GATEWAY     |
                 |--------------------------------|
                 | A. Authentication              |
                 |    - Decode JWT                |
                 |    - Verify signature via JWKS |
                 |    - Check issuer, audience    |
                 |    - Check expiry              |
                 |                                |
                 | B. Principal & Tenant          |
                 |    - Extract subject           |
                 |    - Derive tenant (from claim|
                 |      or header)               |
                 |    - Build "principal" object  |
                 |                                |
                 | C. Authorization (RBAC)        |
                 |    - Roles & scopes from JWT   |
                 |    - Check required scopes for |
                 |      the endpoint (e.g.        |
                 |      agents:read, tools:admin) |
                 |                                |
                 | D. Rate Limiting               |
                 |    - Increment counters in     |
                 |      Redis (per user/tenant)   |
                 |    - If over limit -> reject   |
                 |                                |
                 | E. Audit Logging               |
                 |    - Record security event     |
                 |      (who, what, when, where)  |
                 +---------------+----------------+
                                 |
                                 | 3. If any check fails:
                                 |    - Return 401/403/429
                                 |    - ProblemDetail response
                                 v
                    [Security failure path ends here]

                                 |
                    (Otherwise security OK)
                                 v
                       +---------+----------+
                       |   ENDPOINT LOGIC   |
                       | (Service Layer)    |
                       +---------+----------+
                                 |
                                 | 4. Call services:
                                 |    - Orchestrator / Jobs / Tools /
                                 |      Models / Tenants / Admin
                                 v
                    +------------+-------------+
                    |  BUSINESS SERVICES       |
                    +------------+-------------+
                                 |
                                 | 5. Downstream calls:
                                 |    - Adapters (LLM, Redis, Memgraph)
                                 |    - Repositories (Postgres)
                                 |    - MCP tools (graph, data, security)
                                 v
                      [Core orchestration / DB ops]

                                 |
                                 | 6. Response assembled:
                                 |    - Data payload
                                 |    - HTTP status
                                 |    - Optional headers (ETag, deprecation)
                                 v
                      +----------+-----------+
                      |  OUTPUT GUARD & PII |
                      |     SCRUBBER        |
                      +----------+-----------+
                                 |
                                 | 7. Scrub logs & payload for PII
                                 |    - Mask sensitive fields
                                 |    - Enforce output policies
                                 v
                      +----------+-----------+
                      |   API RESPONSE       |
                      +----------+-----------+
                                 |
                                 | 8. Client receives:
                                 |    - Data
                                 |    - ProblemDetail on error
                                 v
                          +------+------+
                          |    CLIENT   |
                          +-------------+

---


                           CINECA AGENTIC PLATFORM – FULL ARCHITECTURE & WORKFLOW
                           ======================================================

                                      (Identity & Auth)
                              +-----------------------------------+
                              |        OIDC Identity Provider     |
                              |    (e.g. Auth0 – JWKS / OIDC)     |
                              +-----------------^-----------------+
                                                |
                       (1) Browser login / OAuth redirect, JWKS, token introspection
                                                |
   =============================================================================================
   CLIENTS & UI LAYER
   =============================================================================================

     +---------------------------+                       +-------------------------------+
     |  Agent Chat UI (ui_agent) |                       |  Control Panel UI             |
     |  - Next.js 14 app         |                       |  (ui_control_panel)          |
     |  - Tailwind, shadcn/ui    |                       |  - Streamlit app             |
     |  - Uses JWT access token  |                       |  - Uses JWT access token     |
     +--------------+------------+                       +---------------+--------------+
                    | (2) HTTPS: /v1/agents, /v1/agent-runs,                         |
                    |         /v1/jobs, /v1/tools, /v1/models, etc.                 |
                    +-------------------------+--------------------------------------+
                                              v
   =============================================================================================
   (OPTIONAL) EDGE / NETWORK LAYER
   =============================================================================================

                           +-------------------------------------------+
                           |      Reverse Proxy / API Gateway          |
                           |       (e.g. nginx with TLS, CORS)         |
                           |  - Routes /v1/* to app                    |
                           |  - Terminates HTTPS                       |
                           |  - Forwards Prometheus metrics if needed  |
                           +--------------------+----------------------+
                                                |
                                                | (3) Forwarded HTTP/HTTPS to backend
                                                v
   =============================================================================================
   CORE BACKEND – FASTAPI APPLICATION CONTAINER (`app`)
   =============================================================================================

   +------------------------------------------------------------------------------------------+
   |                                  FastAPI Backend (`app`)                                |
   |------------------------------------------------------------------------------------------|
   |  A. API LAYER (Routers)                                                                  |
   |     - /v1/health/*         : health, components, liveness, readiness, startup           |
   |     - /v1/auth/me          : current principal info                                     |
   |     - /v1/agents/*         : sessions, steps                                            |
   |     - /v1/agent-runs       : create / inspect agent runs                                |
   |     - /v1/tools/*          : MCP tools discovery & invocation                           |
   |     - /v1/jobs/*           : job creation, listing, SSE events                          |
   |     - /v1/models/*         : model instances, defaults, providers, manifests/builtins   |
   |     - /v1/admin/*          : tenants, DB ops, processes, ops overrides                  |
   |     - /v1/batch/*          : bulk operations (models, tools, etc.)                      |
   |     - /v1/export/*         : export/import of configs & tenants                         |
   |     - /v1/internal/*       : internal DB & ops endpoints                                |
   |     - /v1/ (root)          : API root/meta                                              |
   |                                                                                          |
   |  B. CROSS-CUTTING MIDDLEWARE                                                             |
   |     - JWT / OIDC validation (JWKS from Identity Provider)                               |
   |     - Tenant extraction from claims (multi-tenancy)                                     |
   |     - RBAC / scopes enforcement                                                         |
   |     - Rate limiting (Redis-backed sliding windows)                                      |
   |     - PII scrubbing and output guard                                                    |
   |     - Request/response logging, correlation IDs                                         |
   |                                                                                          |
   |  C. SERVICE LAYER & ORCHESTRATION                                                        |
   |     - Orchestrator Service (agent runs engine)                                          |
   |         * Intent classifier (CHAT / GRAPH / SECURITY / ADMIN / DANGEROUS)               |
   |         * Planner (TODO list / steps)                                                   |
   |         * Executor (LLM calls, MCP tools, Memgraph ops, DB reads/writes)                |
   |         * Reflection / synthesis of final answer                                        |
   |         * Mode routing:                                                                 |
   |             · CHAT: conversational agents                                               |
   |             · GRAPH: NL→Cypher, secure Memgraph query                                   |
   |             · SECURITY / ADMIN: privileged tools                                        |
   |             · DANGEROUS: refuse/explain or EXPLAIN-only path                            |
   |     - Session Service (agent sessions, message history)                                 |
   |     - Job Service (job creation, status, SSE log streaming)                             |
   |     - Default Model Resolver (tenant / role-aware default LLM selection)                |
   |     - Provider Service (providers & model instances)                                    |
   |     - ETL / Archive Services (graph ETL, snapshot, export/import)                       |
   |     - Health Service (aggregated component health via Health framework)                 |
   |     - Invocation Store (caching of tool results)                                        |
   |                                                                                          |
   |  D. MCP RUNTIME & TOOLING ECOSYSTEM                                                      |
   |     - MCP runtime (ToolContext, @mcp_tool decorator, RBAC checks, audit)                |
   |     - Tool registry (catalog of 30+ tools)                                              |
   |     - Tool policies (which principal can call which tool, with which scopes)            |
   |     - Tool categories (graph.*, cache.*, data.*, db.*, security.*, admin.*, utils.*,    |
   |       privacy, ratelimit, session, tenancy, user, viz, output, agent, system, etc.)     |
   |                                                                                          |
   |  E. ADAPTERS & RESILIENCE LAYER                                                          |
   |     - LLM adapters (OpenAI-style HTTP, Ollama local, demo providers, future providers)  |
   |     - Memgraph adapter (gqlalchemy client, connection pool, health checks)              |
   |     - Redis adapter (cache + job store helpers)                                         |
   |     - MCP adapter                                                                          |
   |     - Resilience framework:                                                              |
   |         * Retry/backoff policies                                                         |
   |         * Circuit breakers (CLOSED/OPEN/HALF_OPEN) per provider                         |
   |         * Cost tracking (tokens, $$ budgets)                                             |
   |         * Fallback between providers                                                     |
   |                                                                                          |
   |  F. DATA ACCESS LAYER (PostgreSQL Control + Repositories)                                |
   |     - SQLAlchemy models: Tenants, Agents, Sessions, Steps, Jobs, Events, Providers,      |
   |       Model Instances, Manifests, Defaults, Audit/InternalOps, Idempotency keys, etc.   |
   |     - Alembic migrations (26+ versions, JSONB, indexes, audit tables)                   |
   |     - Repository pattern (cursor pagination, ETag, caching, multi-tenant filters)       |
   |                                                                                          |
   |  G. REDIS INTEGRATION (via redis_cache module)                                           |
   |     - High-performance cache (JSON-encoded values, TTLs)                                |
   |     - Job store & queues (ZSET indexes, TTL job docs)                                   |
   |     - Session state, step sequencing, cancellation flags                                |
   |     - Rate-limit counters and sliding windows                                           |
   |     - Idempotency keys for APIs                                                         |
   |                                                                                          |
   |  H. MEMGRAPH DOMAIN INTEGRATION                                                          |
   |     - Graph domain schema (nodes & relationships for tasks, files, users, institutions) |
   |     - NL→Cypher pipeline (graph mode):                                                  |
   |         * Prompt normalization                                                          |
   |         * Cypher candidate generation (LLM / hints)                                     |
   |         * Safety validation (read-only / safe whitelist)                                |
   |         * Execution via Memgraph driver                                                 |
   |         * Result summarization to natural language                                      |
   |     - ETL import/export for datasets & synthetic data                                   |
   |                                                                                          |
   |  I. BACKGROUND FRAMEWORK (APScheduler)                                                   |
   |     - Periodic health checks (Postgres, Redis, Memgraph, providers)                     |
   |     - Provider health monitoring (latency / error rates)                                |
   |     - Backups (Memgraph archives, optional Redis)                                       |
   |     - Cleanup (expired keys, old job events, temp files)                                |
   |     - Metrics for background tasks                                                       |
   |                                                                                          |
   |  J. OBSERVABILITY FRAMEWORK                                                              |
   |     - Prometheus metrics (/metrics endpoint)                                            |
   |       * HTTP, agents, jobs, tools, rate limits, background tasks, etc.                  |
   |     - OpenTelemetry tracing (OTLP exporter → external collector)                        |
   |     - Structured logging with correlation IDs, tenant tags                              |
   |     - Health framework (component registry, policy-based readiness/startup)             |
   +------------------------------------------------------------------------------------------+

   (4) All DB/Cache/Graph/LLM calls are done through adapters + repositories + resilience.

   ============================================================================================
   WORKER & JOB PROCESSING LAYER
   ============================================================================================

   +--------------------------------------------------------------+
   |                   Worker Container (`worker`)                |
   |--------------------------------------------------------------|
   |  - Connects to Redis job queues & job store                  |
   |  - Connects to PostgreSQL control DB                         |
   |  - Uses same adapters / services for long-running tasks      |
   |  - Heartbeat & metrics (Prometheus + OTEL)                   |
   |                                                              |
   |  Job Execution Flow:                                         |
   |   (5a) Pop job ID from Redis queue (by type)                 |
   |   (5b) Load JobDocument metadata from Postgres               |
   |   (5c) Mark status → running; emit "running" JobEvent        |
   |   (5d) Execute handler (ETL, backup, maintenance, demo jobs) |
   |   (5e) Periodically check cancel flag in Redis               |
   |   (5f) Write final JobDocument + events in Postgres          |
   |   (5g) Push JobEvent entries to Redis SSE buffer             |
   +--------------------------------------------------------------+

   (6) Control Panel / API client subscribes to /v1/jobs/{id}/events (SSE)
       → reads events streamed from Postgres/Redis via app → UI.

   ============================================================================================
   DATA & INFRASTRUCTURE LAYER (STATEFUL SERVICES)
   ============================================================================================

           +-------------------------------+
           | PostgreSQL (`postgres`)       |
           |-------------------------------|
           | - Full control plane          |
           |   * Tenants & configs         |
           |   * Agent runs, sessions      |
           |   * Steps, metrics, outputs   |
           |   * Jobs & job events         |
           |   * Providers, models         |
           |   * Manifests, defaults       |
           |   * Audit, internal ops       |
           |   * Idempotency keys          |
           +-------------------------------+
                      ^              ^
          (7a) ORM & repos from app  | (7b) ORM & repos from worker
                      |              |

           +-------------------------------+
           | Redis (`redis`)               |
           |-------------------------------|
           | - Cache (sessions, configs)   |
           | - Job store & queues          |
           | - SSE event buffers           |
           | - Rate limit counters         |
           | - Locks, step sequencing      |
           | - Cancellation flags          |
           +-------------------------------+
                      ^              ^
        (8a) app uses redis_cache   | (8b) worker uses redis_cache

           +-------------------------------+
           | Memgraph (`memgraph`)         |
           |-------------------------------|
           | - Graph domain data           |
           | - Cypher queries              |
           | - Analytics, CRUD             |
           | - Test data & ETL imports     |
           +-------------------------------+
                      ^
          (9) app → adapters.get_client() (NL→Cypher, ETL, tools.graph.*)

           +-------------------------------+
           | Ollama (`ollama`)             |
           |-------------------------------|
           | - Local LLM endpoint          |
           | - Exposed via OpenAI-style    |
           |   HTTP API for adapters       |
           +-------------------------------+
                      ^
            (10) app adapters → HTTP completions via resilience layer

           +-------------------------------+
           | DB Populate (`db-populate`)   |
           |-------------------------------|
           | - One-shot init / migrations  |
           | - Seeds initial Memgraph data |
           | - Possibly seeds Postgres     |
           +-------------------------------+
                      ^
          (11) Runs during deployment / dev bootstrap

   ============================================================================================
   OBSERVABILITY & MONITORING STACK
   ============================================================================================

      +------------------------+        scrape /metrics          +------------------------+
      | Prometheus (`prometheus`) <-----------------------------+ FastAPI app (`app`)    |
      | - Scrapes app, worker, |                                 | Worker (`worker`)      |
      |   optionally Memgraph  |                                 +------------------------+
      +-----------+------------+
                  |
                  |  (12) PromQL queries
                  v
      +------------------------+
      | Grafana (`grafana`)    |
      | - Dashboards for:      |
      |   * HTTP, jobs, agents |
      |   * LLM providers      |
      |   * Background tasks   |
      |   * DB/Redis health    |
      +------------------------+

      +------------------------+
      | OTEL Collector / APM   |
      | - Receives OTLP traces |
      | - Stores in Tempo/Jaeger|
      +-----------^------------+
                  |
        (13) OTLP export from app & worker

   ============================================================================================
   EXTERNAL LLM PROVIDERS
   ============================================================================================

      +------------------------+        +------------------------+        +------------------+
      | OpenAI / Azure OpenAI |        | Other OpenAI-compatible|  ...   | Future providers |
      +-----------^------------+        +-----------^------------+        +---------^--------+
                  |                                 |                               |
        (14) HTTP calls via adapters & resilience (API keys, base URLs, timeouts, budgets)

   ============================================================================================
   HIGH-LEVEL END-TO-END WORKFLOW (TYPICAL AGENT RUN)
   ============================================================================================

   (1)  User logs in (Agent UI / Control Panel) with Identity Provider → receives JWT access token.
   (2)  UI calls backend endpoints (e.g. POST /v1/agent-runs) with Bearer token.
   (3)  Reverse proxy (optional) forwards request to FastAPI app.
   (4)  FastAPI app:
        - Validates JWT (JWKS) + extracts tenant & roles.
        - Applies rate limits & records observability spans/metrics.
        - API router delegates to Orchestrator Service.
   (5)  Orchestrator:
        - Runs Intent Classifier → decides CHAT / GRAPH / SECURITY / ADMIN / DANGEROUS.
        - Builds a plan (TODO steps) with LLM help.
        - For each step:
            * Calls LLM via adapters + resilience layer (OpenAI/Ollama/other).
            * Optionally invokes MCP tools (graph.*, data.*, security.*, admin.*, etc.).
            * For GRAPH mode, generates Cypher (NL→Cypher), validates, and queries Memgraph.
            * Reads/writes control plane data via repositories (Postgres).
            * Uses Redis for session state, caching, idempotency, cancellation flags.
        - Streams intermediate status/metrics into Postgres + Redis.
   (6)  Final response:
        - Orchestrator synthesizes final answer (text / structured JSON).
        - API returns normalized response to UI (agent-run details, steps, metrics).
        - Observability framework emits metrics & traces; health framework reflects component state.
   (7)  For long-running operations:
        - API creates JobDocument in Postgres, enqueues ID in Redis.
        - Worker pulls job, executes using same services/adapters.
        - Job events stored in Postgres and mirrored to Redis SSE buffers.
        - UI subscribes to /v1/jobs/{id}/events to show progress.
   (8)  Background Framework:
        - Periodically checks DB/Redis/Memgraph/LLM providers, runs backups, cleanup, etc.
        - Emits metrics & errors into observability stack.

---


                  CINECA AGENTIC PLATFORM - ARCHITECTURE (HIGH LEVEL)
                  ===================================================

                       +-------------------+      +----------------------+
                       |   End Users       |      |  Admins / Operators  |
                       +-------------------+      +----------------------+
                                  |                         |
                                  v                         v
                       +-------------------+      +----------------------+
                       | Agent Chat UI     |      | Control Panel UI     |
                       | (Next.js)         |      | (Streamlit)          |
                       +-------------------+      +----------------------+
                                  \                         /
                                   \                       /
                                    v                     v
                              +---------------------------------+
                              | Reverse Proxy / API Gateway     |
                              | (e.g. NGINX, TLS termination)   |
                              +---------------------------------+
                                               |
                                               v
                         +------------------------------------------------+
                         |            FASTAPI BACKEND APP                 |
                         |----------------------------------------------- |
                         |  Routers / API Layer:                          |
                         |   - Agents, Agent Runs                        |
                         |   - Jobs                                      |
                         |   - Tools (MCP)                               |
                         |   - Models & Providers                        |
                         |   - Tenants                                   |
                         |   - Auth, Health, Admin, Batch, Export/Import |
                         |                                               |
                         |  Middleware:                                  |
                         |   - JWT auth, RBAC checks                     |
                         |   - Rate limiting                             |
                         |   - Tracing / logging                         |
                         |   - RFC 7807 errors                           |
                         +----------------------+-------------------------+
                                                |
                 +------------------------------+------------------------------+
                 |                                                             |
                 v                                                             v
  +--------------------------------+                           +----------------------------------+
  |         Service Layer          |                           |        MCP Runtime & Tools       |
  |--------------------------------|                           |----------------------------------|
  | - Orchestrator Service         |                           | - Tool registry & policies       |
  | - Session Service              |   calls tools & adapters  | - Tool runtime (ToolContext)     |
  | - Job Service                  +---------------------------> - RBAC & audit for tools         |
  | - Default Model Resolver       |                           | - Telemetry for tool invocations |
  | - Health, ETL, Archive, etc.   |                           | - Tool implementations (17 cats) |
  +--------------------------------+                           +----------------------------------+
                 |                            |                           |
                 |                            |                           |
                 v                            v                           v
      +------------------+        +------------------+          +-------------------------+
      |  LLM Adapters    |        |  Graph Adapter   |          |   Cache / Queue Adapter |
      |------------------|        |  (Memgraph)      |          |   (Redis)               |
      | - OpenAI-style   |        |------------------|          |-------------------------|
      | - Ollama/local   |        | - Graph queries  |          | - Caching               |
      | - Stub providers |        | - NL→Cypher flow |          | - Job queues & events   |
      +------------------+        +------------------+          | - Rate limiting keys     |
                 |                            |                 | - Session / state        |
                 |                            |                 +-------------------------+
                 |                            |
                 v                            v
      +--------------------------+  +---------------------------+
      |  PostgreSQL Control      |  |  Memgraph Graph Database |
      |  Plane                   |  |---------------------------|
      |--------------------------|  | - Domain nodes/edges      |
      | - Tenants                |  | - Analytics & CRUD        |
      | - Providers & Models     |  | - Secure graph queries    |
      | - Agent Runs & Steps     |  +---------------------------+
      | - Jobs & Job Events      |
      | - Tools & Invocations    |
      | - Manifests & Processes  |
      | - Idempotency Keys       |
      | - Audit Logs             |
      +--------------------------+

                 +-----------------------------------------------------------+
                 |                    Worker Processes                       |
                 |-----------------------------------------------------------|
                 | - Consume job queues from Redis                           |
                 | - Load/update job records in PostgreSQL                  |
                 | - Execute long-running tasks (ETL, backups, etc.)       |
                 | - Append job events for SSE streaming                    |
                 +-----------------------------------------------------------+

                 +-----------------------------------------------------------+
                 |                 Security & Governance                     |
                 |-----------------------------------------------------------|
                 | - OIDC/JWT (e.g. Auth0)                                   |
                 | - JWT validation via JWKS                                 |
                 | - Roles, scopes, RBAC policies                            |
                 | - PII scrubbing & output guard                            |
                 | - Audit logs for tools, admin ops, dangerous actions      |
                 +-----------------------------------------------------------+

                 +-----------------------------------------------------------+
                 |                Observability & Health                     |
                 |-----------------------------------------------------------|
                 | - Metrics (Prometheus-friendly)                           |
                 |   * HTTP, agents, tools, jobs, rate limits, bg tasks      |
                 | - Tracing (OpenTelemetry, OTLP exporter)                  |
                 | - Health endpoints (live/ready/startup/components)        |
                 | - Used by external stack (Prometheus, Grafana, Jaeger)    |
                 +-----------------------------------------------------------+




---


                   CINECA AGENTIC PLATFORM - AGENT RUN / CHAT WORKFLOW
                   ====================================================

[1] USER AUTHENTICATION & SESSION SETUP
---------------------------------------

+-----------+           +-------------------+            +--------------------+
| End User  |  opens    | Agent Chat UI     |  redirects | OIDC Provider      |
| (browser) |---------->| (Next.js)         |----------->| (e.g. Auth0)       |
+-----------+           +-------------------+            +--------------------+
                             |   OAuth/OIDC login flow          |
                             |<---------------------------------+
                             |
                             |  receives ID token / access token (JWT)
                             v
                      +-------------------+
                      | Agent Chat UI     |
                      | (has JWT + tenant |
                      |  & roles info)    |
                      +-------------------+


[2] USER PROMPT → BACKEND (AGENT RUN CREATION)
----------------------------------------------

1. User types a message and selects a model (optional) in the Agent Chat UI.
2. UI sends an HTTP request with JWT:

   Agent Chat UI
      |
      |  POST /v1/agent-runs  (Authorization: Bearer <JWT>)
      v
   Reverse Proxy / API Gateway
      |
      v
   FastAPI Backend (Agents API)


[3] REQUEST HANDLING, SECURITY & ROUTING
----------------------------------------

+---------------------------------------------------+
| FastAPI Backend                                   |
|---------------------------------------------------|
| 1. Middleware:                                    |
|    - Validate JWT (issuer, audience, expiry).     |
|    - Extract subject, tenant, roles, scopes.      |
|    - Apply rate limiting via Redis.             |
|                                                   |
| 2. Request reaches Agents router:                 |
|    - Create initial Agent Run record in Postgres. |
|    - Store session metadata (tenant, user, model).|
+---------------------------------------------------+


[4] INTENT CLASSIFICATION & MODE SELECTION
------------------------------------------

FastAPI Backend (Agents Service)
      |
      v
+-----------------------------+
| Intent Classifier           |
|-----------------------------|
| - Analyze user prompt       |
| - Determine mode:           |
|   * CHAT                    |
|   * GRAPH                   |
|   * SECURITY                |
|   * ADMIN                   |
|   * DANGEROUS               |
+-----------------------------+
      |
      | mode + confidence + explanation
      v

+-----------------------------+
| Agent Orchestration Engine  |
+-----------------------------+


[5] ORCHESTRATION & STEP PLANNING
---------------------------------

Agent Orchestration Engine:
  1. Builds a TODO plan (multi-step run):
       - LLM reasoning steps
       - MCP tool calls (graph, data, security, etc.)
       - Optional long-running job submissions
  2. For each step, orchestrator executes:

     +---------------------------+
     | Step Execution Loop      |
     +---------------------------+
             |
             +--> [LLM Provider(s)] via adapters
             |        - Select provider/model via Default Model Resolver
             |        - Apply resilience: timeouts, circuit breakers, fallback
             |        - Track tokens & cost
             |
             +--> [MCP Runtime & Tools]
             |        - Check permissions & RBAC
             |        - Execute tools:
             |            * graph.* → Memgraph
             |            * cache.* → Redis
             |            * data.*, model.*, security.*, etc.
             |        - Log tool invocations in Postgres
             |
             +--> [Jobs Service] (if long-running)
                      - Create job in Postgres
                      - Enqueue job ID in Redis
                      - Worker picks job, runs it, updates events


[6] DATA & STATE INTERACTIONS
-----------------------------

During orchestration, components interact with:

- PostgreSQL (control plane)
  * Store/update: agent runs, steps, jobs, tools, manifests, audit logs.
  * Read: tenant & provider configuration, model defaults, invocations history.

- Redis (cache & coordination)
  * Cache: model configs, provider metadata, session state.
  * Queues: job IDs, job event buffers (for SSE).
  * Rate limiting: per user/tenant/scope.
  * Idempotency keys, cancellation flags.

- Memgraph (graph domain)
  * For GRAPH mode:
      1. LLM (or NL→Cypher logic) generates Cypher.
      2. Safety layer validates Cypher (no dangerous ops).
      3. Execute query on Memgraph.
      4. Results summarized into natural language or structured JSON.


[7] OUTPUT NORMALIZATION, AUDIT & METRICS
-----------------------------------------

After all required steps:

1. Orchestrator produces final answer (text and/or structured JSON).
2. Output is normalized (e.g. {"text": "..."} + optional data).
3. Security & governance layers run:
   - PII scrubbing for logs.
   - Output guard (safety checks).
   - Audit logs for sensitive/admin/dangerous operations.

4. Observability hooks:
   - Record metrics (latency, tokens, tool calls, errors).
   - Emit traces via OpenTelemetry.
   - Update health components status if needed.

5. Agent Run & Steps are persisted in PostgreSQL with:
   - Status (success/failed/cancelled).
   - Detailed step history and timings.
   - References to jobs and tools used.


[8] RESPONSE BACK TO UI & USER
------------------------------

+---------------------------------------------------+
| FastAPI Backend                                   |
|---------------------------------------------------|
| - Returns HTTP 200 with:                          |
|   * Final answer (text / JSON)                    |
|   * Optional run/steps metadata (IDs, status).    |
+---------------------------------------------------+
      |
      v
Reverse Proxy / API Gateway
      |
      v
Agent Chat UI (Next.js)
      |
      v
+---------------------------------------------------+
| Agent Chat UI                                     |
|---------------------------------------------------|
| - Polls /v1/agent-runs/{run_id} until completion  |
| - Displays:                                       |
|   * Conversation messages                         |
|   * Execution steps & tools used (if requested)   |
|   * Latency, token usage, error info              |
+---------------------------------------------------+
      |
      v
+--------------------+
|   End User         |
|  sees final answer |
+--------------------+


[9] LONG-RUNNING JOBS (CONTROL PANEL PATH - OPTIONAL)
-----------------------------------------------------

Admin / Operator (Control Panel UI):
  - Triggers long-running action (ETL, backup, maintenance) via Jobs or Admin APIs.
  - Flow:
      UI → FastAPI Jobs/Admin endpoints → Postgres job record
         → Redis job queue → Worker executes → Postgres + Redis events
         → SSE stream / polling back to Control Panel to show progress.


---


                         ┌───────────────────────────────┐
                         │           Users               │
                         │  - End users (chat)           │
                         │  - Admins / Operators         │
                         └───────────────┬───────────────┘
                                         │
                                         │ HTTP(S)
                                         ▼
                         ┌───────────────────────────────┐
                         │        Reverse Proxy          │
                         │      (e.g. NGINX / Ingress)   │
                         └───────────────┬───────────────┘
                                         │
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend (Core)                          │
│------------------------------------------------------------------------│
│  Routers / API Layer                                                   │
│  - /v1/agents, /v1/jobs, /v1/tools, /v1/models, /v1/admin, /v1/health  │
│                                                                        │
│  Services & Orchestrator                                               │
│  - Orchestrator Service (agent runs, multi-step flows)                 │
│  - Session Service (chat history, steps)                               │
│  - Intent Classifier (CHAT / GRAPH / ADMIN / SECURITY / DANGEROUS)     │
│  - Default Model Resolver, Archive, ETL, Health, Jobs                  │
│                                                                        │
│  MCP Runtime & Tools                                                   │
│  - MCP Runtime (RBAC, audit, telemetry)                                │
│  - Tool Registry & Policies                                            │
│  - Tool Families: graph.*, data.*, security.*, system.*, cache.*,      │
│    model.*, output.*, user.*, tenancy.*, session.*, ratelimit.*, ...   │
│                                                                        │
│  Security & Cross-Cutting                                              │
│  - OIDC / JWT validation, RBAC, scopes                                 │
│  - PII scrubber, output guard, rate limiting                           │
│  - Config & compute settings, utils, pagination, idempotency, ETags    │
│  - Observability: Prometheus metrics, OpenTelemetry tracing, logging    │
└───────────────┬────────────────────────────────────────────────────────┘
                │
                │ uses
                │
   ┌────────────┼───────────────────────┬───────────────────────────────┐
   │            │                       │                               │
   ▼            ▼                       ▼                               ▼
┌────────┐  ┌───────────────┐     ┌───────────────┐              ┌───────────────┐
│Postgres│  │    Redis      │     │   Memgraph    │              │  LLM Providers│
│Control │  │  Cache/Queues │     │  Graph Store  │              │ (OpenAI,      │
│ Plane  │  │  + Rate Limit │     │  + NL→Cypher  │              │  Ollama, ...) │
└────────┘  └───────────────┘     └───────────────┘              └───────────────┘
   ▲             ▲                         ▲                            ▲
   │             │                         │                            │
   │             │                         │ LLM calls + tool contexts  │
   │             │                         │                            │
   │        ┌────┴───────────────┐         │                            │
   │        │  Worker Processes  │─────────┘                            │
   │        │  (Jobs + Background│                                      │
   │        │   Tasks)           │                                      │
   │        └────────────────────┘                                      │
   │                                                                    │
   └────────────────────────────────────────────────────────────────────┘


Presentation Layer (UIs)
──────────────────────────────────────────────────────────────────────────
  - Next.js Agent Chat UI
      • Calls Agents API /v1/agent-runs, /v1/agents/sessions
      • Displays messages, steps, metrics, tool calls

  - Streamlit Control Panel UI
      • Uses admin + jobs + tools + models + tenants APIs
      • Operational dashboards (health, jobs, agents, models, tools)


---


                    ┌────────────────────────────┐
                    │   1. User in Agent Chat UI │
                    │   - Opens Next.js UI       │
                    │   - Authenticates (OIDC)   │
                    └───────────────┬────────────┘
                                    │
                                    │ sends prompt + token
                                    ▼
                     ┌────────────────────────────────┐
                     │ 2. FastAPI Agents API          │
                     │    POST /v1/agent-runs         │
                     └───────────────┬────────────────┘
                                     │
                                     │ validate token (OIDC/JWT)
                                     │ extract tenant, roles, scopes
                                     ▼
                     ┌────────────────────────────────┐
                     │ 3. Intent Classification       │
                     │ - Determine mode:              │
                     │   CHAT / GRAPH / SECURITY      │
                     │   ADMIN / DANGEROUS            │
                     │ - Compute confidence + reason  │
                     └───────────────┬────────────────┘
                                     │
                                     │ mode + context
                                     ▼
                     ┌────────────────────────────────┐
                     │ 4. Orchestrator Service        │
                     │ - Create Agent Run + Session   │
                     │ - Persist run in Postgres      │
                     │ - Initialize TODO plan         │
                     └───────────────┬────────────────┘
                                     │
                    ┌────────────────┼───────────────────────────────┐
                    │                │                               │
                    ▼                ▼                               ▼
           ┌────────────────┐ ┌────────────────┐           ┌────────────────────┐
           │ 5a. LLM Call   │ │ 5b. MCP Tools   │           │ 5c. Graph (Memgraph)│
           │ - Resolve model│ │ - via MCP       │           │ - NL→Cypher or     │
           │   (Default     │ │   runtime       │           │   direct Cypher    │
           │   Model Resolver││ - RBAC, audit   │           │ - Safety checks    │
           │ - Resilience   │ │ - Tool families │           │   (secure_query)   │
           │   (fallbacks,  │ │   graph.*,      │           │ - Execute query    │
           │   circuit      │ │   data.*,       │           │ - Summarize        │
           │   breakers,    │ │   security.*,   │           └────────────────────┘
           │   budgets)     │ │   system.*, ... │
           └────────────────┘ └────────────────┘

                    ▲                ▲                               ▲
                    │                │                               │
                    └───── results / partial answers / metrics ──────┘
                                     │
                                     ▼
                     ┌────────────────────────────────┐
                     │ 6. Orchestrator Step Loop      │
                     │ - For each step:               │
                     │   • Call LLM / tools / graph   │
                     │   • Record inputs/outputs      │
                     │   • Track tokens, latency, etc │
                     │   • Append to Postgres steps   │
                     │ - Check cancellation flags     │
                     │   (Redis)                      │
                     └───────────────┬────────────────┘
                                     │
                                     │ when plan done
                                     ▼
                     ┌────────────────────────────────┐
                     │ 7. Final Run Result            │
                     │ - Normalize output:            │
                     │   • text, JSON, or both        │
                     │ - Persist final state in DB    │
                     │ - Emit metrics (Prometheus)    │
                     └───────────────┬────────────────┘
                                     │
                                     │ GET /v1/agent-runs/{id}
                                     │ polling or SSE (if used)
                                     ▼
                   ┌─────────────────────────────────────┐
                   │ 8. Agent Chat UI Rendering          │
                   │ - Show user + agent messages        │
                   │ - Show steps, tools, metrics        │
                   │ - Allow follow-up question → new    │
                   │   step or new run                   │
                   └─────────────────────────────────────┘



---


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


**Figure X.Y – High-level architecture of the Cineca Agentic Platform.**
The Cineca Agentic Platform is organized in three main layers: client UIs, core backend, and data/infra, all integrated with an external identity provider, LLM providers, and an observability stack. On the client side, a Next.js-based Agent Chat UI provides an interactive interface for end users, while a Streamlit Control Panel UI targets operators and administrators; both obtain OAuth/OIDC JWTs from an external identity provider (e.g. Auth0) and call the FastAPI backend (optionally through a reverse proxy). The backend exposes a versioned HTTP API (agents, agent-runs, tools, jobs, models, tenants, admin, batch, export/import, internal, and health), and is surrounded by cross-cutting middleware for authentication/authorization (JWT + RBAC/scopes), multi-tenancy, rate limiting, PII scrubbing/output-guarding, structured logging, and tracing. Internally, the backend is structured around a service layer (orchestrator, session service, job service, default model resolver, provider service, ETL/archive, health, invocation store), an MCP runtime and tool ecosystem (graph, cache, data, db, security, admin, privacy, ratelimit, session, tenancy, user, viz, system, output, agent), and adapters that connect to PostgreSQL (control plane via repositories and Alembic migrations), Redis (cache, job queues, SSE buffers, rate limits, cancellation flags, idempotency), Memgraph (graph domain and NL→Cypher pipeline), and multiple LLM providers (local Ollama and external OpenAI-compatible providers) through a dedicated resilience framework (retries, circuit breakers, cost tracking, and provider fallback). A background framework (APScheduler) runs periodic health checks, provider monitoring, backups, and cleanup tasks, while observability is handled via Prometheus metrics, OpenTelemetry traces, and health probes, which can be consumed by Prometheus, Grafana, and an OTEL collector/APM.

Functionally, a typical agent workflow starts with a user authenticating against the identity provider and invoking the Agents or Agent-Runs API via the Agent UI or Control Panel. The FastAPI backend validates the JWT, enforces tenant and role constraints, and delegates to the Orchestrator Service. The orchestrator first classifies the intent (e.g. CHAT, GRAPH, SECURITY, ADMIN, DANGEROUS), then builds and executes a multi-step plan that may involve LLM calls (through the multi-provider resilience layer), MCP tool invocations, and, in graph mode, a secure NL→Cypher translation and Memgraph query. Throughout execution, state and metadata are persisted to PostgreSQL, ephemeral data and coordination go through Redis, and all operations produce metrics and traces. Long-running operations (e.g. ETL, backups, DB maintenance) are executed as background jobs: the API creates a job record in PostgreSQL and enqueues the job in Redis, workers consume and execute the job using the same service/adapters stack, and job events are streamed back to clients via SSE. In parallel, scheduled background tasks continuously monitor and maintain the health of Postgres, Redis, Memgraph, and LLM providers, ensuring the platform behaves as a production-ready, multi-tenant agentic AI system with strong guarantees on security, resilience, and observability.


---

**PROMPT TO GENERATE ARCHITECTURE + WORKFLOW DIAGRAM**

Create a detailed software architecture and workflow diagram for a project called **“Cineca Agentic Platform”**.

I want a **single, comprehensive diagram** (or a set of tightly related diagrams) that shows:

* All main components/containers
* How they are connected
* The **runtime workflows** of:

  * A typical agent run (chat / graph Q&A)
  * A long-running background job
  * Periodic background tasks (health checks, backups, cleanup)

Use a layered layout: **Clients & UIs → Edge/Proxy → Backend → Workers → Data/Infra → External LLM Providers + Observability**.

Please keep box names clear and close to the labels I give you below.

---

### 1. Top-level layers

Show these **layers from top to bottom**:

1. **Clients & UI Layer**
2. **(Optional) Edge / Reverse Proxy Layer**
3. **Core Backend (FastAPI app)**
4. **Worker & Job Processing Layer**
5. **Data & Infrastructure Layer (stateful services)**
6. **Observability & Monitoring Stack**
7. **External LLM Providers**
8. **Identity Provider (Auth/OIDC)**

---

### 2. Identity & Authentication

Add a box:

* `Identity Provider (OIDC / Auth0-like)`

  * Handles user authentication via OAuth/OIDC.
  * Publishes JWKS for JWT verification.

Connections:

* **UIs → Identity Provider**

  * Arrow: “User login / OAuth redirect, obtain JWT access token”
* **Backend → Identity Provider**

  * Arrow: “Fetch JWKS / OIDC metadata for validating tokens”

Place the Identity Provider slightly above or to the side of the clients but clearly connected to both UIs and Backend.

---

### 3. Clients & UI Layer

Add two main client boxes:

1. `Agent Chat UI (ui_agent)`

   * Next.js app (React, Tailwind, shadcn/ui).
   * Used by end users to chat with agents.
   * Stores/accesses JWT access tokens from the Identity Provider.
   * Calls backend endpoints like `/v1/agents`, `/v1/agent-runs`, `/v1/jobs`, `/v1/tools`, `/v1/models`, `/v1/health`.

2. `Control Panel UI (ui_control_panel)`

   * Streamlit app for operators and admins.
   * Uses JWT access tokens.
   * Calls backend endpoints for:

     * Managing tenants, models, providers, tools.
     * Listing jobs, streaming job events.
     * Running graph/NL→Cypher experiments.
     * Inspecting health and metrics.

Connections:

* Both UIs send HTTP(S) traffic to the **Edge / Reverse Proxy** (if present) or directly to the **FastAPI Backend**.

---

### 4. Edge / Reverse Proxy (optional)

Add:

* `Reverse Proxy / API Gateway (e.g. nginx)`

  * Terminates TLS.
  * Enforces basic routing, possibly CORS.
  * Routes `/v1/*` and `/metrics` to the FastAPI backend.
  * Can also route to UIs if served separately.

Connections:

* `Agent Chat UI` → `Reverse Proxy` → `FastAPI Backend`
* `Control Panel UI` → `Reverse Proxy` → `FastAPI Backend`

If you want to simplify, you can keep the proxy minimal but **keep the arrows correct**.

---

### 5. Core Backend – FastAPI Application (“app” container)

Add one large box:

**`FastAPI Backend (app)`**

Inside this box, show sub-components grouped logically:

#### 5.1 API Layer (Routers)

Sub-box: `API Routers`

Inside, list key domains / paths:

* `/v1/health/*` – health, components, liveness, readiness, startup
* `/v1/auth/me` – current user/principal info
* `/v1/agents/*` – sessions and steps
* `/v1/agent-runs` – create and inspect agent runs
* `/v1/tools/*` – MCP tools discovery & invocation
* `/v1/jobs/*` – job creation, listing, SSE events
* `/v1/models/*` – models, instances, providers, defaults, built-in manifests
* `/v1/admin/*` – tenants, DB ops, processes, overrides
* `/v1/batch/*` – batch/bulk operations (models, tools, etc.)
* `/v1/export/*` – export/import of platform configuration/tenants
* `/v1/internal/*` – internal DB and ops endpoints
* `/v1/` – API root/meta

Arrows:

* From `Reverse Proxy / UIs` into this `API Routers` box.

#### 5.2 Cross-Cutting Middleware

Sub-box: `Middleware & Cross-cutting Concerns`

Include:

* JWT/OIDC validation using JWKS from Identity Provider.
* Tenant extraction from JWT claims → multi-tenancy.
* RBAC & scope checks for authorization.
* Rate limiting based on Redis counters.
* PII scrubbing & output guard on responses.
* Request/response logging with correlation IDs.
* Tracing (OpenTelemetry instrumentation).

Connect:

* `API Routers` → `Middleware` → rest of backend internals.

(Conceptually, middleware wraps router handling.)

#### 5.3 Service Layer & Orchestrator

Sub-box: `Service Layer`

Inside list:

* `Orchestrator Service (Agent Runs Engine)`

  * Applies **Intent Classifier**:

    * Modes: `CHAT`, `GRAPH`, `SECURITY`, `ADMIN`, `DANGEROUS`.
  * Builds a multi-step plan (TODO list) using LLMs.
  * Executes steps:

    * LLM calls via resilience framework.
    * MCP tool invocations.
    * Memgraph queries in graph mode (NL→Cypher).
    * DB operations via repositories.
  * Performs reflection / synthesis of the final answer.
  * Enforces safety for `DANGEROUS` operations (refuse/EXPLAIN-only).

* `Session Service`

  * Manages agent sessions and message history.

* `Job Service`

  * Creates jobs in Postgres.
  * Enqueues job IDs into Redis queues.
  * Reads job status & events for SSE.

* `Default Model Resolver`

  * Chooses default LLM model for a given tenant + role.

* `Provider Service`

  * Manages model providers and model instances.

* `ETL / Archive Services`

  * Graph ETL, archive/restore state, import/export.

* `Health Service`

  * Aggregates component health from Postgres, Redis, Memgraph, providers.

* `Invocation Store`

  * Caches tool invocation results (to avoid re-running expensive tools).

#### 5.4 MCP Runtime & Tools

Sub-box: `MCP Runtime & Tooling Ecosystem`

Include:

* MCP Runtime:

  * `ToolContext` carrying principal, tenant, trace ID, etc.
  * `@mcp_tool` decorator pattern.
  * Permission checks (RBAC, scopes).
  * Auditing and metrics for tool executions.

* Tool Registry:

  * Central catalog of available tools.

* Tool Policy:

  * Defines which principal/role/tenant can invoke which tools.

* Tool Families (just list categories):

  * `graph.*`, `data.*`, `security.*`, `system.*`, `cache.*`, `catalog.*`,
    `db.*`, `privacy.*`, `ratelimit.*`, `session.*`, `tenancy.*`,
    `user.*`, `viz.*`, `output.*`, `agent.*`, `model.*`, etc.

Connect:

* `Service Layer (Orchestrator, Job Service, etc.)` → `MCP Runtime & Tools`.

#### 5.5 Adapters & Resilience Layer

Sub-box: `Adapters & Resilience`

Include:

* LLM adapters:

  * Call local LLM (Ollama).
  * Call external OpenAI-compatible providers.
  * Support multiple providers with different configs.

* Memgraph adapter:

  * Manages connections, runs Cypher, handles health checks.

* Redis adapter:

  * For caching, job queues, rate limits, SSE buffers, state.

* Resilience Framework:

  * Retry/backoff.
  * Circuit breakers with states `CLOSED / OPEN / HALF_OPEN`.
  * Cost tracking (tokens, cost per provider, budgets).
  * Provider fallback (switch to backup provider after failures or budget exceedance).

Connect:

* `Service Layer & Orchestrator` → `Adapters & Resilience` → external services (Postgres via repos, Redis, Memgraph, LLM providers).

#### 5.6 Data Access – Postgres Control Plane

Sub-box: `PostgreSQL Repositories (Control Plane)`

Include:

* SQLAlchemy models & Alembic migrations.

* Tables for:

  * Tenants
  * Agent Runs, Sessions, Steps, Metrics
  * Jobs & Job Events
  * Providers, Model Instances, Manifests, Defaults
  * Audit Logs, Internal Operations
  * Idempotency Keys

* Repository pattern:

  * Cursor-based pagination.
  * ETag support.
  * Multi-tenant filters.
  * Some caching integration.

Connect:

* `Service Layer` → `Postgres Repositories` → external `PostgreSQL` container.

#### 5.7 Redis Integration

Sub-box: `Redis Integration`

Include:

* Caching for hot entities and configs.
* Job store & job queues.
* Event buffers for SSE (job events).
* Rate limit counters & sliding windows.
* Session state, step sequencing.
* Cancellation flags for long-running operations.
* API idempotency keys.

Connect:

* `Service Layer` and `Job Service` → `Redis Integration` → external `Redis` container.

#### 5.8 Memgraph Domain & NL→Cypher

Sub-box: `Memgraph Domain & NL→Cypher`

Include:

* Graph schema for the domain:

  * Example nodes: `User`, `Institution`, `Task`, `File`, etc.
  * Relationships: `WORKS_AT`, `RUNS`, `INPUT`, `OUTPUT`, etc.

* NL→Cypher pipeline:

  * Normalizes natural language questions.
  * Generates candidate Cypher (using LLM/hints).
  * Validates queries for safety (read-only, tenant boundaries).
  * Executes on Memgraph.
  * Summarizes results back to natural language.

Connect:

* `Service Layer (Orchestrator, ETL, Tools graph.*)` → `Memgraph adapter` → `Memgraph` container.

#### 5.9 Background Framework (Scheduler)

Sub-box: `Background Framework (APScheduler)`

Include scheduled tasks:

* Health checks for Postgres, Redis, Memgraph, providers.
* Provider health monitoring (latency/error stats).
* Backups of Memgraph (and optionally Redis) as archives with manifests & checksums.
* Cleanup of stale data (old job events, expired keys, temp files).
* Emission of metrics about background task successes/failures.

Connect:

* `Background Framework` → uses `Service Layer` + `Adapters` + `Data Repositories`.

#### 5.10 Observability Framework

Sub-box: `Observability (Metrics, Traces, Logs, Health)`

Include:

* Prometheus metrics endpoint (`/metrics`).
* Metrics:

  * HTTP requests, latency, errors.
  * Agents: runs, steps, LLM tokens, latencies.
  * Tools: invocations, errors.
  * Jobs: counts, queue depth, processing times.
  * Rate limits & background tasks.
* OpenTelemetry tracing:

  * HTTP routes, DB queries, Redis calls, LLM calls, Memgraph queries.
* Health Framework:

  * Component registry and status (OK/degraded/unavailable).
  * Powers `/v1/health/*` endpoints.

---

### 6. Worker & Job Processing Layer

Add a container:

**`Worker (worker)`**

Inside:

* Connects to Redis job queues & job store.
* Connects to Postgres control plane.
* Uses the same **Service Layer**, **Adapters**, and **Repositories** as the backend for executing jobs.
* Emits metrics and traces via the same observability framework.

Show workflow:

1. `Worker` pops job IDs from Redis queue.
2. Loads job metadata from Postgres.
3. Marks job as `running`.
4. Executes the specific job handler (ETL, backup, maintenance, demo long-running job, etc.).
5. Checks cancellation flags in Redis periodically.
6. Updates Postgres job status (`finished`, `failed`, `cancelled`) and writes job events.
7. Pushes job events to Redis event buffers for SSE streaming.

Connections:

* `Worker` ↔ `Redis` (queues, events, cancellation flags).
* `Worker` ↔ `PostgreSQL`.
* `Worker` ↔ external Memgraph / LLM providers via adapters (if job needs them).
* `Worker` → Observability stack (metrics and traces).

---

### 7. Data & Infrastructure Layer (stateful services)

Add three main data containers:

1. **`PostgreSQL (postgres)`**

   * Control plane DB.
   * Stores:

     * Tenants
     * Agent runs, sessions, steps, metrics
     * Jobs & job events
     * Providers, models, manifests, defaults
     * Idempotency keys
     * Audit logs, internal operations

   Connections:

   * `FastAPI Backend (app)` ↔ `PostgreSQL`
   * `Worker` ↔ `PostgreSQL`

2. **`Redis (redis)`**

   * Cache.
   * Job store & queues.
   * Event buffers (for SSE).
   * Rate-limit counters.
   * Session/cancellation flags.

   Connections:

   * `FastAPI Backend (app)` ↔ `Redis`
   * `Worker` ↔ `Redis`
   * `Background Framework` inside `app` also interacts with `Redis`.

3. **`Memgraph (memgraph)`**

   * Graph database storing domain graph.
   * Used for Cypher queries and graph analytics.

   Connections:

   * `FastAPI Backend (app)` ↔ `Memgraph` (through adapters).
   * `Worker` ↔ `Memgraph` (for ETL, maintenance jobs).

Optionally add:

* `DB Populate / Migration Jobs`

  * A helper container or process that runs migrations and seeds Memgraph / Postgres.

---

### 8. Local LLM Provider

Add:

* `Ollama (Local LLM)`

Connections:

* `Adapters & Resilience` in `FastAPI Backend` → `Ollama` via HTTP.
* `Worker` may also call `Ollama` via the same adapters for jobs.

---

### 9. External LLM Providers

Add a group of boxes:

* `OpenAI / Azure OpenAI`
* `Other OpenAI-compatible Providers`
* (Optionally a generic `Future Providers`)

Connections:

* `Adapters & Resilience` in `FastAPI Backend` → these external LLM providers via HTTPS.
* These connections obey circuit breaker + cost tracking + fallback logic.

---

### 10. Observability & Monitoring Stack

Add:

1. **`Prometheus`**

   * Scrapes metrics from:

     * `FastAPI Backend (app)`
     * `Worker`
     * (Optionally) other components like Memgraph exporters.

2. **`Grafana`**

   * Connects to Prometheus to display dashboards.

3. **`OTEL Collector / APM`**

   * Receives traces via OTLP from `app` and `worker`.
   * Sends traces to a backend like Jaeger/Tempo/APM.

Connections:

* `FastAPI Backend (app)` → `Prometheus` (via `/metrics` scrape).
* `Worker` → `Prometheus` (via `/metrics`).
* `Prometheus` → `Grafana`.
* `FastAPI Backend (app)` → `OTEL Collector` (traces).
* `Worker` → `OTEL Collector` (traces).

---

### 11. Workflows to show (with numbered arrows)

Please annotate **major flows with step numbers** in the diagram:

#### 11.1 Agent Chat / Graph Q&A Workflow

1. User opens `Agent Chat UI` and authenticates with `Identity Provider` → gets JWT.
2. UI sends request (e.g. `POST /v1/agent-runs`) to `FastAPI Backend` via `Reverse Proxy`.
3. Backend validates JWT using JWKS from `Identity Provider`, extracts tenant & roles, applies rate limiting.
4. API Router calls `Orchestrator Service` in the **Service Layer**.
5. Orchestrator uses **Intent Classifier** to decide mode (CHAT/GRAPH/SECURITY/ADMIN/DANGEROUS).
6. Orchestrator builds a plan (TODO steps) using an LLM call via the **Adapters & Resilience** layer.
7. For each step:

   * Calls one or more LLM providers (Ollama / external).
   * Optionally invokes MCP tools (graph.*, data.*, security.*, admin.*, etc.).
   * If GRAPH mode:

     * NL→Cypher: generate Cypher → validate safety → execute on `Memgraph` → summarise results.
   * Reads/writes state to `PostgreSQL` via repositories (runs, steps, metrics).
   * Uses `Redis` for session state, caches, idempotency, cancellation flags.
8. Orchestrator synthesizes final answer (text / structured JSON).
9. API sends response back to `Agent Chat UI`.
10. Observability:

    * Metrics exposed to `Prometheus`, traces sent to `OTEL Collector`, logs written (with tenant/trace context).
    * Health framework updates component statuses as needed.

#### 11.2 Long-running Job Workflow

1. Operator uses `Control Panel UI` to trigger a long-running operation (e.g. ETL or backup) via `POST /v1/jobs` or admin DB endpoints.
2. Backend `Job Service`:

   * Creates a Job record in `PostgreSQL`.
   * Enqueues job ID in `Redis` job queue.
3. `Worker` process:

   * Pops job ID from `Redis`.
   * Loads job metadata from `PostgreSQL`.
   * Marks job as `running`, emits a `running` event.
   * Executes the job handler (which may use `Memgraph`, `Postgres`, `Redis`, and LLM providers).
   * Checks for cancellation flags in `Redis`.
   * Upon completion or error, updates job status in `PostgreSQL` and writes job events.
   * Pushes job events to `Redis` SSE buffers.
4. `Control Panel UI` subscribes to `/v1/jobs/{id}/events` (SSE) on the backend:

   * Backend reads job events from `PostgreSQL`/`Redis` and streams them to the UI in real time.

#### 11.3 Background Tasks Workflow

1. `Background Framework (APScheduler)` in the backend wakes up periodically.
2. Runs health checks:

   * Ping `PostgreSQL`, `Redis`, `Memgraph`, and LLM providers.
3. Runs backups:

   * Export Memgraph data into archives, optionally Redis snapshots.
   * Store manifests, timestamps, checksums.
4. Runs cleanup tasks:

   * Prune stale job events, expired Redis keys, temporary files.
5. Background tasks record results (success/failure) and emit metrics to `Prometheus` and traces to `OTEL Collector`.
6. Health status is reflected in `/v1/health/*` endpoints and visible via the `Control Panel UI`.

---

### 12. Visual Style Suggestions

* Use **layered layout** (top: UIs & Identity; middle: Backend & Workers; bottom: Data & External Providers).
* Group subcomponents into boxes inside the **FastAPI Backend** to show:

  * API Routers
  * Middleware
  * Service Layer
  * MCP Runtime
  * Adapters & Resilience
  * Repositories (Postgres)
  * Redis Integration
  * Memgraph Domain & NL→Cypher
  * Background Framework
  * Observability
* Use **numbered arrows** and short labels to depict workflows as described.

---