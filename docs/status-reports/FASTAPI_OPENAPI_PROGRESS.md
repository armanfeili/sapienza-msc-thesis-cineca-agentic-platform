# FastAPI Swagger/OpenAPI Integration Progress

## ✅ Completed

### 1. Pydantic Models with Examples

#### LoadInstanceRequest ✅
- Added `Modality` enum with text/vision/audio/tool
- Added 6 named examples in `model_config.json_schema_extra`:
  - GPT-4o (OpenAI)
  - GPT-4o-mini (OpenAI)
  - GPT-3.5-Turbo (OpenAI, tenant-scoped)
  - GPT-4 (Azure OpenAI)
  - Claude 3 Opus (OpenRouter)
  - Llama 3.2 3B (Ollama)
- Proper field constraints (context_window ge=1024)
- Modalities uses Enum type

#### SetDefaultRequest ✅  
- Added 3 named examples:
  - By instance UUID (preferred)
  - By instance name (legacy)
  - Top-level name (deprecated)
- Marked legacy fields as DEPRECATED in descriptions

#### TestInstanceRequest ✅
- Added 4 named examples:
  - Factual deterministic
  - Short answer
  - Creative
  - Pre-formatted messages
- All fields properly documented

#### InstanceDetail Response ✅
- Created full response model with all fields
- No more `additionalProp1` placeholders
- Example included with realistic data

## 🚧 In Progress / TODO

### 2. Route Decorators Need Enhancement

Each endpoint needs proper `responses` dict in decorator. Example pattern:

```python
@router.post(
    "/instances",
    response_model=LoadInstanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Load/create model instance",
    description="...",
    operation_id="load_model_instance",  # Stable ID
    responses={
        201: {
            "description": "Instance created successfully",
            "headers": {
                "X-Request-Id": {"description": "Request correlation ID", "schema": {"type": "string"}},
                "ETag": {"description": "Entity tag for cache validation", "schema": {"type": "string"}},
                "Idempotency-Key": {"description": "Idempotency key from request", "schema": {"type": "string"}},
                "Idempotency-Replayed": {"description": "Whether this was a replay (true/false)", "schema": {"type": "string"}},
            },
        },
        200: {
            "description": "Idempotent replay - instance already exists",
            "headers": {
                "X-Request-Id": {"schema": {"type": "string"}},
                "Idempotency-Replayed": {"schema": {"type": "string"}, "example": "true"},
            },
        },
        400: {"description": "Bad Request (validation error, invalid provider_id, etc.)"},
        401: {"description": "Unauthorized (missing or invalid token)"},
        403: {"description": "Forbidden (insufficient permissions)"},
        409: {"description": "Conflict (instance name already exists)"},
        500: {"description": "Internal Server Error"},
    },
)
async def load_instance(
    request: Request,
    response: Response,
    req: LoadInstanceRequest,
    user: UserInfo = Depends(require_perms(["admin:all"])),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", description="Idempotency key for replay protection (24h window)"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id", description="Tenant ID for scoping (null=global)"),
):
```

### 3. Explicit Header Parameters

Current routes implicitly use headers but don't declare them for Swagger. Need to add:

```python
# Example for GET /instances
@router.get(
    "/instances",
    ...
)
async def list_instances(
    request: Request,
    response: Response,
    user: UserInfo = Depends(get_current_user),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match", description="ETag from previous response for cache validation"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id", description="Tenant ID for filtering (null=global)"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    provider_id: Optional[str] = Query(None, description="Filter by provider UUID"),
    loaded: Optional[bool] = Query(None, description="Filter by loaded status"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    page_size: int = Query(100, ge=1, le=1000, description="Items per page"),
    page_token: Optional[str] = Query(None, description="Pagination continuation token"),
):
```

### 4. Routes Requiring Updates

#### GET /instances
- [ ] Add `if_none_match` header param
- [ ] Add explicit query params (tenant_id, provider_id, loaded, enabled, page_size, page_token)
- [ ] Add 304 response to responses dict
- [ ] Document ETag response header

#### POST /instances  
- [ ] Add `idempotency_key` header param
- [ ] Add `x_tenant_id` header param
- [ ] Add responses dict with 200 (replay), 201, 400, 401, 403, 409, 500
- [ ] Document Idempotency-Replayed header

#### GET /defaults
- [ ] Add `if_none_match` header param
- [ ] Add 304 response
- [ ] Document ETag response header
- [ ] Fix 404 error to show correct instance path

#### PATCH /defaults
- [ ] Add responses dict
- [ ] Document request body examples (wired from SetDefaultRequest)

#### GET /instances/{id}
- [ ] Change `response_model` from Dict to InstanceDetail
- [ ] Add `if_none_match` header param
- [ ] Add 304 response
- [ ] Document ETag response header

#### DELETE /instances/{id}
- [ ] Add responses dict (204, 400, 404, 409, 500)
- [ ] Document no-content response

#### POST /instances/{id}/tests
- [ ] Add responses dict
- [ ] Document TestInstanceResponse with proper examples

### 5. Error Instance Path Fix

Currently errors from `/defaults` when no default is set show wrong path. Need to fix:

```python
# In app.py HTTP exception handler
prob = ProblemDetails(
    type="about:blank",
    title=title,
    status=exc.status_code,
    detail=str(getattr(exc, "detail", "")),
    instance=request.url.path,  # ✅ Use actual request path
    extensions=merged_ext,
)
```

### 6. Tag Descriptions

Need to add descriptions to `PREFERRED_TAG_ORDER` in app.py:

```python
OPENAPI_TAGS = [
    {"name": "meta", "description": "Platform metadata and information endpoints"},
    {"name": "health", "description": "Health checks and readiness probes"},
    {"name": "auth", "description": "Authentication and authorization"},
    {"name": "admin-tenants", "description": "Tenant management (admin only)"},
    {"name": "models-providers", "description": "LLM provider registration and configuration"},
    {"name": "models-manifests-builtins", "description": "Built-in model manifests and discovery"},
    {"name": "models-instances", "description": "Model instance lifecycle (load/unload/test)"},
    {"name": "tools", "description": "Tool definitions for agent use"},
    {"name": "jobs", "description": "Background job submission and monitoring"},
    {"name": "agents", "description": "Agent orchestration and execution"},
    {"name": "admin-processes", "description": "Process management (admin only)"},
    {"name": "internal-ops", "description": "Internal operations (not for external use)"},
    {"name": "internal-db", "description": "Database operations (internal only)"},
]

# In custom_openapi() function:
spec["tags"] = OPENAPI_TAGS
```

### 7. Security Scheme Enhancement

Already handled in app.py `custom_openapi()` - HTTPBearer is injected globally. Routes opt-out where needed (e.g., health checks).

## 📋 Implementation Checklist

### Phase 1: Models ✅
- [x] LoadInstanceRequest with 6 examples
- [x] SetDefaultRequest with 3 examples (preferred + legacy)
- [x] TestInstanceRequest with 4 examples
- [x] InstanceDetail response model

### Phase 2: Route Decorators (Next)
- [ ] Update GET /instances with headers + 304
- [ ] Update POST /instances with idempotency headers
- [ ] Update GET /defaults with headers + 304
- [ ] Update PATCH /defaults with responses
- [ ] Update GET /instances/{id} with InstanceDetail
- [ ] Update DELETE /instances/{id} with 204
- [ ] Update POST /instances/{id}/tests with responses

### Phase 3: App Configuration
- [ ] Add OPENAPI_TAGS with descriptions
- [ ] Fix ProblemDetails instance path
- [ ] Verify security scheme injection

### Phase 4: Testing
- [ ] Start docker compose
- [ ] Visit http://localhost:8000/docs
- [ ] Verify examples appear in request bodies
- [ ] Verify headers visible in parameters
- [ ] Verify 304 responses documented
- [ ] Verify InstanceDetail shows full fields (no additionalProp1)
- [ ] Verify tag ordering and descriptions

## 🎯 Key Patterns

### Request Body Examples

FastAPI automatically uses `model_config.json_schema_extra.examples` for Swagger UI dropdown. Each example needs:
- `summary`: Short name shown in dropdown
- `description`: Tooltip text
- `value`: Actual JSON payload

### Response Headers

Declare in `responses` dict:

```python
responses={
    200: {
        "description": "Success",
        "headers": {
            "ETag": {
                "description": "Entity tag for cache validation",
                "schema": {"type": "string"},
                "example": "\"abc123def456\""
            }
        }
    }
}
```

### Header Parameters

Make implicit headers explicit:

```python
idempotency_key: Optional[str] = Header(
    None, 
    alias="Idempotency-Key",
    description="Idempotency key for replay protection (24h window)",
    example="550e8400-e29b-41d4-a716-446655440000"
)
```

### 304 Not Modified

For GET endpoints supporting ETag:

```python
responses={
    200: {...},
    304: {
        "description": "Not Modified - content unchanged since last request (use cached version)",
        "headers": {
            "ETag": {"schema": {"type": "string"}}
        }
    }
}
```

## 📚 References

- FastAPI OpenAPI docs: https://fastapi.tiangolo.com/advanced/additional-responses/
- Pydantic examples: https://docs.pydantic.dev/latest/concepts/json_schema/
- OpenAPI 3.1 spec: https://spec.openapis.org/oas/v3.1.0

---

**Status**: Models complete ✅, Route decorators in progress 🚧  
**Next**: Update route decorators systematically, starting with GET /instances
