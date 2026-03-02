# Cineca Agentic Platform - Operator Runbook

**Quick reference guide for platform operators and SREs**

Version: 1.0.0  
Last Updated: October 30, 2025

---

## 🎯 Overview

This runbook covers common operational tasks for the Cineca Agentic Platform:
- Starting/stopping services
- Setting defaults (providers, models)
- Checking system health
- Managing processes
- Rotating tokens and secrets
- Troubleshooting common issues

**Audience:** Platform operators, SREs, DevOps engineers

---

## 🚀 Quick Start Checklist

### First-Time Setup

- [ ] Clone repository
- [ ] Configure `.env` with Auth0 credentials
- [ ] Start all services: `docker compose up -d`
- [ ] Verify health: `docker compose ps` (all should be `Up (healthy)`)
- [ ] Access UI: http://localhost:8501
- [ ] Login as admin
- [ ] Set default provider (see [Set Defaults](#set-defaults))
- [ ] Set default model instance (see [Set Defaults](#set-defaults))
- [ ] Test agent run (may return demo mode - expected until orchestrator implemented)
- [ ] Test NL→Cypher (should work fully)

---

## 📋 Daily Operations

### Check System Health

**Via API:**
```bash
curl http://localhost:8000/v1/health/live
# Expected: "ok"

curl http://localhost:8000/v1/health/components | jq '.checks | to_entries[] | {component: .key, ok: .value.ok, status: .value.status}'
```

**Expected Output:**
```json
{"component": "app", "ok": true, "status": "ok"}
{"component": "postgres", "ok": true, "status": "ok"}
{"component": "redis", "ok": true, "status": "ok"}
{"component": "memgraph", "ok": true, "status": "ok"}
{"component": "providers", "ok": true, "status": "ok"}
{"component": "workers", "ok": true, "status": "ok"}
```

**⚠️ Known Issue:** Health checks may report `"ok": false` with `"status": "error"` due to strict 2.5s timeout, but services still function. Verify functionality:

```bash
# Test Postgres (via DB counts)
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/db/counts
# Should return: {"ok": true, "nodes": 1234, "edges": 5678}

# Test Ollama
curl http://localhost:11434/api/tags | jq '.models[0]'
# Should list models

# Test Memgraph (via Cypher)
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/tools/graph.schema
# Should return schema
```

**Via UI:**
1. Navigate to **Dashboard** tab
2. Check health cards (all should be green or yellow)
3. If Memgraph shows ❌, DB operations will be disabled

---

### View Running Services

```bash
# List all containers
docker compose ps

# Expected services:
# - app (API server)
# - ui (Streamlit UI)
# - postgres (database)
# - redis (cache)
# - memgraph (graph DB)
# - ollama (LLM provider)
# - jobs-worker (background jobs)
# - prometheus (monitoring)
# - grafana (dashboards)

# Check logs
docker compose logs -f app      # API logs
docker compose logs -f ui        # UI logs
docker compose logs -f postgres  # DB logs
docker compose logs -f memgraph  # Graph DB logs
```

---

### Restart Services

**All services:**
```bash
docker compose restart
```

**Specific service:**
```bash
docker compose restart app
docker compose restart ui
docker compose restart memgraph
```

**Full rebuild (after code changes):**
```bash
docker compose down
docker compose up -d --build --remove-orphans
```

---

## ⚙️ Configuration Management

### Set Defaults

**Why:** Agents need default provider and model to run without explicit configuration.

**Set Default Provider:**

```bash
# Via API
curl -X PUT \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider_id": "ollama-local"}' \
  http://localhost:8000/v1/admin/models/providers/default

# Verify
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/models/providers/main
# Should return: {"ok": true, "main": "ollama-local"}
```

**Via UI:**
1. Login as Admin
2. Navigate to **Models** → **Providers**
3. Find `ollama-local` in list
4. Click **Set as Default**
5. Confirm
6. Verify: Dashboard shows "Default Provider: ollama-local"

**Set Default Model Instance:**

```bash
# List available instances
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/models/instances | jq '.items[] | {id: .id, name: .instance_name, enabled: .enabled, loaded: .loaded}'

# Pick one (e.g., llama-3.2-3b with id: 6491b020-bbe3-47fe-991e-e7c21a15260c)

# Set as default
curl -X PATCH \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat": {"instance_id": "6491b020-bbe3-47fe-991e-e7c21a15260c"}}' \
  http://localhost:8000/v1/models/defaults

# Verify
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/models/defaults
# Should return: {"chat": {"instance_id": "...", "name": "llama-3.2-3b", ...}}
```

**Via UI:**
1. Navigate to **Models** → **Instances**
2. Find desired model (e.g., `llama-3.2-3b`)
3. Click **Set as Default**
4. Select category: **Chat**
5. Submit
6. Verify: Dashboard shows "Default Instance: llama-3.2-3b"

**Tenant-Scoped Defaults:**

Same steps, but select tenant from dropdown first (UI) or add `?tenant_id=...` (API).

---

### List Active Processes

```bash
# Via API
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/processes | jq '.processes[] | {id: .process_id, artifact: .artifact, status: .status}'

# Via UI
# Navigate to Admin → Processes
# View table of active processes
```

**Stop a Process:**

```bash
# Via API
curl -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/processes/{process_id}/stop

# Via UI
# Admin → Processes → Click "Stop" button → Confirm
```

---

### Manage Model Manifests

**View Built-in Manifests:**

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/models/manifests/builtins | jq '.items[] | {id: .id, version: .version, state: .state}'
```

**Stage a Manifest:**

```bash
# Find a manifest ID from above
export MANIFEST_ID="35bd7cc2-dd51-47c1-a693-f6558aea89e5"

# Stage it
curl -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/models/manifests/builtins/staged/$MANIFEST_ID
```

**Activate Staged Manifest:**

```bash
curl -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/models/manifests/builtins/activations
```

**Via UI:**
1. Navigate to **Admin** → **Manifests**
2. View **Built-in Manifests** table
3. Click **Stage** on desired manifest
4. Click **Activate Staged** to apply
5. View history timeline

---

## 🔐 Security Operations

### Rotate Auth0 Tokens

**Fetch New Tokens:**

```bash
# Run script
chmod +x scripts/fetch_auth0_tokens.sh
./scripts/fetch_auth0_tokens.sh

# Outputs three tokens:
# - Admin Token (expires in 24h)
# - User Token (expires in 24h)
# - Machine Token (expires in 24h)
```

**Update Environment:**

```bash
# Export to shell
export AUTH0_ADMIN_TOKEN='eyJhbGci...'
export AUTH0_USER_TOKEN='eyJhbGci...'
export AUTH0_MACHINE_TOKEN='eyJhbGci...'

# Or update .env file
echo "AUTH0_ADMIN_TOKEN=eyJhbGci..." >> .env
```

**Verify Tokens:**

```bash
# Check admin token
curl -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  http://localhost:8000/v1/auth/me | jq '.scopes'
# Should include: ["user:me", "tools:invoke:all", "admin:all"]

# Check user token
curl -H "Authorization: Bearer $AUTH0_USER_TOKEN" \
  http://localhost:8000/v1/auth/me | jq '.scopes'
# Should include: ["user:me", "tools:invoke:basic"]
```

**Via UI:**
1. Click **Logout Admin** (or Logout User)
2. Click **Login Admin** (or Login User)
3. Complete Auth0 flow
4. Token auto-saved to session state
5. Verify in header badge: Shows expiry countdown

---

### Rotate Secrets (Pre-Production)

**⚠️ CRITICAL:** Before production deployment, rotate all development secrets:

1. **Auth0 Client Secrets:**
   - Go to Auth0 Dashboard → Applications
   - Rotate client secrets for:
     - User client (Password Grant)
     - Machine client (Client Credentials)
   - Update `.env` with new secrets

2. **Database Passwords:**
   ```bash
   # Update in .env
   DB_PASSWORD='new-secure-password-$(openssl rand -base64 32)'
   
   # Restart services
   docker compose down
   docker compose up -d
   ```

3. **Redis Password (if enabled):**
   ```bash
   # Update in docker-compose.yml and .env
   REDIS_PASSWORD='new-redis-password'
   ```

4. **API Keys (if any):**
   - Review all third-party integrations
   - Rotate API keys in provider configs

5. **Verify No Plaintext Secrets in Logs:**
   ```bash
   # Search logs for leaked secrets
   docker compose logs | grep -i "client_secret\|password\|token" | grep -v "Bearer <REDACTED>"
   # Should find nothing (tokens should be masked)
   ```

---

## 🔧 Troubleshooting

### Service Won't Start

**Symptom:** `docker compose up -d` fails for a service

**Diagnosis:**
```bash
# Check logs
docker compose logs postgres
docker compose logs memgraph

# Common issues:
# - Port already in use
# - Insufficient disk space
# - Volume mount errors
```

**Solutions:**

**Port conflict:**
```bash
# Find process using port
lsof -i :5432  # Postgres
lsof -i :7687  # Memgraph

# Kill process or change port in docker-compose.yml
```

**Disk space:**
```bash
# Check disk space
df -h

# Clean Docker volumes
docker volume prune
```

**Volume permissions:**
```bash
# Fix permissions
sudo chown -R $USER:$USER ./ops/ollama/models
sudo chown -R $USER:$USER ./db
```

---

### High Memory Usage

**Symptom:** System slow, OOM errors

**Diagnosis:**
```bash
# Check container memory usage
docker stats

# Identify culprit (usually ollama or app)
```

**Solutions:**

**Limit Ollama memory:**
```yaml
# docker-compose.yml
ollama:
  deploy:
    resources:
      limits:
        memory: 4G
```

**Reduce model cache:**
```bash
# Unload unused models
curl -X POST http://localhost:11434/api/delete \
  -d '{"name": "unused-model"}'
```

---

### Memgraph Connection Errors

**Symptom:**
```
ERROR: Failed to connect to Memgraph at memgraph:7687
```

**Diagnosis:**
```bash
# Check Memgraph is running
docker compose ps memgraph

# Check logs
docker compose logs memgraph
```

**Solutions:**

**Restart Memgraph:**
```bash
docker compose restart memgraph

# If persists, clear data and restart
docker compose down memgraph
docker volume rm cineca-agentic-platform_memgraph_data
docker compose up -d memgraph
```

**Re-populate data:**
```bash
docker compose run --rm db-populate
```

---

### Agent Runs Return Demo Mode

**Symptom:**
```json
POST /v1/agent-runs
{"output": "(demo) You said: test", "model": null, "manager": null}
```

**Root Cause:** Backend `src/services/orchestrator` missing `run()` method

**Verification:**
```bash
# Check backend logs
docker compose logs app | grep -i orchestrator
# Look for import errors or "no orchestrator found"
```

**Current Status:** ❌ **Not implemented** (backend gap, not operational issue)

**Workaround:** Use other features (NL→Cypher, tools, sessions, jobs all work)

**Long-term:** Requires backend development - see `docs/UI_FINAL_IMPLEMENTATION_STATUS.md`

---

### UI Shows "Connection Refused"

**Symptom:** UI can't reach API

**Diagnosis:**
```bash
# From UI container, test API
docker exec ui curl http://app:8000/v1/health/live
# Should return "ok"

# Check API is listening
docker exec app netstat -tuln | grep 8000
```

**Solutions:**

**Wrong API_BASE_URL:**
```bash
# For Docker: use service name
API_BASE_URL=http://app:8000

# For host: use localhost
API_BASE_URL=http://localhost:8000
```

**Network issue:**
```bash
# Verify network
docker network ls | grep app-net

# Recreate network
docker compose down
docker compose up -d
```

---

## 📊 Monitoring

### Key Metrics to Watch

**Prometheus:** http://localhost:9090

Queries:
- API latency: `http_request_duration_seconds`
- Error rate: `http_requests_total{status=~"5.."}`
- Active connections: `up{job="app"}`

**Grafana:** http://localhost:3001
- Username: `admin`
- Password: `admin`

Dashboards:
- System Overview
- API Performance
- Database Health

---

### Logs

**View logs:**
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f app

# Last 100 lines
docker compose logs --tail=100 app

# Filter by level
docker compose logs app | grep ERROR
docker compose logs app | grep -i "trace_id"
```

**Log locations (in container):**
- API: `/app/logs/app.log`
- UI: `/app/logs/ui.log`

**Centralized logging (future):**
- Configure FluentBit/Logstash
- Ship to Elasticsearch/Loki
- Dashboard in Kibana/Grafana

---

## 🔄 Backup & Recovery

### Backup

**Postgres:**
```bash
# Backup
docker exec postgres pg_dump -U cineca_user cineca_platform > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20251030.sql | docker exec -i postgres psql -U cineca_user cineca_platform
```

**Memgraph:**
```bash
# Backup (manual)
docker exec memgraph mg_backup --backup-path=/var/lib/memgraph/backup

# Copy to host
docker cp memgraph:/var/lib/memgraph/backup ./memgraph_backup_$(date +%Y%m%d)
```

**Redis:**
```bash
# Trigger save
docker exec redis redis-cli SAVE

# Copy RDB file
docker cp redis:/data/dump.rdb ./redis_backup_$(date +%Y%m%d).rdb
```

---

### Recovery

**From backup:**
```bash
# Stop services
docker compose down

# Restore volumes
docker volume create cineca-agentic-platform_postgres_data
docker run --rm -v cineca-agentic-platform_postgres_data:/data -v $(pwd):/backup alpine sh -c "cd /data && cp -r /backup/postgres_backup/* ."

# Start services
docker compose up -d
```

---

## 📞 Escalation

### Issue Severity Levels

| Level | Description | Response Time | Examples |
|-------|-------------|---------------|----------|
| **P0 - Critical** | Service down, data loss | Immediate | All API 500s, DB corruption |
| **P1 - High** | Degraded performance, partial outage | 1 hour | Memgraph down, slow responses |
| **P2 - Medium** | Non-critical feature broken | 4 hours | Tool invocation fails, UI glitch |
| **P3 - Low** | Minor issue, workaround available | Next business day | Cosmetic bug, docs outdated |

### Escalation Path

1. **Check Runbook:** Review troubleshooting section
2. **Check Logs:** `docker compose logs -f app`
3. **GitHub Issues:** Search for similar issues
4. **Create Issue:** If new, file detailed report
5. **Contact Team:** Via Slack/Email with:
   - Issue description
   - Steps to reproduce
   - Logs/screenshots
   - Environment details

---

## 📚 Reference

### Useful Commands

```bash
# Restart all services
docker compose restart

# View API docs
open http://localhost:8000/v1/docs

# Check API version
curl http://localhost:8000/v1/health/live

# Test auth
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/v1/auth/me

# List models
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/v1/models/instances

# Check defaults
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/v1/models/defaults

# DB counts
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/v1/admin/db/counts
```

### Port Reference

| Service | Port | URL |
|---------|------|-----|
| API | 8000 | http://localhost:8000 |
| UI | 8501 | http://localhost:8501 |
| Postgres | 5432 | postgres://localhost:5432 |
| Redis | 6379 | redis://localhost:6379 |
| Memgraph | 7687, 3000 | bolt://localhost:7687, http://localhost:3000 |
| Ollama | 11434 | http://localhost:11434 |
| Prometheus | 9090 | http://localhost:9090 |
| Grafana | 3001 | http://localhost:3001 |

---

## ✅ Maintenance Checklist

### Daily
- [ ] Check health dashboard (all green/yellow)
- [ ] Review error logs for anomalies
- [ ] Verify backup jobs completed
- [ ] Check disk space (>20% free)

### Weekly
- [ ] Review Grafana dashboards
- [ ] Check for security updates
- [ ] Test agent runs end-to-end
- [ ] Verify token expiry warnings work
- [ ] Review audit logs for suspicious activity

### Monthly
- [ ] Rotate Auth0 tokens (if not auto-renewed)
- [ ] Review and clean old backups
- [ ] Update dependencies (if available)
- [ ] Performance tuning based on metrics
- [ ] Review and update documentation

---

**Last Updated:** October 30, 2025  
**Owner:** Platform Team  
**Review Cycle:** Monthly
