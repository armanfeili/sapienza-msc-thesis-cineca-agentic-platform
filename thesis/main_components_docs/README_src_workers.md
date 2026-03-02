# Workers Package Documentation

## Overview

The `src/workers/` package provides background job processing capabilities for the Cineca Agentic Platform. This package implements asynchronous job execution with PostgreSQL persistence and Redis-based queuing, enabling reliable background processing of long-running tasks.

## Architecture

### Design Principles

- **Reliability**: Job state persistence with PostgreSQL
- **Scalability**: Redis-based queuing for high throughput
- **Observability**: Comprehensive logging and event tracking
- **Resilience**: Graceful error handling and recovery
- **Cancellation**: Support for job cancellation during execution

### Package Structure

```
src/workers/
├── __init__.py          # Package initialization
└── jobs_worker.py       # PostgreSQL-backed job processor
```

### Job Lifecycle

```
Queue → Running → Completed/Failed/Cancelled
   ↓         ↓            ↓
Redis    PostgreSQL    PostgreSQL
queues   persistence   results
```

## Core Components

### 1. Jobs Worker (`jobs_worker.py`)

**Purpose**: Background worker that processes jobs from Redis queues with full PostgreSQL persistence and lifecycle management.

**Key Features**:
- Multi-tenant job processing
- Atomic queue operations
- Heartbeat monitoring
- Graceful shutdown handling
- Event logging for SSE streaming
- Job cancellation support

**Architecture Overview**:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Redis Queue   │───▶│  Jobs Worker   │───▶│ PostgreSQL DB   │
│                 │    │                 │    │                 │
│ • job_id (UUID) │    │ • Poll queues   │    │ • Job metadata │
│ • tenant-aware  │    │ • Execute logic │    │ • Status trans │
│ • FIFO ordering │    │ • Heartbeat     │    │ • Event log    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

#### Worker Configuration

```python
class JobsWorker:
    def __init__(
        self,
        poll_interval: float = 1.0,      # Queue polling frequency
        heartbeat_interval: float = 5.0, # Status update frequency
        max_iterations: int | None = None # Testing limit
    ):
        # Configuration and signal handlers
```

#### Job Processing Flow

```python
async def _process_next_job(self) -> bool:
    """
    1. Poll Redis queues for available jobs
    2. Pop job atomically from queue
    3. Load job from PostgreSQL
    4. Execute with lifecycle management
    5. Handle errors and cancellation
    """
```

## Job Types

### Supported Job Types

The worker supports multiple job types configured via `ALLOWED_JOB_TYPES` setting:

```bash
ALLOWED_JOB_TYPES=demo,test,long-running
```

#### 1. Demo Jobs

**Purpose**: Simple demonstration jobs with configurable sleep duration.

**Characteristics**:
- Fast execution (seconds to minutes)
- Configurable duration via payload
- Cancellation support during sleep
- Progress logging

**Payload Schema**:
```json
{
  "duration_ms": 5000
}
```

**Execution Example**:
```python
# Job execution
start_time = time.time()
for _ in range(sleep_chunks):
    if await check_cancel_flag(job_id):
        raise CancelledError()
    await asyncio.sleep(0.5)

result = {
    "status": "completed",
    "requested_duration_ms": 5000,
    "actual_duration_ms": 5200,
    "message": "Demo job completed successfully"
}
```

#### 2. Test Jobs

**Purpose**: Instant-completion jobs for testing worker infrastructure.

**Characteristics**:
- Sub-second execution
- Payload echo functionality
- Timestamp recording
- No external dependencies

**Payload Schema**:
```json
{
  "test_data": "any_value",
  "metadata": {"key": "value"}
}
```

**Execution Example**:
```python
result = {
    "status": "completed",
    "input": payload,
    "timestamp": "2024-01-01T12:00:00Z",
    "message": "Test job completed"
}
```

#### 3. Long-Running Jobs

**Purpose**: Extended duration jobs with progress tracking and cancellation.

**Characteristics**:
- 30+ seconds execution time
- Step-by-step progress reporting
- Configurable step count
- Regular cancellation checks

**Payload Schema**:
```json
{
  "steps": 10,
  "step_duration": 3.0
}
```

**Execution Example**:
```python
steps = payload.get("steps", 10)
for step in range(1, steps + 1):
    if await check_cancel_flag(job_id):
        raise CancelledError()
    
    logger.info(f"Step {step}/{steps}")
    await asyncio.sleep(3.0)

result = {
    "status": "completed",
    "steps_completed": 10,
    "total_duration_ms": 30000,
    "message": "Completed 10 steps"
}
```

## Job Lifecycle Management

### Status Transitions

Jobs follow a strict state machine with validated transitions:

```
queued → running → finished
    ↓       ↓
 cancelled  failed
```

**State Definitions**:
- **queued**: Job created, waiting for worker
- **running**: Job actively executing
- **finished**: Job completed successfully
- **failed**: Job failed with error
- **cancelled**: Job cancelled by user/system

### Event Logging

All status transitions and significant events are logged:

```python
jobs_service.append_event(
    job_uuid,
    event_type="status",
    event_data={
        "to": "running",
        "from": "queued",
        "timestamp": "2024-01-01T12:00:00Z"
    }
)
```

### Cancellation Mechanism

Jobs can be cancelled at any point using Redis flags:

```python
# Check cancellation during execution
if await asyncio.to_thread(jobs_cache.check_cancel_flag, job_id):
    raise asyncio.CancelledError("Job cancelled")

# Mark as cancelled in database
await self._mark_cancelled(job_uuid, jobs_service)
```

## Heartbeat System

### Purpose

The heartbeat system prevents jobs from appearing stuck when workers crash:

```python
async def _heartbeat_loop(self, job_uuid: UUID, jobs_service: JobsService):
    """Update job timestamp every heartbeat_interval seconds."""
    while True:
        await asyncio.sleep(self.heartbeat_interval)
        jobs_service.repo.touch_job(job_uuid)  # Update updated_at
```

### Configuration

```python
# Environment variables
JOB_WORKER_HEARTBEAT_INTERVAL=5.0  # seconds

# Worker initialization
worker = JobsWorker(heartbeat_interval=5.0)
```

### Monitoring

Stale jobs can be detected by checking `updated_at` timestamp:

```sql
-- Find potentially stuck jobs
SELECT * FROM jobs
WHERE status = 'running'
  AND updated_at < NOW() - INTERVAL '30 seconds';
```

## Queue Management

### Redis Queue Structure

Jobs are queued by type with tenant isolation:

```
Redis Keys:
- job_queue:{job_type}  # FIFO queue of job IDs
- job_cancel:{job_id}   # Cancellation flags
```

### Atomic Operations

Queue operations are atomic to prevent race conditions:

```python
# Atomic pop from queue
job_id = await asyncio.to_thread(
    jobs_cache.queue_pop_job, job_type, timeout=0
)
```

### Round-Robin Processing

Worker polls all allowed job types in round-robin fashion:

```python
allowed_types = ["demo", "test", "long-running"]
for job_type in allowed_types:
    job_id = await pop_from_queue(job_type)
    if job_id:
        await process_job(job_id)
        break  # Process one job per cycle
```

## Error Handling

### Job Execution Errors

Failed jobs are marked with error details:

```python
try:
    result = await execute_job_logic(job)
except Exception as e:
    # Mark as failed
    jobs_service.repo.update_job_error(job_uuid, str(e))
    jobs_service.transition_status(job_uuid, "running", "failed")
    
    # Log error event
    jobs_service.append_event(job_uuid, "status", {
        "to": "failed",
        "error": str(e),
        "timestamp": datetime.utcnow().isoformat()
    })
```

### Worker-Level Errors

Worker continues processing despite individual job failures:

```python
while self.running:
    try:
        processed = await self._process_next_job()
        if not processed:
            await asyncio.sleep(self.poll_interval)
    except Exception as e:
        logger.error(f"Worker loop error: {e}")
        await asyncio.sleep(self.poll_interval)  # Continue polling
```

### Graceful Shutdown

Worker handles SIGTERM/SIGINT for clean shutdown:

```python
def _signal_handler(self, signum, frame):
    logger.info(f"Received {signum}, initiating shutdown")
    self.running = False

# Signal registration
signal.signal(signal.SIGTERM, self._signal_handler)
signal.signal(signal.SIGINT, self._signal_handler)
```

## Configuration

### Environment Variables

```bash
# Worker settings
JOB_WORKER_POLL_INTERVAL=1.0
JOB_WORKER_HEARTBEAT_INTERVAL=5.0

# Job types
ALLOWED_JOB_TYPES=demo,test,long-running

# Backend requirements
USE_POSTGRES_JOBS=true

# Database connections
DATABASE_URL=postgresql://user:pass@localhost/db
REDIS_URL=redis://localhost:6379
```

### Settings Integration

```python
from src.config import settings

# Worker configuration
poll_interval = float(getattr(settings, "JOB_WORKER_POLL_INTERVAL", 1.0))
heartbeat_interval = float(getattr(settings, "JOB_WORKER_HEARTBEAT_INTERVAL", 5.0))

# Job type validation
allowed_types = getattr(settings, "ALLOWED_JOB_TYPES", "demo,test,long-running")
allowed_types = [t.strip() for t in allowed_types.split(",")]
```

## Usage Examples

### Starting the Worker

```bash
# Command line
python -m src.workers.jobs_worker

# With custom configuration
JOB_WORKER_POLL_INTERVAL=0.5 JOB_WORKER_HEARTBEAT_INTERVAL=10 python -m src.workers.jobs_worker
```

### Programmatic Usage

```python
import asyncio
from src.workers.jobs_worker import JobsWorker

async def run_worker():
    worker = JobsWorker(
        poll_interval=1.0,
        heartbeat_interval=5.0
    )
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        print("Worker stopped by user")

asyncio.run(run_worker())
```

### Testing with Iteration Limit

```python
# Process only 5 jobs then stop (for testing)
worker = JobsWorker(max_iterations=5)
await worker.start()
```

## Monitoring and Observability

### Logging

Comprehensive structured logging throughout the worker:

```python
logger.info(f"Popped job {job_id} from queue '{job_type}'")
logger.info(f"Job {job_id} transitioned to RUNNING")
logger.error(f"Job {job_id} failed: {error}")
```

### Metrics

Key metrics to monitor:

- **Queue Depth**: Jobs waiting in Redis queues
- **Processing Rate**: Jobs completed per minute
- **Error Rate**: Failed job percentage
- **Heartbeat Health**: Jobs with recent updates

### Health Checks

Worker health can be monitored via:

```python
# Check if worker is processing jobs
active_jobs = len(worker.current_job_id)

# Database connectivity
db_health = await check_database_connection()

# Redis connectivity  
redis_health = await check_redis_connection()
```

## Database Schema

### Jobs Table

```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    payload_json JSONB,
    result_json JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Job Events Table

```sql
CREATE TABLE job_events (
    id SERIAL PRIMARY KEY,
    job_id UUID REFERENCES jobs(id),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## Integration Patterns

### FastAPI Integration

```python
from fastapi import APIRouter, BackgroundTasks
from src.services.jobs_service import JobsService

router = APIRouter()
jobs_service = JobsService(db)

@router.post("/jobs/{job_type}")
async def create_job(job_type: str, payload: dict, background_tasks: BackgroundTasks):
    # Validate job type
    if job_type not in ["demo", "test", "long-running"]:
        raise HTTPException(400, "Invalid job type")
    
    # Create job
    job = await jobs_service.create_job({
        "type": job_type,
        "payload_json": payload
    })
    
    # Queue for processing
    background_tasks.add_task(queue_job, job.id, job_type)
    
    return {"job_id": job.id, "status": "queued"}
```

### SSE Event Streaming

```python
@router.get("/jobs/{job_id}/events")
async def stream_job_events(job_id: str):
    async def event_generator():
        last_timestamp = 0
        while True:
            events = jobs_service.get_events_since(job_id, last_timestamp)
            for event in events:
                yield f"data: {json.dumps(event)}\n\n"
                last_timestamp = event["timestamp"]
            await asyncio.sleep(1)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

## Testing

### Unit Tests

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_jobs_service(mock_db):
    return JobsService(mock_db)

@pytest.mark.asyncio
async def test_demo_job_execution():
    worker = JobsWorker(max_iterations=1)
    
    # Mock job execution
    result = await worker._execute_demo_job("test-job", {"duration_ms": 100})
    
    assert result["status"] == "completed"
    assert "actual_duration_ms" in result
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_full_job_lifecycle():
    # Create job via API
    response = await client.post("/jobs/demo", json={"duration_ms": 100})
    job_id = response.json()["job_id"]
    
    # Wait for completion
    await asyncio.sleep(0.2)
    
    # Check final status
    job = jobs_service.get_job(UUID(job_id))
    assert job.status == "finished"
    assert job.result_json["status"] == "completed"
```

## Performance Considerations

### Scalability

- **Multiple Workers**: Run multiple worker instances for horizontal scaling
- **Queue Partitioning**: Use different Redis instances per tenant
- **Database Sharding**: Partition jobs table by tenant or time

### Optimization Tips

```python
# Batch database operations
jobs_to_update = []
for job in pending_jobs:
    jobs_to_update.append(job.update_status())
await db.bulk_update(jobs_to_update)

# Connection pooling
# Reuse database connections across job executions
db_session = get_db_session()
try:
    await process_jobs(db_session)
finally:
    db_session.close()
```

## Security Considerations

### Access Control

```python
# Validate job type permissions
def can_create_job(user: User, job_type: str) -> bool:
    permissions = get_user_permissions(user)
    return f"jobs:create:{job_type}" in permissions

# Tenant isolation
def validate_job_access(user: User, job_id: str) -> bool:
    job = jobs_service.get_job(UUID(job_id))
    return job.tenant_id == user.tenant_id
```

### Input Validation

```python
# Validate job payload
def validate_job_payload(job_type: str, payload: dict) -> bool:
    schema = JOB_SCHEMAS.get(job_type)
    if not schema:
        return False
    
    try:
        validate(payload, schema)
        return True
    except ValidationError:
        return False
```

## Troubleshooting

### Common Issues

#### Worker Not Processing Jobs

```bash
# Check Redis connectivity
redis-cli ping

# Check queue contents
redis-cli LLEN job_queue:demo

# Check worker logs
tail -f worker.log | grep "Popped job"
```

#### Jobs Stuck in Running State

```sql
-- Find stale jobs
SELECT id, type, updated_at 
FROM jobs 
WHERE status = 'running' 
  AND updated_at < NOW() - INTERVAL '5 minutes';

-- Manually mark as failed
UPDATE jobs SET status = 'failed', error_message = 'Worker timeout'
WHERE id = 'stuck-job-id';
```

#### High Memory Usage

- **Root Cause**: Large job payloads or results
- **Solution**: Implement payload size limits, compress large data
- **Monitoring**: Track memory usage per job type

### Debug Commands

```bash
# Monitor queue depth
watch 'redis-cli LLEN job_queue:demo; redis-cli LLEN job_queue:test'

# Check active jobs
ps aux | grep jobs_worker

# View recent job events
SELECT job_id, event_type, event_data 
FROM job_events 
WHERE created_at > NOW() - INTERVAL '1 hour' 
ORDER BY created_at DESC LIMIT 10;
```

## Migration Notes

### Version Compatibility

- **PostgreSQL**: Requires JSONB support (PostgreSQL 9.4+)
- **Redis**: Requires list operations and key expiration
- **Python**: Asyncio support (Python 3.7+)

### Breaking Changes

- **Job Status Values**: Changed from `pending` to `queued`
- **Event Format**: Added timestamp fields to event_data
- **Cancellation API**: Now uses Redis flags instead of database columns

## Future Enhancements

### Planned Features

- **Priority Queues**: Job priority levels with weighted scheduling
- **Scheduled Jobs**: Cron-like job scheduling
- **Job Dependencies**: DAG-based job workflows
- **Metrics Export**: Prometheus metrics integration
- **Dead Letter Queue**: Failed job retry and DLQ handling

### Performance Optimizations

- **Batch Processing**: Process multiple jobs concurrently
- **Worker Pools**: Specialized workers per job type
- **Result Streaming**: Large result streaming to avoid memory issues
- **Queue Sharding**: Distribute load across multiple Redis instances