# Swagger UI Header Parameter Fix

## Problem
The `X-Tenant-Id` header was required for POST `/v1/admin/tenants` but didn't appear in Swagger UI's "Try it out" interface, making manual testing difficult.

## Root Cause
Using `Depends(require_tenant_header)` or manually reading from `request.headers` doesn't expose the header parameter in OpenAPI schema. FastAPI needs an **explicit `Header` parameter** in the route signature.

## Solution Implemented

### 1. Added Explicit Header Parameter
Changed the POST endpoint signature from:
```python
async def create_tenant(
    req: CreateTenantRequest,
    request: Request,
    response: Response,
    user: UserInfo = Depends(require_perms([]))
) -> Tenant:
    tenant_context = request.headers.get("X-Tenant-Id")
    if not tenant_context:
        raise HTTPException(status_code=400, ...)
```

To:
```python
from typing import Annotated
from fastapi import Header

async def create_tenant(
    req: CreateTenantRequest,
    request: Request,
    response: Response,
    x_tenant_id: Annotated[
        str, 
        Header(
            ..., 
            alias="X-Tenant-Id",
            description="Admin audit context - which tenant is performing this admin operation",
            example="tenant-admin-root"
        )
    ],
    user: UserInfo = Depends(require_perms([]))
) -> Tenant:
    tenant_context = x_tenant_id  # FastAPI validates automatically
```

### 2. Updated Error Handling
**Before**: Manual validation returned `400 Bad Request`  
**After**: FastAPI automatic validation returns `422 Unprocessable Entity` (more semantically correct)

### 3. Updated OpenAPI Documentation
- Removed `400` response from OpenAPI spec
- Updated `422` response to include two examples:
  - Invalid email format
  - Missing `X-Tenant-Id` header
- Updated status code descriptions in docstring

### 4. Updated Tests
Changed `test_create_tenant_requires_x_tenant_id_header` to expect `422` instead of `400`:
```python
def test_create_tenant_requires_x_tenant_id_header(self, client, admin_token, test_tenant_payload):
    """Create endpoint requires X-Tenant-Id header (422 validation error)."""
    headers = {"Authorization": f"Bearer {admin_token}"}  # Missing X-Tenant-Id
    response = client.post("/v1/admin/tenants", json=test_tenant_payload, headers=headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = response.json()
    assert "detail" in data
```

## Verification

### OpenAPI Schema
```bash
$ cat api/openapi.json | jq '.paths["/v1/admin/tenants"].post.parameters'
```

Output:
```json
[
  {
    "name": "X-Tenant-Id",
    "in": "header",
    "required": true,
    "schema": {
      "type": "string",
      "description": "Admin audit context - which tenant is performing this admin operation",
      "title": "X-Tenant-Id"
    },
    "description": "Admin audit context - which tenant is performing this admin operation",
    "example": "tenant-admin-root"
  }
]
```

### Test Results
```bash
$ pytest tests/test_tenants_contract.py::TestTenantsCreate -v
# ✅ 6/6 tests passing
```

### Swagger UI Impact
Now when users click "Try it out" on POST `/v1/admin/tenants`:
- ✅ **X-Tenant-Id** field appears in the UI
- ✅ Field is marked as **required** (red asterisk)
- ✅ Description and example value are shown
- ✅ User can fill it in before executing

## Files Modified

1. **src/routers/tenants_admin.py**
   - Added `Annotated` and `Header` imports
   - Changed `create_tenant()` signature to include explicit header parameter
   - Removed manual header validation (FastAPI handles it)
   - Updated OpenAPI `responses` dict (removed 400, enhanced 422)
   - Updated status code list in docstring

2. **tests/test_tenants_contract.py**
   - Updated `test_create_tenant_requires_x_tenant_id_header` to expect 422

## Benefits

✅ **Better DX**: Swagger UI now shows the header field  
✅ **Automatic Validation**: FastAPI validates header presence  
✅ **More Semantic**: 422 (validation error) vs 400 (bad request)  
✅ **Self-Documenting**: OpenAPI schema is complete  
✅ **Fewer Bugs**: Can't forget to validate header (FastAPI does it)

## Next Steps

Consider applying the same pattern to other admin endpoints that require `X-Tenant-Id`:
- PATCH `/v1/admin/tenants/{id}`
- DELETE `/v1/admin/tenants/{id}`
- Other `/v1/admin/*` endpoints

This ensures consistency and improves the Swagger UI experience across all admin operations.
