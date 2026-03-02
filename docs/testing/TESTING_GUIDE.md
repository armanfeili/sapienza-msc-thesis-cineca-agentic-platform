# Testing Guide - Production-Ready Orchestrator

Quick reference for running the comprehensive test suite (35 TODO items).

## Prerequisites

### 1. Rebuild & Start Services

```bash
docker compose up -d --build --remove-orphans
```

### 2. Fetch Auth0 Tokens

```bash
./fetch_auth0_tokens.sh --save-to-env
```

### 3. Verify Health

```bash
# Basic health
curl http://127.0.0.1:8000/health

# Detailed health (wait for all services ready)
curl http://127.0.0.1:8000/v1/health/ready
```

---

## Running Tests

### Unit Tests (TODO #1-25)

Tests orchestrator core logic **without** Docker services.

```bash
docker compose exec -T app bash -c "pytest tests/unit/test_orchestrator_comprehensive.py -v -s --tb=short"
```

**Expected:** 25 tests (may skip if optional dependencies missing)

**Coverage:**
- LLM registry & model selection (7 tests)
- TODO list creation & parsing (4 tests)
- TODO execution & tool discovery (7 tests)
- Step execution & routing (5 tests)
- Metrics & rollup (4 tests)

---

### Integration Tests - API Behavior (TODO #32-35)

Tests HTTP-level behavior with real services.

```bash
docker compose exec -T app bash -c "pytest tests/integration/test_agent_execution.py::TestAgentRunsAPIBehavior -v -s --tb=short"
```

**Expected:** 4 tests (requires Auth0, Redis, PostgreSQL)

**Coverage:**
- Idempotency (Idempotency-Key header)
- Headers (Location, X-Request-Id echo)
- Caching (ETag, 304 Not Modified)
- Ownership (user isolation, admin:all scope)

---

### Full E2E Test (TODO #26-35)

Complete orchestration with LLM, tool discovery, metrics.

```bash
docker compose exec -T app bash -c "pytest tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully -v -s --tb=short 2>&1" | tee test_full_output.log
```

**Expected:** 1 test (~5-15 minutes on CPU)

**Coverage (within E2E test):**
- Run-level timeout (RUN_TIMEOUT_SECONDS)
- Metrics persistence (overall_ms, llm_metrics, tool_metrics)
- Fallback behavior
- Partial results
- Final output override
- Prometheus hooks

---

## Troubleshooting

### Test Fails: "Provider list is empty"

**Cause:** Ollama not ready or no models loaded.

**Fix:**
```bash
docker compose ps ollama
docker compose logs ollama --tail=50
docker compose exec ollama ollama list
```

### Test Fails: "Auth0 tokens not found"

**Cause:** Tokens not in environment.

**Fix:**
```bash
./fetch_auth0_tokens.sh --save-to-env
source .env  # If running outside Docker
```

### Test Fails: "Latency budget exceeded"

**Cause:** CPU too slow for default thresholds.

**Fix:** Increase budget:
```bash
docker compose exec -T app bash -c "COLD_LLM_BUDGET_MS=300000 pytest tests/integration/test_agent_execution.py -v"
```

### Test Fails: "Metrics drift exceeded"

**Cause:** Noisy CI environment, timing variance.

**Fix:** Increase tolerance:
```bash
docker compose exec -T app bash -c "E2E_TOLERANCE_PERCENT=10 pytest tests/integration/test_agent_execution.py -v"
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COLD_LLM_BUDGET_MS` | 180000 | Cold LLM call budget (ms) |
| `E2E_TOLERANCE_PERCENT` | 5 | Metrics drift tolerance (%) |
| `EXPECTED_PROVIDER_COUNT` | - | Validate exact provider count |
| `API_BASE_URL` | http://127.0.0.1:8000 | API endpoint |
| `LLM_WARMUP_ENABLED` | True | Enable LLM warmup |
| `LLM_MAX_STEPS` | 10 | Max TODO items |

---

## Test Markers

```bash
# Run all slow tests (integration + E2E)
pytest -m slow -v

# Skip slow tests (unit tests only)
pytest -m "not slow" -v

# Run specific test class
pytest tests/integration/test_agent_execution.py::TestAgentRunsAPIBehavior -v
```

---

## Continuous Integration

### Recommended CI Configuration

```yaml
# .github/workflows/tests.yml
test-orchestrator:
  runs-on: ubuntu-latest
  steps:
    - name: Start services
      run: docker compose up -d --build --wait
    
    - name: Fetch Auth0 tokens
      run: ./fetch_auth0_tokens.sh --save-to-env
    
    - name: Wait for providers
      run: |
        timeout 120 bash -c 'until curl -s http://127.0.0.1:8000/v1/health/ready | grep -q "ok"; do sleep 5; done'
    
    - name: Run unit tests
      run: docker compose exec -T app pytest tests/unit/test_orchestrator_comprehensive.py -v
    
    - name: Run integration tests
      run: docker compose exec -T app pytest tests/integration/test_agent_execution.py::TestAgentRunsAPIBehavior -v
      env:
        E2E_TOLERANCE_PERCENT: 10  # Higher tolerance for CI
        COLD_LLM_BUDGET_MS: 240000  # 4 minutes for cold CI runners
```

---

## Success Criteria

### ✅ All Tests Pass

- **Unit Tests:** 25/25 passed
- **Integration Tests:** 4/4 passed
- **E2E Test:** 1/1 passed (with all validations)

### ✅ Performance Within Budgets

- Cold LLM call: <180s (or <COLD_LLM_BUDGET_MS)
- Warm LLM call: <10s per 100 tokens
- Metrics drift: <5% (or <E2E_TOLERANCE_PERCENT)

### ✅ All Services Healthy

```bash
curl http://127.0.0.1:8000/v1/health/ready
# Response: {"status": "ok", "checks": {"redis": {"ok": true}, "postgres": {"ok": true}, "ollama": {"ok": true}}}
```

---

## Quick Commands

```bash
# Full test suite (unit + integration + E2E)
docker compose exec -T app bash -c "pytest tests/unit/test_orchestrator_comprehensive.py tests/integration/test_agent_execution.py -v"

# Fast check (unit tests only, ~30 seconds)
docker compose exec -T app bash -c "pytest tests/unit/test_orchestrator_comprehensive.py -v"

# Critical path (integration + E2E, ~15-20 minutes)
docker compose exec -T app bash -c "pytest tests/integration/test_agent_execution.py -v"

# Watch logs while testing
docker compose logs -f app | grep -E "(orchestrator|agent_run)"
```

---

## Next Steps After Tests Pass

1. ✅ **Unit Tests Pass** → Orchestrator logic validated
2. ✅ **Integration Tests Pass** → API behavior validated
3. 🚧 **Implement Orchestrator Enhancements** → Add behaviors validated by tests
4. 🚧 **Update Router** → Ensure headers match test expectations
5. ✅ **Deploy to Production** → All validations passing

**Questions?** See `PRODUCTION_READY_IMPLEMENTATION_COMPLETE.md` for detailed documentation.
