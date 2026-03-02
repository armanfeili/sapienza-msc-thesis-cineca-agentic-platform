## Unreleased

### Changed

- **Agent API Response Schema - Type Safety Upgrade**:
  - **BREAKING CHANGE**: Agent run response format now uses strongly-typed Pydantic models instead of generic dictionaries
  - **New Response Models**:
    - `OrchestrationStepInput`: Typed model for planned execution steps (type="step")
      - Fields: `step_id` (str), `action` (str), `input` (dict | None)
    - `OrchestrationStepOutput`: Typed model for step execution results (type="output")
      - Fields: `step_id` (str), `output` (dict | None), `error` (str | None)
    - `TodoItem`: Typed model for agent TODO tasks with status tracking
      - Fields: `task` (str), `status` (Literal["pending", "in_progress", "completed", "failed"] | None)
    - `ExecutionMetrics`: Performance tracking model (reserved for future use)
      - Fields: `model_warmup_ms`, `todo_creation_ms`, `total_llm_calls`, `tool_errors`, `step_count`
  - **Response Schema Changes**:
    - `steps`: Changed from `list[dict[str, Any]]` to `list[OrchestrationStepInput | OrchestrationStepOutput]` (discriminated union)
    - `todos`: Changed from `list[dict[str, str]]` to `list[TodoItem]`
    - `errors`: Added new field `list[str] | None` for error aggregation
    - `metrics`: Added new field `ExecutionMetrics | None` for performance data (currently None, will be populated when orchestrator provides timing data)
  - **Benefits**:
    - Full type safety with Pydantic v2 validation
    - OpenAPI schema now shows proper typed structures instead of generic objects
    - Type-safe client SDK generation (TypeScript, Python, etc.)
    - Better IDE autocomplete and type checking
    - Discriminated unions for step vs output distinction
  - **Migration Notes**:
    - Clients parsing `steps` field must handle discriminated union (`type` field)
    - Clients parsing `todos` field must access structured objects instead of plain dicts
    - New `errors` field provides centralized error collection
    - Database storage automatically serializes Pydantic models to JSON

- **Pydantic v2 Migration (agents.py)**:
  - Migrated `SessionResponse`, `StepResponse`, and `RunResponse` to Pydantic v2
  - Replaced `class Config` with `model_config = ConfigDict(from_attributes=True)`
  - All new models use Pydantic v2 patterns (ConfigDict, Literal types for discriminated unions)

### Removed

- **Legacy UI Directory**: Deleted deprecated `ui_streamlit/` directory (commit 8e38a4f)
  - Empty directory that was superseded by active UI implementation at `ui_control_panel/`
  - Resolves confusion between UI directories
  - Documentation updated to reflect single UI location

### Added

- **Complete Test Suite Achievement (931/931 passing - 100%)**:
  - **Unskipped LLM-dependent tests**: Implemented deterministic LLM stub fixture for `graph.secure_query` "ask" action tests
    - Added `_DeterministicLLMStub` class in `tests/conftest.py` with predictable Cypher generation
    - Removed `@pytest.mark.skip` from `test_ask_requires_principal` and `test_ask_requires_tenant`
    - All RBAC tests now passing with stable, non-network-dependent mocks
  - **Enhanced CALL procedure write detection**: Extended write detection to catch dangerous database procedures
    - Updated `_WRITE_PAT` regex in both `graph.query` and `graph.secure_query` to deny `CALL db.create*`, `db.alter*`, `db.drop*`, `db.execute*`, `db.set*`, `db.delete*`, `db.add*`, `db.remove*`, `db.update*`, `db.insert*`, `db.merge*`, and APOC variants by default
    - Maintains allowlist for safe procedures: `db.labels`, `db.relationshipTypes`, `db.propertyKeys`, `db.indexes`, `db.constraints`, `db.info`, `db.stats`, etc.
    - Removed `@pytest.mark.xfail` from 3 CALL db.* edge case tests - all now passing
  - **Normalized error messages**: All read-only violations now consistently include keywords: "write", "modify", or "read-only" for uniform test assertions
  - **Test Results**:
    - **931 passed, 0 skipped, 0 xfailed, 0 failures**
    - All graph query security tests green
    - All write detection edge cases passing
    - All RBAC enforcement tests passing

- **MCP Tools Registry Finalization**:
  - **New Tools Added**:
    - `graph.secure_query@1`: Safely answer user prompts over Memgraph with NL→Cypher translation, validation (read-only + safety + permissions), and secure execution. Provides end-to-end natural language querying with comprehensive security guardrails.
      - Actions: `ask` (end-to-end), `generate` (NL→Cypher), `validate` (safety checks), `execute` (safe execution)
      - Security features: Read-only enforcement, forbidden clause detection, tenant scoping, permission checks, rate limiting (10/min recommended), timeout protection (5s default), row limits (1000 default)
      - Capabilities: `reads_db`, `nl_to_cypher`, `policy_enforced`
      - Scope: `tools:basic` (read-only access only)
    - `data.archive@1`: Mark, restore, purge, or list archived data (long-running operation)
    - `data.quality@1`: Run data quality checks on graph nodes and relationships
    - `errors.report@1`: Record and retrieve structured error reports
    - `viz.render@1`: Render helpers for graphs, tables, and sparklines (Mermaid/DOT/Markdown/sparkline) - replaced generic `viz` tool
  - **Total Tool Count**: 32 MCP tools (up from 27)
  
- **MCP Manifest Standardization & Normalization**:
  - **Action-Aware Input Schemas**: All 28 multi-action tools now declare explicit `action` enums with required fields in `input_schema`
    - Examples: `graph.query` → `["run","explain","profile"]`, `system.health` → `["liveness","readiness","details"]`, `data.archive` → `["mark","restore","purge","status","list"]`
    - Improved client discoverability and eliminated payload ambiguity
  - **Normalized Metadata Structure**: All 32 tools now have consistent fields:
    - `id` (format: `<name>@1`), `name`, `module` (matches `src.mcp.tools.*` paths), `description` (crisp one-liners)
    - `capabilities` (non-empty semantic tags), `scopes` (RBAC permissions), `namespace` (false for all)
    - `long_running` (true only for `data.archive`, `system.backup`), `input_schema` (action-aware)
  - **Capability Tags** (20 unique capabilities):
    - Database: `reads_db`, `writes_db`
    - NL & Security: `nl_to_cypher`, `policy_enforced`
    - Domain-specific: `data_management`, `model_management`, `session_management`, `user_management`, `tenancy_management`, `cache_management`, `ratelimit_management`, `database_management`, `error_tracking`
    - System: `system_info`, `security_audit`, `visualization`, `output_formatting`, `privacy_management`, `tool_discovery`, `agent_orchestration`
  - **Standardized RBAC Scopes** (3-tier permission model):
    - `tools:basic` (19 tools): Read-only, safe operations (e.g., `graph.schema`, `graph.search`, `graph.secure_query`, `system.health`, `system.metrics`, `system.status`)
    - `tools:all` (10 tools): Write/admin-light operations (e.g., `graph.crud`, `graph.bulk`, `graph.query`, `data.archive`, `system.backup`, `cache.manage`, `db.switch`)
    - `admin:all` (3 tools): Security & tenancy administration (e.g., `security.audit`, `security.permissions`, `tenancy.manage`)
  - **Module Path Verification**: All `module` fields verified to match repository structure exactly (e.g., `src.mcp.tools.graph.secure_query`)
  - **Categories Expanded**: 17 categories covering agent, cache, catalog, data, db, errors, graph, model, output, privacy, ratelimit, security, session, system, tenancy, user, viz

- **Policy Configuration Updates**:
  - Added `tools:basic`, `tools:all`, `admin:all` scopes to `src/mcp/policies.yaml`
  - Mapped scopes to roles: `user` → `tools:basic`, `operator` → `tools:basic` + `tools:all`, `admin` → `admin:all`
  - Aligned policy scopes with manifest tool scopes for consistent RBAC enforcement

- **Documentation Enhancements**:
  - `docs/MCP_TOOLS_REFERENCE.md`: Added comprehensive documentation for `graph.secure_query` with action tables, payload examples, return shapes, security features, and use cases
  - Updated tool count from 7 to 8 graph tools, reflecting addition of `graph.secure_query`
  - `scripts/verify_manifest.py`: Verification script validates all normalization requirements (tool count, metadata completeness, ID format, module paths, capabilities, scopes, long-running flags, action-aware schemas, special tool configurations)

### Changed

- **Tool Descriptions**: Standardized all 32 tool descriptions to crisp, consistent one-liners following "MCP Tool: ..." pattern
  - Example: "Execute ad-hoc Cypher with safety knobs" → "Execute ad-hoc Cypher query against Memgraph with optional parameters"
- **`viz` Tool Replacement**: Generic `viz` tool replaced with properly structured `viz.render@1` exposing 4 actions:
  - `graph_mermaid`, `graph_dot`, `table_markdown`, `sparkline`
  - Improved action-specific field validation and clearer intent separation

### Implementation

- **`graph.secure_query` Module**: Full implementation at `src/mcp/tools/graph/secure_query.py` with:
  - NL→Cypher generation using LLM adapter with schema context
  - Security validation: write operation detection, forbidden clause blocking, tenant scoping checks
  - Permission verification with policy engine integration points
  - Safe execution with timeout protection and row limiting
  - Multi-format result rendering (rows, JSON, CSV, Markdown)
  - Comprehensive audit trail integration
  - 4 actions: `ask`, `generate`, `validate`, `execute`

### Verification

- All manifest verification checks passing:
  - ✅ Tool count: 32/32
  - ✅ All expected tools present (including `graph.secure_query`, `viz.render`)
  - ✅ Metadata completeness: 9 required fields present for all tools
  - ✅ ID format: All IDs follow `<name>@1` pattern
  - ✅ Module paths: All modules start with `src.mcp.tools.`
  - ✅ Capabilities: 20 unique capability tags, all tools have at least one
  - ✅ Scopes: 3 unique scopes, all tools have at least one
  - ✅ Long-running: Only `data.archive` and `system.backup` marked as `long_running: true`
  - ✅ Action-aware: 28/32 tools have action enums with required fields
  - ✅ Special tools: `graph.secure_query` has safety metadata, `viz.render` has 4 actions

---

### Previous Changes

- **MCP Tools Registry Reconciliation & Normalization** (Earlier):
  - **New Tools Added**:
    - `graph.secure_query@1`: End-to-end NL→Cypher with guardrails, permissions, and read-only enforcement (safe natural language querying)
    - `data.archive@1`: Mark, restore, purge, or list archived data
    - `data.quality@1`: Run data quality checks on graph nodes and relationships
    - `errors.report@1`: Record and retrieve structured error reports
  - **Updated `viz.render@1`**: Replaced generic `viz` with properly structured `viz.render` exposing Mermaid/DOT graph rendering, Markdown tables, and sparklines
  - **Total Tool Count**: 32 MCP tools (previously 27)
  
- **MCP Manifest Standardization**:
  - **Unified Metadata**: All tools now have consistent `id`, `module`, `description`, `capabilities`, `scopes`, `namespace`, and `long_running` fields
  - **Action-Aware Input Schemas**: Every tool now declares action enums and required fields in `input_schema` (eliminates ambiguity, improves client discoverability)
  - **Normalized Capabilities**:
    - `reads_db`, `writes_db`: Graph database operations
    - `nl_to_cypher`, `policy_enforced`: NL translation & security
    - `data_management`, `model_management`, `session_management`, etc.: Domain-specific tags
    - `system_info`, `security_audit`, `visualization`: System & observability
  - **Standardized Scopes**:
    - `tools:basic`: Read-only, safe operations (e.g., `graph.schema`, `graph.search`, `system.health`, `graph.secure_query`)
    - `tools:all`: Write/admin-light operations (e.g., `graph.crud`, `graph.bulk`, `data.archive`)
    - `admin:all`: Security & tenancy administration (e.g., `security.audit`, `security.permissions`, `tenancy.manage`)
  - **Long-Running Flags**: Only `data.archive@1` and `system.backup@1` marked `long_running: true`
  - **Categories Expanded**: 17 categories (agent, cache, catalog, data, db, errors, graph, model, output, privacy, ratelimit, security, session, system, tenancy, user, viz)

- **`graph.secure_query` Safety Metadata**:
  - Rate limit hint: `10/min per principal`
  - Safety block: Write operations blocked, read-only enforcement enabled, permission checks required
  - Actions: `ask` (end-to-end), `generate` (NL→Cypher only), `validate` (static checks), `execute` (validated read-only execution)
  - Required fields: `principal`, `tenant` for all actions (enforces multi-tenancy and audit trails)

### Changed

- **MCP Tool Descriptions**: Unified to clear one-liners (e.g., "Execute ad-hoc Cypher with safety knobs" → "Execute ad-hoc Cypher query against Memgraph with optional parameters")
- **Action Enums Alignment**: All multi-action tools now have documented `action` enums matching implementation (e.g., `graph.query`: `["run", "explain", "profile"]`)
- **Module Paths Verified**: All `module` fields match repository layout exactly (e.g., `src.mcp.tools.graph.schema`)

### Breaking Changes

- **Model Instances User Access**: Model endpoints moved from admin-only to user-accessible at `/v1/models/*`. Old `/v1/admin/models/*` paths **DEPRECATED** (will be removed 2026-01-15, 90 days). Update clients to use `/v1/models/*` paths.
- **Model Defaults Scoping**: `PATCH /v1/models/defaults` now requires `X-Default-Scope` header (`user`|`tenant`|`global`). Defaults to `user` scope. Users can only set own defaults; admins can set tenant/global.
- **Provider API Pagination**: `GET /v1/admin/models/providers` now returns `{items, next_page_token, total}` instead of bare array
- **Provider API DELETE**: `DELETE /v1/admin/models/providers/{id}` returns `204 No Content` (was `200 OK` with JSON body)
- **Provider Secret Redaction**: API keys never exposed; replaced with `has_api_key: boolean` indicator
- **Problem+JSON Titles**: Error response titles now match HTTP status codes (401→"Unauthorized", 403→"Forbidden", etc.)
- **Provider RBAC**: All `/v1/admin/models/providers/*` endpoints require `admin:all` scope (non-admin returns 403)
- **Idempotency Status Codes**: Idempotent replays now return correct HTTP status (200 OK for replayed requests with proper `Idempotency-Replayed` header, 201 Created for new creates)

### Added

- **Agents API - Idempotency Semantics**: 
  - `IdempotencyKey` database model now persists HTTP `status_code` (stored in PostgreSQL)
  - Idempotent replays return 200 OK (not 201 Created) per RFC 7231 semantics
  - Status code cached in Redis alongside response body for fast replay path
  - Both `create_session` and `create_step` endpoints support proper idempotent semantics with status code preservation
  
- **Agents API - Rate Limiting Configuration**:
  - New `RATE_LIMIT_MODE` environment variable (`prod|test`) for dynamic rate limit configuration
  - Production mode: 10/min (sessions:create), 100/min (steps:create), 20/min (runs:create), 100/min (list operations)
  - Test mode: 10000/min for all operations (prevents fixture failures in test suites)
  - Configuration persisted via docker-compose environment (`RATE_LIMIT_MODE=test` in dev override)
  
- **Test Hygiene**:
  - Redis cleanup fixture in `tests/conftest.py` removes idempotency, session state, and cache keys after each test
  - Prevents test pollution from Redis keys persisting between test runs
  - Autouse fixture clears: `idempotency:*`, `session:*`, `etag:*`, `*:lock:*`, `seq:*` patterns
  
- **Model Instances User Access**: 
  - New user-accessible paths at `/v1/models/instances`, `/v1/models/defaults`, `/v1/models/instances/{id}`, `/v1/models/instances/{id}/tests`
  - Fine-grained permission scopes: `models:read`, `models:test`, `models:defaults:read`, `models:defaults:write:self`, `models:write`, `models:delete`, `models:defaults:write:tenant`, `models:defaults:write:global`
  - Users can list/get/test enabled instances (disabled instances return 404 to non-admins)
  - Per-user default model preferences with precedence resolution (user → tenant → global → 404)
  - `X-Default-Scope` response header indicating scope used (`user`|`tenant`|`global`)
  - Database migration `007_user_default_models` with FK CASCADE to model_instances
  - Repository layer for user defaults (UPSERT pattern, ETag support, cascade operations)
- **Model Defaults Precedence**: `GET /v1/models/defaults` resolves with 3-level precedence (user default → tenant default → global default)
- **Scope-Based Writes**: `PATCH /v1/models/defaults` accepts `X-Default-Scope` header for user/tenant/global scope selection with permission enforcement

- Provider API: RFC 5988 `Link` headers for pagination navigation
- Provider API: ETag caching support on GET endpoints (304 Not Modified responses)
- Provider API: Idempotency logic in registration (same config→200, different→409)
- Provider API: Health status caching with documented source (last check vs live)
- Provider API: Multi-tenant visibility documentation (global vs tenant-scoped providers)
- Comprehensive contract tests for provider API (50+ test cases)

### Changed

- Provider schemas: Migrated to canonical `src/schemas/providers.py` models
- Provider validation: Enhanced field-level errors (422) with proper `loc`, `msg`, `type` structure
- Provider timestamps: Standardized format (RFC3339 or Unix epoch)
- Health: admin readiness toggle now requires admin authentication (ADMIN_TOKEN header or JWT with admin scope). Calls are audited in logs (readiness.toggled).
- OpenAPI: admin endpoints are hidden when admin routes are disabled; readiness docs improved with examples.
- CI: scripts/publish_openapi_and_smoke.sh added to publish /v1/openapi.json and run a smoke check.
- Dockerfile: existing HEALTHCHECK against /v1/health/live is used to report container health.

Ops notes:
- MIGRATIONS_APPLIED env var or presence of /app/.migrations_ok controls migration gating when ENFORCE_MIGRATIONS=true.
- SHUTDOWN_DRAIN_SECONDS controls graceful drain on shutdown (default 15s).
- RATE_LIMIT_MODE environment variable controls rate limiter configuration (set to `test` in development for lenient limits)

