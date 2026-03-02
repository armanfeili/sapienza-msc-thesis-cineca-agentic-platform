# Model Instances User Access - Migration Guide

**Target Audience**: API clients consuming model instance endpoints  
**Effective Date**: October 17, 2025  
**Deprecation Date**: January 15, 2026 (90 days)  
**Breaking Change**: Path migration + scope-based defaults

---

## 🎯 Executive Summary

Model instance endpoints are now accessible to regular users (not just admins). This change introduces:

1. **New paths** at `/v1/models/*` (user-accessible)
2. **Deprecated paths** at `/v1/admin/models/*` (backward compat for 90 days)
3. **Fine-grained permissions** replace rigid `admin:all` check
4. **Per-user defaults** with precedence resolution
5. **Scope-based writes** for defaults (user/tenant/global)

**Action Required**: Migrate to new paths before January 15, 2026.

---

## 📅 Timeline

| Date | Milestone |
|------|-----------|
| **Oct 17, 2025** | New `/v1/models/*` paths available |
| **Oct 17, 2025** | Old `/v1/admin/models/*` paths **DEPRECATED** |
| **Nov 15, 2025** | 30-day warning (update by Jan 15) |
| **Dec 15, 2025** | 60-day warning (update by Jan 15) |
| **Jan 15, 2026** | **Old paths removed** (breaking change) |

---

## 🔄 Path Migration

### Old Paths (DEPRECATED, remove by Jan 15, 2026)

```http
GET    /v1/admin/models/instances
POST   /v1/admin/models/instances
GET    /v1/admin/models/defaults
PATCH  /v1/admin/models/defaults
GET    /v1/admin/models/instances/{id}
DELETE /v1/admin/models/instances/{id}
POST   /v1/admin/models/instances/{id}/tests
```

### New Paths (REQUIRED after Jan 15, 2026)

```http
GET    /v1/models/instances
POST   /v1/models/instances
GET    /v1/models/defaults
PATCH  /v1/models/defaults
GET    /v1/models/instances/{id}
DELETE /v1/models/instances/{id}
POST   /v1/models/instances/{id}/tests
```

**Migration Steps**:
1. Update all hardcoded URLs from `/v1/admin/models/` to `/v1/models/`
2. Test with your current tokens (both user and admin)
3. Verify filtering behavior (users see only enabled instances)
4. Update any stored references (docs, config files, etc.)

---

## 🔐 Permission Changes

### Old Permission Model

All endpoints required `admin:all` scope. Non-admin users were blocked with 403 Forbidden.

### New Permission Model

Fine-grained scopes allow users to access read/test operations:

| Endpoint | User Tokens | Admin Tokens |
|----------|-------------|--------------|
| GET /instances | ✅ `models:read` or `admin:all` | ✅ `admin:all` |
| POST /instances | ❌ Blocked (403) | ✅ `models:write` or `admin:all` |
| GET /defaults | ✅ `models:defaults:read` or `admin:all` | ✅ `admin:all` |
| PATCH /defaults | ✅ `models:defaults:write:self` (user scope only) | ✅ All scopes with `admin:all` |
| GET /instances/{id} | ✅ `models:read` or `admin:all` | ✅ `admin:all` |
| DELETE /instances/{id} | ❌ Blocked (403) | ✅ `models:delete` or `admin:all` |
| POST /instances/{id}/tests | ✅ `models:test` or `admin:all` | ✅ `admin:all` |

**Required Scopes**:
- **User tokens**: Add `models:read`, `models:test`, `models:defaults:read`, `models:defaults:write:self` scopes
- **Admin tokens**: `admin:all` grants all permissions (no change required)

---

## 🔒 Filtering Behavior Changes

### User Tokens (Non-Admin)

**List Instances** (`GET /instances`):
- ✅ **Before**: 403 Forbidden (no access)
- ✅ **After**: Returns **enabled instances only** (disabled instances filtered out)

**Get Instance** (`GET /instances/{id}`):
- ✅ **Before**: 403 Forbidden (no access)
- ✅ **After**: Returns instance if enabled, **404 Not Found** if disabled (hides existence)

**Test Instance** (`POST /instances/{id}/tests`):
- ✅ **Before**: 403 Forbidden (no access)
- ✅ **After**: Tests enabled instances, **409 Conflict** if disabled

**Security Note**: Disabled instances return 404 (not 403) to hide their existence from non-admin users.

### Admin Tokens

No change - admins see all instances (enabled + disabled) as before.

---

## 📊 Default Model Changes

### GET /defaults - Precedence Resolution

**Old Behavior**:
- Returned global or tenant default (no user-level defaults)

**New Behavior**:
- Resolves with **3-level precedence**:
  1. **User default** (highest priority) - personal preference
  2. **Tenant default** - organization-wide
  3. **Global default** - system-wide fallback
  4. **404 Not Found** - no default at any level

**Response Headers**:
```http
X-Default-Scope: user|tenant|global
```

Indicates which scope was used for resolution.

**Example**:

```http
GET /v1/models/defaults HTTP/1.1
Authorization: Bearer <user-token>
X-Tenant-Id: acme-corp
```

**Response** (user default exists):
```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Default-Scope: user
ETag: "abc123..."

{
  "chat": {
    "instance_id": "6491b020-bbe3-47fe-991e-e7c21a15260c",
    "name": "gpt-4o-production",
    "provider_id": "azure-openai",
    "model_id": "gpt-4o"
  },
  "etag": "abc123..."
}
```

**Response** (falls back to tenant default):
```http
HTTP/1.1 200 OK
X-Default-Scope: tenant
```

---

### PATCH /defaults - Scope Support

**Old Behavior**:
- Required `admin:all` scope
- Set global or tenant default only

**New Behavior**:
- **User scope** (default): Users can set own defaults
- **Tenant/Global scope**: Admins can set tenant/global defaults

**Request Headers**:
```http
X-Default-Scope: user|tenant|global  (optional, defaults to 'user')
X-Tenant-Id: <tenant-id>             (required for tenant scope)
```

**Permission Matrix**:

| Scope | Required Permission | Who Can Set |
|-------|--------------------| ------------|
| `user` | `models:defaults:write:self` or `admin:all` | ✅ Users + Admins |
| `tenant` | `models:defaults:write:tenant` or `admin:all` | ❌ Admins only |
| `global` | `models:defaults:write:global` or `admin:all` | ❌ Admins only |

**Example - User sets own default**:

```http
PATCH /v1/models/defaults HTTP/1.1
Authorization: Bearer <user-token>
X-Default-Scope: user
X-Tenant-Id: acme-corp
Content-Type: application/json

{
  "chat": {
    "instance_id": "6491b020-bbe3-47fe-991e-e7c21a15260c"
  }
}
```

**Response**:
```http
HTTP/1.1 200 OK
X-Default-Scope: user

{
  "ok": true,
  "message": "Default model updated successfully at 'user' scope",
  "instance_id": "6491b020-bbe3-47fe-991e-e7c21a15260c",
  "instance_name": "gpt-4o-production"
}
```

**Example - Admin sets tenant default**:

```http
PATCH /v1/models/defaults HTTP/1.1
Authorization: Bearer <admin-token>
X-Default-Scope: tenant
X-Tenant-Id: acme-corp
Content-Type: application/json

{
  "chat": {
    "instance_id": "12345678-1234-1234-1234-123456789012"
  }
}
```

**Response**:
```http
HTTP/1.1 200 OK
X-Default-Scope: tenant

{
  "ok": true,
  "message": "Default model updated successfully at 'tenant' scope",
  "instance_id": "12345678-1234-1234-1234-123456789012",
  "instance_name": "llama-3-70b-tenant"
}
```

**Example - User attempts tenant scope (Forbidden)**:

```http
PATCH /v1/models/defaults HTTP/1.1
Authorization: Bearer <user-token>
X-Default-Scope: tenant
```

**Response**:
```http
HTTP/1.1 403 Forbidden

{
  "type": "about:blank",
  "title": "Forbidden",
  "detail": "Insufficient permissions to set default at 'tenant' scope. Required: models:defaults:write:tenant or admin:all",
  "instance": "/v1/models/defaults"
}
```

---

## 🧪 Testing Strategy

### Test with User Tokens

1. **List instances** - should see only enabled instances
2. **Get instance** - enabled instances return 200, disabled return 404
3. **Test instance** - enabled instances work, disabled return 409
4. **Get defaults** - should resolve with precedence (user → tenant → global)
5. **Set own default** - should succeed with `X-Default-Scope: user`
6. **Attempt tenant/global scope** - should fail with 403 Forbidden
7. **Create/delete instances** - should fail with 403 Forbidden

### Test with Admin Tokens

1. **List instances** - should see all instances (enabled + disabled)
2. **Get instance** - should access all instances regardless of enabled status
3. **Create/delete instances** - should succeed
4. **Set defaults at any scope** - should succeed for user/tenant/global

### Test Precedence Resolution

1. Set user default → GET /defaults returns user default with `X-Default-Scope: user`
2. Delete user default → GET /defaults falls back to tenant default with `X-Default-Scope: tenant`
3. Delete tenant default → GET /defaults falls back to global default with `X-Default-Scope: global`
4. Delete global default → GET /defaults returns 404 Not Found

---

## 🚨 Error Handling

### New Error Scenarios

**400 Bad Request** - Invalid X-Default-Scope:
```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "detail": "Invalid X-Default-Scope: 'invalid'. Must be 'user', 'tenant', or 'global'",
  "instance": "/v1/models/defaults"
}
```

**403 Forbidden** - Insufficient permissions for scope:
```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "detail": "Insufficient permissions to set default at 'tenant' scope. Required: models:defaults:write:tenant or admin:all",
  "instance": "/v1/models/defaults"
}
```

**404 Not Found** - Disabled instance (user tokens only):
```json
{
  "type": "about:blank",
  "title": "Not Found",
  "detail": "Instance not found",
  "instance": "/v1/models/instances/6491b020-bbe3-47fe-991e-e7c21a15260c"
}
```

**409 Conflict** - Test disabled instance:
```json
{
  "type": "about:blank",
  "title": "Conflict",
  "detail": "Instance is disabled and cannot be tested",
  "instance": "/v1/models/instances/6491b020-bbe3-47fe-991e-e7c21a15260c/tests"
}
```

---

## 📋 Migration Checklist

- [ ] **Update all URLs** from `/v1/admin/models/` to `/v1/models/`
- [ ] **Add user scopes** to user tokens: `models:read`, `models:test`, `models:defaults:read`, `models:defaults:write:self`
- [ ] **Update error handling** for new 404/409 responses on disabled instances
- [ ] **Test filtering behavior** - verify users see only enabled instances
- [ ] **Test precedence resolution** - verify user → tenant → global → 404 order
- [ ] **Update defaults logic** - add `X-Default-Scope` header handling
- [ ] **Test permission enforcement** - verify users blocked from create/delete/tenant-scope
- [ ] **Update documentation** - client-side docs, examples, tutorials
- [ ] **Monitor logs** - check for deprecation warnings on old paths
- [ ] **Plan cutover** - schedule migration before January 15, 2026

---

## 📞 Support

**Questions?** Contact the platform team:
- Email: platform@cineca.example.com
- Slack: #cineca-platform
- Docs: https://docs.cineca.example.com

**Migration deadline**: January 15, 2026 (90 days from Oct 17, 2025)

---

**Last Updated**: October 17, 2025  
**Version**: 1.0  
**Status**: Active migration period
