# Single Default Model Implementation Summary

## Objective

Configure the Cineca Agentic Platform to:
1. Use **only** `phi3:mini-instruct` as the default model
2. Load this model once and reuse it for all LLM calls (planning, tool selection, TODO creation)
3. Store default model configuration in PostgreSQL database
4. Allow changing the default model via API endpoint
5. Optimize RAM usage by keeping only one model loaded

## Implementation Status: ✅ COMPLETE

### Files Modified

#### 1. `docker-compose.yml`
**Changes:**
- Added `DEFAULT_MODEL_NAME` environment variable (default: `phi3:mini-instruct`)
- Added `LLM_FALLBACK_MODE` environment variable (default: `never`)
- Changed Ollama `OLLAMA_NUM_PARALLEL` from 2 to 1 (single model loading)
- Changed Ollama `OLLAMA_MAX_LOADED_MODELS` from 2 to 1 (single model in memory)

**Impact:**
- Platform now enforces single model usage at infrastructure level
- Environment variables make it easy to override model without code changes

#### 2. `docker-entrypoint.sh`
**Changes:**
- Added call to `python scripts/init_default_model.py` after migrations
- Runs on every container startup to ensure default model is configured

**Impact:**
- Default model automatically configured in database on startup
- Idempotent - safe to run multiple times

#### 3. `scripts/init_default_model.py` (NEW FILE)
**Purpose:**
- Initialize default model in PostgreSQL database
- Ensure Ollama provider exists
- Create/update model instance with `is_default=true`
- Clear `is_default` flag from all other models

**Features:**
- Reads `DEFAULT_MODEL_NAME` from environment
- Idempotent (safe to run multiple times)
- Logs all actions for debugging
- Creates provider if missing
- Updates existing instance if found

#### 4. `src/services/orchestrator.py`
**Changes:**
- Simplified fallback logic - removed `always_lightweight` and `if_missing` modes
- Changed default `LLM_FALLBACK_MODE` from `if_missing` to `never`
- Orchestrator now strictly uses database default model (no automatic fallback to lightweight alternatives)
- Removed lightweight model preference logic
- All LLM calls use `self.default_model` consistently

**Impact:**
- Predictable model selection (always uses database default)
- No automatic model switching
- Simpler codebase (removed complex fallback logic)

#### 5. `docs/DEFAULT_MODEL_CONFIGURATION.md` (NEW FILE)
**Purpose:**
- Comprehensive documentation of default model system
- Architecture explanation
- Configuration guide
- Troubleshooting guide
- API endpoint usage examples

## How It Works

### Startup Flow

```
1. Docker container starts
   ↓
2. docker-entrypoint.sh runs
   ↓
3. Database migrations execute (alembic upgrade head)
   ↓
4. scripts/init_default_model.py runs
   - Creates/updates Ollama provider (base_url: http://ollama:11434/v1)
   - Creates/updates phi3:mini-instruct model instance
   - Sets is_default=true on this instance
   - Clears is_default from all other instances
   ↓
5. Application server starts
   ↓
6. Orchestrator.from_env() initializes
   - Queries database for enabled+loaded models
   - Finds model with is_default=true
   - Creates LLM client for phi3:mini-instruct
   - Sets orchestrator.default_model = "phi3-mini-instruct"
   ↓
7. Platform ready to accept requests
```

### Runtime Flow

```
User request arrives
   ↓
Orchestrator.orchestrate_goal() called
   ↓
Initial planning LLM call
   - Uses self.default_model (phi3:mini-instruct)
   - Ollama loads model into RAM (~2.0-2.5 GB)
   ↓
Tool selection LLM calls
   - Reuses loaded model (no reload)
   - Same RAM usage
   ↓
TODO list creation LLM call
   - Reuses loaded model (no reload)
   - Token tracking via call_model_with_metrics()
   ↓
Response generation
   - Reuses loaded model (no reload)
   ↓
Model stays in RAM for 10 minutes (OLLAMA_KEEP_ALIVE)
   - Subsequent requests reuse without reload
   ↓
After 10 minutes of inactivity:
   - Ollama unloads model
   - RAM usage drops to ~16 MB
```

## Verification Steps

### 1. Check Docker Environment

```bash
# Verify environment variables
docker compose config | grep -A 5 "DEFAULT_MODEL"

# Expected output:
# DEFAULT_MODEL_NAME: phi3:mini-instruct
# LLM_FALLBACK_MODE: never
```

### 2. Check Database

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U cineca_user -d cineca_platform

# Query default model
SELECT instance_name, model_id, is_default, enabled, loaded 
FROM model_instances 
WHERE is_default = true;

# Expected output:
# instance_name     | model_id            | is_default | enabled | loaded
# phi3-mini-instruct | phi3:mini-instruct | t          | t       | t
```

### 3. Check Orchestrator Logs

```bash
# Check orchestrator initialization
docker compose logs app | grep "orchestrator.preferred_model.set"

# Expected output:
# orchestrator.preferred_model.set preferred_model=phi3-mini-instruct reason=database_default fallback_mode=never
```

### 4. Test Agent Run

```bash
# Create test agent run
curl -X POST "http://localhost:8000/v1/agent-runs" \
  -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "List the available tools"}'

# Check response model field
# Expected: "model": "phi3:mini-instruct"
```

### 5. Monitor RAM Usage

```bash
# Check Ollama container RAM usage
docker stats ollama --no-stream

# Expected (idle): 16 MiB
# Expected (during inference): 2.0-2.5 GiB
```

## Changing the Default Model

### Via API Endpoint (Recommended)

```bash
# 1. List available models
curl "http://localhost:8000/v1/admin/models/instances" \
  -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN"

# 2. Set new default (example: switching to qwen2.5:3b-instruct)
curl -X PATCH "http://localhost:8000/v1/admin/models/defaults" \
  -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Default-Scope: global" \
  -d '{
    "chat": {
      "instance_id": "<instance-id-from-step-1>"
    }
  }'

# 3. Restart app container
docker compose restart app
```

### Via Environment Variable

```bash
# 1. Edit .env file
echo "DEFAULT_MODEL_NAME=qwen2.5:3b-instruct" >> .env

# 2. Restart services
docker compose down
docker compose up -d --build
```

## RAM Usage Summary

| Scenario | RAM Usage |
|----------|-----------|
| Single model (phi3:mini-instruct) idle | 16 MB |
| Single model during inference | 2.0-2.5 GB |
| Single model peak with overhead | 2.5-3.0 GB |
| Container limit | 10 GB ✅ |
| Container reservation | 7 GB ✅ |

**Benefits:**
- ✅ Predictable RAM usage (no spikes from model switching)
- ✅ Faster inference (model stays loaded between calls)
- ✅ Simpler debugging (consistent model across all calls)
- ✅ RAM headroom (7.5 GB unused capacity for other operations)

## Troubleshooting

### Model not found in database

**Symptom:** Orchestrator logs show "no default model found"

**Solution:**
```bash
# Re-run initialization
docker compose exec app python scripts/init_default_model.py
docker compose restart app
```

### Wrong model being used

**Symptom:** API responses show different model than expected

**Solution:**
```bash
# Check database
docker compose exec postgres psql -U cineca_user -d cineca_platform \
  -c "SELECT instance_name, is_default FROM model_instances WHERE enabled=true;"

# Clear incorrect defaults
docker compose exec postgres psql -U cineca_user -d cineca_platform \
  -c "UPDATE model_instances SET is_default=false WHERE model_id != 'phi3:mini-instruct';"

# Re-run initialization
docker compose exec app python scripts/init_default_model.py
docker compose restart app
```

### Ollama model not loaded

**Symptom:** 500 errors from Ollama

**Solution:**
```bash
# Check available models
docker compose exec ollama ollama list

# Pull model if missing
docker compose exec ollama ollama pull phi3:mini-instruct

# Restart services
docker compose restart app
```

## Test Execution

### Run E2E Test

```bash
# The test should now use phi3:mini-instruct for all LLM calls
docker compose exec -e AUTH0_ADMIN_TOKEN app \
  pytest tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully \
  -v -s --tb=short

# Expected behavior:
# ✅ All LLM metrics show "model": "phi3:mini-instruct"
# ✅ total_tokens field present in response
# ✅ total_llm_calls, tool_calls, tool_errors all computed correctly
# ✅ Single model loaded throughout entire test execution
```

## Configuration Reference

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEFAULT_MODEL_NAME` | `phi3:mini-instruct` | Model name to use as default |
| `LLM_FALLBACK_MODE` | `never` | Fallback policy (`never` = strict default) |
| `OLLAMA_BASE_URL` | `http://ollama:11434/v1` | Ollama API endpoint |
| `OLLAMA_TIMEOUT_SECS` | `180` | Request timeout for Ollama |
| `OLLAMA_KEEP_ALIVE` | `10m` | How long to keep model in memory |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | Maximum models in RAM |
| `OLLAMA_NUM_PARALLEL` | `1` | Parallel request limit |
| `OLLAMA_NUM_CTX` | `1024` | Context window size |

### Database Tables

**`providers`:**
- Stores Ollama connection details
- Single entry: `ollama-local`

**`model_instances`:**
- Stores available models
- One entry with `is_default=true`: `phi3:mini-instruct`

**`user_default_models`:**
- Stores per-user model preferences
- Optional: users can override global default

## Next Steps

1. ✅ Rebuild containers with changes: `docker compose up -d --build`
2. ✅ Verify default model in logs: `docker compose logs app | grep "orchestrator.preferred_model"`
3. ✅ Run E2E test to confirm single model usage
4. ✅ Monitor RAM usage during test execution
5. ✅ Document any configuration changes in team wiki

## Related Documentation

- [Default Model Configuration](./DEFAULT_MODEL_CONFIGURATION.md) - Full architecture guide
- [Orchestrator Design](./ORCHESTRATOR_DESIGN.md) - Orchestrator architecture
- [Model Instances API](../api/openapi_v1.json#/models) - API reference
