# Default Model System - Metrics Runbook

## Overview

This runbook provides operational guidance for monitoring the DB-driven default model system using Prometheus metrics and Grafana dashboards.

## Key Metrics

### 1. Default Model Resolution (DMR)

#### `default_model_resolution_total`
**Type**: Counter  
**Labels**: `source`, `scope`, `tenant_id`

**Description**: Total number of default model resolutions.

**Alert Thresholds**:
- **Warning**: Rate of env_var fallback > 10% of total resolutions
- **Critical**: No database resolutions in 5 minutes (indicates DMR failure)

**Troubleshooting**:
```bash
# Check DMR resolution sources
sum(rate(default_model_resolution_total{source="database"}[5m]))
sum(rate(default_model_resolution_total{source="env_var"}[5m]))

# High fallback rate indicates:
# 1. No default model configured in database
# 2. Database connectivity issues
# 3. Redis cache unavailable

# Actions:
# - Check database: SELECT * FROM default_models WHERE scope = 'global';
# - Verify Redis connectivity
# - Review DMR service logs
```

#### `default_model_resolution_duration_seconds`
**Type**: Histogram  
**Buckets**: 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0

**Description**: Duration of default model resolution in seconds.

**Alert Thresholds**:
- **Warning**: P95 latency > 500ms
- **Critical**: P95 latency > 1s

**Troubleshooting**:
```bash
# Check latency percentiles
histogram_quantile(0.95, sum(rate(default_model_resolution_duration_seconds_bucket[5m])) by (le))
histogram_quantile(0.99, sum(rate(default_model_resolution_duration_seconds_bucket[5m])) by (le))

# High latency indicates:
# 1. Database query performance issues
# 2. Redis cache miss (cold cache)
# 3. Network latency

# Actions:
# - Check PostgreSQL slow query log
# - Verify Redis cache hit rate
# - Review network connectivity
# - Consider increasing Redis cache TTL
```

#### `default_model_cache_hits_total` / `default_model_cache_misses_total`
**Type**: Counter  
**Labels**: `scope`

**Description**: Cache hit/miss counters for default model resolution.

**Alert Thresholds**:
- **Warning**: Cache hit rate < 80%
- **Critical**: Cache hit rate < 50%

**Troubleshooting**:
```bash
# Calculate cache hit rate
sum(default_model_cache_hits_total) / (sum(default_model_cache_hits_total) + sum(default_model_cache_misses_total))

# Low cache hit rate indicates:
# 1. Frequent default model updates (PATCH invalidations)
# 2. Redis cache evictions (memory pressure)
# 3. Short TTL configuration

# Actions:
# - Review PATCH activity: Check audit logs
# - Check Redis memory usage
# - Consider increasing PROVIDER_HEALTH_TTL (default: 7200s)
# - Review cache invalidation logs
```

---

### 2. Model Warmup

#### `model_warmup_total`
**Type**: Counter  
**Labels**: `status` (success, timeout, error), `model_id`

**Description**: Total number of model warmup attempts by status.

**Alert Thresholds**:
- **Warning**: Warmup failure rate > 20%
- **Critical**: Warmup failure rate > 50%

**Troubleshooting**:
```bash
# Check warmup success rate
sum(rate(model_warmup_total{status="success"}[5m])) / sum(rate(model_warmup_total[5m]))

# High failure rate indicates:
# 1. Model not available (Ollama/OpenAI down)
# 2. Timeout too short (default: 300s)
# 3. Network connectivity issues

# Check specific failure types:
rate(model_warmup_total{status="timeout"}[5m])  # Timeout issues
rate(model_warmup_total{status="error"}[5m])    # LLM adapter errors

# Actions:
# - Check LLM provider health
# - Review LLM_WARMUP_TIMEOUT setting (default: 300s)
# - Verify model exists: ollama list or OpenAI API
# - Check model_warmup service logs
```

#### `model_warmup_duration_seconds`
**Type**: Histogram  
**Buckets**: 1, 5, 10, 30, 60, 120, 300

**Description**: Duration of model warmup in seconds.

**Alert Thresholds**:
- **Warning**: P95 duration > 60s
- **Critical**: P95 duration > 180s (approaching timeout)

**Troubleshooting**:
```bash
# Check warmup duration percentiles
histogram_quantile(0.95, sum(rate(model_warmup_duration_seconds_bucket[5m])) by (le))

# Long warmup indicates:
# 1. Large model size (e.g., 70B parameter models)
# 2. Cold Ollama instance (first load)
# 3. Insufficient GPU/CPU resources

# Actions:
# - Review model size and resource allocation
# - Consider using smaller models for default
# - Check Ollama keep-alive setting (default: 10m)
# - Monitor system resources (GPU memory, CPU)
```

#### `model_warmup_attempts`
**Type**: Histogram  
**Buckets**: 1, 2, 3, 4, 5

**Description**: Number of retry attempts before success/failure.

**Alert Thresholds**:
- **Warning**: Average attempts > 1.5
- **Critical**: Average attempts > 2.5

**Troubleshooting**:
```bash
# Check average retry attempts
sum(model_warmup_attempts_sum) / sum(model_warmup_attempts_count)

# High retry count indicates:
# 1. Intermittent LLM provider issues
# 2. Rate limiting
# 3. Retry delay too short (default: 10s)

# Actions:
# - Check LLM provider stability
# - Review LLM_WARMUP_RETRY_MAX (default: 3)
# - Review LLM_WARMUP_RETRY_DELAY (default: 10s)
# - Check for rate limit errors in logs
```

---

### 3. Provider Health

#### `provider_health`
**Type**: Gauge  
**Labels**: `provider`, `model_name`, `healthy` (true/false)

**Description**: Current health status of LLM providers (1=healthy, 0=unhealthy).

**Alert Thresholds**:
- **Warning**: Any provider unhealthy > 5 minutes
- **Critical**: Default provider unhealthy > 2 minutes

**Troubleshooting**:
```bash
# Check provider health status
provider_health{healthy="false"}

# Unhealthy provider indicates:
# 1. LLM service down (Ollama/OpenAI)
# 2. Network connectivity issues
# 3. Authentication failures

# Check background scheduler:
# - Review SCHEDULER_ENABLED (default: true)
# - Review PROVIDER_HEALTH_REFRESH_INTERVAL (default: 3600s)
# - Review PROVIDER_HEALTH_TTL (default: 7200s)

# Actions:
# - Check LLM provider logs
# - Verify API keys (OpenAI)
# - Restart Ollama service: systemctl restart ollama
# - Check network connectivity: curl http://ollama:11434/api/health
```

---

## Grafana Dashboard

**Dashboard**: `Default Model System - Observability`  
**UID**: `default-model-dmr`  
**Import**: `/monitoring/grafana_dashboard_default_model.json`

### Panels

1. **Total DMR Resolutions**: Gauge showing total resolution count
2. **DMR Resolution Rate (by Source)**: Database vs. Env Var fallback
3. **DMR P95 Latency**: 95th percentile resolution time
4. **DMR Latency Percentiles**: P50, P95, P99 over time
5. **Model Warmup Status**: Success/Timeout/Error rates
6. **Provider Health Status**: Healthy vs. Unhealthy providers
7. **DMR Cache Hit Rate**: Percentage of cache hits

---

## Common Issues & Solutions

### Issue 1: High DMR Latency (P95 > 500ms)

**Symptoms**:
- Slow agent creation
- Timeouts in startup warmup
- High P95 latency in DMR metrics

**Root Causes**:
1. Database query performance (missing indexes)
2. Redis cache miss (cold cache)
3. Network latency

**Solutions**:
```bash
# 1. Check PostgreSQL query performance
EXPLAIN ANALYZE SELECT model_id FROM default_models WHERE scope = 'global' AND tenant_id IS NULL;

# 2. Verify index exists
\d default_models

# 3. Check Redis cache hit rate
sum(default_model_cache_hits_total) / (sum(default_model_cache_hits_total) + sum(default_model_cache_misses_total))

# 4. Increase cache TTL if hit rate low
# Update src/config.py: PROVIDER_HEALTH_TTL = 14400  # 4 hours
```

---

### Issue 2: Model Warmup Timeouts

**Symptoms**:
- High `model_warmup_total{status="timeout"}` rate
- Startup warnings in logs
- Slow first agent requests

**Root Causes**:
1. Timeout too short (default: 300s)
2. Large model size (e.g., 70B)
3. Ollama cold start

**Solutions**:
```bash
# 1. Increase timeout
# Update src/config.py: LLM_WARMUP_TIMEOUT = 600  # 10 minutes

# 2. Check model size
ollama list

# 3. Verify Ollama keep-alive
# Update src/services/model_warmup.py: keep_alive="15m"

# 4. Pre-load model manually
ollama run llama3.2:3b-instruct-fp16
```

---

### Issue 3: Provider Health Always Unhealthy

**Symptoms**:
- `provider_health{healthy="false"}` = 1
- Background scheduler warnings
- No health probes succeeding

**Root Causes**:
1. LLM service down
2. Wrong API endpoint configuration
3. Scheduler not running

**Solutions**:
```bash
# 1. Check LLM service
curl http://localhost:11434/api/health  # Ollama
curl https://api.openai.com/v1/models   # OpenAI

# 2. Verify scheduler is running
# Check logs: grep "provider_health_scheduler.started" /var/log/app.log

# 3. Check scheduler configuration
# src/config.py:
# SCHEDULER_ENABLED = True
# PROVIDER_HEALTH_REFRESH_INTERVAL = 3600
# PROVIDER_HEALTH_TTL = 7200

# 4. Restart app to start scheduler
docker-compose restart app
```

---

### Issue 4: High Cache Miss Rate (< 80%)

**Symptoms**:
- Low `default_model_cache_hits_total` / `default_model_cache_misses_total` ratio
- High database query rate
- Slow DMR resolution

**Root Causes**:
1. Frequent PATCH /defaults updates (cache invalidation)
2. Redis memory evictions
3. Short cache TTL

**Solutions**:
```bash
# 1. Check PATCH activity
grep "patch_defaults.invalidated" /var/log/app.log | wc -l

# 2. Check Redis memory
redis-cli INFO memory

# 3. Increase cache TTL
# Update src/config.py: PROVIDER_HEALTH_TTL = 14400  # 4 hours

# 4. Review invalidation logic
# Ensure PATCH only invalidates when model_id changes, not on every request
```

---

## Alerting Rules

Recommended Prometheus alerting rules:

```yaml
groups:
  - name: default_model_system
    rules:
      # DMR Resolution Failures
      - alert: DMRResolutionFailureRateHigh
        expr: |
          sum(rate(default_model_resolution_total{source="env_var"}[5m])) /
          sum(rate(default_model_resolution_total[5m])) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High DMR fallback rate (> 10%)"
          description: "Default model resolution falling back to env var in {{ $value | humanizePercentage }} of requests"

      # DMR Latency
      - alert: DMRLatencyHigh
        expr: |
          histogram_quantile(0.95, sum(rate(default_model_resolution_duration_seconds_bucket[5m])) by (le)) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High DMR P95 latency (> 500ms)"
          description: "Default model resolution P95 latency is {{ $value | humanizeDuration }}"

      # Model Warmup Failures
      - alert: ModelWarmupFailureRateHigh
        expr: |
          sum(rate(model_warmup_total{status=~"timeout|error"}[5m])) /
          sum(rate(model_warmup_total[5m])) > 0.5
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "High model warmup failure rate (> 50%)"
          description: "Model warmup failing in {{ $value | humanizePercentage }} of attempts"

      # Provider Health
      - alert: ProviderUnhealthy
        expr: provider_health{healthy="false"} == 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Provider {{ $labels.provider }} unhealthy"
          description: "LLM provider {{ $labels.provider }} has been unhealthy for 5+ minutes"

      # Cache Hit Rate
      - alert: DMRCacheHitRateLow
        expr: |
          sum(default_model_cache_hits_total) /
          (sum(default_model_cache_hits_total) + sum(default_model_cache_misses_total)) < 0.8
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Low DMR cache hit rate (< 80%)"
          description: "Default model cache hit rate is {{ $value | humanizePercentage }}"
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROVIDER_HEALTH_TTL` | 7200 | Redis cache TTL for health status (seconds) |
| `PROVIDER_HEALTH_REFRESH_INTERVAL` | 3600 | Background health refresh interval (seconds) |
| `SCHEDULER_ENABLED` | true | Enable provider health background scheduler |
| `LLM_WARMUP_TIMEOUT` | 300 | Model warmup timeout (seconds) |
| `LLM_WARMUP_RETRY_MAX` | 3 | Maximum warmup retry attempts |
| `LLM_WARMUP_RETRY_DELAY` | 10 | Delay between warmup retries (seconds) |
| `CATALOG_CACHE_TTL` | 1800 | Tool catalog cache TTL (seconds) |

### Health Check Endpoints

- **Liveness**: `GET /health` - Returns 200 if app is running
- **Readiness**: `GET /readyz` - Returns 200 if DMR initialized (Phase 6)
- **Metrics**: `GET /metrics` - Prometheus metrics endpoint

---

## Emergency Procedures

### Emergency 1: Total DMR Failure (No Database Resolution)

**Action**: Fall back to env var temporarily while investigating

```bash
# 1. Set fallback in environment
export DEFAULT_MODEL_NAME="llama3.2:3b-instruct-fp16"

# 2. Restart app
docker-compose restart app

# 3. Investigate database
docker exec -it postgres psql -U user -d cineca_db
SELECT * FROM default_models WHERE scope = 'global';

# 4. Restore database default if missing
INSERT INTO default_models (model_id, scope, created_by)
VALUES ('llama3.2:3b-instruct-fp16', 'global', 'system');
```

### Emergency 2: Redis Total Failure

**Action**: DMR will fall back to database queries (slower but functional)

```bash
# 1. Check Redis status
docker exec -it redis redis-cli PING

# 2. Restart Redis if needed
docker-compose restart redis

# 3. Monitor DMR latency (expect higher without cache)
# P95 may spike to 100-200ms without Redis

# 4. No action needed - system degrades gracefully
```

---

## Contact & Escalation

- **P1 (Critical)**: Page on-call engineer immediately
- **P2 (High)**: Create incident ticket, notify team lead
- **P3 (Medium)**: Create bug ticket, address in next sprint

**Runbook Maintained By**: Platform Engineering Team  
**Last Updated**: 2025-01-09
