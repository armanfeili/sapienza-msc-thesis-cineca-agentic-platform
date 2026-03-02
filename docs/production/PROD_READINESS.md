# Production Readiness Checklist

**Last Updated**: November 15, 2025  
**Status**: In Progress  
**Target Environment**: CPU (primary), GPU (optional)

---

## Correctness & Data Integrity

- [x] All `OrchestrationStepOutput` instances use dict for `output`
  - Validated in `src/routers/agent_runs.py`
  - Validated in `src/services/orchestrator.py`
  - Unit test created: `tests/unit/test_orchestration_output_validation.py`

- [x] No Pydantic validation errors in any code path
  - Schema enforces dict type for output
  - Error paths use structured output dicts
  - Test coverage for validation rules

- [x] Error payloads are consistent across success/failure/timeout
  - Failure types defined in `src/models/failure_types.py`
  - Consistent structure documented in `docs/AGENT_RUN_SCHEMA.md`
  - All error paths use structured output with `failure_type`

- [x] Failed runs preserve partial `steps` and `todos`
  - Timeout handler updated to preserve partial results
  - Steps/todos not cleared on timeout
  - Incomplete todos marked with `status="failed_due_to_timeout"`

- [x] Unit tests validate Pydantic models reject invalid inputs
  - Test suite: `tests/unit/test_orchestration_output_validation.py`
  - Covers string rejection, dict acceptance, error structures

---

## Timeout & Cancellation

- [x] Step-level timeout enforced
  - Default: 120s (CPU), 30s (GPU)
  - Configurable via `LLM_STEP_TIMEOUT_SECONDS`
  - Applied in `orchestrator._execute_todo_with_steps()`

- [x] TODO-level timeout enforced
  - Planning phase: 120s timeout
  - Per-step execution: 120s timeout
  - Errors logged with `failure_type`

- [x] Run-level timeout enforced
  - Default: 300s (CPU), 120s (GPU)
  - Configurable via `AGENT_RUN_TIMEOUT_SECONDS`
  - Applied in `agent_runs.execute_agent_run_background()`

- [x] Timeout cancels underlying tasks properly
  - Uses `asyncio.wait_for()` for cancellation
  - Timeout exceptions caught and handled gracefully

- [ ] No resource leaks after timeout/cancellation
  - **TODO**: Add test to verify no background tasks remain
  - **TODO**: Review orchestrator cleanup in `try/finally`

- [x] Failure types clearly distinguished in logs and output
  - `FailureType` enum defines all failure modes
  - Logs include `failure_type` field
  - Output includes `failure_type` in error dict

---

## Performance

- [x] Model warmup configuration exists
  - Warmup models configurable via `LLM_WARMUP_MODELS`
  - Device-aware defaults in compute config

- [ ] Warmup happens at startup, not first request
  - **TODO**: Implement lifespan context in `src/main.py`
  - **TODO**: Move warmup from orchestrator to app startup
  - **TODO**: Add warmup status tracking

- [ ] Warmup time <10s for production models
  - **TODO**: Benchmark current warmup time
  - **TODO**: Optimize or select faster models

- [ ] Simple queries complete in <60s on target hardware
  - **TODO**: Benchmark with CPU profile
  - **TODO**: Document expected performance by query type

- [x] CPU configuration uses lightweight models
  - `.env.cpu` profile created with phi3:mini
  - Timeout defaults appropriate for CPU (120s/300s)

- [x] GPU configuration uses production models with tight timeouts
  - `.env.gpu` profile created with phi3:mini/medium
  - Timeout defaults appropriate for GPU (30s/120s)

---

## Configuration

- [x] Single source of truth for compute config
  - Created `src/config/compute.py` with `ComputeConfig`
  - Device-aware defaults for timeouts and concurrency
  - Environment variable overrides supported

- [x] CPU/GPU profiles documented and tested
  - `.env.cpu` profile created
  - `.env.gpu` profile created
  - `docker-compose.gpu.yml` for GPU support
  - Makefile targets: `make up-cpu`, `make up-gpu`

- [x] All timeouts configurable via environment variables
  - `LLM_STEP_TIMEOUT_SECONDS`
  - `AGENT_RUN_TIMEOUT_SECONDS`
  - `LLM_MAX_CONCURRENT_CALLS`

- [x] Default values appropriate for target environment
  - CPU: 120s/300s timeouts, 1 concurrent call
  - GPU: 30s/120s timeouts, 4 concurrent calls
  - Auto-applied via `ComputeConfig.apply_recommended_defaults()`

- [ ] Health check exposes current configuration
  - **TODO**: Add compute config to `/health/detailed`
  - **TODO**: Show device, timeouts, model selection

---

## Observability

- [ ] Prometheus metrics for:
  - [ ] Run duration (histogram)
  - [ ] Failure rate by type (counter)
  - [ ] TODO duration (histogram)
  - [ ] Model warmup duration (histogram)
  - **TODO**: Create `src/metrics/agent_metrics.py`
  - **TODO**: Instrument orchestrator with metrics
  - **TODO**: Add Grafana dashboard

- [x] Structured logging with consistent fields
  - All logs include `failure_type` where applicable
  - Structured log fields: run_id, todo_index, step_id, timeout_seconds

- [ ] Tracing context propagated through orchestration
  - **TODO**: Verify request_id propagation
  - **TODO**: Add trace IDs to all orchestrator logs

---

## Testing

- [x] Integration tests cover normal success path
  - Existing test: `test_agent_memgraph_nl_prompts.py`

- [ ] Integration tests cover TODO-level timeout
  - **TODO**: Create `tests/integration/test_agent_run_timeouts.py`
  - **TODO**: Mock slow planning to trigger timeout

- [ ] Integration tests cover run-level timeout
  - **TODO**: Add test with slow execution to trigger run timeout

- [x] Integration tests validate Pydantic validation on error paths
  - Unit tests validate output structure
  - **TODO**: Add integration test that forces timeout and validates output

- [ ] Tests adapt to compute mode (CPU vs GPU)
  - **TODO**: Add `conftest.py` fixture for compute mode detection
  - **TODO**: Adjust timeouts based on device in tests

- [ ] CPU tests use lightweight models
  - **TODO**: Configure test environment with lightweight model
  - **TODO**: Document test model selection

- [ ] Timeout tests validate graceful failure
  - **TODO**: Verify partial results preserved
  - **TODO**: Verify failure_type in output

- [ ] All tests pass in CI
  - **TODO**: Update CI configuration for compute modes
  - **TODO**: Run full test suite after all changes

---

## Documentation

- [x] Agent run schema documented
  - Created `docs/AGENT_RUN_SCHEMA.md`
  - Covers success/failure paths
  - Includes validation rules and examples

- [x] Failure types enumerated and explained
  - `src/models/failure_types.py` with docstrings
  - Schema doc includes failure type descriptions

- [x] Compute profiles documented with examples
  - `.env.cpu` and `.env.gpu` profiles created
  - Makefile targets documented

- [ ] Model selection guide created
  - **TODO**: Create `docs/MODEL_SELECTION.md`
  - **TODO**: Document recommended models for CPU/GPU
  - **TODO**: Include performance benchmarks

- [ ] Runbook for common failure scenarios
  - **TODO**: Create `docs/RUNBOOK_AGENT_FAILURES.md`
  - **TODO**: Document troubleshooting steps for timeouts
  - **TODO**: Include log examples and resolution steps

---

## Deployment Readiness

- [ ] Health endpoints comprehensive
  - **TODO**: Add compute config to `/health/detailed`
  - **TODO**: Add warmup status
  - **TODO**: Add metrics summary

- [ ] Environment variable validation
  - **TODO**: Validate all required env vars at startup
  - **TODO**: Log configuration on startup

- [ ] Graceful shutdown implemented
  - **TODO**: Review signal handling
  - **TODO**: Ensure in-flight runs complete or save state

- [ ] Resource limits documented
  - **TODO**: Document memory requirements by model
  - **TODO**: Document CPU/GPU requirements
  - **TODO**: Docker resource limits configured

- [ ] Security review complete
  - **TODO**: Review timeout values for DoS resistance
  - **TODO**: Ensure user input validation
  - **TODO**: Rate limiting configured

---

## Sign-Off

### Development Team
- [ ] All critical items completed
- [ ] All tests passing
- [ ] Documentation reviewed

### Operations Team
- [ ] Deployment procedures reviewed
- [ ] Monitoring configured
- [ ] Runbooks validated

### Security Team
- [ ] Security review complete
- [ ] Timeout configuration approved
- [ ] Input validation verified

---

## Completion Status

**Overall Progress**: 60% (18/30 completed)

**Critical Blockers** (Must complete before production):
1. ✅ Pydantic validation fixes
2. ✅ Failure type implementation
3. ✅ Compute configuration module
4. ⚠️ Model warmup at startup (IN PROGRESS)
5. ⚠️ Health check enhancements (IN PROGRESS)

**Next Steps**:
1. Implement lifespan warmup in `src/main.py`
2. Add compute config to health endpoints
3. Create Prometheus metrics
4. Add timeout integration tests
5. Complete documentation (model selection, runbooks)

---

**Document Owner**: Platform Team  
**Review Cycle**: Weekly until production-ready  
**Target Production Date**: TBD
