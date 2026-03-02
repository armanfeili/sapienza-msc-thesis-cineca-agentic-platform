# OpenAPI Tags Reorganization - Complete

**Date**: October 13, 2025  
**Status**: ✅ **COMPLETED**

## Changes Made

Successfully reorganized and renamed all OpenAPI tags according to the specified order and naming convention.

### Tag Order and Names

The following tags are now ordered and named as specified:

1. **meta** (unchanged)
2. **health** (unchanged)
3. **auth** (unchanged)
4. **admin-tenants** (unchanged)
5. **models-providers** (unchanged)
6. **models-manifests-builtins** (renamed from "Builtins Manifests")
7. **models-instances** (renamed from "Model Instances")
8. **tools** (unchanged)
9. **jobs** (unchanged)
10. **agents** (unchanged)
11. **admin-processes** (renamed from "processes")
12. **internal-ops** (unchanged)
13. **internal-db** (unchanged)

### Files Modified

1. **src/app.py**
   - Updated `PREFERRED_TAG_ORDER` list to reflect new order and names
   - This controls the order tags appear in Swagger UI

2. **src/routers/model_instances.py**
   - Changed tag from `["Model Instances"]` to `["models-instances"]`
   - Router: `APIRouter(prefix="/models", tags=["models-instances"])`

3. **src/routers/manifests.py**
   - Changed tag from `["Builtins Manifests"]` to `["models-manifests-builtins"]`
   - Router: `APIRouter(prefix="/models/manifests/builtins", tags=["models-manifests-builtins"])`

4. **src/routers/model_processes.py**
   - Changed tag from `["processes"]` to `["admin-processes"]`
   - Router: `APIRouter(tags=["admin-processes"])`

### Verification Results

✅ **All tags correctly ordered in OpenAPI spec**

```
1.  meta
2.  health
3.  auth
4.  admin-tenants
5.  models-providers
6.  models-manifests-builtins
7.  models-instances
8.  tools
9.  jobs
10. agents
11. admin-processes
12. internal-ops
13. internal-db
```

✅ **All endpoints tagged correctly**

- Model Instances: `models-instances` ✓
- Providers: `models-providers` ✓
- Manifests: `models-manifests-builtins` ✓
- Processes: `admin-processes` ✓

### Impact

- ✅ Swagger UI now shows sections in the specified order
- ✅ All endpoint tags use lowercase with hyphens (consistent naming)
- ✅ Tag names clearly indicate admin vs user sections (admin-tenants, admin-processes)
- ✅ Related tags grouped together (all models-* tags sequential)
- ✅ No breaking changes to API functionality
- ✅ Improved API documentation organization

### Testing

Verified via:
1. OpenAPI JSON spec inspection (`/openapi.json`)
2. Swagger UI visual inspection (tags appear in correct order)
3. Endpoint tag verification (all endpoints correctly tagged)

---

## Notes

- The `Models – Catalog` router was not modified as it was not in the specified list
- All changes are backward compatible (only affects documentation display)
- Tag order is controlled by `PREFERRED_TAG_ORDER` in `src/app.py`
- Individual router tags are defined in each router file
