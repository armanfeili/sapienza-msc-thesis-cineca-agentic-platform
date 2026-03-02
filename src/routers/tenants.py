from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.schemas.auth import UserInfo
from src.schemas.tenants import CreateTenantRequest, Tenant, UpdateTenantRequest
from src.provenance import record_provenance
from src.routers.auth import get_current_user
from src.utils.pagination import compute_etag, make_page

router = APIRouter(tags=["tenants"])


@router.get(
    "",
    response_model=list[Tenant],
    summary="List tenants",
    description="""
Return a paginated list of tenants registered in the platform.

Admin-only endpoint that enumerates tenant records. The response is paginated and may be
ETagged for caching. Each tenant includes basic metadata such as id, name, admin_email and
free-form `metadata` useful for tenant-scoped configuration.
""",
)
async def list_tenants(
    request: Request,
    response: Response,
    page_size: int = 50,
    page_token: str | None = None,
    user: UserInfo = Depends(get_current_user),
) -> list[Tenant]:
    """List tenants with pagination and caching support.

    Use the `X-Tenant-Id` header and `if-none-match` ETag headers where appropriate. Requires
    admin privileges.
    """
    _require_admin(user)
    from src.services.tenants import list_tenants as svc_list

    out = svc_list()
    page_items, _next_token = make_page([t.model_dump() for t in out], page_size=page_size, page_token=page_token)
    etag = compute_etag(page_items)
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)
    response.headers["ETag"] = etag
    record_provenance(
        actor="api",
        action="tenants.list",
        resource="/tenants",
        input={"page_size": page_size, "page_token": page_token},
        output={"count": len(page_items)},
        meta={"user": user.username},
    )
    # Return a plain list to match response_model=List[Tenant]
    return page_items


@router.post(
    "",
    response_model=Tenant,
    status_code=status.HTTP_201_CREATED,
    summary="Create tenant",
    description="""
Create a new tenant record.

Admin-only operation that provisions a tenant id and basic tenant metadata. For auditing the
request must include the `X-Tenant-Id` header indicating which administrative tenant or
context initiated the creation. Returns the created Tenant object on success.
""",
)
async def create_tenant(
    req: CreateTenantRequest, user: UserInfo = Depends(get_current_user), request: Request = None
) -> Tenant:
    """Create and return a new tenant.

    Requires admin privileges and an `X-Tenant-Id` header for audit. The request body must
    include a unique `id` and `name` for the tenant. Returns HTTP 201 with the tenant
    details on success.
    """
    _require_admin(user)
    # creation is not tenant-scoped (admin creates a tenant id), but require X-Tenant-Id to be present for audit
    tid = None
    try:
        tid = request.headers.get("X-Tenant-Id") if request is not None else None
    except Exception:
        tid = None
    if not tid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="X-Tenant-Id header required for tenant create"
        )
    from src.services.tenants import create_tenant as svc_create

    tenant = svc_create(id=req.id, name=req.name, admin_email=req.admin_email)
    record_provenance(
        actor="api",
        action="tenants.create",
        resource="/tenants",
        input=req.model_dump(),
        output={"id": tenant.id},
        meta={"user": user.username, "request_tenant": tid},
        success=True,
    )
    return tenant


@router.get(
    "/{tenant_id}",
    response_model=Tenant,
    summary="Get tenant by id",
    description="""
Retrieve a tenant by its id.

Admin-only read endpoint that returns the tenant record for the requested `tenant_id`.
Returns HTTP 404 when the tenant cannot be found.
""",
)
async def get_tenant(tenant_id: str, user: UserInfo = Depends(get_current_user)) -> Tenant:
    """Fetch a tenant record by id.

    Requires admin privileges. Useful for inspecting tenant configuration and administrative
    contact information.
    """
    _require_admin(user)
    from src.services.tenants import get_tenant as svc_get

    t = svc_get(tenant_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    record_provenance(
        actor="api",
        action="tenants.get",
        resource=f"/tenants/{tenant_id}",
        input={},
        output={"id": tenant_id},
        meta={"user": user.username},
        success=True,
    )
    return t


@router.patch(
    "/{tenant_id}",
    response_model=Tenant,
    summary="Patch tenant",
    description="""
Update tenant metadata or administrative contact information.

Admin-only operation that applies a partial update to the tenant record. Supply only the
fields to change in the request body (name, admin_email, metadata). Returns the updated
tenant record on success.
""",
)
async def patch_tenant(tenant_id: str, req: UpdateTenantRequest, user: UserInfo = Depends(get_current_user)) -> Tenant:
    """Apply a partial update to a tenant record.

    Requires admin privileges. Validation or update errors are returned as HTTP 400.
    """
    _require_admin(user)
    from src.services.tenants import update_tenant as svc_update

    try:
        t = svc_update(tenant_id, **(req.model_dump(exclude_unset=True) or {}))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    record_provenance(
        actor="api",
        action="tenants.patch",
        resource=f"/tenants/{tenant_id}",
        input=req.model_dump(exclude_unset=True),
        output={"id": tenant_id},
        meta={"user": user.username},
        success=True,
    )
    return t


@router.delete(
    "/{tenant_id}",
    response_model=dict[str, bool],
    summary="Delete tenant",
    description="""
Delete a tenant from the platform.

Admin-only destructive operation that removes the tenant record and any associated
tenant-scoped configuration. Use with caution — callers should ensure dependent resources
are cleaned up first. Returns a simple `{ "ok": true }` on success.
""",
)
async def delete_tenant(tenant_id: str, user: UserInfo = Depends(get_current_user)) -> dict[str, bool]:
    """Remove a tenant record from the platform.

    Requires admin privileges. The service may raise errors if the tenant cannot be
    deleted (for example, due to dependent resources); such errors are returned as HTTP
    400 with an explanatory detail.
    """
    _require_admin(user)
    from src.services.tenants import delete_tenant as svc_delete

    svc_delete(tenant_id)
    record_provenance(
        actor="api",
        action="tenants.delete",
        resource=f"/tenants/{tenant_id}",
        input={},
        output={"id": tenant_id},
        meta={"user": user.username},
        success=True,
    )
    return {"ok": True}


def _require_admin(user: UserInfo) -> None:
    if "admin" not in (user.scopes or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin scope required")
