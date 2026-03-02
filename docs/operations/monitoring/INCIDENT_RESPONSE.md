# Incident Response Handbook

**Last Updated**: October 20, 2025  
**Audience**: On-call engineers, SREs, Platform team

---

## 🚨 Critical Incident Response

### When to Activate Critical Response

- **API completely down** (0% availability)
- **Data corruption** detected
- **Security breach** suspected or confirmed
- **All database connections exhausted** (cannot recover)
- **All rate limit checks failing** (bypassed security)

### Critical Incident Immediate Actions (First 5 Minutes)

**DO**:
1. ✅ Page on-call team immediately
2. ✅ Open incident room (Slack channel: #incidents)
3. ✅ Assign Incident Commander (IC)
4. ✅ Document start time and initial observations
5. ✅ Check if this is a **known issue** (see Common Issues section)

**DON'T**:
- ❌ Make emergency code changes without approval
- ❌ Restart services randomly
- ❌ Flush caches without understanding impact
- ❌ Revert commits without investigation

### Critical Incident Decision Tree

```
🚨 CRITICAL INCIDENT
        ↓
Is API responding to ANY request?
    ↙ YES          ↘ NO
    ↓               ↓
Is error rate      Check:
< 5%?         - Pod running?
    ↙ YES      - DB connected?
    ↓          - Cache online?
INVESTIGATE       ↓
(High)        Can you FIX
              in < 15 min?
                ↙ YES  ↘ NO
                ↓       ↓
              FIX      ROLLBACK
              &        (safer)
              VERIFY
```

---

## 🔍 Diagnostic Commands

### Health of All Services

```bash
#!/bin/bash
# Quick health check for all services

echo "=== API Service ===" 
kubectl get deployment cineca-agents-api -o wide

echo "=== Database ===" 
kubectl run psql-check --image=postgres:15 --rm -it -- psql $DATABASE_URL -c "SELECT now();" 2>/dev/null

echo "=== Cache ===" 
kubectl run redis-check --image=redis:7 --rm -it -- redis-cli -u $REDIS_URL ping 2>/dev/null

echo "=== Pod Details ===" 
kubectl describe pod -l app=cineca-agents-api

echo "=== Recent Logs ===" 
kubectl logs -l app=cineca-agents-api --tail=50 --timestamps=true
```

### Detailed Diagnostics for Specific Issues

```bash
# Memory usage
kubectl top pod -l app=cineca-agents-api

# Network connectivity
kubectl exec -it <pod> -- ping db.example.com
kubectl exec -it <pod> -- nc -zv cache.example.com 6379

# Disk space (if applicable)
kubectl exec -it <pod> -- df -h

# Process info
kubectl exec -it <pod> -- ps aux
```

---

## 🔧 Common Issues & Fixes

### Issue 1: "rate limit exceeded" on First Request

**Symptom**: Client gets 429 immediately, even for first request  
**Likely Cause**: `RATE_LIMIT_MODE=test` left in production environment  
**Detection**: Check health endpoint
```bash
curl https://api.example.com/v1/health/startup | jq '.environment.rate_limit_mode'
# Should output: "prod"
```

**Fix**:
```bash
# Option 1: Update environment variable
kubectl set env deployment/cineca-agents-api RATE_LIMIT_MODE=prod
kubectl rollout status deployment/cineca-agents-api

# Option 2: Restart pods (quicker)
kubectl rollout restart deployment/cineca-agents-api
kubectl rollout status deployment/cineca-agents-api

# Verify fix
curl https://api.example.com/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"manager":"auto","tools":[]}'
```

**Time to Fix**: 2-3 minutes  
**Severity**: CRITICAL (all requests fail)  
**Test After**: Run smoke test suite

---

### Issue 2: "database connection refused" or Connection Timeout

**Symptom**: All requests fail with "database error"  
**Likely Cause**: 
- Database service down
- Connection pool exhausted
- Network connectivity broken
- Credentials invalid

**Detection**:
```bash
# Check if DB is running
kubectl get pod -l app=postgresql

# Try connecting directly
kubectl run psql-test --image=postgres:15 --rm -it -- \
  psql "postgresql://user:pass@db.example.com:5432/agents_db" -c "SELECT 1;"

# Check connection pool
kubectl logs -l app=cineca-agents-api | grep -i "connection pool"
```

**Fixes (in order of severity)**:

1. **If DB pod down**: Scale it back up
```bash
kubectl scale deployment postgresql --replicas=1
kubectl rollout status deployment postgresql
```

2. **If connection pool exhausted**: Increase pool size temporarily
```bash
kubectl set env deployment/cineca-agents-api \
  DATABASE_POOL_SIZE=30 \
  DATABASE_POOL_TIMEOUT=60
kubectl rollout restart deployment/cineca-agents-api
```

3. **If network broken**: Check DNS and networking
```bash
# DNS test
kubectl run busybox --image=busybox --rm -it -- \
  nslookup db.example.com

# Network policy check
kubectl describe networkpolicy
```

4. **Last resort**: Rollback to previous version
```bash
./scripts/rollback.sh previous
```

**Time to Fix**: 5-15 minutes  
**Severity**: CRITICAL  
**Test After**: Database connectivity test, then smoke tests

---

### Issue 3: "Idempotency-Key collision" or Cache Errors

**Symptom**: Idempotent requests get unique responses (cache not working)  
**Likely Cause**: 
- Redis cache down
- Cache corruption
- Clock skew between services

**Detection**:
```bash
# Test cache connectivity
kubectl run redis-test --image=redis:7 --rm -it -- \
  redis-cli -u $REDIS_URL ping
# Should output: PONG

# Check for errors in logs
kubectl logs -l app=cineca-agents-api | grep -i "cache\|redis"
```

**Fixes**:

1. **If Redis down**: Restart it
```bash
kubectl rollout restart deployment redis
kubectl rollout status deployment redis
sleep 10
./scripts/validate_production_deployment.sh
```

2. **If cache corrupted**: Flush Redis (WARNING: clears all cache)
```bash
# Option 1: Flush only idempotency keys
kubectl run redis-flush --image=redis:7 --rm -it -- \
  redis-cli -u $REDIS_URL --scan --match 'idem:*' | \
  xargs -L 100 redis-cli -u $REDIS_URL DEL

# Option 2: Full flush (more aggressive)
kubectl run redis-flush --image=redis:7 --rm -it -- \
  redis-cli -u $REDIS_URL FLUSHDB

# Then restart API pods
kubectl rollout restart deployment cineca-agents-api
```

3. **If clock skew suspected**: Check pod clocks
```bash
for pod in $(kubectl get pod -l app=cineca-agents-api -o name); do
  echo "$pod:"
  kubectl exec $pod -- date
done
```

**Time to Fix**: 3-10 minutes  
**Severity**: HIGH  
**Test After**: Idempotency test, cache hit rate metric

---

### Issue 4: "authentication failed" or 401 Unauthorized

**Symptom**: Valid tokens return 401 Unauthorized  
**Likely Cause**: 
- Auth0 key rotation (public key changed)
- Network can't reach Auth0
- Token expired
- Bad Authorization header format

**Detection**:
```bash
# Verify token format
echo $AUTH_TOKEN | jq -R 'split(".") | .[1] | @base64d | fromjson'

# Test token validity against Auth0 directly
curl -H "Authorization: Bearer $AUTH_TOKEN" \
  https://$AUTH0_DOMAIN/userinfo

# Check logs for JWT errors
kubectl logs -l app=cineca-agents-api | grep -i "jwt\|token\|401"
```

**Fixes**:

1. **If JWT keys outdated**: Update from Auth0
```bash
# Fetch fresh JWKS
curl https://$AUTH0_DOMAIN/.well-known/jwks.json > /tmp/fresh_jwks.json

# Update secret
kubectl create secret generic auth0-jwks --from-file=/tmp/fresh_jwks.json \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart pods
kubectl rollout restart deployment cineca-agents-api
```

2. **If can't reach Auth0**: Check network
```bash
# From pod, test connectivity
kubectl exec -it <pod> -- curl https://$AUTH0_DOMAIN/.well-known/jwks.json

# If DNS fails
kubectl exec -it <pod> -- nslookup $AUTH0_DOMAIN
```

3. **If token expired**: Get fresh token
```bash
./scripts/fetch_auth0_tokens.sh
export AUTH_TOKEN=$(cat /tmp/auth0_token)
```

**Time to Fix**: 5-10 minutes  
**Severity**: HIGH  
**Test After**: Test with fresh token, smoke tests

---

### Issue 5: High Error Rate (> 1%)

**Symptom**: Many requests returning 5xx errors  
**Likely Cause**: 
- Out of memory
- Unhandled exception in code
- Cascading failure (timeout chain)
- Resource exhaustion (CPU, disk)

**Detection**:
```bash
# Check error rate
curl https://api.example.com/v1/metrics | grep 'http_requests_total.*status="5'

# Check resource usage
kubectl top pod -l app=cineca-agents-api

# Check for exceptions in logs
kubectl logs -l app=cineca-agents-api --tail=200 | grep -i "error\|exception\|traceback"
```

**Fixes**:

1. **If out of memory**: Increase resources or restart
```bash
# Check memory limits
kubectl get pod -l app=cineca-agents-api -o=custom-columns=NAME:.metadata.name,MEMORY:.spec.containers[0].resources.limits.memory

# Increase limits
kubectl set resources deployment cineca-agents-api \
  --limits=memory=2Gi --requests=memory=1Gi

# Or restart to clear
kubectl rollout restart deployment cineca-agents-api
```

2. **If cascading timeouts**: Increase timeout values
```bash
kubectl set env deployment cineca-agents-api \
  DATABASE_POOL_TIMEOUT=60 \
  MAX_REQUEST_TIMEOUT_SECONDS=300

kubectl rollout restart deployment cineca-agents-api
```

3. **If obvious code bug**: Rollback immediately
```bash
./scripts/rollback.sh previous
```

**Time to Fix**: 5-15 minutes  
**Severity**: CRITICAL  
**Test After**: Error rate metric drops, smoke tests pass

---

### Issue 6: Rate Limiting Not Working (All Requests Pass)

**Symptom**: No 429 responses even after limit exceeded  
**Likely Cause**: 
- Rate limit middleware disabled
- Redis not connected for rate limit tracking
- RATE_LIMIT_MODE set incorrectly

**Detection**:
```bash
# Check if Redis is working
kubectl run redis-test --image=redis:7 --rm -it -- \
  redis-cli -u $REDIS_URL GET 'rl:*' | head

# Check logs for rate limit bypass warnings
kubectl logs -l app=cineca-agents-api | grep -i "rate\|limit\|429"

# Test rate limit directly
for i in {1..150}; do
  curl -s -I https://api.example.com/v1/agents/sessions \
    -H "Authorization: Bearer $TOKEN" | grep RateLimit
done | sort | uniq -c
```

**Fixes**:

1. **Verify RATE_LIMIT_MODE is 'prod'**
```bash
kubectl get env deployment cineca-agents-api | grep RATE_LIMIT_MODE
# Should show: RATE_LIMIT_MODE=prod
```

2. **If Redis not working**: (See Issue 3 Cache Errors)

3. **If middleware disabled**: Check config
```bash
kubectl get configmap cineca-config -o yaml | grep -i "rate"
```

**Time to Fix**: 3-5 minutes  
**Severity**: HIGH (security risk)  
**Test After**: Send 150+ requests, verify 429 responses

---

## 📋 Incident Response Checklist

### During Incident

- [ ] Incident started at: ____________
- [ ] Severity level: [ ] CRITICAL [ ] HIGH [ ] MEDIUM
- [ ] Systems affected: [ ] API [ ] Database [ ] Cache [ ] Auth
- [ ] Estimated impact: _____ requests/minute failing
- [ ] Root cause identified: ____________
- [ ] Fix applied at: ____________
- [ ] Services restored at: ____________

### After Incident

- [ ] Incident duration: _____ minutes
- [ ] User impact: _____ unique users affected
- [ ] Write Root Cause Analysis (RCA)
- [ ] Create tickets for prevention
- [ ] Schedule postmortem within 48 hours
- [ ] Update runbooks with new learnings
- [ ] Communicate with stakeholders

---

## 🚦 Escalation Paths

### If Issue Not Identified in 5 Minutes

```
Page: On-call Lead + Database Lead
Channel: #incidents
Message: "Unidentified issue affecting API. Starting investigation."
```

### If Issue Not Fixed in 15 Minutes

```
Page: Incident Commander + Engineering Lead
Decision Point: Fix or Rollback?
  → If unclear: ROLLBACK (safer)
  → If clear fix < 5 min: Continue fix attempt
```

### If Issue Not Fixed in 30 Minutes

```
Page: Engineering Manager + VP of Engineering
Mandatory: Rollback to last known good version
Action: Schedule postmortem for next day
```

---

## 📝 Template: Incident Report

```markdown
# Incident Report: [Service] [Date]

## Summary
[1-2 sentence description of what happened]

## Timeline
- **[Time]**: Issue detected
- **[Time]**: Root cause identified
- **[Time]**: Fix applied
- **[Time]**: Verified resolved
- **[Time]**: All-clear given

## Impact
- Duration: [X] minutes
- Users Affected: [X]
- Requests Failed: [X]
- Data Lost: [Yes/No]
- Security Risk: [Yes/No]

## Root Cause
[Detailed explanation of what went wrong]

## Resolution
[What actions were taken to fix it]

## Prevention
[Changes to prevent recurrence]

## Action Items
- [ ] [Task] - Owner: [Person]
- [ ] [Task] - Owner: [Person]
- [ ] [Task] - Owner: [Person]

## Postmortem Date
[Scheduled date and time]
```

---

## 🆘 Critical Contacts

| Role | Contact | Availability |
|------|---------|--------------|
| On-Call Engineer | Slack: #oncall | 24/7 |
| Database Team Lead | [Email] | Business hours + on-call |
| Security Team | [Email] | 24/7 (emergencies) |
| Cloud Infrastructure | [Ticket System] | 24/7 support |

**After-Hours Escalation**: 
1. Try automated fixes first (see Common Issues)
2. Page on-call lead via PagerDuty
3. If no response in 5 min, page backup

---

## 📚 Additional Resources

- **Monitoring Dashboard**: https://monitoring.example.com/cineca
- **Log Aggregation**: https://logs.example.com/cineca
- **Status Page**: https://status.example.com
- **Production Runbook**: See `PROD_READINESS.md`

---

**Remember**: In case of doubt, ask for help. It's better to escalate early than to make things worse.
