# LLM Model Configuration Guide

**Version:** 1.0  
**Last Updated:** 2025-11-16  
**Status:** Production

## Overview

The Cineca Agentic Platform uses a **database-driven model configuration** approach as the single source of truth for LLM model settings. This design ensures:

- **Consistency**: All components read from the same configuration
- **Auditability**: Configuration changes are tracked in the database
- **Runtime Updates**: Model configuration can be changed without code deployments
- **Multi-tenancy**: Different tenants can use different default models

## Architecture

### Database Tables

The LLM configuration is stored in three PostgreSQL tables:

```sql
-- Provider configuration (e.g., Ollama, OpenAI)
CREATE TABLE providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'ollama', 'openai_compatible', etc.
    config JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Model instance definitions
CREATE TABLE model_instances (
    id TEXT PRIMARY KEY,
    provider_id TEXT REFERENCES providers(id),
    instance_name TEXT NOT NULL,
    model_id TEXT NOT NULL,  -- e.g., 'phi3:mini', 'gpt-4'
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Default model mappings
CREATE TABLE model_defaults (
    id SERIAL PRIMARY KEY,
    scope TEXT NOT NULL,  -- 'global', 'tenant', 'user'
    tenant_id TEXT,       -- NULL for global scope
    user_id TEXT,         -- NULL for global/tenant scope
    instance_id TEXT REFERENCES model_instances(id),
    created_at TIMESTAMP,
    UNIQUE(scope, tenant_id, user_id)
);
```

### Configuration Flow

```
1. Application starts
2. Orchestrator calls model_instance_repo.get_default(scope='global', tenant_id=None)
3. Repository queries model_defaults JOIN model_instances JOIN providers
4. Returns complete configuration: {instance_name, provider_model_id, base_url, provider_name}
5. Orchestrator creates LLMClient with this configuration
6. LLMClient verifies model exists via /api/tags
7. Model configuration is cached in memory for the lifetime of the process
```

## Setup Instructions

### Step 1: Register Provider

Register the Ollama provider (or other LLM provider):

```sql
INSERT INTO providers (id, name, type, config, created_at, updated_at)
VALUES (
    'ollama-local',
    'Local Ollama',
    'ollama',
    '{"base_url": "http://ollama:11434/v1"}'::jsonb,
    NOW(),
    NOW()
);
```

### Step 2: Create Model Instance

Define the model instance (e.g., phi3-mini):

```sql
INSERT INTO model_instances (id, provider_id, instance_name, model_id, created_at, updated_at)
VALUES (
    'phi3-mini',
    'ollama-local',
    'phi3-mini',
    'phi3:mini',
    NOW(),
    NOW()
);
```

### Step 3: Set Global Default

Set the global default model:

```sql
INSERT INTO model_defaults (scope, tenant_id, user_id, instance_id, created_at)
VALUES ('global', NULL, NULL, 'phi3-mini', NOW())
ON CONFLICT (scope, tenant_id, user_id) 
DO UPDATE SET instance_id = EXCLUDED.instance_id, created_at = NOW();
```

### Step 4: Verify Configuration

Use the smoke test endpoint to verify the configuration:

```bash
make llm-smoke-test
```

Expected output:

```json
{
  "status": "success",
  "config_source": "db_default",
  "instance_name": "phi3-mini",
  "provider_model_id": "phi3:mini",
  "base_url": "http://ollama:11434/v1",
  "device": "cpu",
  "latency_ms": 24177
}
```

### Step 5: Check Application Logs

Verify the orchestrator picked up the configuration:

```bash
docker compose logs app | grep "orchestrator.default_model_registered"
```

Expected log entry:

```
INFO orchestrator.default_model_registered 
  instance_name=phi3-mini 
  provider_model_id=phi3:mini 
  base_url=http://ollama:11434/v1 
  provider_name="Local Ollama"
```

## Changing Models

### Changing the Global Default

To switch to a different model (e.g., from phi3-mini to llama3.2:3b):

```sql
-- 1. Ensure model instance exists
INSERT INTO model_instances (id, provider_id, instance_name, model_id, created_at, updated_at)
VALUES (
    'llama32-3b',
    'ollama-local',
    'llama32-3b',
    'llama3.2:3b',
    NOW(),
    NOW()
)
ON CONFLICT (id) DO NOTHING;

-- 2. Update global default
UPDATE model_defaults 
SET instance_id = 'llama32-3b', created_at = NOW()
WHERE scope = 'global' AND tenant_id IS NULL AND user_id IS NULL;
```

**IMPORTANT**: Restart the application for changes to take effect:

```bash
docker compose restart app worker
```

### Tenant-Specific Defaults

To set a different default for a specific tenant:

```sql
INSERT INTO model_defaults (scope, tenant_id, user_id, instance_id, created_at)
VALUES ('tenant', 'acme-corp', NULL, 'llama32-3b', NOW())
ON CONFLICT (scope, tenant_id, user_id) 
DO UPDATE SET instance_id = EXCLUDED.instance_id, created_at = NOW();
```

## Verification

### 1. Smoke Test Endpoint

The `/v1/internal/ops/llm-smoke-test` endpoint performs a lightweight inference test:

```bash
# Using make target
make llm-smoke-test

# Or directly with curl
export AUTH0_MACHINE_TOKEN=$(grep '^AUTH0_MACHINE_TOKEN=' .env | cut -d= -f2 | tr -d ' "')
curl -X POST http://localhost:8000/v1/internal/ops/llm-smoke-test \
  -H "Authorization: Bearer $AUTH0_MACHINE_TOKEN" \
  -H "Content-Type: application/json" | jq .
```

### 2. Application Logs

Check for these log events:

```bash
# Model registration at startup
docker compose logs app | grep "orchestrator.default_model_registered"

# Model verification before inference
docker compose logs app | grep "llm.model_verified"

# Model verification cache hits (debug level)
docker compose logs app | grep "llm.model_verified_cached"
```

### 3. Database Query

Directly query the configuration:

```sql
SELECT 
    md.scope,
    md.tenant_id,
    mi.instance_name,
    mi.model_id,
    p.name as provider_name,
    p.config->>'base_url' as base_url
FROM model_defaults md
JOIN model_instances mi ON md.instance_id = mi.id
JOIN providers p ON mi.provider_id = p.id
WHERE md.scope = 'global' 
  AND md.tenant_id IS NULL 
  AND md.user_id IS NULL;
```

## Troubleshooting

### Issue: Smoke Test Fails with "Model not found"

**Symptoms:**
```json
{
  "status": "error",
  "error": "Model phi3:mini not found on provider"
}
```

**Solutions:**

1. **Check if model is pulled in Ollama:**
   ```bash
   docker compose exec ollama ollama list
   ```

2. **Pull the model if missing:**
   ```bash
   docker compose exec ollama ollama pull phi3:mini
   ```

3. **Verify model_id matches Ollama:**
   ```sql
   SELECT model_id FROM model_instances WHERE id = 'phi3-mini';
   -- Should return 'phi3:mini' (matches Ollama naming)
   ```

### Issue: Multiple Defaults Error

**Symptoms:**
```
ValueError: Multiple default models found for scope=global, tenant_id=None: found 2 defaults with instance_ids=['phi3-mini', 'llama32-3b']
```

**Solution:**
```sql
-- Find duplicates
SELECT scope, tenant_id, user_id, COUNT(*) 
FROM model_defaults 
GROUP BY scope, tenant_id, user_id 
HAVING COUNT(*) > 1;

-- Remove duplicates (keep most recent)
DELETE FROM model_defaults 
WHERE id NOT IN (
    SELECT MAX(id) 
    FROM model_defaults 
    GROUP BY scope, tenant_id, user_id
);
```

### Issue: Timeout During Inference

**Symptoms:**
```
httpx.TimeoutException: timed out after 600.0 seconds
```

**Solutions:**

1. **Check device (CPU vs GPU):**
   - phi3-mini on CPU: 60-120 seconds per inference
   - phi3-mini on GPU: 2-5 seconds per inference

2. **Verify timeout configuration:**
   ```python
   # In src/adapters/llm.py
   AsyncClient(timeout=600.0)  # Should be 600s for CPU
   ```

3. **Consider switching to GPU deployment:**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
   ```

4. **Use smaller model:**
   ```sql
   -- Switch to qwen2.5:0.5b (smaller, faster)
   UPDATE model_defaults 
   SET instance_id = 'qwen25-05b'
   WHERE scope = 'global';
   ```

### Issue: Configuration Not Taking Effect

**Symptoms:**
- Smoke test shows old model
- Logs show wrong model_id

**Solutions:**

1. **Restart application:**
   ```bash
   docker compose restart app worker
   ```

2. **Clear model verification cache (automatic on restart)**

3. **Check for environment variable overrides:**
   ```bash
   # These should NOT be set (DB is source of truth)
   docker compose exec app env | grep -E "LLM_MODEL|LLM_DEFAULT_MODEL|LLM_BASE_URL"
   ```

### Issue: Ollama Connection Refused

**Symptoms:**
```
Connection refused to http://ollama:11434
```

**Solutions:**

1. **Verify Ollama is running:**
   ```bash
   docker compose ps ollama
   ```

2. **Check Ollama health:**
   ```bash
   docker compose exec ollama curl -f http://localhost:11434/api/tags
   ```

3. **Verify base_url in provider config:**
   ```sql
   SELECT config->>'base_url' FROM providers WHERE id = 'ollama-local';
   -- Should return 'http://ollama:11434/v1'
   ```

## Best Practices

### 1. Always Use Database for Configuration

❌ **DON'T:** Set model via environment variables
```bash
export LLM_MODEL="phi3-mini"  # Don't do this
```

✅ **DO:** Update database and restart
```sql
UPDATE model_defaults SET instance_id = 'phi3-mini' WHERE scope = 'global';
```

### 2. Test Configuration Changes

Before deploying to production:

```bash
# 1. Update configuration in DB
# 2. Restart app
docker compose restart app

# 3. Run smoke test
make llm-smoke-test

# 4. Check logs
docker compose logs app --tail=50 | grep "orchestrator.default_model_registered"
```

### 3. Monitor Model Performance

Track inference latency via smoke test:

```bash
# Run smoke test and extract latency
make llm-smoke-test | jq .latency_ms
```

Expected latencies:
- **CPU (phi3-mini):** 60,000-120,000 ms (60-120 seconds)
- **GPU (phi3-mini):** 2,000-5,000 ms (2-5 seconds)

### 4. Document Model Changes

When changing models, document in git:

```bash
git commit -m "Change LLM model from phi3-mini to llama3.2:3b for improved performance"
```

Include migration SQL in commit message:

```sql
UPDATE model_defaults 
SET instance_id = 'llama32-3b'
WHERE scope = 'global';
```

### 5. Use Tenant-Specific Defaults for Testing

Isolate test environments with tenant-specific models:

```sql
-- Production tenant uses production model
INSERT INTO model_defaults (scope, tenant_id, user_id, instance_id, created_at)
VALUES ('tenant', 'prod-tenant', NULL, 'llama32-70b', NOW());

-- Test tenant uses faster model
INSERT INTO model_defaults (scope, tenant_id, user_id, instance_id, created_at)
VALUES ('tenant', 'test-tenant', NULL, 'phi3-mini', NOW());
```

## Integration with CI/CD

### Pre-Deployment Checks

Add smoke test to CI pipeline:

```yaml
# .github/workflows/deploy.yml
- name: Verify LLM Configuration
  run: |
    docker compose up -d
    sleep 10  # Wait for services
    make llm-smoke-test
```

### Database Migrations

Use Alembic migrations for model configuration changes:

```python
# db/postgres_control/versions/xxx_add_llama_model.py
def upgrade():
    op.execute("""
        INSERT INTO model_instances (id, provider_id, instance_name, model_id, created_at, updated_at)
        VALUES ('llama32-3b', 'ollama-local', 'llama32-3b', 'llama3.2:3b', NOW(), NOW())
        ON CONFLICT (id) DO NOTHING;
    """)

def downgrade():
    op.execute("DELETE FROM model_instances WHERE id = 'llama32-3b';")
```

## Related Documentation

- [Ollama Operational Runbook](./OLLAMA_RUNBOOK.md) - Ollama-specific operations and troubleshooting
- [Agent Run Schema](./AGENT_RUN_SCHEMA.md) - Agent run metadata and model configuration persistence
- [Architecture Overview](./ARCHITECTURE.md) - High-level system architecture

## Support

For issues related to LLM configuration:

1. Check smoke test output: `make llm-smoke-test`
2. Review application logs: `docker compose logs app | grep llm`
3. Verify database configuration: See "Verification" section above
4. Consult [Ollama Runbook](./OLLAMA_RUNBOOK.md) for Ollama-specific issues
