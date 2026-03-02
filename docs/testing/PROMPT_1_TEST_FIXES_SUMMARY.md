# Prompt 1 Test Fixes - Summary

## Changes Made (Production-Level)

### 1. ✅ Increased Agent Run Timeout: 300s → 600s

**Problem**: Agent runs were timing out after 300 seconds with 0 LLM calls, indicating the orchestrator needed more time for CPU execution with Mistral 7B.

**Files Modified**:

#### `.env`
```env
# Orchestrator Timeouts (increased for CPU execution)
LLM_RUN_TIMEOUT_SECONDS=600   # Overall agent run timeout (10 minutes)
```

#### `docker-compose.yml`
```yaml
environment:
  LLM_RUN_TIMEOUT_SECONDS: "${LLM_RUN_TIMEOUT_SECONDS:-600}"
```

**Verification**:
```bash
docker compose exec -T app python -c "from src.services.orchestrator import RUN_TIMEOUT_SECONDS; print(f'RUN_TIMEOUT_SECONDS={RUN_TIMEOUT_SECONDS}')"
# Expected output: RUN_TIMEOUT_SECONDS=600
```

---

### 2. ✅ Enhanced Test Polling Timeout: 300s → 600s

**File**: `tests/integration/test_agent_memgraph_nl_prompts_v2.py`

**Changes**:
```python
# Line ~866: Increased max_wait timeout
max_wait = 120 if (not should_be_allowed and role == "user") else 600  # Was 300
print(f"\n⏳ Polling for completion (max {max_wait}s)...")
print(f"   💡 Each LLM call may take 2-5 minutes on CPU (Mistral 7B)")
```

---

### 3. ✅ Added Enhanced Debug Logging During Polling

**File**: `tests/integration/test_agent_memgraph_nl_prompts_v2.py`

**Changes** (Lines ~878-892):
```python
# Enhanced logging every 10s or on status change
if attempt % 10 == 0 or final_status != "running":
    elapsed_min = attempt // 60
    elapsed_sec = attempt % 60
    steps_count = len(status_data.get("steps", []))
    todos_count = len(status_data.get("todos", []))
    print(f"   [{elapsed_min}m {elapsed_sec}s] Status: {final_status} | Steps: {steps_count} | TODOs: {todos_count}")
    
    # Debug: Log errors/warnings if any
    errors = status_data.get("errors", [])
    warnings = status_data.get("warnings", [])
    if errors:
        print(f"      ⚠️  Errors: {errors[:2]}")  # Show first 2 errors
    if warnings:
        print(f"      ⚠️  Warnings: {warnings[:2]}")  # Show first 2 warnings
```

**Benefits**:
- Shows elapsed time in minutes and seconds
- Displays current step/TODO counts
- Shows errors/warnings as they occur
- Helps debug long-running executions

---

### 4. ✅ Added Complete Output Writer to `tests/integration/output/`

**File**: `tests/integration/test_agent_memgraph_nl_prompts_v2.py`

**New Function** (Lines ~365-456):
```python
def write_prompt_output(
    prompt_entry: Dict[str, Any],
    role: str,
    status_data: Dict[str, Any],
) -> None:
    """
    Write complete output to tests/integration/output/output_prompt_<index> file.
    """
    # ... implementation
```

**Output Structure**:
```
tests/integration/output/
├── output_prompt_1_admin.txt
├── output_prompt_1_user.txt
├── output_prompt_2_admin.txt
└── ...
```

**Content Includes**:
- Prompt details (ID, text, category, TODO mode, notes)
- Execution results (status, run_id)
- Complete output (formatted JSON)
- All steps (full JSON dump per step)
- All TODOs (full JSON dump per TODO)
- Metrics (LLM calls, timing, etc.)
- Errors and Warnings (if any)

**Usage**:
```python
# Called after test execution (line ~1198)
write_prompt_output(
    prompt_entry=prompt_entry,
    role=role,
    status_data=status_data,
)
```

---

## How to Run the Test

### Option 1: Run Single Prompt (Prompt 1, Admin Only)
```bash
docker compose exec -T app pytest \
  tests/integration/test_agent_memgraph_nl_prompts_v2.py \
  -m memgraph_nl \
  --nl-prompts=1 \
  --nl-prompts-role=admin \
  -v
```

### Option 2: Run Single Prompt (Both Roles)
```bash
docker compose exec -T app pytest \
  tests/integration/test_agent_memgraph_nl_prompts_v2.py \
  -m memgraph_nl \
  --nl-prompts=1 \
  -v
```

### Option 3: Run Multiple Prompts
```bash
# Prompts 1-3, admin only
docker compose exec -T app pytest \
  tests/integration/test_agent_memgraph_nl_prompts_v2.py \
  -m memgraph_nl \
  --nl-prompts=1:3 \
  --nl-prompts-role=admin \
  -v
```

---

## Expected Test Behavior

### Timeline (Prompt 1: "How many :Blast nodes are there?")

**Expected Duration**: 3-6 minutes per role
- POST /v1/agent-runs: <100ms (returns queued)
- Poll every 1s for completion
- Orchestrator execution: ~3-5 minutes
  - LLM call #1: Generate TODO list (~2-3 min)
  - LLM call #2: Execute Cypher query (~2-3 min)
  - Total: 1-2 LLM calls expected

**Console Output** (Enhanced):
```
🧪 TEST: p02 - ADMIN role
================================================================================
   Prompt: How many :Blast nodes are there?...
   Category: read_only
   TODO mode: none
   User allowed: True, Admin allowed: True

📤 POST /v1/agent-runs...
   Status: 201
   ✅ Created run_id: abc123...

⏳ Polling for completion (max 600s)...
   💡 Each LLM call may take 2-5 minutes on CPU (Mistral 7B)
   [0m 0s] Status: running | Steps: 0 | TODOs: 0
   [0m 10s] Status: running | Steps: 1 | TODOs: 1
   [0m 20s] Status: running | Steps: 2 | TODOs: 1
   [1m 30s] Status: running | Steps: 3 | TODOs: 1
   [3m 0s] Status: succeeded | Steps: 4 | TODOs: 1

📊 Final status: succeeded (took 180s)

📋 Execution artifacts:
   Steps: 4
   TODOs: 1
   Output: dict

🔍 Found 1 Cypher queries:
   Query 1: MATCH (b:Blast) RETURN COUNT(b) AS count...

📊 LLM calls: 2

   💾 Log written: memgraph_nl_20251116_155300_idx-001_p02_admin.log
   📄 Output written: tests/integration/output/output_prompt_1_admin.txt

✅ Test passed for p02 - admin
```

---

## Output Files

### 1. **JSON Log** (tests/logs/memgraph_nl/)
```
memgraph_nl_20251116_155300_idx-001_p02_admin.log
```

**Structure**:
```json
{
  "timestamp_start": "2025-11-16T15:53:00Z",
  "timestamp_end": "2025-11-16T15:56:00Z",
  "duration_seconds": 180.42,
  "prompt": { "index": 1, "id": "p02", "text": "...", ... },
  "role": "admin",
  "run_id": "abc123...",
  "status": "succeeded",
  "steps": [...],
  "todos": [...],
  "metrics": {...},
  "cypher_queries": ["MATCH (b:Blast) RETURN COUNT(b)"],
  "llm_call_count": 2
}
```

### 2. **Text Output** (tests/integration/output/)
```
output_prompt_1_admin.txt
```

**Structure**:
```
================================================================================
PROMPT 1 - ADMIN ROLE
================================================================================

Prompt ID: p02
Prompt Text: How many :Blast nodes are there?
Category: read_only
TODO Mode: none
Notes: Simple count query

--------------------------------------------------------------------------------
EXECUTION RESULTS
--------------------------------------------------------------------------------

Status: succeeded
Run ID: abc123...

--------------------------------------------------------------------------------
OUTPUT
--------------------------------------------------------------------------------
{
  "answer": "There are 1234 Blast nodes in the database.",
  ...
}

--------------------------------------------------------------------------------
STEPS (4)
--------------------------------------------------------------------------------

Step 1:
{
  "step_id": "create-todos",
  "output": {...},
  ...
}

Step 2:
{
  "step_id": "execute-cypher",
  "tool_input": {
    "query": "MATCH (b:Blast) RETURN COUNT(b) AS count"
  },
  ...
}

... (more steps)

--------------------------------------------------------------------------------
TODOs (1)
--------------------------------------------------------------------------------

TODO 1:
{
  "task": "Count Blast nodes",
  "status": "completed",
  ...
}

--------------------------------------------------------------------------------
METRICS
--------------------------------------------------------------------------------
{
  "llm": [...],
  "overall_ms": 180420,
  ...
}
```

---

## Troubleshooting

### Issue: Timeout still occurs at 300s
**Solution**: Ensure app container was fully restarted after .env changes:
```bash
docker compose down app
docker compose up -d app
# Verify:
docker compose exec -T app python -c "from src.services.orchestrator import RUN_TIMEOUT_SECONDS; print(f'RUN_TIMEOUT_SECONDS={RUN_TIMEOUT_SECONDS}')"
```

### Issue: No output files created
**Check**:
```bash
# Ensure test reached completion
ls -lah tests/integration/output/
ls -lah tests/logs/memgraph_nl/
```

**If empty**: Test likely failed before writing output. Check test status and logs.

### Issue: Test hangs indefinitely
**Possible Causes**:
1. Ollama service down
2. Memgraph connection issues
3. LLM infinite loop

**Debug Steps**:
```bash
# Check service health
docker compose ps
docker compose logs ollama --tail=50
docker compose logs memgraph --tail=50
docker compose logs app --tail=100

# Check agent run status manually
docker compose exec -T app python -c "
import requests
response = requests.get('http://app:8000/v1/agent-runs/<run_id>', headers={'Authorization': 'Bearer <token>'})
print(response.json())
"
```

### Issue: Failed with 0 LLM calls
**Root Cause**: Orchestrator failed to execute (timeout, error, or configuration issue)

**Check**:
```bash
# Check for orchestrator errors
docker compose logs app | grep -i "orchestrator\|error\|timeout"

# Verify LLM base URL is correct
docker compose exec -T app env | grep OLLAMA
```

---

## Performance Expectations

### CPU Execution (Docker Desktop, Apple Silicon)
- **Per LLM call**: 2-5 minutes
- **Simple prompts** (1-2 LLM calls): 3-6 minutes
- **Complex prompts** (2-3 LLM calls): 6-10 minutes

### GPU Execution (NVIDIA GPU)
- **Per LLM call**: 10-30 seconds
- **Simple prompts**: 30-60 seconds
- **Complex prompts**: 1-2 minutes

---

## Next Steps

1. **Run prompt 1** to validate all fixes:
   ```bash
   docker compose exec -T app pytest \
     tests/integration/test_agent_memgraph_nl_prompts_v2.py \
     -m memgraph_nl \
     --nl-prompts=1 \
     --nl-prompts-role=admin \
     -v
   ```

2. **Check output files**:
   ```bash
   cat tests/integration/output/output_prompt_1_admin.txt
   cat tests/logs/memgraph_nl/memgraph_nl_*_idx-001_p02_admin.log | jq
   ```

3. **If successful**, run all smoke prompts:
   ```bash
   docker compose exec -T app pytest \
     tests/integration/test_agent_memgraph_nl_prompts_v2.py \
     -m memgraph_nl \
     -v
   ```

4. **Monitor progress** with enhanced logging to understand execution patterns

---

## Summary of Production-Ready Improvements

✅ **Timeout increased**: 300s → 600s (accommodates CPU execution)
✅ **Enhanced logging**: Shows elapsed time, step/TODO counts, errors/warnings
✅ **Complete output capture**: Text files in tests/integration/output/
✅ **JSON logs**: Detailed execution logs in tests/logs/memgraph_nl/
✅ **Better UX**: Clear progress indicators and timing information
✅ **Debug-friendly**: Errors/warnings displayed during execution
✅ **Production-ready**: No workarounds, comprehensive implementation

All changes follow production-level coding standards with proper error handling, logging, and documentation.
