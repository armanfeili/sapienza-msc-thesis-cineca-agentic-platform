# Redis Job Store Runbook

## Overview

This runbook covers operations, troubleshooting, and monitoring for the Redis-backed job storage system.

## Architecture

### Storage Backends

The system supports two job storage backends via the `JOB_STORE_BACKEND` environment variable:

- **`memory`** (default): In-memory dictionaries, suitable for development and single-process deployments
- **`redis`**: Redis-backed persistent storage with TTL-based expiration, suitable for production multi-replica deployments

### Configuration

```bash
# Required for Redis mode
export JOB_STORE_BACKEND=redis
export REDIS_URL=redis://localhost:6379/0

# TTL Configuration
export JOB_TTL_DAYS=10              # Job data retention (default: 10 days)
export IDEMPOTENCY_TTL_HOURS=24     # Idempotency key retention (default: 24 hours)
export SSE_RING_SIZE=100            # SSE event buffer size (default: 100)
```

## Redis Key Schema

### Job Data

| Key Pattern | Type | Description | TTL |
|------------|------|-------------|-----|
| `job:{id}` | HASH | Job document (id, type, status, owner, result, etc.) | JOB_TTL_DAYS |
| `jobs:all` | ZSET | Global job index (score = created_at epoch ms) | None* |
| `jobs:owner:{owner}` | ZSET | Per-user job index (score = created_at epoch ms) | None* |
| `jobs:status:{status}` | ZSET | Status-based index (score = created_at epoch ms) | None* |

*ZSET indexes don't have TTL but orphaned members are removed when job HASH expires.

### SSE Event Streaming

| Key Pattern | Type | Description | TTL |
|------------|------|-------------|-----|
| `job:{id}:events` | LIST | Event ring buffer (FIFO, capped at SSE_RING_SIZE) | JOB_TTL_DAYS |
| `job:{id}:event_seq` | COUNTER | Monotonic event ID counter (atomic INCR) | JOB_TTL_DAYS |

### Idempotency

| Key Pattern | Type | Description | TTL |
|------------|------|-------------|-----|
| `idem:{owner}:{tenant}:{type}:{hash}:{key}` | STRING | Maps idempotency key → job_id | IDEMPOTENCY_TTL_HOURS |

**Hash Format**: First 16 chars of SHA256(JSON payload)

## Operations

### Switching Backends

1. **Development/Testing**: Use memory backend
   ```bash
   export JOB_STORE_BACKEND=memory
   # No Redis required
   ```

2. **Production**: Use Redis backend
   ```bash
   export JOB_STORE_BACKEND=redis
   export REDIS_URL=redis://redis-host:6379/0
   ```

3. **Instant Rollback**: Change env var and restart pods
   ```bash
   kubectl set env deployment/app JOB_STORE_BACKEND=memory
   ```

### Inspecting Jobs in Redis

```bash
# List all job keys
redis-cli KEYS "job:*"

# Get job details
redis-cli HGETALL "job:01234567-89ab-cdef-0123-456789abcdef"

# List jobs for a specific user
redis-cli ZREVRANGE "jobs:owner:auth0|user123" 0 -1 WITHSCORES

# List running jobs
redis-cli ZREVRANGE "jobs:status:running" 0 -1 WITHSCORES

# Count jobs by status
redis-cli ZCARD "jobs:status:finished"
redis-cli ZCARD "jobs:status:running"
redis-cli ZCARD "jobs:status:queued"

# View SSE events for a job
redis-cli LRANGE "job:01234567-89ab-cdef-0123-456789abcdef:events" 0 -1

# Check event counter
redis-cli GET "job:01234567-89ab-cdef-0123-456789abcdef:event_seq"

# Check TTL
redis-cli TTL "job:01234567-89ab-cdef-0123-456789abcdef"
```

### Manual Cleanup

```bash
# Delete all job data (CAUTION: Production)
redis-cli --scan --pattern "job:*" | xargs redis-cli DEL
redis-cli --scan --pattern "jobs:*" | xargs redis-cli DEL

# Delete specific job
JOB_ID="01234567-89ab-cdef-0123-456789abcdef"
redis-cli DEL "job:${JOB_ID}"
redis-cli DEL "job:${JOB_ID}:events"
redis-cli DEL "job:${JOB_ID}:event_seq"
redis-cli ZREM "jobs:all" "${JOB_ID}"
redis-cli ZREM "jobs:owner:*" "${JOB_ID}"  # Requires knowing owner
redis-cli ZREM "jobs:status:*" "${JOB_ID}"  # Requires knowing status

# Clean expired idempotency keys (automatic, but manual check)
redis-cli --scan --pattern "idem:*" | while read key; do
  redis-cli TTL "$key"
done
```

### Orphaned ZSET Cleanup

ZSET indexes (`jobs:all`, `jobs:owner:*`, `jobs:status:*`) don't expire automatically. When job HASHes expire, ZSET members become orphaned.

**Detection**:
```bash
# List job IDs in index
redis-cli ZREVRANGE "jobs:all" 0 -1 > /tmp/job_ids.txt

# Check which jobs don't exist
while read job_id; do
  redis-cli EXISTS "job:${job_id}" | grep -q 0 && echo "Orphaned: $job_id"
done < /tmp/job_ids.txt
```

**Cleanup Script** (recommended as cron job or startup task):
```python
import redis
import logging

logger = logging.getLogger(__name__)

async def cleanup_orphaned_zset_members(redis_url: str):
    """Remove ZSET members for expired job HASHes."""
    r = redis.from_url(redis_url, decode_responses=True)
    
    # Check all job indexes
    indexes = ["jobs:all"]
    indexes.extend(r.keys("jobs:owner:*"))
    indexes.extend(r.keys("jobs:status:*"))
    
    total_removed = 0
    for index in indexes:
        members = r.zrange(index, 0, -1)
        for job_id in members:
            if not r.exists(f"job:{job_id}"):
                r.zrem(index, job_id)
                total_removed += 1
                logger.info(f"Removed orphaned member {job_id} from {index}")
    
    logger.info(f"Cleanup complete: {total_removed} orphaned members removed")
    return total_removed
```

## Monitoring

### Key Metrics

**Prometheus Metrics** (to be implemented):
- `job_create_total{backend,status}` - Total job creations
- `job_get_duration_seconds{backend}` - Histogram of GET latency
- `job_list_duration_seconds{backend}` - Histogram of list query latency
- `sse_connections_active{backend}` - Active SSE streams
- `sse_resume_hits_total` - Successful Last-Event-ID resumes
- `sse_gap_events_total` - Ring buffer gaps (no backlog)
- `job_cancellations_total{backend,first_time}` - Cancellation operations

**Redis Metrics** (via `redis_exporter`):
- `redis_connected_clients` - Active connections
- `redis_memory_used_bytes` - Memory usage
- `redis_keyspace_hits_total` - Cache hit rate
- `redis_keyspace_misses_total` - Cache miss rate
- `redis_evicted_keys_total` - Evictions (should be 0 with TTL)

### Health Checks

```bash
# Application health (includes Redis connectivity check)
curl http://localhost:8000/health

# Redis health
redis-cli PING
redis-cli INFO stats
redis-cli INFO memory

# Check current backend
curl http://localhost:8000/metrics | grep job_backend_info
```

### Alerting

**Recommended Alerts**:

1. **Redis Down**: `redis_up == 0`
2. **High Memory**: `redis_memory_used_bytes > 0.8 * redis_memory_max_bytes`
3. **Slow Queries**: `job_get_duration_seconds{quantile="0.99"} > 1.0`
4. **Orphaned ZSET Members**: Custom metric from cleanup script > threshold

## Troubleshooting

### Jobs Not Persisting

**Symptoms**: Jobs created but disappear immediately

**Diagnosis**:
```bash
# Check backend configuration
curl http://localhost:8000/health | jq '.details.redis'

# Verify Redis connection
redis-cli -u $REDIS_URL PING

# Check logs
kubectl logs -f deployment/app | grep -i redis
```

**Solutions**:
- Verify `JOB_STORE_BACKEND=redis` is set
- Verify `REDIS_URL` is correct
- Check Redis authentication (if required)
- Check network connectivity to Redis

### SSE Events Missing

**Symptoms**: SSE stream shows "no-backlog-replay-from" comment

**Diagnosis**:
```bash
# Check event buffer
redis-cli LLEN "job:${JOB_ID}:events"

# Check event counter
redis-cli GET "job:${JOB_ID}:event_seq"

# Check ring size configuration
echo $SSE_RING_SIZE
```

**Explanation**: Ring buffer has fixed size (default 100). Old events are evicted FIFO when buffer is full. This is expected behavior for long-running jobs with many events.

**Solutions**:
- Increase `SSE_RING_SIZE` if needed (trade-off: memory usage)
- Connect to SSE stream earlier to catch events
- Accept gap and continue from live stream

### Idempotency Not Working

**Symptoms**: Duplicate jobs created with same idempotency key

**Diagnosis**:
```bash
# List idempotency keys
redis-cli --scan --pattern "idem:*"

# Check specific key TTL
redis-cli TTL "idem:user:tenant:demo:abc123:my-key"

# Check configuration
echo $IDEMPOTENCY_TTL_HOURS
```

**Solutions**:
- Verify `Idempotency-Key` header is sent consistently
- Check key TTL hasn't expired (default 24 hours)
- Verify payload is identical (JSON serialization order matters)

### High Redis Memory Usage

**Diagnosis**:
```bash
# Check memory usage
redis-cli INFO memory | grep used_memory_human

# Count keys by pattern
redis-cli --scan --pattern "job:*" | wc -l
redis-cli --scan --pattern "jobs:*" | wc -l
redis-cli --scan --pattern "idem:*" | wc -l

# Check largest keys
redis-cli --bigkeys
```

**Solutions**:
- Verify TTLs are set correctly
- Run orphaned ZSET cleanup
- Reduce `JOB_TTL_DAYS` if appropriate
- Increase Redis memory limit
- Enable Redis eviction policy (NOT recommended for job data)

### Race Conditions / Concurrent Modifications

**Symptoms**: Job status inconsistencies, duplicate cancellations

**Current Behavior**: 
- Job updates use Redis pipelines (atomic within pipeline)
- Cancellation uses read-check-update pattern (minimal race window)
- Tests verify correctness (first cancel = 202, subsequent = 200)

**If Issues Occur**:
- Consider Lua script for true CAS (compare-and-set) semantics
- Add distributed locks for critical sections
- Monitor for concurrency issues via metrics

## Multi-Replica Deployment

### Current Status

**SSE Streaming**: Redis pubsub is configured but not actively used. Current implementation polls job status every 200ms. SSE works correctly in multi-replica deployments but clients may experience:
- Connection to different replicas on reconnect
- Need to rely on Last-Event-ID resume for event continuity

**Job Data**: Fully compatible with multi-replica deployments via Redis shared state

### Recommendations

1. **Use sticky sessions** for SSE endpoints to keep client connected to same replica
2. **Configure Redis pubsub** for real-time SSE updates (reduce polling overhead)
3. **Monitor orphaned events** via cleanup script running on single replica (leader election)

## Migration Guide

### From Memory to Redis

1. **Start Redis**: `docker compose up -d redis`
2. **Update env vars**:
   ```bash
   export JOB_STORE_BACKEND=redis
   export REDIS_URL=redis://localhost:6379/0
   ```
3. **Restart application**: Existing in-memory jobs will be lost (expected)
4. **Verify**: Check logs for `redis.job.created` messages

### From Redis to Memory (Rollback)

1. **Update env var**: `export JOB_STORE_BACKEND=memory`
2. **Restart application**
3. **Note**: Redis data persists but won't be read (can clean up later)

## Testing

### Run Tests Against Both Backends

```bash
# Memory mode (default)
JOB_STORE_BACKEND=memory pytest tests/test_jobs.py -v

# Redis mode (requires running Redis)
JOB_STORE_BACKEND=redis REDIS_URL=redis://localhost:6379/0 pytest tests/test_jobs.py -v

# Both should pass identically (40/40 tests)
```

### Load Testing

```bash
# Create 100 jobs concurrently
for i in {1..100}; do
  curl -X POST http://localhost:8000/v1/jobs \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: test-$i" \
    -d '{"type":"demo","payload":{"duration_ms":1000}}' &
done
wait

# Check Redis load
redis-cli INFO stats
redis-cli --bigkeys

# Check job counts
redis-cli ZCARD "jobs:all"
redis-cli ZCARD "jobs:status:running"
```

## Security

### Redis ACLs (Recommended for Production)

```bash
# Create ACL user for job store
redis-cli ACL SETUSER jobstore on >password ~job:* ~jobs:* ~idem:* +@all

# Update REDIS_URL
export REDIS_URL=redis://jobstore:password@redis-host:6379/0
```

### Data Encryption

- **In-transit**: Use `rediss://` URL for TLS
- **At-rest**: Enable Redis encryption (RDB/AOF)
- **Secrets**: Job payloads may contain sensitive data, ensure Redis is secured

## Performance Tuning

### Redis Configuration

```conf
# Recommended redis.conf settings
maxmemory-policy noeviction  # Don't evict TTL keys
save ""                       # Disable RDB snapshots (or configure as needed)
appendonly yes               # Enable AOF for durability
appendfsync everysec         # Balance performance/durability
```

### Connection Pooling

Current configuration (see `src/jobs/redis_client.py`):
```python
max_connections=10    # Connection pool size
socket_timeout=5.0    # Command timeout
socket_connect_timeout=5.0
```

Adjust based on load testing results.

## References

- **Redis Documentation**: https://redis.io/docs/
- **Job API Specification**: `/docs/api/jobs.md`
- **Source Code**: `src/jobs/redis_store.py`
- **Configuration**: `src/config.py`

## Change Log

- **2025-10-08**: Initial Redis job store implementation with dual-mode support
- **2025-10-08**: All 40 tests passing in both memory and Redis modes
