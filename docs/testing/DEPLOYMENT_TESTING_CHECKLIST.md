# Pre-Production Deployment Testing Checklist

## Overview

Comprehensive checklist for testing before production deployment. This ensures all systems are working correctly and the platform is ready for live users.

**Status Key**:
- ✅ Pass
- ⚠️ Warning (non-critical)
- ❌ Fail (blocking)
- ⏭️ Skipped (not applicable)

---

## 1. Infrastructure Testing

### 1.1 Service Health

- [ ] All Docker containers running
  ```bash
  docker compose ps
  # All should be "Up" status
  ```

- [ ] Health endpoints responding
  ```bash
  curl http://localhost:8000/v1/health/live    # Should return 200
  curl http://localhost:8000/v1/health/ready   # Should return 200
  curl http://localhost:8501                    # UI should load
  ```

- [ ] Database connections stable
  ```bash
  curl http://localhost:8000/v1/health/components
  # PostgreSQL, Redis, Memgraph should all be "healthy"
  ```

### 1.2 Resource Limits

- [ ] CPU usage < 70% under normal load
- [ ] Memory usage < 80% under normal load
- [ ] Disk space > 20% free
- [ ] Network latency < 100ms

### 1.3 Networking

- [ ] All required ports accessible
- [ ] SSL/TLS certificates valid
- [ ] Firewall rules configured correctly
- [ ] DNS records pointing to correct endpoints

---

## 2. Security Testing

### 2.1 Authentication & Authorization

- [ ] Admin login works with correct credentials
- [ ] Admin login fails with incorrect credentials
- [ ] User login requires valid credentials
- [ ] Tokens expire after configured time
- [ ] Token refresh works correctly
- [ ] Logout clears all session data

### 2.2 API Security

- [ ] Unauthorized requests return 401
- [ ] Forbidden requests return 403
- [ ] Rate limiting active (test with 100+ requests)
- [ ] CORS headers configured correctly
- [ ] Security headers present (HSTS, CSP, X-Frame-Options)

### 2.3 Data Security

- [ ] Database connections use SSL/TLS
- [ ] Redis connections use TLS
- [ ] Sensitive data encrypted at rest
- [ ] Secrets not exposed in logs
- [ ] API keys properly masked in UI

### 2.4 Security Scan

- [ ] Run container vulnerability scan
  ```bash
  docker scan cineca-agentic-platform-app
  ```

- [ ] Run dependency audit
  ```bash
  pip-audit
  npm audit
  ```

- [ ] Review security audit results
  - No critical vulnerabilities
  - High vulnerabilities addressed or mitigated

---

## 3. Functional Testing

### 3.1 Authentication Flow

- [ ] Admin can log in
- [ ] Admin token has all required scopes
- [ ] User can log in
- [ ] User token has correct scopes
- [ ] Token badge displays correctly in UI
- [ ] Logout works and clears session

### 3.2 Tenant Management

- [ ] Create tenant succeeds
- [ ] List tenants returns all tenants
- [ ] Get tenant by ID returns correct data
- [ ] Update tenant works
- [ ] Delete tenant works (with confirmation)
- [ ] Cascade delete removes all tenant resources

### 3.3 Model Management

- [ ] Create LLM provider succeeds
- [ ] Configure model instance succeeds
- [ ] Set default model works
- [ ] Model test endpoint works
- [ ] List models returns all models
- [ ] Update model configuration works
- [ ] Delete model works

### 3.4 Agent Execution

- [ ] Create agent session succeeds
- [ ] Execute agent with simple prompt works
- [ ] Timeline displays execution steps
- [ ] Agent results displayed correctly
- [ ] Agent error handling works
- [ ] Cancel running agent works

### 3.5 Tool Operations

- [ ] List available tools works
- [ ] Tool documentation displayed
- [ ] Invoke tool with parameters succeeds
- [ ] Tool validation catches invalid parameters
- [ ] Tool results formatted correctly

### 3.6 Job Management

- [ ] Create job succeeds
- [ ] List jobs returns all jobs
- [ ] Get job status works
- [ ] Cancel job works
- [ ] Job idempotency works (same key = same job)

### 3.7 Health Dashboard

- [ ] All components display
- [ ] Component status accurate
- [ ] Latency metrics shown
- [ ] Refresh updates data
- [ ] Error states handled

---

## 4. Performance Testing

### 4.1 Load Testing

- [ ] Run load test with 50 concurrent users
  ```bash
  locust -f tests/performance/locustfile.py --headless -u 50 -r 10 -t 5m
  ```

- [ ] Run load test with 100 concurrent users
- [ ] Run load test with 500 concurrent users (if expected)

**Success Criteria**:
- 95th percentile response time < 1000ms
- Error rate < 1%
- No memory leaks over 30-minute test

### 4.2 Stress Testing

- [ ] Test with maximum concurrent users (capacity test)
- [ ] Test with sustained load over 1 hour
- [ ] Test recovery after spike (2x normal load for 5 minutes)

### 4.3 Performance Metrics

- [ ] API response times < 500ms (p95)
- [ ] UI page load < 3 seconds
- [ ] Database query times < 100ms (p95)
- [ ] Cache hit rate > 80%

---

## 5. Integration Testing

### 5.1 End-to-End Workflows

- [ ] Complete tenant setup workflow
  - Create tenant → Add provider → Configure model → Test execution

- [ ] Complete agent workflow
  - Create session → Execute → Monitor → View results

- [ ] Complete job workflow
  - Create job → Monitor status → Cancel → Verify cancellation

### 5.2 External Integrations

- [ ] Auth0 integration works
- [ ] LLM provider connections work (OpenAI, Anthropic, etc.)
- [ ] Email notifications work (if configured)
- [ ] Webhook deliveries work (if configured)

### 5.3 Database Operations

- [ ] CRUD operations on all entities work
- [ ] Transactions commit correctly
- [ ] Rollbacks work on errors
- [ ] Migrations applied successfully

---

## 6. Backup & Recovery Testing

### 6.1 Backup Creation

- [ ] Manual backup script works
  ```bash
  ./scripts/backup_database.sh
  ```

- [ ] Automated backups configured
- [ ] Backup files created in correct location
- [ ] Backup size reasonable (< 1GB for small deployments)

### 6.2 Restore Testing

- [ ] Restore from latest backup succeeds
  ```bash
  ./scripts/restore_database.sh /path/to/backup.sql
  ```

- [ ] Data integrity verified after restore
- [ ] Application works with restored data

### 6.3 Disaster Recovery

- [ ] Recovery Time Objective (RTO) < 1 hour
- [ ] Recovery Point Objective (RPO) < 24 hours
- [ ] Documented recovery procedures
- [ ] Team trained on recovery process

---

## 7. Monitoring & Alerting

### 7.1 Monitoring Setup

- [ ] Prometheus collecting metrics
- [ ] Grafana dashboards accessible
- [ ] Loki collecting logs
- [ ] AlertManager configured

### 7.2 Metrics Collection

- [ ] Application metrics visible in Grafana
- [ ] System metrics visible (CPU, memory, disk)
- [ ] Custom business metrics tracked
- [ ] Metric retention policy configured

### 7.3 Alerting

- [ ] Critical alerts configured
  - Service down
  - High error rate
  - Database connection failures

- [ ] Warning alerts configured
  - High CPU usage
  - High memory usage
  - Slow response times

- [ ] Alert notifications working
  - Email alerts delivered
  - Slack/Teams notifications (if configured)

- [ ] Alert runbooks documented

---

## 8. Error Handling & Resilience

### 8.1 Error Scenarios

- [ ] API returns proper error codes (400, 404, 500, etc.)
- [ ] Error messages user-friendly
- [ ] Stack traces not exposed to users
- [ ] Errors logged with context

### 8.2 Failure Simulation

- [ ] Stop database → App handles gracefully
- [ ] Stop Redis → App handles gracefully
- [ ] Network timeout → Request fails gracefully
- [ ] Invalid input → Validation errors clear

### 8.3 Circuit Breakers

- [ ] Circuit breakers configured for external services
- [ ] Fallback mechanisms work
- [ ] Auto-recovery after service restoration

---

## 9. Compliance & Documentation

### 9.1 Documentation

- [ ] README.md up to date
- [ ] API documentation complete (OpenAPI)
- [ ] User guide available
- [ ] Deployment guide available
- [ ] Troubleshooting guide available

### 9.2 Compliance

- [ ] GDPR compliance verified (if applicable)
- [ ] Data retention policies documented
- [ ] Audit logging enabled
- [ ] User consent mechanisms in place (if applicable)

### 9.3 Legal

- [ ] Terms of Service available
- [ ] Privacy Policy available
- [ ] License file present
- [ ] Third-party attributions documented

---

## 10. Operational Readiness

### 10.1 Runbooks

- [ ] Deployment runbook available
- [ ] Rollback runbook available
- [ ] Incident response runbook available
- [ ] Maintenance runbook available

### 10.2 Team Readiness

- [ ] Team trained on deployment process
- [ ] On-call rotation configured
- [ ] Escalation procedures documented
- [ ] Contact list up to date

### 10.3 Rollback Plan

- [ ] Previous version tagged
- [ ] Rollback procedure tested
- [ ] Rollback can complete in < 30 minutes
- [ ] Data migration reversible (if applicable)

---

## 11. Pre-Deployment Checklist

### 11.1 Final Verification (1 day before)

- [ ] All tests passing (unit, integration, E2E)
- [ ] No critical bugs open
- [ ] Performance acceptable under load
- [ ] Security scan clean
- [ ] Backup system working

### 11.2 Deployment Day

- [ ] Stakeholders notified
- [ ] Maintenance window scheduled
- [ ] Team available for deployment
- [ ] Communication channels active
- [ ] Rollback plan ready

### 11.3 Post-Deployment (first 24 hours)

- [ ] Monitor error rates
- [ ] Monitor performance metrics
- [ ] Check alert notifications
- [ ] Verify user workflows
- [ ] Collect user feedback

---

## 12. Sign-Off

### Test Execution Summary

| Category | Total Tests | Passed | Failed | Skipped |
|----------|-------------|--------|--------|---------|
| Infrastructure | | | | |
| Security | | | | |
| Functional | | | | |
| Performance | | | | |
| Integration | | | | |
| Backup & Recovery | | | | |
| Monitoring | | | | |
| Error Handling | | | | |
| Compliance | | | | |
| Operational | | | | |
| **TOTAL** | | | | |

### Decision

- [ ] ✅ **APPROVED FOR PRODUCTION** - All critical tests passed
- [ ] ⚠️ **APPROVED WITH WARNINGS** - Non-critical issues documented
- [ ] ❌ **NOT APPROVED** - Critical issues must be resolved

### Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Tech Lead | | | |
| DevOps Engineer | | | |
| QA Lead | | | |
| Product Owner | | | |
| Security Officer | | | |

### Notes

```
[Add any notes, warnings, or special instructions here]
```

---

## 13. Quick Reference

### Critical Commands

```bash
# Check service health
docker compose ps
curl http://localhost:8000/v1/health/ready

# View logs
docker compose logs -f app
docker compose logs -f ui

# Run tests
pytest tests/ -v
npm run test:e2e

# Create backup
./scripts/backup_database.sh

# Restore backup
./scripts/restore_database.sh /path/to/backup.sql

# Deploy
docker compose up -d --build

# Rollback
docker compose down
git checkout <previous-version>
docker compose up -d --build
```

### Emergency Contacts

- **On-Call Engineer**: [Phone/Email]
- **DevOps Lead**: [Phone/Email]
- **Product Owner**: [Phone/Email]
- **Emergency Escalation**: [Phone/Email]

---

**Last Updated**: November 2, 2025  
**Version**: 1.0.0  
**Next Review**: [Date]
