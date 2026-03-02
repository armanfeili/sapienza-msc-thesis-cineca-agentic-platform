# Quick Implementation Guide: Remaining Improvements

## 1. Complete Step Timestamps (30 minutes)

### Add timestamps to 8 locations in `src/services/orchestrator.py`:

**Pattern to apply**:
```python
from datetime import datetime, timezone

def _add_step_with_timestamps(step_id, action, output, error=None):
    started = datetime.now(timezone.utc)
    # ... execute action ...
    finished = datetime.now(timezone.utc)
    
    result.outputs.append({
        "step_id": step_id,
        "action": action,
        "output": output,
        "error": error,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat()
    })
```

**Locations** (line numbers approximate):
1. Line ~1389: `catalog.discover` output
2. Line ~1456: Storage step output
3. Line ~1468: Error output
4. Line ~1513: Format step output
5. Line ~1543: TODO execution output
6. Line ~1569: Another error output
7. Line ~1757: TODO creation output
8. Line ~1784: Final tools output

---

## 2. Decoded Output (45 minutes)

### Step 1: Create Migration
```sql
-- db/migrations/006_change_output_to_jsonb.sql
ALTER TABLE agent_runs ALTER COLUMN output TYPE JSONB USING output::jsonb;
COMMENT ON COLUMN agent_runs.output IS 'Agent run output (structured data)';
```

### Step 2: Update Router
```python
# src/routers/agent_runs.py - In get_agent_run endpoint
output_data = run.output
if isinstance(output_data, str):
    try:
        output_data = json.loads(output_data)
    except:
        pass  # Keep as string if parse fails

# Return decoded
return RunResponse.model_validate({...run, "output": output_data})
```

### Step 3: Update Agent Run Creation
```python
# src/routers/agent_runs.py - Lines 325-335
# Change from:
final_output_text = json.dumps(to_jsonable(step.output))

# To:
final_output_obj = to_jsonable(step.output)
```

### Step 4: Update Repository
```python
# db/postgres_control/repositories/agents.py
# update_status() - Line ~645
# Change output parameter handling to accept dict
if output is not None:
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except:
            pass  # Keep as string
    run.output = output
```

---

## 3. Metrics Population (60 minutes)

### Step 1: Track Metrics During Execution

```python
# src/services/orchestrator.py - Add to OrchestrationResult
class OrchestrationResult:
    def __init__(self):
        self.llm_metrics = []  # Track LLM calls
        self.tool_metrics = []  # Track tool calls
```

### Step 2: Instrument LLM Calls
```python
# Around line ~1150 (todo_list creation)
llm_start = time.time()
response = await self.llm_clients[model].chat_completion(...)
llm_latency = int((time.time() - llm_start) * 1000)

result.llm_metrics.append({
    "model": model,
    "latency_ms": llm_latency,
    "input_tokens": response.usage.prompt_tokens if response.usage else None,
    "output_tokens": response.usage.completion_tokens if response.usage else None,
})
```

### Step 3: Instrument Tool Calls
```python
# Around line ~1850 (tool execution)
tool_start = time.time()
try:
    output = await tool_func(**args)
    success = True
except Exception as e:
    success = False
finally:
    tool_latency = int((time.time() - tool_start) * 1000)
    result.tool_metrics.append({
        "name": tool_name,
        "latency_ms": tool_latency,
        "success": success
    })
```

### Step 4: Populate Metrics in Router
```python
# src/routers/agent_runs.py - After orchestration completes
metrics_data = {
    "overall_ms": latency_ms,
    "llm": result.data.get("llm_metrics", []),
    "tools": result.data.get("tool_metrics", []),
}

AgentRunRepository.update_status(
    ...,
    metrics=metrics_data  # Add this parameter
)
```

### Step 5: Update Repository
```python
# db/postgres_control/repositories/agents.py
def update_status(..., metrics: dict | None = None):
    if metrics is not None:
        run.metrics = metrics
```

---

## 4. Fix Latency Display (5 minutes)

```python
# tests/integration/test_agent_execution.py - After completion

if final_status in ["succeeded", "failed", "cancelled"]:
    # Calculate actual run duration from timestamps
    started_str = status_data.get('started_at')
    finished_str = status_data.get('finished_at')
    
    if started_str and finished_str:
        from datetime import datetime
        started = datetime.fromisoformat(started_str.replace('Z', '+00:00'))
        finished = datetime.fromisoformat(finished_str.replace('Z', '+00:00'))
        duration_sec = (finished - started).total_seconds()
        elapsed_min = int(duration_sec // 60)
        elapsed_sec = int(duration_sec % 60)
    else:
        elapsed_min = attempt // 60
        elapsed_sec = attempt % 60
    
    print(f"✅ Agent run completed with status: {final_status} (took {elapsed_min}m {elapsed_sec}s)")
```

---

## 5. Fix Seed Provider Log (2 minutes)

```bash
# Find the log statement
grep -n "seed_provider.skip" src/app.py

# Change from log.info to log.debug
# Before:
log.info("seed_provider.skip", ...)

# After:
log.debug("seed_provider.skip", reason="...")
```

---

## Testing Checklist

After each improvement, run:

```bash
# 1. Restart app
docker compose restart app && sleep 15

# 2. Run integration test
docker compose exec -T app python -m pytest \
  tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully \
  -xvs --tb=short

# 3. Verify improvements with API
export AUTH0_ADMIN_TOKEN='...'  # From fetch_auth0_tokens.sh
RUN_ID='...'  # From test output

curl -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  http://localhost:8000/v1/agent-runs/$RUN_ID | jq '{
    trace_id,
    warnings,
    started_at,
    finished_at,
    output: (.output | if type == "string" then fromjson else . end),
    metrics,
    steps: [.steps[] | {type, step_id, started_at, finished_at}]
  }'
```

---

## Validation Criteria

### Step Timestamps ✓
- All outputs have `started_at` and `finished_at`
- Timestamps are RFC3339 with Z suffix
- Tool calls show individual latency

### Decoded Output ✓
- API returns `output` as object, not string
- `tools_count`, `tools`, `source_groups` directly accessible
- No client-side JSON parsing needed

### Metrics ✓
- `metrics` object populated (not null)
- LLM metrics include token counts and latency
- Tool metrics include success/failure and latency
- Overall latency matches `latency_ms`

### Latency Display ✓
- Test shows correct run duration
- Calculated from `finished_at - started_at`
- Not from polling loop counter

### Log Noise ✓
- `seed_provider.skip` at debug level
- No duplicate model registration logs
- Clean INFO-level output

---

## Time Estimate

- Step Timestamps: **30 min**
- Decoded Output: **45 min**
- Metrics Population: **60 min**
- Latency Display: **5 min**
- Seed Provider Log: **2 min**

**Total**: ~2.5 hours for complete implementation

---

## Priority Order

1. **Step Timestamps** (highest value for debugging)
2. **Decoded Output** (better API UX)
3. **Metrics** (observability)
4. **Latency Display** (test UX)
5. **Seed Log** (cosmetic)
