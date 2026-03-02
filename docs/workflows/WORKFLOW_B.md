# Long-Running Job Workflow B - Complete Implementation

> **Status**: ✅ Fully Implemented  
> **Last Updated**: January 2026  
> **Authors**: Cineca Agentic Platform Team

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Implementation Summary](#implementation-summary)
4. [Files Modified](#files-modified)
5. [Complete Workflow B Step-by-Step](#complete-workflow-b-step-by-step)
6. [API Usage](#api-usage)
7. [Configuration](#configuration)
8. [Comparison: Workflow A vs Workflow B](#comparison-workflow-a-vs-workflow-b)

---

## Overview

Workflow B provides **asynchronous execution of agent runs** through a robust job queue system. Unlike Workflow A (synchronous HTTP request/response), Workflow B:

- Queues jobs for background processing
- Survives API server restarts
- Provides SSE streaming for real-time progress updates
- Supports job cancellation at any point
- Enables horizontal scaling of workers
- Persists full job history in PostgreSQL

### Use Cases

| Scenario | Recommended Workflow |
|----------|---------------------|
| Quick chat responses (< 30s) | Workflow A |
| Complex multi-step orchestration | Workflow B |
| Long-running NL→Cypher queries | Workflow B |
| Batch processing | Workflow B |
| Fault-tolerant execution | Workflow B |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WORKFLOW B ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐     ┌──────────────┐     ┌─────────────┐     ┌────────────┐  │
│  │  Client  │────▶│  POST /jobs  │────▶│  PostgreSQL │────▶│   Redis    │  │
│  │   (UI)   │     │  (API Layer) │     │  (Job Table)│     │  (Queue)   │  │
│  └──────────┘     └──────────────┘     └─────────────┘     └────────────┘  │
│       │                                                          │          │
│       │                                                          ▼          │
│       │           ┌──────────────────────────────────────────────────┐      │
│       │           │              JOBS WORKER PROCESS                  │      │
│       │           │  ┌────────────────────────────────────────────┐  │      │
│       │           │  │  1. Poll Redis Queue (RPOP)                │  │      │
│       │           │  │  2. Load Job from PostgreSQL               │  │      │
│       │           │  │  3. Check Cancellation Flag                │  │      │
│       │           │  │  4. Transition: queued → running           │  │      │
│       │           │  │  5. Execute Handler:                       │  │      │
│       │           │  │     ├─ demo / test / long-running          │  │      │
│       │           │  │     └─ agent.run (NEW!)                    │  │      │
│       │           │  │        ├─ Load/Create AgentRun             │  │      │
│       │           │  │        ├─ Initialize Orchestrator          │  │      │
│       │           │  │        ├─ Execute orchestrator.run()       │  │      │
│       │           │  │        ├─ Apply PII Scrubbing              │  │      │
│       │           │  │        ├─ Apply Output Guard               │  │      │
│       │           │  │        ├─ Emit Agent Metrics               │  │      │
│       │           │  │        └─ Sync AgentRun ↔ Job State        │  │      │
│       │           │  │  6. Transition: running → finished/failed  │  │      │
│       │           │  │  7. Persist Result to PostgreSQL           │  │      │
│       │           │  └────────────────────────────────────────────┘  │      │
│       │           └──────────────────────────────────────────────────┘      │
│       │                                      │                              │
│       │                                      ▼                              │
│       │           ┌──────────────────────────────────────────────────┐      │
│       │           │               SSE EVENT STREAM                    │      │
│       └──────────▶│  GET /v1/jobs/{id}/events                        │      │
│                   │  - Progress events (per orchestration step)       │      │
│                   │  - Status transitions                             │      │
│                   │  - Heartbeat (keep-alive)                         │      │
│                   │  - Final result                                   │      │
│                   └──────────────────────────────────────────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### State Machine

```
     ┌─────────┐
     │ queued  │ ◀─── POST /v1/jobs creates job
     └────┬────┘
          │ Worker picks up job
          ▼
     ┌─────────┐
     │ running │ ◀─── Worker executes handler
     └────┬────┘
          │
    ┌─────┼─────┬────────────┐
    │     │     │            │
    ▼     ▼     ▼            ▼
┌────────┐ ┌────────┐ ┌───────────┐
│finished│ │ failed │ │ cancelled │
└────────┘ └────────┘ └───────────┘
    │           │            │
    └───────────┴────────────┘
                │
         Terminal States
```

---

## Implementation Summary

### What Was Implemented

| Component | Description | File(s) |
|-----------|-------------|---------|
| **agent.run job type** | New job type for async agent execution | `src/config.py`, `docker-compose.yml` |
| **AgentRunJobPayload schema** | Pydantic model for payload validation | `src/schemas/jobs.py` |
| **JSON Schema validation** | Request payload validation for agent.run | `src/routers/jobs.py` |
| **`_execute_agent_run_job()` handler** | Main worker handler with full orchestrator integration | `src/workers/jobs_worker.py` |
| **Orchestrator integration** | LLM calls, MCP tools, NL→Cypher pipeline | `src/workers/jobs_worker.py` |
| **PII scrubbing** | Sanitize sensitive data in job results | `src/workers/jobs_worker.py` |
| **Output guard** | Validate/filter output content | `src/workers/jobs_worker.py` |
| **Agent metrics** | Prometheus metrics for monitoring | `src/workers/jobs_worker.py` |
| **Progress events** | Per-step SSE events for real-time updates | `src/workers/jobs_worker.py` |
| **AgentRun ↔ Job sync** | Bidirectional state synchronization | `src/workers/jobs_worker.py` |
| **`use_jobs` parameter** | Option to use jobs worker from agent-runs endpoint | `src/routers/agent_runs.py` |

---

## Files Modified

### 1. `src/config.py`

**Change**: Added `agent.run` to default allowed job types.

```python
# Line 408
ALLOWED_JOB_TYPES: str = Field(
    default="demo,test,long-running,agent.run",
    description="Comma-separated list of allowed job types"
)
```

### 2. `docker-compose.yml`

**Change**: Updated both `app` and `worker` services to allow `agent.run`.

```yaml
# Line 88 (app service)
ALLOWED_JOB_TYPES: "demo,test,long-running,agent.run"

# Line 149 (worker service)
ALLOWED_JOB_TYPES: "demo,test,long-running,agent.run"
```

### 3. `src/schemas/jobs.py`

**Change**: Added `AgentRunJobPayload` Pydantic model.

```python
class AgentRunJobPayload(BaseModel):
    """Payload schema for agent.run job type."""
    
    # Required fields
    prompt: str = Field(..., description="The user's prompt/goal")
    user_id: str = Field(..., description="User ID from JWT")
    tenant_id: str = Field(..., description="Tenant identifier")
    
    # Optional fields
    session_id: str | None = Field(default=None)
    run_id: str | None = Field(default=None)
    model: str | None = Field(default=None)
    manager: str | None = Field(default=None)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_steps: int = Field(default=8, ge=1, le=50)
    metadata: dict[str, Any] | None = Field(default=None)
    trace_id: str | None = Field(default=None)
    request_id: str | None = Field(default=None)
    principal: dict[str, Any] | None = Field(default=None)
```

### 4. `src/routers/jobs.py`

**Change**: Added JSON Schema for `agent.run` payload validation.

```python
# Lines 1381-1438
"agent.run": {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "minLength": 1},
        "user_id": {"type": "string", "minLength": 1},
        "tenant_id": {"type": "string", "minLength": 1},
        "session_id": {"type": "string", "format": "uuid"},
        "run_id": {"type": "string", "format": "uuid"},
        "model": {"type": "string"},
        "manager": {"type": "string"},
        "temperature": {"type": "number", "minimum": 0.0, "maximum": 2.0},
        "max_steps": {"type": "integer", "minimum": 1, "maximum": 50},
        "metadata": {"type": "object"},
        "trace_id": {"type": "string"},
        "request_id": {"type": "string"},
        "principal": {"type": "object"},
    },
    "required": ["prompt", "user_id", "tenant_id"],
    "additionalProperties": True,
}
```

### 5. `src/workers/jobs_worker.py`

**Changes**:

1. Added imports for PII scrubber, output guard, and agent metrics
2. Added `agent.run` case to `_execute_job_type()` dispatcher
3. Implemented `_execute_agent_run_job()` handler (270+ lines)
4. Implemented `_emit_progress_event()` helper

**Key handler implementation**:

```python
async def _execute_agent_run_job(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Execute agent.run job with full orchestrator integration."""
    
    # Step 1: Create or load AgentRun record
    # Step 2: Initialize Orchestrator
    # Step 3: Build orchestrator params
    # Step 4: Execute orchestrator.run() with timeout
    # Step 5: Process orchestration result
    # Step 6: Apply PII scrubbing
    # Step 7: Apply output guard validation
    # Step 8: Emit agent metrics
    # Step 9: Update AgentRun with final state (sync with Job)
    # Step 10: Build and return result
```

### 6. `src/routers/agent_runs.py`

**Change**: Added `use_jobs` query parameter for optional jobs-based execution.

```python
async def create_agent_run(
    ...
    use_jobs: bool = False,  # NEW: Use jobs worker instead of background task
) -> dict[str, Any]:
    
    if use_jobs:
        # Create agent.run job via JobsService
        # Worker will execute asynchronously
        ...
```

---

## Complete Workflow B Step-by-Step

### Phase 1: Job Submission (API Layer)

| Step | Component | Description |
|------|-----------|-------------|
| 1 | Client | User/Admin sends request via UI or API client |
| 2 | OIDC | Authentication via JWT token |
| 3 | API Gateway | `POST /v1/jobs` received |
| 4 | Security | JWT validation, RBAC check, rate limiting |
| 5 | Validation | Job type validated against `ALLOWED_JOB_TYPES` |
| 6 | Schema | Payload validated against JSON Schema for `agent.run` |
| 7 | Idempotency | Check Redis + PostgreSQL for duplicate request |
| 8 | PostgreSQL | Create job record with `status=queued` |
| 9 | Redis | Enqueue job ID via `LPUSH` to type-specific queue |
| 10 | Redis | Set job state in HASH |
| 11 | Redis | Cache idempotency mapping |
| 12 | Response | Return HTTP 202 with `Location` header |

### Phase 2: Job Processing (Worker)

| Step | Component | Description |
|------|-----------|-------------|
| 13 | Worker | Poll Redis queue via `RPOP`/`BRPOP` |
| 14 | PostgreSQL | Load job record from database |
| 15 | Redis | Check pre-execution cancellation flag |
| 16 | PostgreSQL | Transition status: `queued` → `running` |
| 17 | PostgreSQL | Append status event to `job_events` table |
| 18 | Worker | Start async heartbeat task |

### Phase 3: agent.run Execution (NEW)

| Step | Component | Description |
|------|-----------|-------------|
| 19 | PostgreSQL | Load linked AgentRun record (if `run_id` provided) |
| 20 | PostgreSQL | Create AgentRun if not exists, set `status=running` |
| 21 | Redis | Emit progress event: `agent_run_started` |
| 22 | Orchestrator | Initialize `Orchestrator.from_env()` |
| 23 | Redis | Emit progress event: `orchestrator_init` |
| 24 | Redis | Check cancellation flag |
| 25 | Orchestrator | Build params (temperature, max_steps, principal, etc.) |
| 26 | Redis | Emit progress event: `orchestration_start` |
| 27 | Orchestrator | Execute `orchestrator.run()` with timeout |
| 28 | LLM | Make LLM provider calls (with resilience/fallback) |
| 29 | MCP | Invoke MCP tools (with RBAC checks) |
| 30 | Memgraph | Execute NL→Cypher pipeline (for GRAPH mode) |
| 31 | PostgreSQL | Persist steps (per-step via orchestrator) |
| 32 | Redis | Update session state (via orchestrator) |
| 33 | Redis | Check cancellation between steps |
| 34 | Redis | Emit progress events per orchestration step |
| 35 | Result | Process orchestration result (output, todos, steps, metrics) |
| 36 | Security | Apply PII scrubbing to output and structured data |
| 37 | Security | Apply output guard validation |
| 38 | Prometheus | Emit agent-specific metrics |
| 39 | PostgreSQL | Update AgentRun: `running` → `succeeded`/`failed` |
| 40 | Redis | Emit progress event: `orchestration_complete` |

### Phase 4: Job Finalization

| Step | Component | Description |
|------|-----------|-------------|
| 41 | Worker | Checks cancellation flags periodically |
| 42 | Redis | Emits status events to event buffer |
| 43 | PostgreSQL | Appends events to `job_events` table |
| 44 | PostgreSQL | Transition to terminal status: `finished`/`failed`/`cancelled` |
| 45 | PostgreSQL | Persist result/error |
| 46 | PostgreSQL | Append terminal event to `job_events` |

### Phase 5: Client Polling (Optional)

| Step | Component | Description |
|------|-----------|-------------|
| 47 | Client | `GET /v1/jobs/{id}/events` for SSE streaming |
| 48 | SSE | Real-time progress events |
| 49 | SSE | Heartbeat keep-alive |
| 50 | SSE | Terminal event with final result |

### Phase 6: Additional Operations

| Step | Component | Description |
|------|-----------|-------------|
| 51 | API | `DELETE /v1/jobs/{id}` for cancellation |
| 52 | Redis | Atomic cancellation via Lua script |
| 53 | TTL | Job cleanup on expiration |
| 54 | Prometheus | Job store metrics emission |

---

## API Usage

### Option 1: Direct Job Creation

```bash
# Create an agent.run job
curl -X POST https://api.example.com/v1/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: unique-request-id" \
  -d '{
    "type": "agent.run",
    "payload": {
      "prompt": "What users have the most tasks in the system?",
      "user_id": "user@example.com",
      "tenant_id": "default",
      "temperature": 0.2,
      "max_steps": 8,
      "metadata": {
        "source": "dashboard",
        "priority": "high"
      }
    }
  }'

# Response (HTTP 202)
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "owner": "user@example.com",
  "type": "agent.run",
  "created_at": "2026-01-23T10:30:00Z"
}
```

### Option 2: Agent Runs with Jobs Worker

```bash
# Use jobs worker via agent-runs endpoint
curl -X POST "https://api.example.com/v1/agent-runs?use_jobs=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the capital of France?",
    "temperature": 0.2,
    "max_steps": 8
  }'

# Response includes job_id
{
  "run_id": "123e4567-e89b-12d3-a456-426614174000",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "execution_mode": "jobs_worker"
}
```

### Polling for Status

```bash
# Check job status
curl https://api.example.com/v1/jobs/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN"

# Response when complete
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "finished",
  "result": {
    "status": "completed",
    "run_id": "123e4567-e89b-12d3-a456-426614174000",
    "output": "The capital of France is Paris.",
    "todos": [...],
    "steps": [...],
    "metrics": {...},
    "elapsed_ms": 15234
  }
}
```

### SSE Event Streaming

```bash
# Stream real-time events
curl -N https://api.example.com/v1/jobs/550e8400-e29b-41d4-a716-446655440000/events \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream"

# Events received:
event: progress
data: {"stage": "agent_run_started", "run_id": "123e4567...", "message": "Agent run initialized"}

event: progress
data: {"stage": "orchestrator_init", "message": "Initializing orchestrator"}

event: progress
data: {"stage": "orchestration_start", "message": "Starting orchestration"}

event: progress
data: {"stage": "orchestration_complete", "success": true, "steps_count": 3, "todos_count": 2}

event: status
data: {"to": "finished", "from": "running", "timestamp": "2026-01-23T10:30:15Z"}
```

### Job Cancellation

```bash
# Cancel a running job
curl -X DELETE https://api.example.com/v1/jobs/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN"

# Response
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled"
}
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_POSTGRES_JOBS` | `false` | Enable PostgreSQL backend for jobs |
| `ALLOWED_JOB_TYPES` | `demo,test,long-running,agent.run` | Comma-separated allowed types |
| `JOB_WORKER_POLL_INTERVAL` | `1.0` | Queue polling interval (seconds) |
| `JOB_WORKER_HEARTBEAT_INTERVAL` | `5.0` | Heartbeat interval (seconds) |
| `JOB_TTL_DAYS` | `10` | Job retention period |
| `SSE_RING_SIZE` | `100` | Max events per job for SSE |
| `IDEMPOTENCY_TTL_HOURS` | `24` | Idempotency key expiry |

### Docker Compose

```yaml
services:
  app:
    environment:
      USE_POSTGRES_JOBS: "true"
      ALLOWED_JOB_TYPES: "demo,test,long-running,agent.run"

  worker:
    command: python -m src.workers.jobs_worker
    environment:
      USE_POSTGRES_JOBS: "true"
      ALLOWED_JOB_TYPES: "demo,test,long-running,agent.run"
      JOB_WORKER_POLL_INTERVAL: "1.0"
      JOB_WORKER_HEARTBEAT_INTERVAL: "5.0"
```

---

## Comparison: Workflow A vs Workflow B

| Aspect | Workflow A (Sync) | Workflow B (Async) |
|--------|-------------------|-------------------|
| **Endpoint** | `POST /v1/agent-runs` | `POST /v1/jobs` |
| **Execution** | FastAPI BackgroundTasks | Dedicated Worker Process |
| **Timeout** | HTTP request timeout | Configurable RUN_TIMEOUT_SECONDS |
| **Persistence** | AgentRun only | Job + AgentRun (linked) |
| **Progress** | Poll `GET /agent-runs/{id}` | SSE `GET /jobs/{id}/events` |
| **Cancellation** | Limited | Full support via Redis flags |
| **Scalability** | Single API process | Horizontal worker scaling |
| **Fault Tolerance** | Lost on restart | Survives restarts |
| **Best For** | Quick responses | Long-running tasks |

### When to Use Each

**Use Workflow A when:**
- Response expected in < 30 seconds
- Simple chat interactions
- Low latency is critical

**Use Workflow B when:**
- Complex multi-step orchestration
- Long-running NL→Cypher queries
- Need real-time progress updates
- Require job cancellation
- Processing batch requests
- High availability required

---

## Monitoring

### Prometheus Metrics

The worker emits the following metrics for `agent.run` jobs:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `agent_run_duration_seconds` | Histogram | `status`, `tenant_id` | Total execution time |
| `agent_run_success_total` | Counter | `tenant_id` | Successful runs |
| `agent_run_failures_total` | Counter | `failure_type`, `tenant_id` | Failed runs |
| `agent_todos_count` | Histogram | `tenant_id` | TODOs generated per run |

### Logging

All operations are logged with structured fields:

```json
{
  "event": "agent_run.job_created",
  "job_id": "550e8400-...",
  "run_id": "123e4567-...",
  "user_id": "user@example.com",
  "tenant_id": "default",
  "execution_mode": "jobs_worker"
}
```

---

## Troubleshooting

### Common Issues

**1. Job stuck in `queued` status**
- Check worker is running: `docker-compose logs worker`
- Verify Redis connectivity
- Check `ALLOWED_JOB_TYPES` includes `agent.run`

**2. Job fails immediately**
- Check payload validation errors in API logs
- Verify `prompt`, `user_id`, `tenant_id` are provided

**3. Orchestration timeout**
- Increase `RUN_TIMEOUT_SECONDS` in orchestrator config
- Check LLM provider connectivity
- Review orchestrator logs for specific step failures

**4. SSE not receiving events**
- Verify job ID is correct
- Check `SSE_RING_SIZE` hasn't been exceeded
- Ensure proper `Accept: text/event-stream` header

---

## Future Enhancements

- [ ] Job priority queues (high/normal/low)
- [ ] Job scheduling (cron-like)
- [ ] Job dependencies (DAG execution)
- [ ] Multi-tenant worker isolation
- [ ] Job result caching
- [ ] Retry policies per job type

---

## References

- [Jobs API Documentation](../api/JOBS_API.md)
- [Agent Runs API Documentation](../api/AGENT_RUNS_API.md)
- [Orchestrator Documentation](../orchestrator/README.md)
- [Worker Operations Guide](../operations/runbooks/worker-guide.md)


# Workflow B Quick Reference

> Quick reference for the Long-Running Job Workflow (async agent execution)

## TL;DR

```bash
# Create agent.run job
POST /v1/jobs
{
  "type": "agent.run",
  "payload": {
    "prompt": "Your question here",
    "user_id": "user@example.com",
    "tenant_id": "default"
  }
}

# Poll for result
GET /v1/jobs/{job_id}

# Stream events
GET /v1/jobs/{job_id}/events (SSE)

# Cancel job
DELETE /v1/jobs/{job_id}
```

## State Machine

```
queued → running → finished | failed | cancelled
```

## Required Payload Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | ✅ | User's question/goal |
| `user_id` | string | ✅ | User identifier |
| `tenant_id` | string | ✅ | Tenant identifier |

## Optional Payload Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `session_id` | uuid | null | Session for context |
| `run_id` | uuid | auto | Pre-created AgentRun ID |
| `model` | string | DB default | LLM model override |
| `manager` | string | null | Manager LLM client |
| `temperature` | float | 0.2 | Sampling temperature |
| `max_steps` | int | 8 | Max orchestration steps |
| `metadata` | object | {} | Custom metadata |
| `trace_id` | string | null | Distributed trace ID |
| `principal` | object | null | Security context |

## Progress Events

Events emitted during execution:

1. `agent_run_started` - AgentRun initialized
2. `orchestrator_init` - Orchestrator ready
3. `orchestration_start` - Execution began
4. `orchestration_complete` - Finished (success/failure)
5. `completed` - Final status with result

## Environment Variables

```bash
USE_POSTGRES_JOBS=true              # Enable jobs backend
ALLOWED_JOB_TYPES=demo,test,long-running,agent.run
JOB_WORKER_POLL_INTERVAL=1.0        # Queue poll interval
JOB_WORKER_HEARTBEAT_INTERVAL=5.0   # Heartbeat interval
```

## Alternative: Use Jobs from Agent Runs

```bash
POST /v1/agent-runs?use_jobs=true
{
  "prompt": "Your question"
}
```

## Files

| File | Purpose |
|------|---------|
| `src/workers/jobs_worker.py` | Worker with agent.run handler |
| `src/routers/jobs.py` | Jobs API endpoints |
| `src/schemas/jobs.py` | AgentRunJobPayload schema |
| `src/config.py` | ALLOWED_JOB_TYPES config |
## Overview

Workflow B provides asynchronous execution of agent runs through a robust job queue system, enabling:

- Background processing that survives API restarts
- Real-time progress via SSE streaming
- Job cancellation at any point
- Horizontal scaling of workers
- Full job history in PostgreSQL

## Quick Start

```bash
# 1. Ensure worker is running
docker-compose up worker

# 2. Create a job
curl -X POST http://localhost:8000/v1/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "agent.run",
    "payload": {
      "prompt": "What is AI?",
      "user_id": "user@example.com",
      "tenant_id": "default"
    }
  }'

# 3. Stream events
curl -N http://localhost:8000/v1/jobs/{job_id}/events \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream"
```

## Related Documentation

- [Jobs API Reference](../api/JOBS_API.md)
- [Worker Operations](../operations/runbooks/worker-guide.md)
- [Orchestrator](../orchestrator/README.md)
