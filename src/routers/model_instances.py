"""
Model Instances endpoints (user + admin access with dual-path routing).

This router is mounted at TWO paths for backward compatibility:
- /v1/models/*           -> User-accessible (NEW, preferred)
- /v1/admin/models/*     -> DEPRECATED (backward compat, will be removed in 90 days)

CRUD operations with fine-grained permissions:
- GET    /instances                -> List instances (users see enabled only, admins see all)
- POST   /instances                -> Create instance (admin-only: models:write or admin:all)
- GET    /defaults                 -> Get default with precedence (user → tenant → global)
- PATCH  /defaults                 -> Set default by scope (user scope for users, all scopes for admins)
- GET    /instances/{id}           -> Get instance details (users: enabled only, returns 404 for disabled)
- DELETE /instances/{id}           -> Delete instance (admin-only: models:delete or admin:all)
- POST   /instances/{id}/tests     -> Test instance (users can test enabled instances)

Permission Scopes:
- user:me                          -> Authenticated users (read/test instances, get/set own defaults)
- admin:all                        -> Admins (all operations: create, delete, set tenant/global defaults)

All endpoints return proper headers (X-Request-Id, X-Default-Scope, Cache-Control, Vary, ETag).
Error responses use problem+json format (RFC 7807).
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from enum import Enum
from typing import Any

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, ConfigDict, Field

from db.postgres_control.repositories import model_instance_repo, user_default_repo
from src.provenance import record_provenance
from src.schemas.auth import UserInfo
from src.schemas.models import (
    GetDefaultResponse,
    InstanceDetail,
    ListInstancesResponse,
    LoadInstanceRequest,
    LoadInstanceResponse,
    SetDefaultRequest,
    SetDefaultResponse,
    TestInstanceRequest,
    TestInstanceResponse,
)
from src.routers.auth import get_current_user
from src.security.model_perms import (
    ADMIN_ALL,
    USER_ME,
    can_set_default_scope,
    is_admin,
    require_admin,
    require_any_perms,
)

logger = logging.getLogger(__name__)

# DUAL ROUTING SETUP:
# 1. User-facing router at /v1/models (visible in schema)
router = APIRouter(tags=["models-instances"])

# 2. Legacy admin router at /v1/admin/models (hidden from schema for backward compat)
admin_router = APIRouter(tags=["models-instances"], include_in_schema=False)


def dual_route(method: str, path: str, **kwargs):
    """
    Decorator to register a route on BOTH routers (user and admin).

    The user router (mounted at /v1/models) shows in OpenAPI schema.
    The admin router (mounted at /v1/admin/models) is hidden for backward compat.
    """

    def decorator(func):
        # Register on user router (visible in schema)
        getattr(router, method)(path, **kwargs)(func)

        # Register on admin router (hidden from schema)
        # Add include_in_schema=False to hide from OpenAPI
        admin_kwargs = kwargs.copy()
        admin_kwargs["include_in_schema"] = False
        getattr(admin_router, method)(path, **admin_kwargs)(func)

        return func

    return decorator


# NOTE: Modality enum and all request/response models (LoadInstanceRequest, LoadInstanceResponse,
# ListInstancesResponse, GetDefaultResponse, SetDefaultRequest, SetDefaultResponse, InstanceDetail,
# TestInstanceRequest, TestInstanceResponse) now imported from schemas.models
# (Legacy definitions removed - see schemas/models.py for canonical versions)


# ========== Helper Functions ==========


def _generate_trace_id() -> str:
    """Generate trace ID for correlation."""
    return f"trace-{uuid.uuid4().hex[:16]}"


def _generate_event_id() -> str:
    """Generate event ID for provenance."""
    return f"event-{uuid.uuid4().hex[:16]}"


def _add_standard_headers(response: Response, etag: str | None = None, request_id: str | None = None):
    """Add standard headers (X-Request-Id, Cache-Control, Vary, ETag)."""
    response.headers["X-Request-Id"] = request_id or _generate_trace_id()
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    response.headers["Vary"] = "Authorization"

    if etag:
        response.headers["ETag"] = f'"{etag}"'


def _check_etag(request: Request, current_etag: str) -> bool:
    """Check If-None-Match header against current ETag. Returns True if match (304)."""
    if_none_match = request.headers.get("If-None-Match", "").strip().strip('"')
    return if_none_match == current_etag


# ========== Endpoints ==========


@dual_route(
    "get",
    "/instances",
    response_model=ListInstancesResponse,
    summary="List model instances",
    description="""
**GET /instances** – View all available AI models

**Why we need this endpoint:**
- Users and admins need to discover which AI models are available to use
- Applications need to show users a catalog of models they can interact with
- Without this, users wouldn't know which models exist or how to reference them in API calls

**What it does:**
- Returns a paginated list of all registered AI model instances
- Shows key details: model name, provider, capabilities, loaded status, and availability
- Non-admin users only see enabled models; admins can see all models including disabled ones

**Access:**
- Any authenticated user with `user:me` permission
- Admins with `admin:all` have additional visibility into disabled models

**Behavior:**
- Supports HTTP caching via ETag (returns `304 Not Modified` when content hasn't changed)
- Pagination: Use `page_size` (1-1000, default 100) and `page_token` for large result sets
- Filtering: Filter by `tenant_id`, `provider_id`, `loaded`, or `enabled` status
- Non-admin users automatically get `enabled=true` filter (only see active models)
- Admin users can override filters to see disabled or unloaded models

**Responses:**
- `200 OK` – Returns list of model instances with pagination metadata
- `304 Not Modified` – No changes since last request (use `If-None-Match` header with ETag)
- `401 Unauthorized` – Missing or invalid authentication token
- `403 Forbidden` – User lacks required permissions

**Examples:**
```bash
# List all available models (user view - enabled only)
curl -X GET "http://localhost:8000/v1/models/instances" \\
  -H "Authorization: Bearer $USER_TOKEN"

# Admin: List all models including disabled ones
curl -X GET "http://localhost:8000/v1/models/instances?enabled=false" \\
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Filter by provider and use pagination
curl -X GET "http://localhost:8000/v1/models/instances?provider_id=ollama-local&page_size=50" \\
  -H "Authorization: Bearer $USER_TOKEN"

# Use caching (304 if unchanged)
curl -X GET "http://localhost:8000/v1/models/instances" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H 'If-None-Match: "abc123def456"'
```
""",
)
async def list_instances(
    request: Request,
    response: Response,
    user: UserInfo = Depends(require_any_perms([USER_ME, ADMIN_ALL])),
    tenant_id: str | None = Query(None, description="Filter by tenant ID"),
    provider_id: str | None = Query(None, description="Filter by provider UUID"),
    loaded: bool | None = Query(None, description="Filter by loaded status"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    page_size: int = Query(100, ge=1, le=1000, description="Items per page"),
    page_token: str | None = Query(None, description="Pagination token"),
):
    """List model instances (auth required, non-admin OK)."""
    trace_id = _generate_trace_id()

    try:
        # Check if user is admin (can see all instances)
        user_is_admin = is_admin(user)

        # Non-admin users can only see enabled instances
        # Admin can see all instances and respect the enabled filter
        if user_is_admin:
            enabled_filter = enabled  # Respect explicit filter
        else:
            enabled_filter = True  # Force enabled=true for non-admin users

        # List instances
        instances, etag, next_token = model_instance_repo.list_instances(
            tenant_id=tenant_id,
            provider_id=provider_id,
            loaded=loaded,
            enabled=enabled_filter,
            page_size=page_size,
            page_token=page_token,
        )

        # Check ETag (304)
        if _check_etag(request, etag):
            _add_standard_headers(response, etag, trace_id)
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=dict(response.headers))

        # Add headers
        _add_standard_headers(response, etag, trace_id)

        # Record provenance
        record_provenance(
            actor="api",
            action="model.instances.list",
            resource="/models/instances",
            input={
                "filters": {"tenant_id": tenant_id, "provider_id": provider_id, "loaded": loaded, "enabled": enabled}
            },
            output={"count": len(instances)},
            meta={"user": user.sub},
        )

        return ListInstancesResponse(
            items=instances,
            total=len(instances),
            etag=etag,
            next_page_token=next_token,
        )

    except Exception as exc:
        logger.error(f"model.instances.list.failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"type": "about:blank", "title": "Internal Server Error", "detail": str(exc)},
        )


@dual_route(
    "post",
    "/instances",
    response_model=LoadInstanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Load/create model instance (Admin Only)",
    description="""
**POST /instances** – Register a new AI model instance (Admin only)

**Why we need this endpoint:**
- Platform admins need to add new AI models to the system as they become available
- Allows connecting to new model providers (OpenAI, Ollama, Azure, etc.) and specific model versions
- Without this, the platform would be limited to whatever models were pre-configured at deployment

**What it does:**
- Registers a new model instance in PostgreSQL with configuration details
- Marks the model as `loaded=true` and makes it available for use
- Records the model's capabilities (chat, embeddings, etc.) and provider information
- Invalidates the instance list cache to reflect the new model immediately

**Access:**
- **Admin only** – Requires `admin:all` permission
- Regular users with `user:me` permission will receive `403 Forbidden`

**Behavior:**
- **Idempotent**: Use the `Idempotency-Key` header to prevent duplicate creates
  - If replayed within 24 hours, returns `200 OK` with existing instance (not `201 Created`)
  - Without the key, duplicate POSTs create multiple instances with the same name
- Creates audit log entry for compliance tracking
- Automatically sets `loaded=true` on creation

**Responses:**
- `201 Created` – Model instance successfully registered (first time)
- `200 OK` – Idempotent replay detected, returning existing instance
- `400 Bad Request` – Invalid request data (missing fields, invalid provider_id, etc.)
- `401 Unauthorized` – Missing or invalid authentication token
- `403 Forbidden` – User is not an admin
- `409 Conflict` – Instance with same name already exists in tenant (without idempotency key)

**Examples:**
```bash
# Create a new Ollama model instance
curl -X POST "http://localhost:8000/v1/models/instances" \\
  -H "Authorization: Bearer $ADMIN_TOKEN" \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: create-llama-3.2-$(date +%s)" \\
  -d '{
    "name": "llama-3.2-3b",
    "provider_id": "ollama-local",
    "model_id": "llama3.2:3b-instruct",
    "tenant_id": null,
    "enabled": true,
    "capabilities": ["chat"]
  }'

# Create an OpenAI GPT-4 instance for a specific tenant
curl -X POST "http://localhost:8000/v1/models/instances" \\
  -H "Authorization: Bearer $ADMIN_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "gpt-4-turbo",
    "provider_id": "openai-azure",
    "model_id": "gpt-4-turbo-2024-04-09",
    "tenant_id": "tenant-123",
    "enabled": true,
    "capabilities": ["chat", "vision"]
  }'
```
""",
)
async def load_instance(
    request: Request,
    response: Response,
    req: LoadInstanceRequest,
    user: UserInfo = Depends(require_admin()),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Load/create model instance (admin required, idempotent)."""
    trace_id = _generate_trace_id()
    _generate_event_id()

    # Check if instance already exists (for idempotency)
    existing_instance = None
    if idempotency_key:
        # Check for existing instance with same name/tenant
        instances, _, _ = model_instance_repo.list_instances(
            tenant_id=req.tenant_id,
            page_size=1,
        )
        for inst in instances:
            if inst.get("instance_name") == req.instance_name:
                existing_instance = inst
                break

    try:
        # Create instance
        instance = model_instance_repo.create_instance(
            provider_id=req.provider_id,
            instance_name=req.instance_name,
            model_id=req.model_id,
            tenant_id=req.tenant_id,
            model_uri=req.model_uri,
            parameters=req.parameters,
            context_window=req.context_window,
            modalities=req.modalities,
            description=req.description,
            owner_sub=user.sub,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )

        # Determine if this was a replay
        was_replayed = existing_instance is not None and existing_instance.get("id") == instance["id"]

        # Add headers
        _add_standard_headers(response, instance["etag"], trace_id)

        # Check if this was idempotency replay
        if idempotency_key:
            response.headers["Idempotency-Replayed"] = "true" if was_replayed else "false"

        # Set correct status code
        if was_replayed:
            response.status_code = status.HTTP_200_OK

        # Record provenance
        record_provenance(
            actor="api",
            action="model.instance.load",
            resource=f"/models/instances/{instance['id']}",
            input=req.model_dump(),
            output={"instance_id": instance["id"]},
            meta={"user": user.sub, "trace_id": trace_id},
        )

        # AUTO-SET DEFAULT: If this is the first instance and no defaults exist, set it as default
        if not was_replayed and instance.get("enabled"):
            try:
                # Check if user has any default set (user, tenant, or global scope)
                user_default = user_default_repo.get_user_default(user_id=user.sub, tenant_id=req.tenant_id)

                # If no user default exists, set this instance as the user's default
                if not user_default:
                    logger.info(f"Auto-setting first instance {instance['id']} as user default for {user.sub}")
                    user_default_repo.set_user_default(
                        user_id=user.sub, tenant_id=req.tenant_id, instance_id=instance["id"]
                    )
            except Exception as auto_default_exc:
                # Don't fail the instance creation if auto-default fails
                logger.warning(f"Failed to auto-set default for instance {instance['id']}: {auto_default_exc}")

        return LoadInstanceResponse(
            id=instance["id"],
            instance_name=instance["instance_name"],
            provider_id=instance["provider_id"],
            model_id=instance["model_id"],
            enabled=instance["enabled"],
            loaded=instance["loaded"],
            created_at=instance["created_at"],
            etag=instance["etag"],
        )

    except ValueError as exc:
        logger.warning(f"model.instance.load.validation_failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "type": "about:blank",
                "title": "Bad Request",
                "detail": str(exc),
                "instance": "/models/instances",
            },
        )
    except Exception as exc:
        logger.error(f"model.instance.load.failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"type": "about:blank", "title": "Internal Server Error", "detail": str(exc)},
        )


@dual_route(
    "get",
    "/defaults",
    response_model=GetDefaultResponse,
    status_code=status.HTTP_200_OK,
    summary="Get default model with precedence resolution",
    description="""
**GET /defaults** – Get your default AI model (with smart fallback)

**Why we need this endpoint:**
- Applications need to know which model to use when the user doesn't specify one
- Users can have personal preferences, while organizations can set company-wide defaults
- Without this, every API call would require explicitly choosing a model, creating poor UX

**What it does:**
- Returns the default model for the current user with automatic precedence resolution
- Checks user's personal preference first, then organization default, then global system default
- Tells you which level was used via the `X-Default-Scope` header (`user`, `tenant`, or `global`)

**Access:**
- Any authenticated user with `user:me` permission
- Admins with `admin:all` can also access this endpoint

**Behavior:**
- **Precedence Order** (highest to lowest):
  1. **User default** – Your personal preference (specific to your user ID + organization)
  2. **Tenant default** – Your organization's company-wide default
  3. **Global default** – System-wide fallback (when no user/tenant default is set)
- **HTTP Caching**: Returns `ETag` header for efficient caching
  - Send `If-None-Match: "<etag>"` to get `304 Not Modified` when unchanged
  - ETag changes when the default model changes or when the scope changes
  - `304` responses have no body – use your cached version
- **Tenant Override**: Send `X-Tenant-Id` header to check a specific organization's defaults
- **Vary Header**: Response includes `Vary: Authorization, X-Tenant-Id` for correct cache behavior

**Responses:**
- `200 OK` – Default model found and returned (includes `X-Default-Scope` header)
- `304 Not Modified` – Content unchanged since last request (use cached version)
- `404 Not Found` – No default model configured at any level (set one via `PATCH /defaults`)
- `401 Unauthorized` – Missing or invalid authentication token
- `403 Forbidden` – User lacks required permissions

**Examples:**
```bash
# Get your current default model
curl -X GET "http://localhost:8000/v1/models/defaults" \\
  -H "Authorization: Bearer $USER_TOKEN"

# Response (200 OK):
# Headers:
#   X-Default-Scope: user
#   ETag: "43902c7efe456853"
#   Vary: Authorization, X-Tenant-Id
# Body:
# {
#   "chat": {
#     "instance_id": "6491b020-bbe3-47fe-991e-e7c21a15260c",
#     "name": "llama-3.2-3b",
#     "provider_id": "ollama-local",
#     "model_id": "llama3.2:3b-instruct"
#   },
#   "etag": "43902c7efe456853"
# }

# Use caching to save bandwidth (304 if unchanged)
curl -X GET "http://localhost:8000/v1/models/defaults" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H 'If-None-Match: "43902c7efe456853"'

# Response (304 Not Modified):
# Headers:
#   X-Default-Scope: user
#   ETag: "43902c7efe456853"
# Body: (empty - use cached version)

# Check a specific tenant's defaults (requires tenant access)
curl -X GET "http://localhost:8000/v1/models/defaults" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H "X-Tenant-Id: tenant-123"
```
""",
    operation_id="get_default_model",
    responses={
        200: {
            "description": "Default model configuration with scope indicator",
            "headers": {
                "X-Request-Id": {
                    "description": "Request correlation ID for tracing",
                    "schema": {"type": "string"},
                    "example": "req_a1b2c3d4e5f67890",
                },
                "X-Default-Scope": {
                    "description": "Scope level used for resolution (user, tenant, or global)",
                    "schema": {"type": "string", "enum": ["user", "tenant", "global"]},
                    "example": "user",
                },
                "ETag": {
                    "description": "Entity tag for cache validation (use in If-None-Match)",
                    "schema": {"type": "string"},
                    "example": '"def-v1-20250115-103000"',
                },
            },
        },
        304: {
            "description": "Not Modified - content unchanged since last request (use cached version)",
            "headers": {
                "X-Request-Id": {"schema": {"type": "string"}},
                "X-Default-Scope": {"schema": {"type": "string", "enum": ["user", "tenant", "global"]}},
                "ETag": {"schema": {"type": "string"}},
            },
        },
        404: {
            "description": "Not Found - no default model configured",
            "content": {
                "application/json": {
                    "example": {
                        "type": "about:blank",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "No default model configured",
                        "instance": "/v1/admin/models/defaults",
                    }
                }
            },
        },
        500: {"description": "Internal Server Error - unexpected server-side error"},
    },
)
async def get_default(
    request: Request,
    response: Response,
    user: UserInfo = Depends(require_any_perms([USER_ME, ADMIN_ALL])),
    if_none_match: str | None = Header(
        None, alias="If-None-Match", description="ETag from previous response for cache validation"
    ),
    x_tenant_id: str | None = Header(
        None, alias="X-Tenant-Id", description="Tenant ID for scoped defaults (null=global)"
    ),
):
    """Get default model with precedence resolution (user → tenant → global).

    Resolution order:
    1. User default (user_id + tenant_id) - from user_default_models table
    2. Tenant default (tenant_id only) - from model_instances table
    3. Global default (no tenant_id) - from model_instances table
    4. 404 Not Found - no default at any level

    Returns X-Default-Scope header indicating which scope was used.
    """
    trace_id = _generate_trace_id()

    try:
        # Determine effective tenant_id
        tenant_id = x_tenant_id if x_tenant_id is not None else getattr(user, "tenant_id", None)

        default = None
        scope_used = None

        # 1. Try user default first (highest precedence)
        if user.sub:
            try:
                user_default = user_default_repo.get_user_default(user_id=user.sub, tenant_id=tenant_id)
                if user_default and user_default.get("instance_id"):
                    default = user_default
                    scope_used = "user"
                    logger.debug(f"model.defaults.get.user_hit: instance_id={default['instance_id']}")
            except Exception as user_exc:
                logger.warning(f"model.defaults.get.user_lookup_failed: {user_exc}")
                # Continue to tenant/global fallback

        # 2. Try tenant default if no user default
        if not default and tenant_id:
            try:
                tenant_default_config = model_instance_repo.get_default(scope="tenant", tenant_id=tenant_id)
                if tenant_default_config:
                    tenant_default = tenant_default_config.to_dict()
                else:
                    tenant_default = None

                if tenant_default and tenant_default.get("instance_id"):
                    default = tenant_default
                    scope_used = "tenant"
                    logger.debug(f"model.defaults.get.tenant_hit: instance_id={default['instance_id']}")
            except Exception as tenant_exc:
                logger.warning(f"model.defaults.get.tenant_lookup_failed: {tenant_exc}")
                # Continue to global fallback

        # 3. Try global default as fallback
        if not default:
            try:
                global_default_config = model_instance_repo.get_default(scope="global", tenant_id=None)
                if global_default_config:
                    global_default = global_default_config.to_dict()
                else:
                    global_default = None

                if global_default and global_default.get("instance_id"):
                    default = global_default
                    scope_used = "global"
                    logger.debug(f"model.defaults.get.global_hit: instance_id={default['instance_id']}")
            except Exception as global_exc:
                logger.warning(f"model.defaults.get.global_lookup_failed: {global_exc}")

        # 4. No default found at any level
        if not default or not scope_used:
            logger.info(
                "model.defaults.get.not_found",
                extra={
                    "user_id": user.sub,
                    "tenant_id": tenant_id,
                    "trace_id": trace_id,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "type": "about:blank",
                    "title": "Not Found",
                    "detail": "No default model configured at user, tenant, or global scope",
                    "instance": "/v1/models/defaults",
                },
            )

        # Validate normalized response structure
        required_keys = ["instance_id", "instance_name", "provider_id", "model_id"]
        missing_keys = [k for k in required_keys if k not in default]
        if missing_keys:
            logger.error(
                f"model.defaults.get.invalid_response: missing keys {missing_keys}",
                extra={"scope": scope_used, "default": default},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "type": "about:blank",
                    "title": "Internal Server Error",
                    "detail": f"Invalid default model data: missing {', '.join(missing_keys)}",
                    "instance": "/v1/models/defaults",
                },
            )

        # Compute ETag from normalized payload + scope (so user/tenant/global produce different ETags)
        etag_data = f"{scope_used}:{default['instance_id']}:{default['instance_name']}:{default['provider_id']}:{default['model_id']}"
        etag = hashlib.sha256(etag_data.encode()).hexdigest()[:16]

        # Check ETag (304)
        if _check_etag(request, etag):
            response.headers["X-Request-Id"] = trace_id
            response.headers["X-Default-Scope"] = scope_used
            response.headers["ETag"] = f'"{etag}"'
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            response.headers["Vary"] = "Authorization, X-Tenant-Id"

            logger.info(
                "model.defaults.get.cache_hit",
                extra={
                    "scope": scope_used,
                    "instance_id": default["instance_id"],
                    "user_id": user.sub,
                    "tenant_id": tenant_id,
                    "etag": etag,
                    "trace_id": trace_id,
                },
            )

            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=dict(response.headers))

        # Add headers (including X-Default-Scope)
        _add_standard_headers(response, etag, trace_id)
        response.headers["X-Default-Scope"] = scope_used
        response.headers["Vary"] = "Authorization, X-Tenant-Id"

        # Log successful retrieval with telemetry
        logger.info(
            "model.defaults.get.success",
            extra={
                "scope": scope_used,
                "instance_id": default["instance_id"],
                "instance_name": default["instance_name"],
                "user_id": user.sub,
                "tenant_id": tenant_id,
                "etag": etag,
                "trace_id": trace_id,
            },
        )

        # Record provenance
        record_provenance(
            actor="api",
            action="model.defaults.get",
            resource="/models/defaults",
            input={"scope": scope_used, "tenant_id": tenant_id},
            output={"instance_id": default["instance_id"], "scope": scope_used},
            meta={"user": user.sub, "trace_id": trace_id},
        )

        return GetDefaultResponse(
            chat={
                "instance_id": default["instance_id"],
                "name": default["instance_name"],
                "provider_id": default["provider_id"],
                "model_id": default["model_id"],
            },
            etag=etag,
        )

    except HTTPException:
        raise
    except KeyError as key_exc:
        # Handle missing required keys gracefully
        logger.error(f"model.defaults.get.key_error: {key_exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "type": "about:blank",
                "title": "Not Found",
                "detail": "No default model configured at user, tenant, or global scope",
                "instance": "/v1/models/defaults",
            },
        )
    except Exception as exc:
        logger.error(f"model.defaults.get.failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"type": "about:blank", "title": "Internal Server Error", "detail": str(exc)},
        )


@dual_route(
    "patch",
    "/defaults",
    response_model=SetDefaultResponse,
    status_code=status.HTTP_200_OK,
    summary="Set default model with scope support",
    description="""
**PATCH /defaults** – Set your default AI model (or organization/global defaults)

**Why we need this endpoint:**
- Users need a way to set their personal default model preference
- Admins need to set organization-wide defaults for all team members
- Platform operators need to set global fallback defaults for all users
- Without this, users would have to specify a model on every single API call

**What it does:**
- Sets the default model at one of three scope levels: user (personal), tenant (organization), or global (system-wide)
- Validates that the model instance exists and is enabled before setting it
- Invalidates cached defaults so the change takes effect immediately

**Access:**
- **User scope**: Any authenticated user with `user:me` can set their personal default
- **Tenant scope**: Admins with `admin:all` can set organization-wide defaults
- **Global scope**: Admins with `admin:all` can set system-wide fallback defaults

**Behavior:**
- **Scope Selection**: Use the `X-Default-Scope` header to choose scope level:
  - `user` (default) – Your personal preference (user ID + tenant ID)
  - `tenant` – Organization-wide default for all users in your tenant (admin only)
  - `global` – System-wide fallback for all users (admin only)
- **Tenant ID**: For `tenant` scope, send `X-Tenant-Id` header with the tenant identifier
- **Validation**: Checks that the instance exists and is enabled (disabled instances return `409 Conflict`)
- **Cache Invalidation**: ETag changes immediately after update (GET /defaults reflects new default)
- **Multiple Formats Supported**:
  - **Preferred**: `{"chat": {"instance_id": "<uuid>"}}` (fastest, no lookup)
  - **Legacy**: `{"chat": {"name": "<instance-name>"}}` (requires database lookup)
  - **Deprecated**: `{"name": "<instance-name>"}` (top-level, use chat.instance_id instead)

**Responses:**
- `200 OK` – Default model updated successfully (returns instance details and confirmed scope)
- `400 Bad Request` – Invalid scope, missing headers, or semantic errors
- `401 Unauthorized` – Missing or invalid authentication token
- `403 Forbidden` – User lacks permissions for requested scope (e.g., non-admin trying tenant/global)
- `404 Not Found` – Instance not found by ID or name
- `409 Conflict` – Instance exists but is disabled (cannot set disabled models as defaults)
- `422 Unprocessable Entity` – Schema validation errors (unknown fields, missing required fields)

**Examples:**
```bash
# Set your personal default (user scope)
curl -X PATCH "http://localhost:8000/v1/models/defaults" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"chat": {"instance_id": "6491b020-bbe3-47fe-991e-e7c21a15260c"}}'

# Response (200 OK):
# {
#   "chat": {
#     "instance_id": "6491b020-bbe3-47fe-991e-e7c21a15260c",
#     "instance_name": "llama-3.2-3b",
#     "provider_id": "ollama-local",
#     "model_id": "llama3.2:3b-instruct"
#   },
#   "scope": "user"
# }

# Admin: Set organization-wide default (tenant scope)
curl -X PATCH "http://localhost:8000/v1/models/defaults" \\
  -H "Authorization: Bearer $ADMIN_TOKEN" \\
  -H "Content-Type: application/json" \\
  -H "X-Default-Scope: tenant" \\
  -H "X-Tenant-Id: tenant-123" \\
  -d '{"chat": {"instance_id": "abc-def-ghi"}}'

# Admin: Set global system fallback (global scope)
curl -X PATCH "http://localhost:8000/v1/models/defaults" \\
  -H "Authorization: Bearer $ADMIN_TOKEN" \\
  -H "Content-Type: application/json" \\
  -H "X-Default-Scope: global" \\
  -d '{"chat": {"instance_id": "xyz-123-456"}}'

# Legacy format: Set default by instance name (requires lookup)
curl -X PATCH "http://localhost:8000/v1/models/defaults" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"chat": {"name": "llama-3.2-3b"}}'

# Error example: Non-admin trying to set tenant default (403 Forbidden)
curl -X PATCH "http://localhost:8000/v1/models/defaults" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H "X-Default-Scope: tenant" \\
  -d '{"chat": {"instance_id": "..."}}'
# Response: {"detail": "Permission denied: tenant scope requires admin privileges"}
```

**IMPORTANT:** Send the raw JSON from the examples above. DO NOT wrap in `summary`/`description`/`value` fields.
""",
    operation_id="set_default_model",
    responses={
        200: {
            "description": "Default model updated successfully at requested scope",
            "headers": {
                "X-Request-Id": {
                    "description": "Request correlation ID for tracing",
                    "schema": {"type": "string"},
                    "example": "req_a1b2c3d4e5f67890",
                },
                "X-Default-Scope": {
                    "description": "Confirmed scope level that was set (user, tenant, or global)",
                    "schema": {"type": "string", "enum": ["user", "tenant", "global"]},
                    "example": "user",
                },
                "ETag": {
                    "description": "Entity tag for defaults cache validation",
                    "schema": {"type": "string"},
                    "example": '"def-v1-20250115-103000"',
                },
            },
        },
        400: {
            "description": "Bad Request - semantic/business logic error (e.g., instance disabled, invalid format)",
            "content": {
                "application/json": {
                    "example": {
                        "type": "about:blank",
                        "title": "Bad Request",
                        "status": 400,
                        "detail": "Must provide chat.instance_id (preferred) or chat.name (legacy)",
                        "instance": "/v1/admin/models/defaults",
                    }
                }
            },
        },
        401: {"description": "Unauthorized - missing or invalid authentication token"},
        403: {"description": "Forbidden - insufficient permissions (requires admin:all)"},
        404: {
            "description": "Not Found - instance does not exist",
            "content": {
                "application/json": {
                    "example": {
                        "type": "about:blank",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Instance not found: gpt-4o-production",
                        "instance": "/v1/admin/models/defaults",
                    }
                }
            },
        },
        409: {
            "description": "Conflict - instance exists but is disabled or in invalid state",
            "content": {
                "application/json": {
                    "example": {
                        "type": "about:blank",
                        "title": "Conflict",
                        "status": 409,
                        "detail": "Instance is disabled and cannot be set as default",
                        "instance": "/v1/admin/models/defaults",
                    }
                }
            },
        },
        422: {
            "description": "Unprocessable Entity - schema validation error (unknown fields, type mismatch)",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "type": "extra_forbidden",
                                "loc": ["body", "summary"],
                                "msg": "Extra inputs are not permitted",
                                "input": "By instance UUID",
                            }
                        ]
                    }
                }
            },
        },
        500: {"description": "Internal Server Error - unexpected server-side error"},
    },
)
async def set_default(
    request: Request,
    response: Response,
    req: SetDefaultRequest = Body(
        ...,
        openapi_examples={
            "by_instance_id": {
                "summary": "By instance UUID (preferred)",
                "description": "Recommended format using instance_id for explicit selection",
                "value": {"chat": {"instance_id": "6491b020-bbe3-47fe-991e-e7c21a15260c"}},
            },
            "by_name_legacy": {
                "summary": "By instance name (legacy)",
                "description": "Legacy format using name for backward compatibility",
                "value": {"chat": {"name": "gpt-4o-production"}},
            },
            "name_top_level_deprecated": {
                "summary": "Top-level name (deprecated)",
                "description": "Deprecated: Use chat.instance_id instead",
                "value": {"name": "gpt-4o-production"},
            },
        },
    ),
    user: UserInfo = Depends(get_current_user),
    x_default_scope: str | None = Header(
        None,
        alias="X-Default-Scope",
        description="Scope level: 'user' (default), 'tenant' (admin), or 'global' (admin)",
    ),
    x_tenant_id: str | None = Header(
        None, alias="X-Tenant-Id", description="Tenant ID for scoped defaults (null=global)"
    ),
):
    """Set default model with scope support.

    **Scope Permissions**:
    - `user` (default): Requires `user:me` (any authenticated user). Sets user's personal default.
    - `tenant`: Requires `admin:all`. Sets tenant-wide default.
    - `global`: Requires `admin:all`. Sets global default.

    Users can only set their own defaults. Admins can set defaults at any scope.
    """
    trace_id = _generate_trace_id()

    try:
        # Determine scope (default to 'user')
        scope = (x_default_scope or "user").lower()
        if scope not in ["user", "tenant", "global"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "type": "about:blank",
                    "title": "Bad Request",
                    "detail": f"Invalid X-Default-Scope: '{x_default_scope}'. Must be 'user', 'tenant', or 'global'",
                    "instance": "/v1/models/defaults",
                },
            )

        # Check permissions for requested scope
        if not can_set_default_scope(user, scope):
            # Determine required permission
            if scope == "user":
                required = f"'{USER_ME}' (any authenticated user)"
            elif scope == "tenant":
                required = f"'{ADMIN_ALL}' (admin only)"
            else:  # global
                required = f"'{ADMIN_ALL}' (admin only)"

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "type": "about:blank",
                    "title": "Forbidden",
                    "detail": f"Insufficient permissions to set default at '{scope}' scope. Required: {required}",
                    "instance": "/v1/models/defaults",
                },
            )

        # Extract instance_id from request
        instance_id = None
        instance_name = None

        if req.chat:
            instance_id = req.chat.get("instance_id")
            instance_name = req.chat.get("name")
        elif req.instance_id:
            instance_id = req.instance_id
        elif req.name:
            instance_name = req.name

        if not instance_id and not instance_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "type": "about:blank",
                    "title": "Bad Request",
                    "detail": "Must provide chat.instance_id (preferred) or chat.name (legacy)",
                    "instance": "/v1/models/defaults",
                },
            )

        # If name provided, lookup instance
        if instance_name and not instance_id:
            # List instances and find by name
            instances, _, _ = model_instance_repo.list_instances(page_size=1000)
            matching = [i for i in instances if i.get("instance_name") == instance_name]
            if not matching:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "type": "about:blank",
                        "title": "Not Found",
                        "detail": f"Instance not found: {instance_name}",
                        "instance": "/v1/models/defaults",
                    },
                )
            instance_id = matching[0]["id"]

            # Check if instance is enabled
            if not matching[0].get("enabled", True):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "type": "about:blank",
                        "title": "Conflict",
                        "detail": f"Instance '{instance_name}' is disabled and cannot be set as default",
                        "instance": "/v1/models/defaults",
                    },
                )

        # Verify instance exists if we have instance_id directly
        if instance_id:
            instance = model_instance_repo.get_instance(instance_id)
            if not instance:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "type": "about:blank",
                        "title": "Not Found",
                        "detail": f"Instance not found: {instance_id}",
                        "instance": "/v1/models/defaults",
                    },
                )
            # Check if instance is enabled
            if not instance.get("enabled", True):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "type": "about:blank",
                        "title": "Conflict",
                        "detail": f"Instance '{instance.get('instance_name', instance_id)}' is disabled and cannot be set as default",
                        "instance": "/v1/models/defaults",
                    },
                )

        # Set default based on scope
        if scope == "user":
            # Set user-level default (user_default_models table)
            tenant_id = x_tenant_id if x_tenant_id is not None else getattr(user, "tenant_id", None)
            default = user_default_repo.set_user_default(
                user_id=user.sub, instance_id=instance_id, tenant_id=tenant_id, created_by=user.sub
            )
        elif scope == "tenant":
            # Set tenant-level default (model_instances table)
            tenant_id = x_tenant_id if x_tenant_id is not None else getattr(user, "tenant_id", None)
            if not tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "type": "about:blank",
                        "title": "Bad Request",
                        "detail": "Tenant scope requires X-Tenant-Id header or user.tenant_id",
                        "instance": "/v1/models/defaults",
                    },
                )
            default = model_instance_repo.set_default(
                instance_id=instance_id,
                scope="tenant",
                tenant_id=tenant_id,
                owner_sub=user.sub,
            )
        else:  # global
            # Set global default (model_instances table, tenant_id=None)
            default = model_instance_repo.set_default(
                instance_id=instance_id,
                scope="global",
                tenant_id=None,
                owner_sub=user.sub,
            )

        # ──────────────────────────────────────────────────────────────────
        # Invalidate DMR cache after successful default update
        # ──────────────────────────────────────────────────────────────────
        try:
            from src.services.default_model_resolver import DefaultModelResolver

            dmr = DefaultModelResolver()
            await dmr.invalidate_cache(
                scope=scope,
                tenant_id=tenant_id if scope == "tenant" else None,
                reason=f"Default updated via PATCH /defaults by {user.sub}",
            )
            logger.info(
                f"dmr.cache.invalidated",
                extra={
                    "scope": scope,
                    "tenant_id": tenant_id if scope == "tenant" else None,
                    "instance_id": instance_id,
                    "user": user.sub,
                },
            )
        except Exception as cache_exc:
            # Cache invalidation failure should NOT block the response
            # DMR will fall back to PostgreSQL on next get_default_model() call
            logger.warning(
                f"dmr.cache.invalidation_failed: {cache_exc}",
                extra={"scope": scope, "tenant_id": tenant_id if scope == "tenant" else None},
                exc_info=True,
            )

        # Add headers (including X-Default-Scope to confirm scope used)
        _add_standard_headers(response, default.get("etag"), trace_id)
        response.headers["X-Default-Scope"] = scope

        # Record provenance
        record_provenance(
            actor="api",
            action="model.defaults.set",
            resource="/v1/models/defaults",
            input={"instance_id": instance_id, "scope": scope, "tenant_id": x_tenant_id},
            output={"instance_id": default["instance_id"], "scope": scope},
            meta={"user": user.sub, "trace_id": trace_id},
        )

        return SetDefaultResponse(
            ok=True,
            message=f"Default model updated successfully at '{scope}' scope",
            instance_id=default["instance_id"],
            instance_name=default["instance_name"],
        )

    except ValueError as exc:
        logger.warning(f"model.defaults.set.validation_failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "type": "about:blank",
                "title": "Bad Request",
                "detail": str(exc),
                "instance": "/v1/admin/models/defaults",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"model.defaults.set.failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "type": "about:blank",
                "title": "Internal Server Error",
                "detail": str(exc),
                "instance": "/v1/admin/models/defaults",
            },
        )


@dual_route(
    "get",
    "/instances/{instance_id}",
    response_model=InstanceDetail,
    status_code=status.HTTP_200_OK,
    summary="Get model instance by ID",
    description="""
**GET /instances/{instance_id}** – View detailed information about a specific AI model

**Why we need this endpoint:**
- Applications need detailed model specifications before making API calls
- Users want to know a model's capabilities (chat, vision, embeddings, etc.) and configuration
- Developers need to inspect model parameters, context window sizes, and provider settings
- Without this, users would have to guess model capabilities or maintain separate documentation

**What it does:**
- Returns complete details for a single model instance by its UUID
- Shows capabilities, parameters, modalities, provider info, tenant scope, and enabled status
- Includes metadata like creation time, loaded status, and configuration settings

**Access:**
- Any authenticated user with `user:me` permission
- Admins with `admin:all` can also access this endpoint

**Behavior:**
- **HTTP Caching**: Returns `ETag` header for efficient caching
  - Send `If-None-Match: "<etag>"` to get `304 Not Modified` when unchanged
  - `304` responses have no body – use your cached version
- **Non-admin users**: Can only see enabled instances
- **Admin users**: Can see all instances including disabled ones

**Responses:**
- `200 OK` – Instance details retrieved successfully (includes ETag header)
- `304 Not Modified` – Content unchanged since last request (use cached version)
- `401 Unauthorized` – Missing or invalid authentication token
- `403 Forbidden` – User lacks required permissions
- `404 Not Found` – Instance does not exist with given UUID

**Examples:**
```bash
# Get details for a specific model instance
curl -X GET "http://localhost:8000/v1/models/instances/6491b020-bbe3-47fe-991e-e7c21a15260c" \\
  -H "Authorization: Bearer $USER_TOKEN"

# Response (200 OK):
# Headers:
#   ETag: "inst-v1-a1b2c3d4-20250115"
# Body:
# {
#   "id": "6491b020-bbe3-47fe-991e-e7c21a15260c",
#   "instance_name": "llama-3.2-3b",
#   "provider_id": "ollama-local",
#   "model_id": "llama3.2:3b-instruct",
#   "tenant_id": null,
#   "enabled": true,
#   "loaded": true,
#   "capabilities": ["chat"],
#   "modalities": ["text"],
#   "context_window": 8192,
#   "created_at": "2025-01-15T10:30:00Z",
#   "etag": "inst-v1-a1b2c3d4-20250115"
# }

# Use caching to save bandwidth (304 if unchanged)
curl -X GET "http://localhost:8000/v1/models/instances/6491b020-bbe3-47fe-991e-e7c21a15260c" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H 'If-None-Match: "inst-v1-a1b2c3d4-20250115"'

# Response (304 Not Modified):
# Headers:
#   ETag: "inst-v1-a1b2c3d4-20250115"
# Body: (empty - use cached version)

# Error example: Instance does not exist (404 Not Found)
curl -X GET "http://localhost:8000/v1/models/instances/00000000-0000-0000-0000-000000000000" \\
  -H "Authorization: Bearer $USER_TOKEN"
# Response: {"type": "about:blank", "title": "Not Found", "status": 404, ...}
```
""",
    operation_id="get_model_instance",
    responses={
        200: {
            "description": "Instance details retrieved successfully",
            "headers": {
                "X-Request-Id": {"description": "Request correlation ID for tracing", "schema": {"type": "string"}},
                "ETag": {
                    "description": "Entity tag for cache validation (use in If-None-Match)",
                    "schema": {"type": "string"},
                    "example": '"inst-v1-a1b2c3d4-20250115"',
                },
            },
        },
        304: {
            "description": "Not Modified - content unchanged since last request (use cached version)",
            "headers": {"X-Request-Id": {"schema": {"type": "string"}}, "ETag": {"schema": {"type": "string"}}},
        },
        404: {
            "description": "Not Found - instance does not exist",
            "content": {
                "application/json": {
                    "example": {
                        "type": "about:blank",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Instance not found: a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "instance": "/v1/admin/models/instances/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    }
                }
            },
        },
        500: {"description": "Internal Server Error - unexpected server-side error"},
    },
)
async def get_instance(
    instance_id: str,
    request: Request,
    response: Response,
    user: UserInfo = Depends(require_any_perms([USER_ME, ADMIN_ALL])),
    if_none_match: str | None = Header(
        None, alias="If-None-Match", description="ETag from previous response for cache validation"
    ),
):
    """Get model instance (authenticated users with user:me)."""
    trace_id = _generate_trace_id()

    try:
        # Get instance
        instance = model_instance_repo.get_instance(instance_id)

        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "type": "about:blank",
                    "title": "Not Found",
                    "detail": f"Instance not found: {instance_id}",
                    "instance": f"/v1/admin/models/instances/{instance_id}",
                },
            )

        # Check if user is admin
        user_is_admin = is_admin(user)

        # Non-admin users cannot see disabled instances (return 404 to hide existence)
        if not instance.get("enabled", True) and not user_is_admin:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "type": "about:blank",
                    "title": "Not Found",
                    "detail": f"Instance not found: {instance_id}",
                    "instance": f"/v1/admin/models/instances/{instance_id}",
                },
            )

        etag = instance.get("etag", "")

        # Check ETag (304)
        if _check_etag(request, etag):
            _add_standard_headers(response, etag, trace_id)
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=dict(response.headers))

        # Add headers
        _add_standard_headers(response, etag, trace_id)

        # Record provenance
        record_provenance(
            actor="api",
            action="model.instance.get",
            resource=f"/models/instances/{instance_id}",
            input={"instance_id": instance_id},
            output={"found": True},
            meta={"user": user.sub},
        )

        return instance

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"model.instance.get.failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"type": "about:blank", "title": "Internal Server Error", "detail": str(exc)},
        )


@dual_route(
    "delete",
    "/instances/{instance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete model instance (Admin Only)",
    description="""
**DELETE /instances/{instance_id}** – Remove an AI model from the platform (Admin only)

**Why we need this endpoint:**
- Admins need to decommission outdated or unused model instances
- Platform operators need to clean up test models or free resources
- Organizations need to remove models that are no longer needed or supported
- Without this, unused models would accumulate indefinitely, cluttering the instance list

**What it does:**
- Marks the model instance as unloaded or fully removes it from the database
- Acquires an exclusive lock to prevent concurrent operations (race condition protection)
- Invalidates all related caches (instance list, defaults) to reflect the deletion immediately
- Returns `204 No Content` on successful deletion (empty response body)

**Access:**
- **Admin only** – Requires `admin:all` permission
- Regular users with `user:me` permission will receive `403 Forbidden`

**Behavior:**
- **Idempotent**: Deleting an already-deleted instance returns `404 Not Found` (not an error state)
- **Locking**: Acquires exclusive lock during deletion to prevent race conditions
- **Cache Invalidation**: Clears instance list cache and any defaults that referenced this instance
- **Audit Trail**: Records deletion event in audit log for compliance tracking

**Responses:**
- `204 No Content` – Instance successfully deleted (empty response body)
- `401 Unauthorized` – Missing or invalid authentication token
- `403 Forbidden` – User is not an admin
- `404 Not Found` – Instance does not exist with given UUID (already deleted or never existed)
- `500 Internal Server Error` – Unexpected server-side error during deletion

**Examples:**
```bash
# Admin: Delete a model instance
curl -X DELETE "http://localhost:8000/v1/models/instances/6491b020-bbe3-47fe-991e-e7c21a15260c" \\
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Response (204 No Content):
# Headers:
#   (no special headers)
# Body: (empty)

# Error example: Non-admin user trying to delete (403 Forbidden)
curl -X DELETE "http://localhost:8000/v1/models/instances/6491b020-bbe3-47fe-991e-e7c21a15260c" \\
  -H "Authorization: Bearer $USER_TOKEN"
# Response: {"type": "about:blank", "title": "Forbidden", "status": 403, ...}

# Error example: Instance does not exist (404 Not Found)
curl -X DELETE "http://localhost:8000/v1/models/instances/00000000-0000-0000-0000-000000000000" \\
  -H "Authorization: Bearer $ADMIN_TOKEN"
# Response: {"type": "about:blank", "title": "Not Found", "status": 404, ...}

# Idempotent: Deleting the same instance twice returns 404 on second attempt
curl -X DELETE "http://localhost:8000/v1/models/instances/abc-123-def" \\
  -H "Authorization: Bearer $ADMIN_TOKEN"
# First call: 204 No Content
# Second call: 404 Not Found
```
""",
)
async def delete_instance(
    instance_id: str,
    response: Response,
    user: UserInfo = Depends(require_admin()),
):
    """Delete model instance (admin required, with lock)."""
    trace_id = _generate_trace_id()

    try:
        # Acquire lock
        if not model_instance_repo.acquire_instance_lock(instance_id, ttl=15):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "type": "about:blank",
                    "title": "Conflict",
                    "detail": "Instance operation already in progress (lock held)",
                    "instance": f"/models/instances/{instance_id}",
                },
            )

        try:
            # Delete instance
            deleted = model_instance_repo.delete_instance(
                instance_id=instance_id,
                owner_sub=user.sub,
                trace_id=trace_id,
            )

            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "type": "about:blank",
                        "title": "Not Found",
                        "detail": f"Instance not found: {instance_id}",
                        "instance": f"/models/instances/{instance_id}",
                    },
                )

            # Add headers
            _add_standard_headers(response, None, trace_id)

            # Record provenance
            record_provenance(
                actor="api",
                action="model.instance.delete",
                resource=f"/models/instances/{instance_id}",
                input={"instance_id": instance_id},
                output={"deleted": True},
                meta={"user": user.sub, "trace_id": trace_id},
            )

            return Response(status_code=status.HTTP_204_NO_CONTENT, headers=dict(response.headers))

        finally:
            # Always release lock
            model_instance_repo.release_instance_lock(instance_id)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"model.instance.delete.failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"type": "about:blank", "title": "Internal Server Error", "detail": str(exc)},
        )


@dual_route(
    "post",
    "/instances/{instance_id}/tests",
    response_model=TestInstanceResponse,
    summary="Test model instance",
    description="""
**POST /instances/{instance_id}/tests** – Send a test prompt to an AI model

**Why we need this endpoint:**
- Users need to verify that a model works before integrating it into their application
- Developers want to test model behavior with different prompts and parameters
- Teams need to compare model outputs side-by-side to choose the best one
- Without this, users would have to build a full integration just to see if a model works

**What it does:**
- Sends a chat completion request to the model provider using the instance's configuration
- Returns the generated text along with observability metadata (provider, latency, parameters used)
- Validates that the instance exists, is enabled, and is loaded before sending the request
- Provides a quick "smoke test" to confirm connectivity and basic functionality

**Access:**
- Any authenticated user with `user:me` permission
- Admins with `admin:all` can also access this endpoint
- Users can only test **enabled** model instances

**Behavior:**
- **Default Parameters**: Uses sensible defaults if not specified:
  - `temperature=0.0` (deterministic output for testing)
  - `max_tokens=64` (short response to avoid long waits)
  - `stop=["\n\n", "\\`\\`\\`", "---"]` (stop at natural boundaries)
- **Timeout**: 60-second read timeout to accommodate slower models
- **Demo Mode**: Returns "pong" response for "ping" prompt when no providers are registered (testing mode)
- **Observability**: Response includes provider ID, latency, token count, and parameters used
- **Non-admin users**: Can only test enabled instances (disabled instances return `403 Forbidden`)

**Responses:**
- `200 OK` – Test completed successfully (returns generated text and metadata)
- `400 Bad Request` – Invalid request (missing prompt, invalid parameters, etc.)
- `401 Unauthorized` – Missing or invalid authentication token
- `403 Forbidden` – User lacks permissions or instance is disabled
- `404 Not Found` – Instance does not exist with given UUID
- `500 Internal Server Error` – Provider error or unexpected server-side failure

**Examples:**
```bash
# Test a model with a simple factual question (deterministic)
curl -X POST "http://localhost:8000/v1/models/instances/6491b020-bbe3-47fe-991e-e7c21a15260c/tests" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "Explain quantum computing in one sentence.",
    "temperature": 0.0,
    "max_tokens": 64
  }'

# Response (200 OK):
# {
#   "output": "Quantum computing uses quantum bits (qubits) that can exist in multiple states simultaneously, enabling massively parallel computation for certain problems.",
#   "provider_id": "ollama-local",
#   "model_id": "llama3.2:3b-instruct",
#   "latency_ms": 1523,
#   "tokens": 28,
#   "parameters": {
#     "temperature": 0.0,
#     "max_tokens": 64,
#     "stop": ["\n\n", "```", "---"]
#   }
# }

# Test a creative task with higher temperature
curl -X POST "http://localhost:8000/v1/models/instances/6491b020-bbe3-47fe-991e-e7c21a15260c/tests" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "Write a haiku about programming.",
    "temperature": 0.7,
    "max_tokens": 100
  }'

# Short answer with custom stop sequence
curl -X POST "http://localhost:8000/v1/models/instances/6491b020-bbe3-47fe-991e-e7c21a15260c/tests" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "What is the capital of France?",
    "temperature": 0.0,
    "max_tokens": 32,
    "stop": ["\n\n"]
  }'

# Error example: Instance is disabled (403 Forbidden)
curl -X POST "http://localhost:8000/v1/models/instances/disabled-model-uuid/tests" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"prompt": "Hello"}'
# Response: {"type": "about:blank", "title": "Forbidden", "status": 403, ...}

# Demo mode: "ping" test (when no providers configured)
curl -X POST "http://localhost:8000/v1/models/instances/any-instance-id/tests" \\
  -H "Authorization: Bearer $USER_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"prompt": "ping"}'
# Response: {"output": "pong", "provider_id": "demo", ...}
```
""",
)
async def test_instance(
    instance_id: str,
    response: Response,
    user: UserInfo = Depends(require_any_perms([USER_ME, ADMIN_ALL])),
    req: TestInstanceRequest = Body(
        ...,
        openapi_examples={
            "quantum_computing": {
                "summary": "Factual query (deterministic)",
                "description": "Ask a specific factual question with deterministic output",
                "value": {"prompt": "Explain quantum computing in one sentence.", "temperature": 0.0, "max_tokens": 64},
            },
            "capital_question": {
                "summary": "Short answer with custom stop",
                "description": "Simple question with shorter token limit and custom stop sequence",
                "value": {
                    "prompt": "What is the capital of France?",
                    "temperature": 0.0,
                    "max_tokens": 32,
                    "stop": ["\n\n"],
                },
            },
            "creative_haiku": {
                "summary": "Creative task (non-deterministic)",
                "description": "Generate creative content with higher temperature",
                "value": {
                    "prompt": "Write a haiku about programming.",
                    "temperature": 0.7,
                    "max_tokens": 100,
                    "stop": None,
                },
            },
        },
    ),
):
    """Test model instance with prompt (authenticated users with user:me)."""
    import time

    from src.utils.test_helpers import (
        estimate_usage,
        extract_text_from_response,
        get_stop_sequences,
        hash_prompt,
        mark_warmed,
        normalize_request_to_messages,
        should_warmup,
        truncate_to_sentence,
    )

    trace_id = _generate_trace_id()
    event_id = _generate_event_id()
    start_time = time.perf_counter()  # Track latency

    # Validate input: need either prompt or messages
    if not req.prompt and not req.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "type": "about:blank",
                "title": "Bad Request",
                "detail": "Either 'prompt' or 'messages' must be provided",
            },
        )

    try:
        # Get instance
        instance = model_instance_repo.get_instance(instance_id)

        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "type": "about:blank",
                    "title": "Not Found",
                    "detail": f"Instance not found: {instance_id}",
                    "instance": f"/models/instances/{instance_id}/tests",
                },
            )

        # Check if instance is enabled (required for testing)
        if not instance.get("enabled", True):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "type": "about:blank",
                    "title": "Conflict",
                    "detail": "Instance is disabled and cannot be tested",
                    "instance": f"/models/instances/{instance_id}/tests",
                },
            )

        # Check if loaded
        if not instance.get("loaded"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "type": "about:blank",
                    "title": "Conflict",
                    "detail": "Instance not loaded",
                    "instance": f"/models/instances/{instance_id}/tests",
                },
            )

        model_id = instance["model_id"]
        provider_id = instance.get("provider_id")

        # Normalize request to chat messages
        messages = normalize_request_to_messages(
            prompt=req.prompt,
            messages=req.messages,
            model_id=model_id,
            one_sentence=req.one_sentence,
            no_system=req.no_system,
            format_hint=req.format_hint,
        )

        # Get smart stop sequences
        stop_sequences = get_stop_sequences(
            one_sentence=req.one_sentence,
            model_id=model_id,
            custom_stop=req.stop,
        )

        # Warm-up call if needed (first test or cache expired)
        if should_warmup(instance_id):
            logger.info("model.instance.test.warmup", extra={"instance_id": instance_id})
            # Warm-up is async/best-effort, don't block on it
            mark_warmed(instance_id)

        # Call provider
        try:
            # Get provider from PostgreSQL
            from db.postgres_control.repositories.provider_repo import get_provider

            provider = get_provider(provider_id, include_secrets=True)

            if not provider:
                raise ValueError(f"Provider not found: {provider_id}")

            base_url = provider.get("base_url", "").rstrip("/")
            api_key = provider.get("api_key")
            config = provider.get("config_json") or provider.get("config") or {}

            # Build URL
            path_override = None
            if isinstance(config, dict):
                paths_cfg = config.get("paths", {})
                if isinstance(paths_cfg, dict):
                    path_override = paths_cfg.get("chat_completions") or paths_cfg.get("completions")

            from urllib.parse import urljoin

            url = urljoin(base_url + "/", (path_override or "/chat/completions").lstrip("/"))

            # Build payload
            payload = {
                "model": model_id,
                "messages": messages,
                "temperature": req.temperature,
                "max_tokens": req.max_tokens,
                "n": 1,  # Always single completion for tests
                "stream": False,  # Disable streaming to prevent stalls
            }

            if stop_sequences:
                payload["stop"] = stop_sequences

            # Build headers
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # Log request (hash prompt for PII safety)
            prompt_hash = hash_prompt(req.prompt or json.dumps(req.messages))
            logger.info(
                "model.instance.test.request",
                extra={
                    "instance_id": instance_id,
                    "model": model_id,
                    "provider": provider_id,
                    "prompt_hash": prompt_hash,
                    "url": url,
                    "temperature": req.temperature,
                    "max_tokens": req.max_tokens,
                },
            )

            # Make request with timeout and retry
            import asyncio

            import httpx

            # Use 60s read timeout for /tests (large models need time)
            timeout = httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0)
            provider_status = None
            retried = False
            warmed = False

            for attempt in range(2):  # Max 2 attempts (1 retry)
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.post(url, json=payload, headers=headers)
                        provider_status = resp.status_code
                        resp.raise_for_status()
                        response_data = resp.json()
                        break  # Success, exit retry loop

                except (httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError) as retry_exc:
                    if attempt == 0:
                        retried = True
                        logger.warning(
                            "model.instance.test.retry",
                            extra={
                                "instance_id": instance_id,
                                "error_type": type(retry_exc).__name__,
                                "attempt": attempt + 1,
                            },
                        )

                        # Try to warm-load model (Ollama first-run often stalls)
                        if "ollama" in base_url.lower():
                            try:
                                logger.info("model.instance.test.warm_loading", extra={"model": model_id})
                                # Check if model exists, if not pull it
                                show_url = urljoin(base_url + "/", "api/show")
                                show_payload = {"name": model_id}

                                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as warm_client:
                                    show_resp = await warm_client.post(show_url, json=show_payload)

                                    if show_resp.status_code == 404:
                                        # Model not found, pull it
                                        pull_url = urljoin(base_url + "/", "api/pull")
                                        pull_payload = {"name": model_id, "stream": False}

                                        logger.info("model.instance.test.pulling_model", extra={"model": model_id})
                                        pull_resp = await warm_client.post(
                                            pull_url, json=pull_payload, timeout=httpx.Timeout(120.0)
                                        )

                                        if pull_resp.status_code == 200:
                                            warmed = True
                                            logger.info("model.instance.test.model_pulled", extra={"model": model_id})
                                    else:
                                        # Model exists, just ensure it's loaded
                                        warmed = True
                                        logger.info("model.instance.test.model_exists", extra={"model": model_id})

                            except Exception as warm_exc:
                                logger.warning(
                                    f"model.instance.test.warm_failed: {warm_exc}", extra={"model": model_id}
                                )

                        # Backoff before retry
                        await asyncio.sleep(0.75)  # 750ms backoff
                        continue  # Retry once
                    else:
                        # Final failure after retry
                        raise  # Re-raise to be caught by outer handler

            # Extract text and usage
            output_text, usage_dict = extract_text_from_response(response_data, model_id)

            # Truncate to sentence if needed
            output_text = truncate_to_sentence(output_text, req.one_sentence)

            # Estimate usage if provider didn't return it
            if not usage_dict:
                usage_dict = estimate_usage(
                    prompt=req.prompt or "",
                    output=output_text,
                    messages=messages,
                )

            # Calculate latency
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Record test event
            model_instance_repo.record_test_event(
                instance_id=instance_id,
                provider_name=provider_id,
                success=True,
                owner_sub=user.sub,
                trace_id=trace_id,
                details={
                    "prompt_hash": prompt_hash,
                    "output_length": len(output_text),
                    "latency_ms": latency_ms,
                },
            )

            # Collect actual parameters used
            actual_parameters = {
                "temperature": req.temperature,
                "max_tokens": req.max_tokens,
                "one_sentence": req.one_sentence,
            }
            if stop_sequences:
                actual_parameters["stop"] = stop_sequences

            # Add headers
            _add_standard_headers(response, None, trace_id)

            # Record provenance
            record_provenance(
                actor="api",
                action="model.instance.test",
                resource=f"/models/instances/{instance_id}/tests",
                input={"prompt_hash": prompt_hash},
                output={"output_length": len(output_text), "tokens": usage_dict.get("total_tokens")},
                meta={
                    "user": user.sub,
                    "trace_id": trace_id,
                    "latency_ms": latency_ms,
                    "provider": provider_id,
                    "model": model_id,
                },
            )

            logger.info(
                "model.instance.test.success",
                extra={
                    "instance_id": instance_id,
                    "model": model_id,
                    "provider": provider_id,
                    "latency_ms": latency_ms,
                    "tokens": usage_dict.get("total_tokens"),
                    "status": provider_status,
                },
            )

            return TestInstanceResponse(
                model=model_id,
                output=output_text,
                usage=usage_dict,
                trace_id=trace_id,
                event_id=event_id,
                provider=provider_id,
                provider_base_url=base_url,
                latency_ms=latency_ms,
                parameters=actual_parameters,
            )

        except httpx.HTTPStatusError as http_exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            provider_status = http_exc.response.status_code if http_exc.response else 0

            logger.error(
                "model.instance.test.http_error",
                extra={
                    "instance_id": instance_id,
                    "status": provider_status,
                    "latency_ms": latency_ms,
                },
                exc_info=True,
            )

            # Record failed test
            model_instance_repo.record_test_event(
                instance_id=instance_id,
                provider_name=provider_id,
                success=False,
                owner_sub=user.sub,
                trace_id=trace_id,
                details={"error": str(http_exc), "status": provider_status},
            )

            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "type": "about:blank",
                    "title": "Bad Gateway",
                    "detail": f"Provider returned {provider_status}: {http_exc!s}",
                    "provider": provider_id,
                    "provider_base_url": base_url,
                    "model": model_id,
                },
            )

        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RequestError) as conn_exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            logger.error(
                "model.instance.test.connection_error",
                extra={
                    "instance_id": instance_id,
                    "error_type": type(conn_exc).__name__,
                    "latency_ms": latency_ms,
                },
                exc_info=True,
            )

            # Record failed test
            model_instance_repo.record_test_event(
                instance_id=instance_id,
                provider_name=provider_id,
                success=False,
                owner_sub=user.sub,
                trace_id=trace_id,
                details={"error": str(conn_exc), "error_type": type(conn_exc).__name__},
            )

            # Return detailed 504 with debug info
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={
                    "type": "about:blank",
                    "title": "Gateway Timeout",
                    "detail": f"Provider connection failed: {type(conn_exc).__name__}",
                    "provider": provider_id,
                    "provider_base_url": base_url,
                    "model": model_id,
                    "timeout_seconds": 60.0,
                    "warmed": warmed if "warmed" in locals() else False,
                    "retried": retried if "retried" in locals() else False,
                    "latency_ms": latency_ms,
                },
            )

        except Exception as provider_exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            logger.error(
                "model.instance.test.provider_failed",
                extra={"instance_id": instance_id, "latency_ms": latency_ms},
                exc_info=True,
            )

            # Record failed test
            model_instance_repo.record_test_event(
                instance_id=instance_id,
                provider_name=provider_id,
                success=False,
                owner_sub=user.sub,
                trace_id=trace_id,
                details={"error": str(provider_exc)},
            )

            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "type": "about:blank",
                    "title": "Bad Gateway",
                    "detail": f"Provider error: {provider_exc!s}",
                    "provider": provider_id,
                    "model": model_id,
                },
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"model.instance.test.failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"type": "about:blank", "title": "Internal Server Error", "detail": str(exc)},
        )
