# Production Readiness Checklist & Deployment Guide

**Status**: Production deployment checklist  
**Last Updated**: October 20, 2025  
**Version**: 1.0

---

## 📋 Pre-Deployment Verification

### Infrastructure Ready?

- [ ] Kubernetes cluster provisioned (or Docker Compose for single-node)
- [ ] PostgreSQL database initialized with migrations
- [ ] Redis cluster deployed with persistence
- [ ] Memgraph instance ready (if using knowledge graph)
- [ ] Network policies configured (TLS for inter-service communication)
- [ ] Load balancer configured with health checks
- [ ] DNS records pointing to load balancer
- [ ] SSL/TLS certificates installed

### Configuration Ready?

- [ ] All required environment variables documented and set (see below)
- [ ] Database credentials rotated (not using defaults)
- [ ] API keys for external services (Auth0, etc.) provisioned
- [ ] Rate limiting configured for production load
- [ ] Monitoring and logging infrastructure ready
- [ ] Backup and disaster recovery tested

### Code Ready?

- [ ] All tests passing (27/27 integration tests)
- [ ] All auth tests passing (8/8 security tests)
- [ ] No hardcoded secrets in code or docs
- [ ] OpenAPI documentation complete
- [ ] Production build tested locally
- [ ] Git history clean and documented

---

## 🔧 Required Environment Variables

### Core Service Configuration

```bash
# API Server
API_HOST=0.0.0.0                    # Bind address
API_PORT=8000                       # API port
ENVIRONMENT=production              # prod, staging, dev
LOG_LEVEL=info                      # debug, info, warning, error
DEBUG=false                         # Never true in production

# Rate Limiting (CRITICAL)
RATE_LIMIT_MODE=prod               # prod=100/min, test=10000/min (MUST be 'prod' in production)

# Database
DATABASE_URL=postgresql://user:pass@db.prod.example.com:5432/agents_db
DATABASE_POOL_SIZE=20              # Connection pool size
DATABASE_POOL_TIMEOUT=30           # Timeout in seconds
```

### Cache & Session Configuration

```bash
# Redis (required for caching, idempotency, rate limiting)
REDIS_URL=redis://cache.prod.example.com:6379/0
IDEMPOTENCY_TTL_SECONDS=86400      # 24 hours
SESSION_TTL_SECONDS=3600           # 1 hour
CACHE_TTL_SECONDS=300              # 5 minutes

# Memgraph (optional, for knowledge graphs)
MEMGRAPH_URL=bolt://memgraph:7687
MEMGRAPH_USER=neo4j
MEMGRAPH_PASSWORD=<secure-password>
```

### Authentication & Authorization

```bash
# Auth0
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_CLIENT_ID=<client-id>
AUTH0_CLIENT_SECRET=<client-secret>
AUTH0_AUDIENCE=https://api.example.com

# JWT Validation
JWT_ALGORITHM=RS256
JWT_SIGNING_KEY=<public-key-from-auth0>
JWT_VERIFICATION_KEY=<public-key-from-auth0>
```

### Monitoring & Observability

```bash
# Application Insights / OpenTelemetry
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=cineca-agents-api
OTEL_ENVIRONMENT=production

# Structured Logging
LOG_FORMAT=json                    # json for structured logs
LOG_CORRELATION_ID_HEADER=X-Request-Id

# Metrics
METRICS_ENABLED=true
METRICS_PORT=9090
```

### Feature Flags & Limits

```bash
# Operational Limits
MAX_SESSION_DURATION_HOURS=24
MAX_STEPS_PER_SESSION=1000
MAX_REQUEST_BODY_BYTES=10485760  # 10MB
MAX_RESPONSE_TIMEOUT_SECONDS=300

# Feature Flags
ENABLE_DEPRECATION_WARNINGS=true
ENABLE_EXPERIMENTAL_FEATURES=false
ENABLE_ADMIN_ENDPOINTS=true      # Set to false to hide /admin/* endpoints
```

---

## 🏥 Health Check Endpoints

### Startup Probe: `/health/startup`

**Purpose**: Verify application initialization (called once)  
**Expected Response**:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2025-10-20T09:30:00Z",
  "environment": {
    "rate_limit_mode": "prod",
    "rate_limit_backend": "redis",
    "database": "postgresql",
    "cache": "redis"
  },
  "limits": {
    "sessions/create": 100,
    "steps/create": 100,
    "runs/create": 20
  },
  "checks": {
    "database": "ok",
    "cache": "ok",
    "auth": "ok"
  }
}
```

**Kubernetes Configuration**:
```yaml
startupProbe:
  httpGet:
    path: /health/startup
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 30  # 150 seconds max
```

### Liveness Probe: `/health/live`

**Purpose**: Check if app is running (called periodically)  
**Expected Response**:
```json
{
  "status": "ok",
  "uptime_seconds": 3600,
  "requests_processed": 5432
}
```

**Kubernetes Configuration**:
```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3
```

### Readiness Probe: `/health/ready`

**Purpose**: Check if app is ready to handle traffic  
**Expected Response**:
```json
{
  "status": "ok",
  "database": "connected",
  "cache": "connected",
  "requests_queued": 0
}
```

**Kubernetes Configuration**:
```yaml
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 2
```

---

## 🔍 Smoke Test Suite

Run these after deployment to verify basic functionality:

```bash
#!/bin/bash
set -e

API_URL="https://api.example.com/v1"
ADMIN_TOKEN="<valid-admin-token>"  # See section below

echo "Running smoke tests..."

# 1. Health Check
echo "✓ Testing health endpoint..."
curl -s "$API_URL/health" | jq . || exit 1

# 2. Authentication (User Endpoint)
echo "✓ Testing user authentication..."
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_URL/user/me" | jq . || exit 1

# 3. Session Creation (Idempotency)
echo "✓ Testing session creation..."
SESSION=$(curl -s -X POST "$API_URL/agents/sessions" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-$(date +%s)" \
  -d '{"manager":"auto","tools":[]}' | jq -r '.session_id')
echo "Created session: $SESSION"

# 4. Session Retrieval
echo "✓ Testing session retrieval..."
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_URL/agents/sessions/$SESSION" | jq . || exit 1

# 5. Rate Limiting Headers
echo "✓ Testing rate limit headers..."
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_URL/agents/sessions/$SESSION" | \
  grep -q "RateLimit-Limit" || exit 1

# 6. ETag Caching
echo "✓ Testing ETag caching..."
RESPONSE=$(curl -s -w "%{http_code}" -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_URL/agents/sessions")
HTTP_CODE=$(echo "$RESPONSE" | tail -c 4)
[ "$HTTP_CODE" = "200" ] || exit 1

# 7. Idempotency Replay
echo "✓ Testing idempotency replay..."
IDEM_KEY="test-idempotency-$(date +%s)"
RESP1=$(curl -s -X POST "$API_URL/agents/sessions" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d '{"manager":"auto","tools":[]}')
RESP2=$(curl -s -X POST "$API_URL/agents/sessions" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d '{"manager":"auto","tools":[]}')
echo "$RESP2" | grep -q "Idempotency-Replayed" || exit 1

# 8. Session Cleanup
echo "✓ Testing session deletion..."
curl -s -X DELETE -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_URL/agents/sessions/$SESSION" | jq . || exit 1

echo "✅ All smoke tests passed!"
```

---

## 🔐 Token Management

### Fetch Fresh Tokens

Use the provided script to fetch tokens without hardcoding:

```bash
#!/bin/bash
# scripts/fetch_auth0_tokens.sh

set -e

AUTH0_DOMAIN="${AUTH0_DOMAIN:-your-tenant.auth0.com}"
AUTH0_CLIENT_ID="${AUTH0_CLIENT_ID:-your-client-id}"
AUTH0_CLIENT_SECRET="${AUTH0_CLIENT_SECRET:-your-client-secret}"
AUTH0_AUDIENCE="${AUTH0_AUDIENCE:-https://api.example.com}"

echo "Fetching Auth0 tokens..."

# Get access token
TOKEN=$(curl -s --request POST \
  --url "https://$AUTH0_DOMAIN/oauth/token" \
  --header "content-type: application/json" \
  --data "{
    \"client_id\": \"$AUTH0_CLIENT_ID\",
    \"client_secret\": \"$AUTH0_CLIENT_SECRET\",
    \"audience\": \"$AUTH0_AUDIENCE\",
    \"grant_type\": \"client_credentials\"
  }" | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  echo "❌ Failed to fetch token"
  exit 1
fi

echo "✅ Token fetched (first 20 chars): ${TOKEN:0:20}..."
echo "Store this token in: ADMIN_TOKEN environment variable"
echo "$TOKEN"
```

### Token Rotation Schedule

- **Fetch Schedule**: Every 7 days (tokens expire in 30 days)
- **Test Schedule**: Every 24 hours (verify tokens work)
- **Emergency Rotation**: If token compromised, fetch immediately
- **Backup Tokens**: Keep 2-3 tokens valid during rotation window

### Remove Hardcoded Tokens from Docs

- ❌ Never commit tokens to Git
- ❌ Never store in `.env` file in repo
- ✅ Use secure vaults (AWS Secrets Manager, HashiCorp Vault, Azure Key Vault)
- ✅ Use environment variables set by deployment platform
- ✅ Rotate tokens on a schedule

---

## 📊 Rate Limiting Validation

### Verify Rate Limit Configuration

```bash
#!/bin/bash
# scripts/validate_rate_limits.sh

API_URL="https://api.example.com/v1"
TOKEN="<admin-token>"

echo "Validating rate limit configuration..."

# Check that RATE_LIMIT_MODE=prod in health endpoint
curl -s -H "Authorization: Bearer $TOKEN" "$API_URL/health/startup" | \
  jq '.environment.rate_limit_mode' | grep -q "prod" || {
  echo "❌ RATE_LIMIT_MODE is not set to 'prod'"
  exit 1
}

# Check rate limit headers present
HEADERS=$(curl -s -I -H "Authorization: Bearer $TOKEN" \
  "$API_URL/agents/sessions")
echo "$HEADERS" | grep -q "RateLimit-Limit" || {
  echo "❌ RateLimit headers not present"
  exit 1
}

# Check actual rate limit values
LIMIT=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "$API_URL/agents/sessions" | \
  grep -i "RateLimit-Limit" | awk '{print $2}')

if [ "$LIMIT" -lt 50 ]; then
  echo "⚠️  Rate limit suspiciously low: $LIMIT/min"
fi

echo "✅ Rate limit configuration validated"
echo "   - Mode: prod"
echo "   - Limit: $LIMIT requests/minute"
```

---

## 🔄 Rollback Procedures

### Quick Rollback (Within 5 minutes)

```bash
#!/bin/bash
# scripts/rollback.sh REVISION

REVISION=${1:-previous}  # or specific Git SHA

echo "Rolling back to: $REVISION"

# 1. Stop current deployment
kubectl set image deployment/cineca-agents-api \
  cineca-agents-api=cineca-agents:$REVISION

# 2. Wait for rollout
kubectl rollout status deployment/cineca-agents-api

# 3. Verify health
sleep 10
./scripts/validate_production_deployment.sh
```

### Database Rollback (if migrations failed)

```bash
#!/bin/bash
# scripts/rollback_database.sh REVISION

REVISION=${1:-previous}

echo "Rolling back database to: $REVISION"

# Using Alembic
alembic downgrade $REVISION

# Verify connectivity
psql $DATABASE_URL -c "SELECT 1;" || exit 1

echo "✅ Database rolled back"
```

### Cache Flush (if cache corruption suspected)

```bash
#!/bin/bash
# scripts/flush_cache.sh

echo "⚠️  Flushing Redis cache (will clear sessions, cache, rate limits)"
redis-cli -u $REDIS_URL FLUSHDB

echo "✅ Cache flushed. Restart API pods for full recovery."
```

---

## 🚨 Incident Response Workflow

### Incident Severity Levels

**🔴 CRITICAL** (< 30 min SLA)
- API completely down
- Data corruption detected
- Security breach suspected
- Database unreachable

**🟠 HIGH** (< 2 hour SLA)
- Rate limiting not working
- Authentication failing for some users
- Performance degradation (> 50% increase in latency)

**🟡 MEDIUM** (< 4 hour SLA)
- Specific endpoint slow
- Minor feature broken
- Documentation errors

### Incident Triage

1. **Identify Severity**: Which of the above?
2. **Check Basics**:
   ```bash
   # Health check
   curl -s https://api.example.com/v1/health
   
   # Pod logs
   kubectl logs -f deployment/cineca-agents-api --tail=100
   
   # Database connectivity
   psql $DATABASE_URL -c "SELECT 1;"
   
   # Cache connectivity
   redis-cli -u $REDIS_URL ping
   ```
3. **Gather Context**:
   - When did it start?
   - Which endpoints affected?
   - Error patterns in logs?
   - Recent deployments?
4. **Execute Escalation Path** (see below)

### Escalation Path

```
Incident Detected
    ↓
[SEV-CRITICAL] → Immediate Rollback (go/no-go decision in 5 min)
    ↓
[SEV-HIGH] → Debug (15 min) → Fix | Rollback
    ↓
[SEV-MEDIUM] → Post-incident, fix in next sprint
```

### Common Issues & Fixes

#### Issue: "rate limit exceeded" on first request

**Cause**: `RATE_LIMIT_MODE=test` left in production  
**Fix**:
```bash
kubectl set env deployment/cineca-agents-api RATE_LIMIT_MODE=prod
kubectl rollout status deployment/cineca-agents-api
```

#### Issue: "database connection refused"

**Cause**: Connection pool exhausted or DB down  
**Fix**:
```bash
# Check DB connectivity from pod
kubectl exec -it <pod> -- psql $DATABASE_URL -c "SELECT 1;"

# Increase pool size
kubectl set env deployment/cineca-agents-api DATABASE_POOL_SIZE=30

# If DB down, contact database team
```

#### Issue: "idempotency key collision" errors

**Cause**: Redis cache corruption or clock skew  
**Fix**:
```bash
# Flush idempotency cache only
redis-cli -u $REDIS_URL DEL idem:*

# Verify clock sync
kubectl exec -it <pod> -- date
```

#### Issue: "authentication failed" for valid tokens

**Cause**: Auth0 key rotation or network issue  
**Fix**:
```bash
# Verify JWT key is current
curl -s https://$AUTH0_DOMAIN/.well-known/jwks.json | jq .

# Test token validity
curl -s -H "Authorization: Bearer $TOKEN" \
  https://api.example.com/v1/user/me

# If 401, token expired or not valid for this API
```

---

## 📈 Monitoring & Alerting

### Critical Metrics to Monitor

```prometheus
# Error rate should be < 0.1%
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Response latency p99 should be < 1s
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Active connections should be < 50% of pool
db_connections_active / db_connections_max

# Cache hit rate should be > 80%
redis_hits / (redis_hits + redis_misses)

# Rate limit rejections should be 0 (unless under attack)
rate(rate_limit_rejected_requests_total[1m])
```

### Alert Rules (Prometheus)

```yaml
groups:
  - name: cineca-agents
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.01
        for: 5m
        annotations:
          summary: "High error rate detected"

      - alert: HighLatency
        expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 2
        for: 5m
        annotations:
          summary: "High latency detected"

      - alert: DatabaseConnectionPoolExhausted
        expr: db_connections_active >= db_connections_max * 0.9
        for: 2m
        annotations:
          summary: "Database connection pool nearly exhausted"

      - alert: CacheDown
        expr: redis_up == 0
        for: 1m
        annotations:
          summary: "Cache (Redis) is down"
```

### Logging Best Practices

- **Structured Logging**: All logs in JSON format
- **Correlation IDs**: Every log entry includes X-Request-Id
- **Log Levels**: 
  - DEBUG: Development only
  - INFO: Normal operations
  - WARNING: Recoverable errors
  - ERROR: Unrecoverable errors (investigate)
- **Retention**: Keep 30 days in hot storage, 1 year archived
- **Search**: Tag logs by: endpoint, user_id, session_id, error_code

---

## ✅ Pre-Deployment Checklist

### 24 Hours Before Deployment

- [ ] All smoke tests pass locally
- [ ] All integration tests pass (27/27)
- [ ] All auth tests pass (8/8)
- [ ] No hardcoded secrets in code
- [ ] Documentation up to date
- [ ] Incident response team briefed
- [ ] Rollback procedures tested
- [ ] Staging environment validated

### 1 Hour Before Deployment

- [ ] All services healthy (kubectl get pods)
- [ ] Database accessible and responsive
- [ ] Cache (Redis) accessible
- [ ] All dependent services running
- [ ] Team on standby for issues
- [ ] Slack channel open for notifications

### Deployment Steps

1. Deploy to staging first (canary deployment)
2. Run smoke tests in staging
3. Get approval from tech lead
4. Deploy to production (rolling update)
5. Monitor error rate for 15 minutes
6. If stable, deployment complete
7. If issues, activate rollback procedures

### Post-Deployment Validation

- [ ] Health endpoints all return 200 OK
- [ ] Smoke test suite passes (all 8 tests)
- [ ] Error rate normal (< 0.1%)
- [ ] Latency normal (p99 < 1s)
- [ ] Rate limits working (< 10 rejections/min)
- [ ] Idempotency working (replays return 201)
- [ ] Authentication working (all token types)
- [ ] Monitoring dashboards show green

---

## 📞 Contacts & Escalation

| Role | Name | Email | On-Call |
|------|------|-------|----------|
| Deployment Lead | [To Be Filled] | - | TBD |
| Database Lead | [To Be Filled] | - | TBD |
| Security Lead | [To Be Filled] | - | TBD |
| Operations Lead | [To Be Filled] | - | TBD |

### Escalation Path

1. **API Down**: Deployment Lead → Operations Lead
2. **Database Issue**: Database Lead → Infrastructure Team
3. **Security Concern**: Security Lead → CISO
4. **Unknown Issue**: Start with logs, escalate if unresolved in 15 min

---

## 📝 Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Oct 20, 2025 | Initial production readiness guide |

---

**IMPORTANT**: This guide must be reviewed and approved by all stakeholders before first production deployment.
