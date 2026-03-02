# Health API Quick Reference

## Canonical Endpoints

| Endpoint | Purpose | Response Type | Kubernetes Use |
|----------|---------|---------------|----------------|
| `GET /v1/health/live` | Process liveness | Plain text `ok` | liveness probe |
| `GET /v1/health/ready` | Service readiness | JSON (all components) | readiness probe |
| `GET /v1/health/startup` | Startup completion | JSON (extended) | startup probe |
| `GET /v1/health/components` | All component status | JSON (all components) | Monitoring |
| `GET /v1/health/components/{name}` | Single component | JSON (one component) | Targeted checks |

## Component Names

| Name | Description | Required for Readiness |
|------|-------------|----------------------|
| `app` | Process runtime | ✅ Yes |
| `postgres` | PostgreSQL database | ✅ Yes |
| `redis` | Redis cache | ✅ Yes |
| `memgraph` | Memgraph graph DB | ❌ No (optional) |
| `providers` | LLM provider registry | ❌ No (optional) |
| `workers` | Background job workers | ❌ No (optional) |
| `ollama` | Ollama LLM service | ℹ️ Informational |
| `prometheus` | Prometheus metrics | ℹ️ Informational |
| `grafana` | Grafana dashboards | ℹ️ Informational |

## Response Format

### Standard Response
```json
{
  "service": "cineca-agentic-platform",
  "version": "0.1.0",
  "status": "ok|degraded|error",
  "time": "2025-01-24T20:00:24.340182Z",
  "checks": {
    "component_name": {
      "ok": true,
      "status": "ok",
      "latency_ms": 5,
      "details": {}
    }
  }
}
```

### Single Component Response
```json
{
  "ok": true,
  "status": "ok",
  "latency_ms": 5,
  "details": {}
}
```

## Status Codes

| Code | Meaning | When |
|------|---------|------|
| 200 | Healthy or degraded (allowed) | Most cases |
| 503 | Service unavailable | Critical component failure |
| 404 | Not found | Invalid component name |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HEALTH_TIMEOUT_MS` | 200 | Default probe timeout |
| `HEALTH_DB_TIMEOUT_MS` | 500 | Database probe timeout |
| `HEALTH_CACHE_TIMEOUT_MS` | 200 | Cache probe timeout |
| `READY_ALLOW_DEGRADED` | true | Allow degraded state in readiness |
| `HEALTH_ENFORCE_MIGRATIONS` | false | Require migrations for startup |

## Example Usage

### Check Overall Health
```bash
curl http://localhost:8000/v1/health/ready | jq '.status'
```

### Check Specific Component
```bash
curl http://localhost:8000/v1/health/components/postgres | jq '.ok'
```

### Kubernetes Liveness Probe
```yaml
livenessProbe:
  httpGet:
    path: /v1/health/live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30
```

### Kubernetes Readiness Probe
```yaml
readinessProbe:
  httpGet:
    path: /v1/health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

### Kubernetes Startup Probe
```yaml
startupProbe:
  httpGet:
    path: /v1/health/startup
    port: 8000
  failureThreshold: 30
  periodSeconds: 10
```

## Common Patterns

### Wait for Service Ready
```bash
until curl -sf http://localhost:8000/v1/health/ready | jq -e '.status == "ok"'; do
  echo "Waiting for service..."
  sleep 2
done
echo "Service ready!"
```

### Check Component Before Operation
```bash
if curl -sf http://localhost:8000/v1/health/components/postgres | jq -e '.ok'; then
  echo "Database is healthy, proceeding..."
else
  echo "Database is down, aborting"
  exit 1
fi
```

### Monitor Degraded State
```bash
# Alert if service degraded for too long
status=$(curl -s http://localhost:8000/v1/health/ready | jq -r '.status')
if [ "$status" = "degraded" ]; then
  echo "WARNING: Service running in degraded mode"
  # Send alert to monitoring system
fi
```

## Deployment Checklist

- [ ] Update liveness probe path to `/v1/health/live`
- [ ] Update readiness probe path to `/v1/health/ready`
- [ ] Add startup probe at `/v1/health/startup`
- [ ] Update monitoring dashboards to use new component endpoints
- [ ] Configure `READY_ALLOW_DEGRADED` based on deployment strategy
- [ ] Configure `HEALTH_DB_TIMEOUT_MS` for database timeout (default: 500ms)
- [ ] Configure `HEALTH_CACHE_TIMEOUT_MS` for cache timeout (default: 200ms)
- [ ] Test health checks in staging environment
- [ ] Update CI/CD pipelines with new health check URLs
- [ ] Update documentation and runbooks with new endpoint paths
