# PostgreSQL Jobs Worker Guide

Complete guide for deploying and managing the PostgreSQL-backed jobs worker service.

## Overview

The jobs worker is a background service that processes asynchronous jobs from Redis queues and persists results to PostgreSQL. It provides:

- ✅ **Persistent Jobs**: All job data stored in PostgreSQL (survives restarts)
- ✅ **Queue-Based Processing**: Uses Redis for fast job queuing
- ✅ **Status Lifecycle**: Tracks jobs through queued → running → finished/failed/cancelled
- ✅ **Event Logging**: All transitions logged for Server-Sent Events (SSE) streaming
- ✅ **Heartbeat Monitoring**: Worker updates job timestamps to indicate liveness
- ✅ **Graceful Shutdown**: Handles SIGTERM/SIGINT for clean shutdown
- ✅ **Multiple Job Types**: Supports demo, test, and long-running job types

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌────────────────┐
│             │         │              │         │                │
│  API Client │────────▶│  API Server  │────────▶│   PostgreSQL   │
│             │         │              │         │                │
└─────────────┘         └──────┬───────┘         └────────┬───────┘
                               │                          │
                               │ Push job to queue        │ Job data
                               ▼                          │
                        ┌──────────────┐                  │
                        │              │                  │
                        │    Redis     │                  │
                        │              │                  │
                        └──────┬───────┘                  │
                               │                          │
                               │ Poll queues              │
                               ▼                          │
                        ┌──────────────┐                  │
                        │              │                  │
                        │    Worker    │─────────────────▶│
                        │              │  Update status   │
                        └──────────────┘                  │
                                                          │
                                                          ▼
                                                   ┌──────────────┐
                                                   │              │
                                                   │  SSE Stream  │
                                                   │              │
                                                   └──────────────┘
```

## Quick Start

### 1. Enable PostgreSQL Jobs

Set in your environment (`.env` or `docker-compose.yml`):

```bash
USE_POSTGRES_JOBS=true
```

### 2. Start Worker with Docker Compose

The worker is already configured in `docker-compose.yml`:

```bash
# Start all services including worker
docker compose up -d

# Start only worker
docker compose up -d worker

# Check worker logs
docker compose logs -f worker
```

### 3. Create a Job

```bash
curl -X POST http://localhost:8000/v1/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "test", "payload": {"message": "Hello Worker!"}}'
```

### 4. Check Job Status

```bash
# Query PostgreSQL
docker compose exec postgres psql -U cineca_user -d cineca_platform \
  -c "SELECT id, type, status, result_json FROM jobs ORDER BY created_at DESC LIMIT 5;"

# Via API
curl http://localhost:8000/v1/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN"
```

## Configuration

### Environment Variables

See [environment-variables.md](./environment-variables.md) for complete reference.

**Required:**
- `USE_POSTGRES_JOBS=true` - Enable PostgreSQL backend
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` - PostgreSQL connection
- `REDIS_URL` - Redis connection string

**Optional:**
- `JOB_WORKER_POLL_INTERVAL=1.0` - Queue polling interval (seconds)
- `JOB_WORKER_HEARTBEAT_INTERVAL=5.0` - Heartbeat update interval (seconds)
- `ALLOWED_JOB_TYPES=demo,test,long-running` - Allowed job types

### Docker Compose Configuration

```yaml
worker:
  build:
    context: .
    dockerfile: Dockerfile
    target: app
  container_name: jobs-worker
  command: ["python", "-u", "-m", "src.workers.jobs_worker"]
  environment:
    USE_POSTGRES_JOBS: "true"
    JOB_WORKER_POLL_INTERVAL: "1.0"
    JOB_WORKER_HEARTBEAT_INTERVAL: "5.0"
    ALLOWED_JOB_TYPES: "demo,test,long-running"
    # PostgreSQL connection
    DB_HOST: "postgres"
    DB_PORT: "5432"
    DB_NAME: "cineca_platform"
    DB_USER: "cineca_user"
    DB_PASSWORD: "change_me_now"
    # Redis connection
    REDIS_URL: "redis://redis:6379/0"
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  restart: unless-stopped
```

## Job Types

### Demo Job

Simulates work by sleeping for a specified duration.

**Payload:**
```json
{
  "type": "demo",
  "payload": {
    "duration_ms": 3000
  }
}
```

**Result:**
```json
{
  "status": "completed",
  "message": "Demo job completed successfully",
  "actual_duration_ms": 3015,
  "requested_duration_ms": 3000
}
```

### Test Job

Completes instantly and echoes the input payload.

**Payload:**
```json
{
  "type": "test",
  "payload": {
    "message": "Hello Worker!"
  }
}
```

**Result:**
```json
{
  "input": {"message": "Hello Worker!"},
  "status": "completed",
  "message": "Test job completed",
  "timestamp": "2025-10-12T11:21:24.358621"
}
```

### Long-Running Job

Multi-step processing job (future use).

**Payload:**
```json
{
  "type": "long-running",
  "payload": {
    "steps": 10
  }
}
```

## Monitoring

### Health Checks

#### PostgreSQL Health
```bash
curl http://localhost:8000/v1/health/db
```

**Response:**
```json
{
  "ok": true,
  "database": "postgresql"
}
```

#### Redis Health (with Queue Stats)
```bash
curl http://localhost:8000/v1/health/redis
```

**Response:**
```json
{
  "ok": true,
  "url": "redis://redis:6379/0",
  "queues": {
    "demo": 0,
    "test": 2,
    "long-running": 1
  }
}
```

### Worker Logs

```bash
# Follow worker logs
docker compose logs -f worker

# Show last 100 lines
docker compose logs --tail=100 worker

# Show logs with timestamps
docker compose logs -f -t worker
```

### Job Status Query

```sql
-- Check recent jobs
SELECT 
  id, 
  type, 
  status, 
  created_at, 
  started_at, 
  completed_at,
  queue_latency_ms,
  exec_latency_ms
FROM jobs 
ORDER BY created_at DESC 
LIMIT 10;

-- Check job events
SELECT 
  seq_id,
  event_type,
  event_json,
  created_at
FROM job_events 
WHERE job_id = '<job-uuid>'
ORDER BY seq_id;

-- Queue statistics
SELECT 
  status, 
  COUNT(*) as count 
FROM jobs 
GROUP BY status;
```

### Metrics

Job metrics are exposed via Prometheus endpoint:

```bash
curl http://localhost:8000/metrics | grep job_
```

## Operations

### Starting the Worker

```bash
# With Docker Compose
docker compose up -d worker

# Standalone (requires environment variables)
export USE_POSTGRES_JOBS=true
python -m src.workers.jobs_worker
```

### Stopping the Worker

```bash
# Graceful shutdown (waits for current job)
docker compose stop worker

# Force stop
docker compose kill worker
```

### Restarting the Worker

```bash
docker compose restart worker
```

### Scaling Workers

To run multiple worker instances:

```yaml
# docker-compose.yml
worker:
  # ... existing configuration ...
  deploy:
    replicas: 3  # Run 3 worker instances
```

Or manually:

```bash
docker compose up -d --scale worker=3
```

**Note:** Multiple workers can safely process jobs from the same queues (jobs are popped atomically).

### Viewing Worker Status

```bash
# Check if worker is running
docker compose ps worker

# Check worker resource usage
docker stats jobs-worker

# Check worker process
docker compose exec worker ps aux
```

## Troubleshooting

### Worker Not Starting

**Symptoms:** Worker container exits immediately

**Checks:**
1. Verify `USE_POSTGRES_JOBS=true`
2. Check PostgreSQL connectivity: `docker compose logs postgres`
3. Check Redis connectivity: `docker compose logs redis`
4. Review worker logs: `docker compose logs worker`

**Common Causes:**
- Missing environment variables
- PostgreSQL not ready (increase `depends_on` wait time)
- Redis not reachable
- Database migrations not applied

### Jobs Not Being Processed

**Symptoms:** Jobs stuck in "queued" status

**Checks:**
1. Verify worker is running: `docker compose ps worker`
2. Check worker logs for errors: `docker compose logs worker`
3. Verify job type is allowed: Check `ALLOWED_JOB_TYPES`
4. Check Redis queue length: `curl http://localhost:8000/v1/health/redis`

**Common Causes:**
- Worker not running
- Job type not in `ALLOWED_JOB_TYPES`
- Worker crashed (check logs)
- Redis connection lost

### Jobs Failing

**Symptoms:** Jobs transition to "failed" status

**Checks:**
1. Check job error message: `SELECT id, error_json FROM jobs WHERE status = 'failed';`
2. Review worker logs: `docker compose logs worker | grep ERROR`
3. Check job payload format

**Common Causes:**
- Invalid payload format
- Missing required payload fields
- Worker code exceptions (check logs)

### High Memory Usage

**Symptoms:** Worker container consuming excessive memory

**Checks:**
1. Check job payload sizes
2. Review long-running jobs
3. Check for memory leaks (restart worker)

**Solutions:**
- Limit payload sizes
- Increase worker memory limit in docker-compose.yml
- Scale horizontally (more workers, smaller memory each)

### Slow Job Processing

**Symptoms:** Jobs taking longer than expected

**Checks:**
1. Check database query performance
2. Review `JOB_WORKER_POLL_INTERVAL` (might be too high)
3. Check system resources: `docker stats`

**Solutions:**
- Increase `DB_POOL_SIZE` for more connections
- Optimize job execution code
- Scale workers horizontally
- Reduce `JOB_WORKER_POLL_INTERVAL` for faster pickup

## Best Practices

### Production Deployment

1. **Use SSL/TLS**: Set `DB_SSLMODE=require` for PostgreSQL
2. **Strong Passwords**: Change `DB_PASSWORD` from default
3. **Resource Limits**: Set CPU/memory limits in docker-compose.yml
4. **Health Checks**: Monitor `/health/db` and `/health/redis`
5. **Log Aggregation**: Send logs to centralized system (ELK, Splunk)
6. **Metrics**: Monitor job queue length, processing time
7. **Alerting**: Alert on worker failures, high queue depth

### Development Workflow

1. **Local Development**:
   ```bash
   docker compose up -d postgres redis
   export USE_POSTGRES_JOBS=true
   python -m src.workers.jobs_worker
   ```

2. **Testing**:
   ```bash
   # Run worker in foreground for debugging
   docker compose up worker  # No -d flag
   ```

3. **Debugging**:
   ```bash
   # Attach to running worker
   docker compose exec worker bash
   
   # Check worker process
   ps aux | grep worker
   ```

### Maintenance

1. **Database Cleanup**: Periodically archive old completed jobs
2. **Log Rotation**: Configure log rotation for worker logs
3. **Version Updates**: Test worker code changes in staging first
4. **Backup**: Regular PostgreSQL backups include job data

## Advanced Topics

### Custom Job Types

To add new job types:

1. Update `ALLOWED_JOB_TYPES` environment variable
2. Add handler in `src/workers/jobs_worker.py`:
   ```python
   async def _execute_custom_job(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
       # Your custom job logic
       return {"status": "completed", "result": "..."}
   ```
3. Register in `_execute_job_type()` method

### Job Priorities

Jobs support priority (higher = more urgent). Future enhancement: implement priority queues.

### Dead Letter Queue

Future enhancement: Jobs that fail repeatedly move to dead letter queue for manual review.

### Scheduled Jobs

Future enhancement: Cron-like job scheduling using PostgreSQL triggers or separate scheduler service.

## References

- [Environment Variables](./environment-variables.md)
- [Configuration](./configuration.md)
- [Deployment](./deployment.md)
- [Task 11: Worker Implementation](../TASK_11_WORKER_COMPLETE.md)

---

**Last Updated**: 2025-10-12  
**Version**: 1.0
