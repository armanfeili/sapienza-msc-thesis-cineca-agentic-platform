# Redis Job Store - Quick Start

## Switching from Memory to Redis Backend

### 1. Install Redis

**macOS**:
```bash
brew install redis
brew services start redis
```

**Docker**:
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

### 2. Configure Environment

```bash
# .env or environment
export JOB_STORE_BACKEND=redis
export REDIS_URL=redis://localhost:6379/0

# Optional: adjust TTL
export JOB_TTL_DAYS=7
```

### 3. Verify Connection

```bash
redis-cli ping
# Should return: PONG
```

### 4. Run Tests

```bash
# Test with Redis backend
JOB_STORE_BACKEND=redis pytest tests/ -v

# CI matrix (both backends)
pytest tests/
```

---

## Troubleshooting

### Connection Refused

**Error**: `redis.exceptions.ConnectionError: Error connecting to localhost:6379`

**Fix**:
```bash
# Check Redis is running
redis-cli ping

# Start Redis
brew services start redis  # macOS
docker start redis-container  # Docker
```

### High Latency

**Symptoms**: Slow job creation, P95 > 2s

**Debug**:
```bash
# Check Redis latency
redis-cli --latency

# Check memory usage
redis-cli info memory
```

**Fix**:
- Scale Redis vertically (more memory/CPU)
- Enable AOF persistence tuning: `appendfsync everysec`
- Check network latency

### Orphaned Index Members

**Symptoms**: Alert `IndexOrphansAccumulating` fires

**Debug**:
```bash
# Check ZSET size
redis-cli ZCARD jobs:all

# Count orphans manually
redis-cli ZRANGE jobs:all 0 -1 | while read id; do
  redis-cli EXISTS "job:$id" || echo "Orphan: $id"
done
```

**Fix**:
- Increase cleanup batch size: `BACKGROUND_REDIS_CLEANUP_BATCH_SIZE=1000`
- Decrease interval: `BACKGROUND_REDIS_CLEANUP_INTERVAL=1800`

---

## Monitoring

### Prometheus Metrics

Exposed at `/metrics`:

```promql
# Job creation rate (per second)
rate(job_create_total[5m])

# P95 latency
histogram_quantile(0.95, rate(job_create_duration_seconds_bucket[5m]))

# Failure rate
rate(job_create_total{status="error"}[5m]) / rate(job_create_total[5m])

# Active SSE connections
sse_connections_active{backend="redis"}
```

### Grafana Dashboard

Import `ops/grafana/redis-job-store-dashboard.json`:
- Job creation/get latency (P50/P95/P99)
- Failure rate by status
- SSE connection count
- Index orphan cleanup rate

---

## Production Checklist

- [ ] Redis persistence configured (AOF or RDB)
- [ ] Prometheus scraping `/metrics`
- [ ] Alert rules imported (`ops/prometheus/alerts.yml`)
- [ ] Background cleanup enabled (default: on)
- [ ] Load tests passed (TBD)
- [ ] Runbook documented (`docs/runbooks/redis-job-store.md`)

---

**See Also**:
- [Full Production Guide](docs/redis-job-store-production.md)
- [Architecture Diagram](docs/architecture.md#job-store)
- [CI Matrix Workflow](.github/workflows/job-store-matrix.yml)
