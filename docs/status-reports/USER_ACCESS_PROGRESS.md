# User Access Implementation - Progress Report

**Date**: October 17, 2025  
**Status**: 🚧 In Progress (Phases 1-3 Complete)

## Completed Phases

### ✅ Phase 1: Dual Router Registration

**Objective**: Mount model_instances router at both `/v1/models` (user path) and `/v1/admin/models` (deprecated admin path)

**Changes**:
1. **src/routers/model_instances.py** - Removed `/models` prefix from router definition (now set at mount time)
2. **src/routers/admin.py** - Updated to mount model_instances with explicit `/models` prefix, added deprecation comment
3. **src/app.py** - Added new mount point for `/v1/models` before admin routes

**Result**:
- ✅ Both paths registered in OpenAPI spec
- ✅ `/models/instances`, `/models/defaults`, `/models/instances/{id}`, `/models/instances/{id}/tests` accessible at both locations
- ⚠️ FastAPI warnings about duplicate operation IDs (expected, non-breaking)

### ✅ Phase 2: Permission Helpers

**Objective**: Create flexible permission system to replace rigid `admin:all` checks

**New File**: `src/security/model_perms.py` (320 lines)

**Permission Constants**:
```python
# User-level
MODELS_READ = "models:read"
MODELS_TEST = "models:test"
MODELS_DEFAULTS_READ = "models:defaults:read"
MODELS_DEFAULTS_WRITE_SELF = "models:defaults:write:self"

# Admin-level
MODELS_WRITE = "models:write"
MODELS_DELETE = "models:delete"
MODELS_DEFAULTS_WRITE_TENANT = "models:defaults:write:tenant"
MODELS_DEFAULTS_WRITE_GLOBAL = "models:defaults:write:global"

# Legacy
ADMIN_ALL = "admin:all"
```

**Helper Functions**:
- `has_permission(user, permission)` - Check single permission
- `has_any_permission(user, permissions)` - Check multiple permissions (OR logic)
- `has_all_permissions(user, permissions)` - Check multiple permissions (AND logic)
- `is_admin(user)` - Check if user has admin privileges
- `check_permission(user, permissions)` - Raise HTTPException if missing permissions

**FastAPI Dependencies**:
- `require_any_perms(permissions)` - Require any of multiple permissions
- `require_all_perms(permissions)` - Require all permissions
- `require_admin()` - Require admin privileges

**Scope Helpers**:
- `can_set_default_scope(user, scope)` - Check if user can set defaults at scope
- `get_allowed_default_scopes(user)` - Get list of scopes user can modify

### ✅ Phase 3: Route Permission Updates

**Objective**: Replace `require_perms(["admin:all"])` with flexible permission checks

**Updated Endpoints**:

| Endpoint | Old Auth | New Auth | Notes |
|----------|----------|----------|-------|
| GET /instances | `get_current_user` | `require_any_perms([MODELS_READ, ADMIN_ALL])` | Now user-accessible |
| POST /instances | `require_perms(["admin:all"])` | `require_admin()` | Admin-only (create) |
| GET /defaults | `get_current_user` | `require_any_perms([MODELS_DEFAULTS_READ, ADMIN_ALL])` | User-accessible |
| PATCH /defaults | `require_perms(["admin:all"])` | *Kept for now* | Scope logic in Phase 8 |
| GET /instances/{id} | `require_perms(["admin:all"])` | `require_any_perms([MODELS_READ, ADMIN_ALL])` | User-accessible |
| DELETE /instances/{id} | `require_perms(["admin:all"])` | `require_admin()` | Admin-only (delete) |
| POST /instances/{id}/tests | `require_perms(["admin:all"])` | `require_any_perms([MODELS_TEST, ADMIN_ALL])` | User-accessible |

**Documentation Updates**:
- Added `**Required Scopes**` sections to all endpoint descriptions
- Updated summaries (e.g., "Admin Only" suffix for admin-only endpoints)
- Removed "admin:all required" wording from user-accessible endpoints

**Build Status**: ✅ App builds and starts successfully

---

## Remaining Phases

### 🔲 Phase 4: User Filtering Logic

**Objective**: Add behavior safeguards to protect user experience

**Planned Changes**:

1. **list_instances()** - Filter enabled=true for non-admin users
   ```python
   is_admin = has_any_permission(user, [ADMIN_ALL, MODELS_WRITE])
   enabled_filter = enabled if is_admin else True  # Force enabled for users
   ```

2. **get_instance()** - Return 404 (not 403) for disabled instances to users
   ```python
   if not instance.get("enabled") and not is_admin:
       raise HTTPException(404, "Instance not found")  # Hide existence
   ```

3. **test_instance()** - Return 409 for disabled instances
   ```python
   if not instance.get("enabled"):
       raise HTTPException(409, "Instance is disabled and cannot be tested")
   ```

### 🔲 Phase 5: User Defaults Database Schema

**Objective**: Create database table for user-scoped defaults

**Migration File**: `db/postgres_control/migrations/versions/XXXX_add_user_default_models.py`

**Schema**:
```sql
CREATE TABLE user_default_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255),  -- NULL for global user default
    chat_instance_id UUID NOT NULL REFERENCES model_instances(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(255),
    etag VARCHAR(64),
    CONSTRAINT uq_user_tenant_default UNIQUE(user_id, tenant_id)
);

CREATE INDEX idx_user_default_models_user_id ON user_default_models(user_id);
CREATE INDEX idx_user_default_models_tenant_id ON user_default_models(tenant_id);
CREATE INDEX idx_user_default_models_instance_id ON user_default_models(chat_instance_id);
```

### 🔲 Phase 6: UserDefaultModelRepo

**Objective**: Implement repository layer for user defaults

**New File**: `db/postgres_control/repositories/user_default_models.py`

**Methods**:
- `get_user_default(user_id, tenant_id)` - Get user's default with precedence
- `set_user_default(user_id, instance_id, tenant_id)` - Set/update user default
- `delete_user_default(user_id, tenant_id)` - Delete user default
- `cascade_clear_defaults(instance_id)` - Clear all user defaults for deleted instance

### 🔲 Phase 7: GET /defaults Precedence

**Objective**: Implement default resolution precedence

**Resolution Order**:
1. User default (user_id + tenant_id)
2. Tenant default (tenant_id only)
3. Global default (tenant_id=None)
4. 404 Not Found

**Response Headers**:
- `X-Default-Scope: user|tenant|global` - Indicates which scope was used

### 🔲 Phase 8: PATCH /defaults Scope Support

**Objective**: Allow users to set their own defaults, admins to set tenant/global

**New Header**: `X-Default-Scope: user|tenant|global` (default: user)

**Permission Matrix**:
| Scope | Required Permissions |
|-------|---------------------|
| user | `models:defaults:write:self` or `admin:all` |
| tenant | `models:defaults:write:tenant` or `admin:all` |
| global | `models:defaults:write:global` or `admin:all` |

### 🔲 Phase 9: OpenAPI Documentation

**Objective**: Update OpenAPI spec with new paths and deprecation markers

**Tasks**:
- Mark `/admin/models/*` paths as deprecated
- Add security schemes for new scopes
- Document X-Default-Scope header
- Separate tags: `models-instances` (user) vs `models-instances-admin` (admin)
- Update descriptions removing "admin" wording

### 🔲 Phase 10: Integration Tests

**Objective**: Validate user vs admin access patterns

**Test Coverage**:
- User token can list/get/test enabled instances
- User token cannot see disabled instances
- User token blocked from create/delete
- User can set own default
- User cannot set tenant/global defaults
- Admin can do everything
- Default precedence works correctly

### 🔲 Phase 11: Documentation & Migration Guide

**Objective**: Document changes for users and API clients

**Files to Create/Update**:
- `CHANGELOG.md` - Version history entry
- `docs/USER_ACCESS_MIGRATION_GUIDE.md` - Client migration steps
- `docs/USER_ACCESS_IMPLEMENTATION_PLAN.md` - Update with actual notes
- README updates if needed

---

## Known Issues

### Duplicate Operation ID Warnings

**Issue**: FastAPI warns about duplicate operation IDs when same router is mounted twice

**Warning Example**:
```
UserWarning: Duplicate Operation ID get_default_model for function get_default
UserWarning: Duplicate Operation ID set_default_model for function set_default
UserWarning: Duplicate Operation ID get_model_instance for function get_instance
```

**Impact**: Non-breaking, cosmetic only. OpenAPI spec includes both paths.

**Resolution Options**:
1. ✅ **Accept warnings** - Simplest, no code changes, zero risk
2. Custom operation_id per mount - Requires wrapper functions or metaclass
3. Separate router instances - More complex, duplicates code

**Decision**: Accept warnings for now. Can revisit if it causes client issues.

---

## Testing Strategy

### Manual Testing (Current)

```bash
# Verify both paths exist
curl -s http://localhost:8000/v1/openapi.json | jq -r '.paths | keys | .[]' | grep models

# Expected output:
# /admin/models/defaults
# /admin/models/instances
# /admin/models/instances/{instance_id}
# /admin/models/instances/{instance_id}/tests
# /models/defaults
# /models/instances
# /models/instances/{instance_id}
# /models/instances/{instance_id}/tests
```

### Automated Testing (Phase 10)

1. **Permission Tests** - Verify scope enforcement
2. **Filtering Tests** - Verify enabled-only for users
3. **Precedence Tests** - Verify default resolution order
4. **Backward Compatibility Tests** - Verify old paths still work

---

## Rollout Plan

### Step 1: Development (Current Phase)
- ✅ Implement dual registration
- ✅ Add permission helpers
- ✅ Update route permissions
- 🔲 Add user filtering
- 🔲 Implement user defaults

### Step 2: Testing
- 🔲 Integration tests
- 🔲 Manual QA with test tokens
- 🔲 Performance testing

### Step 3: Documentation
- 🔲 API docs
- 🔲 Migration guide
- 🔲 CHANGELOG

### Step 4: Deployment
- 🔲 Deploy to dev
- 🔲 Deploy to staging
- 🔲 Deploy to production
- 🔲 Monitor metrics

### Step 5: Deprecation
- 🔲 30-day notice (email + logs)
- 🔲 60-day notice (email + logs)
- 🔲 90-day sunset (remove old paths)

---

## Next Steps

1. **Immediate**: Implement Phase 4 (user filtering logic)
2. **Short-term**: Phases 5-6 (database schema + repository)
3. **Medium-term**: Phases 7-8 (default precedence)
4. **Long-term**: Phases 9-11 (docs, tests, migration)

**Estimated Completion**: 
- Core functionality (Phases 1-8): 2-3 days
- Testing & docs (Phases 9-11): 1-2 days
- **Total**: 3-5 days

---

**Last Updated**: 2025-10-17 09:50 UTC  
**Next Review**: After Phase 4 completion
