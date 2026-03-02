# Agent Run Fixes Summary

**Date**: November 13, 2025  
**Test**: `test_agent_memgraph_nl_prompts.py::TestAgentMemgraphNLPrompts::test_nl_prompts_memgraph_rbac_matrix[admin-prompt_entry0]`

## Issues Fixed ✅

### 1. Database Constraint Issue - `'queued'` Status Not Allowed
**Problem**: The database check constraint only allowed statuses: `'running', 'succeeded', 'failed', 'cancelled'`  
But the code was trying to set status to `'queued'`.

**Error**:
```
psycopg2.errors.CheckViolation: new row for relation "agent_runs" violates check constraint "agent_runs_status_check"
```

**Files Modified**:
- `db/postgres_control/models/agent_run.py` - Updated constraint to include `'queued'`
- `db/postgres_control/alembic/versions/008_create_agent_tables.py` - Updated migration
- `db/postgres_control/alembic/versions/021_add_queued_status_to_agent_runs.py` - New migration

**Fix Applied**:
```python
# Updated constraint
CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="agent_runs_status_check")

# Updated default
status = Column(String(50), nullable=False, default="queued", server_default="queued")
```

**Database Updated**:
```sql
ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_status_check;
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled'));
ALTER TABLE agent_runs ALTER COLUMN status SET DEFAULT 'queued';
```

---

### 2. Invalid Parameter `started_at` in `update_status()` Call
**Problem**: The background function was calling `AgentRunRepository.update_status()` with a `started_at` parameter that doesn't exist.

**Error**:
```
AgentRunRepository.update_status() got an unexpected keyword argument 'started_at'
```

**File Modified**: `src/routers/agent_runs.py`

**Fix Applied**:
```python
# Before:
AgentRunRepository.update_status(
    db,
    run_id=run_id,
    status="running",
    started_at=datetime.now(timezone.utc),  # ❌ This parameter doesn't exist
)

# After:
AgentRunRepository.update_status(
    db,
    run_id=run_id,
    status="running",  # ✅ started_at is set automatically when run is created
)
```

---

## Current Issue ❌ - Orchestrator Hangs Indefinitely

### Symptoms:
1. Agent run creates successfully with status `'queued'` ✅
2. Background task starts and updates status to `'running'` ✅
3. Orchestrator initializes and registers all tools ✅
4. Orchestrator creates TODO list (3 items) ✅
5. **Orchestrator starts executing first TODO but never completes** ❌
6. No error messages in logs ❌
7. Run stays in `'running'` status indefinitely ❌
8. Database shows empty `steps` and `todos` arrays ❌

### Timeline of Execution:
```
17:00:52 - Run created (status='queued')
17:00:53 - Background task started
17:00:53 - Status updated to 'running'
17:00:53 - Orchestrator model warmup starts
17:02:43 - Orchestrator creates TODO list (3 items)
17:02:44 - Starts executing TODO #1: "Identify the database containing Blast node information"
17:02:45 - Makes first LLM call
17:02:46 - Model warmup completes (110 seconds)
17:02:46+ - NO MORE ORCHESTRATOR LOGS
17:11:06 - Test times out after 600 seconds
```

### Database State:
```sql
run_id                                | b3d94168-c7fd-4345-bcb4-47e6faa1617d
status                                | running
started_at                            | 2025-11-13 17:00:52.994111+00
finished_at                           | NULL
steps                                 | []
todos                                 | []
```

### Logs Show:
- Last orchestrator log: `"orchestrator.todo.executing"` at 17:02:44
- Last LLM HTTP call: `POST http://ollama:11434/v1/chat/completions` at 17:02:45
- After that: Only GET requests for run status (test polling)
- No error logs, no exceptions, no timeout warnings

### Possible Causes:
1. **Infinite loop** in TODO execution logic
2. **Blocking operation** that never completes (e.g., waiting for a lock, network call, etc.)
3. **Deadlock** in database or resource access
4. **Bug in orchestrator** that causes it to hang after first LLM call
5. **Missing await** in async code causing synchronous blocking

### Next Steps to Debug:
1. Add more detailed logging in `src/services/orchestrator.py` around TODO execution
2. Add timeout mechanism for individual TODO execution
3. Check for blocking/synchronous calls in async context
4. Review the orchestrator's `_execute_todo_with_steps()` method
5. Add circuit breaker or timeout for LLM calls
6. Check if there's a while loop that never exits

---

## Test Results:

### Before Fixes:
```
FAILED - HTTP 500: Check constraint violation
```

### After Database/Parameter Fixes:
```
FAILED - TIMEOUT: Agent run did not complete within 600s
Last status: running
LLM calls: 0 (expected 1)
```

### Expected Behavior:
```
PASSED - Agent run completes successfully
Status: succeeded
LLM calls: 1
Final output: Cypher query result with Blast node count
```

---

## Files Modified:

1. ✅ `db/postgres_control/models/agent_run.py`
2. ✅ `db/postgres_control/alembic/versions/008_create_agent_tables.py`
3. ✅ `db/postgres_control/alembic/versions/021_add_queued_status_to_agent_runs.py` (new)
4. ✅ `src/routers/agent_runs.py`

---

## Commands Used:

```bash
# Drop and recreate constraint
docker compose exec -T postgres bash -c "export PGPASSWORD=\$POSTGRES_PASSWORD && psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c \"ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_status_check;\""

docker compose exec -T postgres bash -c "export PGPASSWORD=\$POSTGRES_PASSWORD && psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c \"ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled'));\""

docker compose exec -T postgres bash -c "export PGPASSWORD=\$POSTGRES_PASSWORD && psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c \"ALTER TABLE agent_runs ALTER COLUMN status SET DEFAULT 'queued';\""

# Rebuild containers
docker compose up -d --build --remove-orphans

# Run test
docker compose exec -T app bash -c "pytest 'tests/integration/test_agent_memgraph_nl_prompts.py::TestAgentMemgraphNLPrompts::test_nl_prompts_memgraph_rbac_matrix[admin-prompt_entry0]' -v -s --tb=short 2>&1" | tee agent_memgraph_nl_prompts_full_output.log
```

---

## Conclusion:

✅ **Fixed**: Database constraint and parameter issues  
❌ **Remaining**: Orchestrator hangs indefinitely during TODO execution  
🔍 **Action Required**: Debug orchestrator execution flow to find blocking operation
