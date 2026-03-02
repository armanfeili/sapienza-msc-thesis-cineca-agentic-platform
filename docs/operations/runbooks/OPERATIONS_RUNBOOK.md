# Internal Operations Endpoints - Operations Runbook

**Version:** v0.1.0-internal-ops-phase2  
**Last Updated:** 2025-10-23  
**Status:** Production Ready

---

## Quick Reference

### Endpoints Overview

| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|---------------|
| `/v1/internal/ops/preview-staged` | GET | List staged provider manifests | M2M |
| `/v1/internal/ops/auto-start-override` | POST/GET/DELETE | Control auto-start feature | M2M |
| `/v1/internal/db/counts` | GET | Database entity counts | M2M |
| `/v1/internal/db/jobs` | GET/POST | Manage background jobs | M2M |
| `/v1/internal/db/jobs/{job_id}` | GET/DELETE | Job details/cancellation | M2M |

**Authentication:** All endpoints require M2M token with `internal:all` scope.

---

## Getting M2M Access Token

### Prerequisites

- Auth0 M2M client credentials (client_id + client_secret)
- Access to Auth0 tenant: `cineca.eu.auth0.com`
- API audience: `api://cineca-agentic-platform`

### Obtain Token

```bash
# Request M2M access token from Auth0
curl -X POST "https://cineca.eu.auth0.com/oauth/token" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "<M2M_CLIENT_ID>",
    "client_secret": "<M2M_CLIENT_SECRET>",
    "audience": "api://cineca-agentic-platform",
    "grant_type": "client_credentials"
  }'

# Extract access_token from response
export M2M_TOKEN="<access_token_from_response>"
```

### Token Details

- **Grant Type:** `client-credentials` (gty claim in JWT)
- **Scope:** `internal:all` (required for all internal endpoints)
- **TTL:** Configurable (default: 3600s / 1 hour)
- **Algorithm:** RS256 (validated against Auth0 JWKS)

---

## Common Operations

### 1. Check Staged Provider Manifests

```bash
curl "https://api.cineca.com/v1/internal/ops/preview-staged" \
  -H "Authorization: Bearer $M2M_TOKEN"
```

**Success Response (200):**
```json
{
  "items": [
    {
      "id": "provider-123",
      "name": "Example Provider",
      "version": "1.0.0",
      "status": "staged"
    }
  ],
  "count": 1,
  "timestamp": "2025-10-23T12:00:00Z"
}
```

**Headers:**
- `X-Request-Id`: Unique request identifier
- `X-Correlation-Id`: Correlation ID for distributed tracing
- `X-Subject`: Actor subject from JWT
- `X-Cache-Status`: `miss|hit|refresh`

### 2. Enable Auto-Start Override

```bash
curl -X POST "https://api.cineca.com/v1/internal/ops/auto-start-override" \
  -H "Authorization: Bearer $M2M_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "ttl_seconds": 600
  }'
```

**Success Response (200):**
```json
{
  "enabled": true,
  "set_by": "OrcZzF86Wvh4DaSaaRf7uHLFRNpqa40N@clients",
  "set_at": "2025-10-23T12:00:00Z",
  "expires_at": "2025-10-23T12:10:00Z",
  "ttl_seconds": 600
}
```

### 3. Check Database Entity Counts

```bash
curl "https://api.cineca.com/v1/internal/db/counts" \
  -H "Authorization: Bearer $M2M_TOKEN"
```

**Success Response (200 - Memgraph Available):**
```json
{
  "total_tools": 42,
  "total_users": 128,
  "total_sessions": 15,
  "timestamp": "2025-10-23T12:00:00Z"
}
```

**Feature Unavailable Response (501 - Memgraph Unavailable):**
```json
{
  "type": "about:blank#not-implemented",
  "title": "Not Implemented",
  "status": 501,
  "detail": "Feature 'database counts' requires Memgraph, which is currently unavailable",
  "instance": "/v1/internal/db/counts"
}
```

**Headers (501):**
- `Retry-After: 60` (retry in 60 seconds)
- `X-Feature: memgraph=unavailable` (reason for 501)

### 4. Create Background Job

```bash
curl -X POST "https://api.cineca.com/v1/internal/db/jobs" \
  -H "Authorization: Bearer $M2M_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "create",
    "wipe": false
  }'
```

**Success Response (202):**
```json
{
  "job_id": "job-abc123",
  "status": "pending",
  "created_at": "2025-10-23T12:00:00Z"
}
```

**Headers:**
- `Location: /v1/internal/db/jobs/job-abc123`

### 5. Check Job Status

```bash
curl "https://api.cineca.com/v1/internal/db/jobs/job-abc123" \
  -H "Authorization: Bearer $M2M_TOKEN"
```

**Response (200):**
```json
{
  "job_id": "job-abc123",
  "status": "running",
  "progress": 45,
  "created_at": "2025-10-23T12:00:00Z",
  "started_at": "2025-10-23T12:00:05Z"
}
```

**Possible Status Values:**
- `pending` - Job queued, not started
- `running` - Job in progress
- `completed` - Job finished successfully
- `failed` - Job encountered error

---

## Common Error Scenarios

### Error 1: 401 Unauthorized

**Cause:** Invalid or expired token

**Solution:**
1. Verify token is not expired (check `exp` claim)
2. Obtain fresh token from Auth0
3. Verify audience is `api://cineca-agentic-platform`

```bash
# Decode JWT to check expiration (requires jq)
echo "$M2M_TOKEN" | cut -d'.' -f2 | base64 -d | jq '.exp'
date -r $(echo "$M2M_TOKEN" | cut -d'.' -f2 | base64 -d | jq -r '.exp')
```

### Error 2: 403 Forbidden

**Cause:** Token missing `internal:all` scope or wrong grant type

**Symptoms:**
```json
{
  "type": "about:blank#forbidden",
  "title": "Forbidden",
  "status": 403,
  "detail": "Access denied: requires M2M authentication with internal:all scope"
}
```

**Solution:**
1. Verify token has `gty: "client-credentials"` claim
2. Check scope includes `internal:all`
3. Admin/user tokens are **not allowed** on internal endpoints

### Error 3: 501 Not Implemented (Memgraph Unavailable)

**Cause:** `/v1/internal/db/counts` requires Memgraph connection

**Symptoms:**
```json
{
  "status": 501,
  "detail": "Feature 'database counts' requires Memgraph, which is currently unavailable"
}
```

**Response Headers:**
- `Retry-After: 60` (wait 60 seconds before retrying)
- `X-Feature: memgraph=unavailable`

**Solution:**
1. Wait for `Retry-After` duration (60 seconds)
2. Check Memgraph service status: `docker compose ps memgraph`
3. Restart Memgraph if needed: `docker compose restart memgraph`
4. Contact DevOps if persistent

### Error 4: 409 Conflict (Idempotency Key Conflict)

**Cause:** Duplicate `X-Idempotency-Key` with different request body

**Symptoms:**
```json
{
  "type": "about:blank#conflict",
  "title": "Conflict",
  "status": 409,
  "detail": "Idempotency key already used with different request body"
}
```

**Solution:**
1. Use unique idempotency key for each unique request
2. Reuse same key only if request body is identical
3. Wait 24 hours for key to expire if stuck

---

## Monitoring & Debugging

### Check Audit Logs (PostgreSQL)

```sql
-- Recent operations (last hour)
SELECT 
  correlation_id,
  actor_sub,
  event_type,
  operation_result,
  created_at
FROM internal_ops_events
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 20;

-- Failed operations
SELECT 
  correlation_id,
  event_type,
  operation_result,
  response_status_code,
  response_body,
  created_at
FROM internal_ops_events
WHERE operation_result != 'success'
ORDER BY created_at DESC
LIMIT 10;

-- Operations by actor
SELECT 
  actor_sub,
  COUNT(*) as operation_count,
  COUNT(CASE WHEN operation_result = 'success' THEN 1 END) as success_count,
  COUNT(CASE WHEN operation_result != 'success' THEN 1 END) as failure_count
FROM internal_ops_events
WHERE created_at >= CURRENT_DATE
GROUP BY actor_sub
ORDER BY operation_count DESC;
```

### Check Application Logs

```bash
# View recent logs with correlation IDs
docker compose logs app --tail=100 --follow | grep -E "X-Request-Id|X-Correlation-Id"

# Check for errors
docker compose logs app --tail=500 | grep -i error

# Search for specific correlation ID
docker compose logs app | grep "corr-abc123"
```

### Check Redis Cache

```bash
# Connect to Redis
docker compose exec redis redis-cli

# List idempotency keys (24h TTL)
KEYS "idempotency:*"

# Check specific key
GET "idempotency:sha256_hash_of_request"
TTL "idempotency:sha256_hash_of_request"

# List cache keys (mtime tracking)
KEYS "cache:*"

# Check cache hit rate (approximate)
INFO stats | grep keyspace_hits
INFO stats | grep keyspace_misses
```

---

## Performance Metrics

### Response Time Targets

| Endpoint | P50 | P95 | P99 |
|----------|-----|-----|-----|
| `/v1/internal/ops/preview-staged` (cache hit) | 50ms | 150ms | 300ms |
| `/v1/internal/ops/preview-staged` (cache miss) | 100ms | 200ms | 400ms |
| `/v1/internal/ops/auto-start-override` | 30ms | 100ms | 200ms |
| `/v1/internal/db/counts` (Memgraph available) | 150ms | 500ms | 1000ms |
| `/v1/internal/db/jobs` | 50ms | 150ms | 300ms |

### Cache Performance

- **Hit Rate Target:** >50% for `preview-staged` endpoint
- **Idempotency Replay Rate:** <5% (most requests should be unique)
- **Cache Coherence:** mtime tracking ensures fresh data

### Database Performance

- **Audit Table Writes:** <50ms P95
- **Query Performance:** Efficient with 100k+ audit entries (7 indexes)
- **Expected Growth:** ~100-1000 audit entries per day

---

## Incident Response

### Scenario 1: High Error Rate (>5%)

**Symptoms:**
- Surge in 4xx/5xx responses on `/v1/internal/*` endpoints
- Alert triggered

**Actions:**
1. Check application logs for error patterns
2. Query audit table for failed operations
3. Verify Auth0 service status
4. Check Redis and PostgreSQL connectivity
5. Escalate to DevOps if persistent

### Scenario 2: Cache Hit Rate Drop (<30%)

**Symptoms:**
- Cache hit rate unexpectedly low
- Increased response times

**Actions:**
1. Check Redis memory usage: `docker compose exec redis redis-cli INFO memory`
2. Verify Redis eviction policy: `maxmemory-policy allkeys-lru`
3. Check for cache key conflicts or misconfigurations
4. Review mtime tracking in logs

### Scenario 3: Memgraph Unavailable (Persistent 501)

**Symptoms:**
- `/v1/internal/db/counts` always returns 501
- `X-Feature: memgraph=unavailable` header present

**Actions:**
1. Check Memgraph service: `docker compose ps memgraph`
2. Check Memgraph logs: `docker compose logs memgraph --tail=100`
3. Restart Memgraph: `docker compose restart memgraph`
4. Verify Memgraph connection settings in environment variables
5. Escalate to DevOps if unrecoverable

### Scenario 4: Audit Table Growth (>10GB)

**Symptoms:**
- `internal_ops_events` table exceeds 10GB
- Slow query performance

**Actions:**
1. Check table size: `SELECT pg_size_pretty(pg_total_relation_size('internal_ops_events'));`
2. Archive old entries (>90 days)
3. Vacuum table: `VACUUM ANALYZE internal_ops_events;`
4. Consider partitioning by created_at if growth continues

---

## Configuration Reference

### Environment Variables

```bash
# Token validation
INTERNAL_TOKEN_MAX_TTL_SECONDS=3600  # 1 hour (300-7200s enforced in prod)

# Feature flags
INTERNAL_UI_OVERRIDE_ALLOWED=true  # Enable auto-start override feature
AUTO_START_OVERRIDE_TTL_SECONDS=600  # 10 minutes (60-3600s enforced)

# Database connections
POSTGRES_DSN=postgresql://user:pass@host:5432/cineca_platform
REDIS_URL=redis://host:6379/0

# Auth0
AUTH0_DOMAIN=cineca.eu.auth0.com
AUTH0_AUDIENCE=api://cineca-agentic-platform
```

### Production vs. Development

**Production:**
- `INTERNAL_TOKEN_MAX_TTL_SECONDS`: Enforced range 300-7200s
- No secrets in `.env` files (use secret manager)
- Strict RBAC enforcement

**Development:**
- `INTERNAL_TOKEN_MAX_TTL_SECONDS`: Can exceed 7200s if explicitly set (e.g., 86400)
- Secrets can be in `docker-compose.override.yml` (never commit)
- Same RBAC enforcement (no shortcuts)

---

## Security Best Practices

1. **Never commit secrets** to `.env` or docker-compose files
2. **Rotate M2M client secret** regularly (every 90 days minimum)
3. **Monitor audit table** for suspicious activity
4. **Verify token claims** (gty, scope, aud) before granting access
5. **Use correlation IDs** for distributed tracing and debugging
6. **Rate limit** M2M clients if abuse detected
7. **Alert on anomalies** (error rate surge, unusual access patterns)

---

## Contact & Escalation

**Primary Contact:** DevOps Team  
**Security Contact:** Security Team  
**Escalation:** Team Lead

**Documentation:**
- Deployment Guide: `docs/INTERNAL_ENDPOINTS_DEPLOYMENT_READY.md`
- Security Documentation: `docs/INTERNAL_ENDPOINTS_SECURITY.md`
- Deployment Checklist: `docs/DEPLOYMENT_CHECKLIST.md`

**Issue Reporting:** GitHub Issues  
**Incident Response:** See `docs/INTERNAL_ENDPOINTS_SECURITY.md` Section 6

---

**Last Updated:** 2025-10-23  
**Version:** v0.1.0-internal-ops-phase2  
**Status:** Production Ready
