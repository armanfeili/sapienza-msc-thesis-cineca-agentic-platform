# P1 Task 3: graph.secure_query Hardening — COMPLETE ✅

**Status:** ✅ Complete  
**Date:** 2025-06-XX  
**Tests:** 26/26 passing  
**Time:** ~1.5 hours

---

## 🎯 Objective

Harden the **graph.secure_query** tool (flagship NL→Cypher→Results gateway) with:
- P0 runtime infrastructure (`@mcp_tool` decorator)
- Pydantic v2 schema validation
- Comprehensive test coverage

---

## 📋 Implementation Summary

### 1. Tool Code Updates (`src/mcp/tools/graph/secure_query.py`)

**Changes:**
- ✅ Added P0 imports: `mcp_tool`, `ToolContext`, `GraphSecureQueryPayload`
- ✅ Wrapped `invoke()` with `@mcp_tool(tool_name="graph.secure_query", required_scope="tools:basic")`
- ✅ Added Pydantic validation: `validated = GraphSecureQueryPayload(**payload)`
- ✅ Removed manual `audit_access()` calls (now automatic via decorator)
- ✅ Preserved all security features: write detection, forbidden clause blocking, NL→Cypher generation

**Before:**
```python
def invoke(payload: dict, principal: str, tenant: str) -> dict:
    """Secure query invocation with manual audit."""
    audit_access(...)  # Manual audit
    action = payload.get("action")
    # ... action dispatch
```

**After:**
```python
@mcp_tool(tool_name="graph.secure_query", required_scope="tools:basic")
def invoke(payload: dict, ctx: ToolContext) -> dict:
    """Secure query invocation with automatic RBAC/audit."""
    validated = GraphSecureQueryPayload(**payload)  # Pydantic validation
    action = validated.action
    # ... action dispatch (same as before)
```

---

### 2. Schema Updates (`src/mcp/schemas.py`)

**Changes:**
- ✅ Fixed `GraphSecureQueryPayload` validators
- ✅ Replaced `@field_validator` with `@model_validator(mode="after")` for action-dependent validation
- ✅ Combined prompt/cypher validation into single `validate_action_requirements()` method

**Validation Logic:**
```python
@model_validator(mode="after")
def validate_action_requirements(self):
    """Validate required fields based on action."""
    action = self.action
    
    # ask and generate require prompt
    if action in {"ask", "generate"}:
        if not self.prompt:
            raise ValueError(f"'prompt' is required for action '{action}'")
    
    # validate and execute require cypher
    if action in {"validate", "execute"}:
        if not self.cypher:
            raise ValueError(f"'cypher' is required for action '{action}'")
    
    return self
```

**Why model_validator?**
- `@field_validator` doesn't have access to other fields during validation
- `@model_validator(mode="after")` validates the entire model after all fields are set
- Same pattern as `GraphGenerateCypherPayload` (proven working)

---

### 3. Test Suite (`tests/mcp/tools/test_graph_secure_query.py`)

**Coverage:** 26 tests organized into 8 categories

| Category | Tests | Focus |
|----------|-------|-------|
| Schema Validation | 5 | Required fields per action (prompt for ask/generate, cypher for validate/execute) |
| Security Validation | 6 | Write detection (CREATE, MERGE, DELETE, SET, DROP), forbidden clauses |
| Execute Action | 5 | Safe execution, params, write blocking, max_rows limit, timeout enforcement |
| Result Formatting | 4 | Output formats: rows, json, csv, markdown |
| Generate Action | 1 | NL→Cypher generation with mocked LLM |
| Ask Action | 1 | End-to-end: generate→validate→execute pipeline |
| RBAC | 2 | Principal requirement, authentication context |
| Edge Cases | 2 | Empty results, case-insensitive keyword detection |

**Key Test Patterns:**
```python
# Schema validation
def test_schema_validation_ask_requires_prompt(mock_memgraph, mock_llm):
    with pytest.raises(ValidationError) as exc:
        invoke({"action": "ask", "principal": "...", "tenant": "..."}, ctx)
    assert "'prompt' is required" in str(exc.value)

# Security validation
def test_validate_blocks_create(mock_memgraph):
    result = invoke({
        "action": "validate",
        "cypher": "CREATE (n:User {name: $name})",
        "principal": "...", "tenant": "..."
    }, ctx)
    assert result["ok"] is False
    assert "write operations not allowed" in result["error"]

# Execute with formatting
def test_execute_format_json(mock_memgraph):
    result = invoke({
        "action": "execute",
        "cypher": "MATCH (n:User) RETURN n.name",
        "return_format": "json",
        "principal": "...", "tenant": "..."
    }, ctx)
    assert result["ok"] is True
    assert '"name": "Alice"' in result["data"]
```

**Fixtures:**
- `mock_memgraph`: Returns 2 sample users (Alice, Bob)
- `mock_llm`: Returns sample `MATCH (n:User) RETURN n LIMIT 100`

---

## 🧪 Test Results

```bash
pytest tests/mcp/tools/test_graph_secure_query.py -v

# ✅ 26 passed in 1.84s
```

**All P1 Tests (Tasks 1-3):**
```bash
pytest tests/mcp/tools/test_graph_query.py \
       tests/mcp/tools/test_graph_generate_cypher.py \
       tests/mcp/tools/test_graph_secure_query.py -v

# ✅ 78 passed in 3.34s
# - graph.query: 22 tests
# - graph.generate_cypher: 30 tests
# - graph.secure_query: 26 tests
```

---

## 🔒 Security Features Preserved

The hardened `graph.secure_query` maintains all original security features:

1. **Write Detection** (regex-based):
   - Blocks: `CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`
   - Allows: `MATCH`, `RETURN`, `WITH`, `WHERE`, `ORDER BY`, `LIMIT`

2. **Forbidden Clause Detection** (regex-based):
   - Blocks: `DROP DATABASE`, `AUTH`, `CLEAR`, `TERMINATE`, `KILL`, `SHUTDOWN`

3. **Safety Validation** (`_validate_cypher()`):
   - Case-insensitive keyword detection
   - Regex patterns: `WRITE_PATTERN`, `FORBIDDEN_PATTERN`

4. **Permission Checks** (`_check_permissions()`):
   - RBAC integration via `permissions_adapter.check_permission()`
   - Action: `read` (read-only) or `write` (CREATE/MERGE/DELETE/SET)
   - Resource: `memgraph:query`

5. **NL→Cypher Generation** (`_generate_cypher_from_nl()`):
   - Uses `llm_adapter.generate_cypher()` with structured prompts
   - Safety instructions: "Only generate read-only queries..."
   - Example generation included in prompt

6. **Result Formatting**:
   - `rows`: Raw dictionaries (default)
   - `json`: Pretty-printed JSON
   - `csv`: Comma-separated values
   - `markdown`: GitHub-flavored table

---

## 📊 Tool Architecture

```
graph.secure_query
├── 4 Actions:
│   ├── ask: NL → generate → validate → execute → format
│   ├── generate: NL → Cypher (no execution)
│   ├── validate: Cypher → safety check (no execution)
│   └── execute: Cypher → run + format
│
├── Security Validators:
│   ├── _validate_cypher(query) → raises if write/forbidden
│   └── _check_permissions(action, principal, tenant) → raises if denied
│
├── NL→Cypher Generation:
│   └── _generate_cypher_from_nl(prompt, max_rows) → Cypher string
│
└── Result Formatters:
    ├── _format_rows(rows) → list[dict]
    ├── _format_json(rows) → JSON string
    ├── _format_csv(rows) → CSV string
    └── _format_markdown(rows) → Markdown table
```

---

## 🔍 Debugging Notes

### Issue 1: Schema Validation Not Triggering

**Symptom:** Tests expected `ValidationError` but none was raised.

**Root Cause:** `@field_validator` doesn't have access to other fields during validation:
```python
# ❌ Doesn't work
@field_validator("prompt", mode="after")
def validate_prompt_required(cls, v, info):
    action = info.data.get("action")  # ⚠️ action not available yet
    if action in {"ask", "generate"} and not v:
        raise ValueError("...")
```

**Solution:** Use `@model_validator(mode="after")`:
```python
# ✅ Works
@model_validator(mode="after")
def validate_action_requirements(self):
    action = self.action  # ✅ All fields available
    if action in {"ask", "generate"} and not self.prompt:
        raise ValueError("...")
```

**Lesson:** Action-dependent validation requires `@model_validator`, not `@field_validator`.

---

## ✅ Completion Checklist

- [x] Update tool code with `@mcp_tool` decorator
- [x] Add Pydantic schema validation (`GraphSecureQueryPayload`)
- [x] Remove manual `audit_access()` calls
- [x] Fix schema validators (use `@model_validator`)
- [x] Create comprehensive test suite (26 tests)
- [x] Run and verify all tests pass (26/26 ✅)
- [x] Verify all P1 tests pass (78/78 ✅)
- [x] Document completion (this file)

---

## 📈 Impact

**Before Hardening:**
- Manual RBAC checks (easy to forget)
- No input validation (runtime errors possible)
- No test coverage

**After Hardening:**
- Automatic RBAC enforcement (decorator)
- Pydantic validation (fail-fast on bad input)
- 26 tests covering all actions, security, formatting, RBAC

**Security Improvements:**
- ✅ All requests require `principal` + `tenant` (enforced by schema)
- ✅ All requests audited automatically (via decorator)
- ✅ Invalid payloads rejected before execution
- ✅ Write operations blocked (unless explicitly allowed)
- ✅ Forbidden clauses always blocked

---

## 🚀 Next Steps

**P1 Task 4:** Harden `security.permissions` tool
- Apply same pattern: `@mcp_tool` + Pydantic + tests
- Estimated: 1 hour

**P1 Task 5:** Harden `graph.schema` tool
- Apply same pattern: `@mcp_tool` + Pydantic + tests
- Estimated: 1 hour

**Final Integration:** Real-world testing
- Docker services: Memgraph, PostgreSQL, Redis
- Auth tokens: ADMIN_TOKEN, USER_TOKEN, MACHINE_TOKEN
- End-to-end: NL prompt → Cypher → Results

---

## 📝 Code Changes

**Files Modified:**
1. `/src/mcp/tools/graph/secure_query.py` (~538 lines)
2. `/src/mcp/schemas.py` (updated `GraphSecureQueryPayload` validator)

**Files Created:**
1. `/tests/mcp/tools/test_graph_secure_query.py` (519 lines, 26 tests)

**Total Lines Changed:** ~60 lines modified, ~519 lines added

---

## 🎓 Lessons Learned

1. **Model Validators for Cross-Field Validation:**
   - Use `@model_validator(mode="after")` when validation depends on multiple fields
   - `@field_validator` only has access to the current field

2. **Mocking External Services:**
   - Mock Memgraph with `mock_memgraph` fixture (returns sample data)
   - Mock LLM with `mock_llm` fixture (returns sample Cypher)
   - Keeps tests fast and deterministic

3. **Consistent Patterns:**
   - All P1 tools follow same structure: decorator → validation → action dispatch
   - Makes debugging easier (same patterns across tools)

4. **Security by Default:**
   - Decorator enforces RBAC/audit without manual calls
   - Schema enforces required fields (principal, tenant)
   - Fail-fast on invalid input

---

**Completion Date:** 2025-06-XX  
**Completed By:** AI Agent  
**Validated By:** Test Suite (26/26 passing)  
**Status:** ✅ **COMPLETE - Ready for P1 Task 4**
