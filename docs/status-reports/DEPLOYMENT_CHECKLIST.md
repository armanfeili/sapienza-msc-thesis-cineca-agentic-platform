# Internal Operations Endpoints - Deployment Checklist

**Target:** Production deployment of Phase 2 Internal Operations endpoints  
**Status:** ✅ Ready for Staging → Production  
**Version:** v0.1.0-internal-ops-phase2

---

## Pre-Deployment Checklist

### 1. Code Review & Approval

- [ ] **Pull Request Created**
  - Base: `main` ← Compare: `chore/restify-tests-and-docs`
  - URL: https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform/compare
  - Description: Use template from `.github/PULL_REQUEST_TEMPLATE_INTERNAL_OPS.md`

- [ ] **Reviewers Assigned**
  - [ ] Team lead approval
  - [ ] Security team review (RBAC, JWT validation, audit trail)
  - [ ] DevOps team review (deployment process, configuration)

- [ ] **Automated Checks Passing**
  - [ ] All 16 pytest tests passing (4m 9s runtime)
  - [ ] Linting passed
  - [ ] Type checking passed
  - [ ] Security scan passed

- [ ] **Branch Protection Enabled**
  - [ ] Require PR approval before merge
  - [ ] Require status checks to pass
  - [ ] Require up-to-date branches

---

## Secrets & Security Hygiene

### 2. Auth0 M2M Secret Rotation

- [ ] **Rotate Development Secret**
  - [ ] Generate new M2M client secret in Auth0 dashboard
  - [ ] Update CI/CD secrets manager with new secret
  - [ ] Update staging environment variables
  - [ ] Test with new secret in staging
  - [ ] Verify old secret no longer works

- [ ] **Verify Secret Storage**
  - [ ] Secret stored in CI/CD secrets manager ✅
  - [ ] Secret stored in production runtime environment ✅
  - [ ] **NO secrets in `.env` files committed to repo** ⚠️
  - [ ] **NO secrets in docker-compose files** ⚠️
  - [ ] Audit `.env.example` to ensure no real secrets present

### 3. Token Validation Verification

- [ ] **Audience Validation**
  - [ ] API accepts only Access Tokens (not ID tokens)
  - [ ] Audience: `api://cineca-agentic-platform`
  - [ ] Test with ID token → expect 401 Unauthorized

- [ ] **Grant Type Validation**
  - [ ] API accepts only `gty: "client-credentials"` tokens
  - [ ] Test with `gty: "password"` (user token) → expect 403 Forbidden
  - [ ] Test with admin token → expect 403 Forbidden

- [ ] **Issuer Validation**
  - [ ] Issuer: `https://cineca.eu.auth0.com/`
  - [ ] JWKS endpoint accessible: `https://cineca.eu.auth0.com/.well-known/jwks.json`

---

## Configuration Finalization

### 4. Staging Environment Variables

- [ ] **Token Configuration**
  ```bash
  INTERNAL_TOKEN_MAX_TTL_SECONDS=3600  # 1 hour (300-7200s enforced)
  ```

- [ ] **Feature Flags**
  ```bash
  INTERNAL_UI_OVERRIDE_ALLOWED=true  # or false based on policy
  AUTO_START_OVERRIDE_TTL_SECONDS=600  # 10 minutes (60-3600s enforced)
  ```

- [ ] **Database Connections** (from secret manager)
  ```bash
  POSTGRES_DSN=postgresql://user:pass@host:5432/cineca_platform
  REDIS_URL=redis://host:6379/0
  ```

- [ ] **Auth0 Configuration**
  ```bash
  AUTH0_DOMAIN=cineca.eu.auth0.com
  AUTH0_AUDIENCE=api://cineca-agentic-platform
  AUTH0_M2M_CLIENT_ID=<from-secret-manager>
  AUTH0_M2M_CLIENT_SECRET=<from-secret-manager>
  ```

- [ ] **OpenAPI Configuration**
  - [ ] Verify "Servers" base URL: `https://staging.cineca.com`
  - [ ] Update `api/openapi_v1.json` if needed

### 5. Production Environment Variables

- [ ] **Token Configuration** (same as staging)
- [ ] **Feature Flags** (adjust based on policy)
  ```bash
  INTERNAL_UI_OVERRIDE_ALLOWED=false  # Stricter in production
  ```
- [ ] **Database Connections** (from secret manager)
- [ ] **Auth0 Configuration** (from secret manager)
- [ ] **OpenAPI Configuration**
  - [ ] Servers base URL: `https://api.cineca.com`

---

## Database Migration

### 6. PostgreSQL Audit Table

**Staging:**

- [ ] **Backup Database**
  ```bash
  docker compose exec postgres pg_dump -U cineca_user cineca_platform > backup_pre_migration.sql
  ```

- [ ] **Apply Migration**
  ```bash
  docker compose exec -T postgres psql -U cineca_user -d cineca_platform \
    < db/migrations/internal_ops_audit_table.sql
  ```

- [ ] **Verify Table Creation**
  ```sql
  \d internal_ops_events
  -- Should show 14 columns + 7 indexes
  ```

- [ ] **Test Audit Logging**
  ```bash
  # Make a test request
  curl -X POST "https://staging.cineca.com/v1/internal/ops/auto-start-override" \
    -H "Authorization: Bearer $M2M_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"enabled": true, "ttl_seconds": 300}'
  
  # Verify audit entry
  docker compose exec postgres psql -U cineca_user -d cineca_platform \
    -c "SELECT * FROM internal_ops_events ORDER BY created_at DESC LIMIT 1;"
  ```

**Production:**

- [ ] **Backup Database**
- [ ] **Apply Migration** (same script)
- [ ] **Verify Table Creation**
- [ ] **Test Audit Logging**

---

## Sanity Testing (Staging)

### 7. Functional Tests with M2M Token

**Get M2M Token:**
```bash
curl -X POST "https://cineca.eu.auth0.com/oauth/token" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "<M2M_CLIENT_ID>",
    "client_secret": "<M2M_CLIENT_SECRET>",
    "audience": "api://cineca-agentic-platform",
    "grant_type": "client_credentials"
  }'

export M2M_TOKEN="<access_token_from_response>"
```

- [ ] **Test 1: Auto-Start Override**
  ```bash
  curl -X POST "https://staging.cineca.com/v1/internal/ops/auto-start-override" \
    -H "Authorization: Bearer $M2M_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"enabled": true, "ttl_seconds": 300}'
  ```
  - **Expected:** `200 OK`
  - **Response:** `{"enabled": true, "set_by": "<actor>", ...}`

- [ ] **Test 2: Preview Staged**
  ```bash
  curl "https://staging.cineca.com/v1/internal/ops/preview-staged" \
    -H "Authorization: Bearer $M2M_TOKEN"
  ```
  - **Expected:** `200 OK`
  - **Response:** `{"items": [...], "count": N, ...}`

- [ ] **Test 3: DB Counts (Memgraph)**
  ```bash
  curl "https://staging.cineca.com/v1/internal/db/counts" \
    -H "Authorization: Bearer $M2M_TOKEN"
  ```
  - **Expected:** `200 OK` (if Memgraph available) or `501 Not Implemented`
  - **Response (200):** `{"total_tools": N, "total_users": M, ...}`
  - **Response (501):** `{"type": "...", "status": 501, ...}`
  - **Headers (501):** `Retry-After: 60`, `X-Feature: memgraph=unavailable`

- [ ] **Test 4: DB Jobs List**
  ```bash
  curl "https://staging.cineca.com/v1/internal/db/jobs" \
    -H "Authorization: Bearer $M2M_TOKEN"
  ```
  - **Expected:** `200 OK`
  - **Response:** `{"items": [...], "total": N}`

- [ ] **Test 5: Create DB Job**
  ```bash
  curl -X POST "https://staging.cineca.com/v1/internal/db/jobs" \
    -H "Authorization: Bearer $M2M_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"type": "create", "wipe": false}'
  ```
  - **Expected:** `202 Accepted`
  - **Headers:** `Location: /v1/internal/db/jobs/{job_id}`

- [ ] **Test 6: Get Job Status**
  ```bash
  curl "https://staging.cineca.com/v1/internal/db/jobs/{job_id}" \
    -H "Authorization: Bearer $M2M_TOKEN"
  ```
  - **Expected:** `200 OK`
  - **Response:** `{"status": "pending"|"running"|"completed"|"failed", ...}`

### 8. Security Tests (RBAC Enforcement)

- [ ] **Test 7: Admin Token Rejected**
  ```bash
  # Get admin user token (gty: "password", admin:all scope)
  curl "https://staging.cineca.com/v1/internal/ops/preview-staged" \
    -H "Authorization: Bearer $ADMIN_TOKEN"
  ```
  - **Expected:** `403 Forbidden`
  - **Response:** `{"type": "...", "detail": "Access denied", ...}`

- [ ] **Test 8: User Token Rejected**
  ```bash
  # Get regular user token (gty: "password", user:me scope)
  curl "https://staging.cineca.com/v1/internal/ops/preview-staged" \
    -H "Authorization: Bearer $USER_TOKEN"
  ```
  - **Expected:** `403 Forbidden`

- [ ] **Test 9: No Token Rejected**
  ```bash
  curl "https://staging.cineca.com/v1/internal/ops/preview-staged"
  ```
  - **Expected:** `401 Unauthorized`

- [ ] **Test 10: Expired Token Rejected**
  ```bash
  curl "https://staging.cineca.com/v1/internal/ops/preview-staged" \
    -H "Authorization: Bearer <expired-token>"
  ```
  - **Expected:** `401 Unauthorized`

### 9. Observability Tests

- [ ] **Test 11: Headers Present**
  ```bash
  curl -i "https://staging.cineca.com/v1/internal/ops/preview-staged" \
    -H "Authorization: Bearer $M2M_TOKEN"
  ```
  - **Expected Headers:**
    - `X-Request-Id: <uuid>`
    - `X-Correlation-Id: <uuid>`
    - `X-Subject: <actor-sub>`
    - `X-Cache-Status: miss|hit|refresh|none`

- [ ] **Test 12: Audit Entries Created**
  ```sql
  SELECT 
    correlation_id, 
    actor_sub, 
    event_type, 
    operation_result, 
    created_at
  FROM internal_ops_events
  WHERE created_at > NOW() - INTERVAL '10 minutes'
  ORDER BY created_at DESC
  LIMIT 5;
  ```
  - **Expected:** Rows corresponding to recent test requests

- [ ] **Test 13: Logs Include Correlation IDs**
  ```bash
  docker compose logs app | grep -A 5 "X-Correlation-Id"
  ```
  - **Expected:** Log entries with correlation IDs matching response headers

### 10. Performance & Reliability Tests

- [ ] **Test 14: Idempotency (Duplicate Requests)**
  ```bash
  # First request
  curl -X POST "https://staging.cineca.com/v1/internal/ops/auto-start-override" \
    -H "Authorization: Bearer $M2M_TOKEN" \
    -H "X-Idempotency-Key: test-key-001" \
    -H "Content-Type: application/json" \
    -d '{"enabled": true, "ttl_seconds": 300}'
  
  # Duplicate request (within 24h)
  curl -X POST "https://staging.cineca.com/v1/internal/ops/auto-start-override" \
    -H "Authorization: Bearer $M2M_TOKEN" \
    -H "X-Idempotency-Key: test-key-001" \
    -H "Content-Type: application/json" \
    -d '{"enabled": true, "ttl_seconds": 300}'
  ```
  - **Expected:** Both return `200 OK` with same response
  - **Headers:** Second response includes `X-Idempotency-Replayed: true`

- [ ] **Test 15: Cache Coherence (force_refresh)**
  ```bash
  # First request (cache miss)
  curl "https://staging.cineca.com/v1/internal/ops/preview-staged" \
    -H "Authorization: Bearer $M2M_TOKEN"
  
  # Second request (cache hit)
  curl "https://staging.cineca.com/v1/internal/ops/preview-staged" \
    -H "Authorization: Bearer $M2M_TOKEN"
  
  # Third request (force refresh)
  curl "https://staging.cineca.com/v1/internal/ops/preview-staged?force_refresh=true" \
    -H "Authorization: Bearer $M2M_TOKEN"
  ```
  - **Expected Headers:**
    - Request 1: `X-Cache-Status: miss`
    - Request 2: `X-Cache-Status: hit`
    - Request 3: `X-Cache-Status: refresh`

- [ ] **Test 16: Rate Limiting (if enabled)**
  ```bash
  # Send 100 requests in rapid succession
  for i in {1..100}; do
    curl "https://staging.cineca.com/v1/internal/ops/preview-staged" \
      -H "Authorization: Bearer $M2M_TOKEN" -w "%{http_code}\n" -o /dev/null -s
  done
  ```
  - **Expected:** 200 OK for most, possibly 429 Too Many Requests if rate limit hit

---

## Observability & Monitoring

### 11. Logging Verification

- [ ] **Check Application Logs**
  ```bash
  docker compose logs app --tail=100 --follow
  ```
  - [ ] Request/response logging present
  - [ ] Correlation IDs in log entries
  - [ ] Error stack traces for 5xx errors
  - [ ] Performance metrics (request duration)

- [ ] **Check PostgreSQL Audit Table**
  ```sql
  -- Total events today
  SELECT COUNT(*) FROM internal_ops_events 
  WHERE created_at >= CURRENT_DATE;
  
  -- Events by type
  SELECT event_type, COUNT(*) 
  FROM internal_ops_events 
  GROUP BY event_type 
  ORDER BY COUNT(*) DESC;
  
  -- Recent errors
  SELECT * FROM internal_ops_events 
  WHERE operation_result != 'success' 
  ORDER BY created_at DESC 
  LIMIT 10;
  ```

### 12. Alerting Setup

- [ ] **4xx/5xx Surge Alerts**
  - [ ] Alert if error rate > 5% over 5-minute window
  - [ ] Alert if 5xx errors > 10 per minute

- [ ] **Redis Connection Failures**
  - [ ] Alert if Redis unavailable > 1 minute
  - [ ] Alert if cache hit rate < 50% (unexpected)

- [ ] **PostgreSQL Issues**
  - [ ] Alert if database connection failures
  - [ ] Alert if audit table write failures
  - [ ] Alert if `internal_ops_events` table size > 10 GB

- [ ] **Memgraph Unavailability**
  - [ ] Monitor 501 responses from `/v1/internal/db/counts`
  - [ ] Alert if 501 rate > 50% over 10-minute window

---

## CI/CD Pipeline

### 13. Automated Testing

- [ ] **Add CI Job for Pytest**
  ```yaml
  # .github/workflows/test.yml
  test-internal-ops:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run internal ops tests
        run: pytest tests/test_internal_phase2.py -v
  ```

- [ ] **Add Staging Deployment Job**
  ```yaml
  deploy-staging:
    needs: [test-internal-ops]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to staging
        run: |
          # Your deployment script
          ./scripts/deploy.sh staging
  ```

- [ ] **Branch Protection Rules**
  - [ ] Require `test-internal-ops` job to pass before merge
  - [ ] Require manual approval for production deployment

### 14. Deployment Automation

- [ ] **Staging Auto-Deploy on PR Merge**
  - [ ] Trigger: Merge to `main` branch
  - [ ] Action: Deploy to staging environment
  - [ ] Notification: Slack/email on success/failure

- [ ] **Production Manual Deployment**
  - [ ] Require manual approval from team lead
  - [ ] Run smoke tests after deployment
  - [ ] Rollback plan in place

---

## Post-Deployment Monitoring (Staging)

### 15. 24-48 Hour Observation Period

- [ ] **Day 1 Monitoring**
  - [ ] Check error logs every 4 hours
  - [ ] Monitor audit table growth (expect ~100-1000 entries/day)
  - [ ] Verify idempotency cache working (check Redis keys)
  - [ ] Monitor response times (expect < 500ms p95)

- [ ] **Day 2 Monitoring**
  - [ ] Review all audit entries for anomalies
  - [ ] Check cache hit rate (expect > 50% for preview-staged)
  - [ ] Verify no memory leaks (check app container memory)
  - [ ] Confirm no database performance degradation

### 16. Performance Metrics

- [ ] **Response Time Targets**
  - [ ] `/v1/internal/ops/preview-staged`: < 200ms p95 (with cache hit)
  - [ ] `/v1/internal/ops/auto-start-override`: < 100ms p95
  - [ ] `/v1/internal/db/counts`: < 500ms p95 (Memgraph query)
  - [ ] `/v1/internal/db/jobs`: < 150ms p95

- [ ] **Cache Performance**
  - [ ] Hit rate > 50% for preview-staged endpoint
  - [ ] Idempotency replay rate < 5% (most requests unique)

- [ ] **Database Performance**
  - [ ] Audit table writes < 50ms p95
  - [ ] Query performance with 100k+ audit entries

---

## Production Deployment

### 17. Production Readiness Gate

- [ ] **Staging Validation Complete**
  - [ ] All 16 sanity tests passing
  - [ ] 24-48 hour observation period complete
  - [ ] No critical errors or performance issues
  - [ ] Security tests passing (RBAC enforcement)

- [ ] **Stakeholder Approval**
  - [ ] Team lead sign-off
  - [ ] Security team approval
  - [ ] Product owner confirmation

- [ ] **Rollback Plan Prepared**
  - [ ] Database rollback script ready
  - [ ] Previous version tagged and available
  - [ ] Downtime window scheduled (if needed)

### 18. Production Deployment Steps

1. **Pre-Deployment**
   - [ ] Backup production database
   - [ ] Notify stakeholders of deployment window
   - [ ] Verify secrets and environment variables

2. **Deployment**
   - [ ] Apply database migration
   - [ ] Deploy application code
   - [ ] Restart services in rolling fashion

3. **Verification**
   - [ ] Run all 16 sanity tests in production
   - [ ] Verify audit table logging
   - [ ] Check observability headers
   - [ ] Confirm RBAC enforcement

4. **Post-Deployment**
   - [ ] Monitor logs for 2 hours
   - [ ] Check error rates
   - [ ] Notify stakeholders of successful deployment

---

## Post-Merge Housekeeping

### 19. Documentation & Release

- [ ] **Create Git Tag**
  ```bash
  git tag -a v0.1.0-internal-ops-phase2 -m "Phase 2: Internal Operations Endpoints"
  git push origin v0.1.0-internal-ops-phase2
  ```

- [ ] **Create GitHub Release**
  - [ ] Title: `v0.1.0 - Internal Operations Endpoints (Phase 2)`
  - [ ] Description: Summary from PR template
  - [ ] Attach: Migration script, deployment guide

- [ ] **Operations Runbook**
  - [ ] How to get M2M token from Auth0
  - [ ] Common error scenarios and resolutions
  - [ ] How to handle 501 responses (Memgraph unavailable)
  - [ ] Audit table query examples
  - [ ] Incident response procedures

- [ ] **Update OpenAPI Documentation** (Optional)
  - [ ] Add detailed descriptions for all 6 endpoints
  - [ ] Add request/response examples
  - [ ] Document error responses
  - [ ] Add authentication requirements

- [ ] **RFC 7807 Error Audit** (Optional)
  - [ ] Audit all error responses for format consistency
  - [ ] Ensure `type`, `title`, `status`, `detail`, `instance` fields
  - [ ] Standardize error types (e.g., `about:blank#forbidden`)

---

## Success Criteria

### 20. Production Acceptance

- ✅ **Security**
  - [ ] All M2M authentication tests passing
  - [ ] Admin/user tokens properly rejected (403)
  - [ ] No secrets in repository
  - [ ] Token TTL validation working

- ✅ **Reliability**
  - [ ] Idempotency preventing duplicate operations
  - [ ] Cache coherence working (mtime tracking)
  - [ ] Enhanced 501 responses with Retry-After
  - [ ] Error rate < 1%

- ✅ **Observability**
  - [ ] All response headers present (X-Request-Id, etc.)
  - [ ] Audit table logging all operations
  - [ ] Correlation IDs in logs
  - [ ] Performance metrics tracking

- ✅ **Testing**
  - [ ] 16/16 automated tests passing
  - [ ] 16/16 manual sanity tests passing
  - [ ] Security tests passing (RBAC)
  - [ ] Performance tests within targets

- ✅ **Documentation**
  - [ ] Deployment guide complete
  - [ ] API documentation updated
  - [ ] Operations runbook created
  - [ ] Security documentation reviewed

---

## Contact & Support

**Primary Contact:** DevOps Team  
**Security Contact:** Security Team  
**Escalation:** Team Lead

**Documentation:**
- Deployment Guide: `docs/INTERNAL_ENDPOINTS_DEPLOYMENT_READY.md`
- Security Documentation: `docs/INTERNAL_ENDPOINTS_SECURITY.md`
- Phase 2 Summary: `docs/INTERNAL_ENDPOINTS_PHASE2_COMPLETE.md`

**Issue Reporting:** GitHub Issues  
**Incident Response:** See `docs/INTERNAL_ENDPOINTS_SECURITY.md` Section 6

---

**Deployment Status:** 🚀 Ready for Staging  
**Confidence Level:** ✅ High (82% complete, all critical features tested)  
**Estimated Deployment Time:** 2-3 hours (including testing)
