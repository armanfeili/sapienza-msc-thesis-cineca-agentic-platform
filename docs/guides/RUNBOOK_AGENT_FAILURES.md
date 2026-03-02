# Agent Failure Runbook

Operational procedures for diagnosing and resolving agent orchestration failures.

## Quick Reference

| Failure Type | Severity | MTTR Target | First Action |
|--------------|----------|-------------|--------------|
| `todo_plan_timeout` | Medium | 10min | Check CPU/model size |
| `todo_step_timeout` | Medium | 10min | Review step complexity |
| `run_timeout` | High | 5min | Check run configuration |
| `orchestrator_error` | Critical | 2min | Check service health |
| `llm_error` | High | 5min | Verify Ollama/API status |
| `tool_error` | Medium | 10min | Review tool logs |
| `validation_error` | Low | 15min | Check input schema |
| `permission_denied` | Medium | 10min | Review RBAC config |
| `resource_exhausted` | Critical | 2min | Scale resources |
| `rate_limit_exceeded` | Medium | 10min | Adjust rate limits |

## Failure Types

### 1. `todo_plan_timeout`

**Description:** Agent failed to generate TODO plan within timeout period.

**Common Causes:**
- CPU too slow for model size
- Model not warmed up
- Overly complex prompt
- Resource contention

**Symptoms:**
```json
{
  "status": "failed",
  "output": {
    "failure_type": "todo_plan_timeout",
    "message": "TODO planning exceeded timeout (120s)",
    "elapsed_seconds": 120
  },
  "todos_data": []  // Empty or partial
}
```

**Diagnostic Steps:**

1. **Check model warmup status:**
   ```bash
   curl http://localhost:8000/v1/health/config | jq '.models'
   ```
   - Verify warmup_models includes plan model
   - Check startup logs for warmup duration

2. **Review timeout configuration:**
   ```bash
   curl http://localhost:8000/v1/health/config | jq '.timeouts'
   ```
   - CPU should have 120s+ step timeout
   - GPU can use 30-60s

3. **Check resource utilization:**
   ```bash
   docker stats app ollama
   ```
   - Look for CPU throttling
   - Check memory saturation

4. **Examine logs:**
   ```bash
   docker compose logs app --tail=100 | grep -i "todo_plan"
   ```
   - Look for "Planning TODO" messages
   - Check elapsed time vs timeout

**Resolution:**

**Quick Fix (Immediate):**
```bash
# Increase timeout
docker compose exec -T app bash -c "
  export LLM_STEP_TIMEOUT_SECONDS=180
  # Restart needed
"
docker compose restart app
```

**Permanent Fix:**

Option A - Use faster model:
```env
# .env
OLLAMA_PLAN_MODEL=phi3:mini  # Instead of phi3:medium
WARMUP_MODELS=phi3:mini
```

Option B - Increase timeout:
```env
# .env
LLM_STEP_TIMEOUT_SECONDS=180  # From 120
```

Option C - Upgrade to GPU:
```bash
make up-gpu  # Uses GPU profile with 30s timeout
```

**Prevention:**
- Always warmup planning model at startup
- Use phi3:mini for planning on CPU
- Monitor warmup duration metric in Grafana
- Set alerts for planning duration >60s

---

### 2. `todo_step_timeout`

**Description:** Individual TODO step exceeded execution timeout.

**Common Causes:**
- Slow tool execution (database query, API call)
- LLM inference too slow
- Model size too large for hardware
- Network latency to external services

**Symptoms:**
```json
{
  "status": "failed",
  "output": {
    "failure_type": "todo_step_timeout",
    "message": "Step execution exceeded timeout (120s)",
    "step_id": "step_003"
  },
  "steps_data": [
    {"id": "step_001", "status": "completed"},
    {"id": "step_002", "status": "completed"},
    {"id": "step_003", "status": "timeout", "elapsed": 120}
  ]
}
```

**Diagnostic Steps:**

1. **Identify which step timed out:**
   ```bash
   # Get agent run details
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/v1/agent-runs/$RUN_ID | \
     jq '.steps_data[] | select(.status=="timeout")'
   ```

2. **Check step type:**
   - LLM call → Model inference issue
   - Tool call → Tool execution issue
   - Check logs for step details

3. **Review step logs:**
   ```bash
   docker compose logs app | grep -A10 "step_id=$STEP_ID"
   ```

4. **Check tool performance:**
   ```bash
   # If database tool
   docker compose logs postgres | tail -50
   
   # If API tool
   docker compose logs app | grep "tool_call" | grep "duration"
   ```

**Resolution:**

**Quick Fix:**
```bash
# Increase step timeout
docker compose exec -T app bash -c "
  export LLM_STEP_TIMEOUT_SECONDS=180
"
docker compose restart app
```

**Permanent Fix:**

Option A - Optimize tool:
```python
# If custom tool is slow
# Example: Add timeout to external API calls
async def call_external_api(url: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        return await client.get(url)
```

Option B - Use faster model:
```env
# .env
OLLAMA_EXECUTE_MODEL=phi3:mini  # Faster inference
```

Option C - Reduce concurrent calls:
```env
# .env
MAX_CONCURRENT_LLM_CALLS=1  # Reduce contention
```

**Prevention:**
- Monitor step duration metrics
- Set alerts for p95 > 60s on CPU, >15s on GPU
- Add timeouts to all external tool calls
- Use GPU for production workloads

---

### 3. `run_timeout`

**Description:** Entire agent run exceeded maximum duration.

**Common Causes:**
- Too many steps in plan
- Cumulative slow steps
- Run timeout too aggressive
- Infinite loop in planning

**Symptoms:**
```json
{
  "status": "failed",
  "output": {
    "failure_type": "run_timeout",
    "message": "Agent run exceeded timeout (300s)",
    "elapsed_seconds": 301
  },
  "steps_data": [...],  // Partial results
  "todos_data": [...]   // May be complete
}
```

**Diagnostic Steps:**

1. **Check run duration:**
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/v1/agent-runs/$RUN_ID | \
     jq '{duration: .duration_seconds, steps: (.steps_data | length)}'
   ```

2. **Analyze step distribution:**
   ```bash
   # Check step durations
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/v1/agent-runs/$RUN_ID | \
     jq '.steps_data[] | {id, status, duration}'
   ```

3. **Review Grafana metrics:**
   - Check "Agent Run Duration p95" panel
   - Look for outliers
   - Compare to historical baseline

**Resolution:**

**Quick Fix:**
```env
# .env
AGENT_RUN_TIMEOUT_SECONDS=600  # Increase from 300
```

**Permanent Fix:**

Option A - Optimize prompt:
```
Instead of: "Analyze all data in detail"
Use: "Analyze top 10 records"
```

Option B - Use GPU:
```bash
make up-gpu  # 120s run timeout, faster execution
```

Option C - Break into smaller runs:
```python
# Split complex task into multiple agent runs
run1 = await create_agent_run(prompt="Step 1: ...")
run2 = await create_agent_run(prompt="Step 2: ...")
```

**Prevention:**
- Set run timeout to 2.5x expected duration
- Monitor run duration trends
- Alert on runs >80% of timeout
- Review prompts that generate >10 steps

---

### 4. `orchestrator_error`

**Description:** Unexpected error in orchestrator service.

**Common Causes:**
- Unhandled exception in orchestrator
- Database connection failure
- Redis connection failure
- Code bug

**Symptoms:**
```json
{
  "status": "failed",
  "output": {
    "failure_type": "orchestrator_error",
    "message": "Internal orchestrator error: ...",
    "error_type": "ValueError"
  }
}
```

**Diagnostic Steps:**

1. **Check orchestrator logs:**
   ```bash
   docker compose logs app | grep -i "orchestrator" | tail -50
   ```

2. **Check service health:**
   ```bash
   curl http://localhost:8000/v1/health/live
   curl http://localhost:8000/v1/health/ready
   ```

3. **Verify dependencies:**
   ```bash
   docker compose ps
   # All services should be "Up"
   ```

4. **Check error details:**
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/v1/agent-runs/$RUN_ID | \
     jq '.output'
   ```

**Resolution:**

**Immediate:**
```bash
# Restart orchestrator
docker compose restart app

# Check if resolved
curl http://localhost:8000/v1/health/ready
```

**If database issue:**
```bash
# Check Postgres
docker compose logs postgres --tail=50

# Restart if needed
docker compose restart postgres app
```

**If Redis issue:**
```bash
# Check Redis
docker compose logs redis --tail=50

# Restart if needed
docker compose restart redis app
```

**If code bug:**
1. Capture full error from logs
2. Create incident ticket
3. Review recent deployments
4. Consider rollback

**Prevention:**
- Monitor orchestrator error rate
- Set up exception tracking (Sentry)
- Add comprehensive error handling
- Test with chaos engineering

---

### 5. `llm_error`

**Description:** Error communicating with LLM provider.

**Common Causes:**
- Ollama service down
- Model not available
- OpenAI API key invalid
- Rate limit exceeded (OpenAI)
- Network connectivity

**Symptoms:**
```json
{
  "status": "failed",
  "output": {
    "failure_type": "llm_error",
    "message": "LLM request failed: Connection refused",
    "provider": "ollama"
  }
}
```

**Diagnostic Steps:**

1. **Check Ollama health:**
   ```bash
   docker compose ps ollama
   curl http://localhost:11434/api/tags
   ```

2. **Verify model availability:**
   ```bash
   docker compose exec ollama ollama list
   ```

3. **Test model inference:**
   ```bash
   curl http://localhost:11434/api/generate -d '{
     "model": "phi3:mini",
     "prompt": "test",
     "stream": false
   }'
   ```

4. **Check Ollama logs:**
   ```bash
   docker compose logs ollama --tail=100
   ```

**Resolution:**

**If Ollama down:**
```bash
docker compose restart ollama
docker compose logs ollama -f  # Wait for startup
```

**If model missing:**
```bash
docker compose exec ollama ollama pull phi3:mini
```

**If OpenAI API issue:**
```bash
# Verify API key
docker compose exec app bash -c 'echo $OPENAI_API_KEY'

# Test API directly
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**If rate limited:**
- Wait for rate limit reset (check headers)
- Reduce MAX_CONCURRENT_LLM_CALLS
- Switch to Ollama for development

**Prevention:**
- Monitor Ollama uptime
- Set up health check alerts
- Use fallback provider (Ollama + OpenAI)
- Pre-pull all required models
- Add retry logic with backoff

---

### 6. `tool_error`

**Description:** Error executing agent tool.

**Common Causes:**
- Tool bug
- Invalid tool arguments
- External service unavailable
- Permission denied
- Timeout in tool execution

**Symptoms:**
```json
{
  "status": "failed",
  "output": {
    "failure_type": "tool_error",
    "message": "Tool execution failed: memgraph_query",
    "tool_name": "memgraph_query",
    "error": "Connection refused"
  }
}
```

**Diagnostic Steps:**

1. **Identify failed tool:**
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/v1/agent-runs/$RUN_ID | \
     jq '.output.tool_name'
   ```

2. **Check tool service:**
   ```bash
   # If database tool
   docker compose ps memgraph postgres
   
   # If API tool
   docker compose logs app | grep "tool_call" | tail -20
   ```

3. **Review tool logs:**
   ```bash
   docker compose logs app | grep "tool_name=$TOOL_NAME"
   ```

4. **Test tool manually:**
   ```bash
   # Example: Test Memgraph connection
   docker compose exec memgraph mgconsole -c "SHOW DATABASES;"
   ```

**Resolution:**

**If service down:**
```bash
docker compose restart memgraph  # Or affected service
```

**If permission issue:**
- Review RBAC configuration
- Check user permissions in database
- Verify Auth0 roles

**If tool bug:**
1. Capture error details
2. Create incident ticket
3. Disable tool temporarily:
   ```python
   # In tool registry
   # tools = [tool1, tool2, buggy_tool]
   tools = [tool1, tool2]  # Remove buggy_tool
   ```

**Prevention:**
- Add input validation to all tools
- Implement circuit breakers
- Add retry logic for transient failures
- Monitor tool error rates by tool_name
- Test tools in isolation

---

## Log Analysis

### Finding Failures

**All failures in last hour:**
```bash
docker compose logs app --since 1h | \
  grep '"failure_type"' | \
  jq -r '.failure_type' | \
  sort | uniq -c
```

**Failures by type:**
```bash
docker compose logs app --since 1h | \
  grep '"failure_type":"todo_step_timeout"' | \
  jq '{run_id, step_id, elapsed}'
```

**Slow runs (>200s):**
```bash
docker compose logs app | \
  grep '"event":"agent_run_completed"' | \
  jq 'select(.duration_seconds > 200) | {run_id, duration_seconds, status}'
```

### Prometheus Queries

**Failure rate by type (5min):**
```promql
rate(agent_run_failures_total[5m])
```

**Timeout percentage:**
```promql
sum(rate(agent_run_failures_total{failure_type=~".*timeout"}[5m])) 
/ 
sum(rate(agent_run_duration_seconds_count[5m])) * 100
```

**P95 run duration by status:**
```promql
histogram_quantile(0.95, 
  sum by (status, le) (rate(agent_run_duration_seconds_bucket[5m]))
)
```

## Escalation

### When to Escalate

**Escalate to on-call engineer if:**
- Failure rate > 20% for 10 minutes
- Any `orchestrator_error` spike
- `resource_exhausted` errors
- Cascading failures across services
- User-reported issue affecting multiple tenants

### Escalation Checklist

Before escalating:
- [ ] Captured relevant logs (last 500 lines)
- [ ] Checked Grafana dashboards
- [ ] Verified service health
- [ ] Attempted basic resolution steps
- [ ] Documented timeline of events
- [ ] Identified affected users/tenants

Include in escalation:
- Failure type and count
- Time range of incident
- Affected services
- Steps already taken
- Relevant log excerpts
- Prometheus query results
- User impact assessment

## Common Scenarios

### Scenario 1: Mass Timeouts After Deployment

**Symptoms:**
- All runs timing out
- Started after recent deployment
- No hardware changes

**Root Cause:**
- Model not warmed up
- Configuration change
- Code regression

**Resolution:**
```bash
# 1. Check config
curl http://localhost:8000/v1/health/config

# 2. Verify warmup
docker compose logs app | grep "warmup"

# 3. If warmup failed, restart
docker compose restart app

# 4. If still failing, rollback
git checkout previous-version
docker compose up -d --build
```

### Scenario 2: Intermittent Tool Failures

**Symptoms:**
- Tool errors come and go
- Same tool, different results
- No clear pattern

**Root Cause:**
- Network connectivity issues
- External service flaky
- Race condition
- Resource contention

**Resolution:**
```bash
# 1. Check network
docker compose exec app ping -c 3 memgraph

# 2. Check service health
docker stats

# 3. Add retry logic
# In tool code:
@retry(stop=stop_after_attempt(3), wait=wait_exponential())
async def call_tool(...):
    ...

# 4. Monitor closely
docker compose logs -f app | grep "tool_error"
```

### Scenario 3: Gradual Performance Degradation

**Symptoms:**
- Runs getting slower over time
- Started fast, now hitting timeouts
- Memory usage increasing

**Root Cause:**
- Memory leak
- Cache bloat
- Connection pool exhaustion

**Resolution:**
```bash
# 1. Check resource usage
docker stats app ollama

# 2. Restart services
docker compose restart app ollama

# 3. Clear caches
docker compose exec redis redis-cli FLUSHALL

# 4. Monitor memory
watch -n 5 'docker stats --no-stream app'

# 5. If leak confirmed, investigate
# Use memory profiler, review recent changes
```

## Monitoring & Alerts

### Recommended Alerts

**Critical (Page immediately):**
- `orchestrator_error` rate > 1/min for 5min
- Agent run failure rate > 50% for 5min
- Ollama service down for 2min

**High (Slack alert):**
- Agent run failure rate > 20% for 10min
- P95 run duration > 250s for 10min
- Timeout rate > 30% for 10min

**Medium (Email):**
- Todo plan timeout rate > 10% for 30min
- Tool error rate increasing (>5x baseline)
- Warmup duration > 120s

### Grafana Dashboard Panels

Key panels to watch:
1. Success Rate (should be >90%)
2. P95 Run Duration (should be <200s)
3. Failure Rate by Type (should be near 0)
4. Active Runs (queued + running)
5. Timeout Breakdown

## Additional Resources

- [Model Selection Guide](MODEL_SELECTION.md) - Choosing right models
- [Production Readiness Checklist](PROD_READINESS.md) - Deployment prep
- [Agent Run Schema](AGENT_RUN_SCHEMA.md) - Data structure reference
- [Grafana Dashboard](../monitoring/grafana/dashboards/agent_runs.json)
