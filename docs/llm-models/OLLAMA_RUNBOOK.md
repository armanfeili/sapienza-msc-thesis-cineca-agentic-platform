# Ollama Operational Runbook

**Version:** 1.0  
**Last Updated:** 2025-11-16  
**Audience:** DevOps, Platform Engineers, SREs

## Overview

This runbook provides operational guidance for managing Ollama as the LLM inference backend for the Cineca Agentic Platform. It covers configuration, monitoring, troubleshooting, and performance tuning.

## Quick Reference

| Metric | CPU (phi3-mini) | GPU (phi3-mini) |
|--------|-----------------|-----------------|
| Inference Time | 60-120 seconds | 2-5 seconds |
| Timeout Setting | 600 seconds | 120 seconds |
| Memory Usage | ~2.2 GB | ~2.2 GB VRAM |
| Concurrent Requests | 1-2 | 5-10 |

## Architecture

### Component Overview

```
┌─────────────────┐
│  Orchestrator   │ (reads model config from DB)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   LLMClient     │ (verifies model, makes inference calls)
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│     Ollama      │ (serves models on :11434)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Model Storage  │ (/models or ~/.ollama/models)
└─────────────────┘
```

### Model Configuration Flow

1. **Database** stores model configuration (NOT environment variables)
2. **Orchestrator** reads default model from PostgreSQL on startup
3. **LLMClient** verifies model exists via `/api/tags` endpoint
4. **Model verification cache** prevents repeated HTTP calls
5. **Inference** uses 600s timeout for CPU, 120s for GPU

## Installation & Setup

### Docker Compose Deployment

**CPU Configuration** (default):

```yaml
# docker-compose.yml
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ./models:/models
      - ollama-data:/root/.ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 3
```

**GPU Configuration**:

```yaml
# docker-compose.gpu.yml
services:
  ollama:
    image: ollama/ollama:latest
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
```

### Model Configuration

**❌ INCORRECT - Using Environment Variables:**

```bash
# DON'T DO THIS
export LLM_MODEL="phi3-mini"
export LLM_BASE_URL="http://ollama:11434/v1"
```

**✅ CORRECT - Using Database:**

```sql
-- 1. Register provider
INSERT INTO providers (id, name, type, config, created_at, updated_at)
VALUES (
    'ollama-local',
    'Local Ollama',
    'ollama',
    '{"base_url": "http://ollama:11434/v1"}'::jsonb,
    NOW(),
    NOW()
);

-- 2. Create model instance
INSERT INTO model_instances (id, provider_id, instance_name, model_id, created_at, updated_at)
VALUES (
    'phi3-mini',
    'ollama-local',
    'phi3-mini',
    'phi3:mini',
    NOW(),
    NOW()
);

-- 3. Set as default
INSERT INTO model_defaults (scope, tenant_id, user_id, instance_id, created_at)
VALUES ('global', NULL, NULL, 'phi3-mini', NOW());
```

See [LLM Model Configuration Guide](./LLM_MODEL_CONFIGURATION.md) for detailed setup instructions.

## Operational Procedures

### Starting Ollama

```bash
# Start all services including Ollama
docker compose up -d

# Verify Ollama is healthy
docker compose ps ollama
# Should show: STATUS = Up X minutes (healthy)

# Check Ollama logs
docker compose logs ollama --tail=50
```

### Pulling Models

Models should be pulled **before** setting them as default:

```bash
# Pull phi3-mini (2.2GB, ~3-5 minutes on good connection)
docker compose exec ollama ollama pull phi3:mini

# Pull llama3.2:3b (2.0GB)
docker compose exec ollama ollama pull llama3.2:3b

# Pull qwen2.5:0.5b (395MB, fastest)
docker compose exec ollama ollama pull qwen2.5:0.5b
```

**List available models:**

```bash
docker compose exec ollama ollama list
```

Expected output:

```
NAME            ID              SIZE    MODIFIED
phi3:mini       4f2222927938    2.2 GB  2 hours ago
llama3.2:3b     a80c4f17acd5    2.0 GB  3 days ago
```

### Verifying Configuration

After pulling models and updating database:

```bash
# 1. Restart application to pick up new config
docker compose restart app worker

# 2. Run smoke test
make llm-smoke-test

# 3. Check logs for model registration
docker compose logs app | grep "orchestrator.default_model_registered"
```

### Changing Models

**Procedure:**

1. **Pull new model** (if not already available):
   ```bash
   docker compose exec ollama ollama pull llama3.2:3b
   ```

2. **Update database** (create instance if needed):
   ```sql
   INSERT INTO model_instances (id, provider_id, instance_name, model_id, created_at, updated_at)
   VALUES ('llama32-3b', 'ollama-local', 'llama32-3b', 'llama3.2:3b', NOW(), NOW())
   ON CONFLICT (id) DO NOTHING;
   
   UPDATE model_defaults 
   SET instance_id = 'llama32-3b', created_at = NOW()
   WHERE scope = 'global' AND tenant_id IS NULL;
   ```

3. **Restart services**:
   ```bash
   docker compose restart app worker
   ```

4. **Verify**:
   ```bash
   make llm-smoke-test
   ```

## Monitoring

### Health Checks

**Ollama Service Health:**

```bash
# Docker health status
docker compose ps ollama

# Manual health check
curl -f http://localhost:11434/api/tags
```

**Application Health:**

```bash
# LLM smoke test (includes latency)
make llm-smoke-test

# Expected: latency_ms < 120000 for CPU, < 10000 for GPU
```

### Key Metrics

Monitor these metrics in production:

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| **Inference Latency** | Time from request to response | >120s (CPU), >10s (GPU) |
| **Error Rate** | Failed LLM calls / total calls | >5% |
| **Model Verification Time** | Time to check /api/tags | >5s |
| **Ollama Container Restarts** | Number of restarts in 24h | >3 |
| **Memory Usage** | Ollama container memory | >80% of limit |

### Log Monitoring

**Key log events to track:**

```bash
# Model registration (startup)
docker compose logs app | grep "orchestrator.default_model_registered"

# Model verification (before each inference)
docker compose logs app | grep "llm.model_verified"

# Model verification cache hits (performance)
docker compose logs app | grep "llm.model_verified_cached"

# LLM errors (failures)
docker compose logs app | grep "llm.error"

# Timeouts
docker compose logs app | grep "httpx.TimeoutException"
```

### Prometheus Metrics

If Prometheus is enabled:

```prometheus
# Inference latency histogram
histogram_quantile(0.95, sum(rate(llm_inference_duration_seconds_bucket[5m])) by (le))

# Error rate
rate(llm_errors_total[5m]) / rate(llm_requests_total[5m])

# Cache hit rate
rate(llm_verification_cache_hits_total[5m]) / rate(llm_verification_attempts_total[5m])
```

## Timeout Configuration

### Understanding Timeouts

The platform has three timeout layers:

1. **LLM Client Timeout** (`src/adapters/llm.py`):
   ```python
   AsyncClient(timeout=600.0)  # 600 seconds for CPU inference
   ```

2. **Step Timeout** (per agent step):
   ```python
   step_timeout_seconds = 600  # Total time for one reasoning step
   ```

3. **Run Timeout** (entire agent run):
   ```python
   run_timeout_seconds = 600  # Total time for complete agent execution
   ```

### CPU vs GPU Timeout Settings

| Device | LLM Timeout | Step Timeout | Run Timeout |
|--------|-------------|--------------|-------------|
| CPU    | 600s        | 600s         | 600s        |
| GPU    | 120s        | 300s         | 600s        |

### Changing Timeouts

**For CPU deployments** (current configuration):

```python
# src/adapters/llm.py (line ~442)
AsyncClient(timeout=600.0)  # Already set to 600s

# tests/integration/test_agent_memgraph_nl_prompts_v2.py (line ~422)
orchestrator_config = {
    "step_timeout_seconds": "600",
    ...
}
```

**For GPU deployments** (reduce timeouts for faster failure detection):

```python
# src/adapters/llm.py
AsyncClient(timeout=120.0)  # Reduce to 120s for GPU

# Restart required
docker compose restart app worker
```

## Troubleshooting

### Issue 1: Model Not Found

**Symptoms:**

```json
{
  "status": "error",
  "error": "Model phi3:mini not found on provider"
}
```

**Diagnosis:**

```bash
# Check if model is pulled
docker compose exec ollama ollama list

# Check model ID in database
docker compose exec postgres psql -U cineca_user -d cineca_db \
  -c "SELECT instance_name, model_id FROM model_instances WHERE id = 'phi3-mini';"
```

**Resolution:**

```bash
# Option 1: Pull the model
docker compose exec ollama ollama pull phi3:mini

# Option 2: Fix model_id in database (if wrong)
UPDATE model_instances 
SET model_id = 'phi3:mini'  -- Must match Ollama model name
WHERE id = 'phi3-mini';

# Restart and verify
docker compose restart app
make llm-smoke-test
```

### Issue 2: Inference Timeout

**Symptoms:**

```
httpx.TimeoutException: timed out after 600.0 seconds
```

**Diagnosis:**

```bash
# Check device (CPU vs GPU)
docker compose exec ollama nvidia-smi || echo "No GPU detected"

# Check recent inference latencies
docker compose logs app | grep "llm.inference_complete" | tail -5
```

**Resolution:**

**Option A: Switch to GPU** (if available):

```bash
# Stop services
docker compose down

# Start with GPU profile
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# Verify GPU is detected
docker compose exec ollama nvidia-smi

# Test with reduced timeout
make llm-smoke-test
```

**Option B: Use smaller/faster model**:

```bash
# Pull qwen2.5:0.5b (much faster on CPU)
docker compose exec ollama ollama pull qwen2.5:0.5b

# Update database
INSERT INTO model_instances (id, provider_id, instance_name, model_id, created_at, updated_at)
VALUES ('qwen25-05b', 'ollama-local', 'qwen25-05b', 'qwen2.5:0.5b', NOW(), NOW());

UPDATE model_defaults 
SET instance_id = 'qwen25-05b' 
WHERE scope = 'global';

# Restart and test
docker compose restart app
make llm-smoke-test
```

**Option C: Increase timeout** (not recommended):

```python
# src/adapters/llm.py
AsyncClient(timeout=900.0)  # Increase to 900s (15 minutes)
```

### Issue 3: Ollama Returns 500 Error

**Symptoms:**

```
llm.error status_code=500 provider=ollama model=phi3:mini
```

**Diagnosis:**

```bash
# Check Ollama logs
docker compose logs ollama --tail=100

# Common errors:
# - Out of memory
# - Model corrupted
# - Ollama crash
```

**Resolution:**

**Memory Issues:**

```bash
# Check memory usage
docker stats ollama --no-stream

# Increase Docker memory limit
# In docker-compose.yml:
services:
  ollama:
    deploy:
      resources:
        limits:
          memory: 8G  # Increase from default
```

**Corrupted Model:**

```bash
# Remove and re-pull model
docker compose exec ollama ollama rm phi3:mini
docker compose exec ollama ollama pull phi3:mini

# Restart Ollama
docker compose restart ollama

# Verify
make llm-smoke-test
```

**Ollama Crash:**

```bash
# Check exit code
docker compose ps ollama

# Restart Ollama
docker compose restart ollama

# Check for persistent issues
docker compose logs ollama --tail=200 | grep -i "error\|fatal\|panic"
```

### Issue 4: Multiple Defaults Error

**Symptoms:**

```
ValueError: Multiple default models found for scope=global, tenant_id=None: 
found 2 defaults with instance_ids=['phi3-mini', 'llama32-3b']
```

**Diagnosis:**

```sql
-- Find all defaults
SELECT * FROM model_defaults 
WHERE scope = 'global' AND tenant_id IS NULL;
```

**Resolution:**

```sql
-- Keep only the most recent default
DELETE FROM model_defaults 
WHERE id NOT IN (
    SELECT MAX(id) 
    FROM model_defaults 
    WHERE scope = 'global' AND tenant_id IS NULL
);

-- Verify only one remains
SELECT COUNT(*) FROM model_defaults 
WHERE scope = 'global' AND tenant_id IS NULL;
-- Should return 1
```

### Issue 5: High Memory Usage

**Symptoms:**

```bash
docker stats ollama
# Shows >90% memory usage
```

**Diagnosis:**

```bash
# Check loaded models
docker compose exec ollama ollama ps

# Each model consumes memory while loaded
```

**Resolution:**

```bash
# Option 1: Unload unused models (automatic after 5 min idle)
# Wait 5 minutes or restart Ollama
docker compose restart ollama

# Option 2: Use smaller models
# qwen2.5:0.5b uses 395MB vs phi3:mini 2.2GB

# Option 3: Increase Docker memory
# docker-compose.yml
services:
  ollama:
    deploy:
      resources:
        limits:
          memory: 8G
```

### Issue 6: Slow Model Verification

**Symptoms:**

```bash
# Logs show repeated verification checks
docker compose logs app | grep "llm.model_verified" | wc -l
# Shows high count (>100)
```

**Diagnosis:**

```bash
# Check cache hit ratio
docker compose logs app | grep -c "llm.model_verified_cached"  # Should be high
docker compose logs app | grep -c "llm.model_verified"         # Should be low
```

**Resolution:**

Already implemented in `src/adapters/llm.py`:

```python
# Module-level cache (lines ~42-45)
_VERIFIED_MODELS: set[tuple[str, str]] = set()

# Verification checks cache before HTTP call (lines ~327-395)
if (base_url, model_id) in _VERIFIED_MODELS:
    logger.debug("llm.model_verified_cached", ...)
    return
```

**If cache not working:**

```bash
# Restart app to clear any issues
docker compose restart app

# Verify cache is working
docker compose logs app --tail=100 | grep "llm.model_verified_cached"
```

## Performance Tuning

### Model Selection

Choose model based on requirements:

| Model | Size | CPU Latency | GPU Latency | Use Case |
|-------|------|-------------|-------------|----------|
| qwen2.5:0.5b | 395 MB | 10-20s | <1s | Fast prototypes, testing |
| phi3:mini | 2.2 GB | 60-120s | 2-5s | **Production (current)** |
| llama3.2:3b | 2.0 GB | 90-150s | 3-8s | Better quality |
| mistral:7b | 4.1 GB | 180-300s | 5-15s | Highest quality |

### Concurrent Requests

**CPU Deployments:**

```yaml
# Limit concurrency to prevent resource exhaustion
services:
  ollama:
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 8G
```

**Recommended:** 1-2 concurrent requests on CPU

**GPU Deployments:**

```yaml
services:
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - count: 1
              capabilities: [gpu]
```

**Recommended:** 5-10 concurrent requests on single GPU

### Caching Strategy

Model verification caching is enabled by default:

```python
# Automatic caching in src/adapters/llm.py
_VERIFIED_MODELS: set[tuple[str, str]] = set()

# First call: HTTP request to /api/tags
# Subsequent calls: Cache hit (no HTTP request)
```

**Monitor cache effectiveness:**

```bash
# Should see many cache hits
docker compose logs app | grep "llm.model_verified_cached" | wc -l

# Should see few verification checks
docker compose logs app | grep "llm.model_verified" | grep -v "cached" | wc -l
```

## Disaster Recovery

### Backup Models

Models are stored in Docker volume:

```bash
# Create backup
docker run --rm \
  -v cineca-agentic-platform_ollama-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/ollama-models-$(date +%Y%m%d).tar.gz /data

# Restore backup
docker compose down
docker volume rm cineca-agentic-platform_ollama-data
docker volume create cineca-agentic-platform_ollama-data
docker run --rm \
  -v cineca-agentic-platform_ollama-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/ollama-models-YYYYMMDD.tar.gz -C /
docker compose up -d
```

### Recreate Ollama from Scratch

```bash
# 1. Stop and remove Ollama
docker compose stop ollama
docker compose rm -f ollama
docker volume rm cineca-agentic-platform_ollama-data

# 2. Recreate Ollama
docker compose up -d ollama

# 3. Pull required models
docker compose exec ollama ollama pull phi3:mini

# 4. Verify
make llm-smoke-test
```

## Alerting Recommendations

### Critical Alerts (Page Immediately)

```yaml
- alert: OllamaDown
  expr: up{job="ollama"} == 0
  for: 2m
  severity: critical
  
- alert: LLMInferenceFailureRate
  expr: rate(llm_errors_total[5m]) / rate(llm_requests_total[5m]) > 0.5
  for: 5m
  severity: critical

- alert: LLMInferenceTimeout
  expr: histogram_quantile(0.95, llm_inference_duration_seconds) > 600
  for: 10m
  severity: critical
```

### Warning Alerts (Investigate Soon)

```yaml
- alert: LLMInferenceSlowCPU
  expr: histogram_quantile(0.95, llm_inference_duration_seconds) > 120
  for: 15m
  severity: warning

- alert: OllamaMemoryHigh
  expr: container_memory_usage_bytes{name="ollama"} / container_spec_memory_limit_bytes{name="ollama"} > 0.9
  for: 10m
  severity: warning

- alert: LLMCacheHitRateLow
  expr: rate(llm_verification_cache_hits_total[10m]) / rate(llm_verification_attempts_total[10m]) < 0.8
  for: 15m
  severity: warning
```

## References

- [LLM Model Configuration Guide](./LLM_MODEL_CONFIGURATION.md) - Database-driven configuration
- [Ollama Official Documentation](https://ollama.ai/docs) - Upstream documentation
- [Agent Run Schema](./AGENT_RUN_SCHEMA.md) - Understanding agent execution
- [Docker Compose Reference](../docker-compose.yml) - Service definitions

## Support Escalation

1. **Level 1 - Self-Service:**
   - Run `make llm-smoke-test`
   - Check logs: `docker compose logs ollama app`
   - Restart services: `docker compose restart`

2. **Level 2 - Platform Team:**
   - Review this runbook
   - Check Prometheus metrics
   - Investigate database configuration

3. **Level 3 - Senior Engineers:**
   - Code changes required
   - Infrastructure scaling needed
   - Vendor support required

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-11-16 | 1.0 | Initial runbook creation |
