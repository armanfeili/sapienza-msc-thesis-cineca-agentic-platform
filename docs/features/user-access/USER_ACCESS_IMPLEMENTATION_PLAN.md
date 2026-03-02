# Implementation Plan: Open Models-Instances to Users

**Date**: October 17, 2025  
**Status**: 🚧 In Progress  
**Objective**: Allow regular users to access model instances (list, get, test, defaults) while keeping create/delete admin-only

## Current Architecture

### Router Structure
- **Router**: `src/routers/model_instances.py`
- **Current Prefix**: `/models` (defined in router)
- **Mounted At**: `/v1/admin` (via `src/routers/admin.py`)
- **Final Paths**: `/v1/admin/models/*`

### Current Endpoints
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/admin/models/instances` | GET | admin:all | List instances |
| `/v1/admin/models/instances` | POST | admin:all | Create instance |
| `/v1/admin/models/instances/{id}` | GET | admin:all | Get instance |
| `/v1/admin/models/instances/{id}` | DELETE | admin:all | Delete instance |
| `/v1/admin/models/instances/{id}/tests` | POST | admin:all | Test instance |
| `/v1/admin/models/defaults` | GET | get_current_user | Get default |
| `/v1/admin/models/defaults` | PATCH | admin:all | Set default |

## Implementation Strategy

### Phase 1: Dual Registration Approach ✅ RECOMMENDED

**Strategy**: Mount the same router twice - once under `/v1/admin` (deprecated) and once under `/v1` (new).

**Advantages**:
- ✅ Minimal code changes
- ✅ Perfect backward compatibility
- ✅ Can gradually deprecate old paths
- ✅ No conditional logic in route handlers

**Implementation**:
1. In `src/app.py`, add new mount before admin routes:
   ```python
   # Mount models-instances for users (public access)
   _try_include("src.routers.model_instances", prefix="/v1")
   ```

2. Keep existing mount in `src/routers/admin.py`:
   ```python
   _include("src.routers.model_instances", "", skip_admin_guard=True)
   ```

3. Update router in `src/routers/model_instances.py`:
   - Remove `/models` prefix from router definition
   - Add prefix when mounting: `prefix="/models"` in app.py

### Phase 2: Permission Updates

#### New Permission Structure

```python
# User scopes (new)
MODELS_READ = "models:read"              # List/get instances
MODELS_TEST = "models:test"              # Test instances
MODELS_DEFAULTS_READ = "models:defaults:read"      # Read defaults
MODELS_DEFAULTS_WRITE_SELF = "models:defaults:write:self"  # Set own default

# Admin scopes (existing + new)
MODELS_WRITE = "models:write"            # Create instances
MODELS_DELETE = "models:delete"          # Delete instances
MODELS_DEFAULTS_WRITE_TENANT = "models:defaults:write:tenant"  # Set tenant default
MODELS_DEFAULTS_WRITE_GLOBAL = "models:defaults:write:global"  # Set global default
ADMIN_ALL = "admin:all"                  # Legacy admin scope
```

#### Permission Mapping

| Endpoint | User Scopes | Admin Scopes |
|----------|-------------|--------------|
| GET /models/instances | models:read | models:read, admin:all |
| GET /models/instances/{id} | models:read | models:read, admin:all |
| POST /models/instances/{id}/tests | models:test | models:test, admin:all |
| GET /models/defaults | models:defaults:read | models:defaults:read, admin:all |
| PATCH /models/defaults (self) | models:defaults:write:self | models:defaults:write:self, admin:all |
| PATCH /models/defaults (tenant) | ❌ | models:defaults:write:tenant, admin:all |
| PATCH /models/defaults (global) | ❌ | models:defaults:write:global, admin:all |
| POST /admin/models/instances | ❌ | models:write, admin:all |
| DELETE /admin/models/instances/{id} | ❌ | models:delete, admin:all |

### Phase 3: Database Changes for User Defaults

#### New Table: `user_default_models`

```sql
CREATE TABLE user_default_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,  -- Subject from JWT
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

#### Repository Methods

```python
class UserDefaultModelRepo:
    def get_user_default(self, user_id: str, tenant_id: Optional[str] = None) -> Optional[Dict]:
        """Get user's default model with precedence."""
        pass
    
    def set_user_default(self, user_id: str, instance_id: str, tenant_id: Optional[str] = None) -> Dict:
        """Set or update user's default model."""
        pass
    
    def delete_user_default(self, user_id: str, tenant_id: Optional[str] = None) -> bool:
        """Delete user's default model."""
        pass
    
    def cascade_clear_defaults(self, instance_id: str) -> int:
        """Clear all user defaults pointing to deleted instance."""
        pass
```

### Phase 4: Default Resolution Precedence

#### GET /models/defaults Logic

```python
async def get_default(user: UserInfo):
    """
    Resolution order:
    1. User default (user_id + tenant_id)
    2. Tenant default (tenant_id only)
    3. Global default (tenant_id=None)
    4. 404 Not Found
    """
    
    # 1. Check user default
    user_default = user_default_repo.get_user_default(
        user_id=user.sub,
        tenant_id=user.tenant_id
    )
    if user_default:
        return build_response(user_default, scope="user")
    
    # 2. Check tenant default (if tenant_id present)
    if user.tenant_id:
        tenant_default = model_instance_repo.get_default(
            scope="tenant",
            tenant_id=user.tenant_id
        )
        if tenant_default:
            return build_response(tenant_default, scope="tenant")
    
    # 3. Check global default
    global_default = model_instance_repo.get_default(
        scope="global",
        tenant_id=None
    )
    if global_default:
        return build_response(global_default, scope="global")
    
    # 4. No default found
    raise HTTPException(404, "No default model configured")
```

#### PATCH /models/defaults Logic

```python
async def set_default(
    req: SetDefaultRequest,
    user: UserInfo,
    x_default_scope: Optional[str] = Header(None, alias="X-Default-Scope"),
):
    """
    Set default based on scope:
    - 'user' (default): Set user default (requires models:defaults:write:self)
    - 'tenant': Set tenant default (requires models:defaults:write:tenant + admin)
    - 'global': Set global default (requires models:defaults:write:global + admin)
    """
    
    scope = x_default_scope or "user"
    
    if scope == "user":
        # Requires: models:defaults:write:self
        check_permission(user, "models:defaults:write:self")
        return user_default_repo.set_user_default(
            user_id=user.sub,
            instance_id=instance_id,
            tenant_id=user.tenant_id
        )
    
    elif scope == "tenant":
        # Requires: models:defaults:write:tenant or admin:all
        check_permission(user, ["models:defaults:write:tenant", "admin:all"])
        if not user.tenant_id:
            raise HTTPException(400, "X-Tenant-Id required for tenant scope")
        return model_instance_repo.set_default(
            scope="tenant",
            instance_id=instance_id,
            tenant_id=user.tenant_id
        )
    
    elif scope == "global":
        # Requires: models:defaults:write:global or admin:all
        check_permission(user, ["models:defaults:write:global", "admin:all"])
        return model_instance_repo.set_default(
            scope="global",
            instance_id=instance_id,
            tenant_id=None
        )
    
    else:
        raise HTTPException(400, f"Invalid X-Default-Scope: {scope}")
```

### Phase 5: User Safeguards

#### Filter Disabled Instances for Users

```python
async def list_instances(
    user: UserInfo,
    enabled: Optional[bool] = Query(None),
    ...
):
    """List instances with admin/user filtering."""
    
    # Admin can see all instances
    is_admin = has_any_permission(user, ["admin:all", "models:write"])
    
    if is_admin:
        # Admin sees all instances, respects enabled filter
        enabled_filter = enabled
    else:
        # User sees only enabled instances
        enabled_filter = True
    
    instances, total, next_token = model_instance_repo.list_instances(
        enabled=enabled_filter,
        ...
    )
    
    return ListInstancesResponse(...)
```

#### Hide Disabled Instances from Users

```python
async def get_instance(
    instance_id: str,
    user: UserInfo,
):
    """Get instance with visibility check."""
    
    instance = model_instance_repo.get_instance(instance_id)
    
    if not instance:
        raise HTTPException(404, "Instance not found")
    
    # Check if user can see disabled instances
    is_admin = has_any_permission(user, ["admin:all", "models:write"])
    
    if not instance.get("enabled") and not is_admin:
        # Hide disabled instances from users
        raise HTTPException(404, "Instance not found")
    
    return instance
```

#### Test Only Enabled Instances

```python
async def test_instance(
    instance_id: str,
    user: UserInfo,
    req: TestInstanceRequest,
):
    """Test instance with enabled check."""
    
    instance = model_instance_repo.get_instance(instance_id)
    
    if not instance:
        raise HTTPException(404, "Instance not found")
    
    if not instance.get("enabled"):
        raise HTTPException(
            409,
            "Instance is disabled and cannot be tested"
        )
    
    # Proceed with test...
```

### Phase 6: OpenAPI Documentation Updates

#### Update Route Decorators

```python
# User-accessible route
@router.get(
    "/instances",
    response_model=ListInstancesResponse,
    summary="List model instances",
    description="""
List available model instances (authenticated users).

**User Access**: Returns only enabled instances.
**Admin Access**: Can see all instances with enabled filter.

**Required Scopes**: models:read or admin:all
""",
    operation_id="list_model_instances",
    responses={...},
    tags=["models-instances"],  # Remove "admin" from tags
)
async def list_instances(...):
    pass

# Admin-only route
@router.post(
    "/instances",
    response_model=LoadInstanceResponse,
    summary="Create model instance (admin only)",
    description="""
Create a new model instance (admin:all required).

**Admin Only**: Regular users cannot access this endpoint.

**Required Scopes**: models:write or admin:all
""",
    operation_id="create_model_instance",
    responses={...},
    tags=["models-instances-admin"],  # Separate tag for admin-only
)
async def load_instance(...):
    pass
```

#### Mark Deprecated Routes

When dual-mounting, use OpenAPI extensions:

```python
@router.get(
    "/instances",
    deprecated=True,  # Mark old path as deprecated
    summary="[DEPRECATED] List model instances",
    description="""
⚠️ **DEPRECATED**: Use GET /v1/models/instances instead.

This endpoint will be removed in a future release.
""",
)
```

### Phase 7: Migration Checklist

#### Code Changes
- [ ] Update `src/app.py` to dual-mount model_instances router
- [ ] Update `src/routers/model_instances.py` router prefix
- [ ] Create `src/security/model_perms.py` for permission helpers
- [ ] Update all route decorators with new permission checks
- [ ] Add user filtering logic to list_instances
- [ ] Add visibility checks to get_instance
- [ ] Add enabled check to test_instance
- [ ] Update OpenAPI tags and descriptions

#### Database Changes
- [ ] Create Alembic migration for `user_default_models` table
- [ ] Create `UserDefaultModelRepo` in `db/postgres_control/repositories/`
- [ ] Update `model_instance_repo` to support cascade clearing

#### Permission Changes
- [ ] Update `src/security/perm.py` with new scopes
- [ ] Create `require_any_perms()` helper for OR logic
- [ ] Update Auth0 API configuration with new scopes
- [ ] Update role mappings (User role gets new scopes)

#### Testing
- [ ] Add integration tests for user token access
- [ ] Add integration tests for admin token access
- [ ] Test user can list/get/test enabled instances
- [ ] Test user cannot see disabled instances
- [ ] Test user can set their own default
- [ ] Test user cannot set tenant/global defaults
- [ ] Test admin can still do everything
- [ ] Test backward compatibility with old paths

#### Documentation
- [ ] Update API documentation with new paths
- [ ] Document permission model and scopes
- [ ] Add CHANGELOG entry
- [ ] Update client migration guide
- [ ] Document default resolution precedence

## Rollout Strategy

### Phase 1: Internal Testing (Week 1)
- Deploy to dev environment
- Test with dev tokens (user + admin)
- Verify dual paths work
- Verify old paths still work

### Phase 2: Beta Release (Week 2)
- Deploy to staging
- Invite select users to test new paths
- Monitor logs for deprecation warnings
- Collect feedback

### Phase 3: General Availability (Week 3)
- Deploy to production
- Announce new user-accessible endpoints
- Document migration path
- Old paths remain active (deprecated)

### Phase 4: Deprecation (Month 2-3)
- Continue monitoring old path usage
- Send deprecation notices to API clients
- Provide 90-day sunset notice

### Phase 5: Removal (Month 4)
- Remove old /admin/models/* paths
- Keep only /models/* paths
- Complete migration

## Risk Mitigation

### Risk: Unauthorized Access
**Mitigation**: 
- Thorough permission testing
- Scope validation on every endpoint
- Admin-only endpoints remain under /admin prefix

### Risk: Performance Impact
**Mitigation**:
- User queries only fetch enabled instances (faster)
- ETag caching reduces DB load
- Existing indices support filtering

### Risk: Breaking Changes
**Mitigation**:
- Dual registration ensures no breakage
- Deprecation warnings give advance notice
- Comprehensive backward compatibility testing

### Risk: Permission Confusion
**Mitigation**:
- Clear documentation of scope requirements
- Helpful error messages (403 vs 404)
- Example tokens for testing

## Success Criteria

- ✅ User tokens can access GET /models/instances
- ✅ User tokens can access GET /models/instances/{id}
- ✅ User tokens can access POST /models/instances/{id}/tests
- ✅ User tokens can access GET /models/defaults
- ✅ User tokens can access PATCH /models/defaults (self)
- ✅ User tokens cannot access create/delete endpoints
- ✅ Admin tokens continue to work for all endpoints
- ✅ Old /admin/models/* paths still work (deprecated)
- ✅ Users see only enabled instances
- ✅ Per-user defaults work correctly
- ✅ Default resolution precedence works (user > tenant > global)
- ✅ OpenAPI docs show new paths and scopes
- ✅ Zero downtime during rollout
- ✅ All existing tests pass

---

**Next Steps**: Begin Phase 1 implementation with dual router registration
