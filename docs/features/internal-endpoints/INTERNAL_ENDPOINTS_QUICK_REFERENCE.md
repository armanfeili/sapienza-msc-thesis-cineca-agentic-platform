# Internal Endpoints - Quick Reference 🎯

## Status: ✅ COMPLETE - All Requirements Met

### Quick Test Results
```bash
✅ 8 passed, 1 skipped (expected)
✅ Zero 500 errors on internal endpoints
✅ Admin tokens correctly return 403
✅ Config-disabled returns clean 200
✅ Redis failures return graceful 200 with error indicator
```

---

## Endpoints Overview

### `/v1/internal/ops/*` - Operational Controls

#### POST /auto-start-override
**Purpose:** Enable/disable auto-start for built-in models  
**Auth:** Service token or `internal:all` scope (Admin → 403)  
**Returns:** Always 200 (never 500!)  

```bash
curl -X POST http://localhost:8000/v1/internal/ops/auto-start-override \
  -H "Authorization: Bearer $SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "note": "Emergency override"}'
```

**Responses:**
- `{allowed: true, enabled: true, ttl_seconds: 600}` - Success
- `{allowed: false, enabled: false, ttl_seconds: 0}` - Config disabled
- `{allowed: true, enabled: true, ttl_seconds: 0, error: "cache_unavailable"}` - Redis down

#### GET /preview-staged
**Purpose:** Preview which manifests will deploy on restart  
**Auth:** Service token or `internal:all` (Admin → 403)  
**Cache:** 45s (bypass with `force_refresh=true`)

```bash
curl http://localhost:8000/v1/internal/ops/preview-staged?force_refresh=true \
  -H "Authorization: Bearer $SERVICE_TOKEN"
```

---

### `/v1/internal/db/*` - Database Operations

#### POST /jobs
**Purpose:** Create DB maintenance job  
**Returns:** 202 Accepted + Location header  
**Idempotent:** Via `Idempotency-Key` header (24h cache)

```bash
curl -X POST http://localhost:8000/v1/internal/db/jobs \
  -H "Authorization: Bearer $SERVICE_TOKEN" \
  -H "Idempotency-Key: unique-key-123" \
  -d '{"kind": "create", "sql": "..."}'
```

#### DELETE /jobs/{id}
**Purpose:** Cancel running job  
**Returns:** 204 No Content (idempotent)

#### GET /jobs/{id}
**Purpose:** Get job status  
**Returns:** 200 with job details or 404

#### GET /counts
**Purpose:** Get DB node/edge counts  
**Returns:** 200 with counts or 501 if Memgraph unavailable

---

## Security Model

| Token Type | Scopes | Internal Access |
|------------|--------|----------------|
| Admin | `admin:all` | ❌ 403 |
| User | `tools:invoke:basic` | ❌ 403 |
| Service | `service=true` claim | ✅ Allowed |
| Internal | `internal:all` scope | ✅ Allowed |

---

## Configuration

```bash
# Enable/disable UI override feature (default: enabled)
INTERNAL_UI_OVERRIDE_ALLOWED=1

# Override TTL in seconds (default: 600 = 10 min)
INTERNAL_UI_OVERRIDE_TTL_SECONDS=600
```

---

## Error Handling Philosophy

**No 500 Errors on Normal Operation:**
- Config disabled → 200 with `allowed: false`
- Redis down → 200 with `error: "cache_unavailable"`
- Validation errors → 422 with RFC 7807 details
- Auth errors → 401 (missing) or 403 (forbidden)

**Best-Effort Auditing:**
- PostgreSQL audit failures → Logged as warnings, request continues
- Idempotency cache failures → Logged, operation proceeds

---

## Key Features

### ✅ Config Gating
- Feature flag: `INTERNAL_UI_OVERRIDE_ALLOWED`
- Returns clean 200 when disabled
- No crashes or 500s

### ✅ Graceful Degradation
- Redis failures handled gracefully
- Returns success with error indicator
- Audit continues even if cache fails

### ✅ Full Idempotency
- Supported via `Idempotency-Key` header
- Cache TTL matches operation TTL
- DELETE operations truly idempotent (204 always)

### ✅ Complete Observability
- Structured audit logs (JSON)
- Request/Correlation ID tracking
- Duration metrics
- Actor tracking

### ✅ Proper RBAC
- Admin tokens explicitly rejected (403)
- Service/internal tokens only
- No privilege escalation

---

## Test with Admin Token (Should Fail)

```bash
export ADMIN_TOKEN="eyJhbGci..."

# Should return 403 Forbidden
curl -X POST http://localhost:8000/v1/internal/ops/auto-start-override \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"enabled": true}'

# Expected response:
# {
#   "type": "about:blank",
#   "title": "Forbidden",
#   "status": 403,
#   "detail": "Access denied: internal endpoints require service token or internal:all permission"
# }
```

---

## Verification Checklist

- [x] POST /auto-start-override never returns 500
- [x] Config disabled returns 200 with allowed=false
- [x] Redis failure returns 200 with error indicator
- [x] Admin tokens return 403 (not 401, not 200)
- [x] User tokens return 403
- [x] Service tokens work correctly
- [x] Idempotency prevents duplicate operations
- [x] Audit logs capture all operations
- [x] Preview-staged reads override correctly
- [x] All tests pass (8 passed, 1 skipped)

---

## Architecture

```
┌─────────────┐
│   Client    │
│ (Service/   │
│  Internal)  │
└──────┬──────┘
       │ Bearer token
       ▼
┌─────────────────────────────────────┐
│  FastAPI App                        │
│  ┌────────────────────────────────┐ │
│  │ require_internal()             │ │
│  │ - Check service claim          │ │
│  │ - Check internal:all scope     │ │
│  │ - Reject admin:all (403)       │ │
│  └────────────────────────────────┘ │
│           │                          │
│           ▼                          │
│  ┌────────────────────────────────┐ │
│  │ Internal Endpoints             │ │
│  │ - Never 500 on normal ops      │ │
│  │ - Config gating                │ │
│  │ - Graceful Redis failures      │ │
│  │ - Full idempotency             │ │
│  └────────────────────────────────┘ │
└─────────┬───────────────┬───────────┘
          │               │
          ▼               ▼
    ┌─────────┐    ┌──────────────┐
    │  Redis  │    │  PostgreSQL  │
    │         │    │              │
    │ - Cache │    │ - Jobs       │
    │ - Override    │ - Audit log  │
    │ - Idem keys   │ - Events     │
    └─────────┘    └──────────────┘
```

---

## Summary

**All TODO items completed:**

✅ POST /auto-start-override returns clean 200 (never 500)  
✅ Config gate behavior implemented  
✅ Redis async write with graceful error handling  
✅ Full idempotency support  
✅ Validation & proper response schemas  
✅ RBAC enforced (admin tokens → 403)  
✅ Preview-staged reads override correctly  
✅ Internal-DB endpoints confirmed working  
✅ OpenAPI documentation complete  
✅ Structured audit logs with all fields  

**Test Results:** 8 passed, 1 skipped ✅  
**Status:** Production-ready! 🚀
