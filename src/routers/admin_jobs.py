from __future__ import annotations

import contextlib

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from src.schemas.auth import UserInfo
from src.schemas.jobs import JobCreateRequest as JobRequest, JobListResponse, JobResponse
from src.security.perm import require_perms
from src.utils.pagination import compute_etag

router = APIRouter(tags=["jobs"])


@router.get(
    "",
    name="list_admin_jobs",
    response_model=JobListResponse,
    summary="List all jobs (admin collection)",
    description=(
        "GET /v1/admin/jobs – List all users' jobs (admin only)\n\n"
        "**Why we need this endpoint:**\n"
        "- **System monitoring**: Admins need visibility into all background jobs across all users to monitor system health.\n"
        "- **Debugging**: Helps identify stuck jobs, failed operations, or patterns of user issues.\n"
        "- **Resource management**: Shows which jobs are consuming resources and helps plan capacity.\n"
        "- **Support**: Enables admin team to investigate user-reported problems with specific jobs.\n"
        "- Without this endpoint, admins would have no way to see system-wide job activity or help users troubleshoot.\n\n"
        "**What it does:**\n"
        "- Returns jobs from all users and tenants (system-wide visibility)\n"
        "- Supports filtering by status and pagination\n"
        "- Includes caching to reduce load when monitoring\n\n"
        "**Access:**\n"
        "- Requires `admin:all` permission\n"
        "- Regular users get `403 Forbidden`\n"
        "- Use regular `/v1/jobs` to see only your own jobs\n\n"
        "**Behavior:**\n"
        "- **Filtering**: Add `?status=running` or `?status=queued&status=running` to filter results\n"
        "- **Pagination**: Results are sorted newest first (default 25 per page, max 50). Use `next_page_token` from response to get more\n"
        "- **Caching**: Returns `ETag` header. Send it back as `If-None-Match` to get `304 Not Modified` when nothing changed\n"
        "- **Scope**: Shows all jobs regardless of owner (admin oversight)\n\n"
        "**Responses:**\n"
        "- 200: OK – Job list with pagination info (`items`, `total`, `has_more`, `next_page_token`)\n"
        "- 304: Not Modified – No changes since your last request (when using If-None-Match)\n"
        "- 400: Bad Request – Invalid page_token (must be numeric offset like '0', '25')\n"
        "- 401: Unauthorized – Missing or invalid authentication token\n"
        "- 403: Forbidden – Requires admin:all permission\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# List all jobs (admin view)\n"
        "curl -X GET http://localhost:8000/v1/admin/jobs \\\n"
        '     -H "Authorization: Bearer $ADMIN_TOKEN"\n\n'
        "# Filter by status\n"
        'curl -X GET "http://localhost:8000/v1/admin/jobs?status=running" \\\n'
        '     -H "Authorization: Bearer $ADMIN_TOKEN"\n\n'
        "# Efficient monitoring with ETag\n"
        "curl -X GET http://localhost:8000/v1/admin/jobs \\\n"
        '     -H "Authorization: Bearer $ADMIN_TOKEN" \\\n'
        '     -H "If-None-Match: W/\\"abc123\\""\n'
        "```"
    ),
    responses={
        200: {
            "description": "OK",
            "headers": {
                "ETag": {
                    "schema": {"type": "string"},
                    "description": "Hash of response content and filters for conditional requests",
                },
                "Cache-Control": {"schema": {"type": "string"}, "example": "private, max-age=15"},
                "Vary": {"schema": {"type": "string"}, "example": "Authorization"},
            },
        },
        304: {
            "description": "Not Modified - Content unchanged since last fetch",
            "headers": {
                "ETag": {"schema": {"type": "string"}},
                "Cache-Control": {"schema": {"type": "string"}, "example": "private, max-age=15"},
                "Vary": {"schema": {"type": "string"}, "example": "Authorization"},
            },
        },
        400: {"description": "Bad Request - Invalid page_token"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden - requires admin:all"},
    },
)
async def list_admin_jobs(
    request: Request,
    response: Response,
    user: UserInfo = Depends(require_perms(["admin:all"])),
    status_filter: list[str] | None = Query(
        None,
        alias="status",
        description="Filter by job status (repeatable). Valid values: queued, running, finished, failed, cancelled",
        examples=[["finished"], ["running", "queued"]],
    ),
    limit: int = Query(25, ge=1, le=50, description="Number of items per page (max 50, default 25)"),
    page_token: str | None = Query(
        None,
        description="Opaque pagination token (integer offset) from previous response's next_page_token. Returns 400 if invalid.",
        examples=["0", "25", "50"],
    ),
) -> Response:
    """List all jobs with admin-level status filtering and pagination."""
    from src.jobs.factory import get_stores
    from src.jobs.models import JobStatus
    from src.provenance import record_provenance
    from src.utils.principal import principal_identity

    # --- Get store implementations based on feature flag ---
    job_store_impl, _, _ = get_stores()

    # Parse status filter to enum values
    status_enums = None
    if status_filter:
        try:
            status_enums = [JobStatus(s) for s in status_filter]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid status filter: {e}")

    # Pagination with validation
    start_idx = 0
    if page_token:
        try:
            start_idx = int(page_token)
            if start_idx < 0:
                raise HTTPException(status_code=400, detail="Invalid page_token: offset must be non-negative")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid page_token: must be a valid offset integer")

    # List all jobs with optional status filter
    job_docs, total = await job_store_impl.list_all(
        status=status_enums[0] if status_enums and len(status_enums) == 1 else None,
        offset=start_idx,
        limit=limit + 1,  # Fetch one extra to check if there are more pages
    )

    # Check if we have more results
    has_more = len(job_docs) > limit
    if has_more:
        job_docs = job_docs[:limit]  # Trim to requested limit

    # When using multi-status filters, need to fetch more and filter in-memory
    # (Redis doesn't support multi-status index queries natively in this design)
    if status_enums and len(status_enums) > 1:
        # Fetch more to account for filtering
        all_jobs, total = await job_store_impl.list_all(
            status=None, offset=start_idx, limit=limit * 3  # Heuristic: fetch 3x to increase chances of filling page
        )
        filtered_jobs = [j for j in all_jobs if j.status in status_enums]
        job_docs = filtered_jobs[:limit]
        has_more = len(filtered_jobs) > limit

    # Calculate next token
    next_token = str(start_idx + len(job_docs)) if has_more else None

    # Total count (for multi-status, approximate from current page)
    total = start_idx + len(job_docs) + (1 if has_more else 0)

    # Build response items
    items = []
    for job_doc in job_docs:
        # Convert datetime to ISO string if needed
        created_ts = job_doc.created_at
        if hasattr(created_ts, "isoformat"):
            created_ts = created_ts.isoformat()
        if created_ts and not created_ts.endswith("Z"):
            created_ts = created_ts + "Z"

        updated_ts = job_doc.updated_at
        if hasattr(updated_ts, "isoformat"):
            updated_ts = updated_ts.isoformat()
        if updated_ts and not updated_ts.endswith("Z"):
            updated_ts = updated_ts + "Z"

        items.append(
            JobResponse(
                id=job_doc.id,
                type=job_doc.type,
                status=job_doc.status.value,
                created_at=created_ts,
                updated_at=updated_ts,
                tenant_id=job_doc.tenant_id,
                owner=job_doc.owner,
                result=job_doc.result,
            )
        )

    # Provenance audit
    with contextlib.suppress(Exception):
        record_provenance(
            actor="api",
            action="admin_jobs.list",
            resource="/admin/jobs",
            input={"filters": {"status": status_filter}, "limit": limit, "offset": start_idx},
            output={"count": len(items), "total": total},
            meta={"user": principal_identity(user)},
            success=True,
        )

    result_body = JobListResponse(
        items=items,
        next_page_token=next_token,
        has_more=has_more,
        total=total,
    )

    # Compute ETag including route and filter context
    body_dict = result_body.model_dump()
    etag_context = {
        "route": "admin_jobs",
        "filters": {
            "status": status_filter,
        },
    }
    etag = compute_etag(body_dict, context=etag_context)

    # Check If-None-Match
    if_none_match = request.headers.get("if-none-match", "").strip()
    if etag and if_none_match == etag:
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "Cache-Control": "private, max-age=30",
                "Vary": "Authorization",
            },
        )

    # Return 200
    return JSONResponse(
        content=body_dict,
        status_code=200,
        headers={
            "ETag": etag,
            "Cache-Control": "private, max-age=30",
            "Vary": "Authorization",
        },
    )


# Deprecated list endpoint - remove
@router.get(
    "/deprecated-list",
    response_model=JobListResponse,
    summary="List jobs (removed)",
    include_in_schema=False,
)
async def list_jobs_deprecated(
    page_size: int = Query(50, ge=1, le=1000),
    page_token: str | None = None,
    user: UserInfo = Depends(require_perms(["admin:all"])),
):
    # This endpoint has been removed in the current API shape. Return 404 to signal it's not available.
    raise HTTPException(status_code=404, detail="Not Found")


# Deprecated HEAD endpoint removed per API cleanup list. Use GET /v1/admin/jobs instead.


# Expose the canonical create action under the admin jobs prefix as well so
# `/v1/admin/jobs:create` is available. This forwards to the implementation
# in `src.routers.jobs`.
try:
    # Register a small forwarding endpoint so the colon-action is visible
    # under the admin mount point and uses the same auth/deps as the
    # canonical implementation.
    from fastapi import Request, Response

    from src.routers.jobs import (
        JobRequest,
        create_job,  # type: ignore
    )

    @router.post(
        "",
        summary="Create a background job (admin proxy)",
        description=(
            "POST /v1/admin/jobs – Create a job on behalf of a user (admin only)\n\n"
            "**Why we need this endpoint:**\n"
            "- **Admin testing**: Admins need to test job processing and debug issues without switching user accounts.\n"
            "- **Support operations**: Enables support staff to trigger jobs for users during troubleshooting.\n"
            "- **System maintenance**: Allows admins to start background tasks for system maintenance or data migration.\n"
            "- **Testing & QA**: Simplifies testing by letting admins create jobs without simulating user authentication.\n"
            "- Without this endpoint, admins would need separate credentials or tools to manage background job operations.\n\n"
            "**What it does:**\n"
            "- Creates a background job using the same logic as `/v1/jobs`\n"
            "- Allows admins to submit jobs through administrative tools\n"
            "- Returns job ID and status immediately (doesn't wait for completion)\n\n"
            "**Access:**\n"
            "- Requires `admin:all` permission\n"
            "- Regular users should use `/v1/jobs` instead\n"
            "- Job owner is still set to the authenticated admin's token subject\n\n"
            "**Behavior:**\n"
            "- **Idempotency**: Same behavior as `/v1/jobs` - use `Idempotency-Key` header to prevent duplicates\n"
            "- **Auto-deduplication**: Identical payloads are deduplicated within 24h window\n"
            "- **Job types**: Must be in allowed list (e.g., 'demo', 'test')\n"
            "- **Retention**: Jobs auto-expire (Redis: 10 days, Memory: 7 days)\n"
            "- **Forwarding**: This endpoint forwards to `/v1/jobs` implementation\n\n"
            "**Responses:**\n"
            '- 202: Accepted – New job created. Returns `{"id": "...", "status": "queued", "owner": "admin@example.com"}`\n'
            "- 200: OK – Idempotent replay. Returns existing job with `Idempotency-Replayed: true` header\n"
            "- 400: Bad Request – Unknown job type or invalid payload\n"
            "- 401: Unauthorized – Missing or invalid authentication token\n"
            "- 403: Forbidden – Requires admin:all permission\n"
            "- 422: Validation Error – Malformed request body\n\n"
            "**Examples:**\n"
            "```bash\n"
            "# Admin creates a job\n"
            "curl -X POST http://localhost:8000/v1/admin/jobs \\\n"
            '     -H "Authorization: Bearer $ADMIN_TOKEN" \\\n'
            '     -H "Content-Type: application/json" \\\n'
            '     -d \'{"type": "demo", "payload": {"duration_ms": 2000}}\'\n'
            "```"
        ),
        responses={
            202: {
                "description": "Accepted (new job queued)",
                "headers": {
                    "Location": {"schema": {"type": "string"}, "description": "Canonical URL to poll job status"},
                    "X-Request-Id": {"schema": {"type": "string"}, "description": "Unique identifier for this request"},
                    "Idempotency-Key": {"schema": {"type": "string"}, "description": "Echoed back from request header"},
                    "Idempotency-Replayed": {
                        "schema": {"type": "string"},
                        "description": "'false' for a freshly created job",
                    },
                    "Cache-Control": {"schema": {"type": "string"}},
                },
                "content": {
                    "application/json": {"example": {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "status": "queued"}}
                },
            },
            200: {
                "description": "OK (idempotent replay of existing logical job)",
                "headers": {
                    "Location": {"schema": {"type": "string"}},
                    "X-Request-Id": {"schema": {"type": "string"}, "description": "Unique identifier for this request"},
                    "Idempotency-Key": {"schema": {"type": "string"}, "description": "Echoed back from request header"},
                    "Idempotency-Replayed": {
                        "schema": {"type": "string"},
                        "description": "'true' when the supplied Idempotency-Key previously created a job",
                    },
                    "Cache-Control": {"schema": {"type": "string"}},
                },
                "content": {
                    "application/json": {"example": {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "status": "queued"}}
                },
            },
            400: {"description": "Bad Request – unknown job type or invalid payload"},
            403: {"description": "Forbidden – requires admin:all permission"},
            415: {"description": "Unsupported Media Type – missing or incorrect Content-Type header"},
            422: {"description": "Unprocessable Entity – schema validation failed"},
        },
    )
    async def create_job_proxy(
        req: JobRequest, request: Request, response: Response, user: UserInfo = Depends(require_perms(["admin:all"]))
    ):
        """Forward job creation requests to the main job handler.

        This proxy delegates to the canonical job creation handler to preserve consistent
        behavior and response headers. The JobRequest schema enables proper OpenAPI documentation.
        """
        # Call the create handler from jobs module and pass-through the Response so headers are set
        return await create_job(req, request, user, response)

except Exception:
    # best-effort: if jobs module isn't available, skip this registration
    pass


# Provide a proxy for cancelling jobs under the admin mount so tests may call
# `/v1/admin/jobs/{job_id}:cancel` which should delegate to canonical implementation.
try:
    from src.routers.jobs import cancel_job as cancel_job_canonical  # type: ignore

    @router.delete(
        "/{job_id}",
        summary="Cancel job (admin proxy)",
        description=(
            "DELETE /v1/admin/jobs/{job_id} – Cancel any user's job (admin only)\n\n"
            "**Why we need this endpoint:**\n"
            "- **Emergency control**: Admins need ability to stop runaway or problematic jobs from any user.\n"
            "- **System health**: Enables cancelling resource-intensive jobs that are degrading system performance.\n"
            "- **Support operations**: Allows support staff to cancel stuck jobs during user support sessions.\n"
            "- **Resource management**: Helps free up worker capacity by stopping unnecessary jobs.\n"
            "- Without this endpoint, admins would have no way to intervene and stop problematic jobs, risking system stability.\n\n"
            "**What it does:**\n"
            "- Cancels a background job owned by any user (system-wide access)\n"
            "- First successful cancel returns `202 Accepted`, subsequent calls return `200 OK`\n"
            "- Safe to retry (idempotent) – won't cause errors if already cancelled or finished\n\n"
            "**Access:**\n"
            "- Requires `admin:all` permission\n"
            "- Can cancel jobs owned by any user (admin override)\n"
            "- Regular users should use `/v1/jobs/{job_id}` to cancel their own jobs\n\n"
            "**Behavior:**\n"
            "- **Idempotency**: First cancel returns 202, all subsequent calls return 200 (safe to retry)\n"
            "- **Terminal states**: Already finished/failed/cancelled jobs return 200 with current status\n"
            "- **Atomicity**: Redis backend uses atomic Lua script for race-free cancellation\n"
            "- **Forwarding**: This endpoint forwards to `/v1/jobs/{job_id}` implementation with admin access\n\n"
            "**Responses:**\n"
            "- 202: Accepted – Job successfully transitioned to 'cancelled' state\n"
            "- 200: OK – Job already in terminal state (cancelled, finished, or failed)\n"
            "- 400: Bad Request – Invalid job_id format (must be UUID)\n"
            "- 401: Unauthorized – Missing or invalid authentication token\n"
            "- 403: Forbidden – Requires admin:all permission\n"
            "- 404: Not Found – Job doesn't exist\n\n"
            "**Examples:**\n"
            "```bash\n"
            "# Admin cancels any job\n"
            "curl -X DELETE http://localhost:8000/v1/admin/jobs/123e4567-e89b-12d3-a456-426614174000 \\\n"
            '     -H "Authorization: Bearer $ADMIN_TOKEN"\n'
            "```"
        ),
    )
    async def cancel_job_proxy(job_id: str, user: UserInfo = Depends(require_perms(["admin:all"]))):
        """Forward job cancellation requests to the canonical cancellation handler.

        Requires authentication. The canonical handler will perform authorization checks
        and return appropriate success or error responses.
        """
        return await cancel_job_canonical(job_id, user)

except Exception:
    pass
