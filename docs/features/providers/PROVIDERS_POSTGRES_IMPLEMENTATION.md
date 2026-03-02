# Models-Providers Implementation Summary

## Completed: PostgreSQL Foundation (Steps 1-3)

### ✅ 1. PostgreSQL Schema (Models)

Created `/db/postgres_control/models/provider.py` with 4 tables:

#### `providers` (Main Registry - Authoritative)
- **Columns**: `id`, `name`, `type`, `base_url`, `model`, `tenant_id`, `config_json`, `has_api_key`, `created_at`, `updated_at`
- **Indexes**: `(tenant_id, name)` unique, `tenant_id`, `type`, `created_at`
- **Purpose**: Stores all provider metadata; `config_json` accepts arbitrary provider-specific keys

#### `provider_secrets` (Encrypted Secrets - Never Exposed)
- **Columns**: `provider_id` (FK to providers), `api_key_encrypted`, `created_at`, `updated_at`
- **Purpose**: Stores encrypted API keys separately; **NEVER** returned in API responses
- **Encryption**: Uses Fernet symmetric encryption (key from `settings.PROVIDER_SECRET_KEY`)

#### `provider_defaults` (Scope Resolution)
- **Columns**: `scope`, `tenant_id`, `provider_id` (FK), `created_at`, `updated_at`
- **Unique**: `(scope, tenant_id)` - one default per scope per tenant
- **Purpose**: Stores default provider selections with precedence: tenant > global

#### `provider_audit_events` (Append-Only Audit Trail)
- **Columns**: `id` (auto-increment), `provider_id`, `actor`, `action`, `tenant_id`, `payload` (JSON), `trace_id`, `event_id`, `created_at`
- **Indexes**: `provider_id`, `actor`, `action`, `created_at`, `tenant_id`
- **Purpose**: Immutable log of all provider mutations (register, patch, delete, set_default)

### ✅ 2. Alembic Migration

Created `/db/postgres_control/alembic/versions/004_create_providers_tables.py`:
- **Revision**: 004 (follows 003_create_jobs_tables)
- **Features**: All 4 tables with proper indexes, constraints, CASCADE deletes
- **Reversible**: Includes `downgrade()` to drop tables cleanly

### ✅ 3. PostgreSQL Repository Layer

Created `/db/postgres_control/repositories/provider_repo.py` with:

#### CRUD Operations (PostgreSQL Authoritative)
- `create_provider()` - Insert provider + encrypted secret + audit event
- `list_providers()` - Query with tenant filtering, redacted output
- `get_provider()` - Fetch by ID, optional `include_secrets=True` for internal use
- `patch_provider()` - Deep-merge config, update secret, audit event
- `delete_provider()` - CASCADE delete secrets, auto-clear defaults, audit event

#### Defaults Management
- `set_provider_default()` - Upsert default for scope/tenant
- `get_provider_default()` - Resolution precedence: tenant → global → None

#### Secret Handling
- `_encrypt_secret()` / `_decrypt_secret()` - Fernet encryption/decryption
- `_redact_secrets()` - Masks `api_key`, `config.headers.authorization`, `config.auth.token`
- **Policy**: API responses use `has_api_key` boolean; raw key NEVER exposed

#### Redis Caching (Short TTL, Invalidate on Write)
- **Keys**:
  - `providers:by_id:{id}` - Single provider (TTL: 5 min)
  - `providers:list:{filters}` - List pages (TTL: 1 min)
  - `providers:default:{scope}:{tenant}` - Default resolution (TTL: 10 min)
  - `providers:health:{id}` - Health snapshot (TTL: 2 min)
  - `providers:etag:{id}`, `providers:etag:list:{hash}` - ETags (TTL: 5 min)
- **Invalidation**: `_redis_invalidate_provider()` clears all related keys on write

#### ETag Support
- `compute_provider_etag()` - Deterministic SHA256 hash of redacted provider + `updated_at`
- `compute_list_etag()` - Hash of entire paginated result set

#### Audit Logging
- `_audit_event()` - Append-only writes to `provider_audit_events` with:
  - `before`/`after` snapshots for PATCH
  - `trace_id`/`event_id` for correlation
  - All mutations logged (register, patch, delete, set_default)

---

## Remaining Work (Steps 4-9)

### 🔄 4. Update Router Endpoints (`src/routers/model_management.py`)

**Current State**: Endpoints use `src/repositories/models_repo.py` (Redis-only in-memory)

**Required Changes**:
1. Replace `import src.repositories.models_repo` with `import db.postgres_control.repositories.provider_repo as pg_repo`
2. Update ALL endpoints to call `pg_repo.*` instead of `models_repo.*`
3. Add ETag headers to responses:
   ```python
   etag = pg_repo.compute_provider_etag(provider_id)
   response.headers["ETag"] = etag
   if request.headers.get("if-none-match") == etag:
       return Response(status_code=304)
   ```
4. Add `Link` header for pagination (RFC 5988)
5. Ensure all responses include `X-Request-Id`, `X-Event-Id` (from audit events)

#### Endpoints to Update:
- `GET /providers` → `pg_repo.list_providers()`, add ETag, Link headers
- `POST /providers/register` → `pg_repo.create_provider()`, idempotency check (409 on conflict)
- `GET /providers/main` → `pg_repo.get_provider_default()`, ETag support, 404 when no default
- `GET /providers/{id}` → `pg_repo.get_provider()`, ETag, health snapshot
- `PATCH /providers/{id}` → `pg_repo.patch_provider()`, merge config, invalidate caches
- `DELETE /providers/{id}` → `pg_repo.delete_provider()`, auto-clear defaults, 204 + headers
- `PUT /providers/default` → `pg_repo.set_provider_default()`, scope resolution

### 🔄 5. Health Check Integration

**Current State**: Health checks in Redis via `models_repo.refresh_provider_health()`

**Required**:
1. Keep health checks in **Redis only** (volatile, non-authoritative)
2. After provider registration, run initial health check:
   ```python
   health = await _check_provider_health(provider_id, base_url)
   pg_repo.set_provider_health(provider_id, health)
   ```
3. Optional: Background worker to periodically refresh health snapshots
4. Attach health to provider responses:
   ```python
   provider = pg_repo.get_provider(provider_id)
   provider["health"] = pg_repo.get_provider_health(provider_id)
   ```

### 🔄 6. Caching & Invalidation Verification

**Redis Keys Structure** (already implemented in `provider_repo.py`):
```
providers:by_id:{id}          → Single provider JSON (TTL: 5 min)
providers:list:{filters}       → Paginated list (TTL: 1 min)
providers:default:{scope}:{tenant} → Default resolution (TTL: 10 min)
providers:health:{id}          → Health snapshot (TTL: 2 min)
providers:etag:{id}            → ETag for single provider (TTL: 5 min)
providers:etag:list:{hash}     → ETag for list query (TTL: 5 min)
```

**Invalidation Triggers** (already implemented):
- `create_provider()` → Invalidate list caches, ETags
- `patch_provider()` → Invalidate by_id, list, ETags, health
- `delete_provider()` → Invalidate all related keys
- `set_provider_default()` → Invalidate default keys (tenant + global)

**Verification**: Add logging to confirm cache hits/misses in router endpoints.

### 🔄 7. Run Alembic Migration

**Steps**:
1. Ensure PostgreSQL container is running: `docker compose up -d postgres`
2. Run migration: `alembic upgrade head` (or `make migrate` if Makefile exists)
3. Verify tables exist: `psql -c "\dt providers*"`
4. Seed test data (optional):
   ```sql
   INSERT INTO providers (id, name, type, base_url, model, tenant_id, config_json, has_api_key)
   VALUES ('test-openai', 'Test OpenAI', 'openai_compatible', 'https://api.openai.com/v1', 'gpt-4', NULL, '{}', true);
   ```

### 🔄 8. Smoke Tests (`tests/providers/test_providers_smoke.py`)

Create minimal smoke tests per TODO spec:

#### Test 1: `GET /providers` (List)
```python
def test_list_providers_smoke(admin_client):
    # Register a provider
    resp = admin_client.post("/v1/admin/models/providers/register", json={...})
    assert resp.status_code == 200
    
    # List providers
    resp = admin_client.get("/v1/admin/models/providers")
    assert resp.status_code == 200
    assert "ETag" in resp.headers
    assert "Cache-Control" in resp.headers
    
    items = resp.json()["items"]
    assert len(items) > 0
    assert items[0]["has_api_key"] == True
    assert "api_key" not in items[0] or items[0]["api_key"] is None
    
    # Test If-None-Match (304)
    etag = resp.headers["ETag"]
    resp = admin_client.get("/v1/admin/models/providers", headers={"If-None-Match": etag})
    assert resp.status_code == 304
```

#### Test 2: `POST /providers/register` (Idempotency)
```python
def test_register_provider_idempotency(admin_client):
    payload = {...}
    
    # First registration
    resp1 = admin_client.post("/v1/admin/models/providers/register", json=payload)
    assert resp1.status_code == 200
    
    # Repeat same payload (idempotent)
    resp2 = admin_client.post("/v1/admin/models/providers/register", json=payload)
    assert resp2.status_code == 200  # or 201 if you prefer
    assert resp2.json()["ok"] == True
    
    # Different config (conflict)
    payload["base_url"] = "https://different.url"
    resp3 = admin_client.post("/v1/admin/models/providers/register", json=payload)
    assert resp3.status_code == 409
    assert "X-Conflict-Details" in resp3.headers
```

#### Test 3-9: Similar patterns for GET /main, GET /{id}, PATCH, DELETE, PUT /default

### 🔄 9. Documentation Updates

Update docs to reflect PostgreSQL-backed providers:

#### `/docs/providers-api.md` (new file):
```markdown
# Providers API (PostgreSQL-Backed)

## Storage Architecture

- **PostgreSQL**: Authoritative source (providers, secrets, defaults, audit events)
- **Redis**: Cache layer (TTL: 1-10 min, invalidated on writes)
- **Secret Policy**: API keys encrypted at rest (Fernet), NEVER exposed in responses

## Endpoints

### GET /v1/admin/models/providers
- **Caching**: ETag + If-None-Match → 304
- **Pagination**: Link header (RFC 5988)
- **Redaction**: `has_api_key` boolean, secrets masked

### POST /v1/admin/models/providers/register
- **Idempotency**: Same config → 200 (no-op), different config → 409
- **Audit**: Logged to `provider_audit_events`

(... continue for all endpoints)
```

---

## File Summary

### Created Files
1. `/db/postgres_control/models/provider.py` - SQLAlchemy models (4 tables)
2. `/db/postgres_control/alembic/versions/004_create_providers_tables.py` - Migration
3. `/db/postgres_control/repositories/provider_repo.py` - PostgreSQL repository
4. `/docs/PROVIDERS_POSTGRES_IMPLEMENTATION.md` - This file

### Modified Files
1. `/db/postgres_control/models/__init__.py` - Added provider models to exports

### Files Requiring Updates (Next Steps)
1. `/src/routers/model_management.py` - Replace models_repo with pg_repo
2. `/tests/providers/test_providers_smoke.py` - Add smoke tests (new file)
3. `/docs/providers-api.md` - Document PostgreSQL-backed architecture (new file)

---

## Quick Start (Post-Migration)

```bash
# 1. Run migration
docker compose up -d postgres
alembic upgrade head

# 2. Verify tables
docker compose exec postgres psql -U postgres -d cineca -c "\dt providers*"

# 3. Update router to use pg_repo (manual step)
# Edit src/routers/model_management.py

# 4. Restart app
docker compose restart api

# 5. Run smoke tests
pytest tests/providers/test_providers_smoke.py -v
```

---

## Migration Checklist (Final)

- [x] PostgreSQL models (`Provider`, `ProviderSecret`, `ProviderDefault`, `ProviderAuditEvent`)
- [x] Alembic migration (004_create_providers_tables)
- [x] PostgreSQL repository with CRUD, secrets, audit, caching, ETags
- [ ] Update router endpoints to use `pg_repo` instead of `models_repo`
- [ ] Run Alembic migration (`alembic upgrade head`)
- [ ] Add health check integration (optional background worker)
- [ ] Write smoke tests (8 endpoint scenarios from TODO)
- [ ] Documentation (providers-api.md, architecture diagrams)
- [ ] Verify caching/invalidation with request logging
- [ ] Load testing (optional: verify PostgreSQL + Redis performance)

---

## Notes on Design Decisions

### 1. **Encryption Key Management**
- Current: Uses `settings.PROVIDER_SECRET_KEY` or generates ephemeral key (DEV ONLY)
- Production: Should use AWS Secrets Manager, HashiCorp Vault, or similar
- TODO: Add key rotation support

### 2. **Secret Redaction**
- `has_api_key` boolean provided to indicate key presence
- Redaction at repository layer (not endpoint layer) for consistency
- `include_secrets=True` parameter for internal use (orchestrator routing) - NEVER exposed via API

### 3. **Audit Events**
- Append-only (no updates/deletes)
- Includes `before`/`after` snapshots for PATCH operations
- Correlation via `trace_id` + `event_id` from provenance system

### 4. **Default Resolution Precedence**
- Explicit precedence: tenant-scoped > global > 404
- Cached in Redis with separate keys per scope/tenant
- Auto-clear on provider deletion (policy decision: prevent dangling refs)

### 5. **Config Flexibility**
- `config_json` uses `extra="allow"` semantics (arbitrary provider-specific keys)
- Deep merge on PATCH (not full replacement)
- Redaction rules still apply to nested secrets (headers.authorization, auth.token)

### 6. **Health Snapshots**
- Redis-only (volatile, non-authoritative)
- Short TTL (2 min) to encourage fresh checks
- Optional: Add `provider_health_history` table for long-term analytics (not in v1 scope)

### 7. **Multi-Tenant Visibility**
- Admin sees ALL providers (global + tenant-scoped)
- Future user endpoint would filter: global + user's tenant only
- Enforced at query level (`OR tenant_id IS NULL OR tenant_id = ?`)
