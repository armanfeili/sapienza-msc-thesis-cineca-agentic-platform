# Disaster Recovery Runbook

**Last Updated**: December 2024

**RTO (Recovery Time Objective)**: 4 hours
**RPO (Recovery Point Objective)**: 1 hour

## Overview

This runbook guides recovery of the Cineca Agentic Platform from catastrophic failures including:
- Complete data center outage
- Database corruption
- Accidental data deletion
- Security breach requiring clean rebuild
- Infrastructure failure (Kubernetes cluster, cloud region)

## Pre-Requisites

### Required Access
- [ ] AWS/Cloud provider admin access
- [ ] Kubernetes cluster admin (kubectl, helm)
- [ ] Database credentials (Postgres, Redis, Memgraph)
- [ ] S3 bucket access (backup storage)
- [ ] DNS management access
- [ ] Secrets management (Vault, AWS Secrets Manager)

### Required Tools
```bash
# Install required tools
brew install postgresql redis awscli kubectl helm

# Verify tool versions
psql --version        # PostgreSQL 14+
redis-cli --version   # Redis 6+
aws --version         # AWS CLI 2+
kubectl version       # Kubernetes 1.24+
```

### Backup Verification
```bash
# List available backups
aws s3 ls s3://cineca-backups/prod/

# Download latest backups
aws s3 sync s3://cineca-backups/prod/ ./dr-restore/ --exclude "*" --include "*$(date +%Y%m%d)*"

# Verify backup integrity
gunzip -t dr-restore/postgres_*.sql.gz
gunzip -t dr-restore/redis_*.rdb.gz
tar -tzf dr-restore/memgraph_*.tar.gz
```

## Recovery Scenarios

### Scenario 1: Database Corruption (Postgres)

**Symptoms**: Query errors, data inconsistency, unable to connect

**Recovery Steps**:

1. **Assess Damage** (5 min)
```bash
# Check PostgreSQL logs
kubectl logs -n cineca-platform deployment/postgres --tail=100

# Attempt connection
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT version();"

# Check data integrity
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT pg_database_size('cineca_control');"
```

2. **Stop Application** (5 min)
```bash
# Scale down app pods to prevent writes
kubectl scale deployment/api-server --replicas=0 -n cineca-platform
kubectl scale deployment/orchestrator --replicas=0 -n cineca-platform

# Verify no connections
psql -h $POSTGRES_HOST -U $POSTGRES_USER -c "SELECT count(*) FROM pg_stat_activity WHERE datname='cineca_control';"
```

3. **Restore from Backup** (30-60 min)
```bash
# Download latest backup
export BACKUP_DATE=$(date +%Y%m%d)
aws s3 cp s3://cineca-backups/prod/postgres_${BACKUP_DATE}_*.sql.gz ./

# Drop and recreate database (DESTRUCTIVE!)
psql -h $POSTGRES_HOST -U $POSTGRES_USER -c "DROP DATABASE IF EXISTS cineca_control;"
psql -h $POSTGRES_HOST -U $POSTGRES_USER -c "CREATE DATABASE cineca_control;"

# Restore backup
gunzip -c postgres_${BACKUP_DATE}_*.sql.gz | psql -h $POSTGRES_HOST -U $POSTGRES_USER -d cineca_control

# Verify restoration
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d cineca_control -c "SELECT COUNT(*) FROM users;"
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d cineca_control -c "SELECT COUNT(*) FROM agent_runs;"
```

4. **Restart Application** (10 min)
```bash
# Scale up pods
kubectl scale deployment/api-server --replicas=3 -n cineca-platform
kubectl scale deployment/orchestrator --replicas=2 -n cineca-platform

# Wait for healthy
kubectl wait --for=condition=ready pod -l app=api-server -n cineca-platform --timeout=300s

# Smoke test
curl -f https://api.cineca-platform.io/health
```

5. **Verify Recovery** (10 min)
```bash
# Check data
curl -H "Authorization: Bearer $TOKEN" https://api.cineca-platform.io/api/v1/agents | jq '.count'

# Check recent activity
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d cineca_control -c \
  "SELECT created_at FROM agent_runs ORDER BY created_at DESC LIMIT 1;"

# Run integration test
pytest tests/integration/test_end_to_end.py -v
```

**Expected Recovery Time**: 60-90 minutes
**Data Loss**: Up to 1 hour (RPO)

---

### Scenario 2: Redis Cache Loss

**Symptoms**: Slow performance, cache misses, session loss

**Recovery Steps**:

1. **Assess Impact** (5 min)
```bash
# Check Redis status
redis-cli -h $REDIS_HOST PING

# Check key count
redis-cli -h $REDIS_HOST DBSIZE

# Check memory usage
redis-cli -h $REDIS_HOST INFO memory
```

2. **Restore from Backup** (10 min)
```bash
# Download latest backup
aws s3 cp s3://cineca-backups/prod/redis_$(date +%Y%m%d)_*.rdb.gz ./

# Stop Redis
kubectl scale deployment/redis --replicas=0 -n cineca-platform

# Restore RDB file (in Redis pod)
kubectl cp redis_*.rdb.gz cineca-platform/redis-0:/data/dump.rdb.gz
kubectl exec -n cineca-platform redis-0 -- gunzip -f /data/dump.rdb.gz

# Restart Redis
kubectl scale deployment/redis --replicas=1 -n cineca-platform
```

3. **Warm Cache** (15 min)
```bash
# Trigger cache warming
curl -X POST https://api.cineca-platform.io/admin/cache/warm

# Verify cache population
redis-cli -h $REDIS_HOST DBSIZE
```

**Expected Recovery Time**: 30 minutes
**Data Loss**: Cache data (non-critical), sessions invalidated

---

### Scenario 3: Complete Infrastructure Loss

**Symptoms**: Entire Kubernetes cluster unavailable, data center outage

**Recovery Steps**:

1. **Provision New Infrastructure** (60 min)
```bash
# Clone infrastructure repo
git clone https://github.com/cineca-platform/infrastructure.git
cd infrastructure

# Provision new cluster (Terraform/Pulumi)
terraform init
terraform plan -var="region=us-west-2" -var="environment=dr"
terraform apply -auto-approve

# Configure kubectl
aws eks update-kubeconfig --name cineca-platform-dr --region us-west-2
```

2. **Deploy Base Services** (30 min)
```bash
# Install cert-manager, ingress-nginx
helm install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace
helm install ingress-nginx ingress-nginx/ingress-nginx --namespace ingress-nginx --create-namespace

# Deploy databases
helm install postgres bitnami/postgresql -n cineca-platform --create-namespace
helm install redis bitnami/redis -n cineca-platform
helm install memgraph memgraph/memgraph -n cineca-platform
```

3. **Restore Data** (60 min)
```bash
# Restore Postgres
./ops/backup/restore.sh --type postgres --file dr-restore/postgres_latest.sql.gz

# Restore Redis
./ops/backup/restore.sh --type redis --file dr-restore/redis_latest.rdb.gz

# Restore Memgraph
./ops/backup/restore.sh --type memgraph --file dr-restore/memgraph_latest.tar.gz
```

4. **Deploy Application** (30 min)
```bash
# Deploy via Helm
helm install cineca-platform ./helm/cineca-platform \
  --namespace cineca-platform \
  --values values.prod.yaml \
  --set image.tag=v1.2.3

# Wait for rollout
kubectl rollout status deployment/api-server -n cineca-platform
kubectl rollout status deployment/orchestrator -n cineca-platform
```

5. **Update DNS** (15 min)
```bash
# Get load balancer IP
kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Update DNS A record (via AWS Route53, Cloudflare, etc.)
aws route53 change-resource-record-sets --hosted-zone-id Z1234 --change-batch '{
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "api.cineca-platform.io",
      "Type": "A",
      "TTL": 60,
      "ResourceRecords": [{"Value": "<NEW_IP>"}]
    }
  }]
}'
```

6. **Verify Service** (15 min)
```bash
# Health check
curl https://api.cineca-platform.io/health

# Smoke test
curl -H "Authorization: Bearer $TOKEN" https://api.cineca-platform.io/api/v1/agents

# Run full test suite
pytest tests/integration/ -v
```

**Expected Recovery Time**: 3-4 hours
**Data Loss**: Up to 1 hour (RPO)

---

## Periodic DR Drills

### Quarterly Drill Schedule

| Quarter | Drill Type | Scope | Duration |
|---------|------------|-------|----------|
| Q1 | Database restore | Postgres only | 1 hour |
| Q2 | Cache restore | Redis only | 30 min |
| Q3 | Full DR | All databases + app | 4 hours |
| Q4 | Chaos engineering | Random failures | 2 hours |

### DR Drill Checklist

**Pre-Drill**:
- [ ] Notify team (Slack, email)
- [ ] Create isolated test environment
- [ ] Download recent backups
- [ ] Verify backup integrity
- [ ] Document baseline (RTO/RPO targets)

**During Drill**:
- [ ] Follow runbook steps
- [ ] Time each phase
- [ ] Document blockers
- [ ] Screenshot errors
- [ ] Test monitoring/alerting

**Post-Drill**:
- [ ] Calculate actual RTO/RPO
- [ ] Compare to targets
- [ ] Document lessons learned
- [ ] Update runbook
- [ ] Schedule remediation work

### Automated DR Drill

```bash
# Run automated DR drill (non-destructive)
./ops/backup/dr-drill.sh --environment=staging --verify-only
```

See `ops/backup/dr-drill.sh` for automated drill script.

---

## Backup Verification

### Daily Verification (Automated)
```bash
# Cron job (run daily at 2 AM)
0 2 * * * /opt/cineca/ops/backup/verify-backups.sh >> /var/log/backup-verify.log 2>&1
```

### Manual Verification
```bash
# List recent backups
aws s3 ls s3://cineca-backups/prod/ --recursive | grep $(date +%Y%m%d)

# Download and test restore
./ops/backup/backup.sh --type all
./ops/backup/restore.sh --type postgres --file /var/backups/cineca-platform/postgres_latest.sql.gz
```

---

## Escalation Path

| Severity | Contact | Response Time |
|----------|---------|---------------|
| P1 (Critical) | On-call engineer + Manager | 15 min |
| P2 (High) | On-call engineer | 1 hour |
| P3 (Medium) | Team Slack channel | 4 hours |
| P4 (Low) | Ticket queue | 24 hours |

**On-Call Rotation**: ops-oncall@cineca-platform.io

**PagerDuty**: https://cineca-platform.pagerduty.com

---

## Success Criteria

### RTO Compliance
- [ ] Postgres restore: < 60 min
- [ ] Redis restore: < 30 min
- [ ] Memgraph restore: < 45 min
- [ ] Full infrastructure: < 4 hours

### RPO Compliance
- [ ] Data loss: < 1 hour
- [ ] Backup frequency: Every 1 hour
- [ ] Backup retention: 30 days

### DR Drill Success
- [ ] Completed within RTO
- [ ] Data verified post-restore
- [ ] Application functional
- [ ] Zero manual intervention
- [ ] Runbook accurate

---

## Post-Recovery Verification

```bash
# Run comprehensive verification
./ops/backup/verify-recovery.sh

# Checklist:
# - [ ] All services healthy (kubectl get pods -n cineca-platform)
# - [ ] Database row counts match
# - [ ] API endpoints responding
# - [ ] Integration tests passing
# - [ ] Monitoring shows green
# - [ ] No error spikes in logs
# - [ ] User authentication working
# - [ ] Agent runs completing
```

---

## Continuous Improvement

### Quarterly Review
- Analyze drill results
- Update RTO/RPO targets
- Identify automation gaps
- Train new team members
- Test new backup locations

### Metrics to Track
- Time to detect failure
- Time to start recovery
- Time to restore data
- Time to verify recovery
- Total downtime

---

## References

- [Backup Scripts](./ops/backup/)
- [Infrastructure as Code](https://github.com/cineca-platform/infrastructure)
- [Monitoring Dashboards](https://grafana.cineca-platform.io)
- [Incident Management](https://confluence.cineca-platform.io/incidents)
