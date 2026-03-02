# Providers API Visibility Fix

**Date**: October 13, 2025  
**Issue**: Providers section missing from FastAPI Swagger UI  
**Status**: ✅ **FIXED**

## Problem

The Providers API endpoints were not visible in the FastAPI Swagger UI documentation page. Users could not discover or interact with the 7 provider management endpoints through the interactive API docs.

## Root Cause

The `model_management.py` router (which contains all the provider endpoints) was disabled/commented out in `src/routers/admin.py`:

```python
# _include("src.routers.model_management", "/models")  # DISABLED: Use model_instances.py for PostgreSQL-backed endpoints
```

While the instance-related endpoints in `model_management.py` were correctly migrated to the new PostgreSQL-backed `model_instances.py` router, the **provider endpoints** were only in `model_management.py` and got accidentally disabled along with the instance endpoints.

## Solution

Re-enabled the `model_management` router in `src/routers/admin.py` to expose the provider endpoints:

```python
_include("src.routers.model_management", "/models")  # Includes providers endpoints (instances endpoints are disabled in that router)
```

**Note**: The instance endpoints in `model_management.py` are renamed with `_DISABLED_` prefix, so they don't conflict with the new PostgreSQL-backed endpoints in `model_instances.py`.

## Verification

### OpenAPI Spec
All 7 provider endpoints now appear in the OpenAPI specification with the `models-providers` tag:

```
✓ GET    /v1/admin/models/providers              - List providers
✓ POST   /v1/admin/models/providers/register     - Register new provider
✓ GET    /v1/admin/models/providers/main         - Get main/default provider
✓ GET    /v1/admin/models/providers/{id}         - Get provider details
✓ PATCH  /v1/admin/models/providers/{id}         - Update provider
✓ DELETE /v1/admin/models/providers/{id}         - Delete provider
✓ PUT    /v1/admin/models/providers/default      - Set default provider
```

### Functional Tests
```bash
# List providers
curl -X GET http://localhost:8000/v1/admin/models/providers \
  -H "Authorization: Bearer $ADMIN_TOKEN"
# Returns: HTTP 200 with provider list

# Register provider
curl -X POST http://localhost:8000/v1/admin/models/providers/register \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "test-provider", "type": "openai_compatible", "base_url": "https://api.openai.com/v1", "model": "gpt-4"}'
# Returns: HTTP 200 with success message
```

## Files Changed

1. **src/routers/admin.py**
   - Uncommented `_include("src.routers.model_management", "/models")`
   - Added clarifying comment about providers vs instances

## Impact

- ✅ All 7 provider endpoints now visible in Swagger UI
- ✅ No conflicts with model instances endpoints (they use different paths)
- ✅ Existing functionality preserved (providers still Redis-backed)
- ✅ No breaking changes to API consumers

## Related Documentation

- Provider endpoints are documented in `src/routers/model_management.py`
- Instance endpoints are documented in `src/routers/model_instances.py`
- Both routers can coexist as they manage different resources with different storage backends
  - Providers: Redis-backed (via `models_repo`)
  - Instances: PostgreSQL-backed (via `model_instance_repo`)
