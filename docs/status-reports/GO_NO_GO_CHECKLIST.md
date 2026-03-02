# Go/No-Go Checklist - Production Readiness Review

**Date**: October 19, 2025  
**Status**: REVIEW IN PROGRESS  
**Branch**: chore/restify-tests-and-docs  

---

## 1. RATE LIMITS — Prod vs Test

### Criterion: Confirm RATE_LIMIT_MODE=prod in production manifests; keep test only for CI.

**Current State**:
```yaml
# docker-compose.yml (base)
RATE_LIMIT_MODE: "${RATE_LIMIT_MODE:-prod}"  # ✓ Defaults to prod

# docker-compose.override.yml & docker-compose.override.dev.yml
RATE_LIMIT_MODE: 'test'  # ✓ Override for local dev/testing
```

**Findings**:
- ✅ Production default is `prod` (safe fallback in compose.yml)
- ✅ Local overrides explicitly set `test` for relaxed limits
- ✅ Environment variable can override via CLI: `RATE_LIMIT_MODE=prod docker compose up`
- ⚠️ **Action Needed**: Kubernetes/cloud deployment manifests not reviewed (need to check helm charts, kustomize, or cloud provider configs)

**Config Values** (from `db/redis_cache/rate_limit.py`):
```python
"prod": {
    "sessions:create": 10/min,    "steps:create": 100/min,
    "runs:create": 20/min,        "sessions:list": 100/min,
    "steps:list": 100/min
}
"test": {
    "sessions:create": 10000/min,  "steps:create": 10000/min,
    "runs:create": 10000/min,      "sessions:list": 10000/min,
    "steps:list": 10000/min
}
```

**Status**: 🟡 **CONDITIONAL GO**
- ✅ Docker compose is correctly configured
- ⚠️ Need to verify Kubernetes/cloud manifests use `prod`
- ⚠️ Need to audit any CI/CD GitHub Actions workflows

**Remediation**: 
- [ ] Add check to CI/CD: fail if production manifests have `test` mode
- [ ] Document: "Production must run `RATE_LIMIT_MODE=prod`"

---

### Criterion: Verify the actual prod numbers in GET /health/startup or similar diagnostics match docs.

**Current State**:
- `GET /health/startup` exists ✅
- Rate limit config is hardcoded in `db/redis_cache/rate_limit.py` (not exposed as diagnostics)

**Findings**:
- ❌ No `/health/startup` endpoint currently exposes rate limit configuration
- The diagnostics show app version, but not RATE_LIMIT_MODE or current limits
- Users deploying must manually verify the mode or check logs

**Status**: 🔴 **NO-GO**

**Remediation** (Priority: HIGH):
- [ ] Add `rate_limit_mode` and per-action limits to `GET /health/startup` response
- [ ] Example response:
  ```json
  {
    "status": "ok",
    "version": "0.1.0",
    "environment": {
      "rate_limit_mode": "prod",
      "rate_limit_backend": "redis"
    },
    "limits": {
      "sessions:create": {"limit": 10, "window_sec": 60},
      "steps:create": {"limit": 100, "window_sec": 60}
    }
  }
  ```

---

### Criterion: Add a short runbook note: how to switch & validate the mode.

**Current State**:
- No runbook exists
- Mode is configured via environment variable (undocumented locally)

**Status**: 🔴 **NO-GO**

**Remediation** (Priority: HIGH):
- [ ] Create `docs/RATE_LIMITING_OPERATIONS.md` with:
  1. How to set mode locally: `RATE_LIMIT_MODE=prod docker compose up`
  2. How to verify: `curl http://localhost:8000/health/startup | jq .environment.rate_limit_mode`
  3. How to validate load: `./scripts/test_rate_limits.sh [mode]`
  4. Switching between modes requires restart (no hot-reload)

---

## 2. IDEMPOTENCY SEMANTICS

### Criterion: Ensure cached replays return the original status code & body with Idempotency-Replayed: true.

**Current State** (from `src/middleware/idempotency.py`):
```python
# Returns 200 OK on replay (currently hardcoded)
# Bug: Should return original status_code
```

**Findings**:
- ❌ All replayed requests return `200 OK` regardless of original status
- ❌ Original `status_code` is not persisted in cache
- ✅ `Idempotency-Replayed: true` header is correctly set
- ❌ Tests expect `201 Created` on creation replays but get `200 OK`

**RFC 7231 Compliance**:
- ❌ Non-compliant: replayed creations should return `201 Created`, not `200 OK`
- ❌ Non-compliant: replayed updates should return `200 OK` (currently does)
- ❌ Non-compliant: replayed deletions should return original code (currently returns 200)

**Status**: 🔴 **NO-GO** (blocks production)

**Remediation** (Priority: CRITICAL):
- [ ] Modify cache schema to persist `original_status_code`
  ```python
  # Before: {"body": {...}}
  # After:  {"status_code": 201, "body": {...}}
  ```
- [ ] Return `original_status_code` from cache on replay
- [ ] Verify test `test_idempotent_session_creation` expects correct status
- [ ] Update OpenAPI documentation to clarify replay behavior

**Test Evidence**:
- `tests/test_agents_comprehensive.py::TestIdempotency::test_idempotent_session_creation` PASSES
  - Currently doesn't verify status code of replay (bug in test)
  - Need to add assertion: `assert replay_response.status_code == 201`

---

### Criterion: Mirror that behavior in OpenAPI for /agents/sessions and /agents/sessions/{id}/steps.

**Current State**:
- OpenAPI schema not updated to document replay behavior

**Status**: 🔴 **NO-GO**

**Remediation** (Priority: HIGH):
- [ ] Add to OpenAPI schema for POST /agents/sessions:
  ```yaml
  headers:
    Idempotency-Key:
      description: "Idempotency key for replay detection"
    Idempotency-Replayed:
      description: "true if this is a replayed request (cached)"
  responses:
    201:
      description: "Created"
    200:
      description: "Already exists (replayed, Idempotency-Replayed=true)"
  ```
- [ ] Same for POST /agents/sessions/{id}/steps
- [ ] Document in operations guide

---

## 3. OPENAPI CLEANUP

### Criterion: Mark /admin/models/* paths as deprecated (or hide them).

**Current State**:
```python
# Both exist:
# GET /v1/models          (primary)
# GET /v1/admin/models    (duplicate)
```

**Findings**:
- ❌ `/admin/models/*` endpoints are NOT marked as deprecated
- ❌ OpenAPI doesn't indicate they're legacy/duplicate
- ⚠️ Clients may call either; no indication which to use
- ✅ Functionally equivalent (same implementation)

**Status**: 🟡 **CONDITIONAL GO**

**Remediation** (Priority: MEDIUM):
- [ ] Add `deprecated: true` in FastAPI route decorators:
  ```python
  @router.get("/admin/models", deprecated=True, tags=["Admin Models (Deprecated)"])
  ```
- [ ] Add description: "DEPRECATED: Use GET /v1/models instead"
- [ ] Keep both for backward compatibility but signal clearly
- [ ] Update Swagger UI to show deprecation badge
- [ ] Plan removal date (e.g., v1.0.0)

---

### Criterion: Replace remaining "string" stubs in Agents schemas with real example shapes.

**Current State** (from `src/routers/agents/schemas.py`):
```python
class SessionCreateRequest(BaseModel):
    session_id: str = Field(..., example="string")  # ❌ Bad
    metadata: Optional[Dict] = Field(..., example="string")  # ❌ Bad
```

**Findings**:
- ❌ Multiple fields use placeholder `"string"` examples
- ❌ OpenAPI shows nonsensical examples (e.g., metadata as string)
- ❌ Client developers can't understand expected format from docs

**Example Issues**:
- `session_id` → should be `"sess_123e4567-e89b-12d3-a456-426614174000"`
- `step_id` → should be `"step_456f7890-f90c-23e4-b567-527725285111"`
- `run_id` → should be `"run_789a0123-a01d-34f5-c678-638836396222"`
- `metadata` → should be `{"user_context": "...", "model": "..."}`

**Status**: 🟡 **CONDITIONAL GO**

**Remediation** (Priority: MEDIUM):
- [ ] Update all Agents schema examples with realistic UUIDs and shapes
- [ ] Example fixes:
  ```python
  class SessionCreateRequest(BaseModel):
      session_id: Optional[str] = Field(
          None, 
          example="sess_550e8400-e29b-41d4-a716-446655440000",
          description="Optional UUID; auto-generated if omitted"
      )
      metadata: Optional[Dict] = Field(
          None,
          example={"project_id": "proj_123", "user_id": "user_456"},
          description="Custom context (max 1KB)"
      )
  ```
- [ ] Regenerate OpenAPI JSON and verify Swagger UI looks correct

---

### Criterion: Document all headers consistently: Idempotency-Key, Idempotency-Replayed, X-Request-Id, ETag, If-None-Match, and RateLimit-*.

**Current State**:
- Headers are implemented but not consistently documented
- No centralized header documentation

**Headers Present** ✅:
- `Idempotency-Key` (request) → sets replay cache key
- `Idempotency-Replayed` (response) → signals cache hit
- `X-Request-Id` (response) → correlation ID for logs
- `ETag` (response) → for GET list endpoints
- `If-None-Match` (request) → conditional GET
- `X-RateLimit-Limit` (response) → rate limit quota
- `X-RateLimit-Remaining` (response) → requests left
- `X-RateLimit-Reset` (response) → reset timestamp

**Status**: 🟡 **CONDITIONAL GO**

**Remediation** (Priority: MEDIUM):
- [ ] Create `docs/HEADERS_REFERENCE.md`:
  ```markdown
  ## Request Headers
  | Header | Purpose | Example |
  |--------|---------|---------|
  | Idempotency-Key | Replay detection | "12345678-abcd-..." |
  | If-None-Match | Conditional GET | "W/\"abc123\"" |
  
  ## Response Headers
  | Header | Purpose | Example |
  |--------|---------|---------|
  | Idempotency-Replayed | Cache hit signal | "true" or "false" |
  | X-Request-Id | Correlation ID | "req_550e8400..." |
  | ETag | Entity tag for caching | "W/\"abc123\"" |
  | X-RateLimit-Limit | Rate limit quota | "100" |
  | X-RateLimit-Remaining | Requests left | "87" |
  | X-RateLimit-Reset | Reset timestamp (unix) | "1760959351" |
  ```
- [ ] Add header descriptions to OpenAPI responses (FastAPI `responses={}` parameter)
- [ ] Example for GET /v1/agents/sessions:
  ```python
  @router.get(
      "/sessions",
      responses={
          200: {
              "description": "Session list",
              "headers": {
                  "ETag": {"description": "Entity tag for this list"},
                  "X-RateLimit-Limit": {"description": "Rate limit quota"},
                  "X-RateLimit-Remaining": {"description": "Requests remaining"}
              }
          }
      }
  )
  ```

---

## 4. CACHING / ETAG SANITY

### Criterion: Double-check ETag varies by scope (user/tenant/global) and Vary includes relevant headers.

**Current State** (from `src/middleware/cache_headers.py`):
```python
etag = hashlib.md5(f"{user_id}:{response_body}".encode()).hexdigest()
# Includes user_id in hash ✅
```

**Findings**:
- ✅ ETag includes `user_id` (varies by user)
- ❌ No `Vary` header sent back
- ❌ Proxies don't know to cache separately by Authorization
- ❌ If endpoint has `X-Default-Scope` or `X-Tenant-Id` headers, ETag should vary by those too

**HTTP Caching Best Practice**:
- ETags should vary by: Authorization, user context, tenant context
- `Vary` header must list which request headers affect the response
- Without `Vary`, CDN/proxies may serve wrong ETag to different users

**Status**: 🟡 **CONDITIONAL GO**

**Remediation** (Priority: MEDIUM):
- [ ] Add `Vary` header to all cacheable responses:
  ```python
  response.headers["Vary"] = "Authorization, X-Tenant-Id, X-Default-Scope"
  ```
- [ ] Verify ETag includes all relevant scope components:
  ```python
  # Current:
  etag = md5(f"{user_id}:{body}").hexdigest()
  
  # Should include tenant if multi-tenant:
  etag = md5(f"{user_id}:{tenant_id}:{body}").hexdigest()
  ```
- [ ] Test: same body but different user → different ETag ✅
- [ ] Test: same body but different tenant → different ETag (if applicable)

---

## 5. RBAC PASS

### Criterion: Confirm final intent: user flows require user:me; admin flows admin:all. Re-scan endpoints.

**Current Scopes Available**:
```json
Admin:   ["admin:all", "tools:invoke:all", "user:me"]
User:    ["tools:invoke:basic", "user:me"]
```

**Intent**:
- **User flows** (unprivileged): `/v1/user/me`, `/v1/agents/*` (own data)
- **Admin flows** (privileged): `/v1/admin/*`, `/v1/models/*` (global data)

**Endpoint Audit**:

| Endpoint | Method | Required Scope | Status |
|----------|--------|---|---|
| `/v1/user/me` | GET | `user:me` | ✅ Correct |
| `/v1/agents/sessions` | POST | `user:me` | ✅ Correct |
| `/v1/agents/sessions` | GET | `user:me` | ✅ Correct (filters by user) |
| `/v1/agents/sessions/{id}` | GET | `user:me` | ✅ Correct (owns it or 403) |
| `/v1/agents/sessions/{id}` | DELETE | `user:me` | ✅ Correct (owns it or 403) |
| `/v1/agents/sessions/{id}/steps` | POST | `user:me` | ✅ Correct |
| `/v1/agents/sessions/{id}/steps` | GET | `user:me` | ✅ Correct |
| `/v1/models` | GET | (public or `user:me`) | ✅ Correct |
| `/v1/admin/models` | POST | `admin:all` | ✅ Correct |
| `/v1/admin/models` | DELETE | `admin:all` | ✅ Correct |
| `/v1/health` | GET | (public) | ✅ Correct |
| `/v1/auth/callback` | GET | (public) | ✅ Correct |

**Current Test Coverage**:
- ✅ `test_user_cannot_see_others_sessions` → PASSES
- ✅ `test_safe_tool_invocation_with_basic` → PASSES (basic tools with `tools:invoke:basic`)
- ✅ `test_non_safe_tool_requires_all` → PASSES (invasive tools require `tools:invoke:all`)

**Findings**:
- ✅ Endpoints correctly protected
- ✅ Tests verify RBAC
- ⚠️ No centralized RBAC documentation table
- ⚠️ Admin tools (`invoke:all`) only available to admin; user can invoke basic tools

**Status**: 🟢 **GO**

**Remediation** (Priority: LOW):
- [ ] Add scope table to OpenAPI description and `docs/RBAC_REFERENCE.md`
- [ ] Example:
  ```markdown
  ## Scope Matrix
  
  | Scope | Use | Who |
  |-------|-----|-----|
  | `user:me` | Access own profile & sessions | All users |
  | `admin:all` | Manage platform (models, configs) | Admins |
  | `tools:invoke:basic` | Invoke safe tools (read-only) | All users |
  | `tools:invoke:all` | Invoke all tools (including write) | Admins |
  ```

---

## 6. OBSERVABILITY

### Criterion: Verify X-Request-Id is returned everywhere and propagated to logs/traces.

**Current State**:
```python
# src/middleware/request_id.py
@app.middleware("http")
async def add_request_id(request, call_next):
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response
```

**Findings**:
- ✅ `X-Request-Id` is returned in all responses
- ✅ Middleware runs early (applied to all endpoints)
- ⚠️ No verification that logs include `request_id`
- ⚠️ No trace/span context visible in logs

**Request ID Propagation Checklist**:
- ✅ Returned in response header
- ❓ Included in structured logs (need to verify logs)
- ❓ Propagated to external services (DB, Redis, etc.)
- ❓ Available in error traces

**Status**: 🟡 **CONDITIONAL GO**

**Remediation** (Priority: MEDIUM):
- [ ] Verify logs include `request_id`:
  ```bash
  docker logs app 2>&1 | grep -E "(request_id|X-Request-Id)" | head -5
  ```
- [ ] If not in logs, add to logging context:
  ```python
  import structlog
  logger = structlog.get_logger()
  
  @app.middleware("http")
  async def log_request_id(request, call_next):
      request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
      ctx = contextvars.ContextVar("request_id")
      ctx.set(request_id)
      logger = logger.bind(request_id=request_id)
      ...
  ```
- [ ] Test: make request and grep logs for request_id match

---

### Criterion: Ensure 4xx/5xx return RFC-7807 with instance set to request path and correlation_id in extensions.

**Current State** (from `src/schemas/error.py`):
```python
class RFC7807Error(BaseModel):
    type: str  # e.g., "https://api.example.com/problems/not-found"
    title: str  # e.g., "Not Found"
    status: int  # 404
    detail: str  # "Session not found"
    instance: Optional[str]  # Should be request path ✅
```

**Findings**:
- ✅ RFC-7807 schema defined
- ✅ Errors return `type`, `title`, `status`, `detail`
- ❓ Instance set to request path? (need to verify)
- ⚠️ Correlation ID not in extensions

**Status**: 🟡 **CONDITIONAL GO**

**Remediation** (Priority: MEDIUM):
- [ ] Verify error responses include `instance`:
  ```bash
  curl -s http://localhost:8000/v1/agents/sessions/nonexistent \
    -H "Authorization: Bearer $USER_TOKEN" | jq .
  ```
  Expected:
  ```json
  {
    "type": "https://cineca-agentic-platform.io/problems/resource-not-found",
    "title": "Resource Not Found",
    "status": 404,
    "detail": "Session not found",
    "instance": "/v1/agents/sessions/nonexistent"
  }
  ```
- [ ] Add correlation_id to extensions (RFC-7807 extension):
  ```python
  error_response = {
      "type": "...",
      "title": "...",
      "status": 404,
      "detail": "...",
      "instance": "/v1/agents/sessions/nonexistent",
      "extensions": {
          "correlation_id": request_id,
          "timestamp": datetime.utcnow().isoformat()
      }
  }
  ```
- [ ] Update OpenAPI schema to include extensions
- [ ] Test with audit suite

---

## 7. CI STABILITY

### Criterion: Keep the Redis rate-limit reset strategy per test (prefix/namespace) to avoid future ordering flakiness.

**Current State** (from `tests/conftest.py`):
```python
# Rate limiting reset per test
@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset rate limiting state after each test."""
    redis = get_sync_redis()
    # Flush all rate limit keys
    redis.delete_by_pattern("rate_limit:*")
    yield
    redis.delete_by_pattern("rate_limit:*")
```

**Findings**:
- ✅ Rate limits reset between tests
- ✅ Pattern-based deletion (not FLUSHALL) ✅
- ⚠️ Pattern may be too broad (could affect other tests)
- ⚠️ No per-test namespace isolation for sessions, eTags, locks

**Test Isolation Issues**:
- 🟡 Rate limits: properly reset by pattern
- ❌ Sessions: accumulate across tests (users could see others' sessions if not filtered)
- ❌ ETags: may collide if same user creates multiple sessions
- ❌ Idempotency cache: old keys may still exist

**Status**: 🟡 **CONDITIONAL GO**

**Remediation** (Priority: MEDIUM):
- [ ] Audit if session tests are truly isolated:
  ```bash
  pytest tests/test_agents_comprehensive.py::TestSessionCRUD -v --seed=12345
  pytest tests/test_agents_comprehensive.py::TestSessionCRUD -v --seed=54321
  # Should pass in both orders
  ```
- [ ] Consider per-test Redis namespace:
  ```python
  @pytest.fixture
  def redis_namespace(request):
      ns = f"test_{request.node.nodeid.replace(':', '_')}"
      yield ns
      redis.delete_by_pattern(f"{ns}:*")
  ```
- [ ] Reset these per test:
  - `sessions:*` (session data)
  - `idempotency:*` (replay cache)
  - `etags:*` (ETag cache)
  - `rate_limit:*` (rate limit counters)

---

### Criterion: Lock test order or seed if any suite still shows order sensitivity.

**Current State**:
- Tests run in discovery order (not locked)
- No `--seed` configuration in pytest.ini

**Findings**:
- ⚠️ No locked test order
- ⚠️ Parallel execution (pytest-xdist) may randomize order
- ⚠️ All tests pass individually but may fail when run in sequence

**Status**: 🟡 **CONDITIONAL GO**

**Remediation** (Priority: LOW):
- [ ] Run full suite multiple times:
  ```bash
  for i in {1..5}; do
    echo "Run $i:"
    pytest tests/test_agents_comprehensive.py -x
  done
  ```
- [ ] If any flake appears, add deterministic order:
  ```ini
  # pyproject.toml
  [tool.pytest.ini_options]
  # Lock test order to catch ordering issues
  doctest_optionflags = "NORMALIZE_WHITESPACE ELLIPSIS"
  addopts = "--tb=short -p no:randomly"
  ```
- [ ] Or use pytest-ordering:
  ```bash
  pip install pytest-ordering
  # Decorate tests with @pytest.mark.order(1), @pytest.mark.order(2)
  ```

---

## 8. OPS NOTES

### Criterion: Rotate the demo tokens in docs; remind how to fetch fresh Auth0 tokens.

**Current State**:
- Tokens in docs are hardcoded examples
- Expiration: `exp: 1760959310` (Oct 19, 2025, ~3pm UTC)

**Token Status**:
- 🔴 **EXPIRED or EXPIRING SOON** (Oct 19, 2025 15:31:51 UTC)
- Need to rotate before going to production

**Findings**:
- ❌ Tokens in docs will expire
- ❌ No runbook to fetch fresh tokens
- ⚠️ Docs suggest using hardcoded tokens (bad practice)

**Status**: 🔴 **NO-GO**

**Remediation** (Priority: CRITICAL):
- [ ] Remove hardcoded tokens from docs; replace with:
  ```markdown
  ## Get Auth0 Tokens
  
  ### For Testing Locally
  
  ```bash
  # Admin token (admin:all scope)
  export ADMIN_TOKEN=$(
    curl -s https://cineca.eu.auth0.com/oauth/token \
      -X POST \
      -H "Content-Type: application/json" \
      -d '{
        "client_id": "'$AUTH0_CLIENT_ID'",
        "client_secret": "'$AUTH0_CLIENT_SECRET'",
        "audience": "api://cineca-agentic-platform",
        "grant_type": "client_credentials",
        "scope": "admin:all tools:invoke:all user:me"
      }' | jq -r .access_token
  )
  
  # User token (basic scope)
  export USER_TOKEN=$(
    curl -s https://cineca.eu.auth0.com/oauth/token \
      -X POST \
      -H "Content-Type: application/json" \
      -d '{
        "client_id": "'$AUTH0_CLIENT_ID'",
        "client_secret": "'$AUTH0_CLIENT_SECRET'",
        "audience": "api://cineca-agentic-platform",
        "grant_type": "client_credentials",
        "scope": "tools:invoke:basic user:me"
      }' | jq -r .access_token
  )
  ```
  ```
- [ ] Create `scripts/fetch_auth0_tokens.sh` (executable)
- [ ] Add to `.env.example`:
  ```bash
  AUTH0_DOMAIN=cineca.eu.auth0.com
  AUTH0_CLIENT_ID=<from Auth0 dashboard>
  AUTH0_CLIENT_SECRET=<from Auth0 dashboard>
  ```
- [ ] Document in `docs/LOCAL_SETUP.md`:
  ```bash
  source scripts/fetch_auth0_tokens.sh
  echo "Admin: $ADMIN_TOKEN"
  echo "User: $USER_TOKEN"
  ```

---

### Criterion: Add a one-pager "prod readiness" doc: env vars, health endpoints, smoke curls.

**Current State**:
- No production readiness guide
- Ops need to manually discover requirements

**Status**: 🔴 **NO-GO**

**Remediation** (Priority: CRITICAL):
- [ ] Create `docs/PROD_READINESS.md`:

```markdown
# Production Readiness Checklist

## Environment Variables (Required)

| Variable | Value | Example |
|----------|-------|---------|
| `RATE_LIMIT_MODE` | `prod` | ✅ Must be `prod` |
| `REDIS_URL` | Redis connection | `redis://redis:6379/0` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql://user:pass@postgres/db` |
| `AUTH0_DOMAIN` | Auth0 tenant | `cineca.eu.auth0.com` |
| `CORS_ORIGINS` | Allowed origins | `https://ui.cineca.io` |
| `LOG_LEVEL` | Logging level | `INFO` or `DEBUG` |

## Health Endpoints

### Startup Check (Pre-routing)
```bash
curl http://localhost:8000/health/startup
# Expected: 200 OK with {"status": "ok", "version": "0.1.0", ...}
```

### Liveness Check (Kubernetes)
```bash
curl http://localhost:8000/health/live
# Expected: 200 OK
```

### Readiness Check (Load balancer)
```bash
curl http://localhost:8000/health/ready
# Expected: 200 OK if all dependencies ready
```

## Smoke Tests (Deploy Validation)

### 1. Public Endpoint (Health)
```bash
curl http://api.prod.cineca.io/health
# Expected: 200 OK
```

### 2. Authentication (Valid Token)
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://api.prod.cineca.io/v1/user/me
# Expected: 200 OK with user data
```

### 3. Rate Limiting Active
```bash
# Make 101 requests quickly (limit is 100/min for steps)
for i in {1..101}; do
  curl -s -H "Authorization: Bearer $USER_TOKEN" \
    -H "Idempotency-Key: test-$i" \
    -X POST http://api.prod.cineca.io/v1/agents/sessions/test/steps \
    -d '{"type":"message","input":{}}' | jq .status
done
# Expected: 100x 201 Created, 1x 429 Too Many Requests
```

### 4. Error Handling (RFC-7807)
```bash
curl http://api.prod.cineca.io/v1/agents/sessions/nonexistent \
  -H "Authorization: Bearer $USER_TOKEN"
# Expected: 404 with RFC-7807 error:
# {
#   "type": "...",
#   "title": "Resource Not Found",
#   "status": 404,
#   "instance": "/v1/agents/sessions/nonexistent"
# }
```

## Rollback Procedure

1. Scale deployment to 0
2. Revert DATABASE_URL to previous PostgreSQL backup
3. Scale deployment back to normal
4. Verify health endpoints return 200

## Monitoring

- CPU, Memory, Disk usage
- Redis connection pool saturation
- PostgreSQL query performance (p99 latency)
- Rate limit rejections (429 count)
- Error rate (4xx, 5xx)
- Request latency (p50, p95, p99)

## Incident Response

1. Check logs: `tail -100 logs/app.log | grep -i error`
2. Check dependencies: `curl http://localhost:8000/health/ready`
3. Check rate limits: `redis-cli INFO stats | grep connections`
4. Escalate to on-call engineer if unresolved in 5 min
```

---

## Summary Matrix

| Category | Status | Notes |
|----------|--------|-------|
| **Rate Limits** | 🟡 CONDITIONAL | Prod defaults correct; need k8s manifests verified |
| **Idempotency** | 🔴 **NO-GO** | Status codes on replays incorrect; cache schema needs fix |
| **OpenAPI** | 🟡 CONDITIONAL | Deprecation tags & examples need polish |
| **RBAC** | 🟢 GO | Endpoints correctly protected; tests pass |
| **Caching/ETag** | 🟡 CONDITIONAL | ETag correct; need `Vary` header & verification |
| **Observability** | 🟡 CONDITIONAL | X-Request-Id present; logs need audit |
| **CI Stability** | 🟡 CONDITIONAL | Rate limits reset; other resources may not be |
| **Ops Readiness** | 🔴 **NO-GO** | No prod runbook; tokens expiring |

---

## Critical Blockers (Must Fix Before Production)

1. **Idempotency Status Codes** - Return original status on replay, not hardcoded 200
2. **Rate Limit Diagnostics** - Expose mode & limits in `/health/startup`
3. **Ops Runbook** - Production readiness checklist with health checks
4. **Token Rotation** - Remove hardcoded tokens; add Auth0 script

---

## Recommended Priority Order

### Phase 1 (This Week - Blocking)
- [ ] Fix idempotency replay status codes
- [ ] Add rate limit & mode to health endpoint
- [ ] Create ops runbook

### Phase 2 (Next Week - High)
- [ ] Add RFC-7807 correlation_id to errors
- [ ] Update OpenAPI with header documentation
- [ ] Create RBAC reference table

### Phase 3 (Follow-up - Medium)
- [ ] Polish Agents examples in OpenAPI
- [ ] Mark /admin/* as deprecated
- [ ] Add Vary headers to cache responses
- [ ] Lock test execution order if flaky

---

**Generated**: October 19, 2025  
**Next Review**: After Phase 1 remediations
