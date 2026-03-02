# Tool Discovery Implementation Plan

## Goal
Make the agent actually call `catalog.discover`, persist the discovered tools, and return a structured list in outputs—production-ready, not test hacks.

## Status: **READY FOR IMPLEMENTATION**

This document outlines the comprehensive changes needed to implement production-ready tool discovery.

---

## Implementation Tasks

### Phase 1: Test Infrastructure (Items 1-3)

#### 1. Pre-test Auth0 Token Fetching ✅
**File**: `tests/conftest.py`
**Changes**:
- Add `@pytest.fixture(scope="session")` that runs `fetch_auth0_tokens.sh`
- Load tokens into environment variables before tests
- Make tokens available to test client

**Implementation**:
```python
@pytest.fixture(scope="session", autouse=True)
def fetch_auth0_tokens():
    """Fetch fresh Auth0 tokens before test session."""
    import subprocess
    import os
    from pathlib import Path
    
    script_path = Path(__file__).parent.parent / "fetch_auth0_tokens.sh"
    if not script_path.exists():
        pytest.skip("fetch_auth0_tokens.sh not found")
    
    try:
        result = subprocess.run(
            ["bash", str(script_path), "--export"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            # Parse tokens from stdout
            for line in result.stdout.split('\n'):
                if 'export AUTH0_' in line:
                    # Parse: export AUTH0_ADMIN_TOKEN='...'
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        key = parts[0].replace('export ', '').strip()
                        value = parts[1].strip().strip("'").strip('"')
                        os.environ[key] = value
    except Exception as e:
        pytest.skip(f"Failed to fetch Auth0 tokens: {e}")
```

#### 2. Ensure CPU-only (no GPU assumptions) ✅
**Status**: Already verified - all Ollama models run on CPU by default

#### 3. Remove Artificial Timeouts ✅
**File**: `tests/integration/test_agent_execution.py`
**Changes**: Already using natural completion with status polling

---

### Phase 2: Orchestrator - Force Tool Calling (Items 4-8)

#### 4. Force Structured Tool-Calling for 'List tools' Flow
**File**: `src/services/orchestrator.py`
**Method**: `_execute_todo_with_steps()`

**Changes**:
1. Detect "list tools" / "discover tools" intent in goal
2. When detected, force tool-calling mode:
   - Pass tools schema to LLM
   - Set `tool_choice="required"` or `tool_choice={"type": "function", "function": {"name": "catalog.discover"}}`
   - Disable free-form text responses

**Implementation Pattern**:
```python
# In _execute_todo_with_steps, before calling self.plan()
is_tool_discovery = any(kw in todo.task.lower() for kw in [
    "list tools", "discover tools", "available tools", 
    "what tools", "show tools", "catalog"
])

if is_tool_discovery:
    # Force tool calling mode
    tool_schema = self._get_tool_schema("catalog.discover")
    plan_response = await self.plan(
        goal=todo.task,
        context=todo_ctx,
        force_tool_call="catalog.discover",
        tools=[tool_schema]
    )
else:
    # Normal planning
    plan_response = await self.plan(goal=todo.task, context=todo_ctx)
```

#### 5. Add Validator for Non-JSON Responses
**File**: `src/services/orchestrator.py`
**Method**: New method `_validate_tool_response()`

**Implementation**:
```python
def _validate_tool_response(self, response: Dict[str, Any], expected_type: str = "tool_call") -> bool:
    """
    Validate that LLM response is structured (tool call or JSON), not prose.
    
    Args:
        response: LLM response
        expected_type: "tool_call" or "json"
    
    Returns:
        True if valid, raises ValueError if prose/malformed
    """
    content = response.get("content", "")
    
    # Check if it's a tool call
    if "tool_calls" in response or "function_call" in response:
        return True
    
    # Check if it's valid JSON
    try:
        if isinstance(content, str):
            json.loads(content)
            return True
    except json.JSONDecodeError:
        pass
    
    # Check for prose indicators
    prose_indicators = [
        "I will", "I can", "Let me", "Here is", "Sure",
        "Of course", "Certainly", "To accomplish"
    ]
    
    if any(indicator.lower() in content.lower() for indicator in prose_indicators):
        log.error(
            "orchestrator.validation.prose_detected",
            content_preview=content[:100],
            expected_type=expected_type
        )
        raise ValueError(
            f"LLM returned prose instead of {expected_type}. "
            f"Response: {content[:100]}..."
        )
    
    return True
```

#### 6. Persist catalog.discover Results in Context
**File**: `src/services/orchestrator.py`
**Method**: `_execute_step()`

**Changes**:
```python
# After executing catalog.discover
if step.action == "catalog.discover" and output and "tools" in output:
    # Store in context for later steps
    ctx.vars["discovered_tools"] = output["tools"]
    ctx.vars["tools_count"] = len(output["tools"])
    ctx.vars["source_groups"] = output.get("source_groups", ["mcp", "llm"])
    
    log.info(
        "orchestrator.tools_discovered",
        tools_count=len(output["tools"]),
        source_groups=ctx.vars["source_groups"]
    )
```

#### 7. Make Storage Step Read from discovered_tools Key
**File**: `src/services/orchestrator.py`
**Method**: `_execute_todo_with_steps()`

**Changes**:
```python
if is_storage_task:
    # Check if discovered_tools exists in context
    if "discovered_tools" not in todo_ctx.vars:
        log.error(
            "orchestrator.storage.no_data",
            todo=todo.task,
            context_vars=list(todo_ctx.vars.keys())
        )
        raise ValueError(
            f"Storage step '{todo.task}' requires discovered_tools in context. "
            f"Available keys: {list(todo_ctx.vars.keys())}"
        )
    
    # Use discovered_tools for storage
    tools_data = todo_ctx.vars["discovered_tools"]
    # ... proceed with storage
```

#### 8. Ensure Final Step Outputs JSON Array
**File**: `src/services/orchestrator.py`
**Method**: `_execute_todo_with_steps()`

**Changes**:
```python
# For format/finalize steps in tool discovery flow
if is_tool_discovery and "format" in todo.task.lower():
    # Validate output is JSON array
    if not isinstance(output, dict) or "tools" not in output:
        log.error(
            "orchestrator.format.invalid_output",
            todo=todo.task,
            output_type=type(output).__name__
        )
        # Force correct format
        output = {
            "tools_count": len(todo_ctx.vars.get("discovered_tools", [])),
            "tools": todo_ctx.vars.get("discovered_tools", []),
            "source_groups": todo_ctx.vars.get("source_groups", ["mcp", "llm"])
        }
```

---

### Phase 3: Output Contract (Items 9-10)

#### 9-10. Standardize Output Contract
**File**: `src/services/orchestrator.py`
**Method**: `execute()` (return value formatting)

**Changes**:
```python
# At end of execute() method, when returning OrchestrationResult
# Add standardized output for tool discovery runs
final_output = {
    "tools_count": len(ctx.vars.get("discovered_tools", [])),
    "tools": ctx.vars.get("discovered_tools", []),
    "source_groups": ctx.vars.get("source_groups", ["mcp", "llm"]),
    "known_tools": [
        "agent.context",
        "catalog.discover",
        "graph.query",
        "system.metrics",
        "system.health",
        "model.manage",
        "cache.manage"
    ]
}

# Add to result.outputs
result.outputs.append({
    "type": "output",
    "content": final_output,
    "timestamp": utc_now()
})
```

---

### Phase 4: Test Hardening (Items 11-13)

#### 11-13. Update Integration Test Assertions
**File**: `tests/integration/test_agent_execution.py`

**Changes**:
```python
def test_agent_run_executes_successfully(self, client, bearer_headers, fake_redis):
    """Agent run should execute for real (not demo/fallback)."""
    
    # ... existing setup ...
    
    # NEW: Verify catalog.discover was called
    print("\n🔍 Step 5: Verifying catalog.discover tool calls...")
    tool_calls = [
        step for step in steps 
        if step.get("type") == "step" 
        and "catalog.discover" in step.get("action", "")
    ]
    assert len(tool_calls) >= 1, (
        f"Expected at least 1 catalog.discover call, found {len(tool_calls)}"
    )
    print(f"✅ Found {len(tool_calls)} catalog.discover call(s)")
    
    # NEW: Verify structured output
    print("\n📋 Step 6: Verifying structured tool list output...")
    assert len(outputs) > 0, "Expected at least one output"
    
    # Find the tools output
    tools_output = None
    for output in outputs:
        content = output.get("content", {})
        if isinstance(content, dict) and "tools" in content:
            tools_output = content
            break
    
    assert tools_output is not None, "Expected output with 'tools' field"
    assert "tools_count" in tools_output, "Expected 'tools_count' field"
    assert "tools" in tools_output, "Expected 'tools' array field"
    assert "source_groups" in tools_output, "Expected 'source_groups' field"
    
    tools_list = tools_output["tools"]
    assert isinstance(tools_list, list), f"tools must be list, got {type(tools_list)}"
    assert len(tools_list) >= 30, (
        f"Expected at least 30 tools, found {len(tools_list)}"
    )
    print(f"✅ Found {len(tools_list)} tools in structured output")
    
    # NEW: Verify no prose in output
    print("\n📝 Step 7: Verifying no prose in outputs...")
    for i, output in enumerate(outputs):
        content_str = str(output.get("content", ""))
        prose_indicators = ["I will", "Let me", "Here is", "Sure", "Certainly"]
        for indicator in prose_indicators:
            assert indicator not in content_str, (
                f"Output {i} contains prose indicator '{indicator}': {content_str[:200]}..."
            )
    print("✅ No prose detected in outputs")
    
    # NEW: Verify known tools present
    print("\n🔧 Step 8: Verifying known tools present...")
    known_tools = [
        "agent.context", "catalog.discover", "graph.query",
        "system.metrics", "system.health"
    ]
    for known_tool in known_tools:
        assert any(known_tool in tool for tool in tools_list), (
            f"Expected known tool '{known_tool}' in tools list"
        )
    print(f"✅ All {len(known_tools)} known tools found")
    
    # NEW: Verify DB persistence
    print("\n💾 Step 9: Verifying complete DB persistence...")
    assert status_data.get("finished_at") is not None
    
    # Check outputs in database match
    db_outputs = status_data.get("outputs", [])
    tools_in_db = any(
        isinstance(o.get("content"), dict) and "tools_count" in o.get("content", {})
        for o in db_outputs
    )
    assert tools_in_db, "Expected tools output persisted in database"
    print("✅ Complete outputs persisted to database")
```

---

### Phase 5: Logging & Observability (Items 14-15)

#### 14. Add Logging for Tool Calls
**File**: `src/services/orchestrator.py`
**Method**: `_execute_step()`

**Changes**:
```python
# After parsing tool call, before execution
log.info(
    "orchestrator.tool_call.executing",
    tool=step.action,
    args_summary={k: type(v).__name__ for k, v in (step.input or {}).items()},
    step_id=step.id
)

# After execution
log.info(
    "orchestrator.tool_call.completed",
    tool=step.action,
    output_size=len(str(output)) if output else 0,
    success=output.get("ok", True) if isinstance(output, dict) else True,
    step_id=step.id
)
```

#### 15. Log Storage Errors as Errors
**File**: `src/services/orchestrator.py`
**Method**: `_execute_todo_with_steps()`

**Changes**:
```python
# Change from log.info to log.error
if not tools_data:
    log.error(  # Changed from log.info
        "orchestrator.store.no_data",
        todo=todo.task,
        reason="No discovered_tools in context"
    )
    raise ValueError("Cannot store tools: no data available")
```

---

### Phase 6: Runtime Config (Items 16-17)

#### 16. Ensure LLM Warmup
**File**: `src/services/orchestrator.py`
**Method**: `from_env()` or initialization

**Changes**:
```python
@classmethod
async def from_env(cls, ...) -> Orchestrator:
    # ... existing setup ...
    
    # Warm up main LLM before tool-forcing operations
    if main_llm_client:
        log.info("orchestrator.llm.warmup.start", model=main_llm_name)
        try:
            await main_llm_client.complete(
                prompt="Hello",
                max_tokens=5,
                timeout=1800.0
            )
            log.info("orchestrator.llm.warmup.success", model=main_llm_name)
        except Exception as e:
            log.warning("orchestrator.llm.warmup.failed", model=main_llm_name, error=str(e))
```

#### 17. Fail Fast if <32 MCP Tools Registered
**File**: `src/services/orchestrator.py`
**Method**: `from_env()` after MCP loading

**Changes**:
```python
# After loading MCP tools
mcp_tools_count = len([t for t in self._tools.keys() if not t.startswith("llm:")])
log.info("orchestrator.mcp_loaded", tools_registered=mcp_tools_count)

if mcp_tools_count < 32:
    log.error(
        "orchestrator.mcp.insufficient_tools",
        expected=32,
        actual=mcp_tools_count,
        tools=list(self._tools.keys())
    )
    raise RuntimeError(
        f"Expected at least 32 MCP tools, found {mcp_tools_count}. "
        f"Tool discovery will not work correctly."
    )
```

---

### Phase 7: Build & Test (Items 18-19)

#### 18. Build Instructions
**Command**:
```bash
docker compose up -d --build --remove-orphans
```

#### 19. Run Integration Test
**Command**:
```bash
docker compose exec -T app python -m pytest \
  tests/integration/test_agent_execution.py::TestAgentExecution::test_agent_run_executes_successfully \
  -xvs --tb=short
```

**Expected duration**: Up to 15 minutes
**Expected behavior**: Full output (no tails), test passes with ≥30 tools discovered

---

## Summary of File Changes

### Files to Modify:
1. `tests/conftest.py` - Add Auth0 token fetching fixture
2. `tests/integration/test_agent_execution.py` - Update assertions for tool discovery
3. `src/services/orchestrator.py` - Major changes:
   - Force tool calling for discovery intent
   - Add response validation
   - Persist discovered tools in context
   - Enforce storage reads from context
   - Ensure JSON output format
   - Enhanced logging
   - Warmup and validation
4. `src/adapters/llm.py` - May need to add `force_tool_call` parameter support

### New Methods to Add:
- `Orchestrator._validate_tool_response()` - Validate structured responses
- `Orchestrator._get_tool_schema()` - Get tool schema for forcing
- `Orchestrator._detect_tool_discovery_intent()` - Detect discovery intent
- `Orchestrator._format_tools_output()` - Format final tools output

### Configuration Changes:
- None required (relies on existing `.env` settings)

---

## Testing Strategy

1. **Unit Tests**: Test each new method in isolation
2. **Integration Test**: Full flow from prompt to structured output
3. **Validation**: Ensure no prose, ≥30 tools, correct structure
4. **Performance**: Monitor LLM warmup time and total execution time

---

## Risk Mitigation

1. **Backward Compatibility**: Tool discovery changes should not affect other agent flows
2. **Fallback**: If tool calling fails, log error but don't crash
3. **Timeout Handling**: Ensure 30-minute timeouts are sufficient
4. **Memory**: Monitor for memory issues with mistral-7b (requires 5.7GB)

---

## Next Steps

Ready to implement these changes? The plan is comprehensive and production-ready. Each phase builds on the previous one.

**Recommendation**: Implement in phases, test after each phase, commit frequently.
