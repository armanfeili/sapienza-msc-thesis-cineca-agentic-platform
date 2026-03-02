# Redis Keys for Internal Endpoints

**Last Updated**: October 22, 2025  
**Owner**: Platform Engineering Team

## Overview

This document describes all Redis key patterns, schemas, and TTL policies used by internal endpoints (`/v1/internal/*`). These keys are designed for ephemeral storage, caching, and operational signals.

---

## Key Naming Convention

All internal endpoint keys use the prefix `internal:` or `idemp:` to distinguish them from application data.

**Patterns**:
- `internal:*` - Operational state and cache
- `idemp:*` - Idempotency deduplication cache
- `dbjob:*` - Database job runtime signals

---

## Auto-Start Override

### Key: `internal:auto_start_override`

**Purpose**: Stores UI override for auto-start behavior of built-in models

**Type**: String (JSON)

**Schema**:
```json
{
  "enabled": true,
  "note": "Emergency disable for memory pressure",
  "set_by_sub": "auth0|service-operator",
  "ts": "2025-10-22T15:30:00Z",
  "ttl": 600
}
```

**Fields**:
- `enabled` (boolean): Whether auto-start is enabled/disabled
- `note` (string, optional): Operator-provided reason/note (max 200 chars)
- `set_by_sub` (string): JWT subject (`sub`) of operator who set this
- `ts` (string): ISO 8601 timestamp when set
- `ttl` (integer): TTL in seconds (for reference; actual TTL is Redis-managed)

**TTL**: Configurable via `INTERNAL_UI_OVERRIDE_TTL_SECONDS` (default: 600s, bounds: 60-3600s)

**Set By**: `POST /v1/internal/ops/auto-start-override`

**Read By**: Platform startup logic, `GET /v1/internal/ops/preview-staged`

**Expiry Behavior**: Auto-expires after TTL; absence means "use default behavior"

---

## Preview Cache

### Key: `internal:preview-staged:v1`

**Purpose**: Caches preview of staged built-in manifests to reduce disk I/O

**Type**: String (JSON)

**Schema**:
```json
{
  "items": [
    {
      "manifest_id": "llama32-3b-q4",
      "manifest_version": "1.0.0",
      "model_id": "llama3.2:3b-instruct",
      "est_mem_mb": 2048,
      "reason": "default_auto_start=true",
      "allowed": true,
      "overridden_by_ui": false,
      "concurrency_ok": true,
      "whitelist_ok": true,
      "resources_ok": true,
      "ts": "2025-10-22T15:30:00Z"
    }
  ],
  "count": 1,
  "source_hash": "sha256:abc123...",
  "ts": "2025-10-22T15:30:00Z"
}
```

**Fields**:
- `items` (array): List of PreviewStagedItem objects
- `count` (integer): Total number of items
- `source_hash` (string): SHA256 hash of manifest directory contents (for invalidation)
- `ts` (string): ISO 8601 timestamp when cache was generated

**PreviewStagedItem Fields**:
- `manifest_id` (string): Unique manifest identifier
- `manifest_version` (string, optional): Semantic version
- `model_id` (string): Model identifier (e.g., Ollama tag)
- `est_mem_mb` (integer): Estimated memory requirement in MB
- `reason` (string): Human-readable allow/deny reason
- `allowed` (boolean): Whether this manifest will be deployed
- `overridden_by_ui` (boolean): Whether UI override changed the decision
- `concurrency_ok` (boolean): Whether concurrency limits allow deployment
- `whitelist_ok` (boolean): Whether manifest is on whitelist (if configured)
- `resources_ok` (boolean): Whether sufficient resources available
- `ts` (string): ISO 8601 timestamp

**TTL**: Configurable via `INTERNAL_PREVIEW_CACHE_TTL_SECONDS` (default: 90s, bounds: 30-300s)

**Set By**: `GET /v1/internal/ops/preview-staged` (on cache miss or `force_refresh=true`)

**Read By**: `GET /v1/internal/ops/preview-staged` (on cache hit)

**Invalidation**: 
- Automatic expiry after TTL
- Force refresh via `?force_refresh=true` query parameter
- Hash mismatch detection (future: implement content hash comparison)

---

## Idempotency Keys

### Pattern: `idemp:/internal/ops/auto-start-override:{key}`

**Purpose**: Idempotency deduplication for override endpoint

**Type**: String (JSON)

**Schema**:
```json
{
  "allowed": true,
  "enabled": true,
  "ttl_seconds": 600,
  "error": null,
  "stored_at": "2025-10-22T15:30:00Z"
}
```

**Key Format**: `idemp:/internal/ops/auto-start-override:{idempotency_key}`
- `{idempotency_key}`: Client-provided unique key from `Idempotency-Key` header

**TTL**: 24 hours (86400 seconds)

**Set By**: `POST /v1/internal/ops/auto-start-override` (on first request with Idempotency-Key)

**Read By**: `POST /v1/internal/ops/auto-start-override` (on duplicate request)

**Response Behavior**: Returns cached response with `Idempotency-Replayed: true` header

---

### Pattern: `idemp:/internal/db/jobs:{key}`

**Purpose**: Idempotency deduplication for job creation

**Type**: String (JSON)

**Schema**:
```json
{
  "ok": true,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "stored_at": "2025-10-22T15:30:00Z"
}
```

**Key Format**: `idemp:/internal/db/jobs:{idempotency_key}`
- `{idempotency_key}`: Client-provided unique key from `Idempotency-Key` header

**TTL**: 24 hours (86400 seconds)

**Set By**: `POST /v1/internal/db/jobs` (on first request with Idempotency-Key)

**Read By**: `POST /v1/internal/db/jobs` (on duplicate request)

**Response Behavior**: Returns cached response (202 + Location header) with `Idempotency-Replayed: true` header

---

## Database Job Signals

### Pattern: `dbjob:cancel:{job_id}`

**Purpose**: Cancel signal for running database jobs

**Type**: String (simple flag)

**Value**: `"1"` (presence indicates cancel requested)

**Key Format**: `dbjob:cancel:{job_id}`
- `{job_id}`: UUID of the database job

**TTL**: 300 seconds (5 minutes) - should be checked frequently by worker

**Set By**: `DELETE /v1/internal/db/jobs/{job_id}`

**Read By**: Background job worker (checks periodically during execution)

**Behavior**: Worker should gracefully stop when this key exists

**Expiry Behavior**: Auto-expires after 5 minutes (assumes job completes or fails by then)

---

### Pattern: `dbjob:progress:{job_id}`

**Purpose**: Real-time progress updates for database jobs

**Type**: String (JSON)

**Schema**:
```json
{
  "state": "running",
  "progress": 0.45,
  "message": "Processing institution relationships (45/100)",
  "ts": "2025-10-22T15:30:00Z"
}
```

**Fields**:
- `state` (string): Job state - `queued`, `running`, `finished`, `failed`, `cancelled`
- `progress` (float): Progress percentage (0.0 to 1.0)
- `message` (string, optional): Human-readable status message
- `ts` (string): ISO 8601 timestamp of last update

**Key Format**: `dbjob:progress:{job_id}`
- `{job_id}`: UUID of the database job

**TTL**: 24 hours (86400 seconds)

**Set By**: Background job worker (updates periodically during execution)

**Read By**: `GET /v1/internal/db/jobs/{job_id}` (merged with PostgreSQL data)

**Update Frequency**: Worker should update every 5-10 seconds during active work

**Expiry Behavior**: Retained for 24h after job completion for debugging/auditing

---

## Key Lifecycle Summary

| Key Pattern | Purpose | TTL | Set By | Read By |
|-------------|---------|-----|--------|---------|
| `internal:auto_start_override` | UI override state | 60-3600s (configurable) | POST override | Startup, GET preview |
| `internal:preview-staged:v1` | Preview cache | 30-300s (configurable) | GET preview | GET preview |
| `idemp:/internal/ops/auto-start-override:{key}` | Idempotency | 24h | POST override | POST override |
| `idemp:/internal/db/jobs:{key}` | Idempotency | 24h | POST jobs | POST jobs |
| `dbjob:cancel:{job_id}` | Cancel signal | 300s | DELETE job | Worker |
| `dbjob:progress:{job_id}` | Job progress | 24h | Worker | GET job status |

---

## Configuration

All TTLs are configurable via environment variables:

```bash
# Auto-start override TTL (seconds, clamped 60-3600)
INTERNAL_UI_OVERRIDE_TTL_SECONDS=600

# Preview cache TTL (seconds, clamped 30-300)
INTERNAL_PREVIEW_CACHE_TTL_SECONDS=90

# Idempotency cache TTL (seconds, fixed at 24h)
IDEMPOTENCY_TTL_SECONDS=86400
```

---

## Monitoring & Alerts

### Key Metrics to Monitor

1. **Cache Hit Rate**: 
   - Key: `internal:preview-staged:v1`
   - Target: >80% hit rate during normal operation

2. **Idempotency Replays**:
   - Keys: `idemp:*`
   - Alert if replay rate >5% (may indicate client retry issues)

3. **Job Cancellations**:
   - Keys: `dbjob:cancel:*`
   - Monitor frequency to detect operational issues

4. **Stale Progress**:
   - Keys: `dbjob:progress:*`
   - Alert if `ts` is >60s old while state is `running`

### Recommended Alerts

```yaml
# Example Prometheus/Alertmanager rules
- alert: InternalCacheMissRate
  expr: rate(redis_keyspace_misses{key=~"internal:preview.*"}[5m]) > 0.5
  annotations:
    summary: "High cache miss rate on internal preview endpoint"

- alert: StaleJobProgress
  expr: time() - redis_key_timestamp{key=~"dbjob:progress:.*"} > 120
  annotations:
    summary: "Job progress not updated in 2 minutes"
```

---

## Debugging

### View Current Override

```bash
redis-cli GET "internal:auto_start_override"
```

### Check Preview Cache

```bash
redis-cli GET "internal:preview-staged:v1"
```

### List All Idempotency Keys

```bash
redis-cli KEYS "idemp:*"
```

### Monitor Job Progress

```bash
redis-cli GET "dbjob:progress:{job_id}"
```

### Force Cache Invalidation

```bash
# Delete preview cache
redis-cli DEL "internal:preview-staged:v1"

# Delete specific idempotency key
redis-cli DEL "idemp:/internal/ops/auto-start-override:my-key-123"
```

---

## Best Practices

1. **Never store sensitive data** in Redis (credentials, tokens, PII)
2. **Always set TTL** on ephemeral keys to prevent memory leaks
3. **Use atomic operations** when updating job progress
4. **Include timestamps** in all JSON values for debugging
5. **Hash manifest content** to detect stale cache reliably
6. **Monitor key expiration** to ensure TTLs are working

---

## Related Documentation

- [Internal Endpoints Implementation Plan](./INTERNAL_ENDPOINTS_IMPLEMENTATION_PLAN.md)
- [PostgreSQL Schema](./postgres_schema.md) (TODO)
- [Environment Variables](./environment-variables.md)

---

## Changelog

- **2025-10-22**: Initial documentation
- **2025-10-22**: Added TTL bounds and configuration details
- **2025-10-22**: Added idempotency key patterns

---

**Contact**: Platform Engineering Team  
**Questions**: #platform-engineering on Slack
