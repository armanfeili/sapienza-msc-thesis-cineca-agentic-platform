# Tools PostgreSQL Migration Guide

This guide walks you through migrating from the legacy in-memory/Redis-only tools storage to the new PostgreSQL + Redis dual-layer architecture.

## Table of Contents

1. [Pre-Migration Checklist](#pre-migration-checklist)
2. [Migration Steps](#migration-steps)
3. [Rollback Procedure](#rollback-procedure)
4. [Post-Migration Validation](#post-migration-validation)
5. [Troubleshooting](#troubleshooting)

## Pre-Migration Checklist

### Requirements

- ✅ PostgreSQL 16+ running and accessible
- ✅ Redis 7+ running and accessible
- ✅ Database migrations applied (Alembic migration 002)
- ✅ Application has network access to both databases
- ✅ Sufficient disk space for tool invocations history

### Environment Variables

Ensure these are set in your deployment:

```bash
# PostgreSQL connection
DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# Redis connection
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your-redis-password  # if auth enabled

# Feature flag (enable PostgreSQL tools storage)
TOOLS_POSTGRES_ENABLED=true

# Optional: Redis key prefix
REDIS_KEY_PREFIX=tools:
```

### Backup Current Data

Before migrating, back up your existing Redis data:

```bash
# Backup Redis data
redis-cli --rdb /backup/redis-dump-$(date +%Y%m%d).rdb

# List existing tool invocations in Redis
redis-cli KEYS "tools:*"
```

### Database Setup

1. **Create database** (if not exists):

```sql
CREATE DATABASE your_database;
```

2. **Run migrations**:

```bash
# From project root
alembic upgrade head
```

3. **Verify tables created**:

```sql
\dt  -- List tables
-- Should see: tools, tool_invocations, tool_audit_events, tenants
```

4. **Create default tenant** (if not exists):

```sql
INSERT INTO tenants (id, name, admin_email, metadata)
VALUES (
    'default-tenant',
    'Default Tenant',
    'admin@localhost',
    '{"auto_created": true}'::jsonb
)
ON CONFLICT (id) DO NOTHING;
```

## Migration Steps

### Step 1: Deploy New Code (Dual-Write Mode)

Deploy the application with the new code. The system will:
- Write to **both** PostgreSQL and Redis
- Read from **PostgreSQL first**, fallback to Redis/legacy store
- Maintain backward compatibility

**No downtime required** - the system gracefully handles both storage backends.

### Step 2: Verify Dual-Write

Test that new invocations are written to both systems:

```bash
# Create a test invocation
curl -X POST http://localhost:8000/v1/tools/system.health/invocations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"args": {"action": "liveness"}}'

# Response will include event_id
# {
#   "event_id": "abc-123-def",
#   "ok": true,
#   ...
# }
```

Verify in PostgreSQL:

```sql
SELECT * FROM tool_invocations
WHERE eid = 'abc-123-def';

-- Should return 1 row with all invocation details
```

Verify in Redis:

```bash
# Check result cache
redis-cli GET "tools:result:abc-123-def"

# Check idempotency mapping (if Idempotency-Key was used)
redis-cli GET "tools:idem:your-key"
```

### Step 3: Migrate Historical Data (Optional)

If you need to preserve historical invocations from Redis:

```bash
# Run migration script (if provided)
python scripts/migrate_tools_from_redis.py --dry-run

# Review the output, then run for real
python scripts/migrate_tools_from_redis.py
```

Or migrate manually:

```python
import redis
import psycopg2
from datetime import datetime

# Connect
r = redis.Redis(host='localhost', port=6379)
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Get all invocation keys
keys = r.keys('invocation:*')

for key in keys:
    data = r.hgetall(key)
    # Parse and insert into PostgreSQL
    cur.execute("""
        INSERT INTO tool_invocations
        (eid, tool_name, params_json, result_json, status, requested_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (eid) DO NOTHING
    """, (
        data['eid'],
        data['tool_name'],
        data['params'],
        data['result'],
        'finished',  # assume finished
        data['owner'],
        datetime.fromtimestamp(float(data['timestamp']))
    ))

conn.commit()
```

### Step 4: Monitor Metrics

Check Prometheus metrics to ensure the migration is working:

```bash
# Tools invocations total
curl http://localhost:8000/metrics | grep tools_invocations_total

# Cache hit rate
curl http://localhost:8000/metrics | grep tools_cache_operations_total

# Idempotency conflicts
curl http://localhost:8000/metrics | grep tools_idempotency_conflicts_total
```

Expected behavior:
- `tools_invocations_total` should be increasing
- `tools_cache_operations_total{result="hit"}` > 50% (after warmup)
- `tools_idempotency_conflicts_total` should be low (< 1% of requests)

### Step 5: Remove Legacy Code (Optional)

After confirming the migration is stable (e.g., 7 days), you can:

1. Remove fallback to legacy `invocation_store`
2. Clean up old Redis keys
3. Remove environment variable `TOOLS_POSTGRES_ENABLED` (make it default)

## Rollback Procedure

If you need to rollback to the legacy system:

### Quick Rollback (No Code Changes)

1. **Disable PostgreSQL storage** via environment variable:

```bash
export TOOLS_POSTGRES_ENABLED=false
```

2. **Restart application**

The system will fall back to using the legacy Redis/in-memory storage.

### Full Rollback (Code Revert)

1. **Revert to previous code version**:

```bash
git revert <commit-hash>  # Revert migration commits
```

2. **Redeploy application**

3. **Verify legacy storage is working**:

```bash
curl -X POST http://localhost:8000/v1/tools/system.health/invocations \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"args": {"action": "liveness"}}'
```

4. **(Optional) Rollback database migration**:

```bash
# Only if you want to remove tables
alembic downgrade -1
```

**Warning**: Rolling back the database migration will **delete all tool invocations data** in PostgreSQL.

## Post-Migration Validation

### Functional Tests

Run the integration test suite:

```bash
# Run all tools tests
pytest tests/test_tools_postgres_integration.py -v

# Run specific test categories
pytest tests/ -k "idempotency" -v  # Idempotency tests
pytest tests/ -k "cache" -v        # Cache tests
pytest tests/ -k "audit" -v        # Audit tests
```

### Performance Tests

Compare latency before/after migration:

```bash
# POST latency (should be <50ms)
time curl -X POST http://localhost:8000/v1/tools/system.health/invocations \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"args": {"action": "liveness"}}'

# GET latency (cache hit, should be <10ms)
time curl http://localhost:8000/v1/tools/system.health/invocations/$EID \
  -H "Authorization: Bearer $TOKEN"
```

### Data Integrity Checks

Verify data consistency:

```sql
-- Count total invocations
SELECT COUNT(*) FROM tool_invocations;

-- Count by status
SELECT status, COUNT(*) FROM tool_invocations
GROUP BY status;

-- Check for orphaned records (no tenant)
SELECT COUNT(*) FROM tool_invocations
WHERE tenant_id NOT IN (SELECT id FROM tenants);
-- Should be 0

-- Check audit trail completeness
SELECT 
    (SELECT COUNT(*) FROM tool_invocations) as invocations,
    (SELECT COUNT(DISTINCT invocation_eid) FROM tool_audit_events) as audited,
    (SELECT COUNT(*) FROM tool_invocations) - 
    (SELECT COUNT(DISTINCT invocation_eid) FROM tool_audit_events) as missing_audit;
```

## Troubleshooting

### Issue: 500 Errors on Invocation Creation

**Symptom**: POST requests fail with 500 Internal Server Error

**Possible Causes**:
1. Default tenant doesn't exist
2. PostgreSQL connection failed
3. Database migration not applied

**Solution**:

```bash
# Check logs
tail -f /var/log/app/uvicorn.log | grep tool

# Create default tenant manually
psql $DATABASE_URL -c "
INSERT INTO tenants (id, name, admin_email)
VALUES ('default-tenant', 'Default Tenant', 'admin@localhost')
ON CONFLICT DO NOTHING;
"

# Verify migration state
alembic current
alembic history
```

### Issue: Idempotency Not Working (Duplicate Invocations)

**Symptom**: Same Idempotency-Key creates multiple invocations

**Possible Causes**:
1. UNIQUE constraint not created
2. PostgreSQL query timing out
3. Idempotency key not being passed to repository

**Solution**:

```sql
-- Check constraint exists
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'tool_invocations'
  AND constraint_type = 'UNIQUE';
-- Should include constraint on (idempotency_key, tool_name)

-- Manually add if missing
ALTER TABLE tool_invocations
ADD CONSTRAINT tool_invocations_idempotency_key_tool_name_key
UNIQUE (idempotency_key, tool_name);
```

### Issue: Cache Always Misses

**Symptom**: All GETs return `X-Cache: MISS` header

**Possible Causes**:
1. Redis connection failed
2. Cache TTL too short
3. Cache keys not being written

**Solution**:

```bash
# Test Redis connection
redis-cli PING
# Should return PONG

# Check existing cache keys
redis-cli KEYS "tools:result:*"

# Monitor cache operations
redis-cli MONITOR | grep tools:

# Check cache TTL
redis-cli TTL "tools:result:abc-123"
# Should be > 0 if cached
```

### Issue: PostgreSQL Performance Slow

**Symptom**: POST/GET requests take > 100ms

**Possible Causes**:
1. Missing indexes
2. Database connection pool exhausted
3. Large JSONB fields

**Solution**:

```sql
-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE tablename = 'tool_invocations';
-- idx_scan should be > 0 for active indexes

-- Add missing indexes if needed
CREATE INDEX CONCURRENTLY idx_tool_invocations_status
ON tool_invocations(status);

-- Check connection pool
SELECT count(*) FROM pg_stat_activity
WHERE datname = 'your_database';
-- Should be < max_connections

-- Analyze query performance
EXPLAIN ANALYZE
SELECT * FROM tool_invocations WHERE eid = 'abc-123';
```

### Issue: Metrics Not Appearing

**Symptom**: `/metrics` endpoint doesn't show tools_* metrics

**Possible Causes**:
1. Metrics not initialized
2. No invocations created yet
3. Prometheus multiprocess mode not set

**Solution**:

```bash
# Check metrics endpoint
curl http://localhost:8000/metrics | grep tools_

# Trigger some invocations to populate metrics
for i in {1..10}; do
  curl -X POST http://localhost:8000/v1/tools/system.health/invocations \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"args": {"action": "liveness"}}'
done

# Check again
curl http://localhost:8000/metrics | grep tools_invocations_total
```

## Getting Help

If you encounter issues not covered here:

1. **Check application logs**: Look for structured logs with `event: tool.*`
2. **Enable debug logging**: Set `LOG_LEVEL=DEBUG`
3. **Review database logs**: Check PostgreSQL slow query log
4. **Consult architecture docs**: See [tools-architecture.md](./tools-architecture.md)
5. **Open an issue**: Provide logs, metrics, and reproduction steps
