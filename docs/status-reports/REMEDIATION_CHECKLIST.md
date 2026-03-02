# Remediation Checklist - Prioritized Actions

**Status**: Production readiness work to complete  
**Timeline**: 8-10 hours focused effort  
**Target**: Production-ready by end of Week 1

---

## 🔴 CRITICAL - BLOCKING (Must fix before any deployment)

### Task 1: Fix Idempotency Replay Status Codes

**Time Estimate**: 2-3 hours  
**Complexity**: Medium (schema change required)  
**Risk**: Low (isolated change)  
**Owner**: Backend Lead

**Acceptance Criteria**:

- [ ] Cached idempotency replays return original status code (201 for creates, 200 for updates)
- [ ] `Idempotency-Replayed: true` header still present
- [ ] Response body identical to original request
- [ ] Test `test_idempotent_session_creation` asserts replay status is 201
- [ ] New test covers all status codes (201, 200, 204, 4xx)

**Implementation Notes**:

Current problem:
```
File: src/middleware/idempotency.py
return Response(body, status_code=200)  # ❌ Wrong
```

Fix:
```
return Response(body, status_code=original_status_code)  # ✅
```

**Blocking**: ✅ YES - RFC 7231 compliance  
**Dependencies**: None

---

### Task 2: Create Production Operations Runbook

**Time Estimate**: 4-6 hours  
**Complexity**: Medium (documentation + scripting)  
**Risk**: Low (informational)  
**Owner**: DevOps Lead + Tech Writer

**Acceptance Criteria**:

- [ ] Document in `docs/PROD_READINESS.md`
- [ ] Includes all required environment variables with examples
- [ ] Health endpoints documented: startup, live, ready
- [ ] Smoke test suite provided (5-6 curl commands)
- [ ] Rate limiting validation steps included
- [ ] Rollback procedure documented
- [ ] Monitoring checklist included
- [ ] Incident response workflow documented

**Deliverables**:

- `docs/PROD_READINESS.md` (checklist + smoke tests)
- `scripts/validate_production_deployment.sh` (automated checks)
- `.env.example` with all production variables
- `docs/INCIDENT_RESPONSE.md` (triage & escalation)

**Blocking**: ✅ YES - Operational risk  
**Dependencies**: None

---

## 🟠 HIGH PRIORITY (Complete this week)

### Task 3: Rotate Auth0 Tokens (Expiring Oct 19)

**Time Estimate**: 1 hour  
**Complexity**: Low  
**Risk**: Medium (new tokens need testing)  
**Owner**: Security Lead

**Acceptance Criteria**:

- [ ] New admin token fetched & validated
- [ ] New user token fetched & validated
- [ ] Tokens have 30+ day expiration
- [ ] Tested: curl with new admin token → 200 OK on /v1/user/me
- [ ] Tested: curl with new user token → 200 OK on /v1/user/me
- [ ] Remove hardcoded tokens from docs
- [ ] Add `scripts/fetch_fresh_tokens.sh` for future rotation

**Blocking**: ✅ YES - Testing will fail with expired tokens  
**Dependencies**: Auth0 account access

---

## 📋 VERIFICATION CHECKLIST

### Before Production Deployment

- [ ] All critical tasks complete & tested
- [ ] All high-priority tasks complete
- [ ] Health endpoint returns rate limit mode
- [ ] Smoke test suite passes
- [ ] All RBAC tests pass
- [ ] All agent tests pass
- [ ] Idempotency tests verify replay status codes
- [ ] No hardcoded tokens in docs or code
- [ ] Production manifests reviewed
- [ ] Ops team trained on runbook
- [ ] Incident response plan reviewed

---

**Last Updated**: October 19, 2025  
**Next Review**: Daily standup until all critical tasks complete
