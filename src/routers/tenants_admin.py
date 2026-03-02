from __future__ import annotations

"""
Tenant management API router.

Provides CRUD operations for tenant lifecycle management with proper
RBAC, pagination, ETag caching, and RFC 7807 error responses.

NOTE: This router is mounted under /v1/admin by src.routers.admin which
      applies the admin:all scope requirement globally.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from db.postgres_control.database import get_db
from db.postgres_control.repositories.tenants import TenantsRepository
from src.config import settings
from src.provenance import record_provenance
from src.schemas.auth import UserInfo
from src.routers.auth import get_current_user
from src.schemas.tenants import (
    CreateTenantRequest,
    Tenant,
    TenantListResponse,
    UpdateTenantRequest,
)
from src.security.perm import require_perms

router = APIRouter(tags=["admin-tenants"])


def _principal_name(user: UserInfo) -> str:
    """Extract principal name from UserInfo."""
    return getattr(user, "sub", None) or getattr(user, "username", "unknown")


# NOTE: No need to check admin:all here - parent router (admin.py) enforces it


# ---------- LIST Tenants ----------


@router.get(
    "",
    response_model=TenantListResponse,
    tags=["admin-tenants"],
    summary="List tenants",
    description="""
GET /v1/admin/tenants – Retrieve all tenants in the platform

**Why we need this endpoint:**
- Platform administrators need to see all registered tenants to monitor the system
- Essential for tenant management and auditing who has access to the platform
- Without it, admins would have no way to discover which organizations are using the system
- Helps identify configuration issues across multiple tenants

**What it does:**
- Fetches a complete list of all tenant organizations registered in the platform
- Returns tenant details including ID, name, admin email, metadata, and timestamps
- Supports pagination to handle large numbers of tenants efficiently
- Includes caching to improve performance for repeated requests

**Access:**
- Only administrators with `admin:all` scope can call this endpoint
- Regular users cannot list all tenants (security isolation)

**Behavior:**
- **Pagination**: Returns up to 100 tenants per page (configurable 1-1000)
- **Caching**: Supports `If-None-Match` header - returns 304 if data hasn't changed
- **Headers**: Includes `ETag` for cache validation and `Link` header for next page
- **Performance**: ETag-based caching reduces bandwidth and server load

**Responses:**
- **200 OK**: Successfully retrieved tenant list (may be empty if no tenants exist)
- **304 Not Modified**: Your cached copy is still valid (ETag match)
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: User lacks required `admin:all` scope

**Examples:**
```bash
# List first 100 tenants
curl -X GET "http://localhost:8000/v1/admin/tenants" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# List with custom page size
curl -X GET "http://localhost:8000/v1/admin/tenants?page_size=50" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Get next page using pagination token
curl -X GET "http://localhost:8000/v1/admin/tenants?page_size=100&page_token=eyJvZmZzZXQiOjEwMH0" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Conditional request with caching (prevents re-downloading if unchanged)
curl -X GET "http://localhost:8000/v1/admin/tenants" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -H 'If-None-Match: "page-hash-abc123"'
```
""",
    responses={
        200: {
            "description": "List of tenants (may be empty)",
            "headers": {
                "ETag": {
                    "description": "Entity tag for cache validation",
                    "schema": {"type": "string", "example": '"page-hash-abc123"'},
                },
                "Link": {
                    "description": "RFC 5988 Link header for pagination (when next page exists)",
                    "schema": {
                        "type": "string",
                        "example": '</v1/admin/tenants?page_size=100&page_token=xyz>; rel="next"',
                    },
                },
                "X-Request-Id": {
                    "description": "Request correlation ID",
                    "schema": {"type": "string", "example": "req_1a2b3c4d"},
                },
            },
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {
                                "id": "tenant-501a149f",
                                "name": "ACME Corporation",
                                "admin_email": "admin@acme.com",
                                "metadata": {"region": "us-east-1", "tier": "premium"},
                                "created_at": "2025-10-11T08:30:00Z",
                                "updated_at": "2025-10-11T08:30:00Z",
                            },
                            {
                                "id": "tenant-a1b2c3d4",
                                "name": "Beta Test Tenant",
                                "admin_email": "beta@example.com",
                                "metadata": {},
                                "created_at": "2025-10-10T10:00:00Z",
                                "updated_at": "2025-10-10T10:00:00Z",
                            },
                        ],
                        "next_page_token": "eyJvZmZzZXQiOjEwMH0",
                        "total": 250,
                    }
                }
            },
        },
        304: {
            "description": "Not Modified - cached response is still valid",
            "headers": {"ETag": {"description": "Entity tag (unchanged)", "schema": {"type": "string"}}},
        },
        401: {
            "description": "Missing or invalid authentication",
            "content": {
                "application/json": {
                    "example": {
                        "type": "https://example.com/probs/unauthorized",
                        "title": "Unauthorized",
                        "status": 401,
                        "detail": "Missing or invalid authentication token",
                        "instance": "/v1/admin/tenants",
                    }
                }
            },
        },
        403: {
            "description": "Missing required admin:all scope",
            "content": {
                "application/json": {
                    "example": {
                        "type": "https://example.com/probs/forbidden",
                        "title": "Forbidden",
                        "status": 403,
                        "detail": "Requires admin:all scope",
                        "instance": "/v1/admin/tenants",
                    }
                }
            },
        },
    },
)
async def list_tenants(
    request: Request,
    response: Response,
    page_size: int = Query(default=100, ge=1, le=1000, description="Page size (1-1000)"),
    page_token: str | None = Query(default=None, description="Pagination token"),
    user: UserInfo = Depends(require_perms([])),
    db: Session = Depends(get_db),
) -> TenantListResponse:
    """List tenants with pagination, caching, and proper RBAC."""
    repo = TenantsRepository(db)

    # Get paginated tenants from repository
    page_items, next_token, total = repo.list(page_size=page_size, page_token=page_token)

    # Convert ORM models to dicts for response
    items_dicts = [t.to_dict() for t in page_items]

    # Compute ETag for caching
    etag = repo.compute_list_etag(page_items)
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return TenantListResponse(items=[], next_page_token=None)

    response.headers["ETag"] = etag

    # Add Link header for pagination (RFC 5988)
    if next_token:
        base_path = str(request.url.path)
        next_url = f"{base_path}?page_size={page_size}&page_token={next_token}"
        response.headers["Link"] = f'<{next_url}>; rel="next"'

    # Provenance logging
    record_provenance(
        actor="api",
        action="tenants.list",
        resource="/admin/tenants",
        input={"page_size": page_size, "page_token": page_token},
        output={"count": len(page_items)},
        meta={"user": _principal_name(user)},
    )

    return TenantListResponse(items=items_dicts, next_page_token=next_token, total=total)


# ---------- CREATE Tenant ----------


@router.post(
    "",
    response_model=Tenant,
    status_code=status.HTTP_201_CREATED,
    tags=["admin-tenants"],
    summary="Create tenant",
    description="""
POST /v1/admin/tenants – Register a new tenant organization

**Why we need this endpoint:**
- New organizations need to be onboarded to the platform
- Creates isolated environments for different companies or teams
- Without it, there's no way to add new customers or departments to the system
- Essential for multi-tenant architecture and proper data isolation

**What it does:**
- Creates a new tenant with a unique server-generated ID
- Validates tenant information (name, admin email, optional metadata)
- Stores tenant configuration for future operations
- Supports idempotent retries (safe to call multiple times with same data)

**Access:**
- Only administrators with `admin:all` scope can create tenants
- Requires `X-Tenant-Id` header for audit trail (which admin tenant created this)

**Behavior:**
- **Auto-generated ID**: Server creates unique tenant ID (format: `tenant-xxxxxxxx`)
- **Idempotency**: Calling with identical data returns existing tenant (200 OK, not 201)
- **Conflict detection**: Returns 409 if tenant name exists with different configuration
- **Validation**: Checks email format, name length, and required fields

**Responses:**
- **201 Created**: New tenant successfully created (includes `Location` header)
- **200 OK**: Tenant already exists with exact same configuration (safe retry)
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: User lacks required `admin:all` scope
- **409 Conflict**: Tenant name exists but with different email or metadata
- **422 Unprocessable Entity**: Invalid email, missing fields, or validation errors

**Examples:**
```bash
# Create a new tenant
curl -X POST "http://localhost:8000/v1/admin/tenants" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -H "Content-Type: application/json" \\
     -H "X-Tenant-Id: tenant-admin-root" \\
     -d '{
       "name": "ACME Corporation",
       "admin_email": "admin@acme.com",
       "metadata": {
         "region": "us-east-1",
         "tier": "premium"
       }
     }'

# Create tenant with minimal fields (metadata optional)
curl -X POST "http://localhost:8000/v1/admin/tenants" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -H "Content-Type: application/json" \\
     -d '{
       "name": "Startup Inc",
       "admin_email": "contact@startup.io"
     }'

# Idempotent retry (returns 200 OK if exact match exists)
curl -X POST "http://localhost:8000/v1/admin/tenants" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -H "Content-Type: application/json" \\
     -d '{
       "name": "ACME Corporation",
       "admin_email": "admin@acme.com",
       "metadata": {"region": "us-east-1", "tier": "premium"}
     }'
```
""",
    responses={
        201: {
            "description": "Tenant created successfully",
            "headers": {
                "Location": {
                    "description": "URL to the created tenant",
                    "schema": {"type": "string", "example": "/v1/admin/tenants/tenant-501a149f"},
                },
                "ETag": {
                    "description": "Entity tag for cache validation",
                    "schema": {"type": "string", "example": '"abc123def456"'},
                },
                "X-Request-Id": {
                    "description": "Request correlation ID",
                    "schema": {"type": "string", "example": "req_1a2b3c4d"},
                },
                "X-Event-Id": {
                    "description": "Provenance event ID",
                    "schema": {"type": "string", "example": "evt_xyz789"},
                },
                "X-Trace-Id": {
                    "description": "Distributed trace ID",
                    "schema": {"type": "string", "example": "trace_abcdef"},
                },
            },
            "content": {
                "application/json": {
                    "example": {
                        "id": "tenant-501a149f",
                        "name": "ACME Corporation",
                        "admin_email": "admin@acme.com",
                        "metadata": {"region": "us-east-1", "tier": "premium"},
                        "created_at": "2025-10-11T08:30:00Z",
                        "updated_at": "2025-10-11T08:30:00Z",
                    }
                }
            },
        },
        200: {
            "description": "Tenant already exists with same config (idempotent - safe retry)",
            "headers": {
                "ETag": {
                    "description": "Entity tag for cache validation",
                    "schema": {"type": "string", "example": '"abc123def456"'},
                }
            },
            "content": {
                "application/json": {
                    "example": {
                        "id": "tenant-501a149f",
                        "name": "ACME Corporation",
                        "admin_email": "admin@acme.com",
                        "metadata": {"region": "us-east-1", "tier": "premium"},
                        "created_at": "2025-10-10T10:00:00Z",
                        "updated_at": "2025-10-10T10:00:00Z",
                    },
                    "description": "Returns existing tenant without modification. Timestamps reflect original creation, not retry time.",
                }
            },
        },
        401: {
            "description": "Missing or invalid authentication",
            "content": {
                "application/json": {
                    "example": {
                        "type": "https://example.com/probs/unauthorized",
                        "title": "Unauthorized",
                        "status": 401,
                        "detail": "Missing or invalid authentication token",
                        "instance": "/v1/admin/tenants",
                    }
                }
            },
        },
        403: {
            "description": "Missing required admin:all scope",
            "content": {
                "application/json": {
                    "example": {
                        "type": "https://example.com/probs/forbidden",
                        "title": "Forbidden",
                        "status": 403,
                        "detail": "Requires admin:all scope",
                        "instance": "/v1/admin/tenants",
                        "extensions": {"required_scopes": ["admin:all"], "user_scopes": ["user:me"]},
                    }
                }
            },
        },
        409: {
            "description": "Tenant name exists with different configuration (conflict - not idempotent)",
            "content": {
                "application/json": {
                    "examples": {
                        "email_mismatch": {
                            "summary": "Same name, different email",
                            "description": "Tenant with this name already exists but with different admin_email",
                            "value": {
                                "type": "https://example.com/probs/conflict",
                                "title": "Conflict",
                                "status": 409,
                                "detail": "Tenant with name 'ACME Corporation' already exists with different configuration",
                                "instance": "/v1/admin/tenants",
                                "extensions": {
                                    "correlation_id": "req_1a2b3c4d",
                                    "conflicts": {
                                        "admin_email": {"existing": "original@acme.com", "requested": "new@acme.com"}
                                    },
                                },
                            },
                        },
                        "metadata_mismatch": {
                            "summary": "Same name and email, different metadata",
                            "description": "Tenant exists with same identifiers but different metadata",
                            "value": {
                                "type": "https://example.com/probs/conflict",
                                "title": "Conflict",
                                "status": 409,
                                "detail": "Tenant with name 'ACME Corporation' already exists with different configuration",
                                "instance": "/v1/admin/tenants",
                                "extensions": {
                                    "correlation_id": "req_5e6f7g8h",
                                    "conflicts": {
                                        "metadata": {
                                            "existing": {"tier": "premium", "region": "us-east-1"},
                                            "requested": {"tier": "enterprise", "region": "us-west-2"},
                                        }
                                    },
                                },
                            },
                        },
                    }
                }
            },
        },
        422: {
            "description": "Validation error (invalid email, missing header, etc.)",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_email": {
                            "summary": "Invalid email format",
                            "value": {
                                "type": "https://example.com/probs/validation",
                                "title": "Validation Error",
                                "status": 422,
                                "detail": "Request validation failed",
                                "instance": "/v1/admin/tenants",
                                "extensions": {"correlation_id": "req_1a2b3c4d"},
                                "errors": [
                                    {
                                        "type": "value_error",
                                        "loc": ["body", "admin_email"],
                                        "msg": "value is not a valid email address: An email address must have an @-sign.",
                                        "input": "not-an-email",
                                        "ctx": {"reason": "An email address must have an @-sign."},
                                    }
                                ],
                            },
                        },
                        "missing_header": {
                            "summary": "Missing X-Tenant-Id header",
                            "value": {
                                "detail": [
                                    {
                                        "type": "missing",
                                        "loc": ["header", "x-tenant-id"],
                                        "msg": "Field required",
                                        "input": None,
                                    }
                                ]
                            },
                        },
                    }
                }
            },
        },
    },
)
async def create_tenant(
    req: CreateTenantRequest,
    request: Request,
    response: Response,
    x_tenant_id: Annotated[
        str,
        Header(
            alias="X-Tenant-Id",
            description="Admin audit context - which tenant is performing this admin operation. Defaults to configured admin tenant.",
            examples={"default": {"summary": "Default admin tenant", "value": "tenant-admin-root"}},
        ),
    ] = settings.ADMIN_DEFAULT_TENANT_ID,
    user: UserInfo = Depends(require_perms([])),
    db: Session = Depends(get_db),
) -> Tenant:
    """Create and return a new tenant with server-generated ID."""
    tenant_context = x_tenant_id
    repo = TenantsRepository(db)

    try:
        # Attempt to create tenant (handles idempotency internally)
        tenant, was_created = repo.create(name=req.name, admin_email=str(req.admin_email), metadata=req.metadata)

        # Set status code based on whether tenant was created or was idempotent
        if was_created:
            response.status_code = status.HTTP_201_CREATED
            action = "tenants.create"
        else:
            response.status_code = status.HTTP_200_OK
            action = "tenants.create.idempotent"

    except ValueError as ve:
        # Check if this is a conflict error (idempotency check failed)
        args = ve.args
        if len(args) == 2 and isinstance(args[1], dict):
            # Conflict with details
            conflicts = args[1]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "type": "https://example.com/probs/conflict",
                    "title": "Conflict",
                    "status": 409,
                    "detail": str(args[0]),
                    "instance": "/v1/admin/tenants",
                    "extensions": {
                        "correlation_id": response.headers.get("X-Request-Id", "unknown"),
                        "conflicts": conflicts,
                    },
                },
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    # Convert ORM model to dict
    tenant_dict = tenant.to_dict()

    # Set Location header
    response.headers["Location"] = f"/v1/admin/tenants/{tenant_dict['id']}"

    # Set ETag for caching
    response.headers["ETag"] = repo.compute_etag(tenant)

    # Provenance
    ev = record_provenance(
        actor="api",
        action=action,
        resource="/admin/tenants",
        input=req.model_dump(),
        output={"id": tenant_dict["id"], "idempotent": not was_created},
        meta={"user": _principal_name(user), "request_tenant": tenant_context},
        success=True,
    )

    response.headers["X-Event-Id"] = ev.event_id
    response.headers["X-Trace-Id"] = ev.trace_id

    return Tenant(**tenant_dict)


# ---------- GET Tenant by ID ----------


@router.get(
    "/{tenant_id}",
    response_model=Tenant,
    tags=["admin-tenants"],
    summary="Get tenant by ID",
    description="""
GET /v1/admin/tenants/{tenant_id} – Retrieve a specific tenant's details

**Why we need this endpoint:**
- Administrators need to view complete details of a specific tenant
- Required for verifying tenant configuration and troubleshooting
- Without it, you'd have to list all tenants and filter manually (inefficient)
- Enables direct access to tenant information for API integrations

**What it does:**
- Fetches detailed information for one specific tenant by its ID
- Returns all tenant properties: name, admin email, metadata, timestamps
- Provides ETag header for efficient caching
- Validates that the tenant exists before returning data

**Access:**
- Only administrators with `admin:all` scope can access tenant details
- Regular users cannot view tenant information

**Behavior:**
- **Direct lookup**: Fast retrieval by tenant ID (no scanning required)
- **Caching support**: Includes ETag header for conditional requests
- **Error handling**: Returns 404 if tenant doesn't exist

**Responses:**
- **200 OK**: Tenant found and details returned successfully
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: User lacks required `admin:all` scope
- **404 Not Found**: No tenant exists with the specified ID

**Examples:**
```bash
# Get a specific tenant by ID
curl -X GET "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Get tenant with response headers shown
curl -X GET "http://localhost:8000/v1/admin/tenants/tenant-abc123" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -v

# Example successful response:
# {
#   "id": "tenant-501a149f",
#   "name": "ACME Corporation",
#   "admin_email": "admin@acme.com",
#   "metadata": {"region": "us-east-1", "tier": "premium"},
#   "created_at": "2025-10-11T08:30:00Z",
#   "updated_at": "2025-10-11T08:30:00Z"
# }
```
""",
    responses={
        200: {
            "description": "Tenant details",
            "headers": {
                "ETag": {
                    "description": "Entity tag for cache validation",
                    "schema": {"type": "string", "example": '"tenant-abc123"'},
                },
                "X-Request-Id": {
                    "description": "Request correlation ID",
                    "schema": {"type": "string", "example": "req_1a2b3c4d"},
                },
            },
            "content": {
                "application/json": {
                    "example": {
                        "id": "tenant-501a149f",
                        "name": "ACME Corporation",
                        "admin_email": "admin@acme.com",
                        "metadata": {"region": "us-east-1", "tier": "premium"},
                        "created_at": "2025-10-11T08:30:00Z",
                        "updated_at": "2025-10-11T08:30:00Z",
                    }
                }
            },
        },
        404: {
            "description": "Tenant not found",
            "content": {
                "application/json": {
                    "example": {
                        "type": "https://example.com/probs/not-found",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Tenant 'tenant-xyz' not found",
                        "instance": "/v1/admin/tenants/tenant-xyz",
                        "extensions": {"correlation_id": "req_1a2b3c4d"},
                    }
                }
            },
        },
    },
)
async def get_tenant(
    tenant_id: str, response: Response, user: UserInfo = Depends(require_perms([])), db: Session = Depends(get_db)
) -> Tenant:
    """Fetch a tenant record by ID."""
    repo = TenantsRepository(db)

    tenant = repo.get_by_id(tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' not found")

    # Set ETag for caching
    response.headers["ETag"] = repo.compute_etag(tenant)

    # Provenance
    record_provenance(
        actor="api",
        action="tenants.get",
        resource=f"/admin/tenants/{tenant_id}",
        input={"tenant_id": tenant_id},
        output={"id": tenant_id},
        meta={"user": _principal_name(user)},
        success=True,
    )

    return Tenant(**tenant.to_dict())


# ---------- PATCH Tenant ----------


@router.patch(
    "/{tenant_id}",
    response_model=Tenant,
    tags=["admin-tenants"],
    summary="Update tenant (partial)",
    description="""
PATCH /v1/admin/tenants/{tenant_id} – Modify tenant configuration

**Why we need this endpoint:**
- Tenant information changes over time (new admin email, updated metadata)
- Allows updating specific fields without replacing the entire tenant record
- Without it, admins would need to delete and recreate tenants (losing history)
- Essential for maintaining accurate tenant data as organizations evolve

**What it does:**
- Updates one or more fields of an existing tenant
- Only changes the fields you specify (leaves others unchanged)
- Intelligently merges metadata (adds new keys, updates existing ones)
- Validates all updates before applying them

**Access:**
- Only administrators with `admin:all` scope can update tenants
- Requires `X-Tenant-Id` header for audit trail

**Behavior:**
- **Partial updates**: Send only the fields you want to change
- **Metadata merging**: New metadata keys are added; existing keys are updated; set to `null` to remove
- **Validation**: Email format and name length are checked before saving
- **Empty requests rejected**: At least one field must be provided

**Responses:**
- **200 OK**: Tenant successfully updated with new values
- **400 Bad Request**: Empty request body (no fields to update)
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: User lacks required `admin:all` scope
- **404 Not Found**: Tenant with specified ID doesn't exist
- **422 Unprocessable Entity**: Invalid email format or validation errors

**Examples:**
```bash
# Update tenant name only
curl -X PATCH "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -H "Content-Type: application/json" \\
     -H "X-Tenant-Id: tenant-admin-root" \\
     -d '{
       "name": "ACME Corp (Updated)"
     }'

# Update admin email
curl -X PATCH "http://localhost:8000/v1/admin/tenants/tenant-abc123" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -H "Content-Type: application/json" \\
     -d '{
       "admin_email": "newadmin@acme.com"
     }'

# Update metadata (merges with existing metadata)
curl -X PATCH "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -H "Content-Type: application/json" \\
     -d '{
       "metadata": {
         "region": "us-west-2",
         "tier": "enterprise",
         "new_field": "value"
       }
     }'

# Update multiple fields at once
curl -X PATCH "http://localhost:8000/v1/admin/tenants/tenant-xyz789" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -H "Content-Type: application/json" \\
     -d '{
       "name": "Updated Name",
       "admin_email": "updated@example.com",
       "metadata": {"status": "active"}
     }'
```
""",
    responses={
        200: {
            "description": "Tenant updated successfully",
            "headers": {
                "ETag": {
                    "description": "Updated entity tag",
                    "schema": {"type": "string", "example": '"tenant-updated-xyz"'},
                },
                "X-Request-Id": {"description": "Request correlation ID", "schema": {"type": "string"}},
                "X-Event-Id": {
                    "description": "Provenance event ID",
                    "schema": {"type": "string", "example": "evt_patch_abc"},
                },
                "X-Trace-Id": {
                    "description": "Distributed trace ID",
                    "schema": {"type": "string", "example": "trace_def456"},
                },
            },
            "content": {
                "application/json": {
                    "example": {
                        "id": "tenant-501a149f",
                        "name": "ACME Corporation (Updated)",
                        "admin_email": "admin@acme.com",
                        "metadata": {"region": "us-west-2", "tier": "premium", "new_key": "value"},
                        "created_at": "2025-10-11T08:30:00Z",
                        "updated_at": "2025-10-11T10:45:00Z",
                    }
                }
            },
        },
        400: {
            "description": "Empty request body",
            "content": {
                "application/json": {
                    "example": {
                        "type": "https://example.com/probs/bad-request",
                        "title": "Bad Request",
                        "status": 400,
                        "detail": "At least one field must be provided for update (name, admin_email, or metadata)",
                        "instance": "/v1/admin/tenants/tenant-501a149f",
                    }
                }
            },
        },
        404: {
            "description": "Tenant not found",
            "content": {
                "application/json": {
                    "example": {
                        "type": "https://example.com/probs/not-found",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Tenant 'tenant-xyz' not found",
                        "instance": "/v1/admin/tenants/tenant-xyz",
                    }
                }
            },
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {
                        "type": "https://example.com/probs/validation",
                        "title": "Validation Error",
                        "status": 422,
                        "detail": "Request validation failed",
                        "instance": "/v1/admin/tenants/tenant-501a149f",
                        "errors": [
                            {
                                "type": "value_error",
                                "loc": ["body", "admin_email"],
                                "msg": "value is not a valid email address",
                                "input": "invalid-email",
                            }
                        ],
                    }
                }
            },
        },
    },
)
async def patch_tenant(
    tenant_id: str,
    req: UpdateTenantRequest,
    response: Response,
    x_tenant_id: Annotated[
        str,
        Header(
            alias="X-Tenant-Id",
            description="Admin audit context - which tenant is performing this admin operation. Defaults to configured admin tenant.",
            examples={"default": {"summary": "Default admin tenant", "value": "tenant-admin-root"}},
        ),
    ] = settings.ADMIN_DEFAULT_TENANT_ID,
    user: UserInfo = Depends(require_perms([])),
    db: Session = Depends(get_db),
) -> Tenant:
    """Apply partial update to tenant."""
    # Reject empty body
    patch_data = req.model_dump(exclude_unset=True)
    if not patch_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided for update (name, admin_email, or metadata)",
        )

    repo = TenantsRepository(db)

    # Extract fields for repository call
    name = patch_data.get("name")
    admin_email = patch_data.get("admin_email")
    metadata = patch_data.get("metadata")

    try:
        tenant = repo.update_partial(tenant_id=tenant_id, name=name, admin_email=admin_email, metadata_merge=metadata)

        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' not found")

    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    tenant_dict = tenant.to_dict()

    # Provenance
    ev = record_provenance(
        actor="api",
        action="tenants.patch",
        resource=f"/admin/tenants/{tenant_id}",
        input=patch_data,
        output={"id": tenant_id},
        meta={"user": _principal_name(user)},
        success=True,
    )

    # Set ETag for caching
    response.headers["ETag"] = repo.compute_etag(tenant)
    response.headers["X-Event-Id"] = ev.event_id
    response.headers["X-Trace-Id"] = ev.trace_id

    return Tenant(**tenant_dict)


# ---------- DELETE Tenant ----------


@router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["admin-tenants"],
    summary="Delete tenant",
    description="""
DELETE /v1/admin/tenants/{tenant_id} – Remove a tenant from the platform

**Why we need this endpoint:**
- Organizations may leave the platform and need to be removed
- Essential for cleanup during testing or when closing customer accounts
- Without it, deleted/inactive tenants would accumulate in the system
- Required for compliance with data removal requirements

**What it does:**
- Permanently removes a tenant and its configuration from the platform
- Checks for dependent resources before deletion (safe deletion policy)
- Prevents accidental data loss by blocking deletion of active tenants
- Records deletion event in audit logs for compliance

**Access:**
- Only administrators with `admin:all` scope can delete tenants
- Requires `X-Tenant-Id` header for audit trail

**Behavior:**
- **Dependency checking**: Fails if tenant has active providers, jobs, or other resources
- **Safe deletion**: Won't delete until all dependencies are removed first
- **Not idempotent**: Deleting non-existent tenant returns 404 (explicit failure)
- **No response body**: Returns 204 with empty body on success

**Responses:**
- **204 No Content**: Tenant successfully deleted (empty response body)
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: User lacks required `admin:all` scope
- **404 Not Found**: Tenant with specified ID doesn't exist
- **409 Conflict**: Cannot delete tenant because it has active resources (providers, jobs, etc.)

**Examples:**
```bash
# Delete a tenant (succeeds only if no dependencies)
curl -X DELETE "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -H "X-Tenant-Id: tenant-admin-root"

# Delete tenant with verbose output to see headers
curl -X DELETE "http://localhost:8000/v1/admin/tenants/tenant-xyz789" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -v

# Example 409 response (tenant has dependencies):
# {
#   "type": "https://example.com/probs/conflict",
#   "title": "Conflict",
#   "status": 409,
#   "detail": "Cannot delete tenant with dependent resources",
#   "instance": "/v1/admin/tenants/tenant-501a149f",
#   "extensions": {
#     "blockers": [
#       {"type": "provider", "id": "provider-abc", "name": "OpenAI GPT-4"},
#       {"type": "job", "id": "job-xyz", "status": "running"}
#     ]
#   }
# }
#
# To delete this tenant: first remove/delete the providers and jobs listed
```
""",
    responses={
        204: {
            "description": "Tenant deleted successfully (no content)",
            "headers": {
                "X-Request-Id": {
                    "description": "Request correlation ID",
                    "schema": {"type": "string", "example": "req_1a2b3c4d"},
                },
                "X-Event-Id": {
                    "description": "Provenance event ID",
                    "schema": {"type": "string", "example": "evt_delete_xyz"},
                },
                "X-Trace-Id": {
                    "description": "Distributed trace ID",
                    "schema": {"type": "string", "example": "trace_abc123"},
                },
            },
        },
        404: {
            "description": "Tenant not found",
            "content": {
                "application/json": {
                    "example": {
                        "type": "https://example.com/probs/not-found",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Tenant 'tenant-xyz' not found",
                        "instance": "/v1/admin/tenants/tenant-xyz",
                        "extensions": {"correlation_id": "req_1a2b3c4d"},
                    }
                }
            },
        },
        409: {
            "description": "Tenant has dependent resources (cannot delete)",
            "content": {
                "application/json": {
                    "example": {
                        "type": "https://example.com/probs/conflict",
                        "title": "Conflict",
                        "status": 409,
                        "detail": "Cannot delete tenant with dependent resources",
                        "instance": "/v1/admin/tenants/tenant-501a149f",
                        "extensions": {
                            "correlation_id": "req_1a2b3c4d",
                            "blockers": [
                                {"type": "provider", "id": "provider-abc", "name": "OpenAI GPT-4"},
                                {"type": "job", "id": "job-xyz", "status": "running"},
                            ],
                        },
                    }
                }
            },
        },
    },
)
async def delete_tenant(
    tenant_id: str,
    response: Response,
    x_tenant_id: Annotated[
        str,
        Header(
            alias="X-Tenant-Id",
            description="Admin audit context - which tenant is performing this admin operation. Defaults to configured admin tenant.",
            examples={"default": {"summary": "Default admin tenant", "value": "tenant-admin-root"}},
        ),
    ] = settings.ADMIN_DEFAULT_TENANT_ID,
    user: UserInfo = Depends(require_perms([])),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a tenant record with dependency checking."""
    repo = TenantsRepository(db)

    # Check if tenant exists
    if not repo.get_by_id(tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' not found")

    # Check for dependencies
    blockers = repo.check_dependencies(tenant_id)
    if blockers:
        # Return RFC 7807 Problem+JSON directly
        from fastapi.responses import JSONResponse

        problem_detail = {
            "type": "https://example.com/probs/conflict",
            "title": "Conflict",
            "status": 409,
            "detail": "Cannot delete tenant with dependent resources",
            "instance": f"/v1/admin/tenants/{tenant_id}",
            "extensions": {"correlation_id": response.headers.get("X-Request-Id", "unknown"), "blockers": blockers},
        }
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=problem_detail)

    # Delete tenant
    try:
        deleted = repo.delete(tenant_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' not found")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Provenance
    ev = record_provenance(
        actor="api",
        action="tenants.delete",
        resource=f"/admin/tenants/{tenant_id}",
        input={"tenant_id": tenant_id},
        output={"id": tenant_id},
        meta={"user": _principal_name(user)},
        success=True,
    )

    # Set headers on response
    response.headers["X-Event-Id"] = ev.event_id
    response.headers["X-Trace-Id"] = ev.trace_id
    response.status_code = status.HTTP_204_NO_CONTENT

    return response
