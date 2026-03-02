# Migration Guide: v1 to v2 API Changes

## Overview

This guide documents breaking changes introduced in v2 of the Cineca Agentic Platform API that affect client SDKs and integrations.

## Breaking Changes

### 1. Provider Management API Updates (BREAKING)

#### 1.1 LIST `/v1/admin/models/providers` Response Structure

**Change**: The response is now a paginated object instead of a bare array.

**Before**:
```json
[
  {
    "id": "provider-1",
    "name": "OpenAI",
    "type": "openai_compatible",
    "api_key": "sk-..."
  }
]
```

**After**:
```json
{
  "items": [
    {
      "id": "provider-1",
      "name": "OpenAI",
      "type": "openai_compatible",
      "has_api_key": true,
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:30:00Z"
    }
  ],
  "next_page_token": "eyJ...",
  "total": 1
}
```

**Migration**:
```typescript
// Before
const providers: Provider[] = await client.get('/v1/admin/models/providers');

// After
const response: ProviderListResponse = await client.get('/v1/admin/models/providers');
const providers = response.items;
// Handle pagination if needed
if (response.next_page_token) {
  const nextPage = await client.get('/v1/admin/models/providers', {
    params: { page_token: response.next_page_token }
  });
}
```

#### 1.2 DELETE `/v1/admin/models/providers/{id}` Returns 204 No Content

**Change**: DELETE now returns `204 No Content` instead of `200 OK` with a response body.

**Before**:
```http
DELETE /v1/admin/models/providers/provider-1
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "message": "Provider deleted successfully"
}
```

**After**:
```http
DELETE /v1/admin/models/providers/provider-1
HTTP/1.1 204 No Content
X-Request-Id: abc-123
X-Event-Id: evt-456
X-Trace-Id: trace-789
```

**Migration**:
```typescript
// Before
const result = await client.delete(`/v1/admin/models/providers/${id}`);
console.log(result.message); // ❌ No longer available

// After
await client.delete(`/v1/admin/models/providers/${id}`);
// Success indicated by 204 status, no response body
// Trace IDs available in response headers
```

#### 1.3 Secret Redaction with `has_api_key` Indicator

**Change**: API keys and secrets are never returned. A `has_api_key` boolean indicates presence.

**Before**:
```json
{
  "id": "provider-1",
  "api_key": "sk-proj-abc123...",
  "config": {
    "headers": {
      "Authorization": "Bearer secret-token"
    }
  }
}
```

**After**:
```json
{
  "id": "provider-1",
  "has_api_key": true,
  "config": {
    "headers": {
      "Authorization": "***"
    }
  }
}
```

**Migration**:
```typescript
// Before
if (provider.api_key) {
  console.log('Has API key:', provider.api_key); // ❌ Security risk
}

// After
if (provider.has_api_key) {
  console.log('Provider has API key configured');
  // Actual key never exposed in API responses
}
```

#### 1.4 Problem+JSON Error Titles Match HTTP Status

**Change**: RFC 7807 Problem Details `title` field now correctly matches the HTTP status code.

**Before**:
```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 403,
  "detail": "Insufficient permissions"
}
```

**After**:
```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Insufficient permissions"
}
```

**Status Code Mappings**:
- `400` → "Bad Request"
- `401` → "Unauthorized"
- `403` → "Forbidden"
- `404` → "Not Found"
- `409` → "Conflict"
- `422` → "Validation Error"
- `429` → "Too Many Requests"
- `500` → "Internal Server Error"

#### 1.5 Pagination Headers (RFC 5988 Link Header)

**New**: Paginated responses now include `Link` headers for navigation.

```http
GET /v1/admin/models/providers?page_size=10
HTTP/1.1 200 OK
Link: </v1/admin/models/providers?page_token=eyJ...&page_size=10>; rel="next"
ETag: "abc123"
X-Request-Id: req-456

{
  "items": [...],
  "next_page_token": "eyJ..."
}
```

**Migration**:
```typescript
// Clients can use Link header for automatic pagination
const linkHeader = response.headers.get('Link');
if (linkHeader) {
  const nextUrl = parseLinkHeader(linkHeader).next;
  // Fetch next page using provided URL
}
```

---

### 2. POST `/v1/jobs` Response Schema (BREAKING)

**Change**: The `POST /v1/jobs` response now includes an `owner` field identifying the job creator.

**Before (v1)**:
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "queued"
}
```

**After (v2)**:
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "queued",
  "owner": "user@example.com"
}
```

**Impact**:
- **JSON parsers**: May fail if strict schema validation is enabled
- **SDKs**: Typescript/OpenAPI-generated clients will show type errors
- **Contract tests**: Need to update assertions to include `owner` field

**Migration**:
```typescript
// Before (v1)
interface JobCreateResponse {
  id: string;
  status: string;
}

// After (v2)
interface JobCreateResponse {
  id: string;
  status: string;
  owner: string;  // NEW: token subject who created the job
}
```

### 2. User Permissions Model (BREAKING BEHAVIOR)

**Change**: Regular users can now create, view, and cancel **their own jobs**. Previously, job operations were admin-only.

**New Permission Model**:
```
┌─────────────────┬──────────────┬─────────────────────────────┐
│ Operation       │ User Role    │ Access Control              │
├─────────────────┼──────────────┼─────────────────────────────┤
│ POST /v1/jobs   │ Any user     │ Creates job (owner = self)  │
│ GET /v1/jobs    │ Any user     │ Lists own jobs only         │
│ GET /v1/jobs/:id│ Owner        │ View own job                │
│                 │ admin:all    │ View any job                │
│ DELETE /v1/jobs │ Owner        │ Cancel own job              │
│                 │ admin:all    │ Cancel any job              │
│ SSE /events     │ Owner        │ Stream own job events       │
│                 │ admin:all    │ Stream any job events       │
└─────────────────┴──────────────┴─────────────────────────────┘
```

**Impact**:
- **User-facing apps**: Can now call job APIs directly (no admin proxy needed)
- **Admin tools**: Continue to work (admin:all permission preserved)
- **Authorization logic**: Must handle owner-based access, not just role checks

**Migration**:
```python
# Before (v1): Only admins could create jobs
if not has_role(user, "admin:all"):
    raise Forbidden("Job creation requires admin permission")

# After (v2): Any authenticated user can create jobs
# Owner is automatically set to token.sub
job = create_job(user, payload)
```

### 3. Anti-Enumeration: 404 vs 403 (BREAKING BEHAVIOR)

**Change**: Non-owners without `admin:all` permission now receive **404 Not Found** instead of **403 Forbidden** when accessing another user's job.

**Before (v1)**:
```bash
# User A tries to access User B's job
GET /v1/jobs/user-b-job-id
→ 403 Forbidden
```

**After (v2)**:
```bash
# User A tries to access User B's job
GET /v1/jobs/user-b-job-id
→ 404 Not Found
```

**Rationale**:
- **Security**: Prevents job ID enumeration attacks
- **Privacy**: User A cannot distinguish "job exists but forbidden" from "job doesn't exist"
- **Standard**: Follows OWASP anti-enumeration best practices

**Impact**:
- **Error handling**: 404 no longer means "job doesn't exist" exclusively
- **Logging**: Must differentiate "genuine 404" from "anti-enumeration 404"
- **UX**: Error messages should say "Job not found or access denied"

**Migration**:
```typescript
// Before (v1): Explicit forbidden handling
try {
  const job = await client.getJob(jobId);
} catch (err) {
  if (err.status === 403) {
    showError("You don't have permission to view this job");
  } else if (err.status === 404) {
    showError("Job not found");
  }
}

// After (v2): Unified 404 handling
try {
  const job = await client.getJob(jobId);
} catch (err) {
  if (err.status === 404) {
    // Could be "not found" OR "access denied"
    showError("Job not found or access denied");
  }
}
```

### 4. Idempotency Key Behavior (CLARIFICATION)

**Change**: Idempotency key computation now **includes payload hash**, providing defensive deduplication even without explicit `Idempotency-Key` header.

**Before (v1)**:
- Required explicit `Idempotency-Key` header for deduplication
- Identical payloads without key → created duplicate jobs

**After (v2)**:
- Explicit `Idempotency-Key` header → uses provided key
- No header → computes key from `owner + tenant + type + payload_hash`
- Identical payloads from same user → deduplicated automatically

**Impact**:
- **Safer**: Prevents accidental duplicate jobs from client retry logic
- **Testing**: Test clients should use unique payloads to avoid unintended deduplication
- **Explicit keys**: Still recommended for critical workflows (e.g., payment processing)

**Example**:
```python
# v2: Same payload returns same job ID (200 OK, replayed)
resp1 = client.post("/v1/jobs", json={"type": "demo", "payload": {"x": 1}})
# → 202 Accepted, job_id=abc123

resp2 = client.post("/v1/jobs", json={"type": "demo", "payload": {"x": 1}})
# → 200 OK, job_id=abc123 (deduplicated by payload hash)

# Different payload creates new job
resp3 = client.post("/v1/jobs", json={"type": "demo", "payload": {"x": 2}})
# → 202 Accepted, job_id=def456
```

### 5. Cache-Control and ETag Headers (NEW)

**Change**: All job read endpoints now include caching headers for performance.

**New Headers**:
- `GET /v1/jobs`: `ETag`, `Cache-Control: private, max-age=30`, `Vary: Authorization`
- `GET /v1/jobs/:id`: `ETag`, `Cache-Control: private, max-age=15`, `Vary: Authorization`
- Support for `If-None-Match` → `304 Not Modified`

**Impact**:
- **Performance**: Clients can cache responses (user-specific, short TTL)
- **Bandwidth**: 304 responses have empty body (saves bandwidth)
- **Vary header**: Ensures cache isolation per user (Authorization header)

**Migration**:
```typescript
// v2: Leverage conditional requests for efficiency
let etag: string | null = null;

async function pollJobStatus(jobId: string) {
  const headers: Record<string, string> = {};
  if (etag) {
    headers['If-None-Match'] = etag;
  }

  const resp = await fetch(`/v1/jobs/${jobId}`, { headers });

  if (resp.status === 304) {
    // No change since last poll (use cached data)
    return cachedJob;
  }

  etag = resp.headers.get('ETag');
  cachedJob = await resp.json();
  return cachedJob;
}
```

## Upgrade Checklist

- [ ] Update OpenAPI spec to v2
- [ ] Regenerate SDK from new spec
- [ ] Add `owner` field to `JobCreateResponse` type
- [ ] Update permission checks: allow owner OR admin:all
- [ ] Change 403 → 404 expectations in tests for non-owner access
- [ ] Update error messages: "not found or access denied"
- [ ] Document new user capabilities (create/view/cancel own jobs)
- [ ] Add `If-None-Match` support for polling (optional, performance)
- [ ] Test with unique payloads to avoid payload-based deduplication conflicts

## Backward Compatibility

### Non-Breaking Changes
- Admin endpoints (`/v1/admin/jobs`) remain unchanged
- SSE protocol (`/v1/jobs/:id/events`) backward compatible
- Idempotency-Key header behavior preserved (explicit keys work identically)

### Deprecated (Still Works)
- None. All v1 features remain functional.

### Removed
- None. No v1 features were removed.

## Additional Resources

- [Security Documentation](../security.md) - RBAC and anti-enumeration details
- [API Reference](../api/) - Full OpenAPI v2 specification
- [Examples](../../examples/) - Updated code samples

## Questions?

For migration support, see:
- GitHub Issues: https://github.com/your-org/cineca-agentic-platform/issues
- API Changelog: [CHANGELOG.md](../../CHANGELOG.md)
