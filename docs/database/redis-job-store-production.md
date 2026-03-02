# Redis Job Store: Production Readiness Features

## Overview

This document tracks the production-ready enhancements added to the Redis job store implementation after successful migration from in-memory to Redis backend.

## Completed Features

### ✅ 1. CI Matrix Testing

**File**: `.github/workflows/job-store-matrix.yml`

**Purpose**: Automated dual-backend testing in CI to prevent regressions.

**Implementation**:
- Matrix strategy testing both `memory` and `redis` backends
- Redis service container (redis:7-alpine) with healthcheck
- Separate test runs with backend isolation via `JOB_STORE_BACKEND` env var
- Coverage reporting for Redis mode
- Backend parity verification job
- JUnit XML artifacts for test results

**Usage**:
```bash
# Workflow runs automatically on push/PR
# View results in GitHub Actions tab
```

---

### ✅ 2. Prometheus Metrics & Alerts

#### Metrics Module

**File**: `src/jobs/metrics.py`

**Metrics Exposed**:

**Counters**:
- `job_create_total{backend,status}` - Job creation attempts
- `job_get_total{backend,status}` - Job retrievals
- `job_list_total{backend,scope}` - List operations
- `job_cancel_total{backend,first_time}` - Cancellation requests
- `sse_resume_hits_total` - SSE resume from Last-Event-ID
- `sse_gap_events_total` - SSE ring buffer evictions
- `idempotency_checks_total` - Idempotency key checks
- `index_orphans_cleaned_total` - Index cleanup operations

**Histograms** (latency tracking):
- `job_create_duration_seconds` (buckets: 0.001 to 1.0)
- `job_get_duration_seconds`
- `job_list_duration_seconds`
- `job_cancel_duration_seconds`

**Gauges**:
- `sse_connections_active{backend}` - Active SSE connections

**Info**:
- `job_backend_info` - Current backend and Redis URL (sanitized)

**Decorators & Helpers**:
```python
from src.jobs.metrics import (
    track_job_create,
    track_job_get,
    track_job_list,
    track_sse_connection,
    record_sse_resume,
    record_sse_gap,
)

@track_job_create(backend="redis")
async def create_job(...):
    ...

with track_sse_connection(backend="redis"):
    # SSE streaming logic
    ...
```

#### Alert Rules

**File**: `ops/prometheus/alerts.yml`

**New Alert Group**: `job_store.rules`

**Alerts**:
1. **JobStoreHighCreateLatency** - P95 > 2s for 10min (warning)
2. **JobStoreHighGetLatency** - P95 > 500ms for 10min (warning)
3. **JobStoreHighFailureRate** - >5% failed creates for 10min (critical)
4. **RedisConnectionErrors** - >0.1/sec for 5min (critical)
5. **SSETooManyGaps** - >1/min avg for 15min (warning, ring buffer eviction)
6. **SSEHighConnectionCount** - >100 active for 10min (info)
7. **JobStoreBackendMismatch** - Backend config change detected (info)
8. **IndexOrphansAccumulating** - >10/hour cleanup rate (warning)

**Runbooks**: All alerts link to `docs/runbooks/redis-job-store.md`

---

### ✅ 3. Atomic Job Cancellation (Lua CAS)

**File**: `src/jobs/lua_scripts.py`

**Purpose**: Eliminate race conditions in concurrent cancellation scenarios using Redis Lua scripts with Compare-And-Set semantics.

#### Lua Scripts

1. **`CANCEL_JOB_SCRIPT`**: Atomic cancellation with CAS
   - Checks job exists
   - Verifies status is `queued` or `running`
   - Updates to `cancelled` atomically
   - Returns transition result

2. **`UPDATE_STATUS_SCRIPT`**: Atomic status update with index management
   - Validates state transition
   - Updates HASH fields and ZSET indexes atomically
   - Handles TTL for terminal states

3. **`CLEANUP_ORPHANS_SCRIPT`**: Batch orphan removal from indexes
   - Scans ZSET members
   - Checks if corresponding job HASH exists
   - Removes orphaned members

4. **`DELETE_JOB_SCRIPT`**: Atomic job deletion with all related keys

5. **`IDEMPOTENCY_CAS_SCRIPT`**: Atomic idempotency check-and-set

#### Integration

**File**: `src/jobs/redis_store.py`

**New Methods**:
```python
class RedisJobStore(JobStore):
    async def cancel_job_atomic(self, job_id: str) -> bool:
        """
        Atomically cancel job using Lua CAS.
        
        Returns:
            True if transitioned from queued/running to cancelled
            False if already terminal or not found
        """
        ...
    
    async def cleanup_orphaned_index_members(
        self,
        index_key: str,
        batch_size: int = 100,
    ) -> int:
        """
        Clean orphaned ZSET members (job IDs without HASHes).
        
        Returns:
            Number of orphaned members removed
        """
        ...
```

**Endpoint Integration**:

**File**: `src/routers/jobs.py`

```python
# Atomic cancellation for Redis backend
if settings.JOB_STORE_BACKEND == "redis":
    first_cancel = await job_store_impl.cancel_job_atomic(job_id)
else:
    # Fallback for memory backend
    ...
```

**Benefits**:
- ✅ No race conditions in concurrent cancellation
- ✅ Single atomic operation (no read-check-update pattern)
- ✅ Graceful handling of already-terminal jobs
- ✅ Backward-compatible with memory backend

---

### ✅ 4. Index Hygiene (Background Cleanup)

**File**: `src/jobs/redis_maintenance.py`

**Purpose**: Periodic background task to remove orphaned ZSET index members (jobs whose HASHes expired via TTL).

#### RedisMaintenanceScheduler

**Configuration** (`src/background.py`):
```python
@dataclass
class BackgroundConfig:
    redis_cleanup_enabled: bool = True
    redis_cleanup_interval_seconds: int = 3600  # 1 hour
    redis_cleanup_batch_size: int = 500
```

**Cleanup Strategy**:
1. **Global Index**: `jobs:all`
2. **Status Indexes**: `jobs:status:{queued,running,finished,failed,cancelled}`
3. **Owner Indexes**: `jobs:owner:*` (SCAN cursor-based)

**Metrics Integration**:
```python
from src.jobs.metrics import record_index_cleanup

# After cleanup
record_index_cleanup(total_removed)
```

**Integration**: Automatically starts with app if `JOB_STORE_BACKEND=redis`

**Startup**:
```python
# src/background.py (in BackgroundManager._register_jobs)
if settings.JOB_STORE_BACKEND == "redis":
    self.scheduler.add_job(
        self._job_redis_cleanup,
        IntervalTrigger(seconds=3600),  # 1 hour
        id="background.redis_cleanup",
        max_instances=1,
    )
```

**Monitoring**:
- Logs: `background.redis_cleanup.completed`
- Metric: `index_orphans_cleaned_total`
- Alert: `IndexOrphansAccumulating` (if >10/hour)

---

## Testing

### Atomic Operations Tests

**File**: `tests/jobs/test_atomic_operations.py`

**Test Coverage**:
1. ✅ Atomic cancellation success (queued → cancelled)
2. ✅ Atomic cancellation already terminal (no-op)
3. ✅ Atomic cancellation not found
4. ✅ Concurrent cancellation safety (10 parallel attempts)
5. ✅ Orphan cleanup basic (removes expired job index entries)
6. ✅ Orphan cleanup batch processing
7. ✅ Orphan cleanup no orphans (returns 0)

**Run Tests**:
```bash
# Memory backend (default)
pytest tests/test_jobs.py::test_cancel_job_first_time -v

# Redis backend (requires Redis running)
JOB_STORE_BACKEND=redis pytest tests/jobs/test_atomic_operations.py -v -k "cancel_job_atomic"
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JOB_STORE_BACKEND` | `memory` | Backend type: `memory` or `redis` |
| `BACKGROUND_REDIS_CLEANUP_ENABLED` | `True` | Enable orphan cleanup |
| `BACKGROUND_REDIS_CLEANUP_INTERVAL` | `3600` | Cleanup interval (seconds) |
| `BACKGROUND_REDIS_CLEANUP_BATCH_SIZE` | `500` | Max members per index scan |

---

## Operational Runbooks

### Scenario: High Job Create Latency

**Alert**: `JobStoreHighCreateLatency` (P95 > 2s)

**Investigation**:
1. Check Redis latency: `redis-cli --latency`
2. Check Redis memory: `redis-cli info memory`
3. Review metrics: `job_create_duration_seconds{quantile="0.95"}`

**Mitigation**:
- Scale Redis vertically (more memory/CPU)
- Enable Redis persistence tuning (AOF fsync=everysec)
- Check network latency to Redis

### Scenario: Index Orphans Accumulating

**Alert**: `IndexOrphansAccumulating` (>10/hour cleanup rate)

**Investigation**:
1. Check TTL settings: `JOB_TTL_DAYS` (default 7 days)
2. Review orphan cleanup logs: `background.redis_cleanup.completed`
3. Verify index consistency: Manual ZSET scan

**Mitigation**:
- Increase cleanup batch size: `BACKGROUND_REDIS_CLEANUP_BATCH_SIZE=1000`
- Decrease cleanup interval: `BACKGROUND_REDIS_CLEANUP_INTERVAL=1800` (30min)
- Investigate premature TTL expiry (check Redis eviction policy)

### Scenario: SSE Ring Buffer Gaps

**Alert**: `SSETooManyGaps` (>1/min avg gaps)

**Investigation**:
1. Check SSE ring size: `SSE_RING_SIZE` (default 100)
2. Review gap metric: `sse_gap_events_total`
3. Check event generation rate vs consumption rate

**Mitigation**:
- Increase ring size: `SSE_RING_SIZE=500`
- Reduce event retention: Lower `SSE_EVENT_RETENTION_SECONDS`
- Optimize client resume logic (use Last-Event-ID)

---

## Remaining TODOs

### 5. Load & Soak Tests (Pending)

**Objective**: Stress test Redis backend with high-rate job creation and concurrent SSE clients.

**Plan**:
- Create `tests/performance/load_test_redis.py`
- Tools: `locust` or `pytest-benchmark`
- Scenarios:
  - Burst job creation (1000 jobs/sec)
  - Concurrent SSE clients (100 connections)
  - Sustained load (24h soak test)
- Metrics baseline: P50/P95/P99 latencies

### 6. Ops Guardrails (Pending)

**Objective**: Production hardening with rate limits, backpressure, and persistence tuning.

**Components**:
- **Rate Limiting**: Middleware for job creation (e.g., 100 req/min per user)
- **Circuit Breaker**: Redis timeout handling with fallback
- **Redis Persistence**: Configure AOF/RDB for durability
  ```
  # redis.conf
  appendonly yes
  appendfsync everysec
  save 900 1
  ```
- **Connection Pooling**: Tune `redis-py` pool size
  ```python
  REDIS_MAX_CONNECTIONS = 50
  REDIS_SOCKET_KEEPALIVE = True
  ```

### 7. Documentation (Pending)

**Objective**: Developer quick-start and troubleshooting guides.

**Files to Update**:
- `README.md`: Add "Switching Backends" section
- `docs/redis-job-store.md`: Full runbook
- `docs/troubleshooting.md`: Common Redis issues

**Content**:
- How to switch from memory to Redis
- Redis connection string format
- Troubleshooting: connection errors, latency, OOM
- Monitoring dashboard screenshots (Grafana)

---

## Summary

### What We've Built

1. **CI/CD**: Automated dual-backend testing with matrix strategy
2. **Observability**: 13 Prometheus metrics + 8 alert rules
3. **Atomicity**: Lua-based CAS for race-free cancellation
4. **Maintenance**: Background orphan cleanup (1-hour intervals)

### Production-Ready Checklist

- [x] CI matrix for backend parity
- [x] Comprehensive metrics instrumentation
- [x] Prometheus alerts with runbook links
- [x] Atomic cancellation (Lua CAS)
- [x] Index hygiene automation
- [ ] Load & soak tests
- [ ] Rate limiting & backpressure
- [ ] Redis persistence tuning
- [ ] Documentation updates

### Next Steps

**Immediate** (Ready for Production):
- Deploy CI workflow (`.github/workflows/job-store-matrix.yml`)
- Configure Prometheus to scrape `/metrics`
- Import alert rules (`ops/prometheus/alerts.yml`)
- Enable background cleanup (default: on)

**Soon** (Pre-Production):
- Run load tests to establish baselines
- Implement rate limiting middleware
- Configure Redis persistence (AOF)
- Create runbook and troubleshooting docs

---

**Last Updated**: 2025-01-XX  
**Authors**: Arman Feili, GitHub Copilot
