# Cineca-Agentic-Platform

https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform

<!-- markdownlint-disable MD003 -->

Lightweight summary
--------------------

`Cineca-Agentic-Platform` is an agentic platform built around FastAPI, Memgraph (graph DB), Redis (cache/rate-limit), and pluggable LLM backends. It exposes a tools-based interface that can convert natural-language requests into Cypher/queries, orchestrate agent runs, and provide secure, multi-tenant APIs for programmatic and interactive use.

This repository contains:

- A FastAPI backend (sources under `src/`).
- DB helpers and a small dataset in `db/` (Memgraph populate scripts and sample data).
- Examples and tools in `examples/` and a Streamlit UI under `ui_control_panel/`.
- Operational manifests and observability tooling in `ops/`, `prometheus` and `grafana` provisioning.
- End-to-end and unit tests in `tests/`.

Key features
------------

- Natural language -> Cypher/SQL/NoSQL conversions and tool-based workflows.
- Pluggable multi-LLM registry and per-tool LLM preferences.
- Agent orchestration with session-scoped prompts/roles.
- Multi-tenant and role-based access controls with audit logging.
- Guardrails: intent filtering, PII scrubbing, and output guards (configurable via env).
- Full observability: Prometheus metrics, Grafana dashboards, and traces.
- Container-first: Dockerfile and `docker-compose.yml` for local stacks.

Status
------

Actively developed as a thesis project. The codebase includes:

- Runtime API and admin surfaces (admin routes are opt-in via `ENABLE_ADMIN_ROUTES`).
- Background jobs, health checks, and lifecycle helpers for model process management.
- Automated tests covering unit, integration, and e2e scenarios (see `tests/`).

**For Operators:** 📘 See **[Operator Runbook](docs/OPERATOR_RUNBOOK.md)** for deployment, configuration, troubleshooting, and maintenance procedures.

Quick Start — Production Deployment
------------------------------------

Get the platform running in production with all services in under 5 minutes:

```bash
# 1. Clone and configure
git clone https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform.git
cd Cineca-Agentic-Platform
cp .env.example .env

# 2. Set required secrets in .env
# Edit: JWT_SECRET, DB_PASSWORD, REDIS_PASSWORD, AUTH0_* (if using Auth0)

# 3. Start all services
docker compose up -d

# 4. Wait for healthy status (~30s)
docker compose ps

# 5. Verify health
curl http://localhost:8000/v1/health/ready

# 6. Configure defaults (provider + model)
# Via UI: http://localhost:8501 → Admin → Providers → Set Default
# Via API: see docs/OPERATOR_RUNBOOK.md#configure-defaults
```

**What's Running:**

- API server: `http://localhost:8000` (FastAPI)
- UI: `http://localhost:8501` (Streamlit)
- PostgreSQL: `localhost:5432` (persistent storage)
- Redis: `localhost:6379` (cache, queues)
- Memgraph: `localhost:7687` (graph database)
- Ollama: `localhost:11434` (local LLM inference)
- Grafana: `http://localhost:3000` (metrics dashboard, admin/admin)
- Prometheus: `http://localhost:9090` (metrics storage)

**Next Steps:**

- 📘 **[Operator Runbook](docs/OPERATOR_RUNBOOK.md)** - Configure defaults, troubleshooting, monitoring
- 🔐 **[Authentication Guide](docs/AUTH_GUIDE.md)** - Set up Auth0 or machine tokens
- 🛠️ **[UI Guide](ui_control_panel/README.md)** - Using the Streamlit interface
- 📊 **[Monitoring Setup](docs/OPERATOR_RUNBOOK.md#monitoring-setup)** - Grafana dashboards and alerts
- 🧪 **[Testing Guide](tests/README.md)** - Run the test suite

Quickstart — Development

1. Create a virtualenv and install deps (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

1. Copy example env and tweak if needed:

```bash
cp .env.example .env
# Edit .env to configure MG_HOST, MG_PORT, JWT_SECRET, etc.
```

1. Run the app locally (dev reload):

```bash

uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

Or use Docker Compose to run a full stack (Memgraph, Redis, Prometheus):

```bash
docker compose up -d --build
docker compose logs -f app
```

Core endpoints
--------------

- Health: GET /v1/health/live and GET /v1/health/ready
- Agents (agentic runs): POST /v1/agents:run
- Models / LLM registry & management: under `/v1/models` (and `/v1/admin` when admin routes are enabled)
- OpenAPI: `/v1/openapi.json` (or `/docs` if `ENABLE_DOCS=true`)

Current API Surface
-------------------

Version: 0.1.0 · OAS: 3.1

Servers: `/v1` · spec at `/v1/openapi.json`

Meta

- GET `/v1/` — Quick sanity check. Returns basic service info.

Health

- GET `/v1/health/live` — “Process is running?” (yes/no). Use for container liveness.
- GET `/v1/health/ready` — “Ready to serve traffic?” (deps OK). Use for load balancers.
- GET `/v1/health/startup` — Detailed startup checks (init, migrations, deps). Use for debugging boot issues.

Auth

- POST `/v1/auth/token` — (If enabled) exchange credentials for a JWT. Runtime identity everywhere else is the token subject (`sub`), not a username.
- GET `/v1/auth/me` — Show who we are (claims/roles) based on our JWT.

Agents

- POST `/v1/agent-runs` — One-shot agent run on our prompt. No session, just input → output.
- POST `/v1/agents/sessions` — Start a long-lived agent session (keeps context/memory).
- GET `/v1/agents/sessions/{id}` — Fetch current session state (history, status).
- POST `/v1/agents/sessions/{id}/steps` — Send the next user/tool step inside a session.
- DELETE `/v1/agents/sessions/{id}` — Stop an in-flight session.

Tools

- GET `/v1/tools` — Show all available tools the agent can use.
- GET `/v1/tools/{name}` — Details for one tool (what it does + input schema).
- POST `/v1/tools/{name}/invocations` — Call a tool directly (bypass the agent).

Jobs

- GET `/v1/jobs/{id}` — Check a background job’s status/result.
- DELETE `/v1/jobs/{id}` — Stop a running job.
- POST `/v1/jobs` — Create a background job (canonical way).
- GET `/v1/jobs/{id}/events` — Live stream job events/logs via SSE.

Models — Catalog

- GET `/v1/models` — List models currently exposed (ids, capabilities).
- POST `/v1/models/completions` — Basic text completion (single-turn, simple input).
- POST `/v1/models/chat/completions` — Chat completion (multi-message format).
- POST `/v1/models/embeddings` — Generate vector embeddings for text.

Models — Instances (Admin)

- GET `/v1/admin/models/instances` — See all loaded model instances.
- POST `/v1/admin/models/instances` — Load/prepare a model into memory.
- GET `/v1/admin/models/instances/{id}` — Inspect one instance (state/metrics).
- DELETE `/v1/admin/models/instances/{id}` — Unload to free resources.
- POST `/v1/admin/models/instances/{id}/tests` — Quick smoke prompt to verify it works.

Defaults (Admin)

- GET `/v1/admin/models/defaults` — See which model is used by default.
- PATCH `/v1/admin/models/defaults` — Change the default model selection.

Manifests (Admin)

- GET `/v1/admin/models/manifests/builtins` — List available built-in manifests.
- POST `/v1/admin/models/manifests/builtins:stage` — Stage a remote built-ins manifest (preview).
- POST `/v1/admin/models/manifests/builtins:activate` — Make the staged manifest active.
- POST `/v1/admin/models/manifests/builtins:rollback` — Revert to prior active manifest.
- GET `/v1/admin/models/manifests/builtins/history` — See activation/rollback history.

Providers (Admin)

- GET `/v1/admin/models/providers` — List configured LLM providers (e.g., OpenAI, local).
- POST `/v1/admin/models/providers/register` — Register a new provider (keys, endpoints).
- GET `/v1/admin/models/providers/main` — Show which provider is currently “main”.
- GET `/v1/admin/models/providers/{id}` — Get one provider’s details.
- PATCH `/v1/admin/models/providers/{id}` — Update provider settings.
- DELETE `/v1/admin/models/providers/{id}` — Remove a provider.
- POST `/v1/admin/models/providers/{id}:setDefault` — Make this provider the default.

Processes (Admin)

- GET `/v1/admin/processes` — List platform processes (PIDs/roles).
- DELETE `/v1/admin/processes/{pid}` — Stop a specific process.
- GET `/v1/admin/processes/history/manifests` — Manifest operations history.
- GET `/v1/admin/processes/history/processes` — Process start/stop history.

Jobs (Admin Proxy)

- GET `/v1/admin/jobs` — List all jobs (admin view).
- POST `/v1/admin/jobs` — Create a job on behalf of others/admin flows.
- DELETE `/v1/admin/jobs/{id}` — Cancel a job from the admin side.

Tenants (Admin)

- GET `/v1/admin/tenants` — List tenants (multi-tenant setups).
- POST `/v1/admin/tenants` — Create a tenant (ids, quotas, policies).
- GET `/v1/admin/tenants/{id}` — Inspect a tenant.
- PATCH `/v1/admin/tenants/{id}` — Update tenant metadata/settings.
- DELETE `/v1/admin/tenants/{id}` — Remove a tenant.

Internal Ops

- POST `/v1/internal/ops/auto-start-override` — Force the demo UI to auto-start/stop.
- GET `/v1/internal/ops/preview-staged` — Show what’s staged before activation (safety check).
- POST `/v1/internal/db/jobs` — Build or populate a DB from a dataset (runs in background; use request body to indicate `mode=create|populate`).
- GET `/v1/internal/db/jobs/{job_id}` — Track DB job progress.
- GET `/v1/internal/db/counts` — Quick node/edge counts for sanity checks.
- DELETE `/v1/internal/db/jobs/{job_id}` — Cancel a DB job mid-run.

Configuration
-------------

Most runtime configuration comes from environment variables. Important ones:

- `MG_HOST`, `MG_PORT` — Memgraph host/port used by the DB adapter.
- `REDIS_URL` or `redis` service — Redis for caching and rate limiting.
- `ENABLE_ADMIN_ROUTES` — enable admin-only management APIs when set.
- `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` — auth configuration.
- `OLLAMA_BASE_URL`, `OLLAMA_TIMEOUT_SECS`, `OLLAMA_MODEL_MAP` — tune local Ollama connectivity, timeouts, and logical → tag mappings. The compose stack pre-wires `host.docker.internal` to the host gateway so `OLLAMA_BASE_URL=http://host.docker.internal:11434` works on Linux and macOS alike (see `docs/ollama.md`).
- Guardrail toggles: `INTENT_FILTER_ENABLED`, `OUTPUT_GUARD_ENABLED`, `PII_SCRUBBING_ENABLED`.

Multi-LLM configuration (overview)
---------------------------------

The platform supports registering multiple LLM backends and mapping tools or agent roles to specific LLMs. Configuration is flexible and accepts JSON or simple k=v lists via environment variables or admin APIs.

- `LLM_CLIENTS` — comma-separated named endpoints (e.g. `planner=http://planner:8080,workerA=http://worker-a:8080`).
- `LLM_TOOL_PREFERENCES` — mapping of tool->preferred LLM (JSON or `k=v` pairs).
- `LLM_AGENT_ROLES` — JSON role -> system prompt prefixes to influence agent behaviors.
- `LLM_TOOL_ACL` — allow-list mapping of clients->tools.

Runtime management & admin APIs
------------------------------

When `ENABLE_ADMIN_ROUTES=1` the admin surface is mounted under `/v1/admin` (example: `/v1/admin/models/llms`). Admin endpoints support listing, registering, and removing LLM clients, updating tool preferences, roles, and ACLs. These APIs are intended for operator usage and should be protected by authentication (JWT or admin tokens).

Security posture for these routes:

- All `/v1/admin/*` requests must present a JWT via the documented HTTP Bearer scheme. Missing tokens receive `401 Unauthorized`.
- Authorization requires the `admin:all` scope (automatically granted when the token's `roles` claim includes `admin`). Requests without it are rejected with `403 Forbidden`.
- The generated OpenAPI contract ships with a single `HTTPBearer` security scheme so tooling can re-use the same credential flow everywhere.

Example (conceptual payloads):

- Register LLM: POST `/v1/admin/models/llms` {name, base_url, model?, api_key?}
- Set prefs: POST `/v1/admin/models/prefs` {prefs: {"search": "workerA"}}
- Run agent with overrides: POST `/v1/agent-runs` with fields `manager`, `llm_preferences`, `agent_role`.

Examples and Dev tooling
------------------------

- `examples/` contains small API/HTTP/py examples for running tools and demo flows.
- `ui_control_panel/` includes a lightweight Streamlit UI for manual testing and demoing LLM registration and session runs.

Observability & Ops
--------------------

- Prometheus & Grafana provisioning under `ops/` and `ops/grafana`.
- Metrics instrumented via `src/observability` and Prometheus client. Container health checks are configured in the `Dockerfile` and `docker-compose.yml`.

### Redis Job Store (Production Features)

The platform supports dual job storage backends: in-memory (default) or Redis (production). Switch backends via `JOB_STORE_BACKEND=redis`.

**Documentation**:
- 🚀 **[Quick Start Guide](docs/redis-job-store-quickstart.md)** - Backend switching, troubleshooting, monitoring
- 📘 **[Production Guide](docs/redis-job-store-production.md)** - Complete feature overview, configuration, runbooks
- ✅ **[Production Checklist](scripts/production_checklist.sh)** - Interactive validation script

**Key Features**:
- ✅ Atomic job cancellation (Lua CAS scripts) - race-free concurrent operations
- ✅ Automatic index hygiene (background orphan cleanup)
- ✅ 13 Prometheus metrics + 8 alert rules for observability
- ✅ CI matrix testing (both backends in GitHub Actions)
- ✅ SSE resilience with Last-Event-ID resume
- ✅ TTL-based auto-expiry (jobs: 10 days, idempotency: 24h)

**Quick Start**:
```bash
# Switch to Redis backend
export JOB_STORE_BACKEND=redis
export REDIS_URL=redis://localhost:6379/0

# Run production checklist
./scripts/production_checklist.sh

# Monitor metrics
curl http://localhost:8000/metrics | grep job_
```

### PostgreSQL Tenant Persistence (Production Ready)

The admin-tenants API uses PostgreSQL 16 for production-grade persistence with full ACID guarantees, connection pooling, and automatic migrations.

**Documentation**:
- 📘 **[Complete Migration Summary](POSTGRES_MIGRATION_COMPLETE.md)** - Comprehensive implementation guide
- 🔧 **[Database Tooling](db/postgres_control/)** - Initialization scripts and seed data
- ✅ **[Validation Script](scripts/validate_postgres_migration.sh)** - Automated endpoint testing

**Key Features**:
- ✅ Full CRUD with idempotency (exact match returns existing, conflict returns 409)
- ✅ Keyset pagination for performance at scale (ORDER BY created_at DESC, id ASC)
- ✅ JSONB metadata with deep merge (PostgreSQL || operator)
- ✅ ETag-based HTTP caching (computed from id + updated_at + version)
- ✅ SQLAlchemy 2.0 ORM with Alembic migrations
- ✅ Connection pooling (QueuePool: size=10, overflow=20, timeout=30s)
- ✅ Auto-migration on container startup
- ✅ Health monitoring at `/v1/health/db`

**Quick Start**:
```bash
# Configure database (already in .env.example)
export DB_HOST=postgres
export DB_PORT=5432
export DB_NAME=cineca_agentic_db
export DB_USER=postgres
export DB_PASSWORD=your_secure_password

# Start with Docker Compose (PostgreSQL included)
docker compose up -d

# Migrations run automatically on startup
# Or manually: make db-migrate

# Seed demo data
make db-seed

# Validate integration
./scripts/validate_postgres_migration.sh

# Database management
make db-shell     # Open PostgreSQL shell
make db-logs      # View database logs
make db-reset     # Reset database (destructive!)
```

**Repository Pattern**:
All admin-tenants endpoints use the `TenantsRepository` abstraction for data access:
- `list(page_size, page_token)` - Keyset pagination with total count
- `create(name, email, metadata)` - Returns (tenant, was_created) for idempotency
- `get_by_id(tenant_id)` - Single tenant lookup
- `update_partial(...)` - JSONB deep merge for metadata
- `delete(tenant_id)` - With dependency cascade checking

**Database Schema**:
```sql
CREATE TABLE tenants (
    id VARCHAR(255) PRIMARY KEY,                    -- tenant-xxxxxxxx
    name VARCHAR(255) NOT NULL,
    admin_email VARCHAR(320) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 1,
    
    CONSTRAINT uq_tenants_name_ci UNIQUE (LOWER(name))  -- Case-insensitive uniqueness
);

-- Auto-update trigger for updated_at and version
CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

**API Contracts Preserved**:
- ✅ All status codes: 200, 201, 204, 304, 404, 409, 422
- ✅ All headers: ETag, Link, Location, X-Event-Id, X-Trace-Id
- ✅ RFC 7807 error responses
- ✅ Provenance logging
- ✅ Zero breaking changes to existing clients

### PostgreSQL Jobs & Worker (Production Ready)

The jobs API (`/v1/jobs`) uses PostgreSQL for persistent job storage with a dedicated background worker service for asynchronous job processing.

**Documentation**:
- 📘 **[Worker Deployment Guide](docs/worker-guide.md)** - Complete operator guide for deploying and managing the worker
- ⚙️ **[Environment Variables](docs/environment-variables.md)** - Comprehensive configuration reference (40+ variables)
- ✅ **[Task 11 Summary](TASK_11_WORKER_COMPLETE.md)** - Worker implementation details

**Key Features**:
- ✅ **Persistent Jobs**: All job data stored in PostgreSQL (survives restarts)
- ✅ **Background Worker**: Dedicated Docker service for job processing
- ✅ **Queue-Based**: Redis queues for fast job distribution (demo, test, long-running)
- ✅ **Status Lifecycle**: queued → running → finished/failed/cancelled
- ✅ **Event Logging**: SSE streaming with job events (status transitions, progress updates)
- ✅ **Heartbeat Monitoring**: Worker updates job timestamps to indicate liveness
- ✅ **Graceful Shutdown**: Handles SIGTERM/SIGINT for clean shutdown
- ✅ **Health Checks**: `/v1/health/db` (PostgreSQL), `/v1/health/redis` (Redis + queue stats)

**Quick Start**:
```bash
# Enable PostgreSQL jobs (already in .env.example)
export USE_POSTGRES_JOBS=true

# Start all services including worker
docker compose up -d

# Create a test job
curl -X POST http://localhost:8000/v1/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "test", "payload": {"message": "Hello Worker!"}}'

# Monitor job via SSE
curl http://localhost:8000/v1/jobs/$JOB_ID/events \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream"

# Check worker logs
docker compose logs -f worker

# Check queue statistics
curl http://localhost:8000/v1/health/redis
# Returns: {"ok": true, "queues": {"demo": 0, "test": 2, "long-running": 1}}
```

**Worker Configuration**:
```yaml
# docker-compose.yml (already configured)
worker:
  container_name: jobs-worker
  command: ["python", "-u", "-m", "src.workers.jobs_worker"]
  environment:
    USE_POSTGRES_JOBS: "true"
    JOB_WORKER_POLL_INTERVAL: "1.0"      # Queue polling (seconds)
    JOB_WORKER_HEARTBEAT_INTERVAL: "5.0" # Heartbeat update (seconds)
    ALLOWED_JOB_TYPES: "demo,test,long-running"
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  restart: unless-stopped
```

**Job Types**:
- **demo**: Sleep simulation (tests worker execution time)
- **test**: Instant echo (verifies end-to-end flow)
- **long-running**: Multi-step processing (future use)

**Database Schema**:
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

**Monitoring**:
- PostgreSQL health: `GET /v1/health/db` → `{"ok": true, "database": "postgresql"}`
- Redis health + queues: `GET /v1/health/redis` → `{"ok": true, "queues": {"demo": 0, "test": 2}}`
- Worker logs: `docker compose logs -f worker`
- Job status: `SELECT id, type, status, queue_latency_ms, exec_latency_ms FROM jobs ORDER BY created_at DESC LIMIT 10;`

### PostgreSQL Tools Persistence (Production Ready)

The tools API (`/v1/tools`) uses PostgreSQL + Redis dual-layer architecture for persistent tool invocations with strong consistency, auditability, and performance.

**Documentation**:
- 📐 **[Architecture Guide](docs/tools-architecture.md)** - Data flow, idempotency, caching strategy
- 🚀 **[Migration Guide](docs/tools-migration-guide.md)** - Step-by-step migration from legacy storage
- ✅ **[Implementation Summary](TOOLS_POSTGRES_REDIS_IMPLEMENTATION.md)** - Complete feature inventory

**Key Features**:
- ✅ Dual-layer storage: PostgreSQL for persistence + Redis for caching
- ✅ Idempotency with conflict detection (409 on parameter mismatch)
- ✅ Automatic audit trail (tool_audit_events table)
- ✅ ETag-based HTTP caching with 304 Not Modified
- ✅ Anti-enumeration security (404 for non-owners)
- ✅ 5 Prometheus metrics (invocations, duration, cache hits, conflicts, queue depth)
- ✅ Structured logging with correlation IDs
- ✅ Sub-10ms GET latency on cache hits
- ✅ Graceful fallback to legacy invocation_store

**Quick Start**:
```bash
# PostgreSQL is already configured if using Docker Compose

# Migrations run automatically on startup
# Or manually: make db-migrate

# Test tool invocation
curl -X POST http://localhost:8000/v1/tools/system.health/invocations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"args": {"action": "liveness"}}'

# Response includes event_id and Location header:
# {
#   "event_id": "abc-123-def",
#   "ok": true,
#   "result": {"healthy": true},
#   "duration_ms": 42
# }

# Retrieve invocation (supports ETag caching)
curl http://localhost:8000/v1/tools/system.health/invocations/$EVENT_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "If-None-Match: $ETAG"  # Returns 304 if unchanged

# Monitor metrics
curl http://localhost:8000/metrics | grep tools_
```

**Database Schema**:
```sql
CREATE TABLE tools (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL DEFAULT '1',
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(id),
    input_schema JSONB,
    description TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(name, version, tenant_id)
);

CREATE TABLE tool_invocations (
    id SERIAL PRIMARY KEY,
    eid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    tool_name VARCHAR(255) NOT NULL,
    tool_version VARCHAR(50) NOT NULL DEFAULT '1',
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(id),
    params_json JSONB,
    result_json JSONB,
    error_json JSONB,
    status VARCHAR(50) DEFAULT 'pending',  -- pending, running, finished, failed
    latency_ms INTEGER,
    requested_by VARCHAR(255),
    idempotency_key VARCHAR(255),
    request_headers JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(idempotency_key, tool_name)  -- Prevents duplicate processing
);

CREATE TABLE tool_audit_events (
    id SERIAL PRIMARY KEY,
    invocation_eid UUID NOT NULL REFERENCES tool_invocations(eid),
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB,
    performed_by VARCHAR(255),
    performed_at TIMESTAMP DEFAULT NOW()
);
```

**Redis Key Patterns**:
- `tools:queue:{name}` - Pending invocations queue
- `tools:result:{eid}` - Cached results (TTL: 1 hour)
- `tools:error:{eid}` - Cached errors (TTL: 1 hour)
- `tools:idem:{key}` - Idempotency mappings (TTL: 24 hours)
- `tools:state:{eid}` - Invocation state (TTL: 1 hour)
- `tools:ratelimit:{user}:{tool}` - Rate limiting (TTL: 60 seconds)

**Idempotency Workflow**:
1. Client sends `Idempotency-Key` header
2. PostgreSQL checks for existing invocation with that key
3. If found with **same params**: Return 200 with `Idempotency-Replayed: true`
4. If found with **different params**: Return 409 Conflict
5. If not found: Create new invocation, cache mapping in Redis

**Observability**:
- Prometheus metrics: `tools_invocations_total`, `tools_invocation_duration_seconds`, `tools_queue_depth`, `tools_cache_operations_total`, `tools_idempotency_conflicts_total`
- Structured logs: `tool.invocation.start`, `tool.invocation.success`, `tool.invocation.failed`, `tool.invocation.cache_hit`, `tool.invocation.cache_miss`
- Correlation IDs in all logs and responses (`X-Request-Id` header)

Testing
-------

Run the project's test suite with pytest. The repository includes unit, integration and e2e tests under `tests/`.

```bash
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Run metadata migration and focused tests (for agent runs and Memgraph NL flows):

```bash
# Apply latest database migrations (includes run_metadata on agent runs)
alembic upgrade head

# Fast unit checks for run metadata round-trip
pytest tests/unit/test_agent_run_repository_metadata.py -q

# Memgraph NL integration (requires docker-compose stack)
pytest tests/integration/test_agent_memgraph_nl_prompts_v2.py -m memgraph_nl --nl-prompts=1 --nl-prompts-role=admin -v
```

For Ollama regressions, run the focused helper target:

```bash
make test-ollama
```

For CI the repo includes GitHub Actions workflows in `.github/workflows/`.

Notes, guardrails and security
-----------------------------

- Admin routes are opt-in. Admin readiness toggles and sensitive operations require admin authentication.
- The repo includes request-intent filtering, output guards and a PII scrubber. These features are toggleable via env vars.
- Do not commit secrets. Use `.env.tokens` (gitignored) for local testing tokens.

Contributing
------------

Contributions are welcome. Please follow the repository's `pre-commit` configuration and run tests locally before opening a PR. Key files:

- Source: `src/`
- Tests: `tests/`
- Docs: `docs/` and `api/openapi.json`

Useful make targets (see `Makefile`): `make install`, `make dev`, `make up`, `make test`.

License
-------

This project is licensed under the MIT License — see `LICENSE` for details.

Further reading
---------------

- Architecture notes: see `docs/architecture.md`.
- Deployment & configuration: see `docs/deployment.md` and `docs/configuration.md`.

<!-- markdownlint-enable MD003 -->
