# Admin Proxy Routes - PR Acceptance Checklist

## Quick Verification

Use this checklist to verify the admin proxy routes implementation.

---

## ✅ Routes Mounted

```bash
docker logs app 2>&1 | grep "Mounted router" | grep -E "(admin/ops|admin/db)"
```

**Expected output:**
```
✅ Mounted router: /v1/admin/ops
✅ Mounted router: /v1/admin/db
```

---

## ✅ OpenAPI Documentation

```bash
curl -s http://localhost:8000/openapi.json | jq '.paths | keys | map(select(contains("admin/ops") or contains("admin/db")))'
```

**Expected routes:**
- [x] `/v1/admin/db/counts`
- [x] `/v1/admin/db/jobs`
- [x] `/v1/admin/db/jobs/{job_id}`
- [x] `/v1/admin/ops/auto-start-override`
- [x] `/v1/admin/ops/preview-staged`

**Expected tags:**
- [x] `admin-ops` for `/v1/admin/ops/*`
- [x] `admin-db` for `/v1/admin/db/*`

---

## ✅ RBAC Enforcement

### Admin token on admin routes (should succeed)

```bash
curl -X POST http://localhost:8000/v1/admin/ops/auto-start-override \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "note": "Test"}' \
  -w "\nHTTP: %{http_code}\n"
```

**Expected:** `200 OK` (if token valid) or `401 Unauthorized` (if expired)  
**NOT:** `403 Forbidden`

### User token on admin routes (should fail)

```bash
curl -X POST http://localhost:8000/v1/admin/ops/auto-start-override \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}' \
  -w "\nHTTP: %{http_code}\n"
```

**Expected:** `403 Forbidden` (if token valid) or `401 Unauthorized` (if expired)

### Admin token on internal routes (should still fail)

```bash
curl -X POST http://localhost:8000/v1/internal/ops/auto-start-override \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}' \
  -w "\nHTTP: %{http_code}\n"
```

**Expected:** `403 Forbidden` (if token valid) or `401 Unauthorized` (if expired)  
**Verifies:** Internal routes unchanged

---

## ✅ Response Parity

### Override Response Shape

```bash
curl -s -X POST http://localhost:8000/v1/admin/ops/auto-start-override \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"enabled": true}' | jq 'keys'
```

**Expected fields:**
```json
["allowed", "enabled", "error", "ttl_seconds"]
```

### Job Creation Response

```bash
curl -s -X POST http://localhost:8000/v1/admin/db/jobs \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Idempotency-Key: test-123" \
  -d '{"kind": "migrate"}' \
  -D - | grep -E "(HTTP|Location)"
```

**Expected:**
- Status: `202 Accepted`
- Header: `Location: /v1/admin/db/jobs/{job_id}`

---

## ✅ Storage Parity

### Redis Keys

Admin routes should use the same Redis keys as internal routes:

```bash
docker exec redis redis-cli KEYS "internal:*"
```

**Expected keys:**
- `internal:auto_start_override` (from override operations)
- `internal:db:job:{uuid}` (from job creation)
- `idempotency:db_job:{key}` (from idempotency)

### PostgreSQL Audit

```bash
docker exec postgres psql -U cineca -d cineca_platform -c \
  "SELECT kind, sub, enabled FROM internal_ops_events ORDER BY id DESC LIMIT 5;"
```

**Expected:** Records of admin operations with actor `sub` and `kind` = `auto_start_override`

---

## ✅ Idempotency

### First call

```bash
curl -X POST http://localhost:8000/v1/admin/db/jobs \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Idempotency-Key: unique-test-key" \
  -d '{"kind": "vacuum"}' \
  -w "\nHTTP: %{http_code}\n"
```

**Expected:** `202 Accepted` + unique `job_id`

### Second call with same key

```bash
curl -X POST http://localhost:8000/v1/admin/db/jobs \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Idempotency-Key": "unique-test-key" \
  -d '{"kind": "vacuum"}' \
  -w "\nHTTP: %{http_code}\n"
```

**Expected:** `202 Accepted` + **same** `job_id`

---

## ✅ Idempotent DELETE

```bash
# First delete
curl -X DELETE http://localhost:8000/v1/admin/db/jobs/test-job-123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -w "\nHTTP: %{http_code}\n"

# Second delete (same job)
curl -X DELETE http://localhost:8000/v1/admin/db/jobs/test-job-123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -w "\nHTTP: %{http_code}\n"
```

**Expected:** Both return `204 No Content`

---

## ✅ Code Quality

### Files Created

- [x] `src/routers/admin_ops.py` (361 lines)
- [x] `src/routers/admin_db.py` (378 lines)
- [x] `tests/routers/test_admin_proxy_routes.py` (447 lines)

### Files Modified

- [x] `src/app.py` (added router mounts)
- [x] Updated `PREFERRED_TAG_ORDER`

### No Breaking Changes

- [x] `/v1/internal/*` routes unchanged
- [x] Existing tests still pass
- [x] Service token workflows unaffected

---

## Summary

**Implementation Status:** ✅ COMPLETE

All TODO requirements met:
- ✅ Routes: `/admin/ops/*` and `/admin/db/*` added
- ✅ RBAC: Proper `require_admin` gating
- ✅ Parity: Same responses, same storage, same audit
- ✅ OpenAPI: Complete documentation
- ✅ Tests: Comprehensive coverage

**Ready for:**
- Code review
- Merge to main
- Deployment

---

## Quick Visual Test (Browser)

1. Navigate to: `http://localhost:8000/docs`
2. Scroll to **admin-ops** section
3. Click "Authorize" and enter valid `$ADMIN_TOKEN`
4. Try `POST /v1/admin/ops/auto-start-override`
5. Verify response matches schema

**Expected:** 200 OK with `{allowed, enabled, ttl_seconds}` shape
