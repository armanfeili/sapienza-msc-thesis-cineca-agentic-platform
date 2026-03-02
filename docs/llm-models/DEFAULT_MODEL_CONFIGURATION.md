# Default Model Configuration

This document explains how the Cineca Agentic Platform manages the default LLM model across the entire stack.

## Overview

The platform uses a **database-first** approach for model configuration:
- Default model is stored in PostgreSQL (`model_instances` table with `is_default=true`)
- All components read from the database at startup
- Model can be changed via API endpoint without restarting services
- Single model loaded in memory for optimal RAM usage

## Current Configuration

**Default Model:** `phi3:mini-instruct`

This model is:
- ✅ Lightweight (2.4 GB on disk, ~2.0-2.5 GB RAM during inference)
- ✅ Fast inference on CPU (~3-15 minutes per call depending on context)
- ✅ Suitable for agentic tasks (planning, tool selection, summarization)

## Architecture

### 1. Database Schema

**`model_instances` table:**
```sql
CREATE TABLE model_instances (
    id UUID PRIMARY KEY,
    instance_name VARCHAR(255) NOT NULL,
    provider_id UUID REFERENCES providers(id),
    model_id VARCHAR(255) NOT NULL,  -- e.g., "phi3:mini-instruct"
    enabled BOOLEAN DEFAULT true,
    loaded BOOLEAN DEFAULT false,
    is_default BOOLEAN DEFAULT false,  -- Only ONE instance should have this=true
    tenant_id VARCHAR(255),  -- NULL = global default
    config JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**`providers` table:**
```sql
CREATE TABLE providers (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    provider_type VARCHAR(50),  -- e.g., "ollama", "openai"
    base_url VARCHAR(500),  -- e.g., "http://ollama:11434/v1"
    enabled BOOLEAN DEFAULT true,
    config JSONB
);
```

### 2. Initialization Flow

**On container startup (`docker-entrypoint.sh`):**

```bash
1. Run database migrations (alembic upgrade head)
2. Run init_default_model.py script:
   - Create/update Ollama provider entry
   - Create/update phi3:mini-instruct model instance
   - Set is_default=true on this instance
   - Clear is_default from all other instances
3. Start application server
```

### 3. Orchestrator Initialization

**`src/services/orchestrator.py` - `from_env()` method:**

```python
1. Query database for all enabled+loaded model instances
2. Find instance with is_default=true
3. Create LLM client for the default model
4. Set orchestrator.default_model = model name
5. Register client with orchestrator.llm_clients
```

### 4. Runtime Behavior

**All LLM calls in orchestrator use `self.default_model`:**

- **Initial planning/reasoning:** `call_model(model=self.default_model)`
- **Tool selection:** `call_model(model=self.default_model)`  
- **TODO list creation:** `call_model_with_metrics(model=self.default_model)`
- **Response generation:** `call_model(model=self.default_model)`

**Single model in memory:**
- Ollama keeps the model loaded for 10 minutes after last use (`OLLAMA_KEEP_ALIVE=10m`)
- Only one model loaded at a time (`OLLAMA_MAX_LOADED_MODELS=1`)
- Subsequent calls reuse the loaded model (no reload overhead)

## Configuration Files

### docker-compose.yml

```yaml
environment:
  # Default model configuration
  DEFAULT_MODEL_NAME: "${DEFAULT_MODEL_NAME:-phi3:mini-instruct}"
  LLM_FALLBACK_MODE: "${LLM_FALLBACK_MODE:-never}"
  OLLAMA_BASE_URL: "${OLLAMA_BASE_URL:-http://ollama:11434/v1}"
  OLLAMA_KEEP_ALIVE: "10m"
  OLLAMA_MAX_LOADED_MODELS: "1"
```

### .env (optional overrides)

```bash
# Override default model
DEFAULT_MODEL_NAME=phi3:mini-instruct

# Never fallback to alternative models
LLM_FALLBACK_MODE=never

# Ollama configuration
OLLAMA_BASE_URL=http://ollama:11434/v1
OLLAMA_TIMEOUT_SECS=180
```

## Changing the Default Model

### Method 1: Via API Endpoint (Recommended)

**Endpoint:** `PATCH /v1/admin/models/defaults`

**Request:**
```bash
curl -X PATCH "http://localhost:8000/v1/admin/models/defaults" \
  -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Default-Scope: global" \
  -d '{
    "chat": {
      "instance_id": "6491b020-bbe3-47fe-991e-e7c21a15260c"
    }
  }'
```

**Steps:**
1. List available models: `GET /v1/admin/models/instances`
2. Find the desired model instance ID
3. Call the set default endpoint
4. Restart app container to reload: `docker compose restart app`

### Method 2: Via Environment Variable (Requires Rebuild)

**Steps:**
1. Update `DEFAULT_MODEL_NAME` in `.env` or `docker-compose.yml`
2. Restart services:
   ```bash
   docker compose down
   docker compose up -d --build
   ```

### Method 3: Via Database Script (Manual)

**Run the initialization script manually:**
```bash
docker compose exec app python scripts/init_default_model.py
docker compose restart app
```

## Verifying Default Model

### Check Database

```sql
-- Find the default model
SELECT 
    instance_name,
    model_id,
    is_default,
    enabled,
    loaded
FROM model_instances
WHERE is_default = true;
```

### Check Application Logs

```bash
docker compose logs app | grep "orchestrator.preferred_model.set"
```

Expected output:
```
orchestrator.preferred_model.set preferred_model=phi3-mini-instruct reason=database_default fallback_mode=never
```

### Check Runtime

**Test the agent run:**
```bash
curl -X POST "http://localhost:8000/v1/agent-runs" \
  -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "List the available tools"
  }'
```

**Check the response `model` field:**
```json
{
  "run_id": "...",
  "status": "running",
  "model": "phi3:mini-instruct",  // ✅ Should match default
  ...
}
```

## RAM Usage Summary

**With single model (`phi3:mini-instruct`):**

| State | RAM Usage |
|-------|-----------|
| Idle (no active inference) | 16 MB |
| During inference | 2.0-2.5 GB |
| Peak with overhead | 2.5-3.0 GB |
| Current limit | 10 GB ✅ |
| Current reservation | 7 GB ✅ |

**Benefit of single model:**
- ✅ No model switching overhead
- ✅ Predictable RAM usage
- ✅ Faster inference (model stays loaded)
- ✅ Simpler debugging (consistent behavior)

## Troubleshooting

### Model not loading

**Check Ollama service:**
```bash
docker compose exec ollama ollama list
```

Expected: `phi3:mini-instruct` in the list

**Pull model if missing:**
```bash
docker compose exec ollama ollama pull phi3:mini-instruct
```

### Wrong model being used

**Check orchestrator logs:**
```bash
docker compose logs app | grep -A 5 "orchestrator.model_registered"
```

**Verify is_default flag:**
```sql
SELECT instance_name, is_default FROM model_instances WHERE enabled=true;
```

**Re-run initialization:**
```bash
docker compose exec app python scripts/init_default_model.py
docker compose restart app
```

### Database connection issues

**Check if migrations ran:**
```bash
docker compose logs app | grep "Running database migrations"
```

**Run migrations manually:**
```bash
docker compose exec app bash -c "cd /app/db/postgres_control && alembic upgrade head"
```

## Best Practices

1. **Always use the API endpoint** to change default model (Method 1)
2. **Verify changes** by checking logs and test runs
3. **Keep only one model as default** (database constraint enforces this)
4. **Use lightweight models** for development/testing
5. **Monitor RAM usage** when changing to larger models
6. **Document changes** in team communications

## See Also

- [Model Instances API Documentation](../api/openapi_v1.json#/models)
- [Orchestrator Architecture](./ORCHESTRATOR_DESIGN.md)
- [Ollama Configuration](./OLLAMA_SETUP.md)
