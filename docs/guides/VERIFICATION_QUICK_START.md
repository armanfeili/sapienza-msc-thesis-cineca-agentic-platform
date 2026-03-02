# Verification Quick Start Guide

## TL;DR - Implementation Status

✅ **ALL TASKS IMPLEMENTED** - Code changes complete and deployed  
⏳ **VERIFICATION PENDING** - Need to run tests to confirm functionality

---

## Are All Tasks Accomplished?

**Answer: YES for implementation, NO for verification**

### Implementation Status (✅ Complete):

- ✅ **A-E (OrchestrationResult, timeouts, errors, metrics, principal)** - All code changes deployed
- ✅ **R1-R3 (Timeout analysis & config)** - Completed in previous session  
- ✅ **R4 (RBAC logging)** - Enhanced principal tracking in MCP runtime
- ✅ **R5 (Cypher extraction visibility)** - Detailed logging in test suite
- ✅ **R6 (Simple mode fast path)** - Environment-gated TODO planning skip

### Verification Status (⏳ Pending):

- ⏳ Test execution not yet run
- ⏳ RBAC behavior not yet confirmed from logs
- ⏳ Cypher extraction not yet validated
- ⏳ Simple mode activation not yet verified

---

## Next Steps: Single Command to Get `test_prompt_1.log`

Run this exact command to verify everything:

```bash
docker compose exec \
  -e LLM_MEMGRAPH_NL_TEST_MODE=true \
  -e MEMGRAPH_NL_SIMPLE_MODE=true \
  app bash -c \
  'pytest tests/integration/test_agent_memgraph_nl_prompts_v2.py::TestAgentMemgraphNLPrompts::test_nl_prompts_memgraph_rbac_matrix \
     --nl-prompts=1 --nl-prompts-role=admin -v -s --tb=short 2>&1 \
   | tee tests/integration/output/test_prompt_1.log'
```

**Expected Runtime:** ~60-90 seconds (with simple mode enabled)

---

## What to Check After Running

### 1. Test Completion
```bash
# Check final status in log
tail -50 tests/integration/output/test_prompt_1.log
```

**Look for:**
- ✅ Status: `succeeded` (or clear error message, not crash)
- ✅ No `TimeoutError` exceptions
- ✅ No `AttributeError: 'NoneType' object has no attribute 'to_dict'`

### 2. RBAC Principal Logging (R4)
```bash
docker compose logs app --since 10m | grep -E "graph.generate_cypher|principal" | tail -20
```

**Look for:**
- ✅ `[principal: OK]` (not `[principal: MISSING]`)
- ✅ `principal_sub=auth0|...`
- ✅ `principal_scopes=['tools:basic', ...]`

### 3. Cypher Extraction (R5)
```bash
cat tests/integration/output/test_prompt_1.log | grep -A 5 "Cypher extraction summary"
```

**Look for:**
- ✅ `graph.generate_cypher calls: 1` (or more)
- ✅ `Cypher queries extracted: 1` (or more)
- ✅ Query starts with `MATCH (b:Blast)`

### 4. Simple Mode Activation (R6)
```bash
docker compose logs app --since 10m | grep "orchestrator.simple_mode"
```

**Look for:**
- ✅ `orchestrator.simple_mode.enabled`
- ✅ `Skipping TODO planning for simple read-only query`

### 5. LLM Metrics
```bash
cat tests/integration/output/test_prompt_1.log | grep "llm_attempted_calls\|llm_successful_calls"
```

**Look for:**
- ✅ `llm_attempted_calls: 2` (or similar positive number)
- ✅ `llm_successful_calls: 2` (or similar, ≤ attempted)

---

## If Something Fails

### Test Times Out
```bash
# Check timeout configuration
docker compose exec app env | grep LLM_MEMGRAPH_NL_TEST_MODE

# Verify Ollama is healthy
docker compose exec app curl -s http://ollama:11434/api/tags | jq
```

### RBAC Permission Denied
```bash
# Regenerate Auth0 tokens
./fetch_auth0_tokens.sh

# Verify scopes in JWT
docker compose logs app --since 5m | grep "jwt.decode" | jq '.scopes'
```

### No Cypher Extracted
```bash
# Check if tool was invoked
docker compose logs app --since 10m | grep "graph.generate_cypher"

# Inspect step output structure
docker compose logs app --since 10m | grep "step.output" | tail -10
```

---

## Final Success Criteria

When you have:

- ✅ File exists: `tests/integration/output/test_prompt_1.log`
- ✅ Test status: `succeeded` (or structured error, not crash)
- ✅ Runtime: < 90 seconds
- ✅ RBAC logs show `[principal: OK]`
- ✅ At least 1 Cypher query extracted
- ✅ Simple mode activated and logged
- ✅ LLM metrics tracked (attempted ≥ 1, successful ≥ 1)

**Then verification is COMPLETE!** 🎉

---

## Documentation Reference

For detailed explanations, see:
- `IMPLEMENTATION_VERIFICATION_CHECKLIST.md` - Comprehensive guide with all code locations
- `docs/R4_R5_R6_IMPLEMENTATION_COMPLETE.md` - R4-R6 implementation details
- `docs/TODO_COMPLETE_SUMMARY.md` - Complete TODO status and validation

---

## Estimated Time to Complete Verification

- Running test: **~2 minutes**
- Checking logs: **~3 minutes**
- **Total: ~5 minutes**

Just run the single command above and validate the output! 🚀
