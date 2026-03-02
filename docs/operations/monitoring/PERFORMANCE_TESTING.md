# Performance & Load Testing Guide

**Last Updated**: December 2024

## Overview

This guide covers performance testing, load testing, and capacity planning for the Cineca Agentic Platform using k6 and Locust.

## Performance Targets

### Latency Targets

| Operation | p50 | p95 | p99 |
|-----------|-----|-----|-----|
| API Requests (read) | < 100ms | < 500ms | < 1s |
| API Requests (write) | < 200ms | < 1s | < 2s |
| Agent E2E Run | < 15s | < 30s | < 2min |
| Cypher Translation | < 500ms | < 1s | < 3s |
| Tool Invocation | < 1s | < 3s | < 10s |
| LLM Call | < 3s | < 10s | < 30s |

### Throughput Targets

| Endpoint | Target RPS | Max RPS |
|----------|------------|---------|
| `/health` | 1000 | 5000 |
| `/api/v1/agents` (list) | 100 | 500 |
| `/api/v1/agents/run` | 10 | 50 |
| `/api/v1/cypher/translate` | 50 | 200 |
| `/api/v1/tools/invoke` | 50 | 200 |

### Resource Limits

| Resource | Limit | Alert Threshold |
|----------|-------|-----------------|
| CPU (per pod) | 2 cores | 80% |
| Memory (per pod) | 4 GB | 80% |
| Database connections | 100 | 80 |
| Redis connections | 1000 | 80% |
| Concurrent agent runs | 50 | 40 |

## k6 Load Testing

### Installation

```bash
# macOS
brew install k6

# Linux
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6

# Docker
docker pull grafana/k6:latest
```

### Running Tests

```bash
# Basic test (1 VU, 1 iteration)
k6 run tests/performance/load-test.js

# Load test (50 VUs, 5 minutes)
k6 run --vus 50 --duration 5m tests/performance/load-test.js

# Stress test (ramp up to 200 VUs)
k6 run --stage 1m:50 --stage 3m:100 --stage 2m:200 --stage 2m:0 tests/performance/load-test.js

# With environment variables
k6 run \
  --env BASE_URL=https://api.cineca-platform.io \
  --env AUTH_TOKEN=$AUTH_TOKEN \
  tests/performance/load-test.js

# Output to JSON for analysis
k6 run --out json=results.json tests/performance/load-test.js

# Output to InfluxDB + Grafana
k6 run --out influxdb=http://localhost:8086/k6 tests/performance/load-test.js
```

### Test Scenarios

#### 1. Agent E2E Workflow
**Goal**: Test complete agent execution flow
**VUs**: 10-20
**Duration**: 10 minutes
**Expected**: 95% success, p95 < 30s

```bash
k6 run \
  --env BASE_URL=http://localhost:8000 \
  --env AUTH_TOKEN=$TOKEN \
  --vus 10 \
  --duration 10m \
  tests/performance/load-test.js
```

#### 2. Cypher Translation
**Goal**: Test NL→Cypher translation throughput
**Rate**: 50 req/s
**Duration**: 5 minutes
**Expected**: 99% success, p95 < 1s

```bash
k6 run \
  --env BASE_URL=http://localhost:8000 \
  --scenario cypher_translation \
  tests/performance/load-test.js
```

#### 3. Bulk Reads
**Goal**: Test database read performance
**Iterations**: 1000 (100 per VU)
**Expected**: 99% success, p95 < 2s

```bash
k6 run \
  --env BASE_URL=http://localhost:8000 \
  --scenario bulk_reads \
  tests/performance/load-test.js
```

#### 4. Spike Test
**Goal**: Test system under sudden traffic spike
**Pattern**: 10 → 100 req/s (spike) → 10 req/s
**Expected**: System recovers, no crashes

```bash
k6 run \
  --env BASE_URL=http://localhost:8000 \
  --scenario spike_test \
  tests/performance/load-test.js
```

### Analyzing Results

```bash
# Summary report
k6 run --summary-export=summary.json tests/performance/load-test.js

# Parse JSON results
jq '.metrics.http_req_duration' results.json

# Calculate percentiles
jq '.metrics.http_req_duration.values | {"p50": .p50, "p95": .p95, "p99": .p99}' results.json

# Error rate
jq '.metrics.http_req_failed.values.rate' results.json
```

## Locust Testing

### Installation

```bash
pip install locust
```

### Running Locust

```bash
# Start Locust web UI
locust -f tests/performance/locust_test.py --host=http://localhost:8000

# Headless mode (no UI)
locust -f tests/performance/locust_test.py \
  --host=http://localhost:8000 \
  --users 100 \
  --spawn-rate 10 \
  --run-time 10m \
  --headless

# Distributed mode (master + workers)
# Terminal 1 (master)
locust -f tests/performance/locust_test.py --master

# Terminal 2-4 (workers)
locust -f tests/performance/locust_test.py --worker --master-host=localhost
```

### Access Locust UI

Open browser: `http://localhost:8089`

## Database Performance Tuning

### PostgreSQL

#### Connection Pool Tuning

```python
# config.py
SQLALCHEMY_POOL_SIZE = 20          # Base pool size
SQLALCHEMY_MAX_OVERFLOW = 40       # Additional connections
SQLALCHEMY_POOL_TIMEOUT = 30       # Seconds to wait for connection
SQLALCHEMY_POOL_RECYCLE = 3600     # Recycle connections after 1 hour
```

#### Query Optimization

```sql
-- Enable query timing
SET track_io_timing = on;

-- Analyze slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Check table bloat
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Vacuum and analyze
VACUUM ANALYZE;
```

#### Index Optimization

```sql
-- Find missing indexes
SELECT 
  schemaname, tablename, 
  pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS size,
  seq_scan, idx_scan
FROM pg_stat_user_tables
WHERE seq_scan > idx_scan
ORDER BY seq_scan DESC;

-- Create indexes
CREATE INDEX CONCURRENTLY idx_agent_runs_tenant_created 
  ON agent_runs(tenant_id, created_at DESC);

CREATE INDEX CONCURRENTLY idx_tool_invocations_status 
  ON tool_invocations(status, created_at DESC);
```

### Redis

#### Memory Optimization

```bash
# Check memory usage
redis-cli INFO memory

# Configure maxmemory policy
redis-cli CONFIG SET maxmemory 2gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Set key expiration
redis-cli CONFIG SET timeout 300  # Close idle connections after 5 min
```

#### Performance Settings

```bash
# Enable lazy freeing
redis-cli CONFIG SET lazyfree-lazy-eviction yes
redis-cli CONFIG SET lazyfree-lazy-expire yes

# Increase client connections
redis-cli CONFIG SET maxclients 10000

# Background save
redis-cli CONFIG SET save "900 1 300 10 60 10000"
```

### Memgraph

#### Timeout Configuration

```cypher
// Set query timeout (30 seconds)
SET GLOBAL QUERY EXECUTION TIMEOUT 30000;

// Set transaction timeout
SET TRANSACTION_TIMEOUT 60000;
```

#### Memory Settings

```bash
# Configure Memgraph memory limit
memgraph --memory-limit=8192  # 8 GB

# Enable storage mode for large graphs
memgraph --storage-mode=ON_DISK_TRANSACTIONAL
```

#### Query Optimization

```cypher
// Use query plan to find bottlenecks
EXPLAIN MATCH (a:Author)-[:WROTE]->(p:Paper)
WHERE p.year > 2020
RETURN a.name, COUNT(p);

// Create indexes
CREATE INDEX ON :Author(name);
CREATE INDEX ON :Paper(year);

// Analyze query performance
PROFILE MATCH (a:Author)-[:WROTE]->(p:Paper)
RETURN a.name, COUNT(p);
```

## Cache Tuning

### Application-Level Caching

```python
# config.py
CACHE_CONFIG = {
    'CACHE_TYPE': 'redis',
    'CACHE_REDIS_URL': 'redis://localhost:6379/1',
    'CACHE_DEFAULT_TIMEOUT': 300,      # 5 minutes
    'CACHE_KEY_PREFIX': 'cineca:',
}

# TTL by cache type
CACHE_TTL = {
    'agent_list': 60,           # 1 minute
    'tool_list': 300,           # 5 minutes
    'cypher_translation': 3600, # 1 hour (deterministic)
    'user_session': 1800,       # 30 minutes
}
```

### Cache Warming

```python
# Warm frequently accessed data on startup
async def warm_cache():
    """Warm cache with frequently accessed data."""
    # Agent definitions
    agents = await get_all_agents()
    await cache.set('agents:all', agents, ttl=300)
    
    # Tool definitions
    tools = await get_all_tools()
    await cache.set('tools:all', tools, ttl=300)
    
    # Common Cypher patterns
    patterns = load_common_cypher_patterns()
    for pattern in patterns:
        await cache.set(f'cypher:{pattern.id}', pattern, ttl=3600)
```

## Bottleneck Identification

### Application Profiling

```python
# Use cProfile for Python profiling
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Your code here

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 functions
```

### APM (Application Performance Monitoring)

```bash
# Install New Relic
pip install newrelic

# Run with New Relic
NEW_RELIC_CONFIG_FILE=newrelic.ini newrelic-admin run-program python main.py

# Or use DataDog
DD_TRACE_ENABLED=true ddtrace-run python main.py
```

### Database Query Profiling

```python
# SQLAlchemy query profiling
from sqlalchemy import event
from sqlalchemy.engine import Engine
import time

@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault('query_start_time', []).append(time.time())

@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.time() - conn.info['query_start_time'].pop(-1)
    if total > 0.1:  # Log slow queries (> 100ms)
        logger.warning(f"Slow query ({total:.3f}s): {statement[:100]}")
```

## Performance Test Report Template

```markdown
# Performance Test Report

**Date**: YYYY-MM-DD
**Environment**: staging/production
**Tool**: k6 / Locust
**Duration**: Xm

## Summary

- **Total Requests**: X
- **Success Rate**: X%
- **Error Rate**: X%
- **Avg Response Time**: Xms
- **p95 Response Time**: Xms
- **p99 Response Time**: Xms
- **Max RPS**: X

## Scenarios Tested

### Agent E2E Workflow
- VUs: 20
- Duration: 10m
- Success Rate: 96.5%
- p95 Latency: 28s ✅ (target: < 30s)

### Cypher Translation
- Rate: 50 req/s
- Duration: 5m
- Success Rate: 99.2%
- p95 Latency: 890ms ✅ (target: < 1s)

## Bottlenecks Identified

1. **LLM API Rate Limiting** - 2% of requests throttled
   - Mitigation: Implement LLM provider fallback

2. **Database Connection Pool Exhaustion** - Peak usage 95%
   - Mitigation: Increase pool size from 20 → 30

3. **Redis Memory Pressure** - 85% memory utilization
   - Mitigation: Enable LRU eviction, increase maxmemory

## Recommendations

- [ ] Increase PostgreSQL connection pool size
- [ ] Implement LLM request queueing
- [ ] Add caching for Cypher translations
- [ ] Scale Redis to 4GB memory
- [ ] Add horizontal pod autoscaling (HPA)

## Next Steps

- Re-run tests after optimizations
- Conduct soak test (24-hour duration)
- Test with production traffic patterns
```

## Continuous Performance Testing

### GitHub Actions Integration

```yaml
# .github/workflows/performance-test.yml
name: Performance Test

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
  workflow_dispatch:

jobs:
  k6-load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run k6 test
        uses: grafana/k6-action@v0.3.0
        with:
          filename: tests/performance/load-test.js
          flags: --out json=results.json
        env:
          BASE_URL: ${{ secrets.STAGING_URL }}
          AUTH_TOKEN: ${{ secrets.TEST_AUTH_TOKEN }}
      
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: k6-results
          path: results.json
      
      - name: Check thresholds
        run: |
          ERROR_RATE=$(jq '.metrics.http_req_failed.values.rate' results.json)
          if (( $(echo "$ERROR_RATE > 0.05" | bc -l) )); then
            echo "Error rate exceeded 5%: $ERROR_RATE"
            exit 1
          fi
```

## References

- [k6 Documentation](https://k6.io/docs/)
- [Locust Documentation](https://docs.locust.io/)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [Redis Performance Best Practices](https://redis.io/docs/management/optimization/)
- [Memgraph Performance Guide](https://memgraph.com/docs/memgraph/reference-guide/performance)
