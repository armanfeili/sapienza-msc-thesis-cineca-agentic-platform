# TODO – Fix orchestrator so memgraph NL test makes LLM calls and does not hang

**Status**: 🚧 In Progress  
**Priority**: Critical  
**Context**: The memgraph NL integration test (`test_nl_prompts_memgraph_rbac_matrix`) currently fails because the orchestrator hangs for 600 seconds during the `building_plan` phase without making any LLM calls. This document outlines the complete fix strategy.

**Current Failure Signature**:
```
"llm_attempted_calls": 0
"llm_successful_calls": 0
"metrics": {"overall_ms": 600040, "llm": [], "tools": [], ...}
"timeout_stage": "unknown"
```

**Root Cause**: The orchestrator executes TODOs using only tool calls (e.g., `graph.schema`, `data.archive`) without ever calling the LLM via `call_model_with_metrics`. Additionally, there's no per-step timeout protection, causing the run to hang until the global 600s run timeout.

---

## A. Inspect and lock down the execution path

### 1. Confirm the agent run flow for the memgraph NL test

- [ ] **File**: `tests/integration/test_agent_memgraph_nl_prompts_v2.py`
  - [ ] Open and locate `_run_single_prompt_test` method (around line 1050)
  - [ ] Find the POST to `/v1/agent-runs` endpoint (around line 1100)
  - [ ] Note the request payload: `{"prompt": prompt_text}`
  - [ ] Confirm test uses prompt ID `p02`: "How many :Blast nodes are there?"

- [ ] **File**: `src/routers/agent_runs.py`
  - [ ] Find the handler `async def create_agent_run(...)` (around line 680)
  - [ ] Trace the flow:
    1. Creates `AgentRun` record in database
    2. Schedules background task: `background_tasks.add_task(execute_agent_run_background, ...)`
  - [ ] Locate `execute_agent_run_background` function (around line 103)
  - [ ] Confirm it:
    - Updates status to "running"
    - Instantiates `Orchestrator.from_env()`
    - Calls `await asyncio.wait_for(orch.run(...), timeout=RUN_TIMEOUT_SECONDS)`

- [ ] **File**: `src/services/orchestrator.py`
  - [ ] Find `async def run(...)` method (around line 2056)
  - [ ] Document the execution stages:
    1. `current_stage = "building_plan"` → creates TODO list
    2. `current_stage = "executing_steps"` → executes each TODO
    3. Generates final summary
  - [ ] Confirm parameters passed from API:
    - `goal`: The user prompt
    - `user_id`, `session_id`, `tenant_id`
    - `params`: May include temperature, max_steps, manager preferences

- [ ] **Verify memgraph NL flow**:
  - [ ] For prompt `p02` ("How many :Blast nodes are there?"):
    - Expected TODO 0: "Initiate a data retrieval process..."
    - Expected TODO 1: "Filter the collected data for specific entities..."
  - [ ] Confirm this is a **normal** agent run (not a special test mode)
  - [ ] Verify planning options: Default orchestrator configuration applies

---

## B. OrchestrationResult – metrics structure

### 2. Ensure OrchestrationResult has a proper metrics dict

- [ ] **File**: `src/services/orchestrator.py`
  - [ ] Locate `class OrchestrationResult` (around line 100)
  - [ ] Verify/add fields:
    ```python
    class OrchestrationResult(BaseModel):
        goal: str
        steps: List[Step] = Field(default_factory=list)
        outputs: List[dict] = Field(default_factory=list)
        todos: List[dict] = Field(default_factory=list)
        warnings: List[str] = Field(default_factory=list)
        errors: List[str] = Field(default_factory=list)
        
        # Metrics fields
        overall_ms: Optional[int] = None
        llm_metrics: List[Dict[str, Any]] = Field(default_factory=list)
        tool_metrics: List[Dict[str, Any]] = Field(default_factory=list)
        model_warmup_ms: Optional[int] = None
        
        # NEW: Top-level metrics dict for API exposure
        metrics: Dict[str, Any] = Field(default_factory=dict)
        
        # Other fields...
        current_stage: Optional[str] = None
        manager: Optional[str] = None
    ```

- [ ] **Update `to_dict()` method** (around line 150):
  - [ ] Ensure returned dict includes complete metrics structure:
    ```python
    def to_dict(self) -> dict[str, Any]:
        # Compute LLM call counts
        total_llm_calls = len(self.llm_metrics)
        llm_attempted = self.metrics.get("llm_attempted_calls", total_llm_calls)
        llm_successful = self.metrics.get("llm_successful_calls", total_llm_calls)
        
        # Compute tool counts
        total_tool_calls = len(self.tool_metrics)
        tool_errors = self.metrics.get("tool_errors", 0)
        
        return {
            "goal": self.goal,
            "steps": self.steps,
            "outputs": self.outputs,
            "todos": self.todos,
            "warnings": self.warnings,
            "errors": self.errors,
            "manager": self.manager,
            "current_stage": self.current_stage,
            
            # Comprehensive metrics dict
            "metrics": {
                "overall_ms": self.overall_ms or 0,
                "llm": self.llm_metrics,
                "tools": self.tool_metrics,
                "model_warmup_ms": self.model_warmup_ms,
                
                # Explicit counters (never None)
                "total_llm_calls": total_llm_calls,
                "llm_call_count": total_llm_calls,
                "llm_attempted_calls": llm_attempted,
                "llm_successful_calls": llm_successful,
                
                "tool_calls": total_tool_calls,
                "tool_errors": tool_errors,
                
                # Timeout stage tracking
                "timeout_stage": self.metrics.get("timeout_stage"),
                
                # Merge any additional metrics
                **self.metrics
            }
        }
    ```

### 3. Ensure metrics dict is populated from internal counters

- [ ] **File**: `src/services/orchestrator.py`
  - [ ] Locate `class Orchestrator` (around line 220)
  - [ ] Add/verify internal counter fields:
    ```python
    class Orchestrator:
        def __init__(self, ...):
            # Existing fields...
            self.llm_call_count: int = 0
            
            # NEW: Detailed tracking counters
            self._llm_attempted_calls: int = 0
            self._llm_successful_calls: int = 0
            self._tool_calls: int = 0
            self._tool_errors: int = 0
            self._timeout_stage: Optional[str] = None
            
            # Internal metrics accumulators
            self._llm_metrics: List[Dict[str, Any]] = []
            self._tool_metrics: List[Dict[str, Any]] = []
    ```

- [ ] **In `Orchestrator.run()` method** (around line 2056):
  - [ ] At the **end** of the method (before returning), populate result metrics:
    ```python
    # Final metrics population
    result.overall_ms = int((time.time() - start_time) * 1000)
    result.llm_metrics = self._llm_metrics
    result.tool_metrics = self._tool_metrics
    
    # Populate metrics dict for API
    result.metrics = {
        "llm_attempted_calls": self._llm_attempted_calls,
        "llm_successful_calls": self._llm_successful_calls,
        "tool_calls": self._tool_calls,
        "tool_errors": self._tool_errors,
        "timeout_stage": self._timeout_stage or "none",
    }
    
    return ServiceResult.ok(result.to_dict())
    ```

---

## C. LLM call instrumentation and counters

### 4. Find the core LLM call wrapper

- [ ] **File**: `src/services/orchestrator.py`
  - [ ] Locate method `async def call_model_with_metrics(...)` (around line 900)
  - [ ] This is the primary wrapper that:
    - Calls the actual LLM adapter
    - Records metrics in `result.llm_metrics`
    - Should increment counters
  - [ ] If missing, also check:
    - `async def call_model(...)`
    - `async def call_model_on(...)`

- [ ] **Trace to LLM adapter**:
  - [ ] File: `src/adapters/llm.py`
  - [ ] Confirm `call_model_with_metrics` eventually calls `await client.complete(...)` from the LLM adapter
  - [ ] Note: The adapter already has httpx timeout configured (600s read timeout)

### 5. Increment LLM counters and log around each call

- [ ] **In `call_model_with_metrics`** (around line 900):
  - [ ] **Before the LLM call**:
    ```python
    # Increment attempt counter
    self._llm_attempted_calls += 1
    
    # Log LLM call start
    log.info(
        "orchestrator.llm_call.start",
        stage=self.current_stage or "unknown",
        attempt=self._llm_attempted_calls,
        model=model or self.default_model,
        prompt_length=len(prompt) if prompt else 0,
    )
    ```

  - [ ] **After successful LLM call**:
    ```python
    # Increment success counter
    self._llm_successful_calls += 1
    
    # Log completion
    log.info(
        "orchestrator.llm_call.completed",
        stage=self.current_stage or "unknown",
        latency_ms=latency_ms,
        response_length=len(response_text) if response_text else 0,
        success=True,
    )
    ```

  - [ ] **On LLM call failure** (in except block):
    ```python
    # Attempt was already incremented; don't increment success
    log.error(
        "orchestrator.llm_call.failed",
        stage=self.current_stage or "unknown",
        error=str(exc),
        elapsed_ms=elapsed_ms,
    )
    ```

- [ ] **In alternative LLM call methods** (`call_model`, `call_model_on`):
  - [ ] Add similar counter increments if these methods are used directly
  - [ ] Ensure all LLM call paths increment `_llm_attempted_calls`

---

## D. Guarantee that planning actually calls the LLM

### 6. Inspect the `plan` method

- [ ] **File**: `src/services/orchestrator.py`
  - [ ] Locate `async def plan(...)` method (around line 1600 or search for `def plan`)
  - [ ] Confirm it:
    - Takes a `goal` or `prompt` parameter
    - Builds a planning prompt (possibly with tool descriptions)
    - Calls `call_model_with_metrics` or similar to invoke the LLM
    - Returns parsed plan/steps

- [ ] **Verify LLM call path**:
  - [ ] The `plan` method should contain:
    ```python
    response = await self.call_model_with_metrics(
        prompt=planning_prompt,
        result=result,
        model=self.default_model,
        temperature=0.3,
        max_tokens=2048,
        ...
    )
    ```
  - [ ] If it doesn't call the LLM, **this is a critical bug** to fix

### 7. Ensure `plan` is used in the memgraph NL flow

- [ ] **Trace TODO creation** (around line 1323 in `_create_agent_todo_list`):
  - [ ] Confirm this method:
    - Calls the LLM to generate a TODO list
    - Uses `call_model_with_metrics` (not just tools)
  - [ ] Current implementation should have:
    ```python
    response = await self.call_model_with_metrics(
        f"{system_prompt}\n\n{user_prompt}",
        result=result,
        model=self.default_model,
        temperature=0.3,
        max_tokens=2048,
        count_call=False,
    )
    ```

- [ ] **Trace TODO execution** (around line 1881 in `_execute_todo_with_steps`):
  - [ ] Find where individual TODOs are executed
  - [ ] Look for code like:
    ```python
    llm_result = await self.plan(todo_prompt, todo_ctx)
    ```
  - [ ] **Current issue**: This may be wrapped in tool-only logic or skipped entirely

- [ ] **Fix: Ensure memgraph NL flow uses LLM**:
  - [ ] **Option A**: Ensure TODO execution calls `plan()` for at least the first TODO
    ```python
    # In _execute_todo_with_steps, for each TODO:
    log.info("orchestrator.todo.executing", index=idx, task=todo["task"])
    
    # Build prompt for this TODO
    todo_prompt = f"Complete this task: {todo['task']}\nGoal: {goal}"
    todo_ctx = OrchestrationContext(...)
    
    # Call plan which uses LLM
    llm_result = await self.plan(todo_prompt, todo_ctx)
    ```

  - [ ] **Option B**: Ensure TODO list creation always uses LLM (already implemented in `_create_agent_todo_list`)

  - [ ] **Verify**: At least **one** of these code paths is hit for prompt `p02`

- [ ] **Test locally** (after implementing):
  - [ ] Add a log statement: `log.info("orchestrator.using_plan_for_todo", index=idx)`
  - [ ] Run the test and grep logs for this event

---

## E. Per-step timeout around planning and long operations

### 8. Add per-step timeout for `plan` calls (step timeout)

- [ ] **File**: `src/services/orchestrator.py`
  - [ ] Locate TODO execution loop in `_execute_todo_with_steps` (around line 1495)
  - [ ] Find where `await self.plan(todo_prompt, todo_ctx)` is called
  - [ ] **Wrap in `asyncio.wait_for`**:
    ```python
    try:
        log.info(
            "orchestrator.todo.plan.start",
            index=idx,
            task=todo["task"],
            timeout_seconds=self._compute_config.step_timeout_seconds,
        )
        
        llm_result = await asyncio.wait_for(
            self.plan(todo_prompt, todo_ctx),
            timeout=self._compute_config.step_timeout_seconds,
        )
        
        log.info(
            "orchestrator.todo.plan.completed",
            index=idx,
            elapsed_ms=(time.time() - step_start) * 1000,
        )
    except asyncio.TimeoutError:
        # Handle timeout (see next item)
        ...
    ```

- [ ] **Add stage tracking helper** (optional but recommended):
  - [ ] Create context manager or simple logging wrapper:
    ```python
    def _set_stage(self, stage: str, **kwargs):
        """Update current stage and log."""
        self.current_stage = stage
        log.info("orchestrator.stage", stage=stage, **kwargs)
    ```
  - [ ] Use before each major operation:
    ```python
    self._set_stage("execute_todo", index=idx)
    ```

### 9. Handle step timeout cleanly

- [ ] **In the `except asyncio.TimeoutError` block**:
  ```python
  except asyncio.TimeoutError:
      # Record timeout details
      self._timeout_stage = f"execute_todo[{idx}]"
      timeout_secs = self._compute_config.step_timeout_seconds
      
      # Log the timeout
      log.error(
          "orchestrator.step.timeout",
          stage=f"execute_todo[{idx}]",
          task=todo["task"],
          timeout_seconds=timeout_secs,
          elapsed_ms=(time.time() - step_start) * 1000,
      )
      
      # Add to errors collection
      result.errors.append(
          f"Step {idx} timed out after {timeout_secs}s: {todo['task']}"
      )
      
      # Abort further execution
      result.current_stage = "failed_timeout"
      log.warning("orchestrator.execution.aborted", reason="step_timeout")
      
      # Don't process remaining TODOs
      break
  ```

- [ ] **After the TODO loop**, check if we hit timeout:
  ```python
  # After TODO execution loop
  if self._timeout_stage:
      # Early exit with failure status
      result.overall_ms = int((time.time() - start_time) * 1000)
      result.metrics = {
          "llm_attempted_calls": self._llm_attempted_calls,
          "llm_successful_calls": self._llm_successful_calls,
          "tool_calls": self._tool_calls,
          "tool_errors": self._tool_errors,
          "timeout_stage": self._timeout_stage,
      }
      return ServiceResult.error(
          "Orchestration failed due to step timeout",
          details=result.to_dict(),
      )
  ```

### 10. Apply similar timeout to initial planning / TODO creation

- [ ] **In `Orchestrator.run()`** (around line 2110):
  - [ ] Find the call to `_create_agent_todo_list`:
    ```python
    todos = await self._create_agent_todo_list(goal, ctx, result)
    ```

  - [ ] **Wrap with timeout**:
    ```python
    try:
        log.info(
            "orchestrator.planning.start",
            goal=goal[:100],
            timeout_seconds=self._compute_config.step_timeout_seconds,
        )
        
        todos = await asyncio.wait_for(
            self._create_agent_todo_list(goal, ctx, result),
            timeout=self._compute_config.step_timeout_seconds,
        )
        
        log.info(
            "orchestrator.planning.completed",
            todos_count=len(todos),
        )
    except asyncio.TimeoutError:
        self._timeout_stage = "planning.todo_list"
        
        log.error(
            "orchestrator.planning.timeout",
            timeout_seconds=self._compute_config.step_timeout_seconds,
        )
        
        result.errors.append(
            f"Planning timed out after {self._compute_config.step_timeout_seconds}s"
        )
        result.current_stage = "failed_timeout"
        result.overall_ms = int((time.time() - start_time) * 1000)
        result.metrics = {
            "llm_attempted_calls": self._llm_attempted_calls,
            "llm_successful_calls": self._llm_successful_calls,
            "timeout_stage": self._timeout_stage,
            "tool_calls": 0,
            "tool_errors": 0,
        }
        
        return ServiceResult.error(
            "Planning phase timed out",
            details=result.to_dict(),
        )
    ```

---

## F. Make sure failures with LLM attempts are visible as such

### 11. Ensure metrics reflect LLM attempts on failure

- [ ] **In all failure paths** (timeout, exception, tool error):
  - [ ] Always populate `result.metrics` before returning:
    ```python
    # Common metrics population for any exit path
    result.overall_ms = int((time.time() - start_time) * 1000)
    result.llm_metrics = self._llm_metrics
    result.tool_metrics = self._tool_metrics
    
    result.metrics = {
        "llm_attempted_calls": self._llm_attempted_calls,
        "llm_successful_calls": self._llm_successful_calls,
        "tool_calls": self._tool_calls,
        "tool_errors": self._tool_errors,
        "timeout_stage": self._timeout_stage or "none",
    }
    ```

- [ ] **Verify no `None` values**:
  - [ ] Use `or 0` for counters: `self._llm_attempted_calls or 0`
  - [ ] Use `or []` for lists: `self._llm_metrics or []`
  - [ ] Use `or "none"` for strings: `self._timeout_stage or "none"`

### 12. Propagate metrics into API response

- [ ] **File**: `src/routers/agent_runs.py`
  - [ ] In `execute_agent_run_background` (around line 180):
  - [ ] After orchestrator completes, extract metrics:
    ```python
    # After: result = await asyncio.wait_for(orch.run(...), timeout=RUN_TIMEOUT_SECONDS)
    
    if result.is_ok():
        result_dict = result.unwrap()
        metrics_data = result_dict.get("metrics", {})
        
        # Ensure all fields present
        if not metrics_data:
            metrics_data = {
                "overall_ms": result_dict.get("overall_ms", 0),
                "llm": result_dict.get("llm_metrics", []),
                "tools": result_dict.get("tool_metrics", []),
                "total_llm_calls": len(result_dict.get("llm_metrics", [])),
                "llm_attempted_calls": 0,
                "llm_successful_calls": 0,
                "tool_calls": 0,
                "tool_errors": 0,
                "timeout_stage": None,
            }
    ```

  - [ ] Store metrics in database:
    ```python
    AgentRunRepository.update_status(
        db,
        run_id=run_id,
        status="succeeded" if success else "failed",
        output=output_text,
        steps=steps_data,
        todos=todos_data,
        errors=errors_list,
        warnings=warnings_list,
        metrics=metrics_data,  # Pass the complete metrics dict
        # ... other fields
    )
    ```

- [ ] **Verify GET endpoint returns metrics** (around line 950):
  - [ ] In `get_agent_run` handler:
  - [ ] Ensure the response includes metrics from the database:
    ```python
    response = RunResponse.model_validate(run)
    # Metrics should be in run.metrics from database
    # Or computed from run.llm_metrics, run.tool_metrics if stored separately
    ```

---

## G. Sanity checks before running the integration test

### 13. Local quick sanity checks

- [ ] **Code formatting**:
  ```bash
  cd /app
  ruff check src/services/orchestrator.py src/routers/agent_runs.py
  black --check src/services/orchestrator.py src/routers/agent_runs.py
  ```

- [ ] **Syntax validation**:
  ```bash
  docker compose exec app python -m compileall src/services/orchestrator.py
  docker compose exec app python -m compileall src/routers/agent_runs.py
  ```

- [ ] **Import check**:
  ```bash
  docker compose exec app python -c "from src.services.orchestrator import Orchestrator; print('OK')"
  ```

- [ ] **Quick manual test** (optional):
  ```bash
  # Create a simple agent run via API
  docker compose exec app curl -X POST http://localhost:8000/v1/agent-runs \
    -H "Authorization: Bearer $AUTH0_MACHINE_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "What tools are available?"}' | jq
  
  # Check if it runs without crashing
  # Check logs for new instrumentation events
  docker compose logs app --tail=50 | grep orchestrator
  ```

---

## H. Run the memgraph NL integration test (only after all TODOs above)

### 14. Only now run the slow integration test once

- [ ] **Prerequisites**:
  - [ ] All items 1–13 are implemented ✅
  - [ ] Code is committed to version control
  - [ ] Containers are rebuilt: `docker compose up -d --build`

- [ ] **Run the test**:
  ```bash
  cd "/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform"
  
  docker compose exec -T app pytest \
    tests/integration/test_agent_memgraph_nl_prompts_v2.py::TestAgentMemgraphNLPrompts::test_nl_prompts_memgraph_rbac_matrix \
    --nl-prompts=1 --nl-prompts-role=admin -v -s --tb=short \
    2>&1 | tee /tmp/memgraph_test_output_final.log
  ```

- [ ] **Success criteria**:
  - [ ] ✅ Test does **NOT** fail with: "Run failed before first LLM call (0 LLM calls)"
  - [ ] ✅ Test output shows: `llm_call_count >= 1`
  - [ ] ✅ Test output shows: `metrics["llm"]` is a non-empty list
  - [ ] ✅ Test output shows: `timeout_stage` is NOT "unknown" (should be "none" or a specific stage)
  - [ ] ✅ Run completes within reasonable time (not 600s unless actually needed)

- [ ] **If test still fails**:
  - [ ] Check logs for new instrumentation events:
    ```bash
    docker compose logs app --since 15m | grep -E "(orchestrator\.(planning|llm_call|todo|stage))"
    ```
  - [ ] Review test output for specific assertion failures
  - [ ] Check metrics structure in test output
  - [ ] If still 0 LLM calls:
    - [ ] Verify `_create_agent_todo_list` is being called
    - [ ] Verify `call_model_with_metrics` is being reached
    - [ ] Add more debug logs in the execution path

- [ ] **Expected test outcome**:
  - [ ] If all fixes are correct: **Test passes** ✅
  - [ ] If test fails on Cypher validation: That's a **different issue** (LLM call issue is fixed)
  - [ ] If test fails on RBAC: That's a **different issue** (LLM call issue is fixed)

---

## Summary Checklist

Before running the test, ensure:

- [x] ✅ `OrchestrationResult.metrics` dict is properly defined
- [ ] ✅ LLM call counters (`_llm_attempted_calls`, `_llm_successful_calls`) exist and are incremented
- [ ] ✅ Structured logging added around all LLM calls
- [ ] ✅ `plan()` method is verified to call LLM
- [ ] ✅ TODO execution for memgraph NL uses `plan()` (calls LLM)
- [ ] ✅ Per-step timeout added around `plan()` calls
- [ ] ✅ Planning timeout added around `_create_agent_todo_list()`
- [ ] ✅ Timeout errors set `_timeout_stage` and abort execution early
- [ ] ✅ All failure paths populate `result.metrics` properly
- [ ] ✅ API response propagates metrics to GET `/v1/agent-runs/{run_id}`
- [ ] ✅ Code passes linting and syntax checks
- [ ] ✅ Quick manual test confirms no immediate crashes

**Only then**: Run the full integration test.

---

## Notes

- **Do NOT modify test assertions**: The test's expectation of `llm_call_count >= 1` is correct; fix the orchestrator, not the test.
- **Do NOT modify timeout configuration**: The 540s step / 600s run timeouts in `compute.py` are already correct.
- **Do NOT modify LLM adapter**: The httpx timeout (600s read) in `llm.py` is already correct.
- **Focus on orchestrator execution flow**: The bug is that the orchestrator hangs without calling the LLM.

---

**Document Version**: 1.0  
**Created**: 2025-11-17  
**Last Updated**: 2025-11-17
