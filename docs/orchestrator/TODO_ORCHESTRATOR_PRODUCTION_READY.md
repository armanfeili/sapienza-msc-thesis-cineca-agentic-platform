# Orchestrator Production Readiness - Complete TODO List

**Date Created**: November 15, 2025  
**Status**: In Progress  
**Priority**: High - Blocking production deployment

---

## Executive Summary

The orchestrator timeout infrastructure is now working, but several critical issues remain before production readiness:

### ✅ **Completed**
- Timeout enforcement at 3 levels (step, TODO, run)
- Model warmup `keep_alive` parameter fixed
- Basic error logging and status updates
- Run-level timeout triggers correctly (300s)

### ⚠️ **Critical Issues**
1. **Pydantic validation errors** - `OrchestrationStepOutput.output` expects dict, gets string
2. **LLM performance on CPU** - 108s warmup + 120s+ planning for simple queries
3. **Inconsistent error handling** - Error payloads vary across code paths
4. **Zero steps/todos persisted** - Failed runs show empty steps and todos in DB

### 📊 **Current Behavior**
- Test run `7662c21f-...` for "How many :Blast nodes?"
  - TODO #1: Completed (tool discovery)
  - TODO #2: Planning timeout after 120s ❌
  - TODO #3: Started but run timeout at 300s ❌
  - Result: `status='failed'`, `steps=0`, `todos=0`, Pydantic error in output

---

## 0. Current State Analysis

### What's Actually Happening

**Observed Behavior**:
```
1. Run created → status='queued'
2. Status → 'running', TODO list generated (3 TODOs)
3. TODO #0 (tool discovery) → Completed ✅
4. TODO #1 planning → 120s timeout → orchestrator.todo.plan_timeout ❌
5. TODO #2 starts → "Summarize..."
6. 300s elapsed → Run-level timeout ❌
7. DB shows: status='failed', steps=0, todos=0, Pydantic error
```

**Key Metrics**:
- Model warmup: **108,712 ms** (~108 seconds) on CPU for `phi3:mini`
- TODO #2 planning: **>120 seconds** (timeout)
- Total run time: **300 seconds** (timeout)
- Query complexity: **Simple** ("How many :Blast nodes?")

**Problems Identified**:
1. Pydantic validation fails on error output (string vs dict)
2. No steps/todos persisted to DB despite partial execution
3. CPU performance unacceptable for simple queries
4. Warmup happening per-run instead of at startup

---

## 1. Correctness / Bug-Fix TODOs

### 1.1. Fix All `OrchestrationStepOutput` String Outputs 🔴 CRITICAL

**Problem**: Multiple code paths create `OrchestrationStepOutput` with `output=<string>` instead of `output=<dict>`, causing Pydantic validation errors.

**Tasks**:
- [ ] **1.1.1** Search entire codebase for `OrchestrationStepOutput(`
  - Files to check:
    - `src/routers/agent_runs.py` (background error handlers)
    - `src/services/orchestrator.py` (error paths in TODO execution)
    - Any other places creating step outputs
  - Command: `grep -r "OrchestrationStepOutput(" src/`

- [ ] **1.1.2** Audit every instantiation, ensure `output=` is:
  - Either a **dict** (e.g., `{"error": "msg"}`, `{"result": "data"}`)
  - Or explicitly `None`
  - NEVER a plain string

- [ ] **1.1.3** Fix identified error branches:
  - Orchestrator timeout: `"Orchestration timeout after 300s"` → `{"error": "Orchestration timeout after 300s"}`
  - Background execution: `"Background execution failed: ..."` → `{"error": "Background execution failed: ..."}`
  - TODO failures: Ensure error outputs are dicts
  - Step timeouts: Ensure timeout error outputs are dicts

- [ ] **1.1.4** Add unit test `test_orchestration_step_output_rejects_string`:
  ```python
  def test_orchestration_step_output_rejects_string():
      """Ensure OrchestrationStepOutput.output must be dict, not string"""
      with pytest.raises(ValidationError):
          OrchestrationStepOutput(
              step_id="test",
              output="plain string should fail"  # Should raise ValidationError
          )
  ```

- [ ] **1.1.5** Add integration test for error path validation:
  - Force orchestrator timeout
  - Fetch run via `/v1/agent-runs/{id}`
  - Assert `output` is valid dict with error info

**Files to Modify**:
- `src/routers/agent_runs.py` - Already fixed one instance, find others
- `src/services/orchestrator.py` - Check error handling in `_execute_todo_with_steps`
- `tests/unit/test_orchestration_models.py` - Add validation test

**Acceptance Criteria**:
- ✅ All `OrchestrationStepOutput` instantiations use dict for `output`
- ✅ Unit test fails when given string output
- ✅ Integration test passes for timeout scenario
- ✅ No Pydantic validation errors in logs after timeout

---

### 1.2. Normalize `AgentRun.output` / `steps` / `todos` Schema 🔴 CRITICAL

**Problem**: Inconsistent structure for run results across success/failure paths. DB shows `steps=0`, `todos=0` after failure.

**Tasks**:
- [ ] **1.2.1** Define canonical schema for `AgentRun`:
  ```python
  # Success path:
  {
    "output": {
      "summary": "...",
      "data": {...},
      "todos_completed": 3,
      "todos_failed": 0
    },
    "steps": [...],  # List of OrchestrationStepOutput
    "todos": [...]   # List of TodoItem
  }
  
  # Failure path:
  {
    "output": {
      "error": "...",
      "error_type": "run_timeout" | "todo_plan_timeout" | "orchestrator_error",
      "partial_results": {...},
      "todos_completed": 1,
      "todos_failed": 1
    },
    "steps": [...],  # Partial steps before failure
    "todos": [...]   # All todos with status
  }
  ```

- [ ] **1.2.2** Document schema in `docs/AGENT_RUN_SCHEMA.md`:
  - Top-level run fields
  - Output structure for success/failure
  - Step structure and required fields
  - TODO structure and status values

- [ ] **1.2.3** Update Pydantic models:
  - Review `OrchestrationResult` in `src/services/orchestrator.py`
  - Review `AgentRun` model in `db/postgres_control/models/agent_run.py`
  - Ensure alignment between orchestrator output and DB schema

- [ ] **1.2.4** Update all result construction sites:
  - Success path in `orchestrator.run()`
  - Timeout path in `agent_runs.py` background handler
  - LLM error path
  - Tool error path

- [ ] **1.2.5** Add integration test `test_agent_run_timeout_schema`:
  - Force orchestrator timeout
  - Fetch `/v1/agent-runs/{id}`
  - Assert JSON structure matches canonical schema
  - Assert `error_type` is present
  - Assert partial `steps` and `todos` are preserved

**Files to Modify**:
- `src/services/orchestrator.py` - OrchestrationResult construction
- `src/routers/agent_runs.py` - Background error handling
- `db/postgres_control/models/agent_run.py` - DB schema review
- `docs/AGENT_RUN_SCHEMA.md` - NEW file

**Acceptance Criteria**:
- ✅ Documented canonical schema
- ✅ All code paths produce consistent structure
- ✅ Failed runs preserve partial steps/todos
- ✅ Integration test validates schema on timeout

---

### 1.3. Ensure Background Error Handling Preserves Partial Results 🟡 HIGH

**Problem**: After timeout, DB shows `steps=0`, `todos=0` despite TODO #1 completing successfully.

**Tasks**:
- [ ] **1.3.1** Review background handler in `agent_runs.py`:
  - Locate where `steps_data` and `todos_data` are populated
  - Check if timeout exception clears these lists
  - Ensure partial results are preserved before exception handling

- [ ] **1.3.2** Update timeout exception handler:
  ```python
  except asyncio.TimeoutError:
      error_msg = f"Orchestration timeout after {RUN_TIMEOUT_SECONDS}s"
      log.error("agent_run.background.timeout", ...)
      errors_list.append(error_msg)
      # Don't clear steps_data/todos_data - preserve what was completed
      success = False
      # Continue to result serialization with partial data
  ```

- [ ] **1.3.3** Ensure `steps_json` and `todos_json` include partial results:
  - After timeout, serialize whatever steps/todos were captured
  - Mark incomplete todos with `"status": "failed_due_to_timeout"`

- [ ] **1.3.4** Add explicit status to todos on timeout:
  ```python
  for todo in todos_data:
      if todo.status == "running":
          todo.status = "failed_due_to_timeout"
  ```

- [ ] **1.3.5** Add test `test_timeout_preserves_partial_results`:
  - Create run that completes 1 TODO then times out
  - Assert DB contains completed TODO
  - Assert DB contains started but incomplete TODO with proper status

**Files to Modify**:
- `src/routers/agent_runs.py` - Background exception handling
- `tests/integration/test_agent_runs.py` - Add partial results test

**Acceptance Criteria**:
- ✅ Timeout preserves completed TODOs in DB
- ✅ Incomplete TODOs marked with clear status
- ✅ Steps from completed TODOs saved to DB
- ✅ Test validates partial result persistence

---

## 2. Timeout & Cancellation Semantics

### 2.1. Confirm Proper Cancellation of `orch.run()` 🟡 HIGH

**Problem**: Need to ensure timeout doesn't leave orchestrator running in background.

**Tasks**:
- [ ] **2.1.1** Review `asyncio.wait_for()` usage in `agent_runs.py`:
  - Verify that `asyncio.TimeoutError` properly cancels underlying task
  - Check if `orch.run()` has any `try/finally` cleanup
  - Ensure no resources leak on cancellation

- [ ] **2.1.2** Add explicit cleanup in timeout handler:
  ```python
  except asyncio.TimeoutError:
      # Log cancellation
      log.info("agent_run.background.cancelled", run_id=str(run_id))
      
      # Update status to failed
      AgentRunRepository.update_status(db, run_id=run_id, status="failed")
      
      # Clear any cached state in orchestrator
      # (if applicable)
  ```

- [ ] **2.1.3** Add test with background task monitoring:
  - Create fake slow LLM that sets a flag when started/completed
  - Trigger timeout
  - Assert:
    - Run status = "failed"
    - Fake LLM task was cancelled (flag shows incomplete)
    - No orchestrator tasks remain in asyncio event loop

- [ ] **2.1.4** Review orchestrator cleanup:
  - Check if `Orchestrator.run()` has `try/finally`
  - Add cleanup for any resources (connections, caches, etc.)

**Files to Modify**:
- `src/routers/agent_runs.py` - Timeout handler
- `src/services/orchestrator.py` - Add cleanup if needed
- `tests/integration/test_agent_run_cancellation.py` - NEW file

**Acceptance Criteria**:
- ✅ Timeout cancels orchestrator task
- ✅ No background tasks leak after timeout
- ✅ Test validates proper cancellation
- ✅ Run status updated atomically

---

### 2.2. Distinguish Timeout Types in Result Payload 🟡 HIGH

**Problem**: Current error messages don't clearly indicate which timeout occurred (TODO vs run).

**Tasks**:
- [ ] **2.2.1** Define failure type enum:
  ```python
  class FailureType(str, Enum):
      TODO_PLAN_TIMEOUT = "todo_plan_timeout"
      TODO_STEP_TIMEOUT = "todo_step_timeout"
      RUN_TIMEOUT = "run_timeout"
      ORCHESTRATOR_ERROR = "orchestrator_error"
      LLM_ERROR = "llm_error"
      TOOL_ERROR = "tool_error"
  ```

- [ ] **2.2.2** Update orchestrator error logging:
  ```python
  # In _execute_todo_with_steps:
  except asyncio.TimeoutError:
      log.error("orchestrator.todo.plan_timeout",
               index=todo_idx,
               failure_type="todo_plan_timeout",  # Add this
               timeout_seconds=STEP_TIMEOUT_SECONDS)
      raise ServiceError(f"Planning timeout for TODO #{todo_idx + 1}",
                        failure_type="todo_plan_timeout")  # Add metadata
  ```

- [ ] **2.2.3** Include failure type in run output:
  ```python
  # In background handler:
  except asyncio.TimeoutError:
      output_text = {
          "error": f"Orchestration timeout after {RUN_TIMEOUT_SECONDS}s",
          "failure_type": "run_timeout",
          "timeout_seconds": RUN_TIMEOUT_SECONDS,
          "todos_completed": len([t for t in todos_data if t.status == "completed"]),
          "todos_failed": len([t for t in todos_data if t.status == "failed"])
      }
  ```

- [ ] **2.2.4** Add failure metadata to metrics:
  ```python
  metrics_data["failure_type"] = "run_timeout"
  metrics_data["failed_todo_index"] = <index if TODO failure>
  ```

- [ ] **2.2.5** Update logs to use structured failure types:
  - All timeout logs should include `failure_type` field
  - All error logs should include context (TODO index, step ID, etc.)

**Files to Modify**:
- `src/models/errors.py` - Add FailureType enum
- `src/services/orchestrator.py` - Update error logging
- `src/routers/agent_runs.py` - Include failure_type in output

**Acceptance Criteria**:
- ✅ Error payloads include `failure_type` field
- ✅ Logs clearly indicate which timeout occurred
- ✅ Metrics track failure types separately
- ✅ Tests validate failure_type in output

---

## 3. LLM Performance & Planning on CPU

### 3.1. Introduce Lightweight Test/Planning Model 🔴 CRITICAL

**Problem**: `phi3:mini` takes 108s to warm up + 120s+ for planning on CPU. Unacceptable for simple queries.

**Tasks**:
- [ ] **3.1.1** Research faster CPU-friendly models:
  - Options: `phi3:3.8b`, `tinyllama`, `qwen2:0.5b`, `gemma:2b`
  - Benchmark warmup and planning time for each
  - Document findings in `docs/MODEL_BENCHMARKS.md`

- [ ] **3.1.2** Add model selection configuration:
  ```python
  # In orchestrator config or env:
  LLM_PLAN_MODEL_NAME=tinyllama  # For TODO planning
  LLM_EXECUTE_MODEL_NAME=phi3:mini  # For execution (if needed)
  LLM_TEST_MODE=true  # Use fastest model for tests
  ```

- [ ] **3.1.3** Update orchestrator to use planning model:
  ```python
  # In Orchestrator.plan():
  plan_model = os.getenv("LLM_PLAN_MODEL_NAME", self.default_model)
  response = await self.llm.complete(
      model=plan_model,
      prompt=planning_prompt,
      ...
  )
  ```

- [ ] **3.1.4** Add model warmup for both models at startup:
  - Warm up planning model
  - Optionally warm up execution model
  - Log warmup times for each

- [ ] **3.1.5** Update test configuration:
  ```yaml
  # docker-compose.test.yml
  environment:
    LLM_TEST_MODE: "true"
    LLM_PLAN_MODEL_NAME: "tinyllama"
    LLM_STEP_TIMEOUT_SECONDS: "60"
    AGENT_RUN_TIMEOUT_SECONDS: "120"
  ```

- [ ] **3.1.6** Add model selection to health check:
  - `/health/detailed` should show active models
  - Show warmup status for each model

**Files to Modify**:
- `src/services/orchestrator.py` - Model selection logic
- `src/services/model_warmup.py` - Multi-model warmup
- `docker-compose.yml` - Add model env vars
- `docker-compose.test.yml` - Test-specific models
- `docs/MODEL_BENCHMARKS.md` - NEW file

**Acceptance Criteria**:
- ✅ Lightweight model option for CPU testing
- ✅ Warmup time <10s for test model
- ✅ Planning time <30s for simple queries
- ✅ Configuration documented and tested

---

### 3.2. Move Warmup to Startup, Not Per-Run 🔴 CRITICAL

**Problem**: 108s warmup penalty on first run. Should happen at container startup.

**Tasks**:
- [ ] **3.2.1** Review current warmup trigger:
  - Check where `model_warmup.py` is called from
  - Confirm it's happening during first `orch.run()` call
  - Move to application startup

- [ ] **3.2.2** Add startup warmup in `main.py` or entrypoint:
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      # Startup
      log.info("app.startup.warmup_started")
      
      warmup_models = os.getenv("LLM_WARMUP_MODELS", "").split(",")
      for model_name in warmup_models:
          if model_name:
              await warmup_model(model_name)
              log.info("app.startup.model_warmed", model=model_name)
      
      log.info("app.startup.complete")
      yield
      # Shutdown
      log.info("app.shutdown")
  
  app = FastAPI(lifespan=lifespan)
  ```

- [ ] **3.2.3** Add warmup status tracking:
  ```python
  # Global state or cache:
  _warmed_models: set[str] = set()
  
  async def warmup_model(model_name: str):
      if model_name in _warmed_models:
          return
      # ... warmup logic ...
      _warmed_models.add(model_name)
  ```

- [ ] **3.2.4** Update health check to show warmup status:
  ```python
  @router.get("/health/detailed")
  async def detailed_health():
      return {
          "status": "healthy",
          "warmup": {
              "completed": list(_warmed_models),
              "pending": [...],
          },
          ...
      }
  ```

- [ ] **3.2.5** Update tests to wait for warmup:
  ```python
  @pytest.fixture(scope="session")
  async def wait_for_warmup():
      # Poll /health/detailed until warmup.completed is non-empty
      ...
  ```

- [ ] **3.2.6** Add warmup metrics:
  - Prometheus gauge for warmup status per model
  - Histogram for warmup duration

**Files to Modify**:
- `src/main.py` - Add lifespan warmup
- `src/services/model_warmup.py` - Add status tracking
- `src/routers/health.py` - Add warmup status endpoint
- `tests/integration/conftest.py` - Add warmup wait fixture

**Acceptance Criteria**:
- ✅ Warmup happens once at startup
- ✅ First run has no warmup penalty
- ✅ Health check exposes warmup status
- ✅ Tests wait for warmup before running

---

### 3.3. Simplify DB-Query Prompts for Simple Cases 🟢 MEDIUM

**Problem**: "How many :Blast nodes?" doesn't need complex multi-step planning.

**Tasks**:
- [ ] **3.3.1** Classify query complexity:
  ```python
  def classify_query_complexity(prompt: str) -> str:
      """Returns 'simple' | 'moderate' | 'complex'"""
      # Simple: count queries, single entity lookups
      if re.search(r'how many|count|list all', prompt, re.I):
          return 'simple'
      # Complex: multi-step reasoning, aggregations
      if re.search(r'compare|analyze|correlate', prompt, re.I):
          return 'complex'
      return 'moderate'
  ```

- [ ] **3.3.2** Create prompt templates by complexity:
  ```python
  SIMPLE_TODO_TEMPLATE = """
  Goal: {goal}
  
  Generate 1-2 simple steps:
  1. Execute database query
  2. Format result
  
  Return JSON array of tasks.
  """
  
  COMPLEX_TODO_TEMPLATE = """
  Goal: {goal}
  
  Break down into detailed steps with reasoning...
  """
  ```

- [ ] **3.3.3** Update orchestrator to use appropriate template:
  ```python
  # In Orchestrator.run():
  complexity = classify_query_complexity(goal)
  
  if complexity == 'simple':
      todo_prompt = SIMPLE_TODO_TEMPLATE.format(goal=goal)
      max_todos = 2
  else:
      todo_prompt = COMPLEX_TODO_TEMPLATE.format(goal=goal)
      max_todos = 5
  ```

- [ ] **3.3.4** Add complexity to metadata:
  - Log query complexity
  - Store in run metadata for analysis

- [ ] **3.3.5** Test simplified prompts:
  - Run test with simple query
  - Assert TODO count ≤ 2
  - Assert planning time < 30s

**Files to Modify**:
- `src/services/orchestrator.py` - Add complexity classification
- `src/prompts/todo_templates.py` - NEW file with templates

**Acceptance Criteria**:
- ✅ Simple queries use simplified prompt
- ✅ Planning time reduced for simple queries
- ✅ TODO count reduced for simple queries
- ✅ Tests validate both paths

---

## 4. CPU vs GPU Configuration as First-Class Citizen

### 4.1. Define Single Source of Truth for Compute Mode 🟡 HIGH

**Problem**: `llm_device: "cpu"` scattered across code, no centralized configuration.

**Tasks**:
- [ ] **4.1.1** Create compute configuration module:
  ```python
  # src/config/compute.py
  from pydantic_settings import BaseSettings
  
  class ComputeConfig(BaseSettings):
      device: str = "cpu"  # cpu | cuda | mps | auto
      max_concurrent_llm_calls: int = 1  # Varies by device
      step_timeout_seconds: int = 120
      run_timeout_seconds: int = 300
      
      class Config:
          env_prefix = "LLM_"
      
      @property
      def recommended_step_timeout(self) -> int:
          """Return device-appropriate timeout"""
          return {
              "cuda": 30,
              "mps": 60,
              "cpu": 120,
              "auto": 60,
          }.get(self.device, 120)
  
  compute_config = ComputeConfig()
  ```

- [ ] **4.1.2** Update orchestrator to use compute config:
  ```python
  # In orchestrator.py:
  from src.config.compute import compute_config
  
  STEP_TIMEOUT_SECONDS = compute_config.step_timeout_seconds
  RUN_TIMEOUT_SECONDS = compute_config.run_timeout_seconds
  ```

- [ ] **4.1.3** Update LLM adapters to respect device:
  ```python
  # In LLM adapter initialization:
  self.device = compute_config.device
  log.info("llm.adapter.initialized", device=self.device)
  ```

- [ ] **4.1.4** Add device validation:
  ```python
  def validate_device(device: str) -> str:
      valid = {"cpu", "cuda", "mps", "auto"}
      if device not in valid:
          raise ValueError(f"Invalid device: {device}. Must be one of {valid}")
      return device
  ```

- [ ] **4.1.5** Update health check to show compute config:
  ```python
  {
      "compute": {
          "device": compute_config.device,
          "max_concurrent_calls": compute_config.max_concurrent_llm_calls,
          "timeouts": {
              "step": compute_config.step_timeout_seconds,
              "run": compute_config.run_timeout_seconds
          }
      }
  }
  ```

**Files to Modify**:
- `src/config/compute.py` - NEW file
- `src/services/orchestrator.py` - Import compute config
- `src/adapters/llm/*.py` - Use compute config
- `src/routers/health.py` - Expose compute config

**Acceptance Criteria**:
- ✅ Single source of truth for compute config
- ✅ All components read from compute_config
- ✅ Device-appropriate defaults applied
- ✅ Configuration exposed via health endpoint

---

### 4.2. Wire CPU/GPU Choice Through Docker Compose 🟡 HIGH

**Problem**: No way to easily switch between CPU and GPU profiles.

**Tasks**:
- [ ] **4.2.1** Add compute env vars to `docker-compose.yml`:
  ```yaml
  services:
    app:
      environment:
        LLM_DEVICE: ${LLM_DEVICE:-cpu}
        LLM_MAX_CONCURRENT_CALLS: ${LLM_MAX_CONCURRENT_CALLS:-1}
        LLM_STEP_TIMEOUT_SECONDS: ${LLM_STEP_TIMEOUT_SECONDS:-120}
        AGENT_RUN_TIMEOUT_SECONDS: ${AGENT_RUN_TIMEOUT_SECONDS:-300}
  ```

- [ ] **4.2.2** Create `.env.cpu` and `.env.gpu` profiles:
  ```bash
  # .env.cpu
  LLM_DEVICE=cpu
  LLM_MAX_CONCURRENT_CALLS=1
  LLM_STEP_TIMEOUT_SECONDS=120
  AGENT_RUN_TIMEOUT_SECONDS=300
  LLM_PLAN_MODEL_NAME=tinyllama
  
  # .env.gpu
  LLM_DEVICE=cuda
  LLM_MAX_CONCURRENT_CALLS=4
  LLM_STEP_TIMEOUT_SECONDS=30
  AGENT_RUN_TIMEOUT_SECONDS=120
  LLM_PLAN_MODEL_NAME=phi3:mini
  ```

- [ ] **4.2.3** Create GPU-specific compose override:
  ```yaml
  # docker-compose.gpu.yml
  services:
    app:
      deploy:
        resources:
          reservations:
            devices:
              - driver: nvidia
                count: 1
                capabilities: [gpu]
  ```

- [ ] **4.2.4** Update Makefile with profiles:
  ```makefile
  .PHONY: up-cpu up-gpu
  
  up-cpu:
  	docker compose --env-file .env.cpu up -d
  
  up-gpu:
  	docker compose --env-file .env.gpu -f docker-compose.yml -f docker-compose.gpu.yml up -d
  ```

- [ ] **4.2.5** Document profile usage in README:
  ```markdown
  ## Running with CPU (default)
  ```
  make up-cpu
  ```
  
  ## Running with GPU
  ```
  make up-gpu
  ```
  ```

**Files to Modify**:
- `docker-compose.yml` - Add compute env vars
- `.env.cpu` - NEW file
- `.env.gpu` - NEW file
- `docker-compose.gpu.yml` - NEW file
- `Makefile` - Add profile targets
- `README.md` - Document profiles

**Acceptance Criteria**:
- ✅ Easy switch between CPU/GPU via Makefile
- ✅ Profile-specific timeouts and concurrency
- ✅ GPU compose file includes device reservation
- ✅ Documentation clear and tested

---

### 4.3. Adapt Tests to Compute Mode 🟡 HIGH

**Problem**: Tests assume GPU-level performance, fail on CPU.

**Tasks**:
- [ ] **4.3.1** Add compute mode detection to tests:
  ```python
  # conftest.py
  import os
  import pytest
  
  @pytest.fixture(scope="session")
  def compute_mode():
      return os.getenv("LLM_DEVICE", "cpu")
  
  @pytest.fixture(scope="session")
  def test_timeout(compute_mode):
      """Return appropriate timeout for compute mode"""
      return {
          "cuda": 60,
          "mps": 90,
          "cpu": 180,
      }.get(compute_mode, 180)
  ```

- [ ] **4.3.2** Update test expectations based on device:
  ```python
  def test_nl_prompts_memgraph(compute_mode, test_timeout):
      if compute_mode == "cpu":
          pytest.skip("CPU mode too slow for this test")
          # OR use lighter model and longer timeout
      
      # ... test logic ...
  ```

- [ ] **4.3.3** Create CPU-specific test suite:
  ```python
  # tests/integration/test_agent_runs_cpu.py
  @pytest.mark.cpu
  class TestAgentRunsCPU:
      """Tests optimized for CPU execution"""
      
      def test_simple_query_cpu(self):
          # Use tinyllama model
          # Accept longer timeouts
          # Assert graceful degradation
  ```

- [ ] **4.3.4** Add test markers:
  ```python
  # pytest.ini
  [pytest]
  markers =
      cpu: Tests that pass on CPU with adjusted timeouts
      gpu: Tests that require GPU
      slow: Tests that may take >60s
  ```

- [ ] **4.3.5** Update CI configuration:
  ```yaml
  # .github/workflows/test.yml
  - name: Run CPU tests
    run: pytest -m cpu
    env:
      LLM_DEVICE: cpu
      LLM_PLAN_MODEL_NAME: tinyllama
  ```

**Files to Modify**:
- `tests/conftest.py` - Add compute mode fixtures
- `tests/integration/test_agent_runs_cpu.py` - NEW file
- `pytest.ini` - Add markers
- `.github/workflows/test.yml` - Update CI

**Acceptance Criteria**:
- ✅ Tests adapt to compute mode automatically
- ✅ CPU tests use lighter models and longer timeouts
- ✅ GPU tests use stricter timeouts
- ✅ CI runs appropriate test suite

---

## 5. Test Harness & Observability

### 5.1. Tighten Integration Test Expectations 🟡 HIGH

**Problem**: Current test just polls for "not running", doesn't validate final state.

**Tasks**:
- [ ] **5.1.1** Define clear test outcomes:
  ```python
  # For simple queries on CPU:
  EXPECTED_OUTCOME = "succeeded"  # Or "failed" if timeout expected
  MAX_WAIT_TIME = 180  # 3 minutes max for CPU
  
  # For complex queries on CPU:
  EXPECTED_OUTCOME = "failed"  # Timeout expected
  MAX_WAIT_TIME = 300
  ```

- [ ] **5.1.2** Update test to assert final state:
  ```python
  def test_nl_prompts_memgraph_rbac_matrix(self, compute_mode):
      # Create run
      run_id = create_agent_run(...)
      
      # Poll with appropriate timeout
      timeout = 180 if compute_mode == "cpu" else 60
      final_status = poll_until_complete(run_id, max_wait=timeout)
      
      # Assert expected outcome
      if compute_mode == "cpu":
          # For CPU, we expect either success or graceful timeout
          assert final_status in ["succeeded", "failed"]
          
          if final_status == "failed":
              # Validate error payload structure
              run_data = fetch_run(run_id)
              assert "output" in run_data
              assert "error" in run_data["output"]
              assert "failure_type" in run_data["output"]
      else:
          # For GPU, we expect success
          assert final_status == "succeeded"
  ```

- [ ] **5.1.3** Add output validation:
  ```python
  def validate_run_output(run_data, expected_status):
      assert run_data["status"] == expected_status
      
      if expected_status == "succeeded":
          assert "output" in run_data
          assert run_data["output"] is not None
          assert len(run_data.get("steps", [])) > 0
      
      elif expected_status == "failed":
          assert "output" in run_data
          assert "error" in run_data["output"]
          assert "failure_type" in run_data["output"]
          # Should still have partial results
          assert run_data.get("todos") is not None
  ```

- [ ] **5.1.4** Add explicit timeout test:
  ```python
  def test_orchestrator_timeout_handling():
      """Test that orchestrator times out gracefully"""
      # Create run with guaranteed timeout (mock slow LLM)
      run_id = create_agent_run_with_slow_llm(...)
      
      # Wait for timeout
      final_status = poll_until_complete(run_id, max_wait=350)
      
      # Assert timeout occurred
      assert final_status == "failed"
      
      run_data = fetch_run(run_id)
      assert run_data["output"]["failure_type"] == "run_timeout"
      assert "timeout" in run_data["output"]["error"].lower()
  ```

- [ ] **5.1.5** Document test expectations in test file:
  ```python
  """
  Integration tests for agent NL→Memgraph execution.
  
  Test Expectations by Compute Mode:
  - CPU: Simple queries may timeout, expect graceful failure
  - GPU: All queries should succeed within 60s
  
  Test Matrix:
  - Simple queries (count, list): Should succeed on GPU, may timeout on CPU
  - Complex queries (analyze, correlate): Should succeed on GPU, will timeout on CPU
  """
  ```

**Files to Modify**:
- `tests/integration/test_agent_memgraph_nl_prompts.py` - Update expectations
- `tests/integration/test_agent_run_timeouts.py` - NEW file for timeout tests

**Acceptance Criteria**:
- ✅ Tests assert specific final status
- ✅ Tests validate output structure on failure
- ✅ Dedicated timeout test validates graceful failure
- ✅ Test expectations documented clearly

---

### 5.2. Add Explicit Metrics for Timing 🟢 MEDIUM

**Problem**: No observability into where time is spent during orchestration.

**Tasks**:
- [ ] **5.2.1** Add Prometheus metrics for agent runs:
  ```python
  # src/metrics/agent_metrics.py
  from prometheus_client import Histogram, Counter, Gauge
  
  agent_run_duration = Histogram(
      'agent_run_duration_seconds',
      'Total duration of agent run',
      buckets=[1, 5, 10, 30, 60, 120, 300, 600]
  )
  
  agent_run_failures = Counter(
      'agent_run_failures_total',
      'Total agent run failures',
      ['failure_type']  # todo_plan_timeout, run_timeout, etc.
  )
  
  agent_todos_total = Histogram(
      'agent_todos_count',
      'Number of TODOs generated per run',
      buckets=[1, 2, 3, 5, 10]
  )
  
  agent_todo_duration = Histogram(
      'agent_todo_duration_seconds',
      'Duration per TODO',
      ['status'],  # completed, failed, timeout
      buckets=[1, 5, 10, 30, 60, 120]
  )
  ```

- [ ] **5.2.2** Instrument orchestrator with metrics:
  ```python
  # In orchestrator.run():
  with agent_run_duration.time():
      # ... orchestration logic ...
      pass
  
  agent_todos_total.observe(len(todos))
  
  # In _execute_todo_with_steps():
  with agent_todo_duration.labels(status="completed").time():
      # ... TODO logic ...
      pass
  ```

- [ ] **5.2.3** Record failure metrics:
  ```python
  # On timeout:
  agent_run_failures.labels(failure_type="run_timeout").inc()
  
  # On TODO failure:
  agent_run_failures.labels(failure_type="todo_plan_timeout").inc()
  ```

- [ ] **5.2.4** Add Grafana dashboard for agent metrics:
  ```json
  {
    "dashboard": {
      "panels": [
        {
          "title": "Agent Run Duration (p50, p95, p99)",
          "targets": [
            {
              "expr": "histogram_quantile(0.50, agent_run_duration_seconds_bucket)"
            }
          ]
        },
        {
          "title": "Failure Rate by Type",
          "targets": [
            {
              "expr": "rate(agent_run_failures_total[5m])"
            }
          ]
        }
      ]
    }
  }
  ```

- [ ] **5.2.5** Add metrics to health check:
  ```python
  @router.get("/health/detailed")
  async def detailed_health():
      return {
          "metrics": {
              "agent_runs_total": ...,
              "avg_duration_seconds": ...,
              "failure_rate": ...
          }
      }
  ```

**Files to Modify**:
- `src/metrics/agent_metrics.py` - NEW file
- `src/services/orchestrator.py` - Add instrumentation
- `src/routers/agent_runs.py` - Record run metrics
- `monitoring/grafana/dashboards/agent_runs.json` - NEW dashboard

**Acceptance Criteria**:
- ✅ Prometheus metrics exported
- ✅ Grafana dashboard shows run duration percentiles
- ✅ Failure rate tracked by type
- ✅ TODO duration tracked separately

---

## 6. Final Production Readiness

### 6.1. Production Readiness Checklist 🔴 CRITICAL

**Create**: `docs/PROD_READINESS.md`

**Tasks**:
- [ ] **6.1.1** Create comprehensive checklist:

```markdown
# Production Readiness Checklist

## Correctness & Data Integrity
- [ ] All `OrchestrationStepOutput` instances use dict for `output`
- [ ] No Pydantic validation errors in any code path
- [ ] Error payloads are consistent across success/failure/timeout
- [ ] Failed runs preserve partial `steps` and `todos`
- [ ] Unit tests validate Pydantic models reject invalid inputs

## Timeout & Cancellation
- [ ] Step-level timeout (120s default) enforced
- [ ] TODO-level timeout (120s default) enforced
- [ ] Run-level timeout (300s default) enforced
- [ ] Timeout cancels underlying tasks properly
- [ ] No resource leaks after timeout/cancellation
- [ ] Failure types clearly distinguished in logs and output

## Performance
- [ ] Model warmup happens at startup, not first request
- [ ] Warmup time <10s for production models
- [ ] Simple queries complete in <60s on target hardware
- [ ] CPU configuration uses lightweight models
- [ ] GPU configuration uses production models with tight timeouts

## Configuration
- [ ] Single source of truth for compute config
- [ ] CPU/GPU profiles documented and tested
- [ ] All timeouts configurable via environment variables
- [ ] Default values appropriate for target environment
- [ ] Health check exposes current configuration

## Observability
- [ ] Prometheus metrics for:
  - [ ] Run duration (histogram)
  - [ ] Failure rate by type (counter)
  - [ ] TODO duration (histogram)
  - [ ] Model warmup duration (histogram)
- [ ] Grafana dashboard for agent metrics
- [ ] Structured logging with consistent fields
- [ ] Tracing context propagated through orchestration

## Testing
- [ ] Integration tests cover:
  - [ ] Normal success path
  - [ ] TODO-level timeout
  - [ ] Run-level timeout
  - [ ] Pydantic validation on error paths
- [ ] Tests adapt to compute mode (CPU vs GPU)
- [ ] CPU tests use lightweight models
- [ ] Timeout tests validate graceful failure
- [ ] All tests pass in CI

## Documentation
- [ ] Agent run schema documented
- [ ] Failure types enumerated and explained
- [ ] Compute profiles documented with examples
- [ ] Model selection guide created
- [ ] Runbook for common failure scenarios
```

- [ ] **6.1.2** Systematically tick off checklist items
- [ ] **6.1.3** Review with team before production deployment
- [ ] **6.1.4** Add "signed off" section with date and approver

**Files to Create**:
- `docs/PROD_READINESS.md` - Main checklist
- `docs/AGENT_RUN_SCHEMA.md` - Data structure reference
- `docs/MODEL_BENCHMARKS.md` - Performance data
- `docs/RUNBOOK_AGENT_FAILURES.md` - Troubleshooting guide

**Acceptance Criteria**:
- ✅ All checklist items addressed or explicitly deferred
- ✅ Documentation complete and reviewed
- ✅ Sign-off obtained from stakeholders
- ✅ Deployment plan documented

---

## Priority Matrix

### 🔴 **CRITICAL** (Must complete before any production use)
1. Fix `OrchestrationStepOutput` Pydantic errors (1.1)
2. Normalize run output schema (1.2)
3. Introduce lightweight test model (3.1)
4. Move warmup to startup (3.2)
5. Production readiness checklist (6.1)

### 🟡 **HIGH** (Should complete for production stability)
1. Preserve partial results on timeout (1.3)
2. Confirm proper cancellation (2.1)
3. Distinguish timeout types (2.2)
4. Single source of truth for compute config (4.1)
5. Wire CPU/GPU through Docker (4.2)
6. Adapt tests to compute mode (4.3)
7. Tighten test expectations (5.1)

### 🟢 **MEDIUM** (Nice to have, improves operations)
1. Simplify prompts for simple queries (3.3)
2. Add explicit timing metrics (5.2)

---

## Success Criteria

### Overall Goal
Enable production deployment of agent orchestrator with:
- **Zero Pydantic validation errors**
- **Graceful timeout handling** at all levels
- **Acceptable performance** on target hardware (CPU or GPU)
- **Comprehensive observability** for debugging
- **Tested and documented** configuration profiles

### Key Metrics
- ✅ Simple queries succeed in <60s (GPU) or timeout gracefully (CPU)
- ✅ No infinite hangs (300s hard limit)
- ✅ Error messages are actionable
- ✅ 100% of integration tests pass
- ✅ Production readiness checklist 100% complete

---

## Timeline Estimate

| Phase | Tasks | Estimated Time | Priority |
|-------|-------|---------------|----------|
| **Phase 1: Critical Fixes** | 1.1, 1.2, 3.1, 3.2 | 2-3 days | 🔴 |
| **Phase 2: Timeout Refinement** | 1.3, 2.1, 2.2 | 1-2 days | 🟡 |
| **Phase 3: Configuration** | 4.1, 4.2, 4.3 | 1-2 days | 🟡 |
| **Phase 4: Testing & Observability** | 5.1, 5.2, 3.3 | 1-2 days | 🟡/🟢 |
| **Phase 5: Documentation & Sign-off** | 6.1 | 1 day | 🔴 |

**Total Estimated Time**: 6-10 days

---

## Next Immediate Steps

1. **Start with 1.1** - Fix all `OrchestrationStepOutput` validation errors
2. **Then 3.1** - Introduce lightweight model for CPU testing
3. **Then 3.2** - Move warmup to startup
4. **Then 1.2** - Normalize output schema
5. **Review progress** and prioritize remaining tasks

---

**Document Owner**: Orchestrator Team  
**Last Updated**: November 15, 2025  
**Status**: Ready for execution
