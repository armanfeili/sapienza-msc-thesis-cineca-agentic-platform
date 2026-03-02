# Graph Tools Implementation Plan

## Overview
Comprehensive hardening and testing of 4 graph tools: **search**, **analytics**, **crud**, **bulk**

## Execution Strategy

### Phase 1: Foundation (Applies to all 4 tools)
**Priority: CRITICAL** - Must be done first to establish consistent patterns

#### 1.1 Pydantic Schema Definitions
- [ ] `src/mcp/schemas.py` - Add schemas for all 4 tools
  - `GraphSearchPayload` with action enum
  - `GraphAnalyticsPayload` with action enum
  - `GraphCrudPayload` with action enum (update existing if present)
  - `GraphBulkPayload` with action enum
  - All with `timeout_ms=5000`, proper defaults, validation rules

#### 1.2 @mcp_tool Decorator Integration
- [ ] Update all 4 `invoke()` functions to use `@mcp_tool` decorator
- [ ] Apply validated payload merge pattern (like P1 tools)
- [ ] Ensure all return `{ok, data?, error?, trace_id, event_id, duration_ms}`

#### 1.3 RBAC Scope Enforcement
- [ ] Define scope matrix:
  - Read operations → `tools:basic`
  - Write/modify → `tools:all`  
  - Admin operations → `admin:all`
- [ ] Add scope parameter to each `@mcp_tool` call
- [ ] Test deny paths for missing scopes

#### 1.4 Audit & Metrics
- [ ] Verify audit_access calls emit correct events
- [ ] Add Prometheus metrics registration for all tools
- [ ] Test audit trail in integration tests

---

### Phase 2: graph.search (Week 1)
**Status: STARTING POINT**

#### 2.1 Implementation
- [ ] Review/update `src/mcp/tools/graph/search.py`
- [ ] Implement actions: `nodes`, `edges`, `count`, `distinct`
- [ ] Add predicate support: eq, neq, gt, gte, lt, lte, contains, starts_with, in
- [ ] Pagination with `page`, `page_size`, returns `{items, page, page_size, total}`
- [ ] Projection with `select` fields
- [ ] Ordering with `order_by` + whitelist
- [ ] Read-only enforcement

#### 2.2 Unit Tests
Create `tests/mcp/tools/test_graph_search.py`:
- [ ] Schema validation tests (10 tests)
- [ ] Filter/predicate tests (12 tests)
- [ ] Pagination tests (6 tests)
- [ ] Projection tests (4 tests)
- [ ] Security tests (8 tests)
- [ ] **Target: 40 unit tests**

#### 2.3 Integration Tests  
Create `tests/integration/test_graph_search_integration.py`:
- [ ] End-to-end node search with filters
- [ ] End-to-end edge search
- [ ] Count accuracy
- [ ] Distinct values
- [ ] Audit verification
- [ ] **Target: 6 integration tests**

---

### Phase 3: graph.analytics (Week 2)
**Status: QUEUED**

#### 3.1 Implementation
- [ ] Review/update `src/mcp/tools/graph/analytics.py`
- [ ] Actions: `degree_distribution`, `shortest_path`, `top_k_degree`, `label_counts`, `relationship_counts`
- [ ] Optional: `connected_components` with timeout guards
- [ ] Read-only enforcement with procedure blocking
- [ ] Input bounds: `k` limits, `max_depth`, `row_limit`, mandatory timeouts

#### 3.2 Unit Tests
Create `tests/mcp/tools/test_graph_analytics.py`:
- [ ] Schema validation (8 tests)
- [ ] Each action happy path (6 tests)
- [ ] Bounds enforcement (8 tests)
- [ ] Read-only enforcement (6 tests)
- [ ] Security tests (6 tests)
- [ ] **Target: 34 unit tests**

#### 3.3 Integration Tests
Create `tests/integration/test_graph_analytics_integration.py`:
- [ ] Label counts against fixture
- [ ] Shortest path within depth
- [ ] Top-k degree
- [ ] Audit/metrics verification
- [ ] **Target: 5 integration tests**

---

### Phase 4: graph.crud (Week 3)
**Status: QUEUED**

#### 4.1 Implementation
- [ ] Review/update `src/mcp/tools/graph/crud.py`  
- [ ] Actions: `create_node`, `update_node`, `delete_node`, `get_node`
- [ ] Actions: `create_edge`, `update_edge`, `delete_edge`, `get_edge`
- [ ] Optional: `upsert_node`, `upsert_edge`
- [ ] Strict write scope enforcement
- [ ] Ambiguous match rejection
- [ ] Cross-tenant isolation

#### 4.2 Unit Tests
Create `tests/mcp/tools/test_graph_crud.py`:
- [ ] Schema validation (10 tests)
- [ ] Node CRUD operations (12 tests)
- [ ] Edge CRUD operations (12 tests)
- [ ] Security/RBAC tests (10 tests)
- [ ] Validation tests (8 tests)
- [ ] **Target: 52 unit tests**

#### 4.3 Integration Tests
Create `tests/integration/test_graph_crud_integration.py`:
- [ ] Create-update-delete roundtrip (nodes)
- [ ] Create-update-delete roundtrip (edges)
- [ ] Cross-tenant isolation
- [ ] Audit/metrics
- [ ] **Target: 5 integration tests**

---

### Phase 5: graph.bulk (Week 4)
**Status: QUEUED**

#### 5.1 Implementation
- [ ] Review/update `src/mcp/tools/graph/bulk.py`
- [ ] Actions: `ingest_nodes`, `ingest_edges`, `upsert_nodes`, `upsert_edges`
- [ ] Dry-run mode
- [ ] Batching with configurable size
- [ ] Idempotency with keys
- [ ] Progress counters: `{processed, succeeded, failed}`
- [ ] Rate limiting with `retry_after`
- [ ] Partial failure handling

#### 5.2 Unit Tests
Create `tests/mcp/tools/test_graph_bulk.py`:
- [ ] Schema validation (8 tests)
- [ ] Batch operations (10 tests)
- [ ] Idempotency tests (6 tests)
- [ ] Dry-run tests (4 tests)
- [ ] Progress tracking (6 tests)
- [ ] Security tests (8 tests)
- [ ] **Target: 42 unit tests**

#### 5.3 Integration Tests
Create `tests/integration/test_graph_bulk_integration.py`:
- [ ] Bulk nodes roundtrip
- [ ] Bulk edges roundtrip
- [ ] Dry-run zero writes
- [ ] Idempotency verification
- [ ] Audit/metrics
- [ ] **Target: 6 integration tests**

---

### Phase 6: Test Infrastructure (Parallel with Phases 2-5)

#### 6.1 Fixtures
Create `tests/fixtures/graph_data.py`:
- [ ] Deterministic seed data (users, institutions, tasks, files, edges)
- [ ] Wipe & reseed helper
- [ ] Known counts for validation

#### 6.2 Helpers
Create `tests/helpers/graph_tools.py`:
- [ ] `invoke_tool(tool_name, payload)` helper
- [ ] Standard envelope assertions
- [ ] Auth token management (USER_TOKEN, ADMIN_TOKEN)

#### 6.3 Integration Test Base
Create `tests/integration/conftest.py`:
- [ ] Shared fixtures for all integration tests
- [ ] Docker Memgraph setup/teardown
- [ ] Auth0 token management
- [ ] Performance SLA guards

---

### Phase 7: Documentation (Final Week)

#### 7.1 API Reference
Update `docs/MCP_TOOLS_REFERENCE.md`:
- [ ] Complete action lists for all 4 tools
- [ ] Request/response examples
- [ ] RBAC scope requirements
- [ ] Safety rules documentation

#### 7.2 Examples
Create `docs/examples/graph_tools_examples.md`:
- [ ] Common patterns for each tool
- [ ] Error handling examples
- [ ] Best practices

---

## Success Metrics

### Test Coverage Targets
- **graph.search**: 40 unit + 6 integration = 46 tests
- **graph.analytics**: 34 unit + 5 integration = 39 tests
- **graph.crud**: 52 unit + 5 integration = 57 tests
- **graph.bulk**: 42 unit + 6 integration = 48 tests
- **Total**: 168 unit + 22 integration = **190 new tests**

### Quality Gates
- [ ] All tests passing (100% pass rate)
- [ ] RBAC enforced on all write operations
- [ ] Audit events present for all operations
- [ ] No regressions in existing P1 tests (134 tests still passing)
- [ ] Integration tests pass with Docker Memgraph
- [ ] Documentation complete and accurate

### CI Integration
- [ ] Add new test suites to CI pipeline
- [ ] Performance guards in place (< 2s per analytics call)
- [ ] Mark long-running tests appropriately

---

## Recommended Execution Order

1. **Week 1**: Foundation + graph.search (46 tests)
2. **Week 2**: graph.analytics (39 tests)
3. **Week 3**: graph.crud (57 tests)
4. **Week 4**: graph.bulk (48 tests)
5. **Final**: Documentation polish & CI integration

## Current Status

- **P1 Baseline**: 134 tests passing ✅
- **Phase 1**: Not started
- **Phase 2**: Not started  
- **Phase 3**: Not started
- **Phase 4**: Not started
- **Phase 5**: Not started
- **Phase 6**: Not started
- **Phase 7**: Not started

---

## Next Immediate Actions

1. Create Pydantic schemas for all 4 tools
2. Start graph.search implementation
3. Create test file structure
4. Build fixture infrastructure

**Estimated Total Effort**: 4 weeks for complete implementation and testing
