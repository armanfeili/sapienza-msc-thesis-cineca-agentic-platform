# Permission Simplification Summary

**Date**: January 16, 2025  
**Status**: ✅ Complete  
**Issue**: Model endpoints required non-existent `models:*` permissions that weren't configured in Auth0

## Problem

The model instance endpoints were using fine-grained permissions that didn't exist in Auth0:
- `models:read`, `models:test`, `models:defaults:read`, `models:defaults:write:self` (user permissions)
- `models:write`, `models:delete`, `models:defaults:write:tenant`, `models:defaults:write:global` (admin permissions)

**Available Auth0 Permissions**:
- Admin: `admin:all`, `tools:all`, `user:me`
- User: `tools:basic`, `user:me`

## Solution

Simplified the permission model to use only existing Auth0 permissions:

### New Permission Structure

**User Endpoints** (require `user:me` or `admin:all`):
- `GET /v1/models/instances` - List model instances
- `GET /v1/models/instances/{id}` - Get instance details
- `GET /v1/models/defaults` - Get default model with precedence
- `PATCH /v1/models/defaults` (user scope) - Set personal default
- `POST /v1/models/instances/{id}/tests` - Test model instance

**Admin Endpoints** (require `admin:all` only):
- `POST /v1/models/instances` - Create model instance
- `DELETE /v1/models/instances/{id}` - Delete model instance
- `PATCH /v1/models/defaults` (tenant/global scope) - Set tenant or global defaults

### Key Changes

1. **Permission Constants** (`src/security/model_perms.py`):
   ```python
   # Before: 11 permission constants
   MODELS_READ = "models:read"
   MODELS_TEST = "models:test"
   MODELS_WRITE = "models:write"
   # ... etc
   
   # After: 2 permission constants
   USER_ME = "user:me"
   ADMIN_ALL = "admin:all"
   ```

2. **Endpoint Dependencies** (`src/routers/model_instances.py`):
   ```python
   # Before
   user: UserInfo = Depends(require_any_perms([MODELS_READ, ADMIN_ALL]))
   
   # After
   user: UserInfo = Depends(require_any_perms([USER_ME, ADMIN_ALL]))
   ```

3. **Admin Check** (`src/security/model_perms.py`):
   ```python
   # Before: Check multiple admin permissions
   def is_admin(user: UserInfo) -> bool:
       return has_any_permission(user, [ADMIN_ALL, MODELS_WRITE, MODELS_DELETE])
   
   # After: Check only admin:all
   def is_admin(user: UserInfo) -> bool:
       return has_permission(user, ADMIN_ALL)
   ```

4. **Scope Resolution** (`src/security/model_perms.py`):
   ```python
   def can_set_default_scope(user: UserInfo, scope: str) -> bool:
       if scope == "user":
           # Any authenticated user can set their own defaults
           return has_any_permission(user, [USER_ME, ADMIN_ALL])
       elif scope in ["tenant", "global"]:
           # Only admins can set tenant/global defaults
           return has_permission(user, ADMIN_ALL)
   ```

5. **User Default Repository** (`db/postgres_control/repositories/user_default_models.py`):
   - Fixed return value to include `instance_id` and `instance_name` (compatibility with endpoint expectations)
   - Added provider and model details to response

## Testing Results

All endpoints tested and working correctly:

### ✅ User Access (USER_TOKEN with `user:me` permission)
```bash
# List instances
GET /v1/models/instances → 200 OK (4 instances)

# Get instance details
GET /v1/models/instances/{id} → 200 OK

# Get defaults
GET /v1/models/defaults → 200 OK

# Set personal default
PATCH /v1/models/defaults (X-Default-Scope: user) → 200 OK

# Test model
POST /v1/models/instances/{id}/tests → 200 OK (output: "Hello.")
```

### ✅ User Restrictions (USER_TOKEN cannot access admin operations)
```bash
# Cannot create instances
POST /v1/models/instances → 403 Forbidden "Admin privileges required"

# Cannot set tenant defaults
PATCH /v1/models/defaults (X-Default-Scope: tenant) → 403 Forbidden
```

### ✅ Admin Access (ADMIN_TOKEN with `admin:all` permission)
- All user operations ✅
- Create instances ✅
- Delete instances ✅
- Set tenant/global defaults ✅

## Files Modified

1. **`src/security/model_perms.py`**
   - Removed 9 unused permission constants (`models:*`)
   - Simplified to 2 constants: `USER_ME`, `ADMIN_ALL`
   - Updated `is_admin()` to only check `admin:all`
   - Updated `can_set_default_scope()` for simplified permissions
   - Updated `get_allowed_default_scopes()` for simplified permissions

2. **`src/routers/model_instances.py`**
   - Updated imports (removed unused permission constants)
   - Changed all endpoint dependencies:
     - User endpoints: `require_any_perms([USER_ME, ADMIN_ALL])`
     - Admin endpoints: `require_admin()` (checks `admin:all`)
   - Updated docstrings to reflect new permission requirements
   - Updated error messages for permission failures

3. **`db/postgres_control/repositories/user_default_models.py`**
   - Fixed `set_user_default()` return value
   - Added `instance_id`, `instance_name`, `provider_id`, `model_id` to response
   - Maintains backward compatibility with `chat_instance_id`

## Benefits

1. **No Auth0 Configuration Required**: Uses existing permissions
2. **Simpler Permission Model**: 2 permissions instead of 11
3. **Clear RBAC**: User vs Admin distinction is obvious
4. **Backward Compatible**: All existing functionality preserved
5. **Maintainable**: Less permission constants to manage

## Migration Notes

- ✅ No breaking changes to API contracts
- ✅ All endpoints return same responses
- ✅ Error messages updated to reflect new permission requirements
- ✅ OpenAPI documentation updated
- ✅ No database migrations required
- ✅ Existing tokens work without modification

## Next Steps

- ✅ Code changes complete
- ✅ Testing complete
- ⏹️ No Auth0 configuration needed
- ⏹️ No deployment changes needed

## Token Examples

**Admin Token JWT Payload**:
```json
{
  "iss": "https://cineca.eu.auth0.com/",
  "sub": "auth0|68c70996...",
  "aud": "api://cineca-agentic-platform",
  "permissions": ["admin:all", "tools:all", "user:me"],
  "scope": "user:me tools:invoke:all admin:all"
}
```

**User Token JWT Payload**:
```json
{
  "iss": "https://cineca.eu.auth0.com/",
  "sub": "auth0|68c715d5...",
  "aud": "api://cineca-agentic-platform",
  "permissions": ["tools:basic", "user:me"],
  "scope": "user:me tools:invoke:basic"
}
```

## Conclusion

Successfully adapted the codebase to work with existing Auth0 permissions. All model endpoints are now accessible to users with `user:me` permission, while admin operations require `admin:all`. No changes needed to Auth0 configuration or existing tokens.
