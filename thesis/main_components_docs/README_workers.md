# Workers Framework

The workers package provides background job processing capabilities for the Cineca Agentic Platform. It implements a robust, PostgreSQL-backed worker system that processes jobs asynchronously from Redis queues.

## Architecture Overview

The workers framework follows these design principles:

- **Queue-Based Processing**: Jobs are queued in Redis and processed by worker instances
- **Database Persistence**: Full job lifecycle tracked in PostgreSQL with status transitions
- **Graceful Shutdown**: Signal handling for clean worker termination
- **Heartbeat Monitoring**: Periodic status updates to detect worker health
- **Cancellation Support**: Runtime job cancellation via Redis flags
- **Event Logging**: Comprehensive audit trail of job execution

## Core Components

### 1. Jobs Worker (`jobs_worker.py`)

PostgreSQL-backed background worker for processing asynchronous jobs.

#### Architecture
```
Redis Queue → Worker Poll → PostgreSQL Load → Execute → PostgreSQL Save → Complete
     ↓              ↓              ↓              ↓              ↓              ↓
  Job ID       Dequeue        Load Job       Run Logic      Store Result    Success
```

#### Features
- **Multi-Queue Support**: Processes jobs from multiple Redis queues by type
- **Status Transitions**: Atomic status updates (queued → running → finished/failed)
- **Cancellation**: Runtime cancellation checks during execution
- **Heartbeat**: Periodic database updates to indicate worker liveness
- **Event Logging**: Structured event logging for job lifecycle tracking
- **Graceful Shutdown**: Signal handling for clean termination

#### Job Types
- **`demo`**: Simple demonstration job with configurable sleep duration
- **`test`**: Instant completion job that echoes input payload
- **`long-running`**: Multi-step job with progress simulation

### 2. Job Lifecycle

#### Status Flow
```
queued → running → finished
    ↓       ↓       ↓
cancelled  failed   (success)
```

#### Status Transitions
- **queued**: Job submitted and waiting for worker
- **running**: Worker has claimed and is executing the job
- **finished**: Job completed successfully with result
- **failed**: Job execution failed with error
- **cancelled**: Job was cancelled before/during execution

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_POSTGRES_JOBS` | `false` | Enable PostgreSQL job backend |
| `JOB_WORKER_POLL_INTERVAL` | `1.0` | Queue polling interval (seconds) |
| `JOB_WORKER_HEARTBEAT_INTERVAL` | `5.0` | Heartbeat update interval (seconds) |
| `ALLOWED_JOB_TYPES` | `demo,test,long-running` | Comma-separated allowed job types |
| `DATABASE_URL` | Required | PostgreSQL connection string |
| `REDIS_URL` | Required | Redis connection string |

### Worker Initialization
```python
from src.workers.jobs_worker import JobsWorker

# Create worker with custom settings
worker = JobsWorker(
    poll_interval=2.0,      # Check queues every 2 seconds
    heartbeat_interval=10.0, # Update status every 10 seconds
    max_iterations=None     # Run indefinitely (None = infinite)
)
```

## Usage Examples

### Starting the Worker
```bash
# Enable PostgreSQL backend
export USE_POSTGRES_JOBS=true

# Configure polling intervals
export JOB_WORKER_POLL_INTERVAL=1.0
export JOB_WORKER_HEARTBEAT_INTERVAL=5.0

# Start worker
python -m src.workers.jobs_worker
```

### Submitting Jobs
```python
from db.redis_cache import jobs_cache

# Submit demo job
job_id = await jobs_cache.queue_job(
    job_type="demo",
    payload={"duration_ms": 5000}
)

# Submit test job
job_id = await jobs_cache.queue_job(
    job_type="test",
    payload={"message": "Hello World", "data": [1, 2, 3]}
)

# Submit long-running job
job_id = await jobs_cache.queue_job(
    job_type="long-running",
    payload={"steps": 20}  # 20 steps × 3s = 60s total
)
```

### Job Execution Flow
```python
# Worker automatically processes jobs:

# 1. Poll Redis queues for job IDs
job_id = await jobs_cache.queue_pop_job("demo", timeout=0)

# 2. Load job from PostgreSQL
job = jobs_service.repo.get_job(UUID(job_id))

# 3. Transition status: queued → running
job = jobs_service.transition_status(job.uuid, "queued", "running")

# 4. Execute job logic
result = await worker._execute_job_type(job_id, job.type, job.payload_json)

# 5. Store result and transition: running → finished
job = jobs_service.repo.update_job_result(job.uuid, result)
job = jobs_service.transition_status(job.uuid, "running", "finished")
```

### Cancellation Support
```python
from db.redis_cache import jobs_cache

# Cancel a running job
await jobs_cache.set_cancel_flag(job_id)

# Worker checks cancellation during execution
if await jobs_cache.check_cancel_flag(job_id):
    raise asyncio.CancelledError("Job cancelled")
```

### Monitoring Job Status
```python
from src.services.jobs_service import JobsService

jobs_service = JobsService(db_session)

# Get job status
job = jobs_service.repo.get_job(job_uuid)
print(f"Job {job.id}: {job.status}")

# Get job events
events = jobs_service.repo.get_job_events(job_uuid)
for event in events:
    print(f"{event.timestamp}: {event.event_type} - {event.event_data}")
```

## Job Types Implementation

### Demo Job
```python
# Payload: {"duration_ms": 5000}
# Simulates work with sleep, checks cancellation every 0.5s
result = {
    "status": "completed",
    "requested_duration_ms": 5000,
    "actual_duration_ms": 4998,
    "message": "Demo job completed successfully"
}
```

### Test Job
```python
# Payload: {"message": "test", "data": [1,2,3]}
# Instant completion, echoes input
result = {
    "status": "completed",
    "input": {"message": "test", "data": [1,2,3]},
    "timestamp": "2024-01-01T12:00:00Z",
    "message": "Test job completed"
}
```

### Long-Running Job
```python
# Payload: {"steps": 10}
# 10 steps × 3 seconds = 30 seconds total
result = {
    "status": "completed",
    "steps_completed": 10,
    "total_duration_ms": 30000,
    "message": "Completed 10 steps"
}
```

## Error Handling

### Job Execution Errors
```python
try:
    result = await worker._execute_job_type(job_id, job_type, payload)
except Exception as e:
    # Mark job as failed
    job = jobs_service.repo.update_job_error(job.uuid, str(e))
    job = jobs_service.transition_status(job.uuid, "running", "failed")

    # Log failure event
    jobs_service.append_event(job.uuid, "status", {
        "to": "failed",
        "error": str(e),
        "timestamp": datetime.utcnow().isoformat()
    })
```

### Worker Loop Errors
```python
while self.running:
    try:
        processed = await self._process_next_job()
        if not processed:
            await asyncio.sleep(self.poll_interval)
    except Exception as e:
        logger.error(f"Error in worker loop: {e}", exc_info=True)
        await asyncio.sleep(self.poll_interval)  # Continue processing
```

### Graceful Shutdown
```python
def _signal_handler(self, signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    self.running = False

# Setup signal handlers
signal.signal(signal.SIGTERM, self._signal_handler)
signal.signal(signal.SIGINT, self._signal_handler)
```

## Performance Characteristics

- **Queue Polling**: Configurable interval (default 1s) with immediate processing
- **Database Operations**: Efficient single-row updates with transactions
- **Heartbeat Overhead**: Minimal database touches (default 5s intervals)
- **Memory Usage**: Bounded by concurrent job processing limits
- **Cancellation Checks**: Lightweight Redis flag checks during execution

## Monitoring and Observability

### Job Metrics
- **Queue Depth**: Jobs waiting in Redis queues
- **Processing Rate**: Jobs completed per minute/hour
- **Error Rate**: Failed vs successful job ratios
- **Execution Time**: Average job duration by type

### Worker Health
- **Heartbeat Status**: Last update timestamp per worker
- **Active Jobs**: Currently processing job count
- **Uptime**: Worker process runtime
- **Error Count**: Processing errors in current session

### Logging
```python
# Structured logging throughout execution
logger.info(f"Popped job {job_id} from queue '{job_type}'")
logger.info(f"Job {job_id} transitioned to RUNNING")
logger.info(f"Job {job_id} completed successfully")
logger.error(f"Job {job_id} failed with error: {e}")
```

## Integration Points

### FastAPI Integration
```python
from fastapi import APIRouter, BackgroundTasks
from db.redis_cache import jobs_cache

router = APIRouter()

@router.post("/jobs/{job_type}")
async def submit_job(job_type: str, payload: dict, background_tasks: BackgroundTasks):
    # Validate job type
    allowed_types = ["demo", "test", "long-running"]
    if job_type not in allowed_types:
        raise HTTPException(400, f"Invalid job type: {job_type}")

    # Submit to queue
    job_id = await jobs_cache.queue_job(job_type, payload)

    # Return job ID for status tracking
    return {"job_id": job_id, "status": "queued"}
```

### Database Schema
```sql
-- Jobs table
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    type VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    payload_json JSONB,
    result_json JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,
    user_id UUID,
    tenant_id UUID
);

-- Job events table
CREATE TABLE job_events (
    id SERIAL PRIMARY KEY,
    job_id UUID REFERENCES jobs(id),
    event_type VARCHAR NOT NULL,
    event_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE
);
```

### Redis Queue Structure
```
Redis Keys:
- jobs:queue:{type}        # Job ID queues by type
- jobs:cancel:{job_id}     # Cancellation flags
- jobs:heartbeat:{job_id}  # Heartbeat timestamps
```

## Security Considerations

- **Input Validation**: Payload validation before job execution
- **Permission Checks**: User authorization for job submission
- **Tenant Isolation**: Multi-tenant job separation
- **Resource Limits**: Execution time and memory constraints
- **Audit Logging**: Comprehensive job execution tracking

## Testing

### Unit Testing
```python
import pytest
from src.workers.jobs_worker import JobsWorker

@pytest.mark.asyncio
async def test_demo_job():
    worker = JobsWorker(max_iterations=1)

    # Test demo job execution
    result = await worker._execute_demo_job("test-job", {"duration_ms": 100})

    assert result["status"] == "completed"
    assert result["requested_duration_ms"] == 100
    assert "actual_duration_ms" in result
```

### Integration Testing
```python
@pytest.mark.asyncio
async def test_full_job_lifecycle():
    # Submit job
    job_id = await jobs_cache.queue_job("test", {"data": "test"})

    # Start worker for one iteration
    worker = JobsWorker(max_iterations=1)
    await worker.start()

    # Verify job completed
    job = jobs_service.repo.get_job(UUID(job_id))
    assert job.status == "finished"
    assert job.result_json["status"] == "completed"
```

## Scaling and Deployment

### Multiple Workers
```bash
# Start multiple worker instances
docker run -e JOB_WORKER_POLL_INTERVAL=0.5 worker-image &
docker run -e JOB_WORKER_POLL_INTERVAL=0.5 worker-image &
docker run -e JOB_WORKER_POLL_INTERVAL=0.5 worker-image &
```

### Queue Partitioning
```python
# Workers can be specialized by job type
export ALLOWED_JOB_TYPES=demo,test  # Worker 1
export ALLOWED_JOB_TYPES=long-running  # Worker 2
```

### Monitoring Setup
```python
# Health check endpoint
@app.get("/health/worker")
async def worker_health():
    return {
        "status": "healthy",
        "active_job": worker.current_job_id,
        "uptime": time.time() - worker.start_time
    }
```

## Troubleshooting

### Common Issues

1. **Jobs Not Processing**
   - Check Redis connectivity
   - Verify USE_POSTGRES_JOBS=true
   - Confirm ALLOWED_JOB_TYPES includes job type

2. **Worker Not Starting**
   - Validate DATABASE_URL format
   - Check PostgreSQL connectivity
   - Review environment variable parsing

3. **Jobs Stuck in Running**
   - Check worker heartbeat (updated_at field)
   - Look for unhandled exceptions in logs
   - Verify cancellation flag handling

4. **High Latency**
   - Adjust JOB_WORKER_POLL_INTERVAL
   - Monitor database connection pool
   - Check Redis performance

### Debug Mode
```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG

# Single iteration for testing
python -c "
import asyncio
from src.workers.jobs_worker import JobsWorker

async def test():
    worker = JobsWorker(max_iterations=1)
    await worker.start()

asyncio.run(test())
"
```

## Future Enhancements

- **Priority Queues**: Job prioritization beyond FIFO
- **Batch Processing**: Group related jobs for efficiency
- **Worker Pools**: Specialized worker pools by capability
- **Metrics Export**: Prometheus metrics for monitoring
- **Circuit Breakers**: Automatic worker failure handling
- **Job Dependencies**: DAG-based job workflows</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_workers.md